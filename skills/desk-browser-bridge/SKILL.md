---
name: desk-browser-bridge
description: >-
  Virgil Desk browser bridge: duplicateTab vs openTab, screenshot-forward
  observe-act-observe, You/Agent/Waiting board, Accept/Deny proposals.
version: 1.0.0
metadata:
  hermes:
    tags: [virgil-desk, browser, handoff]
---

# Desk browser bridge

Use when executing a **Virgil Desk** handoff via Host `desk_browser` tool.

## Tab rules

- **`openTab`** — agent needs a **different URL** than the handoff page.
- **`duplicateTab`** — agent must interact with the **same page** the human is on (never automate the human tab).
- **`captureHandoffSnapshot`** — read-only on human tab at user gesture only.

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

### Choosing `openTab` vs `duplicateTab`

- Different URL than handoff → `openTab`
- Must interact with same page user is on → `duplicateTab`

## Forbidden

- send, submit, pay on agent path without human Accept
- any `click` / `fill` / `scrape` / `screenshot` on `human_tab_id` (except snapshot)

## Proposals

- Calendar / drafts → **Accept** or **Deny** via Host; no auto-commit.

## Harness parity

Hub TO sees mailbox PNG; Desk agent sees `command_result.screenshot` (~4k tokens — cheap vs full workflow).

## Budget

Prefer screenshots over extra replanning turns. Cap ~20 screenshots/handoff unless operator extends.
