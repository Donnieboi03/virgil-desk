# Observability

Append-only `~/.virgil-desk/logs/desk_events.jsonl`

```bash
desk-events --run-id desk_abc123
desk-events --run-id desk_abc123 --kind handoff.snapshot
desk-events --run-id desk_abc123 --summary
```

## Event envelope (all actions)

Every host-emitted event uses the same schema via `record()`:

| Section | Role |
|---------|------|
| `run_id`, `ts`, `kind` | Identity |
| `limits` | Config in effect at event time (`browser`, `host`, `hermes`, `prompts`) — **facts, not root cause** |
| `measure` | Numeric / size measurements for this action |
| `flags` | Boolean facts (e.g. `ok`, `live`, `scrape_text_capped`) |
| *(top-level)* | Action-specific detail (`item_id`, `command_id`, `error`, …) |

**Do not treat `limits` or `flags` as explanations.** They make runs comparable. A low `measure.item_count` is not automatically a cap problem — check whether relevant `flags.*_capped` are true and compare `limits` across `run_id`s.

High-frequency `browser.command` / `browser.command_result` omit `limits` (still present on `handoff.started` and other lifecycle events for the run).

## Event kinds

`handoff.started`, `handoff.snapshot`, `handoff.decomposed`, `handoff.decompose_failed`, `agent.execute_started`, `agent.executed`, `agent.execute_failed`, `item.completed`, `board.patch_dropped`, `browser.command`, `browser.command_result`, `proposal.accepted`, `proposal.denied`, `run.finished`, `policy.denied`

## Examples

### `handoff.snapshot`

`measure`: `excerpt_chars`, `scrape_text_chars`, `full_text_chars`, `link_count`, `full_link_count`, `scroll_loops_executed`, …

`flags`: `has_screenshot`, `scrape_text_capped`, `handoff_excerpt_capped`, `links_capped`

### `handoff.decomposed`

`measure.item_count`, `flags.live`, detail `backend`

### `browser.command_result`

`measure.duration_ms`, `measure.scrape_bytes`, `flags.ok`, `flags.has_screenshot`

### `policy.denied`

detail `rule`, `op`; optional `measure.count` for caps

Compare two runs after changing [`config/desk.yaml`](../config/desk.yaml) — limits on lifecycle events show what was in effect; measures/flags show what happened.
