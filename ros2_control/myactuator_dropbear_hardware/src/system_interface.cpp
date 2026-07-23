#include "myactuator_dropbear_hardware/system_interface.hpp"

#include <chrono>
#include <cmath>
#include <limits>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <utility>
#include <vector>

#include "hardware_interface/types/hardware_interface_return_values.hpp"
#include "pluginlib/class_list_macros.hpp"
#include "rclcpp/logging.hpp"

namespace myactuator_dropbear_hardware
{
namespace
{

const std::string & required(
  const std::unordered_map<std::string, std::string> & values, const std::string & key)
{
  const auto found = values.find(key);
  if (found == values.end() || found->second.empty())
  {
    throw std::invalid_argument("missing required parameter: " + key);
  }
  return found->second;
}

std::uint64_t parse_u64(const std::string & text, const std::string & label)
{
  std::size_t consumed = 0;
  const auto value = std::stoull(text, &consumed, 10);
  if (consumed != text.size())
  {
    throw std::invalid_argument(label + " must be an unsigned decimal integer");
  }
  return value;
}

double parse_double(const std::string & text, const std::string & label)
{
  std::size_t consumed = 0;
  const auto value = std::stod(text, &consumed);
  if (consumed != text.size() || !std::isfinite(value))
  {
    throw std::invalid_argument(label + " must be finite");
  }
  return value;
}

hardware_interface::return_type cycle_result(const OperationResult & result)
{
  switch (result.disposition)
  {
    case ReturnDisposition::SUCCESS:
      return hardware_interface::return_type::OK;
    case ReturnDisposition::NOT_READY:
    case ReturnDisposition::STALE:
    case ReturnDisposition::TIMEOUT:
    case ReturnDisposition::FAULT:
      return hardware_interface::return_type::DEACTIVATE;
    case ReturnDisposition::INVALID:
      return hardware_interface::return_type::ERROR;
  }
  return hardware_interface::return_type::ERROR;
}

}  // namespace

DropbearSystemInterface::DropbearSystemInterface()
: session_(std::make_shared<UnavailableSessionPort>())
{
}

std::uint64_t DropbearSystemInterface::monotonic_ns()
{
  const auto now = std::chrono::steady_clock::now().time_since_epoch();
  return static_cast<std::uint64_t>(
    std::chrono::duration_cast<std::chrono::nanoseconds>(now).count());
}

SystemInterfaceDescriptor DropbearSystemInterface::parse_descriptor(
  const hardware_interface::HardwareInfo & info) const
{
  SystemInterfaceDescriptor descriptor{
    info.name,
    required(info.hardware_parameters, "canonical_configuration_digest"),
    required(info.hardware_parameters, "accepted_graph_decision_id"),
    required(info.hardware_parameters, "accepted_graph_sha256"),
    required(info.hardware_parameters, "source_registry_generation_sha256"),
    required(info.hardware_parameters, "graph_registry_generation_sha256"),
    required(info.hardware_parameters, "simulator_catalog_generation_sha256"),
    {}};

  for (const auto & source_joint : info.joints)
  {
    JointInterfaceDescriptor joint{
      source_joint.name,
      required(source_joint.parameters, "canonical_actuator_id"),
      {},
      {},
      parse_double(
        required(source_joint.parameters, "position_lower_rad"), "position_lower_rad"),
      parse_double(
        required(source_joint.parameters, "position_upper_rad"), "position_upper_rad"),
      parse_double(
        required(source_joint.parameters, "maximum_velocity_rad_s"),
        "maximum_velocity_rad_s"),
      parse_double(
        required(source_joint.parameters, "maximum_output_effort_nm"),
        "maximum_output_effort_nm"),
      parse_double(
        required(source_joint.parameters, "maximum_current_a"), "maximum_current_a")};
    for (const auto & interface : source_joint.command_interfaces)
    {
      if (interface.data_type != "double")
      {
        throw std::invalid_argument("command interfaces must use double");
      }
      joint.command_interfaces.push_back(command_interface_from_string(interface.name));
    }
    for (const auto & interface : source_joint.state_interfaces)
    {
      if (interface.data_type != "double")
      {
        throw std::invalid_argument("state interfaces must use double");
      }
      joint.state_interfaces.push_back(state_interface_from_string(interface.name));
    }
    descriptor.joints.push_back(std::move(joint));
  }
  SemanticCore::validate_descriptor(descriptor);
  return descriptor;
}

CommandLease DropbearSystemInterface::parse_lease(
  const hardware_interface::HardwareInfo & info) const
{
  return {
    required(info.hardware_parameters, "lease_id"),
    required(info.hardware_parameters, "lease_owner"),
    parse_u64(required(info.hardware_parameters, "lease_sequence"), "lease_sequence"),
    parse_u64(
      required(info.hardware_parameters, "lease_issued_monotonic_ns"),
      "lease_issued_monotonic_ns"),
    parse_u64(
      required(info.hardware_parameters, "lease_expires_monotonic_ns"),
      "lease_expires_monotonic_ns")};
}

hardware_interface::CallbackReturn DropbearSystemInterface::on_init(
  const hardware_interface::HardwareComponentInterfaceParams & params)
{
  const auto base_result = hardware_interface::SystemInterface::on_init(params);
  if (base_result != hardware_interface::CallbackReturn::SUCCESS)
  {
    return base_result;
  }
  try
  {
    const auto descriptor = parse_descriptor(params.hardware_info);
    configuration_generation_ = parse_u64(
      required(params.hardware_info.hardware_parameters, "configuration_generation"),
      "configuration_generation");
    command_deadline_ns_ = parse_u64(
      required(params.hardware_info.hardware_parameters, "command_deadline_ns"),
      "command_deadline_ns");
    if (configuration_generation_ == 0 || command_deadline_ns_ == 0)
    {
      throw std::invalid_argument("configuration generation and command deadline must be positive");
    }
    session_id_ = required(params.hardware_info.hardware_parameters, "session_id");
    session_owner_ = required(params.hardware_info.hardware_parameters, "session_owner");
    lease_ = parse_lease(params.hardware_info);

    // The shipped plugin has no implicit authority service or physical adapter.
    // An empty generation tuple makes configure fail closed until those two
    // dependencies are deliberately injected by a later integration package.
    core_ = std::make_unique<SemanticCore>(
      descriptor, session_, &DropbearSystemInterface::monotonic_ns,
      []() {return GenerationTuple{};});
  }
  catch (const std::exception & error)
  {
    RCLCPP_ERROR(get_logger(), "MYACTUATOR descriptor rejected: %s", error.what());
    core_.reset();
    return hardware_interface::CallbackReturn::ERROR;
  }
  return hardware_interface::CallbackReturn::SUCCESS;
}

hardware_interface::CallbackReturn DropbearSystemInterface::callback_result(
  const OperationResult & result, bool critical) const
{
  if (result.succeeded())
  {
    return hardware_interface::CallbackReturn::SUCCESS;
  }
  RCLCPP_ERROR(get_logger(), "MYACTUATOR lifecycle denied: %s", result.detail.c_str());
  if (critical || result.disposition == ReturnDisposition::FAULT)
  {
    return hardware_interface::CallbackReturn::ERROR;
  }
  return hardware_interface::CallbackReturn::FAILURE;
}

hardware_interface::CallbackReturn DropbearSystemInterface::on_configure(
  const rclcpp_lifecycle::State &)
{
  if (!core_)
  {
    return hardware_interface::CallbackReturn::ERROR;
  }
  return callback_result(
    core_->configure(configuration_generation_, session_id_, session_owner_));
}

hardware_interface::CallbackReturn DropbearSystemInterface::on_activate(
  const rclcpp_lifecycle::State &)
{
  if (!core_)
  {
    return hardware_interface::CallbackReturn::ERROR;
  }
  return callback_result(core_->activate(lease_));
}

hardware_interface::CallbackReturn DropbearSystemInterface::on_deactivate(
  const rclcpp_lifecycle::State &)
{
  if (!core_)
  {
    return hardware_interface::CallbackReturn::ERROR;
  }
  return callback_result(core_->deactivate(), true);
}

hardware_interface::CallbackReturn DropbearSystemInterface::on_cleanup(
  const rclcpp_lifecycle::State &)
{
  if (!core_)
  {
    return hardware_interface::CallbackReturn::ERROR;
  }
  return callback_result(core_->cleanup(), true);
}

hardware_interface::CallbackReturn DropbearSystemInterface::on_shutdown(
  const rclcpp_lifecycle::State &)
{
  if (!core_)
  {
    return hardware_interface::CallbackReturn::ERROR;
  }
  return callback_result(core_->shutdown(), true);
}

hardware_interface::CallbackReturn DropbearSystemInterface::on_error(
  const rclcpp_lifecycle::State &)
{
  if (core_)
  {
    core_->error("ros2-control-error-transition");
  }
  return hardware_interface::CallbackReturn::ERROR;
}

hardware_interface::return_type DropbearSystemInterface::read(
  const rclcpp::Time &, const rclcpp::Duration &)
{
  if (!core_)
  {
    return hardware_interface::return_type::ERROR;
  }
  const auto result = core_->read();
  if (result.disposition != ReturnDisposition::SUCCESS)
  {
    return cycle_result({result.disposition, result.detail});
  }
  try
  {
    for (const auto & state : result.states)
    {
      for (const auto & item : state.interfaces)
      {
        const auto value =
          item.second.value.has_value() && item.second.validity == SignalValidity::VALID
            ? *item.second.value
            : std::numeric_limits<double>::quiet_NaN();
        const auto & handle = get_state_interface_handle(
          state.joint_name + "/" + to_string(item.first));
        if (!set_state(handle, value, false))
        {
          core_->error("state-interface-update-failed");
          return hardware_interface::return_type::DEACTIVATE;
        }
      }
    }
  }
  catch (const std::exception &)
  {
    core_->error("state-interface-mapping-failed");
    return hardware_interface::return_type::DEACTIVATE;
  }
  return hardware_interface::return_type::OK;
}

hardware_interface::return_type DropbearSystemInterface::write(
  const rclcpp::Time &, const rclcpp::Duration &)
{
  if (!core_)
  {
    return hardware_interface::return_type::ERROR;
  }
  std::vector<JointCommandValue> commands;
  try
  {
    for (const auto & joint : core_->descriptor().joints)
    {
      for (const auto interface : joint.command_interfaces)
      {
        const auto & handle = get_command_interface_handle(
          joint.joint_name + "/" + to_string(interface));
        double value = std::numeric_limits<double>::quiet_NaN();
        if (get_command(handle, value, false) && std::isfinite(value))
        {
          commands.push_back({joint.joint_name, interface, value});
        }
      }
    }
  }
  catch (const std::exception &)
  {
    core_->error("command-interface-mapping-failed");
    return hardware_interface::return_type::DEACTIVATE;
  }
  if (commands.empty())
  {
    return hardware_interface::return_type::OK;
  }
  const auto issued = monotonic_ns();
  if (issued > std::numeric_limits<std::uint64_t>::max() - command_deadline_ns_)
  {
    core_->error("command-deadline-overflow");
    return hardware_interface::return_type::DEACTIVATE;
  }
  const auto & descriptor = core_->descriptor();
  const CommandBatch batch{
    descriptor.simulator_catalog_generation_sha256,
    descriptor.source_registry_generation_sha256,
    descriptor.graph_registry_generation_sha256,
    configuration_generation_,
    core_->next_batch_sequence(),
    issued,
    issued + command_deadline_ns_,
    std::move(commands)};
  return cycle_result(core_->write(batch));
}

}  // namespace myactuator_dropbear_hardware

PLUGINLIB_EXPORT_CLASS(
  myactuator_dropbear_hardware::DropbearSystemInterface,
  hardware_interface::SystemInterface)
