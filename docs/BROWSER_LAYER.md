# Browser layer

Eyes vs Hands (DOM / CDP Input / OS), costs, and dual-focus fit: [`INTERACTION_LAYERS.md`](INTERACTION_LAYERS.md).

Virgil Desk can drive Chrome two ways. **Handoff / board / decompose** always use the **MV3 extension**. **Execute** (`desk-browser` / `POST /v1/browser` observe·click·fill·scroll·key) follows `browser.driver` in [`config/desk.yaml`](../config/desk.yaml).

| `browser.driver` | Execute path | Cookies | Operator setup |
|------------------|--------------|---------|----------------|
| **`harness`** (default) | Host → `browser-harness` CDP (everyday Chrome) | Everyday Chrome profile (same logins) | `chrome://inspect/#remote-debugging` Allow + Chrome 144+ Allow popup |
| **`extension`** | Host → extension WS → `scripting` + `captureVisibleTab` | Same profile (agent tab duplicate) | Extension side panel connected |

Harness daemon isolation: `BU_NAME=virgil-desk` (never Virgil tick `:9223` / `BU_CDP_URL` to chrome-virgil). Rollback: set `browser.driver: extension` or `DESK_BROWSER_DRIVER=extension`.

## Harness execute (everyday Chrome)

- Sticky CDP **target per `run_id`** (no per-call `with tab()` auto-close).
- Eyes: `page_info` + screenshot dims (`eyes: harness`); `interact_targets` empty in v1 — prefer `{x,y}` or CSS `selector` / `click_element`.
- Hands: compositor clicks via harness `Input.dispatchMouseEvent`.
- Events: `browser.command` / `browser.command_result` include `driver: harness`.
- Teardown: release sticky target on execute cleanup; tabs opened by harness are closed; existing everyday tabs left alone.

Confirm attach: `BU_NAME=virgil-desk browser-harness --doctor` (chrome ok, daemon alive) **without** pointing at `:9223`.

## Observe (extension path / legacy)

When `driver: extension`, **`observe`** returns an Anthropic-style hybrid payload:

- `text_excerpt` — page text (up to `browser.scrape_excerpt_max_chars`, default 12k)
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

Screenshot flow on **extension** driver (brief tab flicker accepted):

1. Remember the human's active tab in the window
2. Activate the agent tab
3. Wait `browser.default_wait_ms`
4. `captureVisibleTab`
5. Restore the prior active tab

Harness screenshots use CDP `Page.captureScreenshot` on the sticky target (no tab flicker API).

## Hand off

1. Extension mints `run_id`, **duplicateTab** into **Virgil · Agent** group
2. Optional scroll loops (`handoff_scroll_loops`) on agent tab
3. Scrape + `captureVisibleTab` on agent tab
4. Host receives rich snapshot → Hermes decompose (text + `--image` when PNG present)

## Agent tab policy

- Agent work runs on `agent_tab_id` in the collapsed **Virgil · Agent** tab group (extension UX)
- Ops on `human_tab_id` are blocked except `captureHandoffSnapshot`
- Navigation: duplicate same-origin path, else open new agent tab
- Harness execute may attach to the handoff URL’s CDP page (same cookies) instead of scripting the extension tab id

Playwright in `packages/e2e/playwright/` is **CI/E2E only** — not the runtime browser driver.

Virgil Hub tick / `browser_queue` stays on isolated Chrome (`~/.chrome-virgil/*`). Desk harness attach is interactive everyday Chrome only.
