#pragma once

// Portable multi-source safety fault arbiter.
//
// This allocation-free core performs no hardware I/O and does not infer
// physical motor-off. A trusted adapter supplies already typed configuration,
// bus, response, drive, limit and feedback observations. Rising failure edges
// are recorded through FaultEvidenceCore before the caller can continue normal
// gateway service.

#include <stdint.h>

#include "fault_evidence.h"

namespace myactuator {
namespace safety {

enum MonitorFailure : uint32_t {
    MONITOR_CONFIGURATION_MISMATCH = 1UL << 0,
    MONITOR_BUS_OFF = 1UL << 1,
    MONITOR_RESPONSE_BUDGET_EXCEEDED = 1UL << 2,
    MONITOR_DRIVE_CRITICAL = 1UL << 3,
    MONITOR_LOCAL_LIMIT = 1UL << 4,
    MONITOR_REQUIRED_FEEDBACK_INVALID = 1UL << 5,
};

static const uint32_t kKnownMonitorFailureMask =
    MONITOR_CONFIGURATION_MISMATCH | MONITOR_BUS_OFF |
    MONITOR_RESPONSE_BUDGET_EXCEEDED | MONITOR_DRIVE_CRITICAL |
    MONITOR_LOCAL_LIMIT | MONITOR_REQUIRED_FEEDBACK_INVALID;

struct FaultMonitorPolicy {
    uint32_t maximum_consecutive_response_timeouts;
    uint32_t required_feedback_mask;
    uint64_t maximum_feedback_age_ms;

    FaultMonitorPolicy(uint32_t response_timeout_budget,
                       uint32_t required_feedback_fields,
                       uint64_t feedback_age_ms)
        : maximum_consecutive_response_timeouts(response_timeout_budget),
          required_feedback_mask(required_feedback_fields),
          maximum_feedback_age_ms(feedback_age_ms) {}
};

struct FaultMonitorSample {
    uint64_t monotonic_ms;
    bool configuration_consistent;
    bool drive_critical;
    bool local_limit_violated;
    uint32_t consecutive_response_timeouts;
    CommandFaultContext command;
    FeedbackFaultContext feedback;
    BusFaultContext bus;
};

enum class FaultMonitorResult : uint8_t {
    OK = 0,
    FAULT_LATCHED,
    FAULT_ACTIVE,
    INVALID_MONITOR,
    RECOVERY_REQUIRED,
    INVALID_POLICY,
    CLOCK_REGRESSION,
    INVALID_SAMPLE,
    EVIDENCE_DENIED,
};

struct FaultMonitorReport {
    FaultMonitorResult result;
    FaultEvidenceResult evidence_result;
    uint32_t active_failure_mask;
    uint32_t newly_latched_mask;
    uint8_t events_attempted;
    uint8_t events_recorded;
};

const char* FaultMonitorResultName(FaultMonitorResult result);

class FaultMonitor {
public:
    FaultMonitor(SafetySupervisor* supervisor,
                 FaultEvidenceCore* evidence,
                 const FaultMonitorPolicy& policy);

    bool valid() const;
    uint32_t activeFailureMask() const;

    // Healthy samples never clear a durable latch. A failure is recorded on
    // its rising edge in the fixed MonitorFailure bit order. If multiple
    // failures rise in one sample, the first retains the pre-fault state and
    // later events are bounded secondary causes.
    FaultMonitorReport observe(const FaultMonitorSample& sample);

private:
    SafetySupervisor* supervisor_;
    FaultEvidenceCore* evidence_;
    FaultMonitorPolicy policy_;
    bool valid_;
    bool policy_valid_;
    bool time_initialized_;
    uint64_t last_now_ms_;
    uint32_t active_failure_mask_;

    static FailureReason reasonForBit(uint32_t bit);
    bool sampleStructurallyValid(const FaultMonitorSample& sample) const;
    bool feedbackRequiredInvalid(const FaultMonitorSample& sample) const;
    uint32_t evaluateFailures(const FaultMonitorSample& sample) const;
    FaultEvidenceResult latchIntegrityFault(uint64_t now_ms);
};

}  // namespace safety
}  // namespace myactuator
