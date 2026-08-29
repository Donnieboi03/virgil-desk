---
name: desk-browser-bridge
description: >-
  Virgil Desk browser bridge: desk-browser CLI, observe-first interact targets,
  You/Agent/Waiting board, Accept/Deny proposals.
version: 1.3.0
metadata:
  hermes:
    tags: [virgil-desk, browser, handoff]
---

# Desk browser bridge

Use when executing a **Virgil Desk** handoff via Host `POST /v1/browser` or the **`desk-browser`** CLI.

## CLI (Hermes `terminal`)

From the Virgil Desk repo root (or with `desk-browser` on PATH):

```bash
export DESK_HOST=127.0.0.1
export DESK_PORT=8787

desk-browser --run-id desk_abc --op observe --human-tab-id 1 --tab-id 2 --wait
desk-browser --run-id desk_abc --op click --human-tab-id 1 --tab-id 2 \
  --params '{"target_id": 7}' --wait
desk-browser --run-id desk_abc --op fill --human-tab-id 1 --tab-id 2 \
  --params '{"target_id": 3, "value": "hello@example.com"}' --wait
desk-browser --run-id desk_abc --op fill --human-tab-id 1 --tab-id 2 \
  --params '{"target_id": 16, "value": "search terms", "press_key": "Enter"}' --wait
desk-browser --run-id desk_abc --op scroll --human-tab-id 1 --tab-id 2 \
  --params '{"direction":"down"}' --wait
desk-browser --run-id desk_abc --op key --human-tab-id 1 --tab-id 2 \
  --params '{"target_id": 16, "key":"Enter"}' --wait
```

- **`--tab-id`** = agent tab from handoff (`agent_tab_id`) — never automate `human_tab_id`.
- **`--wait`** blocks until the extension returns `command_result`.
- Requires extension WebSocket connected (`WS connected` in panel).

Script: [`scripts/desk-browser`](../scripts/desk-browser)

## Tab rules

- **`openTab`** — agent needs a **different URL** than the handoff page.
- **`duplicateTab`** — agent must interact with the **same page** the human is on (never automate the human tab).
- Handoff duplicates first — decompose snapshot comes from the agent tab (excerpt + screenshot).

## Observe–act–observe

Use **`observe`** as the primary read on an agent tab. CLI stdout is a **thin Eyes/Hands envelope** (no screenshot base64 — `screenshot.omitted: true`). It returns:

- `text_excerpt` (first visit for a URL: up to `browser.scrape_excerpt_max_chars`; after a URL change: capped by `browser.observe_followup_excerpt_max_chars`)
- `text_omitted: true` when the URL is unchanged since the last full/follow-up excerpt — targets remain; do not expect inbox text again
- `interact_targets[]` — numbered targets (`id`, `ref`, `label`, `rect`, `center`)
- `scroll_containers[]` when nested panes are scrollable
- Screenshot dims only in CLI (`omitted: true`); do not expect image bytes in the terminal JSON

**Act** by `target_id` (preferred), `text`/`contains`, or `{x,y}` CSS pixels as fallback — not agent-authored CSS selectors.

Loop until the task is done (host also enforces `hermes.execute_max_turns`):

```
observe → pick target_id → click | fill | scroll | key → verify (url + act_resolved + thin post-action result)
```

Mutating ops auto-return post-action scrape metadata (same omit/cap rules). Check `act_resolved.url_before` vs `url_after` when opening threads or navigating.

### Click / fill resolution order (extension)

1. `target_id` or `ref` from last `observe` on this tab+run
2. `text` / `contains` match on target labels
3. `{x, y}` CSS viewport coordinates
4. Legacy `selector` only when explicitly needed

If you see `stale_observe: run observe first`, call `observe` again after navigation.

## Forbidden

- send email, submit payment, or post public content on agent path without human Accept
- any browser op on `human_tab_id` (except snapshot at user gesture)

**Search / navigation Enter is allowed** — use `press_key: "Enter"` on fill or `key` with `target_id`.

## Proposals

Calendar / drafts → **Accept** or **Deny** via Host; no auto-commit.

## Agent execution

Operator clicks **Run agent** on Agent column items. Hermes uses `desk-browser` + this skill during execute.

## Evidence

`command_result` (extension/host) may include screenshots; **`desk-browser` CLI strips base64** before Hermes sees it — keep `act_resolved`, `interact_targets`, and capped scrape fields.

## Budget

First `observe` (or host `initial_scrape`) may be large; same-URL follow-ups omit page text and keep targets. After navigation, expect a capped follow-up excerpt. Host caps `browser.screenshot_max_per_run` per `run_id`; handoff snapshot at user gesture is exempt. Execute also passes Hermes `--max-turns` from `hermes.execute_max_turns` (default 12) — when hit, emit a one-line partial summary and stop.

On **`stall_detected`**: re-observe once, then stop with a one-line partial summary — do not keep clicking stale targets. Prefer `target_id` over coordinates. Do not follow off-origin links during inbox triage (extension auto-closes those tabs).
