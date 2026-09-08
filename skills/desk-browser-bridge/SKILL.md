---
name: desk-browser-bridge
description: >-
  Virgil Desk browser bridge: desk-browser CLI, Path B extension Eyes/Hands
  (default) or harness CDP rollback, You/Agent/Waiting board, Accept/Deny proposals.
version: 1.8.0
metadata:
  hermes:
    tags: [virgil-desk, browser, handoff]
    keywords: [mint_item, subtask]
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
# Mid-flight subtask (board mint — not a browser op)
desk-browser --run-id desk_abc --op mint_item --params '{
  "parent_id": "PARENT_ID",
  "column": "you",
  "title": "Approve calendar invite"
}'
```

- **`--tab-id`** = agent tab from **Run agent** provision (`agent_tab_id`) — never automate `human_tab_id`.
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

- **`openTab`** — agent needs a **different URL** than the handoff page (extension). For You remainder with a URL, use `--params '{"placement":"human"}'` so the tab opens **outside** **Virgil · Agent** (visible in the strip, `active: false`).
- **`duplicateTab`** — same page as human (extension).
- Handoff uses a short-lived scrape tab then closes it; **Run agent** provisions the item collage.

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
- **Done = work finished or parked** — not a one-line “Observed …” alone. Mint You/Waiting children for human remainder; keep pursuing agent-safe children.
- **Stop when done** — after open + body (or task complete / remainder parked), one-line summary and stop; do not burn remaining turns. Turn ceiling is backup only.
- After the thread is open, **may** follow relevant in-body links (Drive/docs/attachments); summarize; not an exhaustive crawl. Still forbid send/pay/public post.
- Tool budget exhausted without opening → one-line `Partial: …` (not a success claim).

## Mid-flight subtasks

When evidence reveals multiple closures, mint with `--op mint_item` (`parent_id`, `column`, `title`). Host blocks parent `done` while agent children are still `proposed`/`running`.

Park human remainder with a board You/Waiting child **and** optional:

```bash
desk-browser --run-id RUN --op openTab --human-tab-id H --url 'https://…' \
  --params '{"placement":"human"}' --wait
```

## Forbidden

- send email, submit payment, or post public content on agent path without human Accept
- any browser op on `human_tab_id` (except snapshot at user gesture)
- bare row CSS selectors (`tr.zA` / `[role=row]`) instead of `target_id`

**Search / navigation Enter is allowed** — use `press_key: "Enter"` on fill or `key`.

## Proposals

Calendar / drafts → **Accept** or **Deny** via Host; no auto-commit.

## Agent execution

Operator clicks **Run agent** on Agent column **root** items. Hermes uses `desk-browser` + this skill during execute.

## Evidence

`command_result` (host) may include screenshots; **`desk-browser` CLI strips base64** and fat target geometry before Hermes sees it.

## Budget

Host caps `browser.screenshot_max_per_run` per `run_id`. Execute also passes Hermes `--max-turns` from `hermes.execute_max_turns` (default 40) — prefer self-stop when criteria are met. If the ceiling is hit without opening/reading, emit a one-line `Partial:` summary and stop. If the provider aborts/stalls mid-turn, stop with `Partial:` rather than thrashing observes.