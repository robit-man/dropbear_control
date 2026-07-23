#include "safety_supervisor.h"

#include <limits.h>

namespace myactuator {
namespace safety {

namespace {

uint32_t faultBit(Fault fault) {
    return static_cast<uint32_t>(fault);
}

}  // namespace

bool Prerequisites::operationalReady() const {
    return configuration_valid && expected_nodes_present && transport_ready &&
           safety_interlock_ready && external_faults_clear;
}

bool Prerequisites::safeToArm() const {
    return operationalReady() && motor_off_confirmed;
}

bool Prerequisites::safeToReset() const {
    return operationalReady() && motor_off_confirmed;
}

SafetySupervisor::SafetySupervisor(const Configuration& configuration)
    : configuration_(configuration),
      prerequisites_(),
      state_(State::BOOT),
      fault_mask_(0),
      lease_active_(false),
      lease_owner_id_(0),
      lease_deadline_ms_(0),
      shutdown_generation_(0),
      shutdown_deadline_ms_(0),
      time_initialized_(false),
      last_now_ms_(0),
      last_sequence_{} {}

State SafetySupervisor::state() const {
    return state_;
}

uint32_t SafetySupervisor::faultMask() const {
    return fault_mask_;
}

LeaseSnapshot SafetySupervisor::lease() const {
    LeaseSnapshot snapshot = {lease_active_, lease_owner_id_,
                              lease_deadline_ms_};
    return snapshot;
}

ShutdownSnapshot SafetySupervisor::shutdown() const {
    ShutdownSnapshot snapshot = {state_ == State::SHUTDOWN,
                                 shutdown_generation_,
                                 shutdown_deadline_ms_};
    return snapshot;
}

bool SafetySupervisor::outputsPermitted() const {
    return state_ == State::ENABLED && lease_active_;
}

bool SafetySupervisor::shutdownIntent() const {
    return state_ == State::SHUTDOWN || state_ == State::FAULT;
}

bool SafetySupervisor::configurationValid() const {
    return configuration_.session_id != 0 &&
           configuration_.minimum_lease_ms != 0 &&
           configuration_.maximum_lease_ms >=
               configuration_.minimum_lease_ms &&
           configuration_.maximum_shutdown_ms != 0 &&
           configuration_.allowed_owner_mask != 0 &&
           configuration_.reset_owner_mask != 0 &&
           (configuration_.reset_owner_mask &
            ~configuration_.allowed_owner_mask) == 0;
}

bool SafetySupervisor::ownerAllowed(uint32_t owner_id) const {
    if (owner_id == 0 || owner_id > kMaximumOwners) {
        return false;
    }
    const uint32_t bit = 1UL << (owner_id - 1);
    return (configuration_.allowed_owner_mask & bit) != 0;
}

bool SafetySupervisor::resetAllowed(uint32_t owner_id) const {
    if (!ownerAllowed(owner_id)) {
        return false;
    }
    const uint32_t bit = 1UL << (owner_id - 1);
    return (configuration_.reset_owner_mask & bit) != 0;
}

void SafetySupervisor::clearLease() {
    lease_active_ = false;
    lease_owner_id_ = 0;
    lease_deadline_ms_ = 0;
}

Result SafetySupervisor::enterShutdown(uint64_t now_ms) {
    clearLease();
    if (shutdown_generation_ == UINT64_MAX ||
        now_ms > UINT64_MAX -
                     static_cast<uint64_t>(configuration_.maximum_shutdown_ms)) {
        latchFault(Fault::TIME_OVERFLOW);
        return Result::TIME_OVERFLOW;
    }
    ++shutdown_generation_;
    shutdown_deadline_ms_ =
        now_ms + static_cast<uint64_t>(configuration_.maximum_shutdown_ms);
    state_ = State::SHUTDOWN;
    return Result::OK;
}

void SafetySupervisor::latchFault(Fault fault) {
    fault_mask_ |= faultBit(fault);
    clearLease();
    state_ = State::FAULT;
}

Result SafetySupervisor::observeTime(uint64_t now_ms) {
    if (time_initialized_ && now_ms < last_now_ms_) {
        latchFault(Fault::CLOCK_REGRESSION);
        return Result::CLOCK_REGRESSION;
    }
    time_initialized_ = true;
    last_now_ms_ = now_ms;
    return Result::OK;
}

Result SafetySupervisor::serviceLeaseExpiry(uint64_t now_ms) {
    if (!lease_active_ || now_ms < lease_deadline_ms_) {
        return Result::OK;
    }

    if (state_ == State::ARMED || state_ == State::ENABLED) {
        const Result shutdown_result = enterShutdown(now_ms);
        if (shutdown_result != Result::OK) {
            return shutdown_result;
        }
    } else {
        clearLease();
    }
    return Result::LEASE_EXPIRED;
}

Result SafetySupervisor::serviceShutdownTimeout(uint64_t now_ms) {
    if (state_ != State::SHUTDOWN || now_ms < shutdown_deadline_ms_) {
        return Result::OK;
    }
    latchFault(Fault::SHUTDOWN_TIMEOUT);
    return Result::MOTOR_OFF_NOT_CONFIRMED;
}

Result SafetySupervisor::serviceTimers(uint64_t now_ms) {
    Result result = serviceLeaseExpiry(now_ms);
    if (result != Result::OK) {
        return result;
    }
    return serviceShutdownTimeout(now_ms);
}

Result SafetySupervisor::validateAndConsumeStamp(const MessageStamp& stamp) {
    if (stamp.session_id != configuration_.session_id) {
        return Result::INVALID_SESSION;
    }
    if (!ownerAllowed(stamp.owner_id)) {
        return Result::INVALID_OWNER;
    }

    uint64_t& last_sequence = last_sequence_[stamp.owner_id - 1];
    if (stamp.sequence == 0 || stamp.sequence <= last_sequence) {
        return Result::REPLAYED_OR_OUT_OF_ORDER;
    }

    // A fresh message is consumed even when its requested transition is not
    // valid in the current state. This prevents a delayed invalid command from
    // becoming valid after a later state transition.
    last_sequence = stamp.sequence;
    return Result::OK;
}

Result SafetySupervisor::validateLeaseDuration(uint64_t now_ms,
                                               uint32_t duration_ms,
                                               uint64_t* deadline_ms) {
    if (duration_ms < configuration_.minimum_lease_ms ||
        duration_ms > configuration_.maximum_lease_ms) {
        return Result::INVALID_LEASE_DURATION;
    }
    if (now_ms > UINT64_MAX - static_cast<uint64_t>(duration_ms)) {
        latchFault(Fault::TIME_OVERFLOW);
        return Result::TIME_OVERFLOW;
    }
    *deadline_ms = now_ms + duration_ms;
    return Result::OK;
}

Result SafetySupervisor::beginDiscovery(uint64_t now_ms) {
    Result result = observeTime(now_ms);
    if (result != Result::OK) {
        return result;
    }
    if (state_ != State::BOOT) {
        return Result::INVALID_STATE;
    }
    if (!configurationValid()) {
        latchFault(Fault::CONFIGURATION_INVALID);
        return Result::CONFIGURATION_INVALID;
    }

    state_ = State::DISCOVERY;
    return Result::OK;
}

Result SafetySupervisor::completeDiscovery(
    uint64_t now_ms, const Prerequisites& prerequisites) {
    Result result = observeTime(now_ms);
    if (result != Result::OK) {
        return result;
    }
    if (state_ != State::DISCOVERY) {
        return Result::INVALID_STATE;
    }

    prerequisites_ = prerequisites;
    if (!prerequisites_.safeToArm()) {
        return Result::PREREQUISITES_NOT_MET;
    }

    state_ = State::DISABLED;
    return Result::OK;
}

Result SafetySupervisor::completeBoot(
    uint64_t now_ms, const Prerequisites& prerequisites) {
    Result result = beginDiscovery(now_ms);
    if (result != Result::OK) {
        return result;
    }
    return completeDiscovery(now_ms, prerequisites);
}

Result SafetySupervisor::updatePrerequisites(
    uint64_t now_ms, const Prerequisites& prerequisites) {
    Result result = observeTime(now_ms);
    if (result != Result::OK) {
        return result;
    }
    result = serviceTimers(now_ms);
    if (result != Result::OK) {
        return result;
    }

    prerequisites_ = prerequisites;
    if ((state_ == State::ARMED || state_ == State::ENABLED ||
         state_ == State::SHUTDOWN) &&
        !prerequisites_.operationalReady()) {
        latchFault(Fault::PREREQUISITE_LOST);
        return Result::PREREQUISITES_NOT_MET;
    }
    return Result::OK;
}

Result SafetySupervisor::tick(uint64_t now_ms) {
    Result result = observeTime(now_ms);
    if (result != Result::OK) {
        return result;
    }
    return serviceTimers(now_ms);
}

Result SafetySupervisor::acquireLease(uint64_t now_ms,
                                      const MessageStamp& stamp,
                                      uint32_t duration_ms) {
    Result result = observeTime(now_ms);
    if (result != Result::OK) {
        return result;
    }
    result = serviceTimers(now_ms);
    if (result != Result::OK) {
        return result;
    }
    result = validateAndConsumeStamp(stamp);
    if (result != Result::OK) {
        return result;
    }
    if (lease_active_ && lease_owner_id_ != stamp.owner_id) {
        return Result::OWNER_CONFLICT;
    }
    if (state_ != State::DISABLED) {
        return Result::INVALID_STATE;
    }
    if (!prerequisites_.safeToArm()) {
        return Result::PREREQUISITES_NOT_MET;
    }

    uint64_t deadline_ms = 0;
    result = validateLeaseDuration(now_ms, duration_ms, &deadline_ms);
    if (result != Result::OK) {
        return result;
    }

    lease_active_ = true;
    lease_owner_id_ = stamp.owner_id;
    lease_deadline_ms_ = deadline_ms;
    state_ = State::ARMED;
    return Result::OK;
}

Result SafetySupervisor::renewLease(uint64_t now_ms,
                                    const MessageStamp& stamp,
                                    uint32_t duration_ms) {
    Result result = observeTime(now_ms);
    if (result != Result::OK) {
        return result;
    }
    result = serviceTimers(now_ms);
    if (result != Result::OK) {
        return result;
    }
    result = validateAndConsumeStamp(stamp);
    if (result != Result::OK) {
        return result;
    }
    if (!lease_active_ ||
        (state_ != State::ARMED && state_ != State::ENABLED)) {
        return Result::INVALID_STATE;
    }
    if (lease_owner_id_ != stamp.owner_id) {
        return Result::OWNER_CONFLICT;
    }
    if (!prerequisites_.operationalReady()) {
        latchFault(Fault::PREREQUISITE_LOST);
        return Result::PREREQUISITES_NOT_MET;
    }

    uint64_t deadline_ms = 0;
    result = validateLeaseDuration(now_ms, duration_ms, &deadline_ms);
    if (result != Result::OK) {
        return result;
    }
    lease_deadline_ms_ = deadline_ms;
    return Result::OK;
}

Result SafetySupervisor::enable(uint64_t now_ms,
                                const MessageStamp& stamp) {
    Result result = observeTime(now_ms);
    if (result != Result::OK) {
        return result;
    }
    result = serviceTimers(now_ms);
    if (result != Result::OK) {
        return result;
    }
    result = validateAndConsumeStamp(stamp);
    if (result != Result::OK) {
        return result;
    }
    if (state_ != State::ARMED || !lease_active_) {
        return Result::INVALID_STATE;
    }
    if (lease_owner_id_ != stamp.owner_id) {
        return Result::OWNER_CONFLICT;
    }
    if (!prerequisites_.safeToArm()) {
        return Result::PREREQUISITES_NOT_MET;
    }

    state_ = State::ENABLED;
    return Result::OK;
}

Result SafetySupervisor::authorizeCommand(uint64_t now_ms,
                                          const MessageStamp& stamp) {
    Result result = observeTime(now_ms);
    if (result != Result::OK) {
        return result;
    }
    result = serviceTimers(now_ms);
    if (result != Result::OK) {
        return result;
    }
    result = validateAndConsumeStamp(stamp);
    if (result != Result::OK) {
        return result;
    }
    if (state_ != State::ENABLED || !lease_active_) {
        return Result::INVALID_STATE;
    }
    if (lease_owner_id_ != stamp.owner_id) {
        return Result::OWNER_CONFLICT;
    }
    if (!prerequisites_.operationalReady()) {
        latchFault(Fault::PREREQUISITE_LOST);
        return Result::PREREQUISITES_NOT_MET;
    }
    return Result::OK;
}

Result SafetySupervisor::requestShutdown(uint64_t now_ms,
                                         const MessageStamp& stamp) {
    Result result = observeTime(now_ms);
    if (result != Result::OK) {
        return result;
    }
    result = serviceTimers(now_ms);
    if (result != Result::OK) {
        return result;
    }
    result = validateAndConsumeStamp(stamp);
    if (result != Result::OK) {
        return result;
    }
    if (!lease_active_ ||
        (state_ != State::ARMED && state_ != State::ENABLED)) {
        return Result::INVALID_STATE;
    }
    if (lease_owner_id_ != stamp.owner_id) {
        return Result::OWNER_CONFLICT;
    }

    return enterShutdown(now_ms);
}

Result SafetySupervisor::acknowledgeShutdown(uint64_t now_ms,
                                             uint64_t shutdown_generation,
                                             bool motor_off_confirmed) {
    Result result = observeTime(now_ms);
    if (result != Result::OK) {
        return result;
    }
    if (state_ != State::SHUTDOWN) {
        return Result::INVALID_STATE;
    }
    result = serviceShutdownTimeout(now_ms);
    if (result != Result::OK) {
        return result;
    }
    if (shutdown_generation == 0 ||
        shutdown_generation != shutdown_generation_) {
        return Result::SHUTDOWN_ACK_MISMATCH;
    }
    if (!motor_off_confirmed) {
        return Result::MOTOR_OFF_NOT_CONFIRMED;
    }

    prerequisites_.motor_off_confirmed = true;
    state_ = State::DISABLED;
    return Result::OK;
}

Result SafetySupervisor::raiseFault(uint64_t now_ms, Fault fault) {
    Result result = observeTime(now_ms);
    if (result != Result::OK) {
        return result;
    }
    if (fault == Fault::NONE) {
        return Result::CONFIGURATION_INVALID;
    }
    latchFault(fault);
    return Result::OK;
}

Result SafetySupervisor::resetFault(
    uint64_t now_ms,
    const MessageStamp& stamp,
    const Prerequisites& prerequisites) {
    Result result = observeTime(now_ms);
    if (result != Result::OK) {
        return result;
    }
    result = validateAndConsumeStamp(stamp);
    if (result != Result::OK) {
        return result;
    }
    if (state_ != State::FAULT) {
        return Result::INVALID_STATE;
    }
    if (!configurationValid()) {
        latchFault(Fault::CONFIGURATION_INVALID);
        return Result::CONFIGURATION_INVALID;
    }
    if (!resetAllowed(stamp.owner_id)) {
        return Result::RESET_NOT_AUTHORIZED;
    }
    if (!prerequisites.safeToReset()) {
        if (!prerequisites.motor_off_confirmed) {
            return Result::MOTOR_OFF_NOT_CONFIRMED;
        }
        return Result::PREREQUISITES_NOT_MET;
    }

    prerequisites_ = prerequisites;
    fault_mask_ = 0;
    clearLease();
    state_ = State::BOOT;
    return Result::OK;
}

}  // namespace safety
}  // namespace myactuator
