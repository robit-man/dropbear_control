# Debug Run 1783051233686-twto82

Updated: 2026-07-03T04:23:48.276Z
Workspace: /home/roko/Documents/Projects/myactuator

## Summary

- events: 82
- tool events: 30
- context dumps: 52
- failures: 5
- mutations: 15
- shell mutations: 0
- focus blocks: 10
- suspicious shell events: 0

## Diagnoses

- focus-supervisor-active: 17
- project-file-mutation: 15
- focus-supervisor-block: 10
- tool-failure: 5

## Anchors

- debug_contract: .omnius/debug-library/CONTRACT.md (exists)
- run_readme: .omnius/debug-library/runs/1783051233686-twto82/README.md (exists)
- run_index: .omnius/debug-library/runs/1783051233686-twto82/index.json (exists)
- run_events_jsonl: .omnius/debug-library/runs/1783051233686-twto82/events.jsonl (exists)
- workboard_active: .omnius/workboards/1783051233686-twto82/active.json (exists)
- workboard_events: .omnius/workboards/1783051233686-twto82/events.jsonl (exists)
- context_dump_latest: .omnius/context-window-dumps/latest.json (exists)
- context_dump_index: .omnius/context-window-dumps/index.jsonl (exists)
- trajectory_log: .omnius/trajectories/trajectories.jsonl (exists)
- checkpoints_dir: .omnius/checkpoints (exists)
- phases_dir: .omnius/phases (exists)
- completion_ledgers_dir: .omnius/completion-ledgers (exists)

## Latest Events

- 2026-07-03T04:23:48.276Z turn 23 context_window_dump: context dump agent_turn | tokens~92411
- 2026-07-03T04:22:38.682Z turn 22 context_window_dump: context dump agent_turn | tokens~93459
- 2026-07-03T04:22:38.667Z turn 20 tool_result success: file_write success | diagnoses=project-file-mutation
- 2026-07-03T04:22:38.489Z turn 20 tool_result success: file_write success | diagnoses=project-file-mutation
- 2026-07-03T04:22:26.293Z turn 20 tool_result success: file_write success | diagnoses=project-file-mutation
- 2026-07-03T04:22:21.441Z turn 20 tool_result success: file_write success | diagnoses=project-file-mutation
- 2026-07-03T04:22:08.542Z turn 20 tool_result success: file_write success | diagnoses=project-file-mutation
- 2026-07-03T04:22:03.926Z turn 0 context_window_dump: context dump agent_turn | tokens~14889
- 2026-07-03T04:22:03.284Z turn 20 tool_result success: file_write success | diagnoses=project-file-mutation
- 2026-07-03T04:20:36.895Z turn 21 context_window_dump: context dump agent_turn | tokens~87462
- 2026-07-03T04:20:34.758Z turn 0 context_window_dump: context dump agent_turn | tokens~14889
- 2026-07-03T04:19:35.020Z turn 0 context_window_dump: context dump brute_force_turn | tokens~15124
- 2026-07-03T04:19:26.958Z turn 0 context_window_dump: context dump agent_turn | tokens~14889
- 2026-07-03T04:19:26.669Z turn 20 context_window_dump: context dump agent_turn | tokens~85983
- 2026-07-03T04:19:26.631Z turn 18 tool_result success: shell success | command=find /home/roko/Documents/Projects/myactuator/firmware/esp32 -type f | sort
- 2026-07-03T04:18:32.271Z turn 0 context_window_dump: context dump brute_force_turn | tokens~15124
- 2026-07-03T04:18:24.204Z turn 0 context_window_dump: context dump agent_turn | tokens~14889
- 2026-07-03T04:18:23.996Z turn 19 context_window_dump: context dump agent_turn | tokens~83685
- 2026-07-03T04:17:48.847Z turn 0 context_window_dump: context dump agent_turn | tokens~14889
- 2026-07-03T04:17:48.236Z turn 17 tool_result success: file_write success | diagnoses=project-file-mutation
- 2026-07-03T04:16:44.058Z turn 18 context_window_dump: context dump agent_turn | tokens~79869
- 2026-07-03T04:16:26.212Z turn 0 context_window_dump: context dump agent_turn | tokens~14889
- 2026-07-03T04:16:25.590Z turn 16 tool_result success: file_write success | diagnoses=project-file-mutation
- 2026-07-03T04:15:23.946Z turn 17 context_window_dump: context dump agent_turn | tokens~76517
- 2026-07-03T04:15:07.571Z turn 0 context_window_dump: context dump agent_turn | tokens~14889
- 2026-07-03T04:15:06.906Z turn 15 tool_result success: file_write success | diagnoses=project-file-mutation
- 2026-07-03T04:14:05.915Z turn 0 context_window_dump: context dump brute_force_turn | tokens~15124
- 2026-07-03T04:13:57.622Z turn 0 context_window_dump: context dump agent_turn | tokens~14889
- 2026-07-03T04:13:57.404Z turn 16 context_window_dump: context dump agent_turn | tokens~72192
- 2026-07-03T04:13:22.787Z turn 0 context_window_dump: context dump agent_turn | tokens~14889
- 2026-07-03T04:13:22.128Z turn 14 tool_result success: file_write success | diagnoses=project-file-mutation
- 2026-07-03T04:12:13.093Z turn 15 context_window_dump: context dump agent_turn | tokens~67705
- 2026-07-03T04:12:09.941Z turn 0 context_window_dump: context dump agent_turn | tokens~14889
- 2026-07-03T04:11:43.624Z turn 0 context_window_dump: context dump agent_turn | tokens~14889
- 2026-07-03T04:10:43.248Z turn 0 context_window_dump: context dump brute_force_turn | tokens~15115
- 2026-07-03T04:10:35.204Z turn 0 context_window_dump: context dump agent_turn | tokens~14889
- 2026-07-03T04:10:34.986Z turn 14 context_window_dump: context dump agent_turn | tokens~62925
- 2026-07-03T04:10:34.969Z turn 12 tool_result success: file_write success | diagnoses=project-file-mutation
- 2026-07-03T04:09:31.099Z turn 0 context_window_dump: context dump agent_turn | tokens~14889
- 2026-07-03T04:09:31.052Z turn 13 context_window_dump: context dump agent_turn | tokens~60846 | required=use_cached_evidence | diagnoses=focus-supervisor-active
