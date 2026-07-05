# Omnius Debug Artifact Library Contract

Schema version: 1

Purpose: provide one stable, navigable location for run-level debugging evidence.
The library does not replace raw artifacts; it indexes and anchors them.

Directory layout:

```text
.omnius/debug-library/
  CONTRACT.md
  README.md
  index.json
  runs/<run-id>/
    README.md
    index.json
    events.jsonl
    events/turn-0000/<event-id>.json
```

Event contract:

- `tool_result` events summarize debug-relevant tool calls: shell calls, task-status calls, failures, mutations, focus-supervisor blocks, and suspicious command shapes.
- `context_window_dump` events summarize outbound model context dumps and their pressure/focus metrics.
- `anchors` are absolute and relative paths to the raw source artifacts that explain the event.
- `diagnoses` are runtime-authored labels. They are hints, not proof; use the anchored raw files for final diagnosis.

Important diagnosis labels:

- `shell-brace-whitespace`: a shell command used brace expansion containing whitespace, which can split an intended path set into unrelated shell words.
- `successful-command-needs-post-state-audit`: the command exited zero but its shape is risky enough that filesystem state should be inspected.
- `focus-supervisor-block`: the tool result or supervisor state shows an unsuccessful blocked next action.
- `focus-supervisor-cached-evidence`: the focus supervisor short-circuited a call successfully by reusing current cached evidence.
- `background-task-id-missing`: task status lookup could not find the spawned task id.
- `raw-discovery-dominates-context`: context-window metrics show low signal/noise around raw discovery output.
- `tool-result-binding-mismatch`: the outbound model transcript contains a tool result whose reported target does not match the assistant tool call it is attached to.
