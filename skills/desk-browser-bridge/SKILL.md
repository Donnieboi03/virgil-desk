---
name: desk-browser-bridge
description: >-
  Virgil Desk browser bridge: desk-browser CLI, duplicateTab vs openTab,
  screenshot-forward observe-act-observe, You/Agent/Waiting board, Accept/Deny proposals.
version: 1.1.0
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

desk-browser --run-id desk_abc --op scrape --human-tab-id 1 --tab-id 2 --wait
desk-browser --run-id desk_abc --op scroll --human-tab-id 1 --tab-id 2 \
  --params '{"direction":"down"}' --wait
desk-browser --run-id desk_abc --op screenshot --human-tab-id 1 --tab-id 2 --wait
```

- **`--tab-id`** = agent tab from handoff (`agent_tab_id`) — never automate `human_tab_id`.
- **`--wait`** blocks until the extension returns `command_result`.
- Requires extension WebSocket connected (`WS connected` in panel).

Script: [`scripts/desk-browser`](../scripts/desk-browser)

## Tab rules

- **`openTab`** — agent needs a **different URL** than the handoff page.
- **`duplicateTab`** — agent must interact with the **same page** the human is on (never automate the human tab).
- Handoff now **duplicates first** — decompose snapshot comes from the agent tab (excerpt + screenshot).

## Observe–act–observe (screenshot-forward)

### After every `click`, `fill`, or navigation on an agent tab

1. `wait` (short; DOM/URL settle)
2. `scrape` (capped excerpt + http(s) links)
3. `screenshot` (required — verify action landed)

Do not mark WorkItem done without post-action screenshot + scrape in evidence.

### Reading a page (no action yet)

1. `screenshot` (baseline — one per agent tab open)
2. Loop: `scroll` → `scrape`
3. Add `screenshot` when ANY:
   - scrape excerpt < 200 chars or no target link found
   - 2 scroll loops without progress
   - layout-heavy UI (forms, wizards, modals)
   - preparing You-column handoff

## Forbidden

- send, submit, pay on agent path without human Accept
- any `click` / `fill` / `scrape` / `screenshot` on `human_tab_id` (except snapshot at user gesture)

## Proposals

- Calendar / drafts → **Accept** or **Deny** via Host; no auto-commit.

## Agent execution

- Operator clicks **Run agent** on Agent column items (manual — not auto after decompose).
- Hermes uses `desk-browser` + this skill during execute.

## Evidence

Desk agents receive `command_result.screenshot` (PNG base64) plus capped scrape excerpts (~4k vision tokens per shot — prefer screenshots over extra replanning turns).

## Budget

Prefer screenshots over extra replanning turns. Cap ~20 screenshot ops per `run_id` via Host policy (handoff snapshot PNG at user gesture is exempt — taken client-side before decompose).
