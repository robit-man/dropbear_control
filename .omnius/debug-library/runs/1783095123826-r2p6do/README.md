# Debug Run 1783095123826-r2p6do

Updated: 2026-07-03T16:52:18.447Z
Workspace: /home/roko/Documents/Projects/myactuator

## Summary

- events: 122
- tool events: 42
- context dumps: 80
- failures: 19
- mutations: 4
- shell mutations: 0
- focus blocks: 17
- suspicious shell events: 0

## Diagnoses

- focus-supervisor-active: 67
- tool-failure: 19
- focus-supervisor-block: 17
- project-file-mutation: 4

## Anchors

- debug_contract: .omnius/debug-library/CONTRACT.md (exists)
- run_readme: .omnius/debug-library/runs/1783095123826-r2p6do/README.md (exists)
- run_index: .omnius/debug-library/runs/1783095123826-r2p6do/index.json (exists)
- run_events_jsonl: .omnius/debug-library/runs/1783095123826-r2p6do/events.jsonl (exists)
- workboard_active: .omnius/workboards/1783095123826-r2p6do/active.json (exists)
- workboard_events: .omnius/workboards/1783095123826-r2p6do/events.jsonl (exists)
- context_dump_latest: .omnius/context-window-dumps/latest.json (exists)
- context_dump_index: .omnius/context-window-dumps/index.jsonl (exists)
- trajectory_log: .omnius/trajectories/trajectories.jsonl (exists)
- checkpoints_dir: .omnius/checkpoints (exists)
- phases_dir: .omnius/phases (exists)
- completion_ledgers_dir: .omnius/completion-ledgers (exists)

## Latest Events

- 2026-07-03T16:52:18.447Z turn 0 context_window_dump: context dump agent_turn | tokens~15249
- 2026-07-03T16:52:18.225Z turn 43 context_window_dump: context dump agent_turn | tokens~75207 | required=report_incomplete | diagnoses=focus-supervisor-active
- 2026-07-03T16:52:18.164Z turn 41 tool_result failure: file_read failure | diagnoses=focus-supervisor-active,focus-supervisor-block,tool-failure
- 2026-07-03T16:50:54.323Z turn 0 context_window_dump: context dump agent_turn | tokens~15240
- 2026-07-03T16:50:54.129Z turn 42 context_window_dump: context dump agent_turn | tokens~77165 | required=report_incomplete | diagnoses=focus-supervisor-active
- 2026-07-03T16:50:54.116Z turn 40 tool_result failure: file_read failure | diagnoses=focus-supervisor-active,focus-supervisor-block,tool-failure
- 2026-07-03T16:50:53.995Z turn 40 tool_result success: file_read success | diagnoses=focus-supervisor-active,focus-supervisor-block
- 2026-07-03T16:49:34.253Z turn 0 context_window_dump: context dump agent_turn | tokens~15240
- 2026-07-03T16:49:34.039Z turn 41 context_window_dump: context dump agent_turn | tokens~76059 | required=report_incomplete | diagnoses=focus-supervisor-active
- 2026-07-03T16:47:49.197Z turn 0 context_window_dump: context dump agent_turn | tokens~15249
- 2026-07-03T16:47:48.888Z turn 39 tool_result success: task_complete success | diagnoses=focus-supervisor-active
- 2026-07-03T16:46:18.825Z turn 0 context_window_dump: context dump agent_turn | tokens~15249
- 2026-07-03T16:46:18.597Z turn 40 context_window_dump: context dump agent_turn | tokens~75114 | required=report_incomplete | diagnoses=focus-supervisor-active
- 2026-07-03T16:46:18.528Z turn 38 tool_result failure: file_write failure | diagnoses=focus-supervisor-active,focus-supervisor-block,tool-failure
- 2026-07-03T16:44:45.337Z turn 0 context_window_dump: context dump agent_turn | tokens~15249
- 2026-07-03T16:44:45.122Z turn 39 context_window_dump: context dump agent_turn | tokens~73855 | required=report_incomplete | diagnoses=focus-supervisor-active
- 2026-07-03T16:44:45.108Z turn 37 tool_result failure: agent failure | diagnoses=focus-supervisor-active,focus-supervisor-block,tool-failure
- 2026-07-03T16:43:08.798Z turn 0 context_window_dump: context dump agent_turn | tokens~15249
- 2026-07-03T16:43:08.527Z turn 38 context_window_dump: context dump agent_turn | tokens~72685 | required=report_incomplete | diagnoses=focus-supervisor-active
- 2026-07-03T16:43:08.511Z turn 36 tool_result failure: file_read failure | diagnoses=focus-supervisor-active,focus-supervisor-block,tool-failure
- 2026-07-03T16:40:38.578Z turn 0 context_window_dump: context dump agent_turn | tokens~15249
- 2026-07-03T16:40:38.337Z turn 37 context_window_dump: context dump agent_turn | tokens~71148 | required=report_incomplete | diagnoses=focus-supervisor-active
- 2026-07-03T16:40:38.324Z turn 35 tool_result failure: shell failure | diagnoses=focus-supervisor-active,focus-supervisor-block,tool-failure | command=cd /home/roko/Documents/Projects/myactuator/firmware/esp32 && sed -i '/-DPROTOCOL_CAN/d; /-DPROTOCOL_RS485/d; /-DPROTOCOL_ETHERCAT/d; /-DMOTOR_RMD_X/d; /-DMOTOR_RH/d; /-DMOTOR_CEM/
[truncated 221 chars]
- 2026-07-03T16:39:00.999Z turn 0 context_window_dump: context dump agent_turn | tokens~15240
- 2026-07-03T16:39:00.697Z turn 36 context_window_dump: context dump agent_turn | tokens~68799 | required=report_incomplete | diagnoses=focus-supervisor-active
- 2026-07-03T16:39:00.682Z turn 34 tool_result failure: file_edit failure | diagnoses=focus-supervisor-active,focus-supervisor-block,tool-failure
- 2026-07-03T16:37:29.596Z turn 0 context_window_dump: context dump agent_turn | tokens~15240
- 2026-07-03T16:37:29.405Z turn 35 context_window_dump: context dump agent_turn | tokens~66938 | required=report_incomplete | diagnoses=focus-supervisor-active
- 2026-07-03T16:37:29.395Z turn 33 tool_result success: file_read success | diagnoses=focus-supervisor-active,focus-supervisor-block
- 2026-07-03T16:37:29.280Z turn 33 tool_result success: file_read success | diagnoses=focus-supervisor-active,focus-supervisor-block
- 2026-07-03T16:36:12.370Z turn 34 context_window_dump: context dump agent_turn | tokens~65127 | required=use_cached_evidence | diagnoses=focus-supervisor-active
- 2026-07-03T16:36:12.360Z turn 32 tool_result success: file_read success | diagnoses=focus-supervisor-active,focus-supervisor-block
- 2026-07-03T16:36:12.237Z turn 32 tool_result success: file_read success | diagnoses=focus-supervisor-active,focus-supervisor-block
- 2026-07-03T16:36:11.869Z turn 0 context_window_dump: context dump agent_turn | tokens~15240
- 2026-07-03T16:36:11.705Z turn 32 tool_result success: file_read success | diagnoses=focus-supervisor-active,focus-supervisor-block
- 2026-07-03T16:34:51.736Z turn 0 context_window_dump: context dump agent_turn | tokens~15249
- 2026-07-03T16:34:51.533Z turn 33 context_window_dump: context dump agent_turn | tokens~65130 | required=use_cached_evidence | diagnoses=focus-supervisor-active
- 2026-07-03T16:33:41.531Z turn 0 context_window_dump: context dump agent_turn | tokens~15240
- 2026-07-03T16:33:41.324Z turn 32 context_window_dump: context dump agent_turn | tokens~64968 | required=use_cached_evidence | diagnoses=focus-supervisor-active
- 2026-07-03T16:32:19.758Z turn 0 context_window_dump: context dump agent_turn | tokens~15240
