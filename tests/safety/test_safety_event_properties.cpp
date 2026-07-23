#include "config_identity_guard.h"
#include "gateway_core.h"
#include "rmd_v44_codec.h"
#include "safety_supervisor.h"

#include <stddef.h>
#include <stdint.h>

#include <cstdlib>
#include <cstring>
#include <iostream>

namespace cfg = myactuator::safety;
namespace gw = myactuator::gateway;
namespace v44 = myactuator::rmd_v44;

namespace {

const uint32_t kSession = 0x4D594143UL;
const uint32_t kOwner = 1;
const uint32_t kOtherOwner = 2;
const uint32_t kLeaseDurationMs = 16;
const uint64_t kCommandLifetimeMs = 8;
const uint64_t kConfigLifetimeMs = 128;
const size_t kRouteCount = 2;

uint64_t g_checks = 0;
uint64_t g_sequences = 0;
uint64_t g_actions = 0;
uint64_t g_polls = 0;
uint64_t g_normal_frames = 0;
uint64_t g_safety_frames = 0;
const char* g_trace = "initialization";
const char* g_action = "INITIALIZE";
uint64_t g_seed = 0;
size_t g_step = 0;

void Check(bool condition, const char* expression, int line) {
    ++g_checks;
    if (condition) {
        return;
    }
    std::cerr << __FILE__ << ':' << line << " property failed: "
              << expression << " trace=" << g_trace
              << " seed=" << g_seed << " step=" << g_step
              << " action=" << g_action << '\n';
    std::exit(1);
}

#define CHECK(expression) Check((expression), #expression, __LINE__)

cfg::SchemaCompatibilityPolicy SchemaPolicy() {
    cfg::SchemaCompatibilityPolicy policy = {1, 1};
    return policy;
}

cfg::Configuration SafetyConfiguration() {
    return cfg::Configuration(
        kSession, 1, 1000, 12, 0x00000003UL, 0x00000003UL);
}

cfg::Prerequisites ReadyPrerequisites() {
    cfg::Prerequisites prerequisites;
    prerequisites.configuration_valid = true;
    prerequisites.expected_nodes_present = true;
    prerequisites.transport_ready = true;
    prerequisites.safety_interlock_ready = true;
    prerequisites.external_faults_clear = true;
    prerequisites.motor_off_confirmed = true;
    return prerequisites;
}

cfg::Prerequisites LostPrerequisites() {
    cfg::Prerequisites prerequisites = ReadyPrerequisites();
    prerequisites.transport_ready = false;
    prerequisites.motor_off_confirmed = false;
    return prerequisites;
}

cfg::ConfigIdentity Identity(uint64_t revision) {
    cfg::ConfigIdentity identity = {};
    const char id[] = "event-property-config";
    const size_t length = sizeof(id) - 1;
    CHECK(length <= cfg::kConfigIdCapacity);
    identity.config_id.length = static_cast<uint8_t>(length);
    std::memcpy(identity.config_id.bytes, id, length);
    for (size_t index = 0; index < cfg::kSha256DigestSize; ++index) {
        identity.digest.bytes[index] = static_cast<uint8_t>(
            0x31U + index + static_cast<size_t>(revision & 0x7FU));
    }
    identity.revision = revision;
    identity.schema_version = 1;
    return identity;
}

cfg::ConfigCandidate Candidate(uint64_t revision,
                               uint64_t generation,
                               uint64_t validity_deadline_ms) {
    cfg::ConfigCandidate candidate = {};
    candidate.identity = Identity(revision);
    candidate.generation = generation;
    candidate.validity_deadline_ms = validity_deadline_ms;
    candidate.structural_validated = true;
    candidate.semantic_validated = true;
    candidate.motion_allowed = true;
    candidate.authorization_class = cfg::AuthorizationClass::MOTION;
    return candidate;
}

cfg::ConfigExpectation Expectation(const cfg::ConfigCandidate& candidate) {
    cfg::ConfigExpectation expectation = {};
    expectation.identity = candidate.identity;
    expectation.generation = candidate.generation;
    return expectation;
}

cfg::GenerationCommitToken Token(uint64_t generation) {
    cfg::GenerationCommitToken token = {};
    token.generation = generation;
    for (size_t index = 0; index < cfg::kCommitTokenSize; ++index) {
        token.bytes[index] = static_cast<uint8_t>(
            0x80U + index + static_cast<size_t>(generation & 0x1FU));
    }
    return token;
}

cfg::ConfigReference Reference(const cfg::ConfigCandidate& candidate) {
    cfg::ConfigReference reference = {};
    reference.identity = candidate.identity;
    reference.generation = candidate.generation;
    reference.authorization_class = candidate.authorization_class;
    return reference;
}

gw::Route Route(size_t index) {
    gw::Route route = {};
    route.token = static_cast<gw::RouteToken>(100 + index);
    route.bus_id = 1;
    route.node_id = static_cast<uint8_t>(index + 1);
    route.owner_id = kOwner;
    route.allowed_opcode_count = 1;
    route.allowed_opcodes[0] =
        static_cast<uint8_t>(v44::Command::kIqControl);
    route.safety_opcode = static_cast<uint8_t>(
        index == 0 ? v44::Command::kStop : v44::Command::kShutdown);
    return route;
}

gw::Route* InitializeRoutes(gw::Route* routes) {
    for (size_t index = 0; index < kRouteCount; ++index) {
        routes[index] = Route(index);
    }
    return routes;
}

v44::Frame IqRequest(uint8_t node_id, int16_t iq_raw) {
    v44::Frame frame = {};
    CHECK(v44::EncodeIqControlRaw(node_id, iq_raw, &frame) ==
          v44::Error::kOk);
    return frame;
}

enum class Action : uint8_t {
    COMPLETE_BOOT = 0,
    ACQUIRE_LEASE,
    ENABLE,
    ENQUEUE_VALID,
    ENQUEUE_WRONG_SESSION,
    ENQUEUE_REPLAYED_CONFIG_GENERATION,
    ENQUEUE_WRONG_OWNER,
    POLL,
    ADVANCE_ONE,
    ADVANCE_COMMAND_WINDOW,
    ADVANCE_TO_LEASE_DEADLINE,
    ADVANCE_TO_CONFIG_DEADLINE,
    TICK,
    RENEW_LEASE,
    REQUEST_SHUTDOWN,
    ACKNOWLEDGE_SHUTDOWN,
    RAISE_FAULT,
    PREREQUISITES_LOST,
    PREREQUISITES_READY,
    RESET_FAULT,
    REVOKE_CONFIG,
    ACTIVATE_NEW_CONFIG,
    BEGIN_CYCLE,
    RESPOND_TO_LAST_TX,
    FAIL_LAST_TRANSPORT,
    FORCE_CLOCK_REGRESSION,
    COUNT,
};

const char* ActionName(Action action) {
    switch (action) {
        case Action::COMPLETE_BOOT: return "COMPLETE_BOOT";
        case Action::ACQUIRE_LEASE: return "ACQUIRE_LEASE";
        case Action::ENABLE: return "ENABLE";
        case Action::ENQUEUE_VALID: return "ENQUEUE_VALID";
        case Action::ENQUEUE_WRONG_SESSION:
            return "ENQUEUE_WRONG_SESSION";
        case Action::ENQUEUE_REPLAYED_CONFIG_GENERATION:
            return "ENQUEUE_REPLAYED_CONFIG_GENERATION";
        case Action::ENQUEUE_WRONG_OWNER: return "ENQUEUE_WRONG_OWNER";
        case Action::POLL: return "POLL";
        case Action::ADVANCE_ONE: return "ADVANCE_ONE";
        case Action::ADVANCE_COMMAND_WINDOW:
            return "ADVANCE_COMMAND_WINDOW";
        case Action::ADVANCE_TO_LEASE_DEADLINE:
            return "ADVANCE_TO_LEASE_DEADLINE";
        case Action::ADVANCE_TO_CONFIG_DEADLINE:
            return "ADVANCE_TO_CONFIG_DEADLINE";
        case Action::TICK: return "TICK";
        case Action::RENEW_LEASE: return "RENEW_LEASE";
        case Action::REQUEST_SHUTDOWN: return "REQUEST_SHUTDOWN";
        case Action::ACKNOWLEDGE_SHUTDOWN:
            return "ACKNOWLEDGE_SHUTDOWN";
        case Action::RAISE_FAULT: return "RAISE_FAULT";
        case Action::PREREQUISITES_LOST: return "PREREQUISITES_LOST";
        case Action::PREREQUISITES_READY: return "PREREQUISITES_READY";
        case Action::RESET_FAULT: return "RESET_FAULT";
        case Action::REVOKE_CONFIG: return "REVOKE_CONFIG";
        case Action::ACTIVATE_NEW_CONFIG:
            return "ACTIVATE_NEW_CONFIG";
        case Action::BEGIN_CYCLE: return "BEGIN_CYCLE";
        case Action::RESPOND_TO_LAST_TX: return "RESPOND_TO_LAST_TX";
        case Action::FAIL_LAST_TRANSPORT: return "FAIL_LAST_TRANSPORT";
        case Action::FORCE_CLOCK_REGRESSION:
            return "FORCE_CLOCK_REGRESSION";
        case Action::COUNT: return "COUNT";
    }
    return "UNKNOWN_ACTION";
}

struct RunStats {
    uint64_t actions;
    uint64_t polls;
    uint64_t normal_frames;
    uint64_t safety_frames;

    RunStats()
        : actions(0), polls(0), normal_frames(0), safety_frames(0) {}
};

class Harness {
public:
    Harness()
        : routes_(),
          revision_(1),
          config_generation_(1),
          reference_(),
          config_guard_(SchemaPolicy()),
          supervisor_(SafetyConfiguration()),
          core_(InitializeRoutes(routes_), kRouteCount,
                gw::Policy(6, 1, 2), &config_guard_, &supervisor_),
          now_ms_(0),
          next_sequence_(1),
          next_command_generation_(1),
          last_issued_command_generation_(0),
          cycle_id_(1),
          enqueue_route_(0),
          last_tx_(),
          last_tx_present_(false),
          stats_() {
        CHECK(core_.valid());
        ActivateCurrentConfiguration();
        CHECK(core_.beginCycle(cycle_id_) == gw::Code::OK);
        AuditState();
        AuditDispositions();
    }

    void Execute(Action action) {
        g_action = ActionName(action);
        ++stats_.actions;
        ++g_actions;
        switch (action) {
            case Action::COMPLETE_BOOT:
                (void)supervisor_.completeBoot(
                    now_ms_, ReadyPrerequisites());
                break;
            case Action::ACQUIRE_LEASE:
                (void)supervisor_.acquireLease(
                    now_ms_, NextStamp(kOwner), kLeaseDurationMs);
                break;
            case Action::ENABLE:
                (void)supervisor_.enable(now_ms_, NextStamp(kOwner));
                break;
            case Action::ENQUEUE_VALID:
                Enqueue(kSession, kOwner, NextCommandGeneration());
                break;
            case Action::ENQUEUE_WRONG_SESSION:
                Enqueue(kSession ^ 0x00FF00FFUL, kOwner,
                        NextCommandGeneration());
                break;
            case Action::ENQUEUE_REPLAYED_CONFIG_GENERATION:
                Enqueue(
                    kSession, kOwner,
                    last_issued_command_generation_ == 0
                        ? static_cast<uint64_t>(1)
                        : last_issued_command_generation_);
                break;
            case Action::ENQUEUE_WRONG_OWNER:
                Enqueue(kSession, kOtherOwner, NextCommandGeneration());
                break;
            case Action::POLL:
                Poll();
                break;
            case Action::ADVANCE_ONE:
                ++now_ms_;
                break;
            case Action::ADVANCE_COMMAND_WINDOW:
                now_ms_ += kCommandLifetimeMs;
                break;
            case Action::ADVANCE_TO_LEASE_DEADLINE:
                AdvanceToLeaseDeadline();
                break;
            case Action::ADVANCE_TO_CONFIG_DEADLINE:
                AdvanceToConfigDeadline();
                break;
            case Action::TICK:
                (void)supervisor_.tick(now_ms_);
                break;
            case Action::RENEW_LEASE:
                (void)supervisor_.renewLease(
                    now_ms_, NextStamp(kOwner), kLeaseDurationMs);
                break;
            case Action::REQUEST_SHUTDOWN:
                (void)supervisor_.requestShutdown(
                    now_ms_, NextStamp(kOwner));
                break;
            case Action::ACKNOWLEDGE_SHUTDOWN:
                AcknowledgeShutdown();
                break;
            case Action::RAISE_FAULT:
                (void)supervisor_.raiseFault(
                    now_ms_, cfg::Fault::EXTERNAL);
                break;
            case Action::PREREQUISITES_LOST:
                (void)supervisor_.updatePrerequisites(
                    now_ms_, LostPrerequisites());
                break;
            case Action::PREREQUISITES_READY:
                (void)supervisor_.updatePrerequisites(
                    now_ms_, ReadyPrerequisites());
                break;
            case Action::RESET_FAULT:
                (void)supervisor_.resetFault(
                    now_ms_, NextStamp(kOwner), ReadyPrerequisites());
                break;
            case Action::REVOKE_CONFIG:
                (void)config_guard_.revoke(now_ms_);
                break;
            case Action::ACTIVATE_NEW_CONFIG:
                ++revision_;
                ++config_generation_;
                ActivateCurrentConfiguration();
                break;
            case Action::BEGIN_CYCLE:
                ++cycle_id_;
                CHECK(core_.beginCycle(cycle_id_) == gw::Code::OK);
                break;
            case Action::RESPOND_TO_LAST_TX:
                RespondToLastTransmit();
                break;
            case Action::FAIL_LAST_TRANSPORT:
                FailLastTransport();
                break;
            case Action::FORCE_CLOCK_REGRESSION:
                ForceClockRegression();
                break;
            case Action::COUNT:
                CHECK(false);
                break;
        }
        AuditState();
        AuditDispositions();
    }

    const RunStats& stats() const {
        return stats_;
    }

private:
    gw::Route routes_[kRouteCount];
    uint64_t revision_;
    uint64_t config_generation_;
    cfg::ConfigReference reference_;
    cfg::ConfigIdentityGuard config_guard_;
    cfg::SafetySupervisor supervisor_;
    gw::GatewayCore core_;
    uint64_t now_ms_;
    uint64_t next_sequence_;
    uint64_t next_command_generation_;
    uint64_t last_issued_command_generation_;
    uint64_t cycle_id_;
    size_t enqueue_route_;
    gw::TxEnvelope last_tx_;
    bool last_tx_present_;
    RunStats stats_;

    cfg::MessageStamp NextStamp(uint32_t owner) {
        return cfg::MessageStamp(owner, kSession, next_sequence_++);
    }

    uint64_t NextCommandGeneration() {
        const uint64_t generation = next_command_generation_++;
        last_issued_command_generation_ = generation;
        return generation;
    }

    void ActivateCurrentConfiguration() {
        const cfg::ConfigCandidate candidate = Candidate(
            revision_, config_generation_, now_ms_ + kConfigLifetimeMs);
        const cfg::GenerationCommitToken token =
            Token(candidate.generation);
        CHECK(config_guard_.stageCandidate(
                  now_ms_, candidate, Expectation(candidate), token) ==
              cfg::ConfigDecision::ALLOWED);
        CHECK(config_guard_.commitStaged(now_ms_, token) ==
              cfg::ConfigDecision::ALLOWED);
        reference_ = Reference(candidate);
    }

    void Enqueue(uint32_t session_id,
                 uint32_t owner_id,
                 uint64_t command_generation) {
        const size_t route_index = enqueue_route_++ % kRouteCount;
        const gw::Route& route = routes_[route_index];
        gw::Submission submission = {};
        submission.route_token = route.token;
        submission.bus_id = route.bus_id;
        submission.node_id = route.node_id;
        submission.owner_id = owner_id;
        submission.traffic_class = gw::TrafficClass::CONTROL;
        submission.config_proof.config = reference_;
        submission.config_proof.command_generation = command_generation;
        submission.safety_session_id = session_id;
        submission.safety_sequence = next_sequence_++;
        submission.absolute_deadline_ms =
            now_ms_ + kCommandLifetimeMs;
        submission.frame = IqRequest(
            route.node_id,
            static_cast<int16_t>(10 + command_generation % 100));
        (void)core_.enqueue(now_ms_, submission);
    }

    bool PrePollAuthorityValid(
        cfg::State state,
        bool outputs_permitted,
        const cfg::LeaseSnapshot& lease,
        const cfg::ConfigGuardSnapshot& config) const {
        return state == cfg::State::ENABLED && outputs_permitted &&
               lease.active && lease.owner_id == kOwner &&
               now_ms_ < lease.deadline_ms && config.active_present &&
               !config.revoked &&
               config.active.authorization_class ==
                   cfg::AuthorizationClass::MOTION &&
               now_ms_ < config.active.validity_deadline_ms;
    }

    void Poll() {
        ++stats_.polls;
        ++g_polls;
        const cfg::State state_before = supervisor_.state();
        const bool outputs_before = supervisor_.outputsPermitted();
        const cfg::LeaseSnapshot lease_before = supervisor_.lease();
        const cfg::ConfigGuardSnapshot config_before =
            config_guard_.snapshot();
        const bool authority_valid_before = PrePollAuthorityValid(
            state_before, outputs_before, lease_before, config_before);

        gw::TxEnvelope output = {};
        const gw::PollResult result =
            core_.pollTransmit(now_ms_, &output);
        CHECK(result != gw::PollResult::INVALID_CORE);
        if (result == gw::PollResult::NO_FRAME) {
            return;
        }

        CHECK(result == gw::PollResult::FRAME_READY);
        last_tx_ = output;
        last_tx_present_ = true;
        CHECK(output.bus_id == 1);
        CHECK(output.route_token == 100 || output.route_token == 101);
        CHECK(output.node_id == 1 || output.node_id == 2);
        CHECK(output.route_token ==
              static_cast<gw::RouteToken>(99 + output.node_id));
        CHECK(output.frame.arbitration_id ==
              v44::RequestArbitrationId(output.node_id));
        CHECK(output.frame.data[0] == output.opcode);

        gw::Disposition disposition = {};
        CHECK(core_.dispositionCount() != 0);
        CHECK(core_.dispositionAt(
            core_.dispositionCount() - 1, &disposition));
        CHECK(disposition.phase == gw::Phase::NATIVE_TX);
        CHECK(disposition.code == gw::Code::OK);
        CHECK(disposition.transaction_id == output.transaction_id);
        CHECK(disposition.route_token == output.route_token);
        CHECK(disposition.bus_id == output.bus_id);
        CHECK(disposition.node_id == output.node_id);
        CHECK(disposition.opcode == output.opcode);
        CHECK(disposition.safety_action == output.safety_action);

        if (output.safety_action) {
            ++stats_.safety_frames;
            ++g_safety_frames;
            CHECK(output.opcode ==
                      static_cast<uint8_t>(v44::Command::kStop) ||
                  output.opcode ==
                      static_cast<uint8_t>(v44::Command::kShutdown));
            CHECK(supervisor_.state() == cfg::State::SHUTDOWN ||
                  supervisor_.state() == cfg::State::FAULT);
            CHECK(!supervisor_.outputsPermitted());
            return;
        }

        ++stats_.normal_frames;
        ++g_normal_frames;
        CHECK(authority_valid_before);
        CHECK(output.opcode ==
              static_cast<uint8_t>(v44::Command::kIqControl));
        CHECK(disposition.owner_id == kOwner);
        CHECK(disposition.session_id == kSession);
        CHECK(disposition.sequence != 0);
        CHECK(disposition.command_generation != 0);
        CHECK(disposition.config_checked);
        CHECK(disposition.config_decision ==
              cfg::ConfigDecision::ALLOWED);
        CHECK(disposition.safety_checked);
        CHECK(disposition.safety_result == cfg::Result::OK);
        CHECK(supervisor_.state() == cfg::State::ENABLED);
        CHECK(supervisor_.outputsPermitted());
        const cfg::LeaseSnapshot lease_after = supervisor_.lease();
        CHECK(lease_after.active);
        CHECK(lease_after.owner_id == kOwner);
        CHECK(now_ms_ < lease_after.deadline_ms);
        const cfg::ConfigGuardSnapshot config_after =
            config_guard_.snapshot();
        CHECK(config_after.active_present);
        CHECK(!config_after.revoked);
        CHECK(now_ms_ < config_after.active.validity_deadline_ms);
    }

    void AdvanceToLeaseDeadline() {
        const cfg::LeaseSnapshot lease = supervisor_.lease();
        if (lease.active && now_ms_ < lease.deadline_ms) {
            now_ms_ = lease.deadline_ms;
        } else {
            ++now_ms_;
        }
    }

    void AdvanceToConfigDeadline() {
        const cfg::ConfigGuardSnapshot config = config_guard_.snapshot();
        if (config.active_present &&
            now_ms_ < config.active.validity_deadline_ms) {
            now_ms_ = config.active.validity_deadline_ms;
        } else {
            ++now_ms_;
        }
    }

    void AcknowledgeShutdown() {
        const cfg::ShutdownSnapshot shutdown = supervisor_.shutdown();
        const uint64_t generation =
            shutdown.active ? shutdown.generation : 0;
        (void)supervisor_.acknowledgeShutdown(
            now_ms_, generation, true);
    }

    v44::Frame ResponseFor(const gw::TxEnvelope& transmitted) {
        v44::Frame response = transmitted.frame;
        response.arbitration_id =
            v44::ResponseArbitrationId(transmitted.node_id);
        return response;
    }

    void RespondToLastTransmit() {
        if (!last_tx_present_) {
            return;
        }
        const gw::Code response = core_.acceptResponse(
            now_ms_, last_tx_.bus_id, ResponseFor(last_tx_));
        if (response != gw::Code::OK) {
            return;
        }
        bool response_slot_released = false;
        if (!last_tx_.safety_action &&
            last_tx_.opcode ==
                static_cast<uint8_t>(v44::Command::kIqControl)) {
            CHECK(core_.recordObservation(
                      now_ms_, last_tx_.transaction_id,
                      gw::ObservationClass::NATIVE_STATE_SAMPLE) ==
                  gw::Code::OK);
            response_slot_released = true;
        }
        if (!response_slot_released) {
            CHECK(core_.releaseCompletedResponse(
                      last_tx_.transaction_id) == gw::Code::OK);
        }
        last_tx_present_ = false;
    }

    void FailLastTransport() {
        if (!last_tx_present_) {
            return;
        }
        const gw::Code result = core_.reportTransportFailure(
            now_ms_, last_tx_.transaction_id,
            gw::TransportFailure::TX_FAILED);
        if (result == gw::Code::TRANSPORT_TX_FAILED) {
            CHECK(supervisor_.state() == cfg::State::FAULT);
            CHECK(!supervisor_.outputsPermitted());
            last_tx_present_ = false;
        }
    }

    void ForceClockRegression() {
        if (now_ms_ == 0) {
            ++now_ms_;
        }
        (void)supervisor_.tick(now_ms_);
        (void)config_guard_.authorizeArm(now_ms_, reference_);
        CHECK(supervisor_.tick(now_ms_ - 1) ==
              cfg::Result::CLOCK_REGRESSION);
        CHECK(config_guard_.revoke(now_ms_ - 1) ==
              cfg::ConfigDecision::CLOCK_REGRESSION);
        CHECK(supervisor_.state() == cfg::State::FAULT);
        CHECK(config_guard_.snapshot().revoked);
    }

    void AuditState() {
        const cfg::State state = supervisor_.state();
        const cfg::LeaseSnapshot lease = supervisor_.lease();
        CHECK(supervisor_.outputsPermitted() ==
              (state == cfg::State::ENABLED && lease.active));
        if (supervisor_.outputsPermitted()) {
            CHECK(lease.owner_id == kOwner);
        }
        CHECK(supervisor_.shutdownIntent() ==
              (state == cfg::State::SHUTDOWN ||
               state == cfg::State::FAULT));
        if (state == cfg::State::SHUTDOWN || state == cfg::State::FAULT) {
            CHECK(!supervisor_.outputsPermitted());
        }
        const cfg::ConfigGuardSnapshot config = config_guard_.snapshot();
        if (config.revoked) {
            CHECK(!config.usable_at_last_observed_time);
        }
    }

    void AuditDispositions() {
        uint64_t previous_event_id = 0;
        for (size_t index = 0; index < core_.dispositionCount(); ++index) {
            gw::Disposition event = {};
            CHECK(core_.dispositionAt(index, &event));
            CHECK(event.event_id > previous_event_id);
            previous_event_id = event.event_id;
            if (event.phase != gw::Phase::NATIVE_TX) {
                continue;
            }
            CHECK(event.code == gw::Code::OK);
            CHECK(event.transaction_id != 0);
            if (event.safety_action) {
                CHECK(event.opcode ==
                          static_cast<uint8_t>(v44::Command::kStop) ||
                      event.opcode ==
                          static_cast<uint8_t>(v44::Command::kShutdown));
                continue;
            }
            CHECK(event.opcode ==
                  static_cast<uint8_t>(v44::Command::kIqControl));
            CHECK(event.owner_id == kOwner);
            CHECK(event.session_id == kSession);
            CHECK(event.sequence != 0);
            CHECK(event.command_generation != 0);
            CHECK(event.config_checked);
            CHECK(event.config_decision ==
                  cfg::ConfigDecision::ALLOWED);
            CHECK(event.safety_checked);
            CHECK(event.safety_result == cfg::Result::OK);
        }
    }
};

RunStats RunTrace(const char* name,
                  const Action* actions,
                  size_t action_count) {
    g_trace = name;
    g_seed = 0;
    g_step = 0;
    ++g_sequences;
    Harness harness;
    for (size_t index = 0; index < action_count; ++index) {
        g_step = index;
        harness.Execute(actions[index]);
    }
    return harness.stats();
}

void CheckExpectedNormalFrames(const char* name,
                               const Action* actions,
                               size_t action_count,
                               uint64_t expected) {
    const RunStats result = RunTrace(name, actions, action_count);
    g_action = "TRACE_EXPECTATION";
    CHECK(result.normal_frames == expected);
}

void RunCuratedAdversarialTraces() {
    const Action valid[] = {
        Action::COMPLETE_BOOT,
        Action::ACQUIRE_LEASE,
        Action::ENABLE,
        Action::ENQUEUE_VALID,
        Action::POLL,
    };
    CheckExpectedNormalFrames(
        "curated-valid-non-vacuous", valid,
        sizeof(valid) / sizeof(valid[0]), 1);

    const Action revoke[] = {
        Action::COMPLETE_BOOT,
        Action::ACQUIRE_LEASE,
        Action::ENABLE,
        Action::ENQUEUE_VALID,
        Action::REVOKE_CONFIG,
        Action::POLL,
    };
    CheckExpectedNormalFrames(
        "curated-queued-then-revoke", revoke,
        sizeof(revoke) / sizeof(revoke[0]), 0);

    const Action lease_expiry[] = {
        Action::COMPLETE_BOOT,
        Action::ACQUIRE_LEASE,
        Action::ENABLE,
        Action::ENQUEUE_VALID,
        Action::ADVANCE_TO_LEASE_DEADLINE,
        Action::POLL,
    };
    CheckExpectedNormalFrames(
        "curated-queued-then-lease-expiry", lease_expiry,
        sizeof(lease_expiry) / sizeof(lease_expiry[0]), 0);

    const Action command_expiry[] = {
        Action::COMPLETE_BOOT,
        Action::ACQUIRE_LEASE,
        Action::ENABLE,
        Action::ENQUEUE_VALID,
        Action::ADVANCE_COMMAND_WINDOW,
        Action::POLL,
    };
    CheckExpectedNormalFrames(
        "curated-queued-then-command-expiry", command_expiry,
        sizeof(command_expiry) / sizeof(command_expiry[0]), 0);

    const Action config_expiry[] = {
        Action::COMPLETE_BOOT,
        Action::ACQUIRE_LEASE,
        Action::ENABLE,
        Action::ENQUEUE_VALID,
        Action::ADVANCE_TO_CONFIG_DEADLINE,
        Action::POLL,
    };
    CheckExpectedNormalFrames(
        "curated-queued-then-config-expiry", config_expiry,
        sizeof(config_expiry) / sizeof(config_expiry[0]), 0);

    const Action fault[] = {
        Action::COMPLETE_BOOT,
        Action::ACQUIRE_LEASE,
        Action::ENABLE,
        Action::ENQUEUE_VALID,
        Action::RAISE_FAULT,
        Action::POLL,
    };
    CheckExpectedNormalFrames(
        "curated-queued-then-fault", fault,
        sizeof(fault) / sizeof(fault[0]), 0);

    const Action prerequisite_loss[] = {
        Action::COMPLETE_BOOT,
        Action::ACQUIRE_LEASE,
        Action::ENABLE,
        Action::ENQUEUE_VALID,
        Action::PREREQUISITES_LOST,
        Action::POLL,
    };
    CheckExpectedNormalFrames(
        "curated-queued-then-prerequisite-loss", prerequisite_loss,
        sizeof(prerequisite_loss) / sizeof(prerequisite_loss[0]), 0);

    const Action shutdown[] = {
        Action::COMPLETE_BOOT,
        Action::ACQUIRE_LEASE,
        Action::ENABLE,
        Action::ENQUEUE_VALID,
        Action::REQUEST_SHUTDOWN,
        Action::POLL,
    };
    CheckExpectedNormalFrames(
        "curated-queued-then-shutdown", shutdown,
        sizeof(shutdown) / sizeof(shutdown[0]), 0);

    const Action shutdown_ack[] = {
        Action::COMPLETE_BOOT,
        Action::ACQUIRE_LEASE,
        Action::ENABLE,
        Action::ENQUEUE_VALID,
        Action::REQUEST_SHUTDOWN,
        Action::ACKNOWLEDGE_SHUTDOWN,
        Action::POLL,
    };
    CheckExpectedNormalFrames(
        "curated-shutdown-ack-does-not-reenable", shutdown_ack,
        sizeof(shutdown_ack) / sizeof(shutdown_ack[0]), 0);

    const Action reset[] = {
        Action::COMPLETE_BOOT,
        Action::ACQUIRE_LEASE,
        Action::ENABLE,
        Action::ENQUEUE_VALID,
        Action::RAISE_FAULT,
        Action::RESET_FAULT,
        Action::POLL,
    };
    CheckExpectedNormalFrames(
        "curated-reset-returns-only-to-boot", reset,
        sizeof(reset) / sizeof(reset[0]), 0);

    const Action config_turnover[] = {
        Action::COMPLETE_BOOT,
        Action::ACQUIRE_LEASE,
        Action::ENABLE,
        Action::ENQUEUE_VALID,
        Action::ACTIVATE_NEW_CONFIG,
        Action::POLL,
    };
    CheckExpectedNormalFrames(
        "curated-queued-then-config-turnover", config_turnover,
        sizeof(config_turnover) / sizeof(config_turnover[0]), 0);

    const Action fresh_config[] = {
        Action::COMPLETE_BOOT,
        Action::ACQUIRE_LEASE,
        Action::ENABLE,
        Action::ACTIVATE_NEW_CONFIG,
        Action::ENQUEUE_VALID,
        Action::POLL,
    };
    CheckExpectedNormalFrames(
        "curated-fresh-config-remains-operable", fresh_config,
        sizeof(fresh_config) / sizeof(fresh_config[0]), 1);

    const Action newer_sequence[] = {
        Action::COMPLETE_BOOT,
        Action::ACQUIRE_LEASE,
        Action::ENABLE,
        Action::ENQUEUE_VALID,
        Action::RENEW_LEASE,
        Action::POLL,
    };
    CheckExpectedNormalFrames(
        "curated-delayed-command-sequence-replay", newer_sequence,
        sizeof(newer_sequence) / sizeof(newer_sequence[0]), 0);

    const Action wrong_session[] = {
        Action::COMPLETE_BOOT,
        Action::ACQUIRE_LEASE,
        Action::ENABLE,
        Action::ENQUEUE_WRONG_SESSION,
        Action::POLL,
    };
    CheckExpectedNormalFrames(
        "curated-wrong-session", wrong_session,
        sizeof(wrong_session) / sizeof(wrong_session[0]), 0);

    const Action clock_regression[] = {
        Action::COMPLETE_BOOT,
        Action::ACQUIRE_LEASE,
        Action::ENABLE,
        Action::ENQUEUE_VALID,
        Action::ADVANCE_ONE,
        Action::FORCE_CLOCK_REGRESSION,
        Action::POLL,
    };
    CheckExpectedNormalFrames(
        "curated-clock-regression", clock_regression,
        sizeof(clock_regression) / sizeof(clock_regression[0]), 0);

    const Action transport_failure[] = {
        Action::COMPLETE_BOOT,
        Action::ACQUIRE_LEASE,
        Action::ENABLE,
        Action::ENQUEUE_VALID,
        Action::POLL,
        Action::FAIL_LAST_TRANSPORT,
        Action::ENQUEUE_VALID,
        Action::POLL,
    };
    CheckExpectedNormalFrames(
        "curated-transport-failure-faults-closed", transport_failure,
        sizeof(transport_failure) / sizeof(transport_failure[0]), 1);

    const Action response_and_continue[] = {
        Action::COMPLETE_BOOT,
        Action::ACQUIRE_LEASE,
        Action::ENABLE,
        Action::ENQUEUE_VALID,
        Action::POLL,
        Action::RESPOND_TO_LAST_TX,
        Action::ENQUEUE_VALID,
        Action::POLL,
    };
    CheckExpectedNormalFrames(
        "curated-correlated-response-continues", response_and_continue,
        sizeof(response_and_continue) / sizeof(response_and_continue[0]), 2);
}

void RunPairwiseEnabledSuffixes() {
    const size_t action_count =
        static_cast<size_t>(Action::COUNT);
    for (size_t first = 0; first < action_count; ++first) {
        for (size_t second = 0; second < action_count; ++second) {
            const Action trace[] = {
                Action::COMPLETE_BOOT,
                Action::ACQUIRE_LEASE,
                Action::ENABLE,
                static_cast<Action>(first),
                static_cast<Action>(second),
                Action::POLL,
            };
            g_trace = "pairwise-enabled-suffix";
            g_seed = first * action_count + second;
            g_step = 0;
            ++g_sequences;
            Harness harness;
            for (size_t index = 0;
                 index < sizeof(trace) / sizeof(trace[0]); ++index) {
                g_step = index;
                harness.Execute(trace[index]);
            }
        }
    }
}

uint64_t NextRandom(uint64_t* state) {
    CHECK(state != NULL);
    uint64_t value = *state;
    value ^= value >> 12;
    value ^= value << 25;
    value ^= value >> 27;
    *state = value;
    return value * UINT64_C(2685821657736338717);
}

void RunSeededLongHaulCorpus() {
    const size_t kSeedCount = 4096;
    const size_t kActionsPerSeed = 64;
    const size_t action_count =
        static_cast<size_t>(Action::COUNT);

    for (size_t seed_index = 0; seed_index < kSeedCount; ++seed_index) {
        g_trace = "seeded-long-haul";
        g_seed = UINT64_C(0x9E3779B97F4A7C15) ^
                 static_cast<uint64_t>(seed_index + 1);
        g_step = 0;
        ++g_sequences;
        Harness harness;

        const size_t prefix = seed_index % 4;
        if (prefix >= 1) {
            harness.Execute(Action::COMPLETE_BOOT);
        }
        if (prefix >= 2) {
            harness.Execute(Action::ACQUIRE_LEASE);
        }
        if (prefix >= 3) {
            harness.Execute(Action::ENABLE);
        }

        uint64_t random_state = g_seed;
        for (size_t step = 0; step < kActionsPerSeed; ++step) {
            g_step = step + prefix;
            const Action action = static_cast<Action>(
                NextRandom(&random_state) % action_count);
            harness.Execute(action);
        }
    }
}

}  // namespace

int main() {
    RunCuratedAdversarialTraces();
    RunPairwiseEnabledSuffixes();
    RunSeededLongHaulCorpus();

    g_trace = "global-non-vacuity";
    g_action = "FINAL_INVARIANTS";
    g_seed = 0;
    g_step = 0;
    CHECK(g_normal_frames >= 3);
    CHECK(g_safety_frames >= 3);
    CHECK(g_polls >= 1000);
    CHECK(g_sequences == 17 +
          static_cast<uint64_t>(Action::COUNT) *
              static_cast<uint64_t>(Action::COUNT) +
          4096);

    std::cout << "SAFETY_EVENT_PROPERTIES_OK checks=" << g_checks
              << " sequences=" << g_sequences
              << " actions=" << g_actions
              << " polls=" << g_polls
              << " normal_tx=" << g_normal_frames
              << " safety_tx=" << g_safety_frames << '\n';
    return 0;
}
