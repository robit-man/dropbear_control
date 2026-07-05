# Debug Run 1783066818924-tz2rco

Updated: 2026-07-03T08:33:35.517Z
Workspace: /home/roko/Documents/Projects/myactuator

## Summary

- events: 72
- tool events: 22
- context dumps: 50
- failures: 13
- mutations: 3
- shell mutations: 0
- focus blocks: 10
- suspicious shell events: 0

## Diagnoses

- focus-supervisor-active: 34
- tool-failure: 13
- focus-supervisor-block: 10
- project-file-mutation: 3

## Anchors

- debug_contract: .omnius/debug-library/CONTRACT.md (exists)
- run_readme: .omnius/debug-library/runs/1783066818924-tz2rco/README.md (exists)
- run_index: .omnius/debug-library/runs/1783066818924-tz2rco/index.json (exists)
- run_events_jsonl: .omnius/debug-library/runs/1783066818924-tz2rco/events.jsonl (exists)
- workboard_active: .omnius/workboards/1783066818924-tz2rco/active.json (exists)
- workboard_events: .omnius/workboards/1783066818924-tz2rco/events.jsonl (exists)
- context_dump_latest: .omnius/context-window-dumps/latest.json (exists)
- context_dump_index: .omnius/context-window-dumps/index.jsonl (exists)
- trajectory_log: .omnius/trajectories/trajectories.jsonl (exists)
- checkpoints_dir: .omnius/checkpoints (exists)
- phases_dir: .omnius/phases (exists)
- completion_ledgers_dir: .omnius/completion-ledgers (exists)

## Latest Events

- 2026-07-03T08:33:35.517Z turn 4 context_window_dump: context dump agent_turn | tokens~6038 | required=update_todos | diagnoses=focus-supervisor-active
- 2026-07-03T08:33:35.513Z turn 2 tool_result failure: memory_search failure | diagnoses=focus-supervisor-active,focus-supervisor-block,tool-failure
- 2026-07-03T08:33:29.877Z turn 4 context_window_dump: context dump agent_turn | tokens~11946 | required=update_todos | diagnoses=focus-supervisor-active
- 2026-07-03T08:33:29.872Z turn 2 tool_result failure: todo_write failure | diagnoses=focus-supervisor-active,tool-failure
- 2026-07-03T08:33:20.160Z turn 3 context_window_dump: context dump agent_turn | tokens~4705 | required=update_todos | diagnoses=focus-supervisor-active
- 2026-07-03T08:33:20.157Z turn 1 tool_result failure: todo_write failure | diagnoses=focus-supervisor-active,tool-failure
- 2026-07-03T08:33:12.127Z turn 3 context_window_dump: context dump agent_turn | tokens~11032 | required=update_todos | diagnoses=focus-supervisor-active
- 2026-07-03T08:33:12.122Z turn 1 tool_result failure: task_complete failure | diagnoses=focus-supervisor-active,focus-supervisor-block,tool-failure
- 2026-07-03T08:33:00.301Z turn 2 context_window_dump: context dump agent_turn | tokens~4028 | required=update_todos | diagnoses=focus-supervisor-active
- 2026-07-03T08:33:00.298Z turn 0 tool_result failure: list_directory failure | diagnoses=focus-supervisor-active,tool-failure
- 2026-07-03T08:32:55.691Z turn 2 context_window_dump: context dump agent_turn | tokens~8635 | required=update_todos | diagnoses=focus-supervisor-active
- 2026-07-03T08:32:55.686Z turn 0 tool_result failure: repl_exec failure | diagnoses=focus-supervisor-active,tool-failure
- 2026-07-03T08:32:35.320Z turn 1 context_window_dump: context dump agent_turn | tokens~3124
- 2026-07-03T08:32:25.332Z turn 1 context_window_dump: context dump agent_turn | tokens~6855
- 2026-07-03T08:32:25.326Z turn 0 tool_result success: memory_read success | diagnoses=focus-supervisor-block
- 2026-07-03T08:32:01.532Z turn 0 context_window_dump: context dump agent_turn | tokens~16334
- 2026-07-03T08:32:01.408Z turn 0 context_window_dump: context dump agent_turn | tokens~16403
- 2026-07-03T08:32:01.155Z turn 25 tool_result success: file_read success | diagnoses=focus-supervisor-active,focus-supervisor-block
- 2026-07-03T08:31:14.576Z turn 26 context_window_dump: context dump agent_turn | tokens~57141 | required=use_cached_evidence | diagnoses=focus-supervisor-active
- 2026-07-03T08:31:14.566Z turn 24 tool_result success: file_read success | diagnoses=focus-supervisor-active,focus-supervisor-block
- 2026-07-03T08:30:39.573Z turn 25 context_window_dump: context dump agent_turn | tokens~57146
- 2026-07-03T08:30:39.458Z turn 23 tool_result success: file_read success | diagnoses=focus-supervisor-active
- 2026-07-03T08:30:03.142Z turn 0 context_window_dump: context dump agent_turn | tokens~15003
- 2026-07-03T08:30:02.942Z turn 24 context_window_dump: context dump agent_turn | tokens~56920
- 2026-07-03T08:30:02.926Z turn 22 tool_result success: file_edit success | diagnoses=project-file-mutation
- 2026-07-03T08:29:22.297Z turn 0 context_window_dump: context dump agent_turn | tokens~14779
- 2026-07-03T08:29:22.075Z turn 23 context_window_dump: context dump agent_turn | tokens~56499
- 2026-07-03T08:28:55.999Z turn 0 context_window_dump: context dump agent_turn | tokens~14779
- 2026-07-03T08:28:55.798Z turn 22 context_window_dump: context dump agent_turn | tokens~56520 | required=read_authoritative_target | diagnoses=focus-supervisor-active
- 2026-07-03T08:28:55.786Z turn 20 tool_result failure: file_edit failure | diagnoses=focus-supervisor-active,focus-supervisor-block,tool-failure
- 2026-07-03T08:28:23.523Z turn 0 context_window_dump: context dump agent_turn | tokens~14779
- 2026-07-03T08:28:23.315Z turn 21 context_window_dump: context dump agent_turn | tokens~55501 | required=read_authoritative_target | diagnoses=focus-supervisor-active
- 2026-07-03T08:28:23.304Z turn 19 tool_result failure: file_edit failure | diagnoses=focus-supervisor-active,tool-failure
- 2026-07-03T08:27:53.187Z turn 20 context_window_dump: context dump agent_turn | tokens~53836
- 2026-07-03T08:27:26.219Z turn 19 context_window_dump: context dump agent_turn | tokens~53933 | required=use_cached_evidence | diagnoses=focus-supervisor-active
- 2026-07-03T08:27:26.207Z turn 17 tool_result success: file_read success | diagnoses=focus-supervisor-active
- 2026-07-03T08:26:54.999Z turn 18 context_window_dump: context dump agent_turn | tokens~53682
- 2026-07-03T08:26:29.950Z turn 0 context_window_dump: context dump agent_turn | tokens~14780
- 2026-07-03T08:26:29.782Z turn 17 context_window_dump: context dump agent_turn | tokens~53956
- 2026-07-03T08:26:29.771Z turn 15 tool_result success: file_edit success | diagnoses=project-file-mutation
