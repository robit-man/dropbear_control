#include <cstdlib>
#include <fstream>
#include <iostream>
#include <memory>
#include <sstream>
#include <string>

#include "hardware_interface/component_parser.hpp"
#include "hardware_interface/system_interface.hpp"
#include "hardware_interface/types/hardware_component_params.hpp"
#include "pluginlib/class_loader.hpp"
#include "rclcpp/rclcpp.hpp"
#include "rclcpp_lifecycle/state.hpp"

int main(int argc, char ** argv)
{
  rclcpp::init(argc, argv);
  try
  {
    pluginlib::ClassLoader<hardware_interface::SystemInterface> loader(
      "hardware_interface", "hardware_interface::SystemInterface");
    auto instance = loader.createUniqueInstance(
      "myactuator_dropbear_hardware/DropbearSystemInterface");

    std::ifstream source(TEST_URDF_PATH);
    if (!source)
    {
      throw std::runtime_error("cannot open denied_hardware.urdf");
    }
    std::ostringstream buffer;
    buffer << source.rdbuf();
    const auto resources =
      hardware_interface::parse_control_resources_from_urdf(buffer.str());
    if (resources.size() != 1)
    {
      throw std::runtime_error("expected exactly one hardware resource");
    }

    hardware_interface::HardwareComponentParams params;
    params.hardware_info = resources.front();
    params.logger = rclcpp::get_logger("myactuator_plugin_load_test");
    params.clock = std::make_shared<rclcpp::Clock>(RCL_STEADY_TIME);
    if (instance->init(params) != hardware_interface::CallbackReturn::SUCCESS)
    {
      throw std::runtime_error("valid exact descriptor did not initialize");
    }
    if (instance->on_export_state_interfaces().size() != 4)
    {
      throw std::runtime_error("state interface export count differs");
    }
    if (instance->on_export_command_interfaces().size() != 3)
    {
      throw std::runtime_error("command interface export count differs");
    }
    if (
      instance->on_configure(rclcpp_lifecycle::State()) !=
      hardware_interface::CallbackReturn::FAILURE)
    {
      throw std::runtime_error("missing authority/adapter did not fail closed");
    }
    std::cout << "plugin_load_test: PASS (load, descriptor, interfaces, fail-closed)\n";
  }
  catch (const std::exception & error)
  {
    std::cerr << "plugin_load_test: FAIL: " << error.what() << "\n";
    rclcpp::shutdown();
    return EXIT_FAILURE;
  }
  rclcpp::shutdown();
  return EXIT_SUCCESS;
}
