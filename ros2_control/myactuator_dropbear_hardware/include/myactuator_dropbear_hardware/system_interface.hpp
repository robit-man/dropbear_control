#ifndef MYACTUATOR_DROPBEAR_HARDWARE__SYSTEM_INTERFACE_HPP_
#define MYACTUATOR_DROPBEAR_HARDWARE__SYSTEM_INTERFACE_HPP_

#include <cstdint>
#include <memory>
#include <string>

#include "hardware_interface/system_interface.hpp"
#include "myactuator_dropbear_hardware/semantic_core.hpp"
#include "rclcpp_lifecycle/state.hpp"

namespace myactuator_dropbear_hardware
{

class DropbearSystemInterface final : public hardware_interface::SystemInterface
{
public:
  DropbearSystemInterface();

  hardware_interface::CallbackReturn on_init(
    const hardware_interface::HardwareComponentInterfaceParams & params) override;
  hardware_interface::CallbackReturn on_configure(
    const rclcpp_lifecycle::State & previous_state) override;
  hardware_interface::CallbackReturn on_activate(
    const rclcpp_lifecycle::State & previous_state) override;
  hardware_interface::CallbackReturn on_deactivate(
    const rclcpp_lifecycle::State & previous_state) override;
  hardware_interface::CallbackReturn on_cleanup(
    const rclcpp_lifecycle::State & previous_state) override;
  hardware_interface::CallbackReturn on_shutdown(
    const rclcpp_lifecycle::State & previous_state) override;
  hardware_interface::CallbackReturn on_error(
    const rclcpp_lifecycle::State & previous_state) override;

  hardware_interface::return_type read(
    const rclcpp::Time & time, const rclcpp::Duration & period) override;
  hardware_interface::return_type write(
    const rclcpp::Time & time, const rclcpp::Duration & period) override;

private:
  static std::uint64_t monotonic_ns();
  SystemInterfaceDescriptor parse_descriptor(
    const hardware_interface::HardwareInfo & info) const;
  CommandLease parse_lease(const hardware_interface::HardwareInfo & info) const;
  hardware_interface::CallbackReturn callback_result(
    const OperationResult & result, bool critical = false) const;

  std::shared_ptr<SessionPort> session_;
  std::unique_ptr<SemanticCore> core_;
  std::uint64_t configuration_generation_{0};
  std::uint64_t command_deadline_ns_{0};
  std::string session_id_;
  std::string session_owner_;
  CommandLease lease_;
};

}  // namespace myactuator_dropbear_hardware

#endif  // MYACTUATOR_DROPBEAR_HARDWARE__SYSTEM_INTERFACE_HPP_
