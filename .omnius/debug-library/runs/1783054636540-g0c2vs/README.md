# Debug Run 1783054636540-g0c2vs

Updated: 2026-07-04T21:34:55.370Z
Workspace: /home/roko/Documents/Projects/myactuator

## Summary

- events: 600
- tool events: 125
- context dumps: 475
- failures: 59
- mutations: 21
- shell mutations: 0
- focus blocks: 113
- suspicious shell events: 0

## Diagnoses

- focus-supervisor-active: 242
- focus-supervisor-block: 113
- tool-failure: 59
- large-context-window: 53
- project-file-mutation: 21
- focus-supervisor-cached-evidence: 12

## Anchors

- debug_contract: .omnius/debug-library/CONTRACT.md (exists)
- run_readme: .omnius/debug-library/runs/1783054636540-g0c2vs/README.md (exists)
- run_index: .omnius/debug-library/runs/1783054636540-g0c2vs/index.json (exists)
- run_events_jsonl: .omnius/debug-library/runs/1783054636540-g0c2vs/events.jsonl (exists)
- workboard_active: .omnius/workboards/1783054636540-g0c2vs/active.json (exists)
- workboard_events: .omnius/workboards/1783054636540-g0c2vs/events.jsonl (exists)
- context_dump_latest: .omnius/context-window-dumps/latest.json (exists)
- context_dump_index: .omnius/context-window-dumps/index.jsonl (exists)
- trajectory_log: .omnius/trajectories/trajectories.jsonl (exists)
- checkpoints_dir: .omnius/checkpoints (exists)
- phases_dir: .omnius/phases (exists)
- completion_ledgers_dir: .omnius/completion-ledgers (exists)

## Latest Events

- 2026-07-04T21:34:55.369Z turn 0 context_window_dump: context dump agent_turn_transient_retry | tokens~16518
- 2026-07-04T21:34:02.473Z turn 47 context_window_dump: context dump brute_force_turn | tokens~121623 | required=read_authoritative_target | diagnoses=focus-supervisor-active,large-context-window
- 2026-07-04T21:33:43.693Z turn 0 context_window_dump: context dump agent_turn_transient_retry | tokens~16518
- 2026-07-04T21:32:33.582Z turn 0 context_window_dump: context dump agent_turn_transient_retry | tokens~16518
- 2026-07-04T21:31:50.935Z turn 46 context_window_dump: context dump brute_force_turn | tokens~121296 | required=read_authoritative_target | diagnoses=focus-supervisor-active,large-context-window
- 2026-07-04T21:31:23.452Z turn 0 context_window_dump: context dump agent_turn_transient_retry | tokens~16518
- 2026-07-04T21:30:13.339Z turn 0 context_window_dump: context dump agent_turn_transient_retry | tokens~16518
- 2026-07-04T21:29:39.301Z turn 45 context_window_dump: context dump brute_force_turn | tokens~120976 | required=read_authoritative_target | diagnoses=focus-supervisor-active,large-context-window
- 2026-07-04T21:29:03.228Z turn 0 context_window_dump: context dump agent_turn_transient_retry | tokens~16518
- 2026-07-04T21:27:53.191Z turn 0 context_window_dump: context dump agent_turn_transient_retry | tokens~16518
- 2026-07-04T21:27:28.650Z turn 44 context_window_dump: context dump brute_force_turn | tokens~120656 | required=read_authoritative_target | diagnoses=focus-supervisor-active,large-context-window
- 2026-07-04T21:26:43.069Z turn 0 context_window_dump: context dump agent_turn_transient_retry | tokens~16518
- 2026-07-04T21:25:33.033Z turn 0 context_window_dump: context dump agent_turn_transient_retry | tokens~16518
- 2026-07-04T21:25:20.917Z turn 43 context_window_dump: context dump brute_force_turn | tokens~120337 | required=read_authoritative_target | diagnoses=focus-supervisor-active,large-context-window
- 2026-07-04T21:24:23.003Z turn 0 context_window_dump: context dump agent_turn_transient_retry | tokens~16518
- 2026-07-04T21:23:12.960Z turn 0 context_window_dump: context dump agent_turn_transient_retry | tokens~16518
- 2026-07-04T21:23:06.970Z turn 58 tool_result failure: file_edit failure | diagnoses=focus-supervisor-active,tool-failure
- 2026-07-04T21:23:06.800Z turn 42 context_window_dump: context dump brute_force_turn | tokens~120019 | diagnoses=large-context-window
- 2026-07-04T21:22:29.822Z turn 58 tool_result success: file_patch success | diagnoses=project-file-mutation
- 2026-07-04T21:22:29.364Z turn 41 context_window_dump: context dump brute_force_turn | tokens~119390 | required=use_cached_evidence | diagnoses=focus-supervisor-active,large-context-window
- 2026-07-04T21:22:02.819Z turn 0 context_window_dump: context dump agent_turn_transient_retry | tokens~16518
- 2026-07-04T21:21:52.001Z turn 58 tool_result failure: file_patch failure | diagnoses=focus-supervisor-active,tool-failure
- 2026-07-04T21:21:51.704Z turn 40 context_window_dump: context dump brute_force_turn | tokens~118982 | required=use_cached_evidence | diagnoses=focus-supervisor-active,large-context-window
- 2026-07-04T21:21:12.420Z turn 58 tool_result success: file_read success | diagnoses=focus-supervisor-active
- 2026-07-04T21:21:12.235Z turn 39 context_window_dump: context dump brute_force_turn | tokens~118584 | required=use_cached_evidence | diagnoses=focus-supervisor-active,large-context-window
- 2026-07-04T21:20:52.771Z turn 0 context_window_dump: context dump agent_turn_transient_retry | tokens~16518
- 2026-07-04T21:20:34.881Z turn 58 tool_result failure: shell failure | diagnoses=focus-supervisor-active,tool-failure | command=cd firmware/esp32 && pio run 2>&1 | head -100
- 2026-07-04T21:20:34.424Z turn 38 context_window_dump: context dump brute_force_turn | tokens~118433 | diagnoses=large-context-window
- 2026-07-04T21:19:54.333Z turn 37 context_window_dump: context dump brute_force_turn | tokens~118105 | diagnoses=large-context-window
- 2026-07-04T21:19:54.005Z turn 58 tool_result success: file_edit success | diagnoses=project-file-mutation
- 2026-07-04T21:19:42.600Z turn 0 context_window_dump: context dump agent_turn_transient_retry | tokens~16518
- 2026-07-04T21:18:52.474Z turn 0 context_window_dump: context dump agent_turn_transient_retry | tokens~16518
- 2026-07-04T21:18:22.367Z turn 0 context_window_dump: context dump agent_turn_transient_retry | tokens~16518
- 2026-07-04T21:18:02.284Z turn 0 context_window_dump: context dump agent_turn_transient_retry | tokens~16518
- 2026-07-04T21:17:47.241Z turn 0 context_window_dump: context dump brute_force_turn | tokens~16518
- 2026-07-04T21:17:37.878Z turn 0 context_window_dump: context dump agent_turn | tokens~16328
- 2026-07-04T21:17:37.662Z turn 36 context_window_dump: context dump brute_force_turn | tokens~117693 | required=read_authoritative_target | diagnoses=focus-supervisor-active,large-context-window
- 2026-07-04T21:15:40.415Z turn 0 context_window_dump: context dump agent_turn_transient_retry | tokens~16509
- 2026-07-04T21:15:36.694Z turn 58 tool_result failure: file_edit failure | diagnoses=focus-supervisor-active,tool-failure
- 2026-07-04T21:15:36.534Z turn 35 context_window_dump: context dump brute_force_turn | tokens~117370 | required=read_authoritative_target | diagnoses=focus-supervisor-active,large-context-window
