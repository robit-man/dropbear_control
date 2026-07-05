# Debug Run 1783235936402-neqrnd

Updated: 2026-07-05T07:55:14.276Z
Workspace: /home/roko/Documents/Projects/myactuator

## Summary

- events: 43
- tool events: 19
- context dumps: 24
- failures: 2
- mutations: 4
- shell mutations: 0
- focus blocks: 0
- suspicious shell events: 0

## Diagnoses

- focus-supervisor-active: 11
- focus-supervisor-cached-evidence: 5
- project-file-mutation: 4
- tool-failure: 2

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
- 2026-07-05T07:34:58.489Z turn 11 context_window_dump: context dump agent_turn | tokens~46191
- 2026-07-05T07:34:58.479Z turn 9 tool_result success: file_read success | diagnoses=focus-supervisor-cached-evidence
- 2026-07-05T07:33:26.083Z turn 10 context_window_dump: context dump agent_turn | tokens~45779
- 2026-07-05T07:31:53.821Z turn 9 context_window_dump: context dump agent_turn | tokens~45406
- 2026-07-05T07:30:24.437Z turn 8 context_window_dump: context dump agent_turn | tokens~45175
- 2026-07-05T07:30:24.417Z turn 6 tool_result success: file_patch success | diagnoses=project-file-mutation
- 2026-07-05T07:28:48.470Z turn 7 context_window_dump: context dump agent_turn | tokens~44284
- 2026-07-05T07:27:22.876Z turn 6 context_window_dump: context dump agent_turn | tokens~43617 | required=read_authoritative_target | diagnoses=focus-supervisor-active
- 2026-07-05T07:27:22.862Z turn 4 tool_result failure: file_edit failure | diagnoses=focus-supervisor-active,tool-failure
- 2026-07-05T07:26:46.368Z turn 5 context_window_dump: context dump agent_turn | tokens~42458
- 2026-07-05T07:24:33.635Z turn 4 context_window_dump: context dump agent_turn | tokens~40659
- 2026-07-05T07:24:33.624Z turn 2 tool_result success: shell success | command=git add -A && git commit -m "Initial commit: ESP32 motor controller firmware with protocol contracts"
- 2026-07-05T07:23:52.435Z turn 3 context_window_dump: context dump agent_turn | tokens~39811 | required=use_cached_evidence | diagnoses=focus-supervisor-active
- 2026-07-05T07:23:52.424Z turn 1 tool_result success: file_read success | diagnoses=focus-supervisor-active
- 2026-07-05T07:23:52.060Z turn 1 tool_result success: file_read success | diagnoses=focus-supervisor-active
- 2026-07-05T07:22:52.421Z turn 1 tool_result success: file_read success | diagnoses=focus-supervisor-active
- 2026-07-05T07:21:30.156Z turn 2 context_window_dump: context dump agent_turn | tokens~37896 | required=use_cached_evidence | diagnoses=focus-supervisor-active
- 2026-07-05T07:21:30.145Z turn 0 tool_result success: memory_search success | diagnoses=focus-supervisor-active
- 2026-07-05T07:21:30.025Z turn 0 tool_result success: file_read success | diagnoses=focus-supervisor-active
- 2026-07-05T07:20:09.883Z turn 1 context_window_dump: context dump agent_turn | tokens~36086 | required=use_cached_evidence | diagnoses=focus-supervisor-active
