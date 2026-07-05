# Debug Run 1783067649743-p1k5kq

Updated: 2026-07-04T22:17:35.429Z
Workspace: /home/roko/Documents/Projects/myactuator

## Summary

- events: 355
- tool events: 121
- context dumps: 234
- failures: 53
- mutations: 29
- shell mutations: 5
- focus blocks: 31
- suspicious shell events: 0

## Diagnoses

- focus-supervisor-active: 149
- tool-failure: 53
- focus-supervisor-block: 31
- project-file-mutation: 29
- focus-supervisor-cached-evidence: 5
- shell-filesystem-mutation: 5

## Anchors

- debug_contract: .omnius/debug-library/CONTRACT.md (exists)
- run_readme: .omnius/debug-library/runs/1783067649743-p1k5kq/README.md (exists)
- run_index: .omnius/debug-library/runs/1783067649743-p1k5kq/index.json (exists)
- run_events_jsonl: .omnius/debug-library/runs/1783067649743-p1k5kq/events.jsonl (exists)
- workboard_active: .omnius/workboards/1783067649743-p1k5kq/active.json (exists)
- workboard_events: .omnius/workboards/1783067649743-p1k5kq/events.jsonl (exists)
- context_dump_latest: .omnius/context-window-dumps/latest.json (exists)
- context_dump_index: .omnius/context-window-dumps/index.jsonl (exists)
- trajectory_log: .omnius/trajectories/trajectories.jsonl (exists)
- checkpoints_dir: .omnius/checkpoints (exists)
- phases_dir: .omnius/phases (exists)
- completion_ledgers_dir: .omnius/completion-ledgers (exists)

## Latest Events

- 2026-07-04T22:17:35.428Z turn 50 context_window_dump: context dump agent_turn | tokens~75701
- 2026-07-04T22:12:54.908Z turn 49 context_window_dump: context dump agent_turn | tokens~75701
- 2026-07-04T22:12:54.881Z turn 47 tool_result success: file_edit success | diagnoses=project-file-mutation
- 2026-07-04T22:12:00.872Z turn 48 context_window_dump: context dump agent_turn | tokens~75324 | required=use_cached_evidence | diagnoses=focus-supervisor-active
- 2026-07-04T22:12:00.845Z turn 46 tool_result success: file_read success | diagnoses=focus-supervisor-active
- 2026-07-04T22:11:08.133Z turn 47 context_window_dump: context dump agent_turn | tokens~74835 | required=use_cached_evidence | diagnoses=focus-supervisor-active
- 2026-07-04T22:11:08.106Z turn 45 tool_result success: file_read success | diagnoses=focus-supervisor-active
- 2026-07-04T22:10:18.647Z turn 46 context_window_dump: context dump agent_turn | tokens~74718 | required=use_cached_evidence | diagnoses=focus-supervisor-active
- 2026-07-04T22:10:18.624Z turn 44 tool_result success: file_read success | diagnoses=focus-supervisor-active
- 2026-07-04T22:09:30.216Z turn 45 context_window_dump: context dump agent_turn | tokens~74597 | required=use_cached_evidence | diagnoses=focus-supervisor-active
- 2026-07-04T22:09:30.193Z turn 43 tool_result success: grep_search success | diagnoses=focus-supervisor-active
- 2026-07-04T22:08:41.529Z turn 44 context_window_dump: context dump agent_turn | tokens~74261 | required=use_cached_evidence | diagnoses=focus-supervisor-active
- 2026-07-04T22:08:41.509Z turn 42 tool_result failure: shell failure | diagnoses=focus-supervisor-active,tool-failure | command=cd /home/roko/Documents/Projects/myactuator/firmware/esp32 && pio run 2>&1 | tail -100
- 2026-07-04T22:07:41.730Z turn 43 context_window_dump: context dump agent_turn | tokens~73975
- 2026-07-04T22:07:41.706Z turn 41 tool_result success: shell success | command=cd /home/roko/Documents/Projects/myactuator/firmware/esp32 && pio lib list 2>&1
- 2026-07-04T22:06:48.501Z turn 42 context_window_dump: context dump agent_turn | tokens~73725
- 2026-07-04T22:06:01.576Z turn 41 context_window_dump: context dump agent_turn | tokens~73618
- 2026-07-04T22:06:01.450Z turn 39 tool_result success: shell success | diagnoses=shell-filesystem-mutation | command=cd /home/roko/Documents/Projects/myactuator/firmware/esp32 && pio lib install "ArduinoJson" 2>&1
- 2026-07-04T22:06:00.308Z turn 39 tool_result success: shell success | diagnoses=shell-filesystem-mutation | command=cd /home/roko/Documents/Projects/myactuator/firmware/esp32 && pio lib install "MCP2515" 2>&1
- 2026-07-04T22:05:09.688Z turn 40 context_window_dump: context dump agent_turn | tokens~72488
- 2026-07-04T22:05:09.658Z turn 38 tool_result success: shell success | diagnoses=shell-filesystem-mutation | command=cd /home/roko/Documents/Projects/myactuator/firmware/esp32 && pio lib install "ArduinoJson" 2>&1
- 2026-07-04T22:04:18.225Z turn 39 context_window_dump: context dump agent_turn | tokens~72025
- 2026-07-04T22:03:29.349Z turn 38 context_window_dump: context dump agent_turn | tokens~73476 | required=use_cached_evidence | diagnoses=focus-supervisor-active
- 2026-07-04T22:03:29.328Z turn 36 tool_result success: file_read success | diagnoses=focus-supervisor-active
- 2026-07-04T22:02:40.318Z turn 37 context_window_dump: context dump agent_turn | tokens~73301 | required=use_cached_evidence | diagnoses=focus-supervisor-active
- 2026-07-04T22:02:40.299Z turn 35 tool_result success: file_read success | diagnoses=focus-supervisor-active
- 2026-07-04T22:02:40.124Z turn 35 tool_result success: file_read success | diagnoses=focus-supervisor-active
- 2026-07-04T22:01:50.021Z turn 36 context_window_dump: context dump agent_turn | tokens~73084 | required=use_cached_evidence | diagnoses=focus-supervisor-active
- 2026-07-04T22:01:50.000Z turn 34 tool_result failure: shell failure | diagnoses=focus-supervisor-active,tool-failure | command=cd /home/roko/Documents/Projects/myactuator/firmware/esp32 && pio run 2>&1 | tail -50
- 2026-07-04T22:00:54.160Z turn 35 context_window_dump: context dump agent_turn | tokens~72724
- 2026-07-04T22:00:54.137Z turn 33 tool_result success: shell success | diagnoses=shell-filesystem-mutation | command=cd /home/roko/Documents/Projects/myactuator/firmware/esp32 && pio lib install "MCP2515" 2>&1
- 2026-07-04T22:00:04.867Z turn 34 context_window_dump: context dump agent_turn | tokens~72397
- 2026-07-04T22:00:04.845Z turn 32 tool_result success: file_patch success | diagnoses=project-file-mutation
- 2026-07-04T21:59:13.586Z turn 33 context_window_dump: context dump agent_turn | tokens~71316
- 2026-07-04T21:59:13.558Z turn 31 tool_result success: shell success | command=cd /home/roko/Documents/Projects/myactuator/firmware/esp32 && pio lib list 2>&1
- 2026-07-04T21:58:25.293Z turn 32 context_window_dump: context dump agent_turn | tokens~70486 | required=use_cached_evidence | diagnoses=focus-supervisor-active
- 2026-07-04T21:58:25.273Z turn 30 tool_result success: file_read success | diagnoses=focus-supervisor-active
- 2026-07-04T21:57:39.336Z turn 31 context_window_dump: context dump agent_turn | tokens~70211 | required=use_cached_evidence | diagnoses=focus-supervisor-active
- 2026-07-04T21:57:39.318Z turn 29 tool_result failure: shell failure | diagnoses=focus-supervisor-active,tool-failure | command=cd /home/roko/Documents/Projects/myactuator/firmware/esp32 && pio pkg install "MCP2515"
- 2026-07-04T21:56:51.259Z turn 30 context_window_dump: context dump agent_turn | tokens~69644
