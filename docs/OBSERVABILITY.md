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

`handoff.started`, `handoff.snapshot`, `handoff.decomposed`, `handoff.decompose_failed`, `agent.execute_started`, `agent.executed`, `agent.execute_failed`, `item.minted`, `item.completed`, `tab.custody`, `board.patch_dropped`, `browser.command`, `browser.command_result`, `execute.cleanup_done`, `proposal.accepted`, `proposal.denied`, `run.finished`, `policy.denied`, `memory.semantic_patched`

### Eyes / Done measurement

| Signal | Where | Use |
|--------|-------|-----|
| `eyes_mode`, `eyes_empty` | `browser.command_result` flags | Ladder coverage |
| `eyes_settle_ms`, `eyes_settle_attempts` | measure | Settle budget health |
| `challenge_extended` | `browser.command_result` flags | Settle used challenge +extra once |
| `inject_ms`, `frame_count` | `browser.command_result` measure | Interact-bundle inject cost / allFrames count |
| `eyes_hints` | detail | Soft URL hints when mode 2 |
| `agent.executed` + `flags.awaiting_human` | execute | Auth gate halt; `preserve_tabs` soft-ends session (tab kept for Show) |
| `agent.resume_ready` | complete You | Parent unblocked for Resume; may include `has_viewport_shot` / `shot_on_agent_tab` |
| `tab.custody` | extension park/reveal | `flags.action` park\|reveal; `has_viewport_shot`; optional `shot_skipped_inactive` |
| `item.completed` | Mark done | Optional `viewport_shot_bytes` / `shot_on_agent_tab` when human still on agent tab |
| `policy.denied` `human_park_tab_denied` / `open_tab_url_required` | browser | Bad park / blank openTab |
| `agent.execute_failed` 409-class detail | execute lock | Double-run attempts (HTTP 409) |
| `semantic_fact_count` / `has_semantic_facts` | `agent.execute_started` measure/flags | Packet semantic inject size (Desk memory, not Hermes RAG) |
| `memory.semantic_patched` | REST PATCH | `op` upsert/delete; `measure.semantic_fact_count` after patch |

`limits` on lifecycle events now include the `memory` section from [`config/desk.yaml`](../config/desk.yaml) (recent/notepad/semantic caps). Map: [`MEMORY.md`](MEMORY.md).

Framework narrative: [`ARCHITECTURE.md`](ARCHITECTURE.md).

## Examples

### `handoff.snapshot`

`measure`: `excerpt_chars`, `scrape_text_chars`, `full_text_chars`, `link_count`, `full_link_count`, `scroll_loops_executed`, …

`flags`: `has_screenshot`, `scrape_text_capped`, `handoff_excerpt_capped`, `links_capped`

### `handoff.decomposed`

`measure.item_count`, optional usage (`prompt_tokens` / `completion_tokens` / `total_tokens` / `cost_usd` when the backend exposes them), `flags.live`, detail `backend`

### `agent.executed` / `agent.execute_failed` / `run.finished`

Optional usage fields on `measure` when present — never required; missing usage does not fail the run. Hermes execute usage is best-effort from `DESK_USAGE:` stdout, session JSON, or profile `state.db` `sessions` (`input_tokens`/`output_tokens`/`actual|estimated_cost_usd`).

### `browser.command_result`

`measure`: `duration_ms`, `scrape_bytes`, `target_count`, optional `eyes_settle_ms` / `eyes_settle_attempts` / `inject_ms` / `frame_count`, …

`flags`: `ok`, `has_screenshot`, `has_interact_targets`, optional `eyes_empty` / `eyes_mode` / `challenge_extended` (harness adds `driver: harness`)

Top-level detail: `command_id`, `op`, `act_resolved`, and when present **`error`**, **`tab_id`**, **`url`**.

`desk-events --run-id … --summary` includes `failed_command_count` and up to 20 `failed_ops` (`op`/`error`/`tab_id`/`url`). When any event carried usage, summary also rolls up `prompt_tokens` / `completion_tokens` / `total_tokens` / `cost_usd` (omit keys that are zero/absent).

Per-item EXT/GAP (when execute windows exist): `items[]` with `wall_ms`, `ext_ms` (Σ `duration_ms` on `browser.command_result`), `gap_ms_sum` / `gap_first_ms` / `gap_later_avg` (result → next `browser.command`), `residual_ms`, `op_ext` (per-op duration + optional inject/frame), optional per-item `usage`. Run skew: `ext_ms_max` / `ext_ms_min` / `ext_ms_median` / `ext_ms_max_item_id`. Summary with `--run-id` reads up to 100k events so windows are not truncated at the default 100-line limit.

### `execute.cleanup_done`

After agent execute cleanup: `item_id`, `closed_tab_ids`, `measure.closed_tab_count`.

### `policy.denied`

detail `rule`, `op`; optional `measure.count` for caps

Compare two runs after changing [`config/desk.yaml`](../config/desk.yaml) — limits on lifecycle events show what was in effect; measures/flags show what happened.
