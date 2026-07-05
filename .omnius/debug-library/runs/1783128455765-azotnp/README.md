# Debug Run 1783128455765-azotnp

Updated: 2026-07-04T01:59:56.172Z
Workspace: /home/roko/Documents/Projects/myactuator

## Summary

- events: 110
- tool events: 19
- context dumps: 91
- failures: 13
- mutations: 6
- shell mutations: 0
- focus blocks: 5
- suspicious shell events: 0

## Diagnoses

- focus-supervisor-active: 26
- tool-failure: 13
- project-file-mutation: 6
- focus-supervisor-block: 5

## Anchors

- debug_contract: .omnius/debug-library/CONTRACT.md (exists)
- run_readme: .omnius/debug-library/runs/1783128455765-azotnp/README.md (exists)
- run_index: .omnius/debug-library/runs/1783128455765-azotnp/index.json (exists)
- run_events_jsonl: .omnius/debug-library/runs/1783128455765-azotnp/events.jsonl (exists)
- workboard_active: .omnius/workboards/1783128455765-azotnp/active.json (exists)
- workboard_events: .omnius/workboards/1783128455765-azotnp/events.jsonl (exists)
- context_dump_latest: .omnius/context-window-dumps/latest.json (exists)
- context_dump_index: .omnius/context-window-dumps/index.jsonl (exists)
- trajectory_log: .omnius/trajectories/trajectories.jsonl (exists)
- checkpoints_dir: .omnius/checkpoints (exists)
- phases_dir: .omnius/phases (exists)
- completion_ledgers_dir: .omnius/completion-ledgers (exists)

## Latest Events

- 2026-07-04T01:59:56.172Z turn 40 context_window_dump: context dump agent_turn | tokens~73354
- 2026-07-04T01:59:03.067Z turn 39 context_window_dump: context dump agent_turn | tokens~73271
- 2026-07-04T01:58:12.592Z turn 38 context_window_dump: context dump agent_turn | tokens~73162
- 2026-07-04T01:57:18.797Z turn 37 context_window_dump: context dump agent_turn | tokens~72616
- 2026-07-04T01:57:18.769Z turn 35 tool_result success: file_write success | diagnoses=project-file-mutation
- 2026-07-04T01:56:21.135Z turn 36 context_window_dump: context dump agent_turn | tokens~71518
- 2026-07-04T01:56:21.106Z turn 34 tool_result success: file_write success | diagnoses=project-file-mutation
- 2026-07-04T01:55:30.255Z turn 35 context_window_dump: context dump agent_turn | tokens~71035
- 2026-07-04T01:54:44.942Z turn 34 context_window_dump: context dump agent_turn | tokens~70659
- 2026-07-04T01:53:59.951Z turn 0 context_window_dump: context dump brute_force_turn | tokens~16779
- 2026-07-04T01:53:51.019Z turn 0 context_window_dump: context dump agent_turn | tokens~16589
- 2026-07-04T01:53:50.767Z turn 33 context_window_dump: context dump agent_turn | tokens~70580
- 2026-07-04T01:53:04.770Z turn 0 context_window_dump: context dump brute_force_turn | tokens~16820
- 2026-07-04T01:52:55.997Z turn 0 context_window_dump: context dump agent_turn | tokens~16589
- 2026-07-04T01:52:55.870Z turn 32 context_window_dump: context dump agent_turn | tokens~70496
- 2026-07-04T01:51:56.098Z turn 0 context_window_dump: context dump brute_force_turn | tokens~16779
- 2026-07-04T01:51:47.280Z turn 0 context_window_dump: context dump agent_turn | tokens~16589
- 2026-07-04T01:51:47.162Z turn 31 context_window_dump: context dump agent_turn | tokens~69627
- 2026-07-04T01:51:47.139Z turn 29 tool_result success: file_write success | diagnoses=project-file-mutation
- 2026-07-04T01:50:50.070Z turn 0 context_window_dump: context dump brute_force_turn | tokens~16779
- 2026-07-04T01:50:41.131Z turn 0 context_window_dump: context dump agent_turn | tokens~16589
- 2026-07-04T01:50:40.864Z turn 30 context_window_dump: context dump agent_turn | tokens~67564
- 2026-07-04T01:50:00.344Z turn 0 context_window_dump: context dump brute_force_turn | tokens~16779
- 2026-07-04T01:49:51.404Z turn 0 context_window_dump: context dump agent_turn | tokens~16589
- 2026-07-04T01:49:51.290Z turn 29 context_window_dump: context dump agent_turn | tokens~67197 | required=read_authoritative_target | diagnoses=focus-supervisor-active
- 2026-07-04T01:49:51.262Z turn 27 tool_result failure: file_write failure | diagnoses=focus-supervisor-active,tool-failure
- 2026-07-04T01:49:01.443Z turn 0 context_window_dump: context dump brute_force_turn | tokens~16779
- 2026-07-04T01:48:52.498Z turn 0 context_window_dump: context dump agent_turn | tokens~16589
- 2026-07-04T01:48:51.780Z turn 28 context_window_dump: context dump agent_turn | tokens~66192
- 2026-07-04T01:48:10.218Z turn 0 context_window_dump: context dump brute_force_turn | tokens~16779
- 2026-07-04T01:48:01.327Z turn 0 context_window_dump: context dump agent_turn | tokens~16589
- 2026-07-04T01:48:01.082Z turn 27 context_window_dump: context dump agent_turn | tokens~65896
- 2026-07-04T01:48:01.056Z turn 25 tool_result success: file_write success | diagnoses=project-file-mutation
- 2026-07-04T01:47:02.958Z turn 0 context_window_dump: context dump agent_turn | tokens~16589
- 2026-07-04T01:47:02.709Z turn 26 context_window_dump: context dump agent_turn | tokens~64716
- 2026-07-04T01:47:02.687Z turn 24 tool_result success: file_write success | diagnoses=project-file-mutation
- 2026-07-04T01:46:07.865Z turn 0 context_window_dump: context dump agent_turn | tokens~16598
- 2026-07-04T01:46:07.473Z turn 25 context_window_dump: context dump agent_turn | tokens~63841 | required=read_authoritative_target | diagnoses=focus-supervisor-active
- 2026-07-04T01:46:07.406Z turn 23 tool_result failure: file_write failure | diagnoses=focus-supervisor-active,tool-failure
- 2026-07-04T01:45:18.801Z turn 0 context_window_dump: context dump brute_force_turn | tokens~16789
