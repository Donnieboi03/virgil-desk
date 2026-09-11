# Testing

| Layer | Command |
|-------|---------|
| Protocol | `npm run test -w @virgil-desk/protocol` |
| Extension unit | `npm run test -w @virgil-desk/extension` |
| Host unit + integration | `npm run test:host` |
| Park resume / URL-first | Host: auth_gate complete → `cleared_gates` + resume Packet; policy openTab URL required; Eyes challenge settle in extension vitest |
| **E2E (mock extension)** | `npm run test:e2e` |
| **Playwright (extension load + handoff smoke)** | `npm run test:playwright` |
| **All** (incl. Playwright) | `npm run test:all` |

## Mock WebSocket E2E

`npm run test:e2e` uses `packages/host/tests/helpers/mock_extension.py` to simulate the Chrome extension: handoff → board patch → `POST /v1/browser` wait → `command_result` with screenshot.

## Playwright

See [`packages/e2e/playwright/README.md`](../packages/e2e/playwright/README.md). Loads unpacked extension in headed Chromium:

- Smoke handoff (`example.com`)
- Form fixture Eyes/Hands (`tests/manual/path_b_smoke.html`)
- Public-page observe
- Optional live Gmail/LinkedIn: `DESK_E2E_LIVE=1` (not CI)

Local headed:

```bash
npm run build -w @virgil-desk/extension
pip install -e packages/host[dev]
cd packages/e2e/playwright && npm install && npx playwright install chromium
npm run test:headed
```

## Feasibility battery

Pass / Partial / Fail grid for Hands + park honesty: [`FEASIBILITY.md`](FEASIBILITY.md). CI covers fixture form/observe/handoff; Gmail draft and vault upload remain manual until stable.

## Hermes decompose + execute (manual)

With `DESK_AGENT_BACKEND=hermes`, hand off a real tab and verify board titles differ from stub. Click **Run agent** and confirm `browser.command` events. See [`HERMES_SETUP.md`](HERMES_SETUP.md) and [`tests/manual/hermes_execute_checklist.md`](../tests/manual/hermes_execute_checklist.md).

Compare runs:

```bash
desk-events --run-id desk_abc --summary
desk-events --run-id desk_xyz --kind handoff.decomposed
```

Milestone gates require tests green before commit.
