#include <stdio.h>
#include <string.h>

#include "artifact_trust_core.h"

namespace trust = myactuator::artifact_trust;

namespace {

int failures = 0;
#define CHECK(value)                                                        \
    do {                                                                    \
        if (!(value)) {                                                     \
            fprintf(stderr, "CHECK failed at %s:%d: %s\n", __FILE__,      \
                    __LINE__, #value);                                      \
            ++failures;                                                     \
        }                                                                   \
    } while (0)

trust::TrustDigest Digest(uint8_t value) {
    trust::TrustDigest output = {};
    for (size_t index = 0U; index < trust::kTrustDigestSize; ++index)
        output.bytes[index] = value;
    return output;
}

trust::ArtifactPolicy Policy() {
    trust::ArtifactPolicy value = {};
    value.platform_profile_selected = true;
    value.trust_anchor_present = true;
    value.verifier_bound = true;
    value.persistent_store_bound = true;
    value.durable_audit_bound = true;
    value.expected_kind = trust::ArtifactKind::CONFIGURATION;
    value.expected_purpose = trust::KeyPurpose::CONFIG_RELEASE;
    value.expected_algorithm = trust::VerificationAlgorithm::ED25519;
    value.expected_key_id_digest = Digest(5U);
    value.expected_target_digest = Digest(3U);
    value.expected_envelope_schema_digest = Digest(4U);
    value.minimum_security_epoch = 3U;
    return value;
}

trust::ArtifactCandidate Candidate() {
    trust::ArtifactCandidate value = {};
    value.transaction_digest = Digest(1U);
    value.artifact_digest = Digest(2U);
    value.target_digest = Digest(3U);
    value.envelope_schema_digest = Digest(4U);
    value.key_id_digest = Digest(5U);
    value.kind = trust::ArtifactKind::CONFIGURATION;
    value.purpose = trust::KeyPurpose::CONFIG_RELEASE;
    value.algorithm = trust::VerificationAlgorithm::ED25519;
    value.deployment_sequence = 11U;
    value.security_epoch = 3U;
    return value;
}

trust::VerificationAssertion Assertion() {
    trust::VerificationAssertion value = {};
    value.assertion_digest = Digest(6U);
    value.adapter_id_digest = Digest(7U);
    value.artifact_digest = Digest(2U);
    value.target_digest = Digest(3U);
    value.envelope_schema_digest = Digest(4U);
    value.key_id_digest = Digest(5U);
    value.kind = trust::ArtifactKind::CONFIGURATION;
    value.purpose = trust::KeyPurpose::CONFIG_RELEASE;
    value.algorithm = trust::VerificationAlgorithm::ED25519;
    value.signature_valid = true;
    value.chain_valid = true;
    value.key_revoked = false;
    return value;
}

trust::PersistentState Active() {
    trust::PersistentState value = {};
    value.available = true;
    value.integrity_verified = true;
    value.active_artifact_digest = Digest(9U);
    value.committed_transaction_digest = Digest(10U);
    value.target_digest = Digest(3U);
    value.envelope_schema_digest = Digest(4U);
    value.key_id_digest = Digest(5U);
    value.kind = trust::ArtifactKind::CONFIGURATION;
    value.purpose = trust::KeyPurpose::CONFIG_RELEASE;
    value.algorithm = trust::VerificationAlgorithm::ED25519;
    value.generation = 5U;
    value.deployment_sequence = 10U;
    value.security_epoch = 3U;
    return value;
}

trust::DurableCommitReceipt Durable() {
    trust::DurableCommitReceipt value = {};
    value.transaction_digest = Digest(1U);
    value.artifact_digest = Digest(2U);
    value.previous_generation = 5U;
    value.next_generation = 6U;
    value.deployment_sequence = 11U;
    value.security_epoch = 3U;
    value.write_completed = true;
    value.readback_verified = true;
    return value;
}

trust::AuditCommitReceipt Audit() {
    trust::AuditCommitReceipt value = {};
    value.transaction_digest = Digest(1U);
    value.artifact_digest = Digest(2U);
    value.committed_generation = 6U;
    value.audit_event_digest = Digest(11U);
    value.durable = true;
    return value;
}

trust::RebootSnapshot Snapshot() {
    trust::RebootSnapshot value = {};
    value.state = Active();
    value.durable_commit_verified = true;
    value.audit_commit_verified = true;
    return value;
}

enum class Operation {
    STAGE,
    COMMIT,
    COMMIT_MISMATCH,
    ABORT,
    ABORT_MISMATCH,
    RESTORE,
};

trust::ArtifactDecision RunVariant(const char* variant) {
    trust::ArtifactPolicy policy = Policy();
    trust::ArtifactCandidate candidate = Candidate();
    trust::VerificationAssertion assertion = Assertion();
    const trust::VerificationAssertion* assertion_pointer = &assertion;
    trust::PersistentState active = Active();
    trust::DurableCommitReceipt durable = Durable();
    trust::AuditCommitReceipt audit = Audit();
    trust::RebootSnapshot snapshot = Snapshot();
    Operation operation = Operation::STAGE;
    bool pre_stage = false;

    if (strcmp(variant, "pass_stage") == 0) {
    } else if (strcmp(variant, "profile_not_selected") == 0) {
        policy.platform_profile_selected = false;
    } else if (strcmp(variant, "anchor_missing") == 0) {
        policy.trust_anchor_present = false;
    } else if (strcmp(variant, "verifier_missing") == 0) {
        policy.verifier_bound = false;
    } else if (strcmp(variant, "assertion_missing") == 0) {
        assertion_pointer = NULL;
    } else if (strcmp(variant, "signature_invalid") == 0) {
        assertion.signature_valid = false;
    } else if (strcmp(variant, "chain_invalid") == 0) {
        assertion.chain_valid = false;
    } else if (strcmp(variant, "key_revoked") == 0) {
        assertion.key_revoked = true;
    } else if (strcmp(variant, "algorithm_mismatch") == 0) {
        assertion.algorithm =
            trust::VerificationAlgorithm::ECDSA_P256_SHA256;
    } else if (strcmp(variant, "key_id_mismatch") == 0) {
        assertion.key_id_digest = Digest(12U);
    } else if (strcmp(variant, "purpose_mismatch") == 0) {
        assertion.purpose = trust::KeyPurpose::CALIBRATION_RELEASE;
    } else if (strcmp(variant, "kind_mismatch") == 0) {
        assertion.kind = trust::ArtifactKind::CALIBRATION;
    } else if (strcmp(variant, "target_mismatch") == 0) {
        assertion.target_digest = Digest(12U);
    } else if (strcmp(variant, "digest_mismatch") == 0) {
        assertion.artifact_digest = Digest(12U);
    } else if (strcmp(variant, "envelope_mismatch") == 0) {
        assertion.envelope_schema_digest = Digest(12U);
    } else if (strcmp(variant, "persistent_unavailable") == 0) {
        active.available = false;
    } else if (strcmp(variant, "persistent_untrusted") == 0) {
        active.integrity_verified = false;
    } else if (strcmp(variant, "security_epoch_rollback") == 0) {
        candidate.security_epoch = 2U;
    } else if (strcmp(variant, "deployment_sequence_rollback") == 0) {
        candidate.deployment_sequence = 9U;
    } else if (strcmp(variant, "duplicate_version_conflict") == 0) {
        candidate.deployment_sequence = 10U;
    } else if (strcmp(variant, "invalid_request") == 0) {
        candidate.transaction_digest = Digest(0U);
    } else if (strcmp(variant, "stage_occupied") == 0) {
        pre_stage = true;
        candidate.transaction_digest = Digest(12U);
        candidate.deployment_sequence = 12U;
    } else if (strcmp(variant, "pass_commit") == 0) {
        operation = Operation::COMMIT;
        pre_stage = true;
    } else if (strcmp(variant, "commit_without_stage") == 0) {
        operation = Operation::COMMIT;
    } else if (strcmp(variant, "commit_transaction_mismatch") == 0) {
        operation = Operation::COMMIT_MISMATCH;
        pre_stage = true;
    } else if (strcmp(variant, "durable_write_incomplete") == 0) {
        operation = Operation::COMMIT;
        pre_stage = true;
        durable.write_completed = false;
    } else if (strcmp(variant, "durable_readback_missing") == 0) {
        operation = Operation::COMMIT;
        pre_stage = true;
        durable.readback_verified = false;
    } else if (strcmp(variant, "durable_transaction_mismatch") == 0) {
        operation = Operation::COMMIT;
        pre_stage = true;
        durable.transaction_digest = Digest(12U);
    } else if (strcmp(variant, "durable_artifact_mismatch") == 0) {
        operation = Operation::COMMIT;
        pre_stage = true;
        durable.artifact_digest = Digest(12U);
    } else if (strcmp(variant, "durable_sequence_mismatch") == 0) {
        operation = Operation::COMMIT;
        pre_stage = true;
        durable.deployment_sequence = 12U;
    } else if (strcmp(variant, "durable_epoch_mismatch") == 0) {
        operation = Operation::COMMIT;
        pre_stage = true;
        durable.security_epoch = 4U;
    } else if (strcmp(variant, "previous_generation_mismatch") == 0) {
        operation = Operation::COMMIT;
        pre_stage = true;
        durable.previous_generation = 4U;
    } else if (strcmp(variant, "next_generation_mismatch") == 0) {
        operation = Operation::COMMIT;
        pre_stage = true;
        durable.next_generation = 7U;
    } else if (strcmp(variant, "audit_adapter_missing") == 0) {
        operation = Operation::COMMIT;
        pre_stage = true;
        policy.durable_audit_bound = false;
    } else if (strcmp(variant, "audit_not_durable") == 0) {
        operation = Operation::COMMIT;
        pre_stage = true;
        audit.durable = false;
    } else if (strcmp(variant, "audit_transaction_mismatch") == 0) {
        operation = Operation::COMMIT;
        pre_stage = true;
        audit.transaction_digest = Digest(12U);
    } else if (strcmp(variant, "audit_artifact_mismatch") == 0) {
        operation = Operation::COMMIT;
        pre_stage = true;
        audit.artifact_digest = Digest(12U);
    } else if (strcmp(variant, "audit_generation_mismatch") == 0) {
        operation = Operation::COMMIT;
        pre_stage = true;
        audit.committed_generation = 7U;
    } else if (strcmp(variant, "audit_digest_missing") == 0) {
        operation = Operation::COMMIT;
        pre_stage = true;
        audit.audit_event_digest = Digest(0U);
    } else if (strcmp(variant, "pass_abort") == 0) {
        operation = Operation::ABORT;
        pre_stage = true;
    } else if (strcmp(variant, "abort_without_stage") == 0) {
        operation = Operation::ABORT;
    } else if (strcmp(variant, "abort_transaction_mismatch") == 0) {
        operation = Operation::ABORT_MISMATCH;
        pre_stage = true;
    } else if (strcmp(variant, "pass_restore") == 0) {
        operation = Operation::RESTORE;
    } else if (strcmp(variant, "restore_integrity_missing") == 0) {
        operation = Operation::RESTORE;
        snapshot.state.integrity_verified = false;
    } else if (strcmp(variant, "restore_durable_missing") == 0) {
        operation = Operation::RESTORE;
        snapshot.durable_commit_verified = false;
    } else if (strcmp(variant, "restore_audit_missing") == 0) {
        operation = Operation::RESTORE;
        snapshot.audit_commit_verified = false;
    } else if (strcmp(variant, "restore_epoch_rollback") == 0) {
        operation = Operation::RESTORE;
        snapshot.state.security_epoch = 2U;
    } else if (strcmp(variant, "restore_digest_missing") == 0) {
        operation = Operation::RESTORE;
        snapshot.state.active_artifact_digest = Digest(0U);
    } else {
        CHECK(false);
    }

    trust::ArtifactTrustEngine engine(policy, active);
    if (pre_stage) {
        trust::VerificationAssertion pre_assertion = Assertion();
        const trust::ArtifactResult staged =
            engine.stage(Candidate(), &pre_assertion);
        CHECK(staged.code == trust::ArtifactDecision::PASS_STAGED);
    }
    trust::ArtifactResult result = {};
    switch (operation) {
        case Operation::STAGE:
            result = engine.stage(candidate, assertion_pointer);
            break;
        case Operation::COMMIT:
            result = engine.commit(Digest(1U), durable, audit);
            break;
        case Operation::COMMIT_MISMATCH:
            result = engine.commit(Digest(12U), durable, audit);
            break;
        case Operation::ABORT:
            result = engine.abort(Digest(1U));
            break;
        case Operation::ABORT_MISMATCH:
            result = engine.abort(Digest(12U));
            break;
        case Operation::RESTORE:
            result = engine.restore(snapshot);
            break;
    }
    CHECK(!result.motion_authorized);
    const bool pass =
        result.code == trust::ArtifactDecision::PASS_STAGED ||
        result.code == trust::ArtifactDecision::PASS_COMMITTED ||
        result.code == trust::ArtifactDecision::PASS_ABORTED ||
        result.code == trust::ArtifactDecision::PASS_RESTORED;
    CHECK(result.proceed_to_next_gate == pass);
    return result.code;
}

bool Extract(const char* line, const char* prefix, char* output,
             size_t output_size) {
    const char* start = strstr(line, prefix);
    if (start == NULL) return false;
    start += strlen(prefix);
    const char* end = strchr(start, '"');
    if (end == NULL) return false;
    const size_t length = static_cast<size_t>(end - start);
    if (length == 0U || length >= output_size) return false;
    memcpy(output, start, length);
    output[length] = '\0';
    return true;
}

void TestSharedCorpus() {
    FILE* file =
        fopen("tests/artifact_trust/golden_artifact_trust.jsonl", "rb");
    CHECK(file != NULL);
    if (file == NULL) return;
    char line[256] = {};
    char variant[96] = {};
    char expected[96] = {};
    size_t count = 0U;
    while (fgets(line, sizeof(line), file) != NULL) {
        CHECK(strchr(line, '\n') != NULL);
        CHECK(Extract(line, "\"variant\":\"", variant, sizeof(variant)));
        CHECK(Extract(line, "\"expected_code\":\"", expected,
                      sizeof(expected)));
        const trust::ArtifactDecision actual = RunVariant(variant);
        CHECK(strcmp(trust::ArtifactDecisionName(actual), expected) == 0);
        ++count;
    }
    CHECK(!ferror(file));
    fclose(file);
    CHECK(count == 48U);
}

void TestTransactionPreservation() {
    trust::ArtifactPolicy policy = Policy();
    trust::PersistentState state = Active();
    trust::ArtifactTrustEngine engine(policy, state);
    trust::ArtifactCandidate candidate = Candidate();
    trust::VerificationAssertion assertion = Assertion();
    CHECK(engine.stage(candidate, &assertion).code ==
          trust::ArtifactDecision::PASS_STAGED);
    CHECK(engine.activeState().generation == 5U);
    trust::DurableCommitReceipt durable = Durable();
    durable.readback_verified = false;
    trust::AuditCommitReceipt audit = Audit();
    CHECK(engine.commit(Digest(1U), durable, audit).code ==
          trust::ArtifactDecision::DURABLE_RECEIPT_INVALID);
    CHECK(engine.stagePresent());
    CHECK(engine.activeState().generation == 5U);
    durable.readback_verified = true;
    const trust::ArtifactResult committed =
        engine.commit(Digest(1U), durable, audit);
    CHECK(committed.code == trust::ArtifactDecision::PASS_COMMITTED);
    CHECK(committed.active_changed);
    CHECK(!engine.stagePresent());
    CHECK(engine.activeState().generation == 6U);
    CHECK(trust::TrustDigestEqual(engine.activeState().active_artifact_digest,
                                  Digest(2U)));
}

void TestRestoreFailsDisabled() {
    trust::ArtifactPolicy policy = Policy();
    trust::ArtifactTrustEngine engine(
        policy, trust::EmptyPersistentState(true, true));
    trust::RebootSnapshot snapshot = Snapshot();
    snapshot.state.integrity_verified = false;
    CHECK(engine.restore(snapshot).code ==
          trust::ArtifactDecision::REBOOT_SNAPSHOT_INVALID);
    CHECK(engine.activeState().generation == 0U);
    CHECK(!engine.activeState().integrity_verified);
    snapshot = Snapshot();
    CHECK(engine.restore(snapshot).code ==
          trust::ArtifactDecision::PASS_RESTORED);
    CHECK(engine.activeState().generation == 5U);
    snapshot = Snapshot();
    snapshot.state.target_digest = Digest(12U);
    CHECK(engine.restore(snapshot).code ==
          trust::ArtifactDecision::REBOOT_SNAPSHOT_INVALID);
}

}  // namespace

int main() {
    TestSharedCorpus();
    TestTransactionPreservation();
    TestRestoreFailsDisabled();
    CHECK(sizeof(trust::ArtifactTrustEngine) <= 640U);
    CHECK(sizeof(trust::ArtifactResult) <= 32U);
    if (failures != 0) {
        fprintf(stderr, "artifact trust failures=%d\n", failures);
        return 1;
    }
    printf("ARTIFACT_TRUST_CPP_OK corpus=48 engine_bytes=%zu motion=false\n",
           sizeof(trust::ArtifactTrustEngine));
    return 0;
}
