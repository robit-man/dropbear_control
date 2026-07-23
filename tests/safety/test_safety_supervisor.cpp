#include "safety_supervisor.h"

#include <stdint.h>

#include <iostream>

using myactuator::safety::Configuration;
using myactuator::safety::Fault;
using myactuator::safety::MessageStamp;
using myactuator::safety::Prerequisites;
using myactuator::safety::Result;
using myactuator::safety::SafetySupervisor;
using myactuator::safety::State;

namespace {

int failures = 0;
int checks = 0;

#define CHECK(condition)                                                        \
    do {                                                                        \
        ++checks;                                                               \
        if (!(condition)) {                                                     \
            ++failures;                                                         \
            std::cerr << __FILE__ << ':' << __LINE__                            \
                      << ": check failed: " #condition << '\n';                \
        }                                                                       \
    } while (false)

const uint32_t kSession = 0xA55A1234UL;
const uint32_t kOwnerOne = 1;
const uint32_t kOwnerTwo = 2;
const uint32_t kOwnerThree = 3;

Configuration validConfiguration() {
    // Owners 1 and 2 may command; only owner 1 may reset faults.
    return Configuration(kSession, 10, 1000, 20, 0x3, 0x1);
}

Prerequisites readyPrerequisites() {
    Prerequisites prerequisites;
    prerequisites.configuration_valid = true;
    prerequisites.expected_nodes_present = true;
    prerequisites.transport_ready = true;
    prerequisites.safety_interlock_ready = true;
    prerequisites.external_faults_clear = true;
    prerequisites.motor_off_confirmed = true;
    return prerequisites;
}

bool hasFault(const SafetySupervisor& supervisor, Fault fault) {
    return (supervisor.faultMask() & static_cast<uint32_t>(fault)) != 0;
}

void bootToDisabled(SafetySupervisor& supervisor, uint64_t now_ms = 0) {
    CHECK(supervisor.completeBoot(now_ms, readyPrerequisites()) == Result::OK);
    CHECK(supervisor.state() == State::DISABLED);
    CHECK(!supervisor.outputsPermitted());
}

void bootAndEnable(SafetySupervisor& supervisor,
                   uint64_t now_ms,
                   uint32_t lease_ms,
                   uint64_t first_sequence = 1) {
    bootToDisabled(supervisor, now_ms);
    CHECK(supervisor.acquireLease(
              now_ms, MessageStamp(kOwnerOne, kSession, first_sequence),
              lease_ms) == Result::OK);
    CHECK(supervisor.state() == State::ARMED);
    CHECK(!supervisor.outputsPermitted());
    CHECK(supervisor.enable(
              now_ms, MessageStamp(kOwnerOne, kSession, first_sequence + 1)) ==
          Result::OK);
    CHECK(supervisor.state() == State::ENABLED);
    CHECK(supervisor.outputsPermitted());
}

void testBootIsDisabledAndGated() {
    SafetySupervisor supervisor(validConfiguration());
    CHECK(supervisor.state() == State::BOOT);
    CHECK(!supervisor.outputsPermitted());
    CHECK(!supervisor.shutdownIntent());
    CHECK(!supervisor.lease().active);

    CHECK(supervisor.beginDiscovery(0) == Result::OK);
    CHECK(supervisor.state() == State::DISCOVERY);
    CHECK(!supervisor.outputsPermitted());

    Prerequisites not_ready = readyPrerequisites();
    not_ready.configuration_valid = false;
    CHECK(supervisor.completeDiscovery(0, not_ready) ==
          Result::PREREQUISITES_NOT_MET);
    CHECK(supervisor.state() == State::DISCOVERY);
    CHECK(supervisor.completeDiscovery(1, readyPrerequisites()) == Result::OK);
    CHECK(supervisor.state() == State::DISABLED);
    CHECK(supervisor.completeBoot(2, readyPrerequisites()) ==
          Result::INVALID_STATE);
}

void testInvalidConfigurationFaultsClosed() {
    const Configuration configurations[] = {
        Configuration(0, 10, 100, 20, 1, 1),
        Configuration(kSession, 0, 100, 20, 1, 1),
        Configuration(kSession, 101, 100, 20, 1, 1),
        Configuration(kSession, 10, 100, 0, 1, 1),
        Configuration(kSession, 10, 100, 20, 0, 0),
        Configuration(kSession, 10, 100, 20, 1, 0),
        Configuration(kSession, 10, 100, 20, 1, 2),
    };

    for (const Configuration& configuration : configurations) {
        SafetySupervisor supervisor(configuration);
        CHECK(supervisor.beginDiscovery(0) ==
              Result::CONFIGURATION_INVALID);
        CHECK(supervisor.state() == State::FAULT);
        CHECK(supervisor.shutdownIntent());
        CHECK(!supervisor.outputsPermitted());
        CHECK(hasFault(supervisor, Fault::CONFIGURATION_INVALID));

        // A malformed immutable configuration can never be reset into a
        // runnable state, even if the remaining fields happen to name a valid
        // reset owner.
        CHECK(supervisor.resetFault(
                  1, MessageStamp(kOwnerOne, configuration.session_id, 1),
                  readyPrerequisites()) != Result::OK);
        CHECK(supervisor.state() == State::FAULT);
    }
}

void testInvalidTransitionsConsumeFreshSequences() {
    SafetySupervisor supervisor(validConfiguration());

    CHECK(supervisor.acquireLease(
              0, MessageStamp(kOwnerOne, kSession, 1), 100) ==
          Result::INVALID_STATE);
    bootToDisabled(supervisor, 1);
    CHECK(supervisor.acquireLease(
              1, MessageStamp(kOwnerOne, kSession, 1), 100) ==
          Result::REPLAYED_OR_OUT_OF_ORDER);
    CHECK(supervisor.enable(1, MessageStamp(kOwnerOne, kSession, 2)) ==
          Result::INVALID_STATE);
    CHECK(supervisor.acquireLease(
              1, MessageStamp(kOwnerOne, kSession, 3), 100) == Result::OK);
    CHECK(supervisor.authorizeCommand(
              1, MessageStamp(kOwnerOne, kSession, 4)) ==
          Result::INVALID_STATE);
    CHECK(supervisor.enable(1, MessageStamp(kOwnerOne, kSession, 5)) ==
          Result::OK);
    CHECK(supervisor.authorizeCommand(
              1, MessageStamp(kOwnerOne, kSession, 4)) ==
          Result::REPLAYED_OR_OUT_OF_ORDER);
    CHECK(supervisor.authorizeCommand(
              1, MessageStamp(kOwnerOne, kSession, 6)) == Result::OK);
}

void testIdentityAndReplayDefenses() {
    SafetySupervisor supervisor(validConfiguration());
    bootToDisabled(supervisor);

    CHECK(supervisor.acquireLease(0, MessageStamp(0, kSession, 1), 100) ==
          Result::INVALID_OWNER);
    CHECK(supervisor.acquireLease(
              0, MessageStamp(kOwnerThree, kSession, 1), 100) ==
          Result::INVALID_OWNER);
    CHECK(supervisor.acquireLease(
              0, MessageStamp(kOwnerOne, kSession + 1, 1), 100) ==
          Result::INVALID_SESSION);
    CHECK(supervisor.acquireLease(
              0, MessageStamp(kOwnerOne, kSession, 0), 100) ==
          Result::REPLAYED_OR_OUT_OF_ORDER);
    CHECK(supervisor.acquireLease(
              0, MessageStamp(kOwnerOne, kSession, 10), 100) == Result::OK);
    CHECK(supervisor.renewLease(
              1, MessageStamp(kOwnerOne, kSession, 10), 100) ==
          Result::REPLAYED_OR_OUT_OF_ORDER);
    CHECK(supervisor.renewLease(
              1, MessageStamp(kOwnerOne, kSession, 9), 100) ==
          Result::REPLAYED_OR_OUT_OF_ORDER);
    CHECK(supervisor.renewLease(
              1, MessageStamp(kOwnerOne, kSession, 11), 100) == Result::OK);
}

void testLeaseDurationAndDeadlineBoundaries() {
    SafetySupervisor supervisor(validConfiguration());
    bootToDisabled(supervisor, 100);

    CHECK(supervisor.acquireLease(
              100, MessageStamp(kOwnerOne, kSession, 1), 9) ==
          Result::INVALID_LEASE_DURATION);
    CHECK(supervisor.acquireLease(
              100, MessageStamp(kOwnerOne, kSession, 2), 1001) ==
          Result::INVALID_LEASE_DURATION);
    CHECK(supervisor.acquireLease(
              100, MessageStamp(kOwnerOne, kSession, 3), 10) == Result::OK);
    CHECK(supervisor.lease().deadline_ms == 110);
    CHECK(supervisor.tick(109) == Result::OK);
    CHECK(supervisor.state() == State::ARMED);
    CHECK(supervisor.tick(110) == Result::LEASE_EXPIRED);
    CHECK(supervisor.state() == State::SHUTDOWN);
    CHECK(!supervisor.lease().active);
    CHECK(supervisor.faultMask() == 0);
    CHECK(supervisor.acknowledgeShutdown(
              110, supervisor.shutdown().generation, true) == Result::OK);
    CHECK(supervisor.state() == State::DISABLED);

    CHECK(supervisor.acquireLease(
              111, MessageStamp(kOwnerOne, kSession, 4), 1000) == Result::OK);
    CHECK(supervisor.lease().deadline_ms == 1111);
}

void testEnabledLeaseExpiryFaultsAndLatches() {
    SafetySupervisor supervisor(validConfiguration());
    bootAndEnable(supervisor, 0, 100);

    CHECK(supervisor.tick(99) == Result::OK);
    CHECK(supervisor.outputsPermitted());
    CHECK(supervisor.tick(100) == Result::LEASE_EXPIRED);
    CHECK(supervisor.state() == State::SHUTDOWN);
    CHECK(!supervisor.outputsPermitted());
    CHECK(supervisor.shutdownIntent());
    CHECK(!supervisor.lease().active);
    CHECK(!hasFault(supervisor, Fault::LEASE_EXPIRED));
    const uint64_t generation = supervisor.shutdown().generation;
    CHECK(supervisor.acknowledgeShutdown(101, generation - 1, true) ==
          Result::SHUTDOWN_ACK_MISMATCH);
    CHECK(supervisor.tick(120) == Result::MOTOR_OFF_NOT_CONFIRMED);
    CHECK(supervisor.state() == State::FAULT);
    CHECK(hasFault(supervisor, Fault::SHUTDOWN_TIMEOUT));

    Prerequisites not_off = readyPrerequisites();
    not_off.motor_off_confirmed = false;
    CHECK(supervisor.resetFault(
              121, MessageStamp(kOwnerOne, kSession, 3), not_off) ==
          Result::MOTOR_OFF_NOT_CONFIRMED);
    CHECK(supervisor.state() == State::FAULT);
    CHECK(hasFault(supervisor, Fault::SHUTDOWN_TIMEOUT));

    Prerequisites unresolved = readyPrerequisites();
    unresolved.external_faults_clear = false;
    CHECK(supervisor.resetFault(
              122, MessageStamp(kOwnerOne, kSession, 4), unresolved) ==
          Result::PREREQUISITES_NOT_MET);
    CHECK(supervisor.state() == State::FAULT);
    CHECK(supervisor.resetFault(
              123, MessageStamp(kOwnerOne, kSession, 5),
              readyPrerequisites()) == Result::OK);
    CHECK(supervisor.state() == State::BOOT);
    CHECK(supervisor.faultMask() == 0);
    CHECK(!supervisor.shutdownIntent());
    CHECK(supervisor.completeBoot(124, readyPrerequisites()) == Result::OK);
    CHECK(supervisor.state() == State::DISABLED);
}

void testSingleWriterContentionAndPerOwnerReplay() {
    SafetySupervisor supervisor(validConfiguration());
    bootToDisabled(supervisor);
    CHECK(supervisor.acquireLease(
              0, MessageStamp(kOwnerOne, kSession, 1), 100) == Result::OK);
    CHECK(supervisor.renewLease(
              1, MessageStamp(kOwnerTwo, kSession, 1), 100) ==
          Result::OWNER_CONFLICT);
    CHECK(supervisor.enable(1, MessageStamp(kOwnerTwo, kSession, 2)) ==
          Result::OWNER_CONFLICT);
    CHECK(supervisor.state() == State::ARMED);
    CHECK(supervisor.enable(1, MessageStamp(kOwnerOne, kSession, 2)) ==
          Result::OK);
    CHECK(supervisor.authorizeCommand(
              2, MessageStamp(kOwnerTwo, kSession, 3)) ==
          Result::OWNER_CONFLICT);
    CHECK(supervisor.authorizeCommand(
              2, MessageStamp(kOwnerOne, kSession, 3)) == Result::OK);
    CHECK(supervisor.requestShutdown(
              3, MessageStamp(kOwnerOne, kSession, 4)) == Result::OK);
    CHECK(supervisor.acknowledgeShutdown(
              4, supervisor.shutdown().generation, true) == Result::OK);

    // Owner two's previously consumed contention message cannot be replayed.
    CHECK(supervisor.acquireLease(
              5, MessageStamp(kOwnerTwo, kSession, 3), 100) ==
          Result::REPLAYED_OR_OUT_OF_ORDER);
    CHECK(supervisor.acquireLease(
              5, MessageStamp(kOwnerTwo, kSession, 4), 100) == Result::OK);
    CHECK(supervisor.lease().owner_id == kOwnerTwo);
}

void testExplicitShutdownRequiresMotorOffEvidence() {
    SafetySupervisor supervisor(validConfiguration());
    bootAndEnable(supervisor, 0, 100);
    CHECK(supervisor.requestShutdown(
              1, MessageStamp(kOwnerOne, kSession, 3)) == Result::OK);
    CHECK(supervisor.state() == State::SHUTDOWN);
    CHECK(supervisor.shutdownIntent());
    CHECK(!supervisor.outputsPermitted());
    CHECK(!supervisor.lease().active);
    const uint64_t first_generation = supervisor.shutdown().generation;
    CHECK(supervisor.acknowledgeShutdown(2, first_generation, false) ==
          Result::MOTOR_OFF_NOT_CONFIRMED);
    CHECK(supervisor.state() == State::SHUTDOWN);
    CHECK(supervisor.acknowledgeShutdown(3, first_generation, true) == Result::OK);
    CHECK(supervisor.state() == State::DISABLED);
    CHECK(!supervisor.shutdownIntent());

    CHECK(supervisor.acquireLease(
              4, MessageStamp(kOwnerOne, kSession, 4), 100) == Result::OK);
    CHECK(supervisor.requestShutdown(
              5, MessageStamp(kOwnerOne, kSession, 5)) == Result::OK);
    CHECK(supervisor.state() == State::SHUTDOWN);
    CHECK(supervisor.shutdown().generation != first_generation);
    CHECK(supervisor.acknowledgeShutdown(6, first_generation, true) ==
          Result::SHUTDOWN_ACK_MISMATCH);
    CHECK(supervisor.acknowledgeShutdown(
              6, supervisor.shutdown().generation, true) == Result::OK);
    CHECK(supervisor.state() == State::DISABLED);
}

void testPrerequisiteLossFaultsActiveStates() {
    bool Prerequisites::*const fields[] = {
        &Prerequisites::configuration_valid,
        &Prerequisites::expected_nodes_present,
        &Prerequisites::transport_ready,
        &Prerequisites::safety_interlock_ready,
        &Prerequisites::external_faults_clear,
    };

    for (size_t i = 0; i < sizeof(fields) / sizeof(fields[0]); ++i) {
        SafetySupervisor supervisor(validConfiguration());
        bootAndEnable(supervisor, 0, 100);
        Prerequisites lost = readyPrerequisites();
        lost.*fields[i] = false;
        CHECK(supervisor.updatePrerequisites(1, lost) ==
              Result::PREREQUISITES_NOT_MET);
        CHECK(supervisor.state() == State::FAULT);
        CHECK(supervisor.shutdownIntent());
        CHECK(!supervisor.outputsPermitted());
        CHECK(hasFault(supervisor, Fault::PREREQUISITE_LOST));
    }

    SafetySupervisor armed(validConfiguration());
    bootToDisabled(armed);
    CHECK(armed.acquireLease(
              0, MessageStamp(kOwnerOne, kSession, 1), 100) == Result::OK);
    Prerequisites lost = readyPrerequisites();
    lost.transport_ready = false;
    CHECK(armed.updatePrerequisites(1, lost) ==
          Result::PREREQUISITES_NOT_MET);
    CHECK(armed.state() == State::FAULT);
    CHECK(hasFault(armed, Fault::PREREQUISITE_LOST));
}

void testFaultLatchingAndGuardedReset() {
    SafetySupervisor supervisor(validConfiguration());
    bootAndEnable(supervisor, 0, 100);
    CHECK(supervisor.raiseFault(1, Fault::EXTERNAL) == Result::OK);
    CHECK(supervisor.raiseFault(2, Fault::PREREQUISITE_LOST) == Result::OK);
    CHECK(supervisor.state() == State::FAULT);
    CHECK(hasFault(supervisor, Fault::EXTERNAL));
    CHECK(hasFault(supervisor, Fault::PREREQUISITE_LOST));
    CHECK(!supervisor.outputsPermitted());

    CHECK(supervisor.resetFault(
              3, MessageStamp(kOwnerTwo, kSession, 1),
              readyPrerequisites()) == Result::RESET_NOT_AUTHORIZED);
    CHECK(supervisor.state() == State::FAULT);
    CHECK(supervisor.faultMask() != 0);
    CHECK(supervisor.resetFault(
              4, MessageStamp(kOwnerOne, kSession, 3),
              readyPrerequisites()) == Result::OK);
    CHECK(supervisor.state() == State::BOOT);
    CHECK(supervisor.faultMask() == 0);
    CHECK(supervisor.raiseFault(5, Fault::NONE) ==
          Result::CONFIGURATION_INVALID);
    CHECK(supervisor.state() == State::BOOT);
}

void testClockRegressionFaultsClosed() {
    SafetySupervisor supervisor(validConfiguration());
    bootAndEnable(supervisor, 100, 100);
    CHECK(supervisor.tick(99) == Result::CLOCK_REGRESSION);
    CHECK(supervisor.state() == State::FAULT);
    CHECK(hasFault(supervisor, Fault::CLOCK_REGRESSION));
    CHECK(supervisor.shutdownIntent());
    CHECK(!supervisor.outputsPermitted());
    CHECK(!supervisor.lease().active);
}

void testTimeOverflowFaultsClosed() {
    SafetySupervisor supervisor(validConfiguration());
    const uint64_t near_max = UINT64_MAX - 5;
    bootToDisabled(supervisor, near_max);
    CHECK(supervisor.acquireLease(
              near_max, MessageStamp(kOwnerOne, kSession, 1), 10) ==
          Result::TIME_OVERFLOW);
    CHECK(supervisor.state() == State::FAULT);
    CHECK(hasFault(supervisor, Fault::TIME_OVERFLOW));
    CHECK(supervisor.shutdownIntent());
    CHECK(!supervisor.outputsPermitted());
}

void testRenewalAndCommandAtExactDeadlineCannotRescueLease() {
    SafetySupervisor renew(validConfiguration());
    bootToDisabled(renew);
    CHECK(renew.acquireLease(
              0, MessageStamp(kOwnerOne, kSession, 1), 10) == Result::OK);
    CHECK(renew.renewLease(
              10, MessageStamp(kOwnerOne, kSession, 2), 10) ==
          Result::LEASE_EXPIRED);
    CHECK(renew.state() == State::SHUTDOWN);

    SafetySupervisor command(validConfiguration());
    bootAndEnable(command, 0, 10);
    CHECK(command.authorizeCommand(
              10, MessageStamp(kOwnerOne, kSession, 3)) ==
          Result::LEASE_EXPIRED);
    CHECK(command.state() == State::SHUTDOWN);
    CHECK(command.shutdownIntent());
}

}  // namespace

int main() {
    testBootIsDisabledAndGated();
    testInvalidConfigurationFaultsClosed();
    testInvalidTransitionsConsumeFreshSequences();
    testIdentityAndReplayDefenses();
    testLeaseDurationAndDeadlineBoundaries();
    testEnabledLeaseExpiryFaultsAndLatches();
    testSingleWriterContentionAndPerOwnerReplay();
    testExplicitShutdownRequiresMotorOffEvidence();
    testPrerequisiteLossFaultsActiveStates();
    testFaultLatchingAndGuardedReset();
    testClockRegressionFaultsClosed();
    testTimeOverflowFaultsClosed();
    testRenewalAndCommandAtExactDeadlineCannotRescueLease();

    if (failures != 0) {
        std::cerr << failures << " of " << checks << " checks failed\n";
        return 1;
    }
    std::cout << "SAFETY_SUPERVISOR_OK " << checks << " checks\n";
    return 0;
}
