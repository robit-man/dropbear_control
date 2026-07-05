# Debug Run 1783098484662-k0bt4g

Updated: 2026-07-03T17:35:16.736Z
Workspace: /home/roko/Documents/Projects/myactuator

## Summary

- events: 106
- tool events: 33
- context dumps: 73
- failures: 16
- mutations: 2
- shell mutations: 0
- focus blocks: 9
- suspicious shell events: 0

## Diagnoses

- focus-supervisor-active: 56
- tool-failure: 16
- focus-supervisor-block: 9
- project-file-mutation: 2

## Anchors

- debug_contract: .omnius/debug-library/CONTRACT.md (exists)
- run_readme: .omnius/debug-library/runs/1783098484662-k0bt4g/README.md (exists)
- run_index: .omnius/debug-library/runs/1783098484662-k0bt4g/index.json (exists)
- run_events_jsonl: .omnius/debug-library/runs/1783098484662-k0bt4g/events.jsonl (exists)
- workboard_active: .omnius/workboards/1783098484662-k0bt4g/active.json (exists)
- workboard_events: .omnius/workboards/1783098484662-k0bt4g/events.jsonl (exists)
- context_dump_latest: .omnius/context-window-dumps/latest.json (exists)
- context_dump_index: .omnius/context-window-dumps/index.jsonl (exists)
- trajectory_log: .omnius/trajectories/trajectories.jsonl (exists)
- checkpoints_dir: .omnius/checkpoints (exists)
- phases_dir: .omnius/phases (exists)
- completion_ledgers_dir: .omnius/completion-ledgers (exists)

## Latest Events

- 2026-07-03T17:35:16.736Z turn 0 context_window_dump: context dump agent_turn | tokens~15094
- 2026-07-03T17:35:16.043Z turn 41 context_window_dump: context dump agent_turn | tokens~70399 | required=use_cached_evidence | diagnoses=focus-supervisor-active
- 2026-07-03T17:35:16.027Z turn 39 tool_result success: file_read success | diagnoses=focus-supervisor-active,focus-supervisor-block
- 2026-07-03T17:34:29.383Z turn 40 context_window_dump: context dump agent_turn | tokens~70262 | required=read_authoritative_target | diagnoses=focus-supervisor-active
- 2026-07-03T17:34:29.364Z turn 38 tool_result failure: shell failure | diagnoses=focus-supervisor-active,focus-supervisor-block,tool-failure | command=cd /home/roko/Documents/Projects/myactuator/firmware/esp32 && pio run 2>&1 | tail -50
- 2026-07-03T17:34:22.166Z turn 0 context_window_dump: context dump agent_turn | tokens~15103
- 2026-07-03T17:34:21.803Z turn 39 context_window_dump: context dump agent_turn | tokens~77597 | required=read_authoritative_target | diagnoses=focus-supervisor-active,focus-supervisor-block
- 2026-07-03T17:33:21.519Z turn 0 context_window_dump: context dump agent_turn | tokens~15094
- 2026-07-03T17:33:21.418Z turn 38 context_window_dump: context dump agent_turn | tokens~77100 | required=read_authoritative_target | diagnoses=focus-supervisor-active
- 2026-07-03T17:33:21.404Z turn 36 tool_result failure: file_edit failure | diagnoses=focus-supervisor-active,tool-failure
- 2026-07-03T17:32:23.042Z turn 0 context_window_dump: context dump agent_turn | tokens~15094
- 2026-07-03T17:32:22.825Z turn 37 context_window_dump: context dump agent_turn | tokens~75711 | required=use_cached_evidence | diagnoses=focus-supervisor-active
- 2026-07-03T17:32:22.809Z turn 35 tool_result success: file_read success | diagnoses=focus-supervisor-active
- 2026-07-03T17:31:32.231Z turn 0 context_window_dump: context dump agent_turn | tokens~15103
- 2026-07-03T17:31:32.029Z turn 36 context_window_dump: context dump agent_turn | tokens~75671 | required=read_authoritative_target | diagnoses=focus-supervisor-active
- 2026-07-03T17:31:32.014Z turn 34 tool_result failure: file_edit failure | diagnoses=focus-supervisor-active,tool-failure
- 2026-07-03T17:30:31.357Z turn 35 context_window_dump: context dump agent_turn | tokens~74509
- 2026-07-03T17:29:40.534Z turn 34 context_window_dump: context dump agent_turn | tokens~74097 | required=use_cached_evidence | diagnoses=focus-supervisor-active
- 2026-07-03T17:29:40.523Z turn 32 tool_result success: file_edit success | diagnoses=focus-supervisor-active
- 2026-07-03T17:28:40.614Z turn 33 context_window_dump: context dump agent_turn | tokens~72651 | required=use_cached_evidence | diagnoses=focus-supervisor-active
- 2026-07-03T17:28:40.603Z turn 31 tool_result success: file_read success | diagnoses=focus-supervisor-active
- 2026-07-03T17:27:45.393Z turn 32 context_window_dump: context dump agent_turn | tokens~71856 | required=use_cached_evidence | diagnoses=focus-supervisor-active
- 2026-07-03T17:27:45.378Z turn 30 tool_result success: file_read success | diagnoses=focus-supervisor-active
- 2026-07-03T17:26:53.843Z turn 0 context_window_dump: context dump agent_turn | tokens~15094
- 2026-07-03T17:26:53.665Z turn 31 context_window_dump: context dump agent_turn | tokens~71709 | required=use_cached_evidence | diagnoses=focus-supervisor-active
- 2026-07-03T17:26:53.651Z turn 29 tool_result success: file_read success | diagnoses=focus-supervisor-active
- 2026-07-03T17:25:58.536Z turn 0 context_window_dump: context dump agent_turn | tokens~15094
- 2026-07-03T17:25:58.336Z turn 30 context_window_dump: context dump agent_turn | tokens~71296 | required=use_cached_evidence | diagnoses=focus-supervisor-active
- 2026-07-03T17:25:58.320Z turn 28 tool_result success: file_read success | diagnoses=focus-supervisor-active
- 2026-07-03T17:25:15.054Z turn 0 context_window_dump: context dump agent_turn | tokens~15094
- 2026-07-03T17:25:14.847Z turn 29 context_window_dump: context dump agent_turn | tokens~70699 | required=use_cached_evidence | diagnoses=focus-supervisor-active
- 2026-07-03T17:25:14.834Z turn 27 tool_result success: file_read success | diagnoses=focus-supervisor-active
- 2026-07-03T17:24:28.893Z turn 0 context_window_dump: context dump agent_turn | tokens~15103
- 2026-07-03T17:24:28.665Z turn 28 context_window_dump: context dump agent_turn | tokens~70506 | required=use_cached_evidence | diagnoses=focus-supervisor-active
- 2026-07-03T17:24:28.651Z turn 26 tool_result failure: shell failure | diagnoses=focus-supervisor-active,tool-failure | command=cd /home/roko/Documents/Projects/myactuator/firmware/esp32 && pio run 2>&1 | head -200
- 2026-07-03T17:23:41.002Z turn 0 context_window_dump: context dump agent_turn | tokens~15094
- 2026-07-03T17:23:40.805Z turn 27 context_window_dump: context dump agent_turn | tokens~64730
- 2026-07-03T17:23:40.793Z turn 25 tool_result success: file_edit success | diagnoses=project-file-mutation
- 2026-07-03T17:23:15.642Z turn 0 context_window_dump: context dump agent_turn | tokens~15103
- 2026-07-03T17:23:15.429Z turn 26 context_window_dump: context dump agent_turn | tokens~64480 | required=use_cached_evidence | diagnoses=focus-supervisor-active
