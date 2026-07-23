#include "myactuator_dropbear_hardware/semantic_core.hpp"

#include <algorithm>
#include <cmath>
#include <regex>
#include <set>
#include <stdexcept>
#include <tuple>
#include <utility>

namespace myactuator_dropbear_hardware
{
namespace
{

const std::regex kSha256{"^[0-9a-f]{64}$"};
const std::regex kIdentifier{"^[a-z][a-z0-9-]{2,127}$"};
const std::regex kGraphDecision{"^(graphdecision|graphv2decision)-[0-9a-f]{20}$"};

const std::set<std::string> kCanonicalActuatorIds = []() {
  std::set<std::string> result;
  for (const auto & side : {"left", "right"})
  {
    for (const auto & joint :
      {"hip-yaw", "hip-roll", "hip-pitch", "knee", "inner-calf", "outer-calf"})
    {
      result.insert(std::string{"actuator-"} + side + "-" + joint);
    }
  }
  return result;
}();

void require(bool condition, const std::string & message)
{
  if (!condition)
  {
    throw std::invalid_argument(message);
  }
}

void require_sha(const std::string & value, const std::string & label)
{
  require(std::regex_match(value, kSha256), label + " must be sha256");
}

void require_identifier(const std::string & value, const std::string & label)
{
  require(std::regex_match(value, kIdentifier), label + " must be an exact identifier");
}

template<typename T>
bool unique_values(const std::vector<T> & values)
{
  return std::set<T>(values.begin(), values.end()).size() == values.size();
}

OperationResult unavailable()
{
  return {ReturnDisposition::NOT_READY, "no concrete session adapter is installed"};
}

bool finite_positive(double value)
{
  return std::isfinite(value) && value > 0.0;
}

}  // namespace

bool OperationResult::succeeded() const noexcept
{
  return disposition == ReturnDisposition::SUCCESS;
}

void SemanticCore::validate_descriptor(const SystemInterfaceDescriptor & descriptor)
{
  require_identifier(descriptor.hardware_name, "hardware_name");
  require_sha(descriptor.canonical_configuration_digest, "configuration digest");
  require(
    std::regex_match(descriptor.accepted_graph_decision_id, kGraphDecision),
    "accepted graph decision is invalid");
  require_sha(descriptor.accepted_graph_sha256, "graph digest");
  require_sha(descriptor.source_registry_generation_sha256, "source generation");
  require_sha(descriptor.graph_registry_generation_sha256, "graph generation");
  require_sha(descriptor.simulator_catalog_generation_sha256, "simulator catalog generation");
  require(!descriptor.joints.empty(), "system descriptor requires exact joints");

  std::set<std::string> joint_names;
  std::set<std::string> actuator_ids;
  for (const auto & joint : descriptor.joints)
  {
    require_identifier(joint.joint_name, "joint_name");
    require(
      kCanonicalActuatorIds.count(joint.canonical_actuator_id) == 1,
      "canonical actuator ID is not exact");
    require(
      !joint.command_interfaces.empty() && unique_values(joint.command_interfaces),
      "command interfaces must be unique typed values");
    require(
      !joint.state_interfaces.empty() && unique_values(joint.state_interfaces),
      "state interfaces must be unique typed values");
    require(
      std::isfinite(joint.position_lower_rad) && std::isfinite(joint.position_upper_rad) &&
      joint.position_lower_rad < joint.position_upper_rad,
      "position limits are invalid");
    require(finite_positive(joint.maximum_velocity_rad_s), "maximum velocity must be positive");
    require(
      finite_positive(joint.maximum_output_effort_nm), "maximum output effort must be positive");
    require(finite_positive(joint.maximum_current_a), "maximum current must be positive");
    require(joint_names.insert(joint.joint_name).second, "joint names are duplicated");
    require(
      actuator_ids.insert(joint.canonical_actuator_id).second,
      "actuator mappings are duplicated");
  }
}

SemanticCore::SemanticCore(
  SystemInterfaceDescriptor descriptor, std::shared_ptr<SessionPort> session,
  MonotonicClock monotonic_clock, GenerationProvider generation_provider)
: descriptor_(std::move(descriptor)),
  session_(std::move(session)),
  clock_(std::move(monotonic_clock)),
  generation_provider_(std::move(generation_provider))
{
  validate_descriptor(descriptor_);
  require(session_ != nullptr, "session port is required");
  require(static_cast<bool>(clock_), "monotonic clock is required");
  require(static_cast<bool>(generation_provider_), "generation provider is required");
}

const SystemInterfaceDescriptor & SemanticCore::descriptor() const noexcept
{
  return descriptor_;
}

ControlLifecycle SemanticCore::state() const noexcept
{
  return state_;
}

std::uint64_t SemanticCore::next_batch_sequence() const noexcept
{
  return next_batch_sequence_;
}

std::optional<OperationResult> SemanticCore::check_generations()
{
  GenerationTuple current;
  try
  {
    current = generation_provider_();
  }
  catch (...)
  {
    error("generation-provider-unavailable");
    return OperationResult{ReturnDisposition::STALE, "generation provider is unavailable"};
  }
  const GenerationTuple expected{
    descriptor_.simulator_catalog_generation_sha256,
    descriptor_.source_registry_generation_sha256,
    descriptor_.graph_registry_generation_sha256};
  if (current != expected)
  {
    error("authority-generation-changed");
    return OperationResult{
      ReturnDisposition::STALE, "catalog/source/graph generation changed"};
  }
  return std::nullopt;
}

OperationResult SemanticCore::configure(
  std::uint64_t configuration_generation, const std::string & session_id,
  const std::string & session_owner)
{
  if (state_ != ControlLifecycle::UNCONFIGURED)
  {
    return {ReturnDisposition::INVALID, "configure requires unconfigured state"};
  }
  if (const auto stale = check_generations())
  {
    return *stale;
  }
  try
  {
    require(configuration_generation > 0, "configuration generation must be positive");
    require_identifier(session_id, "session_id");
    require_identifier(session_owner, "session_owner");
  }
  catch (const std::invalid_argument & error)
  {
    return {ReturnDisposition::INVALID, error.what()};
  }
  const SessionContext context{
    descriptor_.canonical_configuration_digest,
    descriptor_.accepted_graph_decision_id,
    descriptor_.accepted_graph_sha256,
    descriptor_.source_registry_generation_sha256,
    descriptor_.graph_registry_generation_sha256,
    configuration_generation,
    session_id,
    session_owner};
  const auto result = session_->configure(context);
  if (!result.succeeded())
  {
    return result;
  }
  configuration_generation_ = configuration_generation;
  session_id_ = session_id;
  state_ = ControlLifecycle::INACTIVE;
  next_batch_sequence_ = 1;
  return {ReturnDisposition::SUCCESS, "configured"};
}

OperationResult SemanticCore::activate(const CommandLease & lease)
{
  if (state_ != ControlLifecycle::INACTIVE)
  {
    return {ReturnDisposition::INVALID, "activate requires inactive state"};
  }
  if (const auto stale = check_generations())
  {
    return *stale;
  }
  try
  {
    require_identifier(lease.lease_id, "lease_id");
    require_identifier(lease.lease_owner, "lease_owner");
    require(lease.lease_sequence > 0, "lease sequence must be positive");
    require(
      lease.expires_monotonic_ns > lease.issued_monotonic_ns,
      "lease expiry must follow issue time");
    const auto now = clock_();
    require(
      lease.issued_monotonic_ns <= now && now < lease.expires_monotonic_ns,
      "lease is not currently valid");
  }
  catch (const std::invalid_argument & exception)
  {
    this->error("activate-not-ready");
    return {ReturnDisposition::NOT_READY, exception.what()};
  }
  auto result = session_->activate();
  if (!result.succeeded())
  {
    error("activate-not-ready");
    return result;
  }
  for (const auto & joint_descriptor : descriptor_.joints)
  {
    result = session_->open_handle(joint_descriptor.canonical_actuator_id, lease);
    if (!result.succeeded())
    {
      error("activate-admission-denied");
      return result.disposition == ReturnDisposition::STALE
               ? result
               : OperationResult{ReturnDisposition::NOT_READY, result.detail};
    }
  }
  lease_ = lease;
  state_ = ControlLifecycle::ACTIVE;
  return {ReturnDisposition::SUCCESS, "activated"};
}

const JointInterfaceDescriptor * SemanticCore::joint(const std::string & name) const noexcept
{
  const auto found = std::find_if(
    descriptor_.joints.begin(), descriptor_.joints.end(),
    [&name](const auto & item) {return item.joint_name == name;});
  return found == descriptor_.joints.end() ? nullptr : &*found;
}

CommandIntent SemanticCore::intent(
  const JointCommandValue & item, const CommandBatch & batch,
  const JointInterfaceDescriptor & joint_descriptor) const
{
  require_identifier(item.joint_name, "command joint_name");
  require(std::isfinite(item.value), "command value must be finite");
  require(
    std::find(
      joint_descriptor.command_interfaces.begin(), joint_descriptor.command_interfaces.end(),
      item.interface) != joint_descriptor.command_interfaces.end(),
    "command interface is not admitted");
  if (item.interface == CommandInterface::POSITION)
  {
    require(
      joint_descriptor.position_lower_rad <= item.value &&
      item.value <= joint_descriptor.position_upper_rad,
      "position command exceeds admitted limits");
  }
  else if (item.interface == CommandInterface::VELOCITY)
  {
    require(
      std::abs(item.value) <= joint_descriptor.maximum_velocity_rad_s,
      "velocity command exceeds admitted limit");
  }
  else
  {
    require(
      std::abs(item.value) <= joint_descriptor.maximum_output_effort_nm,
      "effort command exceeds admitted limit");
  }
  require(lease_.has_value(), "command lease is unavailable");
  return CommandIntent{
    joint_descriptor.canonical_actuator_id,
    item.interface,
    item.value,
    joint_descriptor.maximum_velocity_rad_s,
    joint_descriptor.maximum_current_a,
    descriptor_.canonical_configuration_digest,
    descriptor_.accepted_graph_decision_id,
    session_id_,
    lease_->lease_id,
    lease_->lease_sequence,
    batch.issued_monotonic_ns,
    batch.deadline_monotonic_ns};
}

OperationResult SemanticCore::write(const CommandBatch & batch)
{
  if (state_ != ControlLifecycle::ACTIVE)
  {
    return {ReturnDisposition::NOT_READY, "write requires active state"};
  }
  if (const auto stale = check_generations())
  {
    return *stale;
  }
  const GenerationTuple actual{
    batch.simulator_catalog_generation_sha256,
    batch.source_registry_generation_sha256,
    batch.graph_registry_generation_sha256};
  const GenerationTuple expected{
    descriptor_.simulator_catalog_generation_sha256,
    descriptor_.source_registry_generation_sha256,
    descriptor_.graph_registry_generation_sha256};
  if (
    actual != expected || batch.configuration_generation != configuration_generation_ ||
    batch.sequence != next_batch_sequence_)
  {
    return {ReturnDisposition::STALE, "batch identity/generation/sequence is stale"};
  }
  const auto now = clock_();
  if (
    batch.issued_monotonic_ns > now || now >= batch.deadline_monotonic_ns ||
    batch.deadline_monotonic_ns <= batch.issued_monotonic_ns)
  {
    return {ReturnDisposition::TIMEOUT, "batch is early or expired"};
  }
  if (!lease_.has_value() || now >= lease_->expires_monotonic_ns ||
    batch.issued_monotonic_ns < lease_->issued_monotonic_ns ||
    batch.deadline_monotonic_ns > lease_->expires_monotonic_ns)
  {
    state_ = ControlLifecycle::FAULTED;
    session_->fault("joint-handle-lease-expired");
    return {ReturnDisposition::FAULT, "command timing is outside current lease/deadline"};
  }
  try
  {
    require(!batch.commands.empty(), "command batch is empty");
    std::set<std::pair<std::string, CommandInterface>> keys;
    std::vector<CommandIntent> intents;
    for (const auto & item : batch.commands)
    {
      require(keys.insert({item.joint_name, item.interface}).second, "duplicate command interface");
      const auto * joint_descriptor = joint(item.joint_name);
      require(joint_descriptor != nullptr, "command joint is not mapped");
      intents.push_back(intent(item, batch, *joint_descriptor));
    }
    for (const auto & command_intent : intents)
    {
      const auto result = session_->submit(command_intent);
      if (!result.succeeded())
      {
        state_ = ControlLifecycle::FAULTED;
        session_->fault("submit-failed");
        return {ReturnDisposition::FAULT, result.detail};
      }
    }
  }
  catch (const std::invalid_argument & error)
  {
    return {ReturnDisposition::INVALID, error.what()};
  }
  ++next_batch_sequence_;
  return {ReturnDisposition::SUCCESS, "write accepted"};
}

ReadResult SemanticCore::read()
{
  if (state_ != ControlLifecycle::ACTIVE)
  {
    return {ReturnDisposition::NOT_READY, "read requires active state", {}};
  }
  if (const auto stale = check_generations())
  {
    return {stale->disposition, stale->detail, {}};
  }
  if (!lease_.has_value() || clock_() >= lease_->expires_monotonic_ns)
  {
    state_ = ControlLifecycle::FAULTED;
    session_->fault("joint-handle-lease-expired");
    return {ReturnDisposition::FAULT, "joint handle lease expired", {}};
  }
  std::vector<JointStateSample> states;
  for (const auto & joint_descriptor : descriptor_.joints)
  {
    auto result = session_->read_state(
      joint_descriptor.joint_name, joint_descriptor.canonical_actuator_id);
    if (!result.first.succeeded())
    {
      state_ = ControlLifecycle::FAULTED;
      session_->fault("read-failed");
      return {ReturnDisposition::FAULT, result.first.detail, {}};
    }
    if (
      result.second.joint_name != joint_descriptor.joint_name ||
      result.second.canonical_actuator_id != joint_descriptor.canonical_actuator_id)
    {
      state_ = ControlLifecycle::FAULTED;
      session_->fault("state-identity-mismatch");
      return {ReturnDisposition::FAULT, "state identity differs from handle/session", {}};
    }
    states.push_back(std::move(result.second));
  }
  return {ReturnDisposition::SUCCESS, "read complete", std::move(states)};
}

OperationResult SemanticCore::deactivate()
{
  if (state_ != ControlLifecycle::ACTIVE)
  {
    return {ReturnDisposition::INVALID, "deactivate requires active state"};
  }
  const auto result = session_->deactivate();
  if (!result.succeeded())
  {
    state_ = ControlLifecycle::FAULTED;
    return {ReturnDisposition::FAULT, result.detail};
  }
  lease_.reset();
  state_ = ControlLifecycle::INACTIVE;
  return {ReturnDisposition::SUCCESS, "deactivated"};
}

OperationResult SemanticCore::error(const std::string & reason)
{
  if (state_ == ControlLifecycle::INACTIVE || state_ == ControlLifecycle::ACTIVE)
  {
    session_->fault(reason);
  }
  if (state_ != ControlLifecycle::UNCONFIGURED && state_ != ControlLifecycle::FINALIZED)
  {
    state_ = ControlLifecycle::FAULTED;
  }
  lease_.reset();
  return {ReturnDisposition::FAULT, reason};
}

OperationResult SemanticCore::cleanup()
{
  if (state_ != ControlLifecycle::INACTIVE && state_ != ControlLifecycle::FAULTED)
  {
    return {ReturnDisposition::INVALID, "cleanup requires inactive or faulted state"};
  }
  const auto result = session_->cleanup();
  if (!result.succeeded())
  {
    state_ = ControlLifecycle::FAULTED;
    return {ReturnDisposition::FAULT, result.detail};
  }
  lease_.reset();
  session_id_.clear();
  configuration_generation_ = 0;
  state_ = ControlLifecycle::UNCONFIGURED;
  return {ReturnDisposition::SUCCESS, "cleaned up"};
}

OperationResult SemanticCore::shutdown()
{
  if (state_ != ControlLifecycle::UNCONFIGURED)
  {
    return {ReturnDisposition::INVALID, "shutdown requires unconfigured state"};
  }
  const auto result = session_->finalize();
  if (!result.succeeded())
  {
    return {ReturnDisposition::INVALID, result.detail};
  }
  state_ = ControlLifecycle::FINALIZED;
  return {ReturnDisposition::SUCCESS, "finalized"};
}

OperationResult UnavailableSessionPort::configure(const SessionContext &)
{
  return unavailable();
}

OperationResult UnavailableSessionPort::activate()
{
  return unavailable();
}

OperationResult UnavailableSessionPort::open_handle(const std::string &, const CommandLease &)
{
  return unavailable();
}

OperationResult UnavailableSessionPort::submit(const CommandIntent &)
{
  return unavailable();
}

std::pair<OperationResult, JointStateSample> UnavailableSessionPort::read_state(
  const std::string &, const std::string &)
{
  return {unavailable(), JointStateSample{}};
}

OperationResult UnavailableSessionPort::deactivate()
{
  return unavailable();
}

void UnavailableSessionPort::fault(const std::string &) noexcept
{
}

OperationResult UnavailableSessionPort::cleanup()
{
  return {ReturnDisposition::SUCCESS, "unavailable session cleaned up"};
}

OperationResult UnavailableSessionPort::finalize()
{
  return {ReturnDisposition::SUCCESS, "unavailable session finalized"};
}

std::string to_string(ControlLifecycle value)
{
  switch (value)
  {
    case ControlLifecycle::UNCONFIGURED: return "unconfigured";
    case ControlLifecycle::INACTIVE: return "inactive";
    case ControlLifecycle::ACTIVE: return "active";
    case ControlLifecycle::FAULTED: return "faulted";
    case ControlLifecycle::FINALIZED: return "finalized";
  }
  throw std::invalid_argument("unknown lifecycle");
}

std::string to_string(ReturnDisposition value)
{
  switch (value)
  {
    case ReturnDisposition::SUCCESS: return "success";
    case ReturnDisposition::NOT_READY: return "not_ready";
    case ReturnDisposition::INVALID: return "invalid";
    case ReturnDisposition::STALE: return "stale";
    case ReturnDisposition::TIMEOUT: return "timeout";
    case ReturnDisposition::FAULT: return "fault";
  }
  throw std::invalid_argument("unknown return disposition");
}

std::string to_string(CommandInterface value)
{
  switch (value)
  {
    case CommandInterface::POSITION: return "position";
    case CommandInterface::VELOCITY: return "velocity";
    case CommandInterface::EFFORT: return "effort";
  }
  throw std::invalid_argument("unknown command interface");
}

std::string to_string(StateInterface value)
{
  switch (value)
  {
    case StateInterface::POSITION: return "position";
    case StateInterface::VELOCITY: return "velocity";
    case StateInterface::EFFORT: return "effort";
    case StateInterface::QAXIS_CURRENT: return "qaxis_current";
  }
  throw std::invalid_argument("unknown state interface");
}

std::string to_string(SignalValidity value)
{
  switch (value)
  {
    case SignalValidity::VALID: return "valid";
    case SignalValidity::STALE: return "stale";
    case SignalValidity::MISSING: return "missing";
    case SignalValidity::FAULTED: return "faulted";
  }
  throw std::invalid_argument("unknown signal validity");
}

std::string to_string(SignalSource value)
{
  switch (value)
  {
    case SignalSource::NATIVE_DRIVE: return "native_drive";
    case SignalSource::EXTERNAL_JOINT_SENSOR: return "external_joint_sensor";
    case SignalSource::REVIEWED_FUSION: return "reviewed_fusion";
    case SignalSource::SYNTHETIC_PLANT: return "synthetic_plant";
    case SignalSource::REPLAY: return "replay";
    case SignalSource::UNAVAILABLE: return "unavailable";
  }
  throw std::invalid_argument("unknown signal source");
}

CommandInterface command_interface_from_string(const std::string & value)
{
  if (value == "position") return CommandInterface::POSITION;
  if (value == "velocity") return CommandInterface::VELOCITY;
  if (value == "effort") return CommandInterface::EFFORT;
  throw std::invalid_argument("unknown command interface: " + value);
}

StateInterface state_interface_from_string(const std::string & value)
{
  if (value == "position") return StateInterface::POSITION;
  if (value == "velocity") return StateInterface::VELOCITY;
  if (value == "effort") return StateInterface::EFFORT;
  if (value == "qaxis_current") return StateInterface::QAXIS_CURRENT;
  throw std::invalid_argument("unknown state interface: " + value);
}

}  // namespace myactuator_dropbear_hardware
