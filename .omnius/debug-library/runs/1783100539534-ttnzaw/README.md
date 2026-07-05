# Debug Run 1783100539534-ttnzaw

Updated: 2026-07-03T18:10:11.274Z
Workspace: /home/roko/Documents/Projects/myactuator

## Summary

- events: 86
- tool events: 23
- context dumps: 63
- failures: 6
- mutations: 6
- shell mutations: 0
- focus blocks: 7
- suspicious shell events: 0

## Diagnoses

- focus-supervisor-active: 19
- focus-supervisor-block: 7
- project-file-mutation: 6
- tool-failure: 6

## Anchors

- debug_contract: .omnius/debug-library/CONTRACT.md (exists)
- run_readme: .omnius/debug-library/runs/1783100539534-ttnzaw/README.md (exists)
- run_index: .omnius/debug-library/runs/1783100539534-ttnzaw/index.json (exists)
- run_events_jsonl: .omnius/debug-library/runs/1783100539534-ttnzaw/events.jsonl (exists)
- workboard_active: .omnius/workboards/1783100539534-ttnzaw/active.json (exists)
- workboard_events: .omnius/workboards/1783100539534-ttnzaw/events.jsonl (exists)
- context_dump_latest: .omnius/context-window-dumps/latest.json (exists)
- context_dump_index: .omnius/context-window-dumps/index.jsonl (exists)
- trajectory_log: .omnius/trajectories/trajectories.jsonl (exists)
- checkpoints_dir: .omnius/checkpoints (exists)
- phases_dir: .omnius/phases (exists)
- completion_ledgers_dir: .omnius/completion-ledgers (exists)

## Latest Events

- 2026-07-03T18:10:11.273Z turn 36 context_window_dump: context dump agent_turn | tokens~63266
- 2026-07-03T18:09:28.054Z turn 0 context_window_dump: context dump agent_turn | tokens~15094
- 2026-07-03T18:09:27.773Z turn 35 context_window_dump: context dump agent_turn | tokens~63118 | required=use_cached_evidence | diagnoses=focus-supervisor-active
- 2026-07-03T18:09:27.756Z turn 33 tool_result success: file_read success | diagnoses=focus-supervisor-active
- 2026-07-03T18:08:54.179Z turn 0 context_window_dump: context dump brute_force_turn | tokens~15330
- 2026-07-03T18:08:46.073Z turn 0 context_window_dump: context dump agent_turn | tokens~15103
- 2026-07-03T18:08:45.832Z turn 34 context_window_dump: context dump agent_turn | tokens~63075 | required=use_cached_evidence | diagnoses=focus-supervisor-active
- 2026-07-03T18:08:45.816Z turn 32 tool_result failure: shell failure | diagnoses=focus-supervisor-active,tool-failure | command=cd firmware/esp32 && pio run 2>&1
- 2026-07-03T18:07:35.110Z turn 33 context_window_dump: context dump agent_turn | tokens~60858
- 2026-07-03T18:07:35.080Z turn 31 tool_result success: file_edit success | diagnoses=project-file-mutation
- 2026-07-03T18:06:44.291Z turn 32 context_window_dump: context dump agent_turn | tokens~61512
- 2026-07-03T18:06:02.866Z turn 31 context_window_dump: context dump agent_turn | tokens~63920
- 2026-07-03T18:06:02.813Z turn 29 tool_result success: file_edit success | diagnoses=project-file-mutation
- 2026-07-03T18:05:08.564Z turn 30 context_window_dump: context dump agent_turn | tokens~66424
- 2026-07-03T18:05:08.547Z turn 28 tool_result success: file_edit success | diagnoses=project-file-mutation
- 2026-07-03T18:04:22.291Z turn 29 context_window_dump: context dump agent_turn | tokens~65961
- 2026-07-03T18:03:38.080Z turn 28 context_window_dump: context dump agent_turn | tokens~65530
- 2026-07-03T18:03:37.825Z turn 26 tool_result success: file_read success | diagnoses=focus-supervisor-block
- 2026-07-03T18:02:50.474Z turn 27 context_window_dump: context dump agent_turn | tokens~67286
- 2026-07-03T18:02:07.315Z turn 26 context_window_dump: context dump agent_turn | tokens~67091
- 2026-07-03T18:02:07.299Z turn 24 tool_result success: file_edit success | diagnoses=project-file-mutation
- 2026-07-03T18:01:22.295Z turn 25 context_window_dump: context dump agent_turn | tokens~66738
- 2026-07-03T18:00:45.313Z turn 0 context_window_dump: context dump brute_force_turn | tokens~15330
- 2026-07-03T18:00:37.094Z turn 0 context_window_dump: context dump agent_turn | tokens~15094
- 2026-07-03T18:00:36.997Z turn 24 context_window_dump: context dump agent_turn | tokens~66224
- 2026-07-03T17:59:02.978Z turn 0 context_window_dump: context dump agent_turn | tokens~15094
- 2026-07-03T17:59:02.871Z turn 23 context_window_dump: context dump agent_turn | tokens~68141
- 2026-07-03T17:58:17.959Z turn 0 context_window_dump: context dump brute_force_turn | tokens~15330
- 2026-07-03T17:58:14.903Z turn 22 context_window_dump: context dump agent_turn | tokens~67477 | required=use_cached_evidence | diagnoses=focus-supervisor-active
- 2026-07-03T17:58:14.877Z turn 20 tool_result success: grep_search success | diagnoses=focus-supervisor-active
- 2026-07-03T17:58:14.819Z turn 20 tool_result success: grep_search success | diagnoses=focus-supervisor-active
- 2026-07-03T17:58:13.950Z turn 20 tool_result success: grep_search success | diagnoses=focus-supervisor-active
- 2026-07-03T17:58:13.702Z turn 0 context_window_dump: context dump agent_turn | tokens~15103
- 2026-07-03T17:58:13.085Z turn 20 tool_result success: grep_search success | diagnoses=focus-supervisor-active
- 2026-07-03T17:57:28.974Z turn 0 context_window_dump: context dump agent_turn | tokens~15104
- 2026-07-03T17:57:28.734Z turn 21 context_window_dump: context dump agent_turn | tokens~65971 | required=use_cached_evidence | diagnoses=focus-supervisor-active
- 2026-07-03T17:57:28.716Z turn 19 tool_result failure: shell failure | diagnoses=focus-supervisor-active,tool-failure | command=cd firmware/esp32 && pio run 2>&1 | tail -50
- 2026-07-03T17:56:13.525Z turn 0 context_window_dump: context dump brute_force_turn | tokens~15330
- 2026-07-03T17:56:05.371Z turn 0 context_window_dump: context dump agent_turn | tokens~15103
- 2026-07-03T17:56:05.107Z turn 20 context_window_dump: context dump agent_turn | tokens~63646 | required=use_cached_evidence | diagnoses=focus-supervisor-active
