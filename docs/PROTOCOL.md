# Protocol

See `packages/protocol/src/index.ts` for TypeScript types.

## REST

- `GET /v1/health`
- `GET /v1/config`
- `POST /v1/handoff` — bounded intake (`url` required); accepts client `run_id`, `agent_tab_id`, `snapshot.screenshot`
- `POST /v1/browser` — browser op (optional `wait: true`)
- `POST /v1/items/{id}/execute` — run Agent column item (`body: { run_id }`)
- `POST /v1/items/{id}/complete` — mark You column item done
- `POST /v1/items/{id}/accept` — commit proposal
- `POST /v1/items/{id}/deny` — reject proposal

## WebSocket `WS /v1/extension`

Extension → Host: `register`, `handoff_started`, `command_result`, `item_ack`

Host → Extension: `board_patch`, `browser_command`, `run_finished`, `error`

## BrowserOp

`captureHandoffSnapshot`, `openTab`, `duplicateTab`, `closeTab`, `scroll`, `scrape`, `screenshot`, `click`, `fill`, `wait`, `focusTab`

## command_result

Required: `command_id`, `ok`, `duration_ms`. Include `scrape_excerpt` and `screenshot` after actions.

Host auto-chains scrape + screenshot after `click` / `fill`.
