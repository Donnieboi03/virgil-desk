# Protocol

See `packages/protocol/src/index.ts` for TypeScript types.

## REST

- `GET /v1/health` — includes `extension_connected`
- `GET /v1/config`
- `POST /v1/handoff` — bounded intake (`url` required); accepts client `run_id`, `agent_tab_id`, `snapshot.screenshot`
- `POST /v1/browser` — browser op (optional `wait: true`); **503** when extension disconnected
- `POST /v1/items/{id}/execute` — run Agent column item (`body: { run_id }`); requires extension; patches evidence on success
- `POST /v1/items/{id}/complete` — mark You column item done; requires extension
- `POST /v1/items/{id}/accept` — commit proposal; requires extension for board patch
- `POST /v1/items/{id}/deny` — reject proposal; requires extension for board patch
- `GET /v1/desk-memory/semantic` — semantic facts slice (`virgil_desk_semantic_v1`); requires extension
- `PATCH /v1/desk-memory/semantic` — `{ op: upsert_fact|delete_fact, … }` → extension `memory_patch`; requires extension

## WebSocket `WS /v1/extension`

Extension → Host: `register`, `handoff_started`, `command_result`, `item_ack`, `memory_snapshot`, `browser_popup_closed`, `execute_cleanup_done`

Host → Extension: `registered` (includes `config`), `handoff_result`, `board_patch`, `browser_command`, `memory_get`, `memory_patch`, `execute_session`, `execute_cleanup`

Board mutations from execute/complete/accept/deny require an active WebSocket; otherwise Host returns **503**.

### Memory + tab lifecycle

- **`memory_get` / `memory_snapshot`**: host loads `{ memory, semantic }` — `virgil_desk_memory_v1` (recent + notepad) and `virgil_desk_semantic_v1` (facts) — before Hermes execute. Packet gets `run_notepad`, `recent_executions`, `semantic_facts`. Full map: [`MEMORY.md`](MEMORY.md).
- **`memory_patch`**: `seed_run` / `append_recent` / `append_bullet` (working + episodic); `upsert_fact` / `delete_fact` (semantic).
- **`execute_session`**: marks the active item/tab so off-origin popups from the agent tab can be quarantined.
- **`execute_cleanup`**: closes that item’s agent tab + tracked spawn tabs (never the human tab).

## BrowserOp

`captureHandoffSnapshot`, `navigate` (host-normalized to `openTab`), `openTab` (agent placement only — `params.placement: human` is **denied**), `duplicateTab` (legacy alias → create), `closeTab`, `scroll`, `scrape`, `screenshot`, **`observe`**, **`probe_form`**, **`probe_links`**, **`probe_table`**, `click`, `fill`, **`key`**, `wait`, `focusTab`

Optional body field: `skip_screenshot` (extension observe defaults true via `observe_skip_screenshot_default`).

### Params (selected)

| Op | Params |
|----|--------|
| `observe` | `{ "annotate": true }` — SoM overlay (default from config) |
| `click` | `{ "target_id": 7 }` (extension primary) |
| `fill` | `{ "target_id": 3, "value": "..." }` |
| `scroll` | `{ "direction": "down" }` \| `{ "target_id": 12, "direction": "down" }` |
| `key` | `{ "key": "Enter" }` |
| `probe_*` | (none required) — form fields / links / table rows |

## command_result

Required: `command_id`, `ok`, `duration_ms`. **`observe`** adds slim `interact_targets`, optional `page_tree` (URL change or empty escalate), `viewport`, `device_pixel_ratio`. Mutating ops add `act_resolved`; post-act screenshots are skipped when extension skip-screenshot default is on.

Same-URL follow-up `observe` may set `text_omitted: true` and omit `page_tree` while keeping targets; URL changes get a capped follow-up excerpt (`browser.observe_followup_excerpt_max_chars`, default 2000). Full observe excerpt defaults to `browser.scrape_excerpt_max_chars` (4000); `page_tree` defaults to 2000 chars; deep escalate text defaults to `browser.eyes_deep_text_max_chars` (4000).

Eyes ladder fields on `command_result` (extension Eyes/Hands): **`eyes_mode`** (`0` default / `1` deep-text promote / `2` soft hints), **`eyes_empty`**, optional **`eyes_hints.url_path_hint`**, settle measures `eyes_settle_ms` / `eyes_settle_attempts`, optional **`challenge_extended`**, **`inject_ms`**, **`frame_count`**. Host also stamps mine-ready **`item_id`** / **`op_seq`** / optional **`site_fingerprint`** on `browser.command`(+result) — see [`OBSERVABILITY.md`](OBSERVABILITY.md). Ladder behavior: [`BROWSER_LAYER.md`](BROWSER_LAYER.md). Done/park/idempotency: [`ARCHITECTURE.md`](ARCHITECTURE.md).

**Mint** (`POST /v1/items/mint`): always creates a child (no host remint collapse). Resume continuity uses Packet `resume.cleared_gates`.

**Execute** (`POST /v1/items/{id}/execute`): concurrent second call → **409** while in progress (same item **or** another item on the same `run_id` — one active execute per run for browser obs stamping).

**`desk-browser` CLI** prints a thin Eyes/Hands envelope: screenshot **base64 stripped**; target geometry (`text`/`rect`/`center`) stripped to `{id,ref,kind,label,frame_id}`; `eyes_mode` / `eyes_hints` / settle flags pass through.

## Hermes models + hooks

- Decompose: `hermes.decompose_model` (default `google/gemini-3.7-flash`); no `--accept-hooks`.
- Execute: `hermes.execute_model` (default `google/gemini-3.7-flash`); `hermes.execute_accept_hooks: false` (single-agent `terminal` + `skills` + desk-browser — no compound-topology hooks).
- Execute tool-loop cap: `hermes.execute_max_turns` (default `40`) → Hermes `--max-turns` (decompose does not set it).

## WorkItem fields (runtime)

Items carry `run_id`, optional `agent_tab_id` / `human_tab_id`, optional **`hints`** (`search_query`, `sender`, `subject_contains`, optional **`members[]`** of `{sender, subject_contains}` for pattern-class clumps), optional **`parent_id`** / **`kind`** (`parent` | `subtask`) for mid-flight children, optional **`park_kind`** (`auth_gate` | `human_remainder`) / **`resume`** / **`resume_ready`**, status including **`awaiting_human`**, `evidence` after execute, and `last_error` on failure (Hermes failures prefer stderr / API snippets over a bare `session_id` line). Decompose coerces agent status to `proposed` (execute owns `done` / `awaiting_human`). Host **`POST /v1/items/mint`** (CLI: `desk-browser --op mint_item`) adds children; parent `done` is blocked while agent children are `proposed`/`running`. Auth-gate You Mark done → parent `proposed` + `resume_parent_id`. Done/park framework: [`ARCHITECTURE.md`](ARCHITECTURE.md).
