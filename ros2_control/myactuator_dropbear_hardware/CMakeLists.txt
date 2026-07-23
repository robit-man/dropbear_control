cmake_minimum_required(VERSION 3.16)
project(myactuator_dropbear_hardware VERSION 0.1.0 LANGUAGES CXX)

if(NOT CMAKE_CXX_STANDARD)
  set(CMAKE_CXX_STANDARD 17)
endif()
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

find_package(ament_cmake REQUIRED)
find_package(hardware_interface REQUIRED)
find_package(pluginlib REQUIRED)
find_package(rclcpp REQUIRED)
find_package(rclcpp_lifecycle REQUIRED)

add_library(myactuator_dropbear_semantic_core
  src/semantic_core.cpp
)
set_target_properties(myactuator_dropbear_semantic_core PROPERTIES POSITION_INDEPENDENT_CODE ON)
target_include_directories(myactuator_dropbear_semantic_core
  PUBLIC
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
    $<INSTALL_INTERFACE:include>
)
target_compile_options(myactuator_dropbear_semantic_core PRIVATE -Wall -Wextra -Wpedantic)

add_library(myactuator_dropbear_system_interface SHARED
  src/system_interface.cpp
)
target_include_directories(myactuator_dropbear_system_interface
  PUBLIC
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
    $<INSTALL_INTERFACE:include>
)
target_link_libraries(
  myactuator_dropbear_system_interface
  myactuator_dropbear_semantic_core
)
ament_target_dependencies(
  myactuator_dropbear_system_interface
  hardware_interface
  pluginlib
  rclcpp
  rclcpp_lifecycle
)
target_compile_options(myactuator_dropbear_system_interface PRIVATE -Wall -Wextra -Wpedantic)

pluginlib_export_plugin_description_file(
  hardware_interface
  myactuator_dropbear_hardware.xml
)

install(
  DIRECTORY include/
  DESTINATION include
)
install(
  TARGETS
    myactuator_dropbear_semantic_core
    myactuator_dropbear_system_interface
  EXPORT export_myactuator_dropbear_hardware
  ARCHIVE DESTINATION lib
  LIBRARY DESTINATION lib
  RUNTIME DESTINATION bin
  INCLUDES DESTINATION include
)

if(BUILD_TESTING)
  enable_testing()

  add_executable(semantic_core_test test/semantic_core_test.cpp)
  target_link_libraries(semantic_core_test PRIVATE myactuator_dropbear_semantic_core)
  target_compile_options(semantic_core_test PRIVATE -Wall -Wextra -Wpedantic)
  add_test(NAME semantic_core_test COMMAND semantic_core_test)

  add_executable(plugin_load_test test/plugin_load_test.cpp)
  ament_target_dependencies(plugin_load_test hardware_interface pluginlib rclcpp)
  target_compile_definitions(
    plugin_load_test
    PRIVATE TEST_URDF_PATH="${CMAKE_CURRENT_SOURCE_DIR}/test/denied_hardware.urdf"
  )
  target_compile_options(plugin_load_test PRIVATE -Wall -Wextra -Wpedantic)
  add_test(NAME plugin_load_test COMMAND plugin_load_test)
endif()

ament_export_targets(export_myactuator_dropbear_hardware HAS_LIBRARY_TARGET)
ament_export_dependencies(hardware_interface pluginlib rclcpp rclcpp_lifecycle)
ament_package()
