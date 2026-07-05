# Debug Run 1783052722873-j5j5xm

Updated: 2026-07-03T04:49:10.541Z
Workspace: /home/roko/Documents/Projects/myactuator

## Summary

- events: 97
- tool events: 30
- context dumps: 67
- failures: 7
- mutations: 3
- shell mutations: 1
- focus blocks: 11
- suspicious shell events: 0

## Diagnoses

- focus-supervisor-active: 12
- focus-supervisor-block: 11
- tool-failure: 7
- project-file-mutation: 3
- shell-filesystem-mutation: 1

## Anchors

- debug_contract: .omnius/debug-library/CONTRACT.md (exists)
- run_readme: .omnius/debug-library/runs/1783052722873-j5j5xm/README.md (exists)
- run_index: .omnius/debug-library/runs/1783052722873-j5j5xm/index.json (exists)
- run_events_jsonl: .omnius/debug-library/runs/1783052722873-j5j5xm/events.jsonl (exists)
- workboard_active: .omnius/workboards/1783052722873-j5j5xm/active.json (exists)
- workboard_events: .omnius/workboards/1783052722873-j5j5xm/events.jsonl (exists)
- context_dump_latest: .omnius/context-window-dumps/latest.json (exists)
- context_dump_index: .omnius/context-window-dumps/index.jsonl (exists)
- trajectory_log: .omnius/trajectories/trajectories.jsonl (exists)
- checkpoints_dir: .omnius/checkpoints (exists)
- phases_dir: .omnius/phases (exists)
- completion_ledgers_dir: .omnius/completion-ledgers (exists)

## Latest Events

- 2026-07-03T04:49:10.540Z turn 0 context_window_dump: context dump brute_force_turn | tokens~15073
- 2026-07-03T04:49:02.605Z turn 0 context_window_dump: context dump agent_turn | tokens~14812
- 2026-07-03T04:49:02.286Z turn 30 context_window_dump: context dump agent_turn | tokens~71435
- 2026-07-03T04:48:16.914Z turn 0 context_window_dump: context dump brute_force_turn | tokens~15101
- 2026-07-03T04:48:08.975Z turn 0 context_window_dump: context dump agent_turn | tokens~14804
- 2026-07-03T04:48:08.705Z turn 29 context_window_dump: context dump agent_turn | tokens~70822
- 2026-07-03T04:48:08.689Z turn 27 tool_result failure: shell failure | diagnoses=tool-failure | command=cd /home/roko/Documents/Projects/myactuator/firmware/esp32 && pio run 2>&1 | tail -50
- 2026-07-03T04:47:13.046Z turn 28 context_window_dump: context dump agent_turn | tokens~68380
- 2026-07-03T04:47:13.034Z turn 26 tool_result success: file_write success | diagnoses=project-file-mutation
- 2026-07-03T04:46:21.672Z turn 0 context_window_dump: context dump brute_force_turn | tokens~15073
- 2026-07-03T04:46:14.280Z turn 27 context_window_dump: context dump agent_turn | tokens~68033
- 2026-07-03T04:46:13.703Z turn 0 context_window_dump: context dump agent_turn | tokens~14812
- 2026-07-03T04:45:29.262Z turn 0 context_window_dump: context dump brute_force_turn | tokens~15073
- 2026-07-03T04:45:21.776Z turn 26 context_window_dump: context dump agent_turn | tokens~68225
- 2026-07-03T04:45:21.288Z turn 0 context_window_dump: context dump agent_turn | tokens~14812
- 2026-07-03T04:44:35.778Z turn 0 context_window_dump: context dump brute_force_turn | tokens~15040
- 2026-07-03T04:44:26.816Z turn 0 context_window_dump: context dump agent_turn | tokens~14804
- 2026-07-03T04:44:26.568Z turn 25 context_window_dump: context dump agent_turn | tokens~68579
- 2026-07-03T04:44:26.554Z turn 23 tool_result failure: shell failure | diagnoses=tool-failure | command=cd /home/roko/Documents/Projects/myactuator/firmware/esp32 && pio run 2>&1 | head -100
- 2026-07-03T04:43:15.814Z turn 0 context_window_dump: context dump brute_force_turn | tokens~15070
- 2026-07-03T04:43:07.877Z turn 0 context_window_dump: context dump agent_turn | tokens~14808
- 2026-07-03T04:43:07.667Z turn 24 context_window_dump: context dump agent_turn | tokens~65434
- 2026-07-03T04:43:07.653Z turn 22 tool_result success: file_edit success | diagnoses=project-file-mutation
- 2026-07-03T04:42:22.174Z turn 0 context_window_dump: context dump brute_force_turn | tokens~15037
- 2026-07-03T04:42:14.203Z turn 0 context_window_dump: context dump agent_turn | tokens~14801
- 2026-07-03T04:42:13.967Z turn 23 context_window_dump: context dump agent_turn | tokens~65663
- 2026-07-03T04:42:13.952Z turn 21 tool_result failure: file_patch failure | diagnoses=tool-failure
- 2026-07-03T04:41:31.971Z turn 0 context_window_dump: context dump brute_force_turn | tokens~15037
- 2026-07-03T04:41:24.075Z turn 0 context_window_dump: context dump agent_turn | tokens~14801
- 2026-07-03T04:41:23.859Z turn 22 context_window_dump: context dump agent_turn | tokens~65615
- 2026-07-03T04:41:23.845Z turn 20 tool_result failure: file_edit failure | diagnoses=tool-failure
- 2026-07-03T04:40:41.977Z turn 0 context_window_dump: context dump brute_force_turn | tokens~15070
- 2026-07-03T04:40:34.062Z turn 0 context_window_dump: context dump agent_turn | tokens~14808
- 2026-07-03T04:40:33.848Z turn 21 context_window_dump: context dump agent_turn | tokens~64805
- 2026-07-03T04:40:33.834Z turn 19 tool_result success: file_edit success | diagnoses=project-file-mutation
- 2026-07-03T04:39:51.302Z turn 0 context_window_dump: context dump brute_force_turn | tokens~15052
- 2026-07-03T04:39:43.354Z turn 0 context_window_dump: context dump agent_turn | tokens~14791
- 2026-07-03T04:39:43.264Z turn 20 context_window_dump: context dump agent_turn | tokens~64074
- 2026-07-03T04:39:43.248Z turn 18 tool_result failure: batch_edit failure | diagnoses=tool-failure
- 2026-07-03T04:38:48.556Z turn 0 context_window_dump: context dump agent_turn | tokens~14791
