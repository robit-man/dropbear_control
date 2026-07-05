# Debug Run 1783065197489-zzttvn

Updated: 2026-07-03T08:16:40.743Z
Workspace: /home/roko/Documents/Projects/myactuator

## Summary

- events: 88
- tool events: 25
- context dumps: 63
- failures: 11
- mutations: 3
- shell mutations: 0
- focus blocks: 12
- suspicious shell events: 0

## Diagnoses

- focus-supervisor-active: 35
- focus-supervisor-block: 12
- tool-failure: 11
- project-file-mutation: 3

## Anchors

- debug_contract: .omnius/debug-library/CONTRACT.md (exists)
- run_readme: .omnius/debug-library/runs/1783065197489-zzttvn/README.md (exists)
- run_index: .omnius/debug-library/runs/1783065197489-zzttvn/index.json (exists)
- run_events_jsonl: .omnius/debug-library/runs/1783065197489-zzttvn/events.jsonl (exists)
- workboard_active: .omnius/workboards/1783065197489-zzttvn/active.json (exists)
- workboard_events: .omnius/workboards/1783065197489-zzttvn/events.jsonl (exists)
- context_dump_latest: .omnius/context-window-dumps/latest.json (exists)
- context_dump_index: .omnius/context-window-dumps/index.jsonl (exists)
- trajectory_log: .omnius/trajectories/trajectories.jsonl (exists)
- checkpoints_dir: .omnius/checkpoints (exists)
- phases_dir: .omnius/phases (exists)
- completion_ledgers_dir: .omnius/completion-ledgers (exists)

## Latest Events

- 2026-07-03T08:16:40.742Z turn 4 tool_result failure: task_complete failure | diagnoses=focus-supervisor-active,focus-supervisor-block,tool-failure
- 2026-07-03T08:16:28.536Z turn 4 context_window_dump: context dump brute_force_turn | tokens~11385 | required=update_todos | diagnoses=focus-supervisor-active
- 2026-07-03T08:15:29.225Z turn 3 context_window_dump: context dump brute_force_turn | tokens~11368 | required=update_todos | diagnoses=focus-supervisor-active
- 2026-07-03T08:15:16.334Z turn 4 tool_result failure: task_complete failure | diagnoses=focus-supervisor-active,focus-supervisor-block,tool-failure
- 2026-07-03T08:15:09.984Z turn 2 context_window_dump: context dump brute_force_turn | tokens~10931 | required=update_todos | diagnoses=focus-supervisor-active
- 2026-07-03T08:14:12.929Z turn 1 context_window_dump: context dump brute_force_turn | tokens~10817 | required=update_todos | diagnoses=focus-supervisor-active
- 2026-07-03T08:14:12.925Z turn 4 tool_result failure: task_complete failure | diagnoses=focus-supervisor-active,focus-supervisor-block,tool-failure
- 2026-07-03T08:14:01.016Z turn 0 context_window_dump: context dump brute_force_turn | tokens~10022 | required=update_todos | diagnoses=focus-supervisor-active
- 2026-07-03T08:14:01.008Z turn 3 tool_result failure: file_write failure | diagnoses=focus-supervisor-active,tool-failure
- 2026-07-03T08:13:43.565Z turn 4 context_window_dump: context dump agent_turn | tokens~10066 | required=update_todos | diagnoses=focus-supervisor-active
- 2026-07-03T08:13:43.558Z turn 2 tool_result failure: todo_write failure | diagnoses=focus-supervisor-active,tool-failure
- 2026-07-03T08:13:28.283Z turn 3 context_window_dump: context dump agent_turn | tokens~9218 | required=update_todos | diagnoses=focus-supervisor-active
- 2026-07-03T08:13:28.277Z turn 1 tool_result failure: task_complete failure | diagnoses=focus-supervisor-active,focus-supervisor-block,tool-failure
- 2026-07-03T08:13:19.732Z turn 2 context_window_dump: context dump agent_turn | tokens~7707 | required=update_todos | diagnoses=focus-supervisor-active
- 2026-07-03T08:12:48.023Z turn 1 context_window_dump: context dump agent_turn | tokens~6365
- 2026-07-03T08:12:48.012Z turn 0 tool_result success: memory_read success | diagnoses=focus-supervisor-block
- 2026-07-03T08:12:42.029Z turn 1 context_window_dump: context dump agent_turn | tokens~5922
- 2026-07-03T08:12:42.021Z turn 0 tool_result success: memory_read success | diagnoses=focus-supervisor-block
- 2026-07-03T08:12:21.141Z turn 0 context_window_dump: context dump agent_turn | tokens~16229
- 2026-07-03T08:12:21.000Z turn 0 context_window_dump: context dump agent_turn | tokens~16039
- 2026-07-03T08:12:20.865Z turn 0 context_window_dump: context dump agent_turn | tokens~14630
- 2026-07-03T08:12:20.685Z turn 21 tool_result success: file_read success | diagnoses=focus-supervisor-active,focus-supervisor-block
- 2026-07-03T08:11:40.482Z turn 0 context_window_dump: context dump brute_force_turn | tokens~14866
- 2026-07-03T08:11:32.680Z turn 0 context_window_dump: context dump agent_turn | tokens~14630
- 2026-07-03T08:11:32.470Z turn 22 context_window_dump: context dump agent_turn | tokens~54773 | required=use_cached_evidence | diagnoses=focus-supervisor-active
- 2026-07-03T08:11:32.459Z turn 19 tool_result success: file_read success | diagnoses=focus-supervisor-active
- 2026-07-03T08:10:55.198Z turn 0 context_window_dump: context dump brute_force_turn | tokens~14866
- 2026-07-03T08:10:47.446Z turn 0 context_window_dump: context dump agent_turn | tokens~14630
- 2026-07-03T08:10:47.256Z turn 21 context_window_dump: context dump agent_turn | tokens~53723
- 2026-07-03T08:06:26.562Z turn 0 context_window_dump: context dump agent_turn | tokens~14630
- 2026-07-03T08:06:26.354Z turn 20 context_window_dump: context dump agent_turn | tokens~52608
- 2026-07-03T08:05:50.315Z turn 0 context_window_dump: context dump brute_force_turn | tokens~14865
- 2026-07-03T08:05:42.531Z turn 0 context_window_dump: context dump agent_turn | tokens~14639
- 2026-07-03T08:05:42.329Z turn 19 context_window_dump: context dump agent_turn | tokens~51850 | required=use_cached_evidence | diagnoses=focus-supervisor-active
- 2026-07-03T08:05:42.313Z turn 17 tool_result failure: shell failure | diagnoses=focus-supervisor-active,tool-failure | command=cd /home/roko/Documents/Projects/myactuator/firmware/esp32 && pio run 2>&1 | tail -50
- 2026-07-03T08:04:44.060Z turn 18 context_window_dump: context dump agent_turn | tokens~52057 | required=use_cached_evidence | diagnoses=focus-supervisor-active
- 2026-07-03T08:04:44.052Z turn 16 tool_result success: file_read success | diagnoses=focus-supervisor-active,focus-supervisor-block
- 2026-07-03T08:03:57.414Z turn 17 context_window_dump: context dump agent_turn | tokens~51020
- 2026-07-03T08:03:56.715Z turn 0 context_window_dump: context dump agent_turn | tokens~14626
- 2026-07-03T08:03:56.561Z turn 15 tool_result success: file_read success | diagnoses=focus-supervisor-active,focus-supervisor-block
