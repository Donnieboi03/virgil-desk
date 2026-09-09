# Browser layer

Eyes vs Hands taxonomy (DOM / CDP Input / OS — archive reference): [`archive/INTERACTION_LAYERS.md`](archive/INTERACTION_LAYERS.md).

Virgil Desk can drive Chrome two ways. **Handoff / board / decompose** always use the **MV3 extension**. **Execute** (`desk-browser` / `POST /v1/browser`) follows `browser.driver` in [`config/desk.yaml`](../config/desk.yaml).

| `browser.driver` | Execute path | Cookies | Operator setup |
|------------------|--------------|---------|----------------|
| **`extension` (default / Path B)** | Host → extension WS → `scripting` (no CDP) | Same profile (agent tab duplicate) | Extension side panel connected |
| **`harness` (rollback)** | Host → `browser-harness` CDP (everyday Chrome) | Everyday Chrome profile | `chrome://inspect/#remote-debugging` Allow + Chrome 144+ Allow popup |

Harness daemon isolation: `BU_NAME=virgil-desk` (never Virgil tick `:9223` / `BU_CDP_URL` to chrome-virgil). Rollback: set `browser.driver: harness` or `DESK_BROWSER_DRIVER=harness`.

## Path B execute (extension default)

Eyes channels (no vision / screenshot by default):

| Channel | When | Hermes sees |
|---------|------|-------------|
| Slim WebMarker targets | every `observe` | `{id, ref, kind, label, frame_id?}` (max 40; conversation rows prioritized) |
| Default excerpt | settle ready | capped `body.innerText` (`eyes_mode: 0`) |
| Escalation deep text + AX `page_tree` | fail-only when T0 empty | promoted into `scrape_excerpt` (`eyes_mode: 1`); tree also kept when URL change / empty |
| Soft URL hints | still empty after escalate | `eyes_mode: 2`, `eyes_empty: true`, optional `eyes_hints.url_path_hint` |
| Probes | on demand | `probe_form` / `probe_links` / `probe_table` |

- Hands: **`target_id`** only (coords kept in extension `targetMap`, stripped from CLI).
- Execute observe defaults `skip_screenshot: true` (`observe_skip_screenshot_default`) — no `captureVisibleTab` tab flicker.
- Same-URL follow-up observe: `text_omitted` + no `page_tree` when content unchanged; keep slim targets. Mode-1 promote forces a non-omitted excerpt.
- **Eyes settle (fast):** after open/scrape/observe, poll until excerpt/targets ready or `eyes_settle_budget_ms` (default 2s, poll 250ms). Happy path exits on first scrape. Empty first scrape does **not** lock omit baseline. If scrape looks like a **challenge** (Cloudflare / Just a moment / checking your browser), extend once by `eyes_challenge_extra_ms` (default 8s) before giving up. Still-empty → one-shot deep text (`eyes_deep_text_max_chars`) + forced DIY `page_tree` → promote or soft hints (no screenshot / no tab focus).

**Desk defaults**

| Phase | Eyes | Hands | Driver |
|-------|------|-------|--------|
| Handoff / decompose | Extension scrape + screenshot | — | Extension |
| Execute (default / Path B) | slim targets + optional `page_tree` + excerpt omit | DOM `target_id` | `browser.driver: extension` |
| Execute (rollback) | dims / scrape; empty targets | CDP Input (`x,y` / selector) | `browser.driver: harness` |

**`eyes_mode` is not soft site tiers A–D** (those remain expectation-only below). Ladder SoT is this file; Done/park: [`ARCHITECTURE.md`](ARCHITECTURE.md).

Implementation: [WebMarker](https://github.com/reidbarber/webmarker) + `deskDeepText` / `deskPageTree` / probes in `interactObserve.bundle.js`. `allFrames: true` stamps `frame_id`; act uses `frameIds`.

## Harness execute (rollback)

- Sticky CDP **target per `run_id`**.
- Eyes: `page_info` + screenshot dims; `interact_targets` empty — `{x,y}` or CSS `selector`.
- Hands: CDP `Input.dispatchMouseEvent`.
- Events include `driver: harness`.

Confirm attach: `BU_NAME=virgil-desk browser-harness --doctor` **without** pointing at `:9223`.

## Scrape vs screenshot (legacy)

| Mechanism | What you get |
|-----------|--------------|
| **Scrape** | Page `innerText`, link list, URL, title |
| **Screenshot** | Real viewport PNG (base64) — activates tab for `captureVisibleTab` |

Prefer **`observe`**. Handoff may still capture a PNG for decompose.

## Soft site tiers (expectation, not hard gates)

| Tier | Examples | Path B expectation |
|------|----------|-------------------|
| **A** | Docs, ordinary SaaS | DOM Eyes/Hands reliable |
| **B** | Gmail-class SPA | Friction OK; follow threads via `target_id`; drafts OK |
| **C** | LinkedIn-class anti-bot | Soft-help You (keywords/draft); **no** agent send/connect; URL may be workaround only |
| **D** | `chrome://`, extension pages | Inject impossible — park / Partial |

Forums: expect soft **A/B** until proven otherwise — do not hard-code forum tiers.

## Hand off

1. Extension mints `run_id`, **duplicateTab** as an **ungrouped** short-lived scrape tab (no Virgil · Agent yet)
2. Optional scroll loops on that snapshot tab
3. Scrape + screenshot, then **close** the snapshot tab
4. Host → Hermes decompose (board cards; **no** agent group / per-item tabs yet)

## Run agent

1. Operator clicks **Run agent** on one Agent root
2. Extension creates **Virgil · Agent** if needed, duplicates that item’s tab into the group, PATCHes `agent_tab_id`
3. Host starts execute with that tab

## Agent tab policy

- Agent work on `agent_tab_id` in **Virgil · Agent** group (provisioned at Run agent)
- Ops on `human_tab_id` blocked except `captureHandoffSnapshot`
- Navigation: duplicate same-origin, else open new agent tab

Playwright in `packages/e2e/playwright/` is **CI/E2E only**. Virgil Hub tick stays on isolated Chrome (`~/.chrome-virgil/*`).
