# Debug Run 1783235936402-neqrnd

Updated: 2026-07-05T08:21:47.895Z
Workspace: /home/roko/Documents/Projects/myactuator

## Summary

- events: 63
- tool events: 26
- context dumps: 37
- failures: 3
- mutations: 6
- shell mutations: 0
- focus blocks: 0
- suspicious shell events: 0

## Diagnoses

- focus-supervisor-active: 13
- project-file-mutation: 6
- focus-supervisor-cached-evidence: 5
- tool-failure: 3

## Anchors

- debug_contract: .omnius/debug-library/CONTRACT.md (exists)
- run_readme: .omnius/debug-library/runs/1783235936402-neqrnd/README.md (exists)
- run_index: .omnius/debug-library/runs/1783235936402-neqrnd/index.json (exists)
- run_events_jsonl: .omnius/debug-library/runs/1783235936402-neqrnd/events.jsonl (exists)
- workboard_active: .omnius/workboards/1783235936402-neqrnd/active.json (exists)
- workboard_events: .omnius/workboards/1783235936402-neqrnd/events.jsonl (exists)
- context_dump_latest: .omnius/context-window-dumps/latest.json (exists)
- context_dump_index: .omnius/context-window-dumps/index.jsonl (exists)
- trajectory_log: .omnius/trajectories/trajectories.jsonl (exists)
- checkpoints_dir: .omnius/checkpoints (exists)
- phases_dir: .omnius/phases (exists)
- completion_ledgers_dir: .omnius/completion-ledgers (exists)

## Latest Events

- 2026-07-05T08:21:47.895Z turn 36 context_window_dump: context dump agent_turn | tokens~71268
- 2026-07-05T08:21:47.868Z turn 34 tool_result success: file_patch success | diagnoses=project-file-mutation
- 2026-07-05T08:19:34.788Z turn 35 context_window_dump: context dump agent_turn | tokens~69686
- 2026-07-05T08:17:24.612Z turn 34 context_window_dump: context dump agent_turn | tokens~69441
- 2026-07-05T08:17:24.562Z turn 32 tool_result success: shell success | command=git log --oneline -10
- 2026-07-05T08:15:18.485Z turn 33 context_window_dump: context dump agent_turn | tokens~69003
- 2026-07-05T08:15:18.464Z turn 31 tool_result success: shell success | command=git log --oneline -10
- 2026-07-05T08:13:11.171Z turn 32 context_window_dump: context dump agent_turn | tokens~68538
- 2026-07-05T08:11:12.763Z turn 31 context_window_dump: context dump agent_turn | tokens~67430
- 2026-07-05T08:10:18.186Z turn 30 context_window_dump: context dump agent_turn | tokens~66907
- 2026-07-05T08:07:18.687Z turn 29 context_window_dump: context dump agent_turn | tokens~66529
- 2026-07-05T08:05:17.627Z turn 28 context_window_dump: context dump agent_turn | tokens~66351
- 2026-07-05T08:05:17.608Z turn 26 tool_result success: shell success | command=git add -A && git commit -m "Add missing getter methods to motor controller"
- 2026-07-05T08:03:18.265Z turn 27 context_window_dump: context dump agent_turn | tokens~65911
- 2026-07-05T08:03:18.238Z turn 25 tool_result success: file_patch success | diagnoses=project-file-mutation
- 2026-07-05T08:01:12.741Z turn 26 context_window_dump: context dump agent_turn | tokens~64256 | required=disambiguate_edit_match | diagnoses=focus-supervisor-active
- 2026-07-05T08:01:12.722Z turn 24 tool_result failure: file_edit failure | diagnoses=focus-supervisor-active,tool-failure
- 2026-07-05T07:59:02.221Z turn 25 context_window_dump: context dump agent_turn | tokens~62032
- 2026-07-05T07:57:07.651Z turn 24 context_window_dump: context dump agent_turn | tokens~60294
- 2026-07-05T07:57:07.626Z turn 22 tool_result success: shell success | command=git add -A && git commit -m "Initial commit: ESP32 motor controller firmware with protocol contracts"
- 2026-07-05T07:55:14.275Z turn 23 context_window_dump: context dump agent_turn | tokens~60029
- 2026-07-05T07:53:22.671Z turn 22 context_window_dump: context dump agent_turn | tokens~59781
- 2026-07-05T07:53:22.653Z turn 20 tool_result success: file_edit success | diagnoses=project-file-mutation
- 2026-07-05T07:51:35.097Z turn 21 context_window_dump: context dump agent_turn | tokens~58926
- 2026-07-05T07:49:46.709Z turn 20 context_window_dump: context dump agent_turn | tokens~57880
- 2026-07-05T07:49:46.690Z turn 18 tool_result success: file_edit success | diagnoses=project-file-mutation
- 2026-07-05T07:47:53.922Z turn 19 context_window_dump: context dump agent_turn | tokens~56168
- 2026-07-05T07:46:09.358Z turn 18 context_window_dump: context dump agent_turn | tokens~54966
- 2026-07-05T07:46:09.339Z turn 16 tool_result success: file_patch success | diagnoses=project-file-mutation
- 2026-07-05T07:44:29.854Z turn 17 context_window_dump: context dump agent_turn | tokens~53565
- 2026-07-05T07:44:29.837Z turn 15 tool_result success: file_read success | diagnoses=focus-supervisor-cached-evidence
- 2026-07-05T07:42:52.938Z turn 16 context_window_dump: context dump agent_turn | tokens~51954
- 2026-07-05T07:41:14.713Z turn 15 context_window_dump: context dump agent_turn | tokens~50771
- 2026-07-05T07:41:14.700Z turn 13 tool_result success: file_read success | diagnoses=focus-supervisor-cached-evidence
- 2026-07-05T07:39:33.881Z turn 14 context_window_dump: context dump agent_turn | tokens~50194
- 2026-07-05T07:39:33.862Z turn 12 tool_result success: shell success | command=git add -A && git commit -m "Initial commit: ESP32 motor controller firmware with protocol contracts"
- 2026-07-05T07:38:00.255Z turn 13 context_window_dump: context dump agent_turn | tokens~48900
- 2026-07-05T07:38:00.238Z turn 11 tool_result success: file_read success | diagnoses=focus-supervisor-cached-evidence
- 2026-07-05T07:36:29.842Z turn 12 context_window_dump: context dump agent_turn | tokens~47970
- 2026-07-05T07:36:29.828Z turn 10 tool_result success: file_read success | diagnoses=focus-supervisor-cached-evidence
