#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"

current_stage="startup"
gate_report="generated/verification/offline_gate_report.json"
report_initialized=false
report_result() {
  local rc=$?
  local report_rc=0
  if [[ "$report_initialized" == true ]]; then
    if [[ "$rc" -eq 0 ]]; then
      python3 tools/offline_gate_report.py --output "$gate_report" \
        finalize --result PASS --exit-code 0 || report_rc=$?
    else
      python3 tools/offline_gate_report.py --output "$gate_report" \
        finalize --result FAIL --exit-code "$rc" \
        --failure-stage "$current_stage" || report_rc=$?
    fi
    python3 tools/offline_gate_report.py --output "$gate_report" print || true
    if [[ "$rc" -eq 0 && "$report_rc" -ne 0 ]]; then
      exit "$report_rc"
    fi
  elif [[ "$rc" -ne 0 ]]; then
    printf '{"gate":"p0-p1-offline","result":"FAIL","stage":"%s","exit_code":%s,"machine_report":"unavailable"}\n' \
      "$current_stage" "$rc" >&2
  fi
}
trap report_result EXIT

if ! command -v python3 >/dev/null 2>&1; then
  printf 'missing required offline test tool: python3\n' >&2
  exit 2
fi
python3 tools/offline_gate_report.py --output "$gate_report" init
report_initialized=true

for command in python3 node npm g++ pio git pdftotext; do
  if ! command -v "$command" >/dev/null 2>&1; then
    printf 'missing required offline test tool: %s\n' "$command" >&2
    exit 2
  fi
done

run() {
  local label="$1"
  local command_text
  local rc
  shift
  current_stage="$label"
  command_text="$*"
  printf '\n== %s ==\n' "$label"
  python3 tools/offline_gate_report.py --output "$gate_report" \
    stage-start --stage "$label" --command "$command_text"
  if "$@"; then
    python3 tools/offline_gate_report.py --output "$gate_report" \
      stage-end --stage "$label" --result PASS --exit-code 0
  else
    rc=$?
    python3 tools/offline_gate_report.py --output "$gate_report" \
      stage-end --stage "$label" --result FAIL --exit-code "$rc"
    return "$rc"
  fi
}

printf '%s\n' \
  'MYACTUATOR P0-P1 OFFLINE GATE' \
  'This command compiles and exercises offline code only.' \
  'It does not command hardware or establish hardware/CAD simulation support.'

run "pinned offline schema test dependencies" \
  python3 tools/check_test_dependencies.py

run "atomic machine-readable offline gate evidence" \
  tests/offline_gate_report/run_tests.sh

run "tracked vendor evidence (44 models / 53 STEP / 9 document sets)" \
  python3 tools/build_asset_manifests.py

run "pinned six-page MYACTUATOR download-index snapshot" \
  python3 tools/manage_myactuator_download_index.py

run "positive-capable exact-tuple protocol applicability lifecycle" \
  tests/protocol_applicability/run_tests.sh

run "bounded lexical inspection of all 53 exact STEP sources" \
  tests/cad_inspection/run_tests.sh

run "fail-closed exact-configuration CAD review and 44-model support ledger" \
  tests/cad_review/run_tests.sh

run "source-bound assembly candidate-review packet manifest" \
  tests/cad_review_packet/run_tests.sh

run "stable flattened topology inventory and fail-closed partition dispositions" \
  tests/flattened_partition/run_tests.sh

run "real-source candidate split/export/articulation without semantic promotion" \
  tests/cad_candidate_export/run_tests.sh

run "independent CAD semantic-review decision authority" \
  tests/cad_review_decision/run_tests.sh

run "local independent CAD reviewer workbench" \
  tests/cad_review_workbench/run_tests.sh

run "all-53-configuration local CAD review campaign" \
  tests/cad_review_campaign/run_tests.sh

run "canonical local CAD runtime registry and browser redaction" \
  tests/runtime_asset_registry/run_tests.sh

run "exact host and Dropbear CAD artifact admission" \
  tests/host_cad_assets/run_tests.sh

run "page-bound 44-model product specification candidate extraction" \
  tests/plant_spec_candidates/run_tests.sh

run "independently reviewed plant-candidate lifecycle materialization" \
  tests/plant_candidate_decisions/run_tests.sh

run "reviewed-fact exact-tuple plant parameter-set assembly" \
  tests/plant_parameter_sets/run_tests.sh

run "reviewed exact sourced-plant runtime adapter" \
  tests/plant_runtime_adapter/run_tests.sh

run "reviewed exact sourced-plant runtime adapter V2" \
  tests/plant_runtime_adapter_v2/run_tests.sh

run "sourced plant schema and explicit simulation backend substitution" \
  tests/plant_registry/run_tests.sh

run "44-model exact plant source-fact and missing-evidence ledger" \
  tests/plant_evidence_ledger/run_tests.sh

run "exact evidence-aware simulator runtime catalog" \
  tests/simulator_runtime/run_tests.sh

run "deterministic synthetic electromechanical plant" \
  tests/plant_core/run_tests.sh

run "deterministic event-scheduled electromechanical plant V2" \
  tests/plant_core_v2/run_tests.sh

run "transactional twelve-axis synthetic plant V2 composition" \
  tests/multi_actuator_plant_v2/run_tests.sh

run "deterministic backend-neutral simulation session" \
  tests/simulation_session/run_tests.sh

run "canonical backend-neutral simulation trace interchange" \
  tests/trace_interchange/run_tests.sh

run "exact locked generic rigid-body benchmark and Dropbear denial" \
  tests/rigid_body_benchmark/run_tests.sh

run "exact CAD review evidence to Dropbear/browser consumer denial" \
  tests/web_cad_registry/run_tests.sh

run "pinned OpenCascade toolchain and synthetic articulation proof" \
  tests/cad_toolchain/run_tests.sh

run "real-source STEP import evidence and shell/solid classification" \
  tests/cad_import/run_tests.sh

run "legacy host regression" \
  bash -c 'cd host && PYTHONPATH=. python3 myactuator_lib/_verify.py'

run "official-source RMD CAN V4.4 codec conformance" \
  tests/protocol/run_tests.sh

run "exact-tuple support and evidence policy" \
  tests/support/run_tests.sh

run "deterministic safety and command-lease model" \
  tests/safety/run_tests.sh

run "atomic configuration identity and admission guard" \
  tests/config_admission/run_tests.sh

run "post-authentication least-privilege and bounded audit core" \
  tests/security_authorization/run_tests.sh

run "exact source-bound ESP32 security platform capability intake" \
  tests/security_platform_intake/run_tests.sh

run "verifier-neutral atomic artifact trust and reboot semantics" \
  tests/artifact_trust/run_tests.sh

run "deterministic V4.4 protocol-state SIL emulator" \
  tests/emulator/run_tests.sh

run "canonical Dropbear configuration schema and semantics" \
  tests/schema/run_tests.sh

run "exact-subject calibration evidence and admission" \
  tests/calibration_registry/run_tests.sh

run "multi-provenance exact effective-limit selection" \
  tests/limit_registry/run_tests.sh

run "deterministic cross-layer Dropbear configuration views" \
  tests/config_views/run_tests.sh

run "pinned fail-closed Dropbear layer reconciliation" \
  tests/dropbear_reconciliation/run_tests.sh

run "exact per-actuator Dropbear readiness denial projection" \
  tests/dropbear_readiness/run_tests.sh

run "pinned Dropbear source/derivative description inventory" \
  tests/dropbear_description_inventory/run_tests.sh

run "independent Dropbear source-authority decision and denial status" \
  tests/dropbear_source_authority/run_tests.sh

run "positive-capable Dropbear source-authority lifecycle registry V2" \
  tests/dropbear_source_registry_v2/run_tests.sh

run "reviewed Dropbear graph decision and semantic admission" \
  tests/dropbear_graph_review/run_tests.sh

run "structured Dropbear graph V2 migration and semantic admission" \
  tests/dropbear_graph_v2/run_tests.sh

run "positive-capable Dropbear graph lifecycle registry V2" \
  tests/dropbear_graph_registry_v2/run_tests.sh

run "denial-only Dropbear graph consumer projections" \
  tests/dropbear_graph_projection/run_tests.sh

run "lifecycle-aware Dropbear graph consumer projections V2" \
  tests/dropbear_graph_lifecycle_projection_v2/run_tests.sh

run "graph-gated typed Dropbear hardware API contract" \
  tests/dropbear_hardware_api/run_tests.sh

run "ROS-independent ros2_control semantic core" \
  tests/ros2_control_core/run_tests.sh

run "pinned ROS 2 C++ SystemInterface handoff and semantic parity" \
  tests/ros2_control_cpp/run_tests.sh

run "Iteration 11 unpowered discovery preparation package" \
  tests/dropbear_unpowered_discovery/run_tests.sh

run "bounded versioned host-link V1 reference" \
  tests/hostlink/run_tests.sh

run "allocation-free native host-link V1 parity" \
  tests/hostlink_native/run_tests.sh

run "bounded fake-transport gateway scheduler" \
  tests/gateway_core/run_tests.sh

run "bounded gateway-to-native-transport runtime" \
  tests/gateway_transport_runtime/run_tests.sh

run "controller-independent CAN adapter conformance" \
  tests/can_adapter_contract/run_tests.sh

run "exact no-I/O CAN adapter manifest intake and disabled factory" \
  tests/can_adapter_intake/run_tests.sh

run "unified 145-subject evidence review and assignment queue" \
  tests/evidence_review_queue/run_tests.sh

run "source-bound 97-packet CAD and plant human evidence handoff" \
  tests/evidence_intake/run_tests.sh

run "source-bound program coverage and objective-gap dashboard" \
  tests/coverage_dashboard/run_tests.sh

run "zero-exception API UI documentation claim-surface audit" \
  tests/claim_surface/run_tests.sh

run "append-only listen-only CAN capture evidence" \
  tests/can_capture/run_tests.sh

run "session-owned exact host-command ingress" \
  tests/host_command_ingress/run_tests.sh

run "correlated gateway evidence to typed host egress" \
  tests/host_gateway_egress/run_tests.sh

run "allocation-free calibrated joint observation and reconciliation" \
  tests/joint_observation_core/run_tests.sh

run "preserved ESP32 no-loss integration seam" \
  tests/esp32_integration_seam/run_tests.sh

run "deterministic host gateway-session lifecycle" \
  tests/gateway_session/run_tests.sh

run "generated-config, host-link and safety-guard composition" \
  tests/stack_contract/run_tests.sh

run "native V1, gateway and protocol-emulator steel thread" \
  tests/stack_v1_gateway/run_tests.sh

run "browser protocol and toy-simulator regressions" \
  npm --prefix web test

if [[ -f tools/validate_traceability.py ]]; then
  run "requirements and traceability integrity" \
    python3 tools/validate_traceability.py
fi

run "ESP32 compile-only regression" \
  env PLATFORMIO_SETTING_ENABLE_TELEMETRY=no pio run \
    --project-dir firmware/esp32 --environment esp32

run "tracked diff whitespace" git diff --check

printf '\n%s\n%s\n%s\n%s\n' \
  'OFFLINE_GATE_OK' \
  'Evidence level: specification + native tests + ESP32 compile only.' \
  'Hardware discovery, bench, HIL, physical stop, output-member review, and' \
  'model/firmware applicability remain required before support is claimed.'
