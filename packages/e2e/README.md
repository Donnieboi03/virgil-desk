# E2E (mock extension)

Automated E2E simulates the Chrome extension over WebSocket — no headed Chrome required.

```bash
npm run test:e2e
```

Coverage:

1. WS handoff → board patch → `POST /v1/browser` (wait) → `command_result` with screenshot
2. `navigate` + same URL → `duplicateTab`; different URL → `openTab`
3. Calendar Accept after mock handoff
4. Hermes backend path with calendar proposal + browser verify
5. Handoff **without** `agent_tab_id` still decomposes (defer tabs until Run agent / PATCH)
6. `openTab` with `params.placement=human` forwarded to the extension
7. Host integration: `mint_item` board_patch + parent done blocked while agent children open (see `packages/host/tests/integration/test_execute_agent.py`)
8. `openTab` result includes `tab_id`; failed scrape logs `error`/`tab_id`; `closeTab` without `tab_id` rejected

Helper: `packages/host/tests/helpers/mock_extension.py`

## Manual Chrome checklist (M2+)

See [`docs/OPERATOR.md`](../../docs/OPERATOR.md) § Manual checklist — run after loading `packages/extension/dist` unpacked:

1. Handoff scrape-then-close (no per-task agent collage)
2. **Run agent** on one root → provisions that item only
3. Mid-run `mint_item` children appear under Agent accordion / You-Waiting columns
4. You child + `openTab` `placement=human` outside **Virgil · Agent**

Playwright smoke (`packages/e2e/playwright`) loads the unpacked extension in CI.
