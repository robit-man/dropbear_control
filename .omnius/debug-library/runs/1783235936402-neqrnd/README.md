# Debug Run 1783235936402-neqrnd

Updated: 2026-07-05T07:23:52.435Z
Workspace: /home/roko/Documents/Projects/myactuator

## Summary

- events: 11
- tool events: 7
- context dumps: 4
- failures: 1
- mutations: 0
- shell mutations: 0
- focus blocks: 0
- suspicious shell events: 0

## Diagnoses

- focus-supervisor-active: 9
- tool-failure: 1

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

- 2026-07-05T07:23:52.435Z turn 3 context_window_dump: context dump agent_turn | tokens~39811 | required=use_cached_evidence | diagnoses=focus-supervisor-active
- 2026-07-05T07:23:52.424Z turn 1 tool_result success: file_read success | diagnoses=focus-supervisor-active
- 2026-07-05T07:23:52.060Z turn 1 tool_result success: file_read success | diagnoses=focus-supervisor-active
- 2026-07-05T07:22:52.421Z turn 1 tool_result success: file_read success | diagnoses=focus-supervisor-active
- 2026-07-05T07:21:30.156Z turn 2 context_window_dump: context dump agent_turn | tokens~37896 | required=use_cached_evidence | diagnoses=focus-supervisor-active
- 2026-07-05T07:21:30.145Z turn 0 tool_result success: memory_search success | diagnoses=focus-supervisor-active
- 2026-07-05T07:21:30.025Z turn 0 tool_result success: file_read success | diagnoses=focus-supervisor-active
- 2026-07-05T07:20:09.883Z turn 1 context_window_dump: context dump agent_turn | tokens~36086 | required=use_cached_evidence | diagnoses=focus-supervisor-active
- 2026-07-05T07:20:09.875Z turn 0 tool_result failure: shell failure | diagnoses=focus-supervisor-active,tool-failure | command=git log --oneline -20
- 2026-07-05T07:20:09.689Z turn 0 tool_result success: shell success | command=git status
- 2026-07-05T07:18:59.440Z turn 0 context_window_dump: context dump agent_turn | tokens~33204
