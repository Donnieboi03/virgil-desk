# Browser layer

Virgil Desk drives Chrome via the **MV3 extension** only: `tabs`, `tabGroups`, `scripting`, and `tabs.captureVisibleTab`.

## Scrape vs screenshot

| Mechanism | What you get |
|-----------|----------------|
| **Scrape** (`scripting.executeScript`) | Page `innerText`, link list, URL, title — text for decompose and thin-page checks |
| **Screenshot** (`captureVisibleTab`) | Real viewport PNG (base64) for visual verify |

Screenshot flow (brief tab flicker accepted):

1. Remember the human's active tab in the window
2. Activate the agent tab
3. Wait `browser.default_wait_ms` (from `GET /v1/config`)
4. `chrome.tabs.captureVisibleTab(windowId, { format: 'png' })`
5. Restore the prior active tab

Limits are loaded at WebSocket `register` and via `GET /v1/config`. Host enforces `screenshot_max_per_run` per `run_id`.

## Agent tab policy

- Agent work runs on `agent_tab_id` in the collapsed **Virgil · Agent** tab group
- Ops on `human_tab_id` are blocked except `captureHandoffSnapshot`
- Navigation: duplicate same-origin path, else open new agent tab

Playwright in `packages/e2e/playwright/` is **CI/E2E only** — not the runtime browser driver.
