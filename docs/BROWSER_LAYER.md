# Browser layer

Virgil Desk drives Chrome via the **MV3 extension** only: `tabs`, `tabGroups`, `scripting`, and `tabs.captureVisibleTab`.

## Observe (preferred agent read)

**`observe`** returns an Anthropic-style hybrid payload:

- `text_excerpt` — page text (up to `browser.scrape_excerpt_max_chars`, default 100k)
- `interact_targets[]` — numbered clickable/fillable elements (`id`, `ref`, `label`, `rect`, `center`)
- `scroll_containers[]` — nested scroll panes when detected
- `screenshot` — viewport PNG with `css_width`, `css_height`, `device_pixel_ratio`

Implementation uses [WebMarker](https://github.com/reidbarber/webmarker) (MIT) for Set-of-Mark overlays, plus occlusion filtering inspired by Opticlick/GPT-4V-Act heuristics. Bundled as `interactObserve.bundle.js` (esbuild, page `MAIN` world).

**Act** by `target_id` from the last observe on this `run_id` + tab: `click`, `fill`, `scroll` (optional container `target_id`), `key`. Fallbacks: `text`, CSS `{x,y}`, legacy `selector`.

Every mutating op returns `act_resolved` (`used`, `url_before`, `url_after`) for observability.

## Scrape vs screenshot (legacy)

| Mechanism | What you get |
|-----------|----------------|
| **Scrape** | Page `innerText`, link list, URL, title |
| **Screenshot** | Real viewport PNG (base64) |

`scrape` / `screenshot` remain for backward compatibility; agents should prefer **`observe`**.

Screenshot flow (brief tab flicker accepted):

1. Remember the human's active tab in the window
2. Activate the agent tab
3. Wait `browser.default_wait_ms`
4. `captureVisibleTab`
5. Restore the prior active tab

## Hand off

1. Extension mints `run_id`, **duplicateTab** into **Virgil · Agent** group
2. Optional scroll loops (`handoff_scroll_loops`) on agent tab
3. Scrape + `captureVisibleTab` on agent tab
4. Host receives rich snapshot → Hermes decompose (text + `--image` when PNG present)

## Agent tab policy

- Agent work runs on `agent_tab_id` in the collapsed **Virgil · Agent** tab group
- Ops on `human_tab_id` are blocked except `captureHandoffSnapshot`
- Navigation: duplicate same-origin path, else open new agent tab

Playwright in `packages/e2e/playwright/` is **CI/E2E only** — not the runtime browser driver.

Future: optional CDP/harness backend with the same observe contract (`observe_backend: extension|cdp`).
