# Playwright extension E2E

Headed Chromium loads the unpacked extension and runs a Host handoff smoke test.

## Prerequisites

```bash
npm run build -w @virgil-desk/extension
pip install -e packages/host[dev]
cd packages/e2e/playwright && npm install
npx playwright install chromium
```

## Run

```bash
# From repo root (uses xvfb on Linux CI)
npm run test:playwright

# Local headed (macOS)
cd packages/e2e/playwright && npm run test:headed
```

Playwright uses port **8799** for the test Host to avoid clashing with a dev server on 8787.

Extension-only browser automation is limited in headless mode — CI runs with `xvfb-run` when available.
