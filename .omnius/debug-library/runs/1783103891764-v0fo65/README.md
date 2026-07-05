# Debug Run 1783103891764-v0fo65

Updated: 2026-07-04T04:01:32.368Z
Workspace: /home/roko/Documents/Projects/myactuator

## Summary

- events: 139
- tool events: 35
- context dumps: 104
- failures: 17
- mutations: 3
- shell mutations: 0
- focus blocks: 10
- suspicious shell events: 0

## Diagnoses

- focus-supervisor-active: 41
- tool-failure: 17
- focus-supervisor-block: 10
- focus-supervisor-cached-evidence: 7
- project-file-mutation: 3

## Anchors

- debug_contract: .omnius/debug-library/CONTRACT.md (exists)
- run_readme: .omnius/debug-library/runs/1783103891764-v0fo65/README.md (exists)
- run_index: .omnius/debug-library/runs/1783103891764-v0fo65/index.json (exists)
- run_events_jsonl: .omnius/debug-library/runs/1783103891764-v0fo65/events.jsonl (exists)
- workboard_active: .omnius/workboards/1783103891764-v0fo65/active.json (exists)
- workboard_events: .omnius/workboards/1783103891764-v0fo65/events.jsonl (exists)
- context_dump_latest: .omnius/context-window-dumps/latest.json (exists)
- context_dump_index: .omnius/context-window-dumps/index.jsonl (exists)
- trajectory_log: .omnius/trajectories/trajectories.jsonl (exists)
- checkpoints_dir: .omnius/checkpoints (exists)
- phases_dir: .omnius/phases (exists)
- completion_ledgers_dir: .omnius/completion-ledgers (exists)

## Latest Events

- 2026-07-04T04:01:32.368Z turn 0 context_window_dump: context dump agent_turn | tokens~16769
- 2026-07-04T04:01:32.136Z turn 14 context_window_dump: context dump agent_turn | tokens~50192
- 2026-07-04T04:01:32.110Z turn 12 tool_result success: file_read success | diagnoses=focus-supervisor-cached-evidence
- 2026-07-04T04:00:38.086Z turn 0 context_window_dump: context dump agent_turn | tokens~16769
- 2026-07-04T04:00:37.859Z turn 13 context_window_dump: context dump agent_turn | tokens~49645
- 2026-07-04T04:00:37.835Z turn 11 tool_result success: file_read success | diagnoses=focus-supervisor-cached-evidence
- 2026-07-04T03:59:41.400Z turn 0 context_window_dump: context dump agent_turn | tokens~16769
- 2026-07-04T03:59:41.172Z turn 12 context_window_dump: context dump agent_turn | tokens~49726
- 2026-07-04T03:58:49.358Z turn 0 context_window_dump: context dump agent_turn | tokens~16769
- 2026-07-04T03:58:49.135Z turn 11 context_window_dump: context dump agent_turn | tokens~48413
- 2026-07-04T03:58:49.108Z turn 9 tool_result success: file_patch success | diagnoses=project-file-mutation
- 2026-07-04T03:57:53.046Z turn 0 context_window_dump: context dump agent_turn | tokens~16751
- 2026-07-04T03:57:52.822Z turn 10 context_window_dump: context dump agent_turn | tokens~47888 | required=read_authoritative_target | diagnoses=focus-supervisor-active
- 2026-07-04T03:57:52.796Z turn 8 tool_result failure: file_edit failure | diagnoses=focus-supervisor-active,tool-failure
- 2026-07-04T03:56:59.425Z turn 0 context_window_dump: context dump agent_turn | tokens~16751
- 2026-07-04T03:56:59.189Z turn 9 context_window_dump: context dump agent_turn | tokens~46339
- 2026-07-04T03:56:59.166Z turn 7 tool_result failure: file_edit failure | diagnoses=tool-failure
- 2026-07-04T03:55:33.718Z turn 0 context_window_dump: context dump agent_turn | tokens~16751
- 2026-07-04T03:55:33.406Z turn 8 context_window_dump: context dump agent_turn | tokens~45351
- 2026-07-04T03:55:33.378Z turn 6 tool_result failure: file_edit failure | diagnoses=tool-failure
- 2026-07-04T03:54:41.232Z turn 7 context_window_dump: context dump agent_turn | tokens~43939
- 2026-07-04T03:54:41.213Z turn 5 tool_result success: file_read success | diagnoses=focus-supervisor-cached-evidence
- 2026-07-04T03:53:41.282Z turn 6 context_window_dump: context dump agent_turn | tokens~43888
- 2026-07-04T03:53:40.261Z turn 4 tool_result success: file_read success | diagnoses=focus-supervisor-active
- 2026-07-04T03:53:39.782Z turn 4 tool_result success: file_read success | diagnoses=focus-supervisor-active
- 2026-07-04T03:52:57.271Z turn 0 context_window_dump: context dump agent_turn | tokens~16741
- 2026-07-04T03:52:57.143Z turn 5 context_window_dump: context dump agent_turn | tokens~42246 | required=update_todos | diagnoses=focus-supervisor-active
- 2026-07-04T03:52:57.114Z turn 3 tool_result success: file_read success | diagnoses=focus-supervisor-active
- 2026-07-04T03:52:19.612Z turn 4 context_window_dump: context dump agent_turn | tokens~41908 | required=update_todos | diagnoses=focus-supervisor-active
- 2026-07-04T03:52:19.586Z turn 2 tool_result success: list_directory success | diagnoses=focus-supervisor-active
- 2026-07-04T03:52:19.499Z turn 2 tool_result success: list_directory success | diagnoses=focus-supervisor-active
- 2026-07-04T03:52:02.586Z turn 0 context_window_dump: context dump agent_turn | tokens~16750
- 2026-07-04T03:52:02.389Z turn 3 context_window_dump: context dump agent_turn | tokens~41131 | required=update_todos | diagnoses=focus-supervisor-active
- 2026-07-04T03:52:02.371Z turn 1 tool_result success: list_directory success | diagnoses=focus-supervisor-active
- 2026-07-04T03:52:02.285Z turn 1 tool_result failure: list_directory failure | diagnoses=focus-supervisor-active,tool-failure
- 2026-07-04T03:51:44.049Z turn 2 context_window_dump: context dump agent_turn | tokens~40749 | required=update_todos | diagnoses=focus-supervisor-active
- 2026-07-04T03:51:44.027Z turn 0 tool_result failure: file_read failure | diagnoses=focus-supervisor-active,tool-failure
- 2026-07-04T03:51:43.930Z turn 0 tool_result failure: file_read failure | diagnoses=focus-supervisor-active,tool-failure
- 2026-07-04T03:51:24.243Z turn 0 context_window_dump: context dump agent_turn | tokens~16740
- 2026-07-04T03:51:24.119Z turn 1 context_window_dump: context dump agent_turn | tokens~39786
