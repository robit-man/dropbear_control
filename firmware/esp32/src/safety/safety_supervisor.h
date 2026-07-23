#pragma once

#include <stdint.h>

namespace myactuator {
namespace safety {

enum class State : uint8_t {
    BOOT = 0,
    DISCOVERY,
    DISABLED,
    ARMED,
    ENABLED,
    SHUTDOWN,
    FAULT,
};

enum class Result : uint8_t {
    OK = 0,
    INVALID_STATE,
    INVALID_OWNER,
    INVALID_SESSION,
    REPLAYED_OR_OUT_OF_ORDER,
    PREREQUISITES_NOT_MET,
    INVALID_LEASE_DURATION,
    OWNER_CONFLICT,
    LEASE_EXPIRED,
    MOTOR_OFF_NOT_CONFIRMED,
    RESET_NOT_AUTHORIZED,
    CLOCK_REGRESSION,
    CONFIGURATION_INVALID,
    TIME_OVERFLOW,
    SHUTDOWN_ACK_MISMATCH,
};

enum class Fault : uint32_t {
    NONE = 0,
    CONFIGURATION_INVALID = 1UL << 0,
    CLOCK_REGRESSION = 1UL << 1,
    TIME_OVERFLOW = 1UL << 2,
    PREREQUISITE_LOST = 1UL << 3,
    LEASE_EXPIRED = 1UL << 4,
    EXTERNAL = 1UL << 5,
    SHUTDOWN_TIMEOUT = 1UL << 6,
    CONFIGURATION_MISMATCH = 1UL << 7,
    BUS_OFF = 1UL << 8,
    RESPONSE_BUDGET_EXCEEDED = 1UL << 9,
    DRIVE_CRITICAL = 1UL << 10,
    LOCAL_LIMIT = 1UL << 11,
    REQUIRED_FEEDBACK_INVALID = 1UL << 12,
    FAULT_EVIDENCE_INVALID = 1UL << 13,
    RESTORED_FAULT_LATCH = 1UL << 14,
};

struct Configuration {
    // Must be a non-zero boot/session nonce supplied by the platform. Reusing
    // it across boots weakens the replay boundary and is therefore forbidden
    // by the integration contract even though this hardware-free core cannot
    // prove nonce freshness by itself.
    uint32_t session_id;
    uint32_t minimum_lease_ms;
    uint32_t maximum_lease_ms;
    uint32_t maximum_shutdown_ms;
    uint32_t allowed_owner_mask;
    uint32_t reset_owner_mask;

    Configuration(uint32_t session,
                  uint32_t minimum_lease,
                  uint32_t maximum_lease,
                  uint32_t maximum_shutdown,
                  uint32_t allowed_owners,
                  uint32_t reset_owners)
        : session_id(session),
          minimum_lease_ms(minimum_lease),
          maximum_lease_ms(maximum_lease),
          maximum_shutdown_ms(maximum_shutdown),
          allowed_owner_mask(allowed_owners),
          reset_owner_mask(reset_owners) {}
};

struct Prerequisites {
    bool configuration_valid;
    bool expected_nodes_present;
    bool transport_ready;
    bool safety_interlock_ready;
    bool external_faults_clear;
    bool motor_off_confirmed;

    Prerequisites()
        : configuration_valid(false),
          expected_nodes_present(false),
          transport_ready(false),
          safety_interlock_ready(false),
          external_faults_clear(false),
          motor_off_confirmed(false) {}

    bool operationalReady() const;
    bool safeToArm() const;
    bool safeToReset() const;
};

struct MessageStamp {
    uint32_t owner_id;
    uint32_t session_id;
    uint64_t sequence;

    MessageStamp(uint32_t owner, uint32_t session, uint64_t seq)
        : owner_id(owner), session_id(session), sequence(seq) {}
};

struct LeaseSnapshot {
    bool active;
    uint32_t owner_id;
    uint64_t deadline_ms;
};

struct ShutdownSnapshot {
    bool active;
    uint64_t generation;
    uint64_t deadline_ms;
};

// SafetySupervisor contains no hardware access and never assumes that a
// software state transition physically disabled an actuator. SHUTDOWN and
// FAULT expose a shutdown intent; a trusted adapter must separately confirm
// motor-off before the supervisor can return to DISABLED or reset a fault.
class SafetySupervisor {
public:
    explicit SafetySupervisor(const Configuration& configuration);

    State state() const;
    uint32_t faultMask() const;
    LeaseSnapshot lease() const;
    ShutdownSnapshot shutdown() const;
    bool outputsPermitted() const;
    bool shutdownIntent() const;

    Result beginDiscovery(uint64_t now_ms);
    Result completeDiscovery(uint64_t now_ms,
                             const Prerequisites& prerequisites);
    // Convenience for offline callers: executes beginDiscovery followed by
    // completeDiscovery at the same monotonic instant.
    Result completeBoot(uint64_t now_ms, const Prerequisites& prerequisites);
    Result updatePrerequisites(uint64_t now_ms,
                               const Prerequisites& prerequisites);
    Result tick(uint64_t now_ms);

    Result acquireLease(uint64_t now_ms,
                        const MessageStamp& stamp,
                        uint32_t duration_ms);
    Result renewLease(uint64_t now_ms,
                      const MessageStamp& stamp,
                      uint32_t duration_ms);
    Result enable(uint64_t now_ms, const MessageStamp& stamp);
    Result authorizeCommand(uint64_t now_ms, const MessageStamp& stamp);
    Result requestShutdown(uint64_t now_ms, const MessageStamp& stamp);
    Result acknowledgeShutdown(uint64_t now_ms,
                               uint64_t shutdown_generation,
                               bool motor_off_confirmed);

    Result raiseFault(uint64_t now_ms, Fault fault);
    Result resetFault(uint64_t now_ms,
                      const MessageStamp& stamp,
                      const Prerequisites& prerequisites);

private:
    static const uint32_t kMaximumOwners = 32;

    Configuration configuration_;
    Prerequisites prerequisites_;
    State state_;
    uint32_t fault_mask_;
    bool lease_active_;
    uint32_t lease_owner_id_;
    uint64_t lease_deadline_ms_;
    uint64_t shutdown_generation_;
    uint64_t shutdown_deadline_ms_;
    bool time_initialized_;
    uint64_t last_now_ms_;
    uint64_t last_sequence_[kMaximumOwners];

    bool configurationValid() const;
    bool ownerAllowed(uint32_t owner_id) const;
    bool resetAllowed(uint32_t owner_id) const;
    Result observeTime(uint64_t now_ms);
    Result serviceLeaseExpiry(uint64_t now_ms);
    Result serviceShutdownTimeout(uint64_t now_ms);
    Result serviceTimers(uint64_t now_ms);
    Result validateAndConsumeStamp(const MessageStamp& stamp);
    Result validateLeaseDuration(uint64_t now_ms,
                                 uint32_t duration_ms,
                                 uint64_t* deadline_ms);
    void clearLease();
    Result enterShutdown(uint64_t now_ms);
    void latchFault(Fault fault);
};

}  // namespace safety
}  // namespace myactuator
