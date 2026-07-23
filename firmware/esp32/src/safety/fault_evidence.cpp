#include "fault_evidence.h"

#include <limits.h>
#include <string.h>

namespace myactuator {
namespace safety {

namespace {

class Crc32c {
public:
    Crc32c() : value_(0xFFFFFFFFUL) {}

    void addByte(uint8_t byte) {
        value_ ^= byte;
        for (uint8_t bit = 0; bit < 8; ++bit) {
            const uint32_t mask =
                static_cast<uint32_t>(-(static_cast<int32_t>(value_ & 1U)));
            value_ = (value_ >> 1) ^ (0x82F63B78UL & mask);
        }
    }

    void addBool(bool value) {
        addByte(value ? 1U : 0U);
    }

    void addU16(uint16_t value) {
        for (uint8_t index = 0; index < 2; ++index) {
            addByte(static_cast<uint8_t>((value >> (index * 8U)) & 0xFFU));
        }
    }

    void addU32(uint32_t value) {
        for (uint8_t index = 0; index < 4; ++index) {
            addByte(static_cast<uint8_t>((value >> (index * 8U)) & 0xFFU));
        }
    }

    void addU64(uint64_t value) {
        for (uint8_t index = 0; index < 8; ++index) {
            addByte(static_cast<uint8_t>((value >> (index * 8U)) & 0xFFU));
        }
    }

    void addI64(int64_t value) {
        addU64(static_cast<uint64_t>(value));
    }

    uint32_t finish() const {
        return ~value_;
    }

private:
    uint32_t value_;
};

bool bytesAreZero(const uint8_t* bytes, size_t size) {
    for (size_t index = 0; index < size; ++index) {
        if (bytes[index] != 0) {
            return false;
        }
    }
    return true;
}

bool commandIsZero(const CommandFaultContext& command) {
    return !command.present && command.owner_id == 0 &&
           command.session_id == 0 && command.sequence == 0 &&
           command.deadline_ms == 0 && command.config_generation == 0 &&
           bytesAreZero(command.config_digest, kFaultConfigDigestSize) &&
           command.route_token == 0 && command.bus_id == 0 &&
           command.node_id == 0 && command.opcode == 0 &&
           command.requested_value_native == 0 &&
           command.admitted_value_native == 0;
}

bool feedbackIsZero(const FeedbackFaultContext& feedback) {
    return feedback.valid_mask == 0 && feedback.sample_generation == 0 &&
           feedback.sampled_at_ms == 0 && feedback.received_at_ms == 0 &&
           feedback.position_urad == 0 && feedback.velocity_urad_s == 0 &&
           feedback.q_axis_current_ma == 0 &&
           feedback.output_effort_unm == 0 && feedback.temperature_mk == 0 &&
           feedback.bus_voltage_mv == 0 &&
           feedback.following_error_urad == 0;
}

bool busIsZero(const BusFaultContext& bus) {
    return !bus.bus_off && bus.transmitted_frames == 0 &&
           bus.received_frames == 0 && bus.transmit_errors == 0 &&
           bus.receive_errors == 0 && bus.response_timeouts == 0 &&
           bus.recovery_attempts == 0 && bus.last_receive_ms == 0;
}

bool eventIsZero(const FaultEvent& event) {
    return event.boot_id == 0 && event.reason == FailureReason::NONE &&
           event.monotonic_ms == 0 && event.state_before == State::BOOT &&
           commandIsZero(event.command) && feedbackIsZero(event.feedback) &&
           busIsZero(event.bus);
}

void checksumCommand(Crc32c* crc, const CommandFaultContext& command) {
    crc->addBool(command.present);
    crc->addU32(command.owner_id);
    crc->addU32(command.session_id);
    crc->addU64(command.sequence);
    crc->addU64(command.deadline_ms);
    crc->addU64(command.config_generation);
    for (size_t index = 0; index < kFaultConfigDigestSize; ++index) {
        crc->addByte(command.config_digest[index]);
    }
    crc->addU16(command.route_token);
    crc->addByte(command.bus_id);
    crc->addByte(command.node_id);
    crc->addByte(command.opcode);
    crc->addI64(command.requested_value_native);
    crc->addI64(command.admitted_value_native);
}

void checksumFeedback(Crc32c* crc, const FeedbackFaultContext& feedback) {
    crc->addU32(feedback.valid_mask);
    crc->addU64(feedback.sample_generation);
    crc->addU64(feedback.sampled_at_ms);
    crc->addU64(feedback.received_at_ms);
    crc->addI64(feedback.position_urad);
    crc->addI64(feedback.velocity_urad_s);
    crc->addI64(feedback.q_axis_current_ma);
    crc->addI64(feedback.output_effort_unm);
    crc->addI64(feedback.temperature_mk);
    crc->addI64(feedback.bus_voltage_mv);
    crc->addI64(feedback.following_error_urad);
}

void checksumBus(Crc32c* crc, const BusFaultContext& bus) {
    crc->addBool(bus.bus_off);
    crc->addU64(bus.transmitted_frames);
    crc->addU64(bus.received_frames);
    crc->addU64(bus.transmit_errors);
    crc->addU64(bus.receive_errors);
    crc->addU64(bus.response_timeouts);
    crc->addU64(bus.recovery_attempts);
    crc->addU64(bus.last_receive_ms);
}

void checksumEvent(Crc32c* crc, const FaultEvent& event) {
    crc->addU32(event.boot_id);
    crc->addByte(static_cast<uint8_t>(event.reason));
    crc->addU64(event.monotonic_ms);
    crc->addByte(static_cast<uint8_t>(event.state_before));
    checksumCommand(crc, event.command);
    checksumFeedback(crc, event.feedback);
    checksumBus(crc, event.bus);
}

}  // namespace

const char* FailureReasonName(FailureReason reason) {
    switch (reason) {
        case FailureReason::NONE: return "NONE";
        case FailureReason::CONFIGURATION_MISMATCH:
            return "CONFIGURATION_MISMATCH";
        case FailureReason::BUS_OFF: return "BUS_OFF";
        case FailureReason::RESPONSE_BUDGET_EXCEEDED:
            return "RESPONSE_BUDGET_EXCEEDED";
        case FailureReason::DRIVE_CRITICAL: return "DRIVE_CRITICAL";
        case FailureReason::LOCAL_LIMIT: return "LOCAL_LIMIT";
        case FailureReason::REQUIRED_FEEDBACK_INVALID:
            return "REQUIRED_FEEDBACK_INVALID";
        case FailureReason::SAFE_ACTION_FAILED:
            return "SAFE_ACTION_FAILED";
        case FailureReason::EXTERNAL: return "EXTERNAL";
        case FailureReason::FAULT_EVIDENCE_INVALID:
            return "FAULT_EVIDENCE_INVALID";
    }
    return "UNKNOWN_FAILURE_REASON";
}

const char* FaultEvidenceResultName(FaultEvidenceResult result) {
    switch (result) {
        case FaultEvidenceResult::OK: return "OK";
        case FaultEvidenceResult::INVALID_ARGUMENT:
            return "INVALID_ARGUMENT";
        case FaultEvidenceResult::RECOVERY_ALREADY_COMPLETED:
            return "RECOVERY_ALREADY_COMPLETED";
        case FaultEvidenceResult::RECOVERY_REQUIRED:
            return "RECOVERY_REQUIRED";
        case FaultEvidenceResult::SNAPSHOT_MISSING:
            return "SNAPSHOT_MISSING";
        case FaultEvidenceResult::SNAPSHOT_CORRUPT:
            return "SNAPSHOT_CORRUPT";
        case FaultEvidenceResult::INVALID_EVENT: return "INVALID_EVENT";
        case FaultEvidenceResult::EVENT_RECORDED_WITH_OVERFLOW:
            return "EVENT_RECORDED_WITH_OVERFLOW";
        case FaultEvidenceResult::GENERATION_EXHAUSTED:
            return "GENERATION_EXHAUSTED";
        case FaultEvidenceResult::NOT_LATCHED: return "NOT_LATCHED";
        case FaultEvidenceResult::RESET_EVIDENCE_REQUIRED:
            return "RESET_EVIDENCE_REQUIRED";
        case FaultEvidenceResult::RESET_GENERATION_MISMATCH:
            return "RESET_GENERATION_MISMATCH";
        case FaultEvidenceResult::SUPERVISOR_DENIED:
            return "SUPERVISOR_DENIED";
    }
    return "UNKNOWN_FAULT_EVIDENCE_RESULT";
}

FaultEvidenceCore::FaultEvidenceCore(SafetySupervisor* supervisor,
                                     uint32_t boot_id)
    : supervisor_(supervisor),
      boot_id_(boot_id),
      recovery_complete_(false),
      last_generation_(0),
      record_() {
    clearRecord();
}

void FaultEvidenceCore::clearRecord() {
    memset(&record_, 0, sizeof(record_));
    record_.latched = false;
}

bool FaultEvidenceCore::validFailureReason(FailureReason reason) {
    return reason >= FailureReason::CONFIGURATION_MISMATCH &&
           reason <= FailureReason::FAULT_EVIDENCE_INVALID;
}

bool FaultEvidenceCore::validState(State state) {
    return state >= State::BOOT && state <= State::FAULT;
}

uint64_t FaultEvidenceCore::reasonBit(FailureReason reason) {
    if (!validFailureReason(reason)) {
        return 0;
    }
    return 1ULL << (static_cast<uint8_t>(reason) - 1U);
}

Fault FaultEvidenceCore::mapSupervisorFault(FailureReason reason) {
    switch (reason) {
        case FailureReason::CONFIGURATION_MISMATCH:
            return Fault::CONFIGURATION_MISMATCH;
        case FailureReason::BUS_OFF:
            return Fault::BUS_OFF;
        case FailureReason::RESPONSE_BUDGET_EXCEEDED:
            return Fault::RESPONSE_BUDGET_EXCEEDED;
        case FailureReason::DRIVE_CRITICAL:
            return Fault::DRIVE_CRITICAL;
        case FailureReason::LOCAL_LIMIT:
            return Fault::LOCAL_LIMIT;
        case FailureReason::REQUIRED_FEEDBACK_INVALID:
            return Fault::REQUIRED_FEEDBACK_INVALID;
        case FailureReason::FAULT_EVIDENCE_INVALID:
            return Fault::FAULT_EVIDENCE_INVALID;
        case FailureReason::SAFE_ACTION_FAILED:
        case FailureReason::EXTERNAL:
        case FailureReason::NONE:
            return Fault::EXTERNAL;
    }
    return Fault::FAULT_EVIDENCE_INVALID;
}

bool FaultEvidenceCore::eventValid(const FaultEvent& event) {
    if (event.boot_id == 0 || !validFailureReason(event.reason) ||
        !validState(event.state_before) ||
        (event.feedback.valid_mask & ~kKnownFeedbackMask) != 0) {
        return false;
    }

    if (!event.command.present) {
        if (!commandIsZero(event.command)) {
            return false;
        }
    } else {
        if (event.command.owner_id == 0 || event.command.session_id == 0 ||
            event.command.sequence == 0 ||
            event.command.config_generation == 0 ||
            bytesAreZero(event.command.config_digest,
                         kFaultConfigDigestSize) ||
            event.command.route_token == 0 || event.command.bus_id == 0 ||
            event.command.node_id == 0 || event.command.opcode == 0) {
            return false;
        }
    }

    if (event.feedback.valid_mask == 0) {
        if (!feedbackIsZero(event.feedback)) {
            return false;
        }
    } else if (event.feedback.sample_generation == 0 ||
               event.feedback.received_at_ms < event.feedback.sampled_at_ms) {
        return false;
    }
    return true;
}

bool FaultEvidenceCore::recordValid(const FaultRecord& record,
                                    uint64_t last_generation) {
    if (!record.latched) {
        if (record.generation != 0 || record.reason_mask != 0 ||
            record.stored_event_count != 0 ||
            record.total_event_count != 0 ||
            record.overflow_event_count != 0 ||
            record.last_event_boot_id != 0 ||
            record.last_event_monotonic_ms != 0) {
            return false;
        }
        for (size_t index = 0; index < kMaximumFaultEvents; ++index) {
            if (!eventIsZero(record.events[index])) {
                return false;
            }
        }
        return true;
    }

    if (record.generation == 0 || record.generation != last_generation ||
        record.stored_event_count == 0 ||
        record.stored_event_count > kMaximumFaultEvents ||
        record.total_event_count < record.stored_event_count ||
        record.overflow_event_count !=
            record.total_event_count - record.stored_event_count ||
        record.reason_mask == 0 || record.last_event_boot_id == 0) {
        return false;
    }

    uint64_t stored_reason_mask = 0;
    for (size_t index = 0; index < record.stored_event_count; ++index) {
        const FaultEvent& event = record.events[index];
        if (!eventValid(event)) {
            return false;
        }
        if (index > 0 &&
            event.boot_id == record.events[index - 1].boot_id &&
            event.monotonic_ms < record.events[index - 1].monotonic_ms) {
            return false;
        }
        stored_reason_mask |= reasonBit(event.reason);
    }
    for (size_t index = record.stored_event_count;
         index < kMaximumFaultEvents;
         ++index) {
        if (!eventIsZero(record.events[index])) {
            return false;
        }
    }

    if ((record.reason_mask & stored_reason_mask) != stored_reason_mask) {
        return false;
    }
    if (record.overflow_event_count == 0) {
        const FaultEvent& last =
            record.events[record.stored_event_count - 1U];
        if (record.reason_mask != stored_reason_mask ||
            record.last_event_boot_id != last.boot_id ||
            record.last_event_monotonic_ms != last.monotonic_ms) {
            return false;
        }
    }
    return true;
}

uint32_t FaultEvidenceCore::computeChecksum(
    const PersistentFaultSnapshot& snapshot) {
    Crc32c crc;
    crc.addU32(snapshot.magic);
    crc.addU16(snapshot.schema_major);
    crc.addU16(snapshot.schema_minor);
    crc.addU64(snapshot.last_generation);
    crc.addBool(snapshot.record.latched);
    crc.addU64(snapshot.record.generation);
    crc.addU64(snapshot.record.reason_mask);
    crc.addU32(snapshot.record.stored_event_count);
    crc.addU32(snapshot.record.total_event_count);
    crc.addU32(snapshot.record.overflow_event_count);
    crc.addU32(snapshot.record.last_event_boot_id);
    crc.addU64(snapshot.record.last_event_monotonic_ms);
    for (size_t index = 0; index < kMaximumFaultEvents; ++index) {
        checksumEvent(&crc, snapshot.record.events[index]);
    }
    return crc.finish();
}

FaultEvidenceResult FaultEvidenceCore::createInitialCleanSnapshot(
    PersistentFaultSnapshot* out) {
    if (out == NULL) {
        return FaultEvidenceResult::INVALID_ARGUMENT;
    }
    memset(out, 0, sizeof(*out));
    out->magic = kFaultSnapshotMagic;
    out->schema_major = kFaultSnapshotSchemaMajor;
    out->schema_minor = kFaultSnapshotSchemaMinor;
    out->checksum_crc32c = computeChecksum(*out);
    return FaultEvidenceResult::OK;
}

FaultEvidenceResult FaultEvidenceCore::latchRecoveryFailure(
    uint64_t now_ms,
    FaultEvidenceResult reported_result) {
    clearRecord();
    last_generation_ = 0;
    recovery_complete_ = true;

    FaultEvent event = {};
    event.boot_id = boot_id_;
    event.reason = FailureReason::FAULT_EVIDENCE_INVALID;
    event.monotonic_ms = now_ms;
    event.state_before =
        supervisor_ == NULL ? State::BOOT : supervisor_->state();
    const FaultEvidenceResult latch_result = appendAndLatch(event);
    if (latch_result == FaultEvidenceResult::SUPERVISOR_DENIED ||
        latch_result == FaultEvidenceResult::GENERATION_EXHAUSTED) {
        return latch_result;
    }
    return reported_result;
}

FaultEvidenceResult FaultEvidenceCore::recoverRequired(
    uint64_t now_ms,
    const PersistentFaultSnapshot* persisted) {
    if (recovery_complete_) {
        return FaultEvidenceResult::RECOVERY_ALREADY_COMPLETED;
    }
    if (supervisor_ == NULL || boot_id_ == 0) {
        return FaultEvidenceResult::INVALID_ARGUMENT;
    }
    if (supervisor_->state() != State::BOOT) {
        return latchRecoveryFailure(now_ms,
                                    FaultEvidenceResult::SUPERVISOR_DENIED);
    }
    if (persisted == NULL) {
        return latchRecoveryFailure(now_ms,
                                    FaultEvidenceResult::SNAPSHOT_MISSING);
    }
    if (persisted->magic != kFaultSnapshotMagic ||
        persisted->schema_major != kFaultSnapshotSchemaMajor ||
        persisted->schema_minor != kFaultSnapshotSchemaMinor ||
        persisted->checksum_crc32c != computeChecksum(*persisted) ||
        !recordValid(persisted->record, persisted->last_generation)) {
        return latchRecoveryFailure(now_ms,
                                    FaultEvidenceResult::SNAPSHOT_CORRUPT);
    }

    last_generation_ = persisted->last_generation;
    record_ = persisted->record;
    recovery_complete_ = true;
    if (!record_.latched) {
        return FaultEvidenceResult::OK;
    }

    const Result supervisor_result =
        supervisor_->raiseFault(now_ms, Fault::RESTORED_FAULT_LATCH);
    return supervisor_result == Result::OK
               ? FaultEvidenceResult::OK
               : FaultEvidenceResult::SUPERVISOR_DENIED;
}

bool FaultEvidenceCore::recoveryComplete() const {
    return recovery_complete_;
}

bool FaultEvidenceCore::boundTo(
    const SafetySupervisor* supervisor) const {
    return supervisor_ != NULL && supervisor_ == supervisor &&
           boot_id_ != 0;
}

bool FaultEvidenceCore::latched() const {
    return record_.latched;
}

uint64_t FaultEvidenceCore::generation() const {
    return record_.generation;
}

const FaultRecord& FaultEvidenceCore::record() const {
    return record_;
}

FaultEvidenceResult FaultEvidenceCore::appendAndLatch(
    const FaultEvent& supplied_event) {
    FaultEvent event = supplied_event;
    event.boot_id = boot_id_;

    if (!record_.latched) {
        if (last_generation_ == UINT64_MAX) {
            if (supervisor_ != NULL) {
                supervisor_->raiseFault(
                    event.monotonic_ms, Fault::FAULT_EVIDENCE_INVALID);
            }
            return FaultEvidenceResult::GENERATION_EXHAUSTED;
        }
        clearRecord();
        record_.latched = true;
        record_.generation = ++last_generation_;
    }

    const Result supervisor_result =
        supervisor_->raiseFault(event.monotonic_ms,
                                mapSupervisorFault(event.reason));
    if (supervisor_result != Result::OK) {
        return FaultEvidenceResult::SUPERVISOR_DENIED;
    }

    record_.reason_mask |= reasonBit(event.reason);
    ++record_.total_event_count;
    record_.last_event_boot_id = event.boot_id;
    record_.last_event_monotonic_ms = event.monotonic_ms;
    if (record_.stored_event_count < kMaximumFaultEvents) {
        record_.events[record_.stored_event_count] = event;
        ++record_.stored_event_count;
        return FaultEvidenceResult::OK;
    }
    ++record_.overflow_event_count;
    return FaultEvidenceResult::EVENT_RECORDED_WITH_OVERFLOW;
}

FaultEvidenceResult FaultEvidenceCore::latch(const FaultEvent& supplied_event) {
    if (supervisor_ == NULL || boot_id_ == 0) {
        return FaultEvidenceResult::INVALID_ARGUMENT;
    }
    if (!recovery_complete_) {
        return latchRecoveryFailure(supplied_event.monotonic_ms,
                                    FaultEvidenceResult::RECOVERY_REQUIRED);
    }

    FaultEvent event = supplied_event;
    event.boot_id = boot_id_;
    if (!eventValid(event) ||
        event.state_before != supervisor_->state()) {
        FaultEvent invalid = {};
        invalid.boot_id = boot_id_;
        invalid.reason = FailureReason::FAULT_EVIDENCE_INVALID;
        invalid.monotonic_ms = supplied_event.monotonic_ms;
        invalid.state_before = supervisor_->state();
        const FaultEvidenceResult latch_result = appendAndLatch(invalid);
        if (latch_result == FaultEvidenceResult::SUPERVISOR_DENIED ||
            latch_result == FaultEvidenceResult::GENERATION_EXHAUSTED) {
            return latch_result;
        }
        return FaultEvidenceResult::INVALID_EVENT;
    }
    return appendAndLatch(event);
}

FaultEvidenceResult FaultEvidenceCore::snapshot(
    PersistentFaultSnapshot* out) const {
    if (out == NULL) {
        return FaultEvidenceResult::INVALID_ARGUMENT;
    }
    if (!recovery_complete_) {
        return FaultEvidenceResult::RECOVERY_REQUIRED;
    }
    memset(out, 0, sizeof(*out));
    out->magic = kFaultSnapshotMagic;
    out->schema_major = kFaultSnapshotSchemaMajor;
    out->schema_minor = kFaultSnapshotSchemaMinor;
    out->last_generation = last_generation_;
    out->record = record_;
    out->checksum_crc32c = computeChecksum(*out);
    return FaultEvidenceResult::OK;
}

FaultEvidenceResult FaultEvidenceCore::reset(
    uint64_t now_ms,
    const MessageStamp& stamp,
    const Prerequisites& prerequisites,
    const FaultResetEvidence& evidence) {
    if (!recovery_complete_) {
        return FaultEvidenceResult::RECOVERY_REQUIRED;
    }
    if (!record_.latched) {
        return FaultEvidenceResult::NOT_LATCHED;
    }
    if (evidence.fault_generation != record_.generation) {
        return FaultEvidenceResult::RESET_GENERATION_MISMATCH;
    }
    if (!evidence.fault_record_durable || !evidence.root_cause_absent ||
        !evidence.motor_off_observed || !evidence.reset_event_durable) {
        return FaultEvidenceResult::RESET_EVIDENCE_REQUIRED;
    }

    const Result supervisor_result =
        supervisor_->resetFault(now_ms, stamp, prerequisites);
    if (supervisor_result != Result::OK) {
        return FaultEvidenceResult::SUPERVISOR_DENIED;
    }
    clearRecord();
    return FaultEvidenceResult::OK;
}

}  // namespace safety
}  // namespace myactuator
