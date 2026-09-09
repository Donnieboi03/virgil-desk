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

`handoff.started`, `handoff.snapshot`, `handoff.decomposed`, `handoff.decompose_failed`, `agent.execute_started`, `agent.executed`, `agent.execute_failed`, `item.minted`, `item.completed`, `board.patch_dropped`, `browser.command`, `browser.command_result`, `execute.cleanup_done`, `proposal.accepted`, `proposal.denied`, `run.finished`, `policy.denied`

### Eyes / Done measurement

| Signal | Where | Use |
|--------|-------|-----|
| `eyes_mode`, `eyes_empty` | `browser.command_result` flags | Ladder coverage |
| `eyes_settle_ms`, `eyes_settle_attempts` | measure | Settle budget health |
| `eyes_hints` | detail | Soft URL hints when mode 2 |
| `item.minted` + `flags.idempotent_reuse` | mint | Deduped parks |
| `agent.executed` + `flags.awaiting_human` | execute | Auth gate halt |
| `agent.resume_ready` | complete You | Parent unblocked for Resume |
| `policy.denied` `human_park_tab_denied` | browser | Agent tried human park tab |
| `agent.execute_failed` 409-class detail | execute lock | Double-run attempts (HTTP 409) |

Framework narrative: [`ARCHITECTURE.md`](ARCHITECTURE.md).

## Examples

### `handoff.snapshot`

`measure`: `excerpt_chars`, `scrape_text_chars`, `full_text_chars`, `link_count`, `full_link_count`, `scroll_loops_executed`, …

`flags`: `has_screenshot`, `scrape_text_capped`, `handoff_excerpt_capped`, `links_capped`

### `handoff.decomposed`

`measure.item_count`, optional usage (`prompt_tokens` / `completion_tokens` / `total_tokens` / `cost_usd` when the backend exposes them), `flags.live`, detail `backend`

### `agent.executed` / `agent.execute_failed` / `run.finished`

Optional usage fields on `measure` when present — never required; missing usage does not fail the run.

### `browser.command_result`

`measure`: `duration_ms`, `scrape_bytes`, `target_count`, …

`flags`: `ok`, `has_screenshot`, `has_interact_targets` (harness adds `driver: harness`)

Top-level detail: `command_id`, `op`, `act_resolved`, and when present **`error`**, **`tab_id`**, **`url`**.

`desk-events --summary` includes `failed_command_count` and up to 20 `failed_ops` (`op`/`error`/`tab_id`/`url`). When any event carried usage, summary also rolls up `prompt_tokens` / `completion_tokens` / `total_tokens` / `cost_usd` (omit keys that are zero/absent).

### `execute.cleanup_done`

After agent execute cleanup: `item_id`, `closed_tab_ids`, `measure.closed_tab_count`.

### `policy.denied`

detail `rule`, `op`; optional `measure.count` for caps

Compare two runs after changing [`config/desk.yaml`](../config/desk.yaml) — limits on lifecycle events show what was in effect; measures/flags show what happened.
