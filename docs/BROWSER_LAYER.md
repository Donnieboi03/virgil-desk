# Browser layer

Eyes vs Hands (DOM / CDP Input / OS), costs, and dual-focus fit: [`INTERACTION_LAYERS.md`](INTERACTION_LAYERS.md).

Virgil Desk can drive Chrome two ways. **Handoff / board / decompose** always use the **MV3 extension**. **Execute** (`desk-browser` / `POST /v1/browser`) follows `browser.driver` in [`config/desk.yaml`](../config/desk.yaml).

| `browser.driver` | Execute path | Cookies | Operator setup |
|------------------|--------------|---------|----------------|
| **`extension` (default / Path B)** | Host → extension WS → `scripting` (no CDP) | Same profile (agent tab duplicate) | Extension side panel connected |
| **`harness` (rollback)** | Host → `browser-harness` CDP (everyday Chrome) | Everyday Chrome profile | `chrome://inspect/#remote-debugging` Allow + Chrome 144+ Allow popup |

Harness daemon isolation: `BU_NAME=virgil-desk` (never Virgil tick `:9223` / `BU_CDP_URL` to chrome-virgil). Rollback: set `browser.driver: harness` or `DESK_BROWSER_DRIVER=harness`.

## Path B execute (extension default)

Three Eyes channels (no vision by default):

| Channel | When | Hermes sees |
|---------|------|-------------|
| Slim WebMarker targets | every `observe` | `{id, ref, kind, label, frame_id?}` (max 40; conversation rows prioritized) |
| AX `page_tree` | URL change only | capped role/label tree (≤2k chars; open shadow + allFrames) |
| Probes | on demand | `probe_form` / `probe_links` / `probe_table` |

- Hands: **`target_id`** only (coords kept in extension `targetMap`, stripped from CLI).
- Execute observe defaults `skip_screenshot: true` (`observe_skip_screenshot_default`) — no `captureVisibleTab` tab flicker.
- Same-URL follow-up observe: `text_omitted` + no `page_tree`; keep slim targets.

Implementation: [WebMarker](https://github.com/reidbarber/webmarker) + `deskPageTree` / probes in `interactObserve.bundle.js`. `allFrames: true` stamps `frame_id`; act uses `frameIds`.

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

## Hand off

1. Extension mints `run_id`, **duplicateTab** into **Virgil · Agent** group
2. Optional scroll loops on agent tab
3. Scrape + screenshot on agent tab (handoff only)
4. Host → Hermes decompose

## Agent tab policy

- Agent work on `agent_tab_id` in **Virgil · Agent** group
- Ops on `human_tab_id` blocked except `captureHandoffSnapshot`
- Navigation: duplicate same-origin, else open new agent tab

Playwright in `packages/e2e/playwright/` is **CI/E2E only**. Virgil Hub tick stays on isolated Chrome (`~/.chrome-virgil/*`).
