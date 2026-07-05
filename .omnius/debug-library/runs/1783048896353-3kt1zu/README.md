# Debug Run 1783048896353-3kt1zu

Updated: 2026-07-04T07:42:24.518Z
Workspace: /home/roko/Documents/Projects/myactuator

## Summary

- events: 186
- tool events: 61
- context dumps: 125
- failures: 38
- mutations: 17
- shell mutations: 1
- focus blocks: 27
- suspicious shell events: 0

## Diagnoses

- focus-supervisor-active: 64
- tool-failure: 38
- focus-supervisor-block: 27
- project-file-mutation: 17
- shell-filesystem-mutation: 1

## Anchors

- debug_contract: .omnius/debug-library/CONTRACT.md (exists)
- run_readme: .omnius/debug-library/runs/1783048896353-3kt1zu/README.md (exists)
- run_index: .omnius/debug-library/runs/1783048896353-3kt1zu/index.json (exists)
- run_events_jsonl: .omnius/debug-library/runs/1783048896353-3kt1zu/events.jsonl (exists)
- workboard_active: .omnius/workboards/1783048896353-3kt1zu/active.json (exists)
- workboard_events: .omnius/workboards/1783048896353-3kt1zu/events.jsonl (exists)
- context_dump_latest: .omnius/context-window-dumps/latest.json (exists)
- context_dump_index: .omnius/context-window-dumps/index.jsonl (exists)
- trajectory_log: .omnius/trajectories/trajectories.jsonl (exists)
- checkpoints_dir: .omnius/checkpoints (exists)
- phases_dir: .omnius/phases (exists)
- completion_ledgers_dir: .omnius/completion-ledgers (exists)

## Latest Events

- 2026-07-04T07:42:24.517Z turn 0 context_window_dump: context dump agent_turn | tokens~15961
- 2026-07-04T07:42:24.394Z turn 21 context_window_dump: context dump agent_turn | tokens~61647 | required=update_todos | diagnoses=focus-supervisor-active
- 2026-07-04T07:42:24.375Z turn 19 tool_result failure: file_patch failure | diagnoses=focus-supervisor-active,tool-failure
- 2026-07-04T07:41:06.621Z turn 0 context_window_dump: context dump agent_turn | tokens~15961
- 2026-07-04T07:41:06.506Z turn 20 context_window_dump: context dump agent_turn | tokens~59513 | required=update_todos | diagnoses=focus-supervisor-active
- 2026-07-04T07:41:06.487Z turn 18 tool_result failure: file_patch failure | diagnoses=focus-supervisor-active,tool-failure
- 2026-07-04T07:39:53.251Z turn 0 context_window_dump: context dump agent_turn | tokens~15960
- 2026-07-04T07:39:53.127Z turn 19 context_window_dump: context dump agent_turn | tokens~57952 | required=update_todos | diagnoses=focus-supervisor-active
- 2026-07-04T07:39:53.111Z turn 17 tool_result failure: file_patch failure | diagnoses=focus-supervisor-active,tool-failure
- 2026-07-04T07:38:41.946Z turn 0 context_window_dump: context dump agent_turn | tokens~15960
- 2026-07-04T07:38:41.722Z turn 18 context_window_dump: context dump agent_turn | tokens~56413 | required=update_todos | diagnoses=focus-supervisor-active
- 2026-07-04T07:38:41.705Z turn 16 tool_result failure: file_patch failure | diagnoses=focus-supervisor-active,tool-failure
- 2026-07-04T07:37:35.935Z turn 0 context_window_dump: context dump agent_turn | tokens~15960
- 2026-07-04T07:37:35.717Z turn 17 context_window_dump: context dump agent_turn | tokens~54876 | required=update_todos | diagnoses=focus-supervisor-active
- 2026-07-04T07:37:35.702Z turn 15 tool_result failure: file_patch failure | diagnoses=focus-supervisor-active,tool-failure
- 2026-07-04T07:36:28.287Z turn 0 context_window_dump: context dump agent_turn | tokens~15960
- 2026-07-04T07:36:28.176Z turn 16 context_window_dump: context dump agent_turn | tokens~53636 | required=update_todos | diagnoses=focus-supervisor-active
- 2026-07-04T07:36:28.158Z turn 14 tool_result failure: file_patch failure | diagnoses=focus-supervisor-active,tool-failure
- 2026-07-04T07:35:19.189Z turn 0 context_window_dump: context dump agent_turn | tokens~15960
- 2026-07-04T07:35:19.099Z turn 15 context_window_dump: context dump agent_turn | tokens~51998 | required=update_todos | diagnoses=focus-supervisor-active
- 2026-07-04T07:35:19.048Z turn 13 tool_result failure: file_patch failure | diagnoses=focus-supervisor-active,tool-failure
- 2026-07-04T07:34:14.422Z turn 0 context_window_dump: context dump agent_turn | tokens~15960
- 2026-07-04T07:34:14.167Z turn 14 context_window_dump: context dump agent_turn | tokens~51207 | required=update_todos | diagnoses=focus-supervisor-active
- 2026-07-04T07:34:14.153Z turn 12 tool_result failure: file_patch failure | diagnoses=focus-supervisor-active,tool-failure
- 2026-07-04T07:33:12.107Z turn 0 context_window_dump: context dump agent_turn | tokens~15960
- 2026-07-04T07:33:11.960Z turn 13 context_window_dump: context dump agent_turn | tokens~50707 | required=update_todos | diagnoses=focus-supervisor-active
- 2026-07-04T07:33:11.947Z turn 11 tool_result failure: file_patch failure | diagnoses=focus-supervisor-active,tool-failure
- 2026-07-04T07:32:22.702Z turn 0 context_window_dump: context dump agent_turn | tokens~15960
- 2026-07-04T07:32:22.485Z turn 12 context_window_dump: context dump agent_turn | tokens~50469 | required=read_authoritative_target | diagnoses=focus-supervisor-active
- 2026-07-04T07:32:22.449Z turn 10 tool_result failure: file_patch failure | diagnoses=focus-supervisor-active,tool-failure
- 2026-07-04T07:31:45.381Z turn 0 context_window_dump: context dump agent_turn | tokens~15960
- 2026-07-04T07:31:45.166Z turn 11 context_window_dump: context dump agent_turn | tokens~49091 | required=read_authoritative_target | diagnoses=focus-supervisor-active
- 2026-07-04T07:31:45.150Z turn 9 tool_result failure: file_patch failure | diagnoses=focus-supervisor-active,tool-failure
- 2026-07-04T07:30:45.340Z turn 0 context_window_dump: context dump agent_turn | tokens~15960
- 2026-07-04T07:30:45.132Z turn 10 context_window_dump: context dump agent_turn | tokens~48757 | required=read_authoritative_target | diagnoses=focus-supervisor-active
- 2026-07-04T07:30:45.112Z turn 8 tool_result failure: file_edit failure | diagnoses=focus-supervisor-active,tool-failure
- 2026-07-04T07:29:39.940Z turn 0 context_window_dump: context dump agent_turn | tokens~15951
- 2026-07-04T07:29:39.712Z turn 9 context_window_dump: context dump agent_turn | tokens~49040
- 2026-07-04T07:28:43.398Z turn 0 context_window_dump: context dump agent_turn | tokens~15960
- 2026-07-04T07:28:43.186Z turn 8 context_window_dump: context dump agent_turn | tokens~48935 | required=read_authoritative_target | diagnoses=focus-supervisor-active
