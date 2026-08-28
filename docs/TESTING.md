# Testing

| Layer | Command |
|-------|---------|
| Protocol | `npm run test -w @virgil-desk/protocol` |
| Extension unit | `npm run test -w @virgil-desk/extension` |
| Host unit + integration | `npm run test:host` |
| **E2E (mock extension)** | `npm run test:e2e` |

E2E uses a mock WebSocket client (`packages/host/tests/helpers/mock_extension.py`) to simulate the Chrome extension: handoff → board patch → `POST /v1/browser` wait → `command_result` with screenshot.

Milestone gates require tests green before commit.
