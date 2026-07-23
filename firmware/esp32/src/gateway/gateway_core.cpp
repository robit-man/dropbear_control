#include "gateway_core.h"

#include <limits.h>
#include <string.h>

namespace myactuator {
namespace gateway {

namespace {

uint8_t Opcode(rmd_v44::Command command) {
    return static_cast<uint8_t>(command);
}

Code ConfigDenialCode(safety::ConfigDecision decision) {
    if (decision == safety::ConfigDecision::COMMAND_GENERATION_REPLAYED) {
        return Code::REPLAY_REJECTED;
    }
    return Code::CONFIG_DENIED;
}

Code SafetyDenialCode(safety::Result result) {
    if (result == safety::Result::REPLAYED_OR_OUT_OF_ORDER) {
        return Code::REPLAY_REJECTED;
    }
    if (result == safety::Result::LEASE_EXPIRED) {
        return Code::LEASE_EXPIRED;
    }
    return Code::SAFETY_DENIED;
}

}  // namespace

const char* CodeName(Code code) {
    switch (code) {
        case Code::OK: return "OK";
        case Code::CORE_INVALID: return "CORE_INVALID";
        case Code::ROUTE_NOT_FOUND: return "ROUTE_NOT_FOUND";
        case Code::ROUTE_MISMATCH: return "ROUTE_MISMATCH";
        case Code::OWNER_MISMATCH: return "OWNER_MISMATCH";
        case Code::INVALID_REQUEST_FRAME: return "INVALID_REQUEST_FRAME";
        case Code::OPCODE_NOT_ALLOWED: return "OPCODE_NOT_ALLOWED";
        case Code::TRAFFIC_CLASS_MISMATCH: return "TRAFFIC_CLASS_MISMATCH";
        case Code::BRAKE_UNSUPPORTED: return "BRAKE_UNSUPPORTED";
        case Code::SAFETY_OPCODE_WRONG_LANE: return "SAFETY_OPCODE_WRONG_LANE";
        case Code::DEADLINE_INVALID: return "DEADLINE_INVALID";
        case Code::DEADLINE_EXPIRED: return "DEADLINE_EXPIRED";
        case Code::CONTROL_QUEUE_FULL: return "CONTROL_QUEUE_FULL";
        case Code::DIAGNOSTIC_QUEUE_FULL: return "DIAGNOSTIC_QUEUE_FULL";
        case Code::CONFIG_DENIED: return "CONFIG_DENIED";
        case Code::SAFETY_DENIED: return "SAFETY_DENIED";
        case Code::REPLAY_REJECTED: return "REPLAY_REJECTED";
        case Code::LEASE_EXPIRED: return "LEASE_EXPIRED";
        case Code::RESPONSE_SLOT_FULL: return "RESPONSE_SLOT_FULL";
        case Code::RESPONSE_OUTSTANDING: return "RESPONSE_OUTSTANDING";
        case Code::RESPONSE_PREEMPTED_BY_SAFETY:
            return "RESPONSE_PREEMPTED_BY_SAFETY";
        case Code::RESPONSE_TIMEOUT: return "RESPONSE_TIMEOUT";
        case Code::RESPONSE_BEFORE_TRANSMIT:
            return "RESPONSE_BEFORE_TRANSMIT";
        case Code::RESPONSE_MALFORMED: return "RESPONSE_MALFORMED";
        case Code::RESPONSE_UNEXPECTED_NODE: return "RESPONSE_UNEXPECTED_NODE";
        case Code::RESPONSE_UNEXPECTED_OPCODE:
            return "RESPONSE_UNEXPECTED_OPCODE";
        case Code::RESPONSE_UNEXPECTED: return "RESPONSE_UNEXPECTED";
        case Code::RESPONSE_DUPLICATE: return "RESPONSE_DUPLICATE";
        case Code::OBSERVATION_BEFORE_RESPONSE:
            return "OBSERVATION_BEFORE_RESPONSE";
        case Code::OBSERVATION_NOT_STATE: return "OBSERVATION_NOT_STATE";
        case Code::TRANSACTION_NOT_FOUND: return "TRANSACTION_NOT_FOUND";
        case Code::DIAGNOSTIC_BUDGET_EXHAUSTED:
            return "DIAGNOSTIC_BUDGET_EXHAUSTED";
        case Code::CYCLE_REGRESSION: return "CYCLE_REGRESSION";
        case Code::SAFETY_ACTION_UNCONFIGURED:
            return "SAFETY_ACTION_UNCONFIGURED";
        case Code::SAFETY_ACTION_NOT_REQUIRED:
            return "SAFETY_ACTION_NOT_REQUIRED";
        case Code::TRANSACTION_ID_EXHAUSTED:
            return "TRANSACTION_ID_EXHAUSTED";
        case Code::TIME_OVERFLOW: return "TIME_OVERFLOW";
        case Code::TRANSPORT_TX_FAILED: return "TRANSPORT_TX_FAILED";
        case Code::TRANSPORT_BUS_OFF: return "TRANSPORT_BUS_OFF";
    }
    return "UNKNOWN_GATEWAY_CODE";
}

GatewayCore::GatewayCore(const Route* routes,
                         size_t route_count,
                         const Policy& policy,
                         safety::ConfigIdentityGuard* config_guard,
                         safety::SafetySupervisor* safety_supervisor)
    : route_count_(0),
      policy_(policy),
      config_guard_(config_guard),
      safety_supervisor_(safety_supervisor),
      valid_(false),
      disposition_head_(0),
      disposition_count_(0),
      next_event_id_(1),
      next_transaction_id_(1),
      cycle_initialized_(false),
      cycle_id_(0),
      diagnostics_sent_in_cycle_(0),
      controls_since_diagnostic_(0) {
    memset(routes_, 0, sizeof(routes_));
    memset(&control_queue_, 0, sizeof(control_queue_));
    memset(&diagnostic_queue_, 0, sizeof(diagnostic_queue_));
    memset(response_slots_, 0, sizeof(response_slots_));
    memset(dispositions_, 0, sizeof(dispositions_));

    if (routes == NULL || route_count == 0 || route_count > kMaximumRoutes ||
        config_guard_ == NULL || safety_supervisor_ == NULL) {
        return;
    }
    route_count_ = route_count;
    for (size_t index = 0; index < route_count_; ++index) {
        routes_[index].route = routes[index];
    }
    valid_ = validateRoutes();
}

bool GatewayCore::valid() const {
    return valid_;
}

size_t GatewayCore::routeCount() const {
    return route_count_;
}

bool GatewayCore::isKnownOpcode(uint8_t opcode) {
    switch (static_cast<rmd_v44::Command>(opcode)) {
        case rmd_v44::Command::kOperatingMode:
        case rmd_v44::Command::kBrakeRelease:
        case rmd_v44::Command::kBrakeLock:
        case rmd_v44::Command::kShutdown:
        case rmd_v44::Command::kStop:
        case rmd_v44::Command::kReadMultiTurnAngle:
        case rmd_v44::Command::kReadSingleTurnAngle:
        case rmd_v44::Command::kReadStatus1:
        case rmd_v44::Command::kReadStatus2:
        case rmd_v44::Command::kReadStatus3:
        case rmd_v44::Command::kIqControl:
        case rmd_v44::Command::kSpeedControl:
        case rmd_v44::Command::kAbsolutePosition:
            return true;
    }
    return false;
}

bool GatewayCore::isBrakeOpcode(uint8_t opcode) {
    return opcode == Opcode(rmd_v44::Command::kBrakeRelease) ||
           opcode == Opcode(rmd_v44::Command::kBrakeLock);
}

bool GatewayCore::isSafetyOpcode(uint8_t opcode) {
    return opcode == Opcode(rmd_v44::Command::kShutdown) ||
           opcode == Opcode(rmd_v44::Command::kStop);
}

bool GatewayCore::isDiagnosticOpcode(uint8_t opcode) {
    return opcode == Opcode(rmd_v44::Command::kOperatingMode) ||
           opcode == Opcode(rmd_v44::Command::kReadMultiTurnAngle) ||
           opcode == Opcode(rmd_v44::Command::kReadSingleTurnAngle) ||
           opcode == Opcode(rmd_v44::Command::kReadStatus1) ||
           opcode == Opcode(rmd_v44::Command::kReadStatus2) ||
           opcode == Opcode(rmd_v44::Command::kReadStatus3);
}

bool GatewayCore::isControlOpcode(uint8_t opcode) {
    return opcode == Opcode(rmd_v44::Command::kIqControl) ||
           opcode == Opcode(rmd_v44::Command::kSpeedControl) ||
           opcode == Opcode(rmd_v44::Command::kAbsolutePosition);
}

bool GatewayCore::validateRoutes() {
    if (policy_.response_deadline_ms == 0 ||
        policy_.diagnostic_budget_per_cycle == 0 ||
        policy_.diagnostic_budget_per_cycle > kDiagnosticQueueCapacity ||
        policy_.maximum_control_before_diagnostic == 0) {
        return false;
    }

    for (size_t index = 0; index < route_count_; ++index) {
        const Route& route = routes_[index].route;
        if (route.token == 0 || route.bus_id == 0 ||
            !rmd_v44::IsValidMotorId(route.node_id) || route.owner_id == 0 ||
            route.owner_id > 32 || route.allowed_opcode_count == 0 ||
            route.allowed_opcode_count > kMaximumAllowedOpcodes) {
            return false;
        }
        for (size_t opcode_index = 0;
             opcode_index < route.allowed_opcode_count;
             ++opcode_index) {
            const uint8_t opcode = route.allowed_opcodes[opcode_index];
            if (!isKnownOpcode(opcode) || isBrakeOpcode(opcode) ||
                isSafetyOpcode(opcode) ||
                (!isControlOpcode(opcode) && !isDiagnosticOpcode(opcode))) {
                return false;
            }
            for (size_t previous = 0; previous < opcode_index; ++previous) {
                if (route.allowed_opcodes[previous] == opcode) {
                    return false;
                }
            }
        }
        if (route.safety_opcode != 0 &&
            !isSafetyOpcode(route.safety_opcode)) {
            return false;
        }
        for (size_t previous = 0; previous < index; ++previous) {
            const Route& other = routes_[previous].route;
            if (route.token == other.token ||
                (route.bus_id == other.bus_id &&
                 route.node_id == other.node_id)) {
                return false;
            }
        }
    }
    return true;
}

const Route* GatewayCore::findRoute(RouteToken token) const {
    for (size_t index = 0; index < route_count_; ++index) {
        if (routes_[index].route.token == token) {
            return &routes_[index].route;
        }
    }
    return NULL;
}

GatewayCore::RouteRuntime* GatewayCore::findRouteRuntime(RouteToken token) {
    for (size_t index = 0; index < route_count_; ++index) {
        if (routes_[index].route.token == token) {
            return &routes_[index];
        }
    }
    return NULL;
}

bool GatewayCore::routeAllowsOpcode(const Route& route,
                                    uint8_t opcode) const {
    for (size_t index = 0; index < route.allowed_opcode_count; ++index) {
        if (route.allowed_opcodes[index] == opcode) {
            return true;
        }
    }
    return false;
}

Code GatewayCore::validateSubmission(uint64_t now_ms,
                                     const Submission& submission,
                                     const Route** route,
                                     uint8_t* opcode) const {
    if (!valid_) {
        return Code::CORE_INVALID;
    }
    if (route == NULL || opcode == NULL) {
        return Code::CORE_INVALID;
    }
    *route = findRoute(submission.route_token);
    if (*route == NULL) {
        return Code::ROUTE_NOT_FOUND;
    }
    if (submission.bus_id != (*route)->bus_id ||
        submission.node_id != (*route)->node_id) {
        return Code::ROUTE_MISMATCH;
    }
    if (submission.owner_id != (*route)->owner_id ||
        submission.config_proof.config.authorization_class !=
            safety::AuthorizationClass::MOTION ||
        submission.safety_session_id == 0) {
        return Code::OWNER_MISMATCH;
    }
    if (submission.absolute_deadline_ms <= now_ms) {
        return Code::DEADLINE_INVALID;
    }

    rmd_v44::DecodedRequest decoded = {};
    const rmd_v44::Error decode_error = rmd_v44::DecodeRequest(
        submission.frame, &decoded, (*route)->node_id, 0);
    if (decode_error != rmd_v44::Error::kOk) {
        return Code::INVALID_REQUEST_FRAME;
    }
    *opcode = static_cast<uint8_t>(decoded.command);
    if (isBrakeOpcode(*opcode)) {
        return Code::BRAKE_UNSUPPORTED;
    }
    if (isSafetyOpcode(*opcode)) {
        return Code::SAFETY_OPCODE_WRONG_LANE;
    }
    if (!routeAllowsOpcode(**route, *opcode)) {
        return Code::OPCODE_NOT_ALLOWED;
    }
    if ((submission.traffic_class == TrafficClass::CONTROL &&
         !isControlOpcode(*opcode)) ||
        (submission.traffic_class == TrafficClass::DIAGNOSTIC &&
         !isDiagnosticOpcode(*opcode))) {
        return Code::TRAFFIC_CLASS_MISMATCH;
    }
    return Code::OK;
}

GatewayCore::Queue* GatewayCore::queueFor(TrafficClass traffic_class) {
    return traffic_class == TrafficClass::CONTROL ? &control_queue_
                                                   : &diagnostic_queue_;
}

size_t GatewayCore::queueCapacity(TrafficClass traffic_class) const {
    return traffic_class == TrafficClass::CONTROL
               ? kControlQueueCapacity
               : kDiagnosticQueueCapacity;
}

bool GatewayCore::queuePush(Queue* queue,
                            size_t capacity,
                            const QueueEntry& entry) {
    if (queue == NULL || queue->count >= capacity) {
        return false;
    }
    const size_t tail = (queue->head + queue->count) % capacity;
    queue->entries[tail] = entry;
    ++queue->count;
    return true;
}

bool GatewayCore::queuePop(Queue* queue,
                           size_t capacity,
                           QueueEntry* entry) {
    if (queue == NULL || entry == NULL || queue->count == 0) {
        return false;
    }
    *entry = queue->entries[queue->head];
    queue->head = (queue->head + 1) % capacity;
    --queue->count;
    return true;
}

Code GatewayCore::beginCycle(uint64_t cycle_id) {
    if (!valid_) {
        return Code::CORE_INVALID;
    }
    if (cycle_initialized_ && cycle_id < cycle_id_) {
        return Code::CYCLE_REGRESSION;
    }
    if (!cycle_initialized_ || cycle_id > cycle_id_) {
        cycle_initialized_ = true;
        cycle_id_ = cycle_id;
        diagnostics_sent_in_cycle_ = 0;
        controls_since_diagnostic_ = 0;
    }
    return Code::OK;
}

Code GatewayCore::enqueue(uint64_t now_ms,
                          const Submission& submission) {
    uint8_t observed_opcode = submission.frame.data[0];
    appendDisposition(now_ms, Phase::RECEIVED, Code::OK, &submission,
                      observed_opcode, false, 0, false,
                      safety::ConfigDecision::ALLOWED, false,
                      safety::Result::OK, rmd_v44::ResponseKind::kNone,
                      ObservationClass::NATIVE_STATE_SAMPLE);

    const Route* route = NULL;
    uint8_t opcode = 0;
    const Code validation =
        validateSubmission(now_ms, submission, &route, &opcode);
    if (validation != Code::OK) {
        appendDisposition(now_ms, Phase::REJECTED, validation, &submission,
                          observed_opcode, false, 0, false,
                          safety::ConfigDecision::ALLOWED, false,
                          safety::Result::OK, rmd_v44::ResponseKind::kNone,
                          ObservationClass::NATIVE_STATE_SAMPLE);
        return validation;
    }

    Queue* queue = queueFor(submission.traffic_class);
    const size_t capacity = queueCapacity(submission.traffic_class);
    const QueueEntry entry = {submission, opcode};
    if (!queuePush(queue, capacity, entry)) {
        const Code full = submission.traffic_class == TrafficClass::CONTROL
                              ? Code::CONTROL_QUEUE_FULL
                              : Code::DIAGNOSTIC_QUEUE_FULL;
        appendDisposition(now_ms, Phase::REJECTED, full, &submission, opcode,
                          false, 0, false,
                          safety::ConfigDecision::ALLOWED, false,
                          safety::Result::OK, rmd_v44::ResponseKind::kNone,
                          ObservationClass::NATIVE_STATE_SAMPLE);
        return full;
    }
    appendDisposition(now_ms, Phase::ADMITTED, Code::OK, &submission, opcode,
                      false, 0, false,
                      safety::ConfigDecision::ALLOWED, false,
                      safety::Result::OK, rmd_v44::ResponseKind::kNone,
                      ObservationClass::NATIVE_STATE_SAMPLE);
    return Code::OK;
}

bool GatewayCore::chooseQueue(TrafficClass* traffic_class) const {
    if (traffic_class == NULL) {
        return false;
    }
    const bool diagnostic_available =
        cycle_initialized_ && diagnostic_queue_.count != 0 &&
        diagnostics_sent_in_cycle_ < policy_.diagnostic_budget_per_cycle;
    if (control_queue_.count != 0) {
        if (diagnostic_available &&
            controls_since_diagnostic_ >=
                policy_.maximum_control_before_diagnostic) {
            *traffic_class = TrafficClass::DIAGNOSTIC;
        } else {
            *traffic_class = TrafficClass::CONTROL;
        }
        return true;
    }
    if (diagnostic_available) {
        *traffic_class = TrafficClass::DIAGNOSTIC;
        return true;
    }
    return false;
}

bool GatewayCore::responseOutstanding(uint8_t bus_id,
                                      uint8_t node_id) const {
    for (size_t index = 0; index < kResponseSlotCapacity; ++index) {
        const ResponseSlot& slot = response_slots_[index];
        if (slot.occupied && !slot.responded && slot.bus_id == bus_id &&
            slot.node_id == node_id) {
            return true;
        }
    }
    return false;
}

void GatewayCore::clearResponseSlot(size_t index) {
    memset(&response_slots_[index], 0, sizeof(response_slots_[index]));
}

int GatewayCore::reserveResponseSlot(bool safety_action,
                                     uint8_t bus_id,
                                     uint8_t node_id,
                                     uint64_t now_ms) {
    for (size_t index = 0; index < kResponseSlotCapacity; ++index) {
        if (!response_slots_[index].occupied) {
            return static_cast<int>(index);
        }
    }
    for (size_t index = 0; index < kResponseSlotCapacity; ++index) {
        if (response_slots_[index].responded) {
            clearResponseSlot(index);
            return static_cast<int>(index);
        }
    }
    if (!safety_action) {
        return -1;
    }

    // A pending normal diagnostic is the first preemption candidate, followed
    // by any pending normal control. A safety response is never preempted.
    for (uint8_t traffic_pass = 0; traffic_pass < 2; ++traffic_pass) {
        const TrafficClass target = traffic_pass == 0
                                        ? TrafficClass::DIAGNOSTIC
                                        : TrafficClass::CONTROL;
        for (size_t index = 0; index < kResponseSlotCapacity; ++index) {
            ResponseSlot& slot = response_slots_[index];
            if (slot.occupied && !slot.responded && !slot.safety_action &&
                slot.traffic_class == target) {
                appendResponseDisposition(
                    now_ms, Phase::REJECTED,
                    Code::RESPONSE_PREEMPTED_BY_SAFETY, &slot,
                    rmd_v44::ResponseKind::kNone,
                    ObservationClass::NATIVE_STATE_SAMPLE);
                clearResponseSlot(index);
                return static_cast<int>(index);
            }
        }
    }
    (void)bus_id;
    (void)node_id;
    return -1;
}

void GatewayCore::initializeResponseSlot(
    size_t index,
    const TxEnvelope& envelope,
    TrafficClass traffic_class,
    uint64_t transmit_time_ms,
    uint64_t response_deadline_ms,
    const Submission* submission) {
    ResponseSlot& slot = response_slots_[index];
    memset(&slot, 0, sizeof(slot));
    slot.occupied = true;
    slot.responded = false;
    slot.safety_action = envelope.safety_action;
    slot.transaction_id = envelope.transaction_id;
    slot.transmit_time_ms = transmit_time_ms;
    slot.response_time_ms = 0;
    slot.response_deadline_ms = response_deadline_ms;
    slot.route_token = envelope.route_token;
    slot.bus_id = envelope.bus_id;
    slot.node_id = envelope.node_id;
    slot.opcode = envelope.opcode;
    slot.traffic_class = traffic_class;
    if (submission != NULL) {
        slot.owner_id = submission->owner_id;
        slot.session_id = submission->safety_session_id;
        slot.sequence = submission->safety_sequence;
        slot.command_generation =
            submission->config_proof.command_generation;
    }
}

bool GatewayCore::safetyActionRequired(const RouteRuntime& runtime,
                                       uint64_t* shutdown_generation,
                                       uint32_t* fault_mask) const {
    if (shutdown_generation == NULL || fault_mask == NULL) {
        return false;
    }
    *shutdown_generation = 0;
    *fault_mask = 0;
    if (safety_supervisor_->state() == safety::State::SHUTDOWN) {
        const safety::ShutdownSnapshot snapshot = safety_supervisor_->shutdown();
        if (snapshot.active && snapshot.generation != 0 &&
            runtime.last_shutdown_generation_attempted !=
                snapshot.generation) {
            *shutdown_generation = snapshot.generation;
            return true;
        }
    }
    if (safety_supervisor_->state() == safety::State::FAULT) {
        const uint32_t current_fault_mask = safety_supervisor_->faultMask();
        if (current_fault_mask != 0 &&
            runtime.last_fault_mask_attempted != current_fault_mask) {
            *fault_mask = current_fault_mask;
            return true;
        }
    }
    return false;
}

PollResult GatewayCore::emitSafetyAction(uint64_t now_ms,
                                         TxEnvelope* out) {
    if (!safety_supervisor_->shutdownIntent()) {
        return PollResult::NO_FRAME;
    }
    for (size_t index = 0; index < route_count_; ++index) {
        RouteRuntime& runtime = routes_[index];
        uint64_t shutdown_generation = 0;
        uint32_t fault_mask = 0;
        if (!safetyActionRequired(runtime, &shutdown_generation, &fault_mask)) {
            continue;
        }

        Submission event_submission = {};
        event_submission.route_token = runtime.route.token;
        event_submission.bus_id = runtime.route.bus_id;
        event_submission.node_id = runtime.route.node_id;
        event_submission.owner_id = runtime.route.owner_id;
        event_submission.traffic_class = TrafficClass::CONTROL;

        if (runtime.route.safety_opcode == 0) {
            if (shutdown_generation != 0) {
                runtime.last_shutdown_generation_attempted = shutdown_generation;
            } else {
                runtime.last_fault_mask_attempted = fault_mask;
            }
            appendDisposition(
                now_ms, Phase::REJECTED, Code::SAFETY_ACTION_UNCONFIGURED,
                &event_submission, 0, true, 0, false,
                safety::ConfigDecision::ALLOWED, false, safety::Result::OK,
                rmd_v44::ResponseKind::kNone,
                ObservationClass::NATIVE_STATE_SAMPLE);
            continue;
        }
        if (next_transaction_id_ == UINT64_MAX) {
            appendDisposition(
                now_ms, Phase::REJECTED, Code::TRANSACTION_ID_EXHAUSTED,
                &event_submission, runtime.route.safety_opcode, true, 0,
                false, safety::ConfigDecision::ALLOWED, false,
                safety::Result::OK, rmd_v44::ResponseKind::kNone,
                ObservationClass::NATIVE_STATE_SAMPLE);
            return PollResult::NO_FRAME;
        }
        if (now_ms > UINT64_MAX - policy_.response_deadline_ms) {
            appendDisposition(now_ms, Phase::REJECTED, Code::TIME_OVERFLOW,
                              &event_submission,
                              runtime.route.safety_opcode, true, 0, false,
                              safety::ConfigDecision::ALLOWED, false,
                              safety::Result::OK,
                              rmd_v44::ResponseKind::kNone,
                              ObservationClass::NATIVE_STATE_SAMPLE);
            return PollResult::NO_FRAME;
        }
        const int response_slot = reserveResponseSlot(
            true, runtime.route.bus_id, runtime.route.node_id, now_ms);
        if (response_slot < 0) {
            appendDisposition(
                now_ms, Phase::REJECTED, Code::RESPONSE_SLOT_FULL,
                &event_submission, runtime.route.safety_opcode, true, 0,
                false, safety::ConfigDecision::ALLOWED, false,
                safety::Result::OK, rmd_v44::ResponseKind::kNone,
                ObservationClass::NATIVE_STATE_SAMPLE);
            return PollResult::NO_FRAME;
        }

        rmd_v44::Frame frame = {};
        const rmd_v44::Error encode = rmd_v44::EncodeZeroPayloadRequest(
            runtime.route.node_id,
            static_cast<rmd_v44::Command>(runtime.route.safety_opcode),
            &frame);
        if (encode != rmd_v44::Error::kOk) {
            appendDisposition(
                now_ms, Phase::REJECTED, Code::INVALID_REQUEST_FRAME,
                &event_submission, runtime.route.safety_opcode, true, 0,
                false, safety::ConfigDecision::ALLOWED, false,
                safety::Result::OK, rmd_v44::ResponseKind::kNone,
                ObservationClass::NATIVE_STATE_SAMPLE);
            return PollResult::NO_FRAME;
        }

        out->safety_action = true;
        out->transaction_id = next_transaction_id_++;
        out->route_token = runtime.route.token;
        out->bus_id = runtime.route.bus_id;
        out->node_id = runtime.route.node_id;
        out->opcode = runtime.route.safety_opcode;
        out->frame = frame;
        initializeResponseSlot(
            static_cast<size_t>(response_slot), *out, TrafficClass::CONTROL,
            now_ms, now_ms + policy_.response_deadline_ms, NULL);
        if (shutdown_generation != 0) {
            runtime.last_shutdown_generation_attempted = shutdown_generation;
        } else {
            runtime.last_fault_mask_attempted = fault_mask;
        }
        appendDisposition(now_ms, Phase::NATIVE_TX, Code::OK,
                          &event_submission, out->opcode, true,
                          out->transaction_id, false,
                          safety::ConfigDecision::ALLOWED, false,
                          safety::Result::OK, rmd_v44::ResponseKind::kNone,
                          ObservationClass::NATIVE_STATE_SAMPLE);
        return PollResult::FRAME_READY;
    }
    return PollResult::NO_FRAME;
}

PollResult GatewayCore::processNormalEntry(uint64_t now_ms,
                                           const QueueEntry& entry,
                                           TxEnvelope* out) {
    const Route* route = NULL;
    uint8_t opcode = 0;
    Code validation = validateSubmission(now_ms, entry.submission, &route,
                                         &opcode);
    if (validation == Code::DEADLINE_INVALID) {
        validation = Code::DEADLINE_EXPIRED;
    }
    if (validation != Code::OK || opcode != entry.opcode) {
        const Code code = validation != Code::OK ? validation
                                                  : Code::ROUTE_MISMATCH;
        appendDisposition(now_ms, Phase::REJECTED, code, &entry.submission,
                          entry.opcode, false, 0, false,
                          safety::ConfigDecision::ALLOWED, false,
                          safety::Result::OK, rmd_v44::ResponseKind::kNone,
                          ObservationClass::NATIVE_STATE_SAMPLE);
        return PollResult::NO_FRAME;
    }
    if (responseOutstanding(route->bus_id, route->node_id)) {
        appendDisposition(now_ms, Phase::REJECTED,
                          Code::RESPONSE_OUTSTANDING, &entry.submission,
                          opcode, false, 0, false,
                          safety::ConfigDecision::ALLOWED, false,
                          safety::Result::OK, rmd_v44::ResponseKind::kNone,
                          ObservationClass::NATIVE_STATE_SAMPLE);
        return PollResult::NO_FRAME;
    }
    if (next_transaction_id_ == UINT64_MAX) {
        appendDisposition(now_ms, Phase::REJECTED,
                          Code::TRANSACTION_ID_EXHAUSTED,
                          &entry.submission, opcode, false, 0, false,
                          safety::ConfigDecision::ALLOWED, false,
                          safety::Result::OK, rmd_v44::ResponseKind::kNone,
                          ObservationClass::NATIVE_STATE_SAMPLE);
        return PollResult::NO_FRAME;
    }
    if (now_ms > UINT64_MAX - policy_.response_deadline_ms) {
        appendDisposition(now_ms, Phase::REJECTED, Code::TIME_OVERFLOW,
                          &entry.submission, opcode, false, 0, false,
                          safety::ConfigDecision::ALLOWED, false,
                          safety::Result::OK, rmd_v44::ResponseKind::kNone,
                          ObservationClass::NATIVE_STATE_SAMPLE);
        return PollResult::NO_FRAME;
    }
    const int response_slot = reserveResponseSlot(
        false, route->bus_id, route->node_id, now_ms);
    if (response_slot < 0) {
        appendDisposition(now_ms, Phase::REJECTED,
                          Code::RESPONSE_SLOT_FULL, &entry.submission,
                          opcode, false, 0, false,
                          safety::ConfigDecision::ALLOWED, false,
                          safety::Result::OK, rmd_v44::ResponseKind::kNone,
                          ObservationClass::NATIVE_STATE_SAMPLE);
        return PollResult::NO_FRAME;
    }

    // These are the final two mutable admission decisions before the caller
    // can observe a normal native frame.
    const safety::ConfigDecision config_decision =
        config_guard_->authorizeTransmit(now_ms,
                                         entry.submission.config_proof);
    if (config_decision != safety::ConfigDecision::ALLOWED) {
        appendDisposition(
            now_ms, Phase::REJECTED, ConfigDenialCode(config_decision),
            &entry.submission, opcode, false, 0, true, config_decision, false,
            safety::Result::OK, rmd_v44::ResponseKind::kNone,
            ObservationClass::NATIVE_STATE_SAMPLE);
        return PollResult::NO_FRAME;
    }
    const safety::MessageStamp stamp(entry.submission.owner_id,
                                     entry.submission.safety_session_id,
                                     entry.submission.safety_sequence);
    const safety::Result safety_result =
        safety_supervisor_->authorizeCommand(now_ms, stamp);
    if (safety_result != safety::Result::OK) {
        appendDisposition(
            now_ms, Phase::REJECTED, SafetyDenialCode(safety_result),
            &entry.submission, opcode, false, 0, true, config_decision, true,
            safety_result, rmd_v44::ResponseKind::kNone,
            ObservationClass::NATIVE_STATE_SAMPLE);
        return PollResult::NO_FRAME;
    }

    out->safety_action = false;
    out->transaction_id = next_transaction_id_++;
    out->route_token = route->token;
    out->bus_id = route->bus_id;
    out->node_id = route->node_id;
    out->opcode = opcode;
    out->frame = entry.submission.frame;
    initializeResponseSlot(
        static_cast<size_t>(response_slot), *out,
        entry.submission.traffic_class,
        now_ms, now_ms + policy_.response_deadline_ms, &entry.submission);
    if (entry.submission.traffic_class == TrafficClass::DIAGNOSTIC) {
        ++diagnostics_sent_in_cycle_;
        controls_since_diagnostic_ = 0;
    } else if (controls_since_diagnostic_ != UINT8_MAX) {
        ++controls_since_diagnostic_;
    }
    appendDisposition(now_ms, Phase::NATIVE_TX, Code::OK,
                      &entry.submission, opcode, false,
                      out->transaction_id, true, config_decision, true,
                      safety_result, rmd_v44::ResponseKind::kNone,
                      ObservationClass::NATIVE_STATE_SAMPLE);
    return PollResult::FRAME_READY;
}

PollResult GatewayCore::pollTransmit(uint64_t now_ms, TxEnvelope* out) {
    if (!valid_ || out == NULL) {
        return PollResult::INVALID_CORE;
    }
    memset(out, 0, sizeof(*out));
    expireResponses(now_ms);

    const size_t maximum_attempts =
        kControlQueueCapacity + kDiagnosticQueueCapacity + route_count_ + 1;
    for (size_t attempt = 0; attempt < maximum_attempts; ++attempt) {
        const PollResult safety_result = emitSafetyAction(now_ms, out);
        if (safety_result == PollResult::FRAME_READY) {
            return safety_result;
        }
        if (safety_supervisor_->shutdownIntent()) {
            return PollResult::NO_FRAME;
        }

        TrafficClass traffic_class = TrafficClass::CONTROL;
        if (!chooseQueue(&traffic_class)) {
            return PollResult::NO_FRAME;
        }
        Queue* queue = queueFor(traffic_class);
        QueueEntry entry = {};
        if (!queuePop(queue, queueCapacity(traffic_class), &entry)) {
            return PollResult::NO_FRAME;
        }
        const PollResult result = processNormalEntry(now_ms, entry, out);
        if (result == PollResult::FRAME_READY) {
            return result;
        }
    }
    return PollResult::NO_FRAME;
}

Code GatewayCore::reportTransportFailure(uint64_t now_ms,
                                         uint64_t transaction_id,
                                         TransportFailure failure) {
    if (!valid_) {
        return Code::CORE_INVALID;
    }
    const Code code = failure == TransportFailure::BUS_OFF
                          ? Code::TRANSPORT_BUS_OFF
                          : Code::TRANSPORT_TX_FAILED;
    for (size_t index = 0; index < kResponseSlotCapacity; ++index) {
        ResponseSlot& slot = response_slots_[index];
        if (!slot.occupied || slot.transaction_id != transaction_id) {
            continue;
        }
        if (slot.responded) {
            return Code::RESPONSE_DUPLICATE;
        }
        appendResponseDisposition(now_ms, Phase::REJECTED, code, &slot,
                                  rmd_v44::ResponseKind::kNone,
                                  ObservationClass::NATIVE_STATE_SAMPLE);
        if (slot.safety_action) {
            RouteRuntime* runtime = findRouteRuntime(slot.route_token);
            if (runtime != NULL) {
                runtime->last_shutdown_generation_attempted = 0;
                runtime->last_fault_mask_attempted = 0;
            }
        }
        clearResponseSlot(index);
        safety_supervisor_->raiseFault(
            now_ms,
            failure == TransportFailure::BUS_OFF
                ? safety::Fault::BUS_OFF
                : safety::Fault::EXTERNAL);
        return code;
    }
    return Code::TRANSACTION_NOT_FOUND;
}

size_t GatewayCore::expireResponses(uint64_t now_ms) {
    size_t expired = 0;
    for (size_t index = 0; index < kResponseSlotCapacity; ++index) {
        ResponseSlot& slot = response_slots_[index];
        if (slot.occupied && !slot.responded &&
            now_ms >= slot.response_deadline_ms) {
            appendResponseDisposition(now_ms, Phase::REJECTED,
                                      Code::RESPONSE_TIMEOUT, &slot,
                                      rmd_v44::ResponseKind::kNone,
                                      ObservationClass::NATIVE_STATE_SAMPLE);
            clearResponseSlot(index);
            ++expired;
        }
    }
    return expired;
}

Code GatewayCore::acceptResponse(uint64_t now_ms,
                                 uint8_t bus_id,
                                 const rmd_v44::Frame& frame) {
    if (!valid_) {
        return Code::CORE_INVALID;
    }
    ResponseSlot pseudo = {};
    pseudo.occupied = true;
    pseudo.bus_id = bus_id;
    pseudo.opcode = frame.data[0];
    pseudo.traffic_class = TrafficClass::DIAGNOSTIC;
    if (frame.is_extended || frame.is_remote ||
        frame.dlc != rmd_v44::kFrameDlc ||
        frame.arbitration_id <= rmd_v44::kResponseBaseId ||
        frame.arbitration_id >
            rmd_v44::kResponseBaseId + rmd_v44::kMaxMotorId) {
        appendResponseDisposition(now_ms, Phase::REJECTED,
                                  Code::RESPONSE_MALFORMED, &pseudo,
                                  rmd_v44::ResponseKind::kNone,
                                  ObservationClass::NATIVE_STATE_SAMPLE);
        return Code::RESPONSE_MALFORMED;
    }
    const uint8_t node_id = static_cast<uint8_t>(
        frame.arbitration_id - rmd_v44::kResponseBaseId);
    const uint8_t opcode = frame.data[0];
    pseudo.node_id = node_id;

    int exact = -1;
    int duplicate = -1;
    bool same_node = false;
    bool same_opcode = false;
    for (size_t index = 0; index < kResponseSlotCapacity; ++index) {
        const ResponseSlot& slot = response_slots_[index];
        if (!slot.occupied || slot.bus_id != bus_id) {
            continue;
        }
        if (slot.node_id == node_id && slot.opcode == opcode) {
            if (slot.responded) {
                duplicate = static_cast<int>(index);
            } else {
                exact = static_cast<int>(index);
            }
        }
        if (!slot.responded && slot.node_id == node_id) {
            same_node = true;
        }
        if (!slot.responded && slot.opcode == opcode) {
            same_opcode = true;
        }
    }
    if (exact < 0) {
        if (duplicate >= 0) {
            appendResponseDisposition(
                now_ms, Phase::REJECTED, Code::RESPONSE_DUPLICATE,
                &response_slots_[static_cast<size_t>(duplicate)],
                rmd_v44::ResponseKind::kNone,
                ObservationClass::NATIVE_STATE_SAMPLE);
            return Code::RESPONSE_DUPLICATE;
        }
        const Code code = same_node
                              ? Code::RESPONSE_UNEXPECTED_OPCODE
                              : (same_opcode ? Code::RESPONSE_UNEXPECTED_NODE
                                             : Code::RESPONSE_UNEXPECTED);
        appendResponseDisposition(now_ms, Phase::REJECTED, code, &pseudo,
                                  rmd_v44::ResponseKind::kNone,
                                  ObservationClass::NATIVE_STATE_SAMPLE);
        return code;
    }

    ResponseSlot& slot = response_slots_[static_cast<size_t>(exact)];
    if (now_ms < slot.transmit_time_ms) {
        appendResponseDisposition(now_ms, Phase::REJECTED,
                                  Code::RESPONSE_BEFORE_TRANSMIT, &slot,
                                  rmd_v44::ResponseKind::kNone,
                                  ObservationClass::NATIVE_STATE_SAMPLE);
        return Code::RESPONSE_BEFORE_TRANSMIT;
    }
    if (now_ms >= slot.response_deadline_ms) {
        appendResponseDisposition(now_ms, Phase::REJECTED,
                                  Code::RESPONSE_TIMEOUT, &slot,
                                  rmd_v44::ResponseKind::kNone,
                                  ObservationClass::NATIVE_STATE_SAMPLE);
        clearResponseSlot(static_cast<size_t>(exact));
        return Code::RESPONSE_TIMEOUT;
    }
    rmd_v44::DecodedResponse decoded = {};
    const rmd_v44::Error decode_error = rmd_v44::DecodeResponse(
        frame, &decoded, slot.node_id, slot.opcode);
    if (decode_error != rmd_v44::Error::kOk) {
        appendResponseDisposition(now_ms, Phase::REJECTED,
                                  Code::RESPONSE_MALFORMED, &slot,
                                  rmd_v44::ResponseKind::kNone,
                                  ObservationClass::NATIVE_STATE_SAMPLE);
        return Code::RESPONSE_MALFORMED;
    }
    slot.responded = true;
    slot.response_time_ms = now_ms;
    slot.response_kind = decoded.kind;
    appendResponseDisposition(now_ms, Phase::NATIVE_RESPONSE, Code::OK,
                              &slot, decoded.kind,
                              ObservationClass::NATIVE_STATE_SAMPLE);
    return Code::OK;
}

Code GatewayCore::recordObservation(
    uint64_t now_ms,
    uint64_t transaction_id,
    ObservationClass observation_class) {
    for (size_t index = 0; index < kResponseSlotCapacity; ++index) {
        ResponseSlot& slot = response_slots_[index];
        if (!slot.occupied || slot.transaction_id != transaction_id) {
            continue;
        }
        if (!slot.responded) {
            appendResponseDisposition(
                now_ms, Phase::REJECTED,
                Code::OBSERVATION_BEFORE_RESPONSE, &slot,
                rmd_v44::ResponseKind::kNone, observation_class);
            return Code::OBSERVATION_BEFORE_RESPONSE;
        }
        if (now_ms < slot.response_time_ms) {
            appendResponseDisposition(
                now_ms, Phase::REJECTED,
                Code::OBSERVATION_BEFORE_RESPONSE, &slot,
                slot.response_kind, observation_class);
            return Code::OBSERVATION_BEFORE_RESPONSE;
        }
        if (slot.response_kind == rmd_v44::ResponseKind::kNone ||
            slot.response_kind == rmd_v44::ResponseKind::kEcho) {
            return Code::OBSERVATION_NOT_STATE;
        }
        appendResponseDisposition(now_ms, Phase::OBSERVED, Code::OK, &slot,
                                  slot.response_kind, observation_class);
        clearResponseSlot(index);
        return Code::OK;
    }
    return Code::TRANSACTION_NOT_FOUND;
}

Code GatewayCore::releaseCompletedResponse(uint64_t transaction_id) {
    for (size_t index = 0; index < kResponseSlotCapacity; ++index) {
        ResponseSlot& slot = response_slots_[index];
        if (slot.occupied && slot.responded &&
            slot.transaction_id == transaction_id) {
            clearResponseSlot(index);
            return Code::OK;
        }
    }
    return Code::TRANSACTION_NOT_FOUND;
}

size_t GatewayCore::controlQueueSize() const {
    return control_queue_.count;
}

size_t GatewayCore::diagnosticQueueSize() const {
    return diagnostic_queue_.count;
}

size_t GatewayCore::outstandingResponseCount() const {
    size_t count = 0;
    for (size_t index = 0; index < kResponseSlotCapacity; ++index) {
        if (response_slots_[index].occupied) {
            ++count;
        }
    }
    return count;
}

size_t GatewayCore::dispositionCount() const {
    return disposition_count_;
}

bool GatewayCore::dispositionAt(size_t oldest_index,
                                Disposition* out) const {
    if (out == NULL || oldest_index >= disposition_count_) {
        return false;
    }
    const size_t index =
        (disposition_head_ + oldest_index) % kDispositionCapacity;
    *out = dispositions_[index];
    return true;
}

void GatewayCore::appendDisposition(
    uint64_t now_ms,
    Phase phase,
    Code code,
    const Submission* submission,
    uint8_t opcode,
    bool safety_action,
    uint64_t transaction_id,
    bool config_checked,
    safety::ConfigDecision config_decision,
    bool safety_checked,
    safety::Result safety_result,
    rmd_v44::ResponseKind response_kind,
    ObservationClass observation_class) {
    Disposition event = {};
    event.event_id = next_event_id_;
    if (next_event_id_ != UINT64_MAX) {
        ++next_event_id_;
    }
    event.transaction_id = transaction_id;
    event.monotonic_ms = now_ms;
    event.phase = phase;
    event.code = code;
    event.opcode = opcode;
    event.safety_action = safety_action;
    event.config_checked = config_checked;
    event.config_decision = config_decision;
    event.safety_checked = safety_checked;
    event.safety_result = safety_result;
    event.response_kind = response_kind;
    event.observation_class = observation_class;
    if (submission != NULL) {
        event.route_token = submission->route_token;
        event.bus_id = submission->bus_id;
        event.node_id = submission->node_id;
        event.traffic_class = submission->traffic_class;
        event.owner_id = submission->owner_id;
        event.session_id = submission->safety_session_id;
        event.sequence = submission->safety_sequence;
        event.command_generation =
            submission->config_proof.command_generation;
    }

    size_t index = 0;
    if (disposition_count_ < kDispositionCapacity) {
        index = (disposition_head_ + disposition_count_) %
                kDispositionCapacity;
        ++disposition_count_;
    } else {
        index = disposition_head_;
        disposition_head_ =
            (disposition_head_ + 1) % kDispositionCapacity;
    }
    dispositions_[index] = event;
}

void GatewayCore::appendResponseDisposition(
    uint64_t now_ms,
    Phase phase,
    Code code,
    const ResponseSlot* slot,
    rmd_v44::ResponseKind response_kind,
    ObservationClass observation_class) {
    if (slot == NULL) {
        return;
    }
    Submission submission = {};
    submission.route_token = slot->route_token;
    submission.bus_id = slot->bus_id;
    submission.node_id = slot->node_id;
    submission.owner_id = slot->owner_id;
    submission.traffic_class = slot->traffic_class;
    submission.safety_session_id = slot->session_id;
    submission.safety_sequence = slot->sequence;
    submission.config_proof.command_generation = slot->command_generation;
    appendDisposition(now_ms, phase, code, &submission, slot->opcode,
                      slot->safety_action, slot->transaction_id, false,
                      safety::ConfigDecision::ALLOWED, false,
                      safety::Result::OK, response_kind,
                      observation_class);
}

}  // namespace gateway
}  // namespace myactuator
