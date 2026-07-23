#include "myactuator_dropbear_hardware/semantic_core.hpp"

#include <cmath>
#include <cstdlib>
#include <iomanip>
#include <iostream>
#include <map>
#include <memory>
#include <sstream>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace mad = myactuator_dropbear_hardware;

namespace
{

constexpr std::uint64_t kNow = 1000000;
const std::string kConfig(64, 'a');
const std::string kGraphSha(64, 'b');
const std::string kGraphId = "graphdecision-" + std::string(20, 'c');
const std::string kSource(64, 'd');
const std::string kGraph(64, 'e');
const std::string kCatalog(64, 'f');

int checks = 0;

void expect(bool condition, const std::string & label)
{
  ++checks;
  if (!condition)
  {
    throw std::runtime_error("expectation failed: " + label);
  }
}

mad::SystemInterfaceDescriptor descriptor()
{
  return {
    "dropbear-control-fixture",
    kConfig,
    kGraphId,
    kGraphSha,
    kSource,
    kGraph,
    kCatalog,
    {{
      "left-knee",
      "actuator-left-knee",
      {
        mad::CommandInterface::POSITION,
        mad::CommandInterface::VELOCITY,
        mad::CommandInterface::EFFORT,
      },
      {
        mad::StateInterface::POSITION,
        mad::StateInterface::VELOCITY,
        mad::StateInterface::EFFORT,
        mad::StateInterface::QAXIS_CURRENT,
      },
      -1.5,
      1.5,
      2.0,
      10.0,
      5.0,
    }}};
}

mad::CommandLease lease()
{
  return {"lease-controller", "controller-fixture", 7, kNow - 100, kNow + 100000};
}

mad::InterfaceValue present(
  double value, mad::SignalSource source = mad::SignalSource::SYNTHETIC_PLANT,
  mad::SignalValidity validity = mad::SignalValidity::VALID)
{
  return {value, validity, source, 10, {"fixture:reviewed-signal"}};
}

mad::InterfaceValue absent(mad::SignalValidity validity = mad::SignalValidity::MISSING)
{
  return {std::nullopt, validity, mad::SignalSource::UNAVAILABLE, 0, {}};
}

mad::JointStateSample sample()
{
  return {
    "left-knee",
    "actuator-left-knee",
    kNow - 10,
    kNow,
    "NONE",
    {
      {
        mad::StateInterface::POSITION,
        present(
          0.1, mad::SignalSource::EXTERNAL_JOINT_SENSOR,
          mad::SignalValidity::STALE),
      },
      {
        mad::StateInterface::VELOCITY,
        present(0.2, mad::SignalSource::REVIEWED_FUSION),
      },
      {
        mad::StateInterface::EFFORT,
        absent(mad::SignalValidity::FAULTED),
      },
      {
        mad::StateInterface::QAXIS_CURRENT,
        present(0.3, mad::SignalSource::NATIVE_DRIVE),
      },
    }};
}

class FakePort final : public mad::SessionPort
{
public:
  mad::OperationResult configure(const mad::SessionContext & context) override
  {
    configured = true;
    session_id = context.session_id;
    return ok("configured");
  }

  mad::OperationResult activate() override
  {
    if (!configured)
    {
      return {mad::ReturnDisposition::NOT_READY, "not configured"};
    }
    active = true;
    return ok("activated");
  }

  mad::OperationResult open_handle(
    const std::string & actuator_id, const mad::CommandLease &) override
  {
    if (!active || actuator_id != "actuator-left-knee")
    {
      return {mad::ReturnDisposition::STALE, "actuator not admitted"};
    }
    return ok("handle opened");
  }

  mad::OperationResult submit(const mad::CommandIntent & intent) override
  {
    if (!active)
    {
      return {mad::ReturnDisposition::FAULT, "inactive"};
    }
    commands.push_back(intent);
    return ok("submitted");
  }

  std::pair<mad::OperationResult, mad::JointStateSample> read_state(
    const std::string &, const std::string &) override
  {
    if (!active)
    {
      return {{mad::ReturnDisposition::FAULT, "inactive"}, {}};
    }
    return {ok("read"), state_sample};
  }

  mad::OperationResult deactivate() override
  {
    active = false;
    return ok("deactivated");
  }

  void fault(const std::string &) noexcept override
  {
    active = false;
    ++fault_count;
  }

  mad::OperationResult cleanup() override
  {
    active = false;
    configured = false;
    return ok("cleaned up");
  }

  mad::OperationResult finalize() override
  {
    return ok("finalized");
  }

  static mad::OperationResult ok(const std::string & detail)
  {
    return {mad::ReturnDisposition::SUCCESS, detail};
  }

  bool configured{false};
  bool active{false};
  std::string session_id;
  std::vector<mad::CommandIntent> commands;
  mad::JointStateSample state_sample{sample()};
  int fault_count{0};
};

struct Fixture
{
  std::uint64_t now{kNow};
  mad::GenerationTuple generations{kCatalog, kSource, kGraph};
  std::shared_ptr<FakePort> port{std::make_shared<FakePort>()};
  mad::SemanticCore core{
    descriptor(), port, [this]() {return now;}, [this]() {return generations;}};

  mad::OperationResult activate()
  {
    const auto configured = core.configure(3, "ros-session-one", "controller-fixture");
    if (!configured.succeeded())
    {
      return configured;
    }
    return core.activate(lease());
  }

  mad::CommandBatch batch(
    const std::vector<mad::JointCommandValue> & commands, std::uint64_t sequence = 1) const
  {
    return {
      kCatalog,
      kSource,
      kGraph,
      3,
      sequence,
      kNow,
      kNow + 1000,
      commands};
  }
};

std::string operation(
  const std::string & name, const mad::OperationResult & result, mad::ControlLifecycle state)
{
  return name + ":" + mad::to_string(result.disposition) + ":" + mad::to_string(state);
}

std::string fixed_value(const std::optional<double> & value)
{
  if (!value.has_value())
  {
    return "null";
  }
  std::ostringstream stream;
  stream << std::fixed << std::setprecision(6) << *value;
  return stream.str();
}

std::vector<std::string> parity_lines()
{
  std::vector<std::string> lines{
    "descriptor_fields=hardware_name,canonical_configuration_digest,"
    "accepted_graph_decision_id,accepted_graph_sha256,"
    "source_registry_generation_sha256,graph_registry_generation_sha256,"
    "simulator_catalog_generation_sha256,joints",
    "joint_fields=joint_name,canonical_actuator_id,command_interfaces,state_interfaces,"
    "position_lower_rad,position_upper_rad,maximum_velocity_rad_s,"
    "maximum_output_effort_nm,maximum_current_a"};

  {
    Fixture fixture;
    std::vector<std::string> operations;
    auto result = fixture.core.configure(3, "ros-session-one", "controller-fixture");
    operations.push_back(operation("configure", result, fixture.core.state()));
    result = fixture.core.activate(lease());
    operations.push_back(operation("activate", result, fixture.core.state()));
    result = fixture.core.deactivate();
    operations.push_back(operation("deactivate", result, fixture.core.state()));
    result = fixture.core.cleanup();
    operations.push_back(operation("cleanup", result, fixture.core.state()));
    result = fixture.core.shutdown();
    operations.push_back(operation("shutdown", result, fixture.core.state()));
    std::ostringstream line;
    line << "lifecycle=";
    for (std::size_t index = 0; index < operations.size(); ++index)
    {
      if (index) line << ";";
      line << operations[index];
    }
    lines.push_back(line.str());
  }

  {
    Fixture fixture;
    expect(fixture.activate().succeeded(), "write fixture activates");
    const std::vector<mad::JointCommandValue> command{
      {"left-knee", mad::CommandInterface::POSITION, 0.25}};
    auto stale = fixture.batch(command);
    stale.simulator_catalog_generation_sha256 = std::string(64, '0');
    auto timeout = fixture.batch(command);
    timeout.issued_monotonic_ns = kNow - 10;
    timeout.deadline_monotonic_ns = kNow;
    auto invalid = fixture.batch(
      {{"left-knee", mad::CommandInterface::POSITION, 2.0}});
    const auto stale_result = fixture.core.write(stale);
    const auto timeout_result = fixture.core.write(timeout);
    const auto invalid_result = fixture.core.write(invalid);
    const auto success_result = fixture.core.write(fixture.batch(command));
    const auto replay_result = fixture.core.write(fixture.batch(command));
    lines.push_back(
      "write=stale:" + mad::to_string(stale_result.disposition) +
      ";timeout:" + mad::to_string(timeout_result.disposition) +
      ";limit:" + mad::to_string(invalid_result.disposition) +
      ";success:" + mad::to_string(success_result.disposition) +
      ";replay:" + mad::to_string(replay_result.disposition));
  }

  {
    Fixture fixture;
    expect(fixture.activate().succeeded(), "read fixture activates");
    const auto result = fixture.core.read();
    expect(result.states.size() == 1, "one state returned");
    std::ostringstream line;
    line << "read=" << mad::to_string(result.disposition);
    for (const auto & item : result.states.front().interfaces)
    {
      line << ";" << mad::to_string(item.first) << ":" << fixed_value(item.second.value)
           << ":" << mad::to_string(item.second.validity)
           << ":" << mad::to_string(item.second.source);
    }
    lines.push_back(line.str());
  }

  {
    Fixture fixture;
    expect(fixture.activate().succeeded(), "revocation fixture activates");
    fixture.generations.front() = std::string(64, '9');
    const auto result = fixture.core.read();
    lines.push_back(
      "revocation=" + mad::to_string(result.disposition) + ":" +
      mad::to_string(fixture.core.state()));
  }
  return lines;
}

void run_assertions()
{
  {
    auto duplicate = descriptor();
    duplicate.joints.push_back(duplicate.joints.front());
    bool rejected = false;
    try
    {
      mad::SemanticCore::validate_descriptor(duplicate);
    }
    catch (const std::invalid_argument &)
    {
      rejected = true;
    }
    expect(rejected, "duplicate descriptor rejected");
  }
  {
    auto unavailable = std::make_shared<mad::UnavailableSessionPort>();
    mad::SemanticCore core{
      descriptor(), unavailable, []() {return kNow;},
      []() {return mad::GenerationTuple{kCatalog, kSource, kGraph};}};
    expect(
      core.configure(3, "ros-session-one", "controller-fixture").disposition ==
      mad::ReturnDisposition::NOT_READY,
      "unavailable adapter denies configure");
    expect(core.state() == mad::ControlLifecycle::UNCONFIGURED, "denial stays unconfigured");
  }
  const auto lines = parity_lines();
  expect(lines.size() == 6, "complete parity surface");
}

}  // namespace

int main(int argc, char ** argv)
{
  try
  {
    run_assertions();
    if (argc == 2 && std::string(argv[1]) == "--emit-parity")
    {
      for (const auto & line : parity_lines())
      {
        std::cout << line << "\n";
      }
    }
    else
    {
      std::cout << "semantic_core_test: PASS (" << checks << " assertions)\n";
    }
  }
  catch (const std::exception & error)
  {
    std::cerr << "semantic_core_test: FAIL: " << error.what() << "\n";
    return EXIT_FAILURE;
  }
  return EXIT_SUCCESS;
}
