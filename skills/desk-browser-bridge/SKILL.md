---
name: desk-browser-bridge
description: >-
  Virgil Desk browser bridge: desk-browser CLI, Path B extension Eyes/Hands
  (default) or harness CDP rollback, You/Agent/Waiting board, Accept/Deny proposals.
version: 1.6.0
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
# Path B (default): click/fill by target_id from observe
desk-browser --run-id desk_abc --op click --human-tab-id 1 --tab-id 2 \
  --params '{"target_id": 7}' --wait
desk-browser --run-id desk_abc --op fill --human-tab-id 1 --tab-id 2 \
  --params '{"target_id": 3, "value": "search terms", "press_key": "Enter"}' --wait
desk-browser --run-id desk_abc --op scroll --human-tab-id 1 --tab-id 2 \
  --params '{"direction":"down"}' --wait
desk-browser --run-id desk_abc --op key --human-tab-id 1 --tab-id 2 \
  --params '{"key":"Enter"}' --wait
# Optional probes (lazy Eyes)
desk-browser --run-id desk_abc --op probe_links --human-tab-id 1 --tab-id 2 --wait
desk-browser --run-id desk_abc --op probe_form --human-tab-id 1 --tab-id 2 --wait
```

- **`--tab-id`** = agent tab from handoff (`agent_tab_id`) — never automate `human_tab_id`.
- **`--wait`** blocks until host returns `command_result` (extension or harness).
- **Extension driver (default / Path B):** no remote-debugging required for execute; extension WS required.
- Rollback: `browser.driver: harness` (or `DESK_BROWSER_DRIVER=harness`) uses CDP `{x,y}` / `selector`.

Script: [`scripts/desk-browser`](../scripts/desk-browser)

## Drivers

See [`docs/BROWSER_LAYER.md`](../docs/BROWSER_LAYER.md).

| Driver | Eyes | Hands |
|--------|------|-------|
| **`extension` (default)** | slim `interact_targets`, optional `page_tree`, excerpt omit on same URL | `target_id` via content script |
| `harness` | url/title/viewport; empty targets | `{x,y}`, `selector` via CDP |

## Tab rules

- **`openTab`** — agent needs a **different URL** than the handoff page (extension).
- **`duplicateTab`** — same page as human (extension).
- Handoff duplicates first — decompose snapshot comes from the agent tab (excerpt + screenshot).

## Observe–act–observe

CLI stdout is a **thin Eyes/Hands envelope** (no screenshot base64 — `screenshot.omitted: true`; targets stripped to id/ref/kind/label/frame_id).

**Extension:** act by `target_id` only. Re-observe after navigation. Use probes when the target map is insufficient.

Loop until the task is done (host also enforces `hermes.execute_max_turns`):

```
observe → act (target_id) → verify (url + act_resolved + thin post-action result)
```

Check `act_resolved.url_before` vs `url_after` when opening threads or navigating. Events may include `driver: extension`.

## Inbox / thread success criteria

- **Must open** the matching message/thread (row `target_id` whose label matches sender/subject) and re-observe body/URL before summarizing.
- **List or search snippets are not done** — never finish from inbox preview alone.
- Prefer row targets with sender/subject in `label`. **Forbidden:** bare CSS `tr.zA`, `tr.zE`, or `[role=row]` (ambiguous; wrong-row risk). Extension rejects those selectors.
- Tool budget exhausted without opening → one-line `Partial: …` (not a success claim).

## Forbidden

- send email, submit payment, or post public content on agent path without human Accept
- any browser op on `human_tab_id` (except snapshot at user gesture)
- bare row CSS selectors (`tr.zA` / `[role=row]`) instead of `target_id`

**Search / navigation Enter is allowed** — use `press_key: "Enter"` on fill or `key`.

## Proposals

Calendar / drafts → **Accept** or **Deny** via Host; no auto-commit.

## Agent execution

Operator clicks **Run agent** on Agent column items. Hermes uses `desk-browser` + this skill during execute.

## Evidence

`command_result` (host) may include screenshots; **`desk-browser` CLI strips base64** and fat target geometry before Hermes sees it.

## Budget

Host caps `browser.screenshot_max_per_run` per `run_id`. Execute also passes Hermes `--max-turns` from `hermes.execute_max_turns` (default 20) — when hit, emit a one-line `Partial:` summary and stop. If the provider aborts/stalls mid-turn, stop with `Partial:` rather than thrashing observes.
