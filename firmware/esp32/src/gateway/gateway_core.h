#pragma once

// Portable bounded gateway scheduler core.
//
// This layer owns no hardware and performs no transport I/O. A transport
// adapter pulls an admitted TxEnvelope and later pushes a native response.
// The core is C++11, allocation-free, exception-free, RTTI-free and has no
// Arduino dependency. Routes in this iteration are synthetic test evidence;
// they do not assert applicability to installed Dropbear actuators.

#include <stddef.h>
#include <stdint.h>

#include "../protocols/rmd_v44_codec.h"
#include "../safety/config_identity_guard.h"
#include "../safety/safety_supervisor.h"

namespace myactuator {
namespace gateway {

static const size_t kMaximumRoutes = 8;
static const size_t kMaximumAllowedOpcodes = 8;
static const size_t kControlQueueCapacity = 8;
static const size_t kDiagnosticQueueCapacity = 4;
static const size_t kResponseSlotCapacity = 8;
static const size_t kDispositionCapacity = 64;

typedef uint16_t RouteToken;

enum class TrafficClass : uint8_t {
    CONTROL = 0,
    DIAGNOSTIC = 1,
};

enum class Phase : uint8_t {
    RECEIVED = 0,
    ADMITTED = 1,
    NATIVE_TX = 2,
    NATIVE_RESPONSE = 3,
    OBSERVED = 4,
    REJECTED = 5,
};

// Codes are dispositions, not claims about physical actuator state.
enum class Code : uint8_t {
    OK = 0,
    CORE_INVALID,
    ROUTE_NOT_FOUND,
    ROUTE_MISMATCH,
    OWNER_MISMATCH,
    INVALID_REQUEST_FRAME,
    OPCODE_NOT_ALLOWED,
    TRAFFIC_CLASS_MISMATCH,
    BRAKE_UNSUPPORTED,
    SAFETY_OPCODE_WRONG_LANE,
    DEADLINE_INVALID,
    DEADLINE_EXPIRED,
    CONTROL_QUEUE_FULL,
    DIAGNOSTIC_QUEUE_FULL,
    CONFIG_DENIED,
    SAFETY_DENIED,
    REPLAY_REJECTED,
    LEASE_EXPIRED,
    RESPONSE_SLOT_FULL,
    RESPONSE_OUTSTANDING,
    RESPONSE_PREEMPTED_BY_SAFETY,
    RESPONSE_TIMEOUT,
    RESPONSE_BEFORE_TRANSMIT,
    RESPONSE_MALFORMED,
    RESPONSE_UNEXPECTED_NODE,
    RESPONSE_UNEXPECTED_OPCODE,
    RESPONSE_UNEXPECTED,
    RESPONSE_DUPLICATE,
    OBSERVATION_BEFORE_RESPONSE,
    OBSERVATION_NOT_STATE,
    TRANSACTION_NOT_FOUND,
    DIAGNOSTIC_BUDGET_EXHAUSTED,
    CYCLE_REGRESSION,
    SAFETY_ACTION_UNCONFIGURED,
    SAFETY_ACTION_NOT_REQUIRED,
    TRANSACTION_ID_EXHAUSTED,
    TIME_OVERFLOW,
    TRANSPORT_TX_FAILED,
    TRANSPORT_BUS_OFF,
};

enum class TransportFailure : uint8_t {
    TX_FAILED = 0,
    BUS_OFF = 1,
};

enum class PollResult : uint8_t {
    NO_FRAME = 0,
    FRAME_READY = 1,
    INVALID_CORE = 2,
};

enum class ObservationClass : uint8_t {
    NATIVE_STATE_SAMPLE = 0,
    EXTERNAL_SENSOR_SAMPLE = 1,
};

struct Route {
    RouteToken token;
    uint8_t bus_id;
    uint8_t node_id;
    uint32_t owner_id;
    uint8_t allowed_opcode_count;
    uint8_t allowed_opcodes[kMaximumAllowedOpcodes];
    // Zero means explicitly unconfigured. Any configured value must be STOP
    // or SHUTDOWN. Brake release/lock is unsupported in every lane.
    uint8_t safety_opcode;
};

struct Policy {
    uint32_t response_deadline_ms;
    uint8_t diagnostic_budget_per_cycle;
    uint8_t maximum_control_before_diagnostic;

    Policy(uint32_t response_deadline,
           uint8_t diagnostic_budget,
           uint8_t maximum_control_burst)
        : response_deadline_ms(response_deadline),
          diagnostic_budget_per_cycle(diagnostic_budget),
          maximum_control_before_diagnostic(maximum_control_burst) {}
};

// A submission captures every admission identity by value. The route is
// repeated deliberately so a stale or cross-layer route mapping is rejected.
struct Submission {
    RouteToken route_token;
    uint8_t bus_id;
    uint8_t node_id;
    uint32_t owner_id;
    TrafficClass traffic_class;
    safety::CommandAdmissionProof config_proof;
    uint32_t safety_session_id;
    uint64_t safety_sequence;
    uint64_t absolute_deadline_ms;
    rmd_v44::Frame frame;
};

struct TxEnvelope {
    bool safety_action;
    uint64_t transaction_id;
    RouteToken route_token;
    uint8_t bus_id;
    uint8_t node_id;
    uint8_t opcode;
    rmd_v44::Frame frame;
};

struct Disposition {
    uint64_t event_id;
    uint64_t transaction_id;
    uint64_t monotonic_ms;
    Phase phase;
    Code code;
    RouteToken route_token;
    uint8_t bus_id;
    uint8_t node_id;
    uint8_t opcode;
    bool safety_action;
    TrafficClass traffic_class;
    uint32_t owner_id;
    uint32_t session_id;
    uint64_t sequence;
    uint64_t command_generation;
    bool config_checked;
    safety::ConfigDecision config_decision;
    bool safety_checked;
    safety::Result safety_result;
    rmd_v44::ResponseKind response_kind;
    ObservationClass observation_class;
};

const char* CodeName(Code code);

class GatewayCore {
public:
    GatewayCore(const Route* routes,
                size_t route_count,
                const Policy& policy,
                safety::ConfigIdentityGuard* config_guard,
                safety::SafetySupervisor* safety_supervisor);

    bool valid() const;
    size_t routeCount() const;

    // A new cycle replenishes the bounded diagnostic budget. Repeating the
    // same cycle is idempotent; cycle regression is rejected.
    Code beginCycle(uint64_t cycle_id);

    Code enqueue(uint64_t now_ms, const Submission& submission);

    // Safety actions always preempt queued normal work. A normal frame is
    // exposed only after a final config authorizeTransmit and a final safety
    // authorizeCommand at now_ms.
    PollResult pollTransmit(uint64_t now_ms, TxEnvelope* out);

    // pollTransmit transfers one already-finally-admitted envelope to the
    // transport boundary and reserves its response slot. A real adapter must
    // report any failure to put that exact frame on the bus. Failure clears
    // the slot, latches an external safety fault, and makes a failed safety
    // action eligible for retry; it never fabricates a native response.
    Code reportTransportFailure(uint64_t now_ms,
                                uint64_t transaction_id,
                                TransportFailure failure);

    // Native response correlation never implies mechanical observation and
    // never acknowledges SafetySupervisor shutdown completion.
    Code acceptResponse(uint64_t now_ms,
                        uint8_t bus_id,
                        const rmd_v44::Frame& frame);
    size_t expireResponses(uint64_t now_ms);

    // OBSERVED is emitted only for an explicit state-sample handoff after a
    // correlated non-echo response. It is not proof of mechanical motion or
    // motor-off. Echo responses must be released without observation.
    Code recordObservation(uint64_t now_ms,
                           uint64_t transaction_id,
                           ObservationClass observation_class);
    Code releaseCompletedResponse(uint64_t transaction_id);

    size_t controlQueueSize() const;
    size_t diagnosticQueueSize() const;
    size_t outstandingResponseCount() const;
    size_t dispositionCount() const;
    bool dispositionAt(size_t oldest_index, Disposition* out) const;

private:
    struct QueueEntry {
        Submission submission;
        uint8_t opcode;
    };

    struct Queue {
        QueueEntry entries[kControlQueueCapacity];
        size_t head;
        size_t count;
    };

    struct ResponseSlot {
        bool occupied;
        bool responded;
        bool safety_action;
        uint64_t transaction_id;
        uint64_t transmit_time_ms;
        uint64_t response_time_ms;
        uint64_t response_deadline_ms;
        RouteToken route_token;
        uint8_t bus_id;
        uint8_t node_id;
        uint8_t opcode;
        TrafficClass traffic_class;
        uint32_t owner_id;
        uint32_t session_id;
        uint64_t sequence;
        uint64_t command_generation;
        rmd_v44::ResponseKind response_kind;
    };

    struct RouteRuntime {
        Route route;
        uint64_t last_shutdown_generation_attempted;
        uint32_t last_fault_mask_attempted;
    };

    RouteRuntime routes_[kMaximumRoutes];
    size_t route_count_;
    Policy policy_;
    safety::ConfigIdentityGuard* config_guard_;
    safety::SafetySupervisor* safety_supervisor_;
    bool valid_;

    Queue control_queue_;
    Queue diagnostic_queue_;
    ResponseSlot response_slots_[kResponseSlotCapacity];
    Disposition dispositions_[kDispositionCapacity];
    size_t disposition_head_;
    size_t disposition_count_;
    uint64_t next_event_id_;
    uint64_t next_transaction_id_;

    bool cycle_initialized_;
    uint64_t cycle_id_;
    uint8_t diagnostics_sent_in_cycle_;
    uint8_t controls_since_diagnostic_;

    bool validateRoutes();
    const Route* findRoute(RouteToken token) const;
    RouteRuntime* findRouteRuntime(RouteToken token);
    bool routeAllowsOpcode(const Route& route, uint8_t opcode) const;
    Code validateSubmission(uint64_t now_ms,
                            const Submission& submission,
                            const Route** route,
                            uint8_t* opcode) const;

    static bool isKnownOpcode(uint8_t opcode);
    static bool isBrakeOpcode(uint8_t opcode);
    static bool isSafetyOpcode(uint8_t opcode);
    static bool isDiagnosticOpcode(uint8_t opcode);
    static bool isControlOpcode(uint8_t opcode);

    Queue* queueFor(TrafficClass traffic_class);
    size_t queueCapacity(TrafficClass traffic_class) const;
    bool queuePush(Queue* queue,
                   size_t capacity,
                   const QueueEntry& entry);
    bool queuePop(Queue* queue,
                  size_t capacity,
                  QueueEntry* entry);
    bool chooseQueue(TrafficClass* traffic_class) const;

    int reserveResponseSlot(bool safety_action,
                            uint8_t bus_id,
                            uint8_t node_id,
                            uint64_t now_ms);
    bool responseOutstanding(uint8_t bus_id, uint8_t node_id) const;
    void clearResponseSlot(size_t index);
    void initializeResponseSlot(size_t index,
                                const TxEnvelope& envelope,
                                TrafficClass traffic_class,
                                uint64_t transmit_time_ms,
                                uint64_t response_deadline_ms,
                                const Submission* submission);

    bool safetyActionRequired(const RouteRuntime& runtime,
                              uint64_t* shutdown_generation,
                              uint32_t* fault_mask) const;
    PollResult emitSafetyAction(uint64_t now_ms, TxEnvelope* out);
    PollResult processNormalEntry(uint64_t now_ms,
                                  const QueueEntry& entry,
                                  TxEnvelope* out);

    void appendDisposition(uint64_t now_ms,
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
                           ObservationClass observation_class);
    void appendResponseDisposition(uint64_t now_ms,
                                   Phase phase,
                                   Code code,
                                   const ResponseSlot* slot,
                                   rmd_v44::ResponseKind response_kind,
                                   ObservationClass observation_class);
};

}  // namespace gateway
}  // namespace myactuator
