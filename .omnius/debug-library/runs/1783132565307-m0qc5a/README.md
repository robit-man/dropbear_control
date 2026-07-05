# Debug Run 1783132565307-m0qc5a

Updated: 2026-07-04T03:11:05.538Z
Workspace: /home/roko/Documents/Projects/myactuator

## Summary

- events: 85
- tool events: 22
- context dumps: 63
- failures: 19
- mutations: 1
- shell mutations: 0
- focus blocks: 4
- suspicious shell events: 0

## Diagnoses

- focus-supervisor-active: 35
- tool-failure: 19
- focus-supervisor-block: 4
- focus-supervisor-cached-evidence: 2
- project-file-mutation: 1

## Anchors

- debug_contract: .omnius/debug-library/CONTRACT.md (exists)
- run_readme: .omnius/debug-library/runs/1783132565307-m0qc5a/README.md (exists)
- run_index: .omnius/debug-library/runs/1783132565307-m0qc5a/index.json (exists)
- run_events_jsonl: .omnius/debug-library/runs/1783132565307-m0qc5a/events.jsonl (exists)
- workboard_active: .omnius/workboards/1783132565307-m0qc5a/active.json (exists)
- workboard_events: .omnius/workboards/1783132565307-m0qc5a/events.jsonl (exists)
- context_dump_latest: .omnius/context-window-dumps/latest.json (exists)
- context_dump_index: .omnius/context-window-dumps/index.jsonl (exists)
- trajectory_log: .omnius/trajectories/trajectories.jsonl (exists)
- checkpoints_dir: .omnius/checkpoints (exists)
- phases_dir: .omnius/phases (exists)
- completion_ledgers_dir: .omnius/completion-ledgers (exists)

## Latest Events

- 2026-07-04T03:11:05.537Z turn 0 context_window_dump: context dump agent_turn | tokens~16409
- 2026-07-04T03:11:05.380Z turn 33 context_window_dump: context dump agent_turn | tokens~71774 | required=read_authoritative_target | diagnoses=focus-supervisor-active
- 2026-07-04T03:11:05.345Z turn 31 tool_result failure: file_edit failure | diagnoses=focus-supervisor-active,tool-failure
- 2026-07-04T03:09:35.573Z turn 0 context_window_dump: context dump agent_turn | tokens~16418
- 2026-07-04T03:09:35.324Z turn 32 context_window_dump: context dump agent_turn | tokens~70619
- 2026-07-04T03:09:35.287Z turn 30 tool_result success: file_read success | diagnoses=focus-supervisor-cached-evidence
- 2026-07-04T03:08:21.187Z turn 0 context_window_dump: context dump agent_turn | tokens~16409
- 2026-07-04T03:08:21.070Z turn 31 context_window_dump: context dump agent_turn | tokens~69978 | required=read_authoritative_target | diagnoses=focus-supervisor-active
- 2026-07-04T03:08:21.045Z turn 29 tool_result failure: file_edit failure | diagnoses=focus-supervisor-active,tool-failure
- 2026-07-04T03:07:19.598Z turn 0 context_window_dump: context dump agent_turn | tokens~16419
- 2026-07-04T03:07:19.469Z turn 30 context_window_dump: context dump agent_turn | tokens~68253
- 2026-07-04T03:05:56.455Z turn 0 context_window_dump: context dump agent_turn | tokens~16419
- 2026-07-04T03:05:56.221Z turn 29 context_window_dump: context dump agent_turn | tokens~67909 | required=read_authoritative_target | diagnoses=focus-supervisor-active
- 2026-07-04T03:05:56.196Z turn 27 tool_result failure: file_write failure | diagnoses=focus-supervisor-active,focus-supervisor-block,tool-failure
- 2026-07-04T03:04:24.578Z turn 0 context_window_dump: context dump agent_turn | tokens~16419
- 2026-07-04T03:04:24.344Z turn 28 context_window_dump: context dump agent_turn | tokens~65680 | required=read_authoritative_target | diagnoses=focus-supervisor-active
- 2026-07-04T03:04:24.315Z turn 26 tool_result failure: file_patch failure | diagnoses=focus-supervisor-active,tool-failure
- 2026-07-04T03:02:58.451Z turn 0 context_window_dump: context dump agent_turn | tokens~16419
- 2026-07-04T03:02:58.216Z turn 27 context_window_dump: context dump agent_turn | tokens~65273 | required=read_authoritative_target | diagnoses=focus-supervisor-active
- 2026-07-04T03:02:58.191Z turn 25 tool_result failure: file_patch failure | diagnoses=focus-supervisor-active,tool-failure
- 2026-07-04T03:01:24.666Z turn 0 context_window_dump: context dump agent_turn | tokens~16419
- 2026-07-04T03:01:24.551Z turn 26 context_window_dump: context dump agent_turn | tokens~64798 | required=read_authoritative_target | diagnoses=focus-supervisor-active
- 2026-07-04T03:01:24.520Z turn 24 tool_result failure: file_edit failure | diagnoses=focus-supervisor-active,tool-failure
- 2026-07-04T03:00:02.255Z turn 0 context_window_dump: context dump agent_turn | tokens~16418
- 2026-07-04T03:00:02.133Z turn 25 context_window_dump: context dump agent_turn | tokens~63405 | required=read_authoritative_target | diagnoses=focus-supervisor-active
- 2026-07-04T03:00:02.111Z turn 23 tool_result failure: file_edit failure | diagnoses=focus-supervisor-active,tool-failure
- 2026-07-04T02:58:42.035Z turn 0 context_window_dump: context dump agent_turn | tokens~16418
- 2026-07-04T02:58:41.850Z turn 24 context_window_dump: context dump agent_turn | tokens~62356 | required=read_authoritative_target | diagnoses=focus-supervisor-active
- 2026-07-04T02:58:41.817Z turn 22 tool_result failure: file_edit failure | diagnoses=focus-supervisor-active,tool-failure
- 2026-07-04T02:57:22.455Z turn 0 context_window_dump: context dump agent_turn | tokens~16418
- 2026-07-04T02:57:22.223Z turn 23 context_window_dump: context dump agent_turn | tokens~61017 | required=read_authoritative_target | diagnoses=focus-supervisor-active,focus-supervisor-block
- 2026-07-04T02:56:38.978Z turn 0 context_window_dump: context dump brute_force_turn | tokens~16609
- 2026-07-04T02:56:30.166Z turn 0 context_window_dump: context dump agent_turn | tokens~16418
- 2026-07-04T02:56:30.040Z turn 22 context_window_dump: context dump agent_turn | tokens~59596 | required=read_authoritative_target | diagnoses=focus-supervisor-active
- 2026-07-04T02:56:30.017Z turn 20 tool_result failure: file_edit failure | diagnoses=focus-supervisor-active,tool-failure
- 2026-07-04T02:55:10.582Z turn 0 context_window_dump: context dump agent_turn | tokens~16418
- 2026-07-04T02:55:10.351Z turn 21 context_window_dump: context dump agent_turn | tokens~57992 | required=read_authoritative_target | diagnoses=focus-supervisor-active,focus-supervisor-block
- 2026-07-04T02:54:22.177Z turn 0 context_window_dump: context dump agent_turn | tokens~16418
- 2026-07-04T02:54:22.050Z turn 20 context_window_dump: context dump agent_turn | tokens~57559 | required=read_authoritative_target | diagnoses=focus-supervisor-active
- 2026-07-04T02:54:22.025Z turn 18 tool_result failure: file_edit failure | diagnoses=focus-supervisor-active,tool-failure
