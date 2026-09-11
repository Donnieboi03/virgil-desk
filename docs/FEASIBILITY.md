# Feasibility battery

Scored **Pass / Partial / Fail / N/A** checks for Eyes/Hands honesty against the north star (park/Resume + Hands claims). Effort band ~6–9h with AI.

Run automated rows in CI where marked; capture manual F-grid notes under this file or chat after dogfood.

| ID | Surface | Expect | Automate | Status |
|----|---------|--------|----------|--------|
| F1 | Fixture form fill by `target_id` | Pass | Playwright `form.spec.ts` | **Pass (CI)** |
| F2 | Fixture click button | Pass | Playwright `form.spec.ts` | **Pass (CI)** |
| F3 | Fixture `probe_form` | Pass | Playwright `form.spec.ts` | **Pass (CI)** |
| F4 | Public page observe (url) | Pass | Playwright `public.spec.ts` | **Pass (CI)** |
| F5 | Handoff → board patch | Pass | Playwright `smoke.spec.ts` + e2e mock WS | **Pass (CI)** |
| F6 | Auth gate → You park → Mark done → Resume | Pass | Host unit park/resume | **Pass (CI)** |
| F7 | Gmail draft-only (no send) | Partial if draft opens; Fail if send | Manual `DESK_E2E_LIVE=1` | Manual (login) |
| F8 | Forbidden send/submit/pay token | Pass (policy deny) | Host unit `test_policy.py` | **Pass (CI)** |
| F9 | Upload missing vault id | Fail | Playwright `form.spec.ts` | **Pass (CI)** |
| F10 | Upload with vault file + `kind:file` | Pass (`upload`) | Playwright `form.spec.ts` | **Pass (CI)** |
| F11 | String `fill` on file input | Fail (documented) | N/A — do not claim | Doc |
| F12 | Waiting Accept calendar | Pass (done, **no** agent tab) | Host `test_accept.py` | **Pass (CI)** |
| F13 | Waiting Accept non-calendar UI | Pass (move to Agent + `needs_agent_tab`) | Host `test_accept_ui_proposal_moves_to_agent_column` | **Pass (CI)** |
| F14 | Notify on You `awaiting_human` (not plain proposed) | Pass | Extension `boardNotify` unit | **Pass (CI)** |
| F15 | Auto Run tab after decompose | Pass when `auto_run_tab` + `host_loop` | Manual dogfood | Manual |

## How to score

- **Pass** — behavior matches claim without human reconstructing chat state.
- **Partial** — works with caveats (live login, flaky SPA, draft-only).
- **Fail** — Hands/park claim is false; fix or stop claiming.
- **N/A** — surface not in scope (e.g. unattended pay).

## Commands

```bash
npm run test -w @virgil-desk/extension
npm run test:host
npm run test:e2e
npm run test:playwright   # form.spec includes F1–F3 + F9–F10
```

Still manual: **F7** (needs logged-in Gmail profile + `DESK_E2E_LIVE=1`), **F15** (flagged auto-run dogfood with OpenRouter).

Upload Options UI dogfood remains useful beyond CI: Options → Document vault → add PDF.
