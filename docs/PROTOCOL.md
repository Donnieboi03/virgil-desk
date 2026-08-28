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

## WebSocket `WS /v1/extension`

Extension → Host: `register`, `handoff_started`, `command_result`, `item_ack`, `memory_snapshot`, `browser_popup_closed`, `execute_cleanup_done`

Host → Extension: `registered` (includes `config`), `handoff_result`, `board_patch`, `browser_command`, `memory_get`, `memory_patch`, `execute_session`, `execute_cleanup`

Board mutations from execute/complete/accept/deny require an active WebSocket; otherwise Host returns **503**.

### Memory + tab lifecycle

- **`memory_get` / `memory_snapshot`**: host loads `virgil_desk_memory_v1` (recent executions + per-run notepad) before Hermes execute.
- **`memory_patch`**: seed notepad at handoff; append recent/bullets after execute.
- **`execute_session`**: marks the active item/tab so off-origin popups from the agent tab can be quarantined.
- **`execute_cleanup`**: closes that item’s agent tab + tracked spawn tabs (never the human tab).

## BrowserOp

`captureHandoffSnapshot`, `navigate` (host-normalized to `openTab` / `duplicateTab`), `openTab`, `duplicateTab`, `closeTab`, `scroll`, `scrape`, `screenshot`, **`observe`**, `click`, `fill`, **`key`**, `wait`, `focusTab`

### Params (selected)

| Op | Params |
|----|--------|
| `observe` | `{ "annotate": true }` — SoM overlay before screenshot (default from config) |
| `click` | `{ "target_id": 7 }` \| `{ "text": "..." }` \| `{ "x": 120, "y": 340 }` \| `{ "selector": "..." }` |
| `fill` | `{ "target_id": 3, "value": "..." }` |
| `scroll` | `{ "direction": "down" }` \| `{ "target_id": 12, "direction": "down" }` |
| `key` | `{ "key": "Enter" }` |

## command_result

Required: `command_id`, `ok`, `duration_ms`. **`observe`** adds `interact_targets`, `viewport`, `device_pixel_ratio`. Mutating ops add `act_resolved` and auto-chain `scrape_excerpt` + `screenshot`.

## WorkItem fields (runtime)

Items carry `run_id`, optional `agent_tab_id` / `human_tab_id`, `evidence` after execute, and `last_error` on failure.
