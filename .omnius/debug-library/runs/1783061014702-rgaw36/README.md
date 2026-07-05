# Debug Run 1783061014702-rgaw36

Updated: 2026-07-04T18:11:34.036Z
Workspace: /home/roko/Documents/Projects/myactuator

## Summary

- events: 707
- tool events: 195
- context dumps: 512
- failures: 76
- mutations: 33
- shell mutations: 0
- focus blocks: 35
- suspicious shell events: 0

## Diagnoses

- focus-supervisor-active: 207
- tool-failure: 76
- focus-supervisor-block: 35
- project-file-mutation: 33
- focus-supervisor-cached-evidence: 20

## Anchors

- debug_contract: .omnius/debug-library/CONTRACT.md (exists)
- run_readme: .omnius/debug-library/runs/1783061014702-rgaw36/README.md (exists)
- run_index: .omnius/debug-library/runs/1783061014702-rgaw36/index.json (exists)
- run_events_jsonl: .omnius/debug-library/runs/1783061014702-rgaw36/events.jsonl (exists)
- workboard_active: .omnius/workboards/1783061014702-rgaw36/active.json (exists)
- workboard_events: .omnius/workboards/1783061014702-rgaw36/events.jsonl (exists)
- context_dump_latest: .omnius/context-window-dumps/latest.json (exists)
- context_dump_index: .omnius/context-window-dumps/index.jsonl (exists)
- trajectory_log: .omnius/trajectories/trajectories.jsonl (exists)
- checkpoints_dir: .omnius/checkpoints (exists)
- phases_dir: .omnius/phases (exists)
- completion_ledgers_dir: .omnius/completion-ledgers (exists)

## Latest Events

- 2026-07-04T18:11:34.035Z turn 45 context_window_dump: context dump agent_turn | tokens~62630
- 2026-07-04T18:11:34.022Z turn 43 tool_result success: file_read success | diagnoses=focus-supervisor-cached-evidence
- 2026-07-04T18:11:09.296Z turn 0 context_window_dump: context dump agent_turn_transient_retry | tokens~16518
- 2026-07-04T18:10:53.668Z turn 44 context_window_dump: context dump agent_turn | tokens~62191 | required=use_cached_evidence | diagnoses=focus-supervisor-active
- 2026-07-04T18:10:53.627Z turn 42 tool_result failure: file_read failure | diagnoses=focus-supervisor-active,tool-failure
- 2026-07-04T18:10:35.686Z turn 43 context_window_dump: context dump agent_turn | tokens~61535 | required=use_cached_evidence | diagnoses=focus-supervisor-active
- 2026-07-04T18:10:35.564Z turn 41 tool_result failure: shell failure | diagnoses=focus-supervisor-active,tool-failure | command=cd firmware/esp32 && pio run 2>&1
- 2026-07-04T18:09:59.254Z turn 0 context_window_dump: context dump agent_turn_transient_retry | tokens~16518
- 2026-07-04T18:09:38.329Z turn 42 context_window_dump: context dump agent_turn | tokens~61185 | required=use_cached_evidence | diagnoses=focus-supervisor-active
- 2026-07-04T18:09:38.313Z turn 40 tool_result failure: shell failure | diagnoses=focus-supervisor-active,focus-supervisor-block,tool-failure | command=cd firmware/esp32 && pio run 2>&1 | tail -100
- 2026-07-04T18:08:49.199Z turn 0 context_window_dump: context dump agent_turn_transient_retry | tokens~16518
- 2026-07-04T18:08:38.386Z turn 41 context_window_dump: context dump agent_turn | tokens~60595
- 2026-07-04T18:08:38.373Z turn 39 tool_result success: file_read success | diagnoses=focus-supervisor-cached-evidence
- 2026-07-04T18:07:39.175Z turn 0 context_window_dump: context dump agent_turn_transient_retry | tokens~16518
- 2026-07-04T18:07:37.172Z turn 40 context_window_dump: context dump agent_turn | tokens~60294
- 2026-07-04T18:06:27.811Z turn 0 context_window_dump: context dump agent_turn_transient_retry | tokens~16518
- 2026-07-04T18:06:24.752Z turn 39 context_window_dump: context dump agent_turn | tokens~59189
- 2026-07-04T18:06:24.738Z turn 37 tool_result success: file_read success | diagnoses=focus-supervisor-cached-evidence
- 2026-07-04T18:05:25.281Z turn 38 context_window_dump: context dump agent_turn | tokens~59076
- 2026-07-04T18:05:25.268Z turn 36 tool_result success: file_read success | diagnoses=focus-supervisor-cached-evidence
- 2026-07-04T18:05:17.722Z turn 0 context_window_dump: context dump agent_turn_transient_retry | tokens~16518
- 2026-07-04T18:04:09.452Z turn 37 context_window_dump: context dump agent_turn | tokens~59720
- 2026-07-04T18:04:09.438Z turn 35 tool_result success: file_read success | diagnoses=focus-supervisor-cached-evidence
- 2026-07-04T18:04:07.631Z turn 0 context_window_dump: context dump agent_turn_transient_retry | tokens~16518
- 2026-07-04T18:03:09.344Z turn 36 context_window_dump: context dump agent_turn | tokens~59624
- 2026-07-04T18:03:09.329Z turn 34 tool_result success: file_read success | diagnoses=focus-supervisor-cached-evidence
- 2026-07-04T18:02:57.544Z turn 0 context_window_dump: context dump agent_turn_transient_retry | tokens~16518
- 2026-07-04T18:02:11.275Z turn 35 context_window_dump: context dump agent_turn | tokens~59473
- 2026-07-04T18:02:11.261Z turn 33 tool_result success: file_read success | diagnoses=focus-supervisor-cached-evidence
- 2026-07-04T18:01:47.431Z turn 0 context_window_dump: context dump agent_turn_transient_retry | tokens~16518
- 2026-07-04T18:01:02.322Z turn 34 context_window_dump: context dump agent_turn | tokens~58524
- 2026-07-04T18:01:02.309Z turn 32 tool_result success: file_read success | diagnoses=focus-supervisor-cached-evidence
- 2026-07-04T18:00:37.333Z turn 0 context_window_dump: context dump agent_turn_transient_retry | tokens~16518
- 2026-07-04T18:00:03.643Z turn 33 context_window_dump: context dump agent_turn | tokens~58256
- 2026-07-04T18:00:03.468Z turn 31 tool_result success: file_read success | diagnoses=focus-supervisor-cached-evidence
- 2026-07-04T17:59:27.240Z turn 0 context_window_dump: context dump agent_turn_transient_retry | tokens~16518
- 2026-07-04T17:58:35.148Z turn 32 context_window_dump: context dump agent_turn | tokens~57571
- 2026-07-04T17:58:17.153Z turn 0 context_window_dump: context dump agent_turn_transient_retry | tokens~16518
- 2026-07-04T17:57:07.065Z turn 0 context_window_dump: context dump agent_turn_transient_retry | tokens~16518
- 2026-07-04T17:55:57.034Z turn 0 context_window_dump: context dump agent_turn_transient_retry | tokens~16518
