#ifndef MYACTUATOR_DROPBEAR_HARDWARE__SEMANTIC_CORE_HPP_
#define MYACTUATOR_DROPBEAR_HARDWARE__SEMANTIC_CORE_HPP_

#include <cstdint>
#include <functional>
#include <memory>
#include <optional>
#include <string>
#include <utility>
#include <vector>

namespace myactuator_dropbear_hardware
{

enum class ControlLifecycle
{
  UNCONFIGURED,
  INACTIVE,
  ACTIVE,
  FAULTED,
  FINALIZED,
};

enum class ReturnDisposition
{
  SUCCESS,
  NOT_READY,
  INVALID,
  STALE,
  TIMEOUT,
  FAULT,
};

enum class CommandInterface
{
  POSITION,
  VELOCITY,
  EFFORT,
};

enum class StateInterface
{
  POSITION,
  VELOCITY,
  EFFORT,
  QAXIS_CURRENT,
};

enum class SignalValidity
{
  VALID,
  STALE,
  MISSING,
  FAULTED,
};

enum class SignalSource
{
  NATIVE_DRIVE,
  EXTERNAL_JOINT_SENSOR,
  REVIEWED_FUSION,
  SYNTHETIC_PLANT,
  REPLAY,
  UNAVAILABLE,
};

struct OperationResult
{
  ReturnDisposition disposition;
  std::string detail;

  bool succeeded() const noexcept;
};

struct JointInterfaceDescriptor
{
  std::string joint_name;
  std::string canonical_actuator_id;
  std::vector<CommandInterface> command_interfaces;
  std::vector<StateInterface> state_interfaces;
  double position_lower_rad;
  double position_upper_rad;
  double maximum_velocity_rad_s;
  double maximum_output_effort_nm;
  double maximum_current_a;
};

struct SystemInterfaceDescriptor
{
  std::string hardware_name;
  std::string canonical_configuration_digest;
  std::string accepted_graph_decision_id;
  std::string accepted_graph_sha256;
  std::string source_registry_generation_sha256;
  std::string graph_registry_generation_sha256;
  std::string simulator_catalog_generation_sha256;
  std::vector<JointInterfaceDescriptor> joints;
};

struct SessionContext
{
  std::string canonical_configuration_digest;
  std::string accepted_graph_decision_id;
  std::string accepted_graph_sha256;
  std::string source_registry_generation_sha256;
  std::string graph_registry_generation_sha256;
  std::uint64_t configuration_generation;
  std::string session_id;
  std::string session_owner;
};

struct CommandLease
{
  std::string lease_id;
  std::string lease_owner;
  std::uint64_t lease_sequence;
  std::uint64_t issued_monotonic_ns;
  std::uint64_t expires_monotonic_ns;
};

struct JointCommandValue
{
  std::string joint_name;
  CommandInterface interface;
  double value;
};

struct CommandBatch
{
  std::string simulator_catalog_generation_sha256;
  std::string source_registry_generation_sha256;
  std::string graph_registry_generation_sha256;
  std::uint64_t configuration_generation;
  std::uint64_t sequence;
  std::uint64_t issued_monotonic_ns;
  std::uint64_t deadline_monotonic_ns;
  std::vector<JointCommandValue> commands;
};

struct CommandIntent
{
  std::string canonical_actuator_id;
  CommandInterface interface;
  double value;
  double maximum_velocity_rad_s;
  double maximum_current_a;
  std::string canonical_configuration_digest;
  std::string accepted_graph_decision_id;
  std::string session_id;
  std::string lease_id;
  std::uint64_t lease_sequence;
  std::uint64_t issued_monotonic_ns;
  std::uint64_t deadline_monotonic_ns;
};

struct InterfaceValue
{
  std::optional<double> value;
  SignalValidity validity;
  SignalSource source;
  std::uint64_t source_age_ns;
  std::vector<std::string> provenance_refs;
};

struct JointStateSample
{
  std::string joint_name;
  std::string canonical_actuator_id;
  std::uint64_t sampled_monotonic_ns;
  std::uint64_t received_monotonic_ns;
  std::string fault_code;
  std::vector<std::pair<StateInterface, InterfaceValue>> interfaces;
};

struct ReadResult
{
  ReturnDisposition disposition;
  std::string detail;
  std::vector<JointStateSample> states;
};

using GenerationTuple = std::vector<std::string>;
using MonotonicClock = std::function<std::uint64_t()>;
using GenerationProvider = std::function<GenerationTuple()>;

class SessionPort
{
public:
  virtual ~SessionPort() = default;
  virtual OperationResult configure(const SessionContext & context) = 0;
  virtual OperationResult activate() = 0;
  virtual OperationResult open_handle(
    const std::string & canonical_actuator_id, const CommandLease & lease) = 0;
  virtual OperationResult submit(const CommandIntent & intent) = 0;
  virtual std::pair<OperationResult, JointStateSample> read_state(
    const std::string & joint_name, const std::string & canonical_actuator_id) = 0;
  virtual OperationResult deactivate() = 0;
  virtual void fault(const std::string & reason) noexcept = 0;
  virtual OperationResult cleanup() = 0;
  virtual OperationResult finalize() = 0;
};

class UnavailableSessionPort final : public SessionPort
{
public:
  OperationResult configure(const SessionContext & context) override;
  OperationResult activate() override;
  OperationResult open_handle(
    const std::string & canonical_actuator_id, const CommandLease & lease) override;
  OperationResult submit(const CommandIntent & intent) override;
  std::pair<OperationResult, JointStateSample> read_state(
    const std::string & joint_name, const std::string & canonical_actuator_id) override;
  OperationResult deactivate() override;
  void fault(const std::string & reason) noexcept override;
  OperationResult cleanup() override;
  OperationResult finalize() override;
};

class SemanticCore
{
public:
  SemanticCore(
    SystemInterfaceDescriptor descriptor, std::shared_ptr<SessionPort> session,
    MonotonicClock monotonic_clock, GenerationProvider generation_provider);

  const SystemInterfaceDescriptor & descriptor() const noexcept;
  ControlLifecycle state() const noexcept;
  std::uint64_t next_batch_sequence() const noexcept;

  OperationResult configure(
    std::uint64_t configuration_generation, const std::string & session_id,
    const std::string & session_owner);
  OperationResult activate(const CommandLease & lease);
  OperationResult write(const CommandBatch & batch);
  ReadResult read();
  OperationResult deactivate();
  OperationResult error(const std::string & reason);
  OperationResult cleanup();
  OperationResult shutdown();

  static void validate_descriptor(const SystemInterfaceDescriptor & descriptor);

private:
  std::optional<OperationResult> check_generations();
  const JointInterfaceDescriptor * joint(const std::string & name) const noexcept;
  CommandIntent intent(
    const JointCommandValue & item, const CommandBatch & batch,
    const JointInterfaceDescriptor & descriptor) const;

  SystemInterfaceDescriptor descriptor_;
  std::shared_ptr<SessionPort> session_;
  MonotonicClock clock_;
  GenerationProvider generation_provider_;
  ControlLifecycle state_{ControlLifecycle::UNCONFIGURED};
  std::uint64_t configuration_generation_{0};
  std::string session_id_;
  std::optional<CommandLease> lease_;
  std::uint64_t next_batch_sequence_{1};
};

std::string to_string(ControlLifecycle value);
std::string to_string(ReturnDisposition value);
std::string to_string(CommandInterface value);
std::string to_string(StateInterface value);
std::string to_string(SignalValidity value);
std::string to_string(SignalSource value);

CommandInterface command_interface_from_string(const std::string & value);
StateInterface state_interface_from_string(const std::string & value);

}  // namespace myactuator_dropbear_hardware

#endif  // MYACTUATOR_DROPBEAR_HARDWARE__SEMANTIC_CORE_HPP_
