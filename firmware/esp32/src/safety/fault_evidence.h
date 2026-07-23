#pragma once

// Allocation-free fault context and restart-latch semantics.
//
// This core performs no storage I/O and grants no motion authority. A trusted
// persistence adapter must durably store each returned snapshot and must pass
// the most recent snapshot back through recoverRequired() before normal boot
// processing. Missing or corrupt recovery input faults the supervisor closed.

#include <stddef.h>
#include <stdint.h>

#include "safety_supervisor.h"

namespace myactuator {
namespace safety {

static const uint32_t kFaultSnapshotMagic = 0x4D414646UL;  // "MAFF"
static const uint16_t kFaultSnapshotSchemaMajor = 1;
static const uint16_t kFaultSnapshotSchemaMinor = 0;
static const size_t kFaultConfigDigestSize = 32;
static const size_t kMaximumFaultEvents = 8;

enum class FailureReason : uint8_t {
    NONE = 0,
    CONFIGURATION_MISMATCH = 1,
    BUS_OFF = 2,
    RESPONSE_BUDGET_EXCEEDED = 3,
    DRIVE_CRITICAL = 4,
    LOCAL_LIMIT = 5,
    REQUIRED_FEEDBACK_INVALID = 6,
    SAFE_ACTION_FAILED = 7,
    EXTERNAL = 8,
    FAULT_EVIDENCE_INVALID = 9,
};

enum FeedbackField : uint32_t {
    FEEDBACK_POSITION = 1UL << 0,
    FEEDBACK_VELOCITY = 1UL << 1,
    FEEDBACK_Q_AXIS_CURRENT = 1UL << 2,
    FEEDBACK_OUTPUT_EFFORT = 1UL << 3,
    FEEDBACK_TEMPERATURE = 1UL << 4,
    FEEDBACK_BUS_VOLTAGE = 1UL << 5,
    FEEDBACK_FOLLOWING_ERROR = 1UL << 6,
};

static const uint32_t kKnownFeedbackMask =
    FEEDBACK_POSITION | FEEDBACK_VELOCITY | FEEDBACK_Q_AXIS_CURRENT |
    FEEDBACK_OUTPUT_EFFORT | FEEDBACK_TEMPERATURE |
    FEEDBACK_BUS_VOLTAGE | FEEDBACK_FOLLOWING_ERROR;

struct CommandFaultContext {
    bool present;
    uint32_t owner_id;
    uint32_t session_id;
    uint64_t sequence;
    uint64_t deadline_ms;
    uint64_t config_generation;
    uint8_t config_digest[kFaultConfigDigestSize];
    uint16_t route_token;
    uint8_t bus_id;
    uint8_t node_id;
    uint8_t opcode;
    int64_t requested_value_native;
    int64_t admitted_value_native;
};

struct FeedbackFaultContext {
    uint32_t valid_mask;
    uint64_t sample_generation;
    uint64_t sampled_at_ms;
    uint64_t received_at_ms;
    int64_t position_urad;
    int64_t velocity_urad_s;
    int64_t q_axis_current_ma;
    int64_t output_effort_unm;
    int64_t temperature_mk;
    int64_t bus_voltage_mv;
    int64_t following_error_urad;
};

struct BusFaultContext {
    bool bus_off;
    uint64_t transmitted_frames;
    uint64_t received_frames;
    uint64_t transmit_errors;
    uint64_t receive_errors;
    uint64_t response_timeouts;
    uint64_t recovery_attempts;
    uint64_t last_receive_ms;
};

struct FaultEvent {
    uint32_t boot_id;
    FailureReason reason;
    uint64_t monotonic_ms;
    State state_before;
    CommandFaultContext command;
    FeedbackFaultContext feedback;
    BusFaultContext bus;
};

struct FaultRecord {
    bool latched;
    uint64_t generation;
    uint64_t reason_mask;
    uint32_t stored_event_count;
    uint32_t total_event_count;
    uint32_t overflow_event_count;
    uint32_t last_event_boot_id;
    uint64_t last_event_monotonic_ms;
    FaultEvent events[kMaximumFaultEvents];
};

// The struct is a field container, not a raw on-storage ABI. Persistence
// adapters must serialize the named fields canonically and preserve checksum.
struct PersistentFaultSnapshot {
    uint32_t magic;
    uint16_t schema_major;
    uint16_t schema_minor;
    uint64_t last_generation;
    FaultRecord record;
    uint32_t checksum_crc32c;
};

struct FaultResetEvidence {
    uint64_t fault_generation;
    bool fault_record_durable;
    bool root_cause_absent;
    bool motor_off_observed;
    bool reset_event_durable;
};

enum class FaultEvidenceResult : uint8_t {
    OK = 0,
    INVALID_ARGUMENT,
    RECOVERY_ALREADY_COMPLETED,
    RECOVERY_REQUIRED,
    SNAPSHOT_MISSING,
    SNAPSHOT_CORRUPT,
    INVALID_EVENT,
    EVENT_RECORDED_WITH_OVERFLOW,
    GENERATION_EXHAUSTED,
    NOT_LATCHED,
    RESET_EVIDENCE_REQUIRED,
    RESET_GENERATION_MISMATCH,
    SUPERVISOR_DENIED,
};

const char* FailureReasonName(FailureReason reason);
const char* FaultEvidenceResultName(FaultEvidenceResult result);

class FaultEvidenceCore {
public:
    FaultEvidenceCore(SafetySupervisor* supervisor, uint32_t boot_id);

    // This factory is only for first provisioning. Reusing it after a prior
    // run would discard a latch and violates the integration contract.
    static FaultEvidenceResult createInitialCleanSnapshot(
        PersistentFaultSnapshot* out);

    // Must run once at boot. Missing, corrupt or semantically invalid input
    // returns an error and also places the supervisor in FAULT.
    FaultEvidenceResult recoverRequired(
        uint64_t now_ms,
        const PersistentFaultSnapshot* persisted);

    bool recoveryComplete() const;
    bool boundTo(const SafetySupervisor* supervisor) const;
    bool latched() const;
    uint64_t generation() const;
    const FaultRecord& record() const;

    // Records one P0 event and latches the supervisor. The supplied boot_id is
    // ignored and replaced with this core's immutable boot identity.
    FaultEvidenceResult latch(const FaultEvent& event);

    FaultEvidenceResult snapshot(PersistentFaultSnapshot* out) const;

    // Clearing requires explicit durable evidence assertions plus the
    // supervisor's existing identity, authorization and prerequisite guards.
    // Success returns the supervisor to BOOT, never ARMED or ENABLED.
    FaultEvidenceResult reset(
        uint64_t now_ms,
        const MessageStamp& stamp,
        const Prerequisites& prerequisites,
        const FaultResetEvidence& evidence);

private:
    SafetySupervisor* supervisor_;
    uint32_t boot_id_;
    bool recovery_complete_;
    uint64_t last_generation_;
    FaultRecord record_;

    static bool validFailureReason(FailureReason reason);
    static bool validState(State state);
    static bool eventValid(const FaultEvent& event);
    static bool recordValid(const FaultRecord& record,
                            uint64_t last_generation);
    static uint64_t reasonBit(FailureReason reason);
    static Fault mapSupervisorFault(FailureReason reason);
    static uint32_t computeChecksum(
        const PersistentFaultSnapshot& snapshot);

    void clearRecord();
    FaultEvidenceResult latchRecoveryFailure(
        uint64_t now_ms,
        FaultEvidenceResult reported_result);
    FaultEvidenceResult appendAndLatch(const FaultEvent& event);
};

}  // namespace safety
}  // namespace myactuator
