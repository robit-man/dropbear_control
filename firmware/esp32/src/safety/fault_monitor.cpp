#include "fault_monitor.h"

namespace myactuator {
namespace safety {

namespace {

bool feedbackIsZero(const FeedbackFaultContext& feedback) {
    return feedback.valid_mask == 0 &&
           feedback.sample_generation == 0 &&
           feedback.sampled_at_ms == 0 &&
           feedback.received_at_ms == 0 &&
           feedback.position_urad == 0 &&
           feedback.velocity_urad_s == 0 &&
           feedback.q_axis_current_ma == 0 &&
           feedback.output_effort_unm == 0 &&
           feedback.temperature_mk == 0 &&
           feedback.bus_voltage_mv == 0 &&
           feedback.following_error_urad == 0;
}

}  // namespace

const char* FaultMonitorResultName(FaultMonitorResult result) {
    switch (result) {
        case FaultMonitorResult::OK: return "OK";
        case FaultMonitorResult::FAULT_LATCHED: return "FAULT_LATCHED";
        case FaultMonitorResult::FAULT_ACTIVE: return "FAULT_ACTIVE";
        case FaultMonitorResult::INVALID_MONITOR: return "INVALID_MONITOR";
        case FaultMonitorResult::RECOVERY_REQUIRED:
            return "RECOVERY_REQUIRED";
        case FaultMonitorResult::INVALID_POLICY: return "INVALID_POLICY";
        case FaultMonitorResult::CLOCK_REGRESSION:
            return "CLOCK_REGRESSION";
        case FaultMonitorResult::INVALID_SAMPLE: return "INVALID_SAMPLE";
        case FaultMonitorResult::EVIDENCE_DENIED: return "EVIDENCE_DENIED";
    }
    return "UNKNOWN_FAULT_MONITOR_RESULT";
}

FaultMonitor::FaultMonitor(SafetySupervisor* supervisor,
                           FaultEvidenceCore* evidence,
                           const FaultMonitorPolicy& policy)
    : supervisor_(supervisor),
      evidence_(evidence),
      policy_(policy),
      valid_(supervisor != NULL && evidence != NULL &&
             evidence->boundTo(supervisor)),
      policy_valid_(
          policy.maximum_consecutive_response_timeouts != 0 &&
          policy.required_feedback_mask != 0 &&
          (policy.required_feedback_mask & ~kKnownFeedbackMask) == 0 &&
          policy.maximum_feedback_age_ms != 0),
      time_initialized_(false),
      last_now_ms_(0),
      active_failure_mask_(0) {}

bool FaultMonitor::valid() const {
    return valid_ && policy_valid_;
}

uint32_t FaultMonitor::activeFailureMask() const {
    return active_failure_mask_;
}

FailureReason FaultMonitor::reasonForBit(uint32_t bit) {
    switch (bit) {
        case MONITOR_CONFIGURATION_MISMATCH:
            return FailureReason::CONFIGURATION_MISMATCH;
        case MONITOR_BUS_OFF:
            return FailureReason::BUS_OFF;
        case MONITOR_RESPONSE_BUDGET_EXCEEDED:
            return FailureReason::RESPONSE_BUDGET_EXCEEDED;
        case MONITOR_DRIVE_CRITICAL:
            return FailureReason::DRIVE_CRITICAL;
        case MONITOR_LOCAL_LIMIT:
            return FailureReason::LOCAL_LIMIT;
        case MONITOR_REQUIRED_FEEDBACK_INVALID:
            return FailureReason::REQUIRED_FEEDBACK_INVALID;
    }
    return FailureReason::FAULT_EVIDENCE_INVALID;
}

bool FaultMonitor::sampleStructurallyValid(
    const FaultMonitorSample& sample) const {
    if ((sample.feedback.valid_mask & ~kKnownFeedbackMask) != 0 ||
        sample.consecutive_response_timeouts >
            sample.bus.response_timeouts) {
        return false;
    }
    if (sample.feedback.valid_mask == 0) {
        return feedbackIsZero(sample.feedback);
    }
    return sample.feedback.sample_generation != 0 &&
           sample.feedback.received_at_ms >=
               sample.feedback.sampled_at_ms &&
           sample.feedback.received_at_ms <= sample.monotonic_ms;
}

bool FaultMonitor::feedbackRequiredInvalid(
    const FaultMonitorSample& sample) const {
    if ((sample.feedback.valid_mask & policy_.required_feedback_mask) !=
        policy_.required_feedback_mask) {
        return true;
    }
    return sample.monotonic_ms - sample.feedback.received_at_ms >
           policy_.maximum_feedback_age_ms;
}

uint32_t FaultMonitor::evaluateFailures(
    const FaultMonitorSample& sample) const {
    uint32_t failures = 0;
    if (!sample.configuration_consistent) {
        failures |= MONITOR_CONFIGURATION_MISMATCH;
    }
    if (sample.bus.bus_off) {
        failures |= MONITOR_BUS_OFF;
    }
    if (sample.consecutive_response_timeouts >
        policy_.maximum_consecutive_response_timeouts) {
        failures |= MONITOR_RESPONSE_BUDGET_EXCEEDED;
    }
    if (sample.drive_critical) {
        failures |= MONITOR_DRIVE_CRITICAL;
    }
    if (sample.local_limit_violated) {
        failures |= MONITOR_LOCAL_LIMIT;
    }
    if (feedbackRequiredInvalid(sample)) {
        failures |= MONITOR_REQUIRED_FEEDBACK_INVALID;
    }
    return failures;
}

FaultEvidenceResult FaultMonitor::latchIntegrityFault(uint64_t now_ms) {
    if (evidence_ == NULL) {
        return FaultEvidenceResult::INVALID_ARGUMENT;
    }
    FaultEvent event = {};
    event.reason = FailureReason::FAULT_EVIDENCE_INVALID;
    event.monotonic_ms = now_ms;
    event.state_before =
        supervisor_ == NULL ? State::BOOT : supervisor_->state();
    return evidence_->latch(event);
}

FaultMonitorReport FaultMonitor::observe(
    const FaultMonitorSample& sample) {
    FaultMonitorReport report = {};
    report.result = FaultMonitorResult::OK;
    report.evidence_result = FaultEvidenceResult::OK;
    report.active_failure_mask = active_failure_mask_;

    if (!valid_) {
        if (supervisor_ != NULL) {
            (void)supervisor_->raiseFault(
                sample.monotonic_ms, Fault::FAULT_EVIDENCE_INVALID);
        }
        report.result = FaultMonitorResult::INVALID_MONITOR;
        return report;
    }
    if (!policy_valid_) {
        report.evidence_result =
            latchIntegrityFault(sample.monotonic_ms);
        report.result = FaultMonitorResult::INVALID_POLICY;
        return report;
    }
    if (!evidence_->recoveryComplete()) {
        report.evidence_result =
            latchIntegrityFault(sample.monotonic_ms);
        report.result = FaultMonitorResult::RECOVERY_REQUIRED;
        return report;
    }
    if (time_initialized_ && sample.monotonic_ms < last_now_ms_) {
        report.evidence_result = latchIntegrityFault(last_now_ms_);
        report.result = FaultMonitorResult::CLOCK_REGRESSION;
        return report;
    }
    time_initialized_ = true;
    last_now_ms_ = sample.monotonic_ms;

    if (!sampleStructurallyValid(sample)) {
        report.evidence_result =
            latchIntegrityFault(sample.monotonic_ms);
        report.result = FaultMonitorResult::INVALID_SAMPLE;
        return report;
    }

    const uint32_t current_failures = evaluateFailures(sample);
    const uint32_t newly_active =
        current_failures & ~active_failure_mask_;
    active_failure_mask_ = current_failures;
    report.active_failure_mask = current_failures;
    report.newly_latched_mask = newly_active;
    if (newly_active == 0) {
        report.result = current_failures == 0
                            ? FaultMonitorResult::OK
                            : FaultMonitorResult::FAULT_ACTIVE;
        return report;
    }

    for (uint8_t bit_index = 0; bit_index < 6; ++bit_index) {
        const uint32_t bit = 1UL << bit_index;
        if ((newly_active & bit) == 0) {
            continue;
        }
        FaultEvent event = {};
        event.reason = reasonForBit(bit);
        event.monotonic_ms = sample.monotonic_ms;
        event.state_before = supervisor_->state();
        event.command = sample.command;
        event.feedback = sample.feedback;
        event.bus = sample.bus;
        ++report.events_attempted;
        report.evidence_result = evidence_->latch(event);
        if (report.evidence_result == FaultEvidenceResult::OK ||
            report.evidence_result ==
                FaultEvidenceResult::EVENT_RECORDED_WITH_OVERFLOW) {
            ++report.events_recorded;
            continue;
        }
        report.result =
            report.evidence_result == FaultEvidenceResult::INVALID_EVENT
                ? FaultMonitorResult::INVALID_SAMPLE
                : FaultMonitorResult::EVIDENCE_DENIED;
        return report;
    }
    report.result = FaultMonitorResult::FAULT_LATCHED;
    return report;
}

}  // namespace safety
}  // namespace myactuator
