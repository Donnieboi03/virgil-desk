# Observability

Append-only `~/.virgil-desk/logs/desk_events.jsonl`

```bash
desk-events --run-id desk_abc123
```

Events: `handoff.started`, `handoff.snapshot`, `handoff.decomposed`, `handoff.decompose_failed`, `agent.execute_started`, `agent.executed`, `agent.execute_failed`, `browser.command`, `browser.command_result`, `proposal.accepted`, `proposal.denied`, `run.finished`, `policy.denied`
