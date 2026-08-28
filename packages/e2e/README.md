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

Helper: `packages/host/tests/helpers/mock_extension.py`

## Manual Chrome checklist (M2+)

See items 1–9 in the plan manual validation section — run after loading `packages/extension/dist` unpacked.

Playwright against a real unpacked extension is deferred to nightly CI.
