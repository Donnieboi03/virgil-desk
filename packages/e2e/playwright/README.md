# Playwright extension E2E

Headed Chromium loads the unpacked extension and runs Host + Eyes/Hands smokes.

## Prerequisites

```bash
npm run build -w @virgil-desk/extension
pip install -e packages/host[dev]
cd packages/e2e/playwright && npm install
npx playwright install chromium
```

## Run (CI / anonymous)

```bash
# From repo root (uses xvfb on Linux CI)
npm run test:playwright

# Local headed (macOS)
cd packages/e2e/playwright && npm run test:headed
```

Coverage:

| Spec | What |
|------|------|
| `smoke.spec.ts` | Extension load + REST handoff on example.com |
| `form.spec.ts` | Local `path_b_smoke.html` — observe, fill, click, probe_form, vault upload |
| `public.spec.ts` | Public `example.com` — observe returns url without crash |
| `live.spec.ts` | **Skipped** unless `DESK_E2E_LIVE=1` |

Product feasibility Pass/Fail grid (forms, draft, upload, notify): [`docs/FEASIBILITY.md`](../../../docs/FEASIBILITY.md).

Playwright uses port **8799** for the test Host (avoid clashing with a dev server on 8787). Workers are serialized (`workers: 1`) so one Host binds that port.

Extension-only browser automation is limited in headless mode — CI runs with `xvfb-run` when available.

## Live sites (local opt-in)

Log into Gmail (and optionally LinkedIn) once in the persistent profile, then:

```bash
DESK_E2E_LIVE=1 npm run test:playwright -- live.spec.ts
```

Profile dir: `packages/e2e/playwright/.pw-user-data-live` (gitignored). Asserts null-safe scrape / observe — **no send**.
