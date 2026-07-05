# Debug Run 1783102391191-glhboy

Updated: 2026-07-03T18:37:13.491Z
Workspace: /home/roko/Documents/Projects/myactuator

## Summary

- events: 52
- tool events: 15
- context dumps: 37
- failures: 8
- mutations: 3
- shell mutations: 0
- focus blocks: 4
- suspicious shell events: 0

## Diagnoses

- focus-supervisor-active: 14
- tool-failure: 8
- focus-supervisor-cached-evidence: 4
- focus-supervisor-block: 4
- project-file-mutation: 3

## Anchors

- debug_contract: .omnius/debug-library/CONTRACT.md (exists)
- run_readme: .omnius/debug-library/runs/1783102391191-glhboy/README.md (exists)
- run_index: .omnius/debug-library/runs/1783102391191-glhboy/index.json (exists)
- run_events_jsonl: .omnius/debug-library/runs/1783102391191-glhboy/events.jsonl (exists)
- workboard_active: .omnius/workboards/1783102391191-glhboy/active.json (exists)
- workboard_events: .omnius/workboards/1783102391191-glhboy/events.jsonl (exists)
- context_dump_latest: .omnius/context-window-dumps/latest.json (exists)
- context_dump_index: .omnius/context-window-dumps/index.jsonl (exists)
- trajectory_log: .omnius/trajectories/trajectories.jsonl (exists)
- checkpoints_dir: .omnius/checkpoints (exists)
- phases_dir: .omnius/phases (exists)
- completion_ledgers_dir: .omnius/completion-ledgers (exists)

## Latest Events

- 2026-07-03T18:37:13.491Z turn 0 context_window_dump: context dump agent_turn | tokens~16227
- 2026-07-03T18:37:13.256Z turn 21 context_window_dump: context dump agent_turn | tokens~60426
- 2026-07-03T18:37:13.231Z turn 19 tool_result success: file_read success | diagnoses=focus-supervisor-cached-evidence
- 2026-07-03T18:35:42.008Z turn 0 context_window_dump: context dump agent_turn | tokens~16227
- 2026-07-03T18:35:41.260Z turn 20 context_window_dump: context dump agent_turn | tokens~60387 | required=read_authoritative_target | diagnoses=focus-supervisor-active
- 2026-07-03T18:35:41.235Z turn 18 tool_result failure: file_edit failure | diagnoses=focus-supervisor-active,focus-supervisor-block,tool-failure
- 2026-07-03T18:34:02.408Z turn 0 context_window_dump: context dump agent_turn | tokens~16227
- 2026-07-03T18:34:01.728Z turn 19 context_window_dump: context dump agent_turn | tokens~59945 | required=read_authoritative_target | diagnoses=focus-supervisor-active
- 2026-07-03T18:34:01.700Z turn 17 tool_result failure: file_edit failure | diagnoses=focus-supervisor-active,focus-supervisor-block,tool-failure
- 2026-07-03T18:33:10.002Z turn 0 context_window_dump: context dump agent_turn | tokens~16227
- 2026-07-03T18:33:09.695Z turn 18 context_window_dump: context dump agent_turn | tokens~59665 | required=read_authoritative_target | diagnoses=focus-supervisor-active
- 2026-07-03T18:33:09.666Z turn 16 tool_result failure: file_edit failure | diagnoses=focus-supervisor-active,focus-supervisor-block,tool-failure
- 2026-07-03T18:31:41.495Z turn 0 context_window_dump: context dump agent_turn | tokens~16227
- 2026-07-03T18:31:41.264Z turn 17 context_window_dump: context dump agent_turn | tokens~58940 | required=read_authoritative_target | diagnoses=focus-supervisor-active
- 2026-07-03T18:31:41.240Z turn 15 tool_result failure: file_edit failure | diagnoses=focus-supervisor-active,focus-supervisor-block,tool-failure
- 2026-07-03T18:30:16.347Z turn 0 context_window_dump: context dump agent_turn | tokens~16227
- 2026-07-03T18:30:16.228Z turn 16 context_window_dump: context dump agent_turn | tokens~58653 | required=read_authoritative_target | diagnoses=focus-supervisor-active
- 2026-07-03T18:30:16.192Z turn 14 tool_result failure: file_edit failure | diagnoses=focus-supervisor-active,tool-failure
- 2026-07-03T18:28:54.971Z turn 0 context_window_dump: context dump agent_turn | tokens~16217
- 2026-07-03T18:28:54.857Z turn 15 context_window_dump: context dump agent_turn | tokens~57275 | required=read_authoritative_target | diagnoses=focus-supervisor-active
- 2026-07-03T18:28:54.828Z turn 13 tool_result failure: file_edit failure | diagnoses=focus-supervisor-active,tool-failure
- 2026-07-03T18:27:33.101Z turn 0 context_window_dump: context dump agent_turn | tokens~16217
- 2026-07-03T18:27:32.851Z turn 14 context_window_dump: context dump agent_turn | tokens~55807
- 2026-07-03T18:27:32.826Z turn 12 tool_result success: file_read success | diagnoses=focus-supervisor-cached-evidence
- 2026-07-03T18:26:16.591Z turn 0 context_window_dump: context dump agent_turn | tokens~16217
- 2026-07-03T18:26:16.461Z turn 13 context_window_dump: context dump agent_turn | tokens~55749
- 2026-07-03T18:25:01.009Z turn 12 context_window_dump: context dump agent_turn | tokens~55383
- 2026-07-03T18:24:59.757Z turn 0 context_window_dump: context dump agent_turn | tokens~16217
- 2026-07-03T18:23:54.980Z turn 0 context_window_dump: context dump agent_turn | tokens~16217
- 2026-07-03T18:23:54.856Z turn 11 context_window_dump: context dump agent_turn | tokens~54512 | required=read_authoritative_target | diagnoses=focus-supervisor-active
- 2026-07-03T18:23:54.831Z turn 9 tool_result failure: file_edit failure | diagnoses=focus-supervisor-active,tool-failure
- 2026-07-03T18:22:45.949Z turn 0 context_window_dump: context dump agent_turn | tokens~16227
- 2026-07-03T18:22:45.799Z turn 10 context_window_dump: context dump agent_turn | tokens~53652
- 2026-07-03T18:22:45.773Z turn 8 tool_result success: file_edit success | diagnoses=project-file-mutation
- 2026-07-03T18:21:39.589Z turn 0 context_window_dump: context dump agent_turn | tokens~16227
- 2026-07-03T18:21:39.361Z turn 9 context_window_dump: context dump agent_turn | tokens~54313
- 2026-07-03T18:21:39.336Z turn 7 tool_result failure: file_edit failure | diagnoses=tool-failure
- 2026-07-03T18:20:32.614Z turn 8 context_window_dump: context dump agent_turn | tokens~51599
- 2026-07-03T18:19:31.963Z turn 7 context_window_dump: context dump agent_turn | tokens~49752
- 2026-07-03T18:19:31.934Z turn 5 tool_result success: file_write success | diagnoses=project-file-mutation
