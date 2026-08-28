# Testing

| Layer | Command |
|-------|---------|
| Protocol | `npm run test -w @virgil-desk/protocol` |
| Extension unit | `npm run test -w @virgil-desk/extension` |
| Host unit + integration | `npm run test:host` |
| **E2E (mock extension)** | `npm run test:e2e` |
| **Playwright (extension load + handoff smoke)** | `npm run test:playwright` |
| **All** | `npm run test:all` |

## Mock WebSocket E2E

`npm run test:e2e` uses `packages/host/tests/helpers/mock_extension.py` to simulate the Chrome extension: handoff → board patch → `POST /v1/browser` wait → `command_result` with screenshot.

## Playwright

See [`packages/e2e/playwright/README.md`](../packages/e2e/playwright/README.md). Loads unpacked extension in headed Chromium and POSTs a REST handoff against a test Host on port 8799.

Local headed:

```bash
npm run build -w @virgil-desk/extension
pip install -e packages/host[dev]
cd packages/e2e/playwright && npm install && npx playwright install chromium
npm run test:headed
```

## Hermes decompose (manual)

With `DESK_AGENT_BACKEND=hermes`, hand off a real tab and verify board titles differ from stub. See [`HERMES_SETUP.md`](HERMES_SETUP.md).

Compare runs:

```bash
desk-events --run-id desk_abc --summary
desk-events --run-id desk_xyz --kind handoff.decomposed
```

Milestone gates require tests green before commit.
