---
name: desk-browser-bridge
description: >-
  Virgil Desk browser bridge: desk-browser CLI, harness on everyday Chrome (default) or
  extension observe targets, You/Agent/Waiting board, Accept/Deny proposals.
version: 1.4.0
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
# Harness (default): click by CSS pixels or selector
desk-browser --run-id desk_abc --op click --human-tab-id 1 --tab-id 2 \
  --params '{"x": 120, "y": 240}' --wait
desk-browser --run-id desk_abc --op click --human-tab-id 1 --tab-id 2 \
  --params '{"selector": "a[href*=\"thread\"]"}' --wait
desk-browser --run-id desk_abc --op fill --human-tab-id 1 --tab-id 2 \
  --params '{"selector": "input[name=q]", "value": "search terms", "press_key": "Enter"}' --wait
desk-browser --run-id desk_abc --op scroll --human-tab-id 1 --tab-id 2 \
  --params '{"direction":"down"}' --wait
desk-browser --run-id desk_abc --op key --human-tab-id 1 --tab-id 2 \
  --params '{"key":"Enter"}' --wait
```

- **`--tab-id`** = agent tab from handoff (`agent_tab_id`) — never automate `human_tab_id`.
- **`--wait`** blocks until host returns `command_result` (extension or harness).
- **Harness driver (default):** needs everyday Chrome with Allow remote debugging — not Virgil `:9223`. Extension WS still required for board/handoff.
- Rollback: host `browser.driver: extension` uses interact_targets + `target_id` again.

Script: [`scripts/desk-browser`](../scripts/desk-browser)

## Drivers

See [`docs/BROWSER_LAYER.md`](../docs/BROWSER_LAYER.md).

| Driver | Eyes | Hands |
|--------|------|-------|
| `harness` | url/title/viewport; screenshot dims (`eyes: harness`); empty `interact_targets` | `{x,y}`, `selector`, fill/key/scroll via CDP |
| `extension` | `interact_targets` + excerpt | `target_id` / text / `{x,y}` via content script |

## Tab rules

- **`openTab`** — agent needs a **different URL** than the handoff page (extension).
- **`duplicateTab`** — same page as human (extension).
- Handoff duplicates first — decompose snapshot comes from the agent tab (excerpt + screenshot).

## Observe–act–observe

CLI stdout is a **thin Eyes/Hands envelope** (no screenshot base64 — `screenshot.omitted: true`).

**Harness:** act with `{x,y}` or `selector`; re-observe after navigation.

**Extension:** act by `target_id` (preferred), `text`/`contains`, or `{x,y}`.

Loop until the task is done (host also enforces `hermes.execute_max_turns`):

```
observe → act → verify (url + act_resolved + thin post-action result)
```

Check `act_resolved.url_before` vs `url_after` when opening threads or navigating. Events may include `driver: harness`.

## Forbidden

- send email, submit payment, or post public content on agent path without human Accept
- any browser op on `human_tab_id` (except snapshot at user gesture)

**Search / navigation Enter is allowed** — use `press_key: "Enter"` on fill or `key`.

## Proposals

Calendar / drafts → **Accept** or **Deny** via Host; no auto-commit.

## Agent execution

Operator clicks **Run agent** on Agent column items. Hermes uses `desk-browser` + this skill during execute.

## Evidence

`command_result` (host) may include screenshots; **`desk-browser` CLI strips base64** before Hermes sees it — keep `act_resolved`, url/title, and capped scrape fields.

## Budget

Host caps `browser.screenshot_max_per_run` per `run_id`. Execute also passes Hermes `--max-turns` from `hermes.execute_max_turns` (default 12) — when hit, emit a one-line partial summary and stop.
