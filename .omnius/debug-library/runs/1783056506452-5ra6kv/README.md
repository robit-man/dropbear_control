# Debug Run 1783056506452-5ra6kv

Updated: 2026-07-05T07:08:23.814Z
Workspace: /home/roko/Documents/Projects/myactuator

## Summary

- events: 841
- tool events: 228
- context dumps: 613
- failures: 108
- mutations: 35
- shell mutations: 3
- focus blocks: 44
- suspicious shell events: 0

## Diagnoses

- focus-supervisor-active: 389
- tool-failure: 108
- focus-supervisor-block: 44
- project-file-mutation: 35
- large-context-window: 22
- focus-supervisor-cached-evidence: 20
- shell-filesystem-mutation: 3

## Anchors

- debug_contract: .omnius/debug-library/CONTRACT.md (exists)
- run_readme: .omnius/debug-library/runs/1783056506452-5ra6kv/README.md (exists)
- run_index: .omnius/debug-library/runs/1783056506452-5ra6kv/index.json (exists)
- run_events_jsonl: .omnius/debug-library/runs/1783056506452-5ra6kv/events.jsonl (exists)
- workboard_active: .omnius/workboards/1783056506452-5ra6kv/active.json (exists)
- workboard_events: .omnius/workboards/1783056506452-5ra6kv/events.jsonl (exists)
- context_dump_latest: .omnius/context-window-dumps/latest.json (exists)
- context_dump_index: .omnius/context-window-dumps/index.jsonl (exists)
- trajectory_log: .omnius/trajectories/trajectories.jsonl (exists)
- checkpoints_dir: .omnius/checkpoints (exists)
- phases_dir: .omnius/phases (exists)
- completion_ledgers_dir: .omnius/completion-ledgers (exists)

## Latest Events

- 2026-07-05T07:08:23.813Z turn 1 tool_result success: task_complete success | diagnoses=focus-supervisor-active
- 2026-07-05T07:07:20.847Z turn 2 context_window_dump: context dump agent_turn | tokens~6454 | required=report_blocked | diagnoses=focus-supervisor-active
- 2026-07-05T07:06:12.514Z turn 1 context_window_dump: context dump agent_turn | tokens~4915
- 2026-07-05T07:06:12.279Z turn 0 tool_result success: memory_read success | diagnoses=focus-supervisor-block
- 2026-07-05T07:05:21.975Z turn 0 context_window_dump: context dump agent_turn | tokens~16742
- 2026-07-05T07:05:21.392Z turn 0 context_window_dump: context dump agent_turn | tokens~16673
- 2026-07-05T07:05:20.409Z turn 59 tool_result failure: file_read failure | diagnoses=focus-supervisor-active,focus-supervisor-block,tool-failure
- 2026-07-05T07:04:32.011Z turn 1 context_window_dump: context dump brute_force_turn | tokens~68942 | required=run_verification | diagnoses=focus-supervisor-active
- 2026-07-05T07:03:47.291Z turn 0 context_window_dump: context dump brute_force_turn | tokens~68583 | required=run_verification | diagnoses=focus-supervisor-active
- 2026-07-05T07:02:59.597Z turn 59 context_window_dump: context dump agent_turn | tokens~73778 | required=run_verification | diagnoses=focus-supervisor-active
- 2026-07-05T07:02:12.670Z turn 58 context_window_dump: context dump agent_turn | tokens~72954 | required=run_verification | diagnoses=focus-supervisor-active
- 2026-07-05T07:01:26.629Z turn 57 context_window_dump: context dump agent_turn | tokens~72074 | required=run_verification | diagnoses=focus-supervisor-active
- 2026-07-05T07:00:41.978Z turn 56 context_window_dump: context dump agent_turn | tokens~71225 | required=run_verification | diagnoses=focus-supervisor-active
- 2026-07-05T06:59:57.641Z turn 55 context_window_dump: context dump agent_turn | tokens~70670 | required=run_verification | diagnoses=focus-supervisor-active
- 2026-07-05T06:59:13.320Z turn 54 context_window_dump: context dump agent_turn | tokens~70595 | required=run_verification | diagnoses=focus-supervisor-active
- 2026-07-05T06:58:28.521Z turn 53 context_window_dump: context dump agent_turn | tokens~70738 | required=run_verification | diagnoses=focus-supervisor-active
- 2026-07-05T06:58:28.505Z turn 51 tool_result failure: file_read failure | diagnoses=focus-supervisor-active,focus-supervisor-block,tool-failure
- 2026-07-05T06:57:43.961Z turn 52 context_window_dump: context dump agent_turn | tokens~70663 | required=run_verification | diagnoses=focus-supervisor-active
- 2026-07-05T06:57:43.944Z turn 50 tool_result failure: file_read failure | diagnoses=focus-supervisor-active,focus-supervisor-block,tool-failure
- 2026-07-05T06:56:59.904Z turn 51 context_window_dump: context dump agent_turn | tokens~69991 | required=run_verification | diagnoses=focus-supervisor-active
- 2026-07-05T06:56:59.889Z turn 49 tool_result failure: file_read failure | diagnoses=focus-supervisor-active,focus-supervisor-block,tool-failure
- 2026-07-05T06:56:15.855Z turn 50 context_window_dump: context dump agent_turn | tokens~69513 | required=run_verification | diagnoses=focus-supervisor-active
- 2026-07-05T06:56:15.832Z turn 48 tool_result failure: shell failure | diagnoses=focus-supervisor-active,tool-failure | command=cd firmware/esp32 && pio run 2>&1 | grep -E "error:|warning:|Error|FAILED" | head -50
- 2026-07-05T06:55:29.939Z turn 49 context_window_dump: context dump agent_turn | tokens~68673 | required=run_verification | diagnoses=focus-supervisor-active
- 2026-07-05T06:55:29.924Z turn 47 tool_result failure: shell failure | diagnoses=focus-supervisor-active,focus-supervisor-block,tool-failure | command=cd firmware/esp32 && pio run 2>&1 | tail -100
- 2026-07-05T06:54:46.533Z turn 48 context_window_dump: context dump agent_turn | tokens~68345 | required=run_verification | diagnoses=focus-supervisor-active
- 2026-07-05T06:53:55.451Z turn 47 context_window_dump: context dump agent_turn | tokens~67794 | required=run_verification | diagnoses=focus-supervisor-active
- 2026-07-05T06:49:26.760Z turn 46 context_window_dump: context dump agent_turn | tokens~67794 | required=run_verification | diagnoses=focus-supervisor-active
- 2026-07-05T06:49:26.746Z turn 44 tool_result failure: shell failure | diagnoses=focus-supervisor-active,focus-supervisor-block,tool-failure | command=cd firmware/esp32 && pio run 2>&1 | tail -50
- 2026-07-05T06:48:40.739Z turn 45 context_window_dump: context dump agent_turn | tokens~67549 | required=run_verification | diagnoses=focus-supervisor-active
- 2026-07-05T06:48:40.725Z turn 43 tool_result failure: file_edit failure | diagnoses=focus-supervisor-active,focus-supervisor-block,tool-failure
- 2026-07-05T06:47:48.605Z turn 44 context_window_dump: context dump agent_turn | tokens~66504 | required=run_verification | diagnoses=focus-supervisor-active
- 2026-07-05T06:47:01.857Z turn 43 context_window_dump: context dump agent_turn | tokens~66299 | required=run_verification | diagnoses=focus-supervisor-active
- 2026-07-05T06:47:01.843Z turn 41 tool_result failure: file_read failure | diagnoses=focus-supervisor-active,focus-supervisor-block,tool-failure
- 2026-07-05T06:46:20.899Z turn 42 context_window_dump: context dump agent_turn | tokens~66201 | required=run_verification | diagnoses=focus-supervisor-active
- 2026-07-05T06:46:20.875Z turn 40 tool_result failure: shell failure | diagnoses=focus-supervisor-active,tool-failure | command=cd firmware/esp32 && pio run 2>&1 | tail -50
- 2026-07-05T06:45:30.644Z turn 41 context_window_dump: context dump agent_turn | tokens~65294
- 2026-07-05T06:44:23.200Z turn 40 context_window_dump: context dump agent_turn | tokens~65127
- 2026-07-05T06:43:37.679Z turn 39 context_window_dump: context dump agent_turn | tokens~64674
- 2026-07-05T06:42:53.674Z turn 38 context_window_dump: context dump agent_turn | tokens~64461
