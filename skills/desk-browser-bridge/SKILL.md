---
name: desk-browser-bridge
description: >-
  Virgil Desk browser bridge: desk-browser CLI, Path B extension Eyes/Hands
  (default) or harness CDP rollback, You/Agent/Waiting board, Accept/Deny proposals.
version: 1.15.2
metadata:
  hermes:
    tags: [virgil-desk, browser, handoff]
    keywords: [mint_item, subtask, auth_wall, soft_help, park_last_resort, url_first_park, awaiting_human, eyes_empty, eyes_mode, verified_terminal]
---

# Desk browser bridge

Use when executing a **Virgil Desk** handoff via Host `POST /v1/browser` or the **`desk-browser`** CLI.

**Primary model = DOM Eyes → `target_id` Hands.** URL open/construct is a **secondary workaround** (hostile/empty Eyes) — not the default path. **Park to You is last resort**, not a general Done option. **Verified terminal page state** (expired / already submitted / deadline passed) after Eyes read = **Completed** — not Partial, not park.

## CLI (Hermes `terminal`)

From the Virgil Desk repo root (or with `desk-browser` on PATH):

```bash
export DESK_HOST=127.0.0.1
export DESK_PORT=8787

desk-browser --run-id desk_abc --op observe --human-tab-id 1 --tab-id 2 --wait
desk-browser --run-id desk_abc --op click --human-tab-id 1 --tab-id 2 \
  --params '{"target_id": 7}' --wait
desk-browser --run-id desk_abc --op fill --human-tab-id 1 --tab-id 2 \
  --params '{"target_id": 3, "value": "search terms", "press_key": "Enter"}' --wait
desk-browser --run-id desk_abc --op scroll --human-tab-id 1 --tab-id 2 \
  --params '{"direction":"down"}' --wait
desk-browser --run-id desk_abc --op key --human-tab-id 1 --tab-id 2 \
  --params '{"key":"Enter"}' --wait
desk-browser --run-id desk_abc --op probe_links --human-tab-id 1 --tab-id 2 --wait
desk-browser --run-id desk_abc --op probe_form --human-tab-id 1 --tab-id 2 --wait
desk-browser --run-id desk_abc --op mint_item --params '{
  "parent_id": "PARENT_ID",
  "column": "agent",
  "title": "Open shared folder and list files"
}'
desk-browser --run-id desk_abc --op closeTab --tab-id 99 --wait
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
| **`extension` (default)** | slim `interact_targets`, optional `page_tree`, excerpt omit on same URL; fail-only `eyes_mode` 0→1→2 | `target_id` via content script |
| `harness` | url/title/viewport; empty targets | `{x,y}`, `selector` via CDP |

## Tab rules

- **`openTab`** (default / agent) — different URL than handoff; stays in **Virgil · Agent**. Use this to **continue** on readable follow-up pages.
- **`openTab` + `placement:human`** — **denied** (`human_park_tab_denied`). Park is URL-first You card only.
- **`duplicateTab`** — same page as human (extension).
- **`closeTab`** — requires `--tab-id`; missing id is rejected (not a silent no-op).
- Handoff uses a short-lived **ungrouped** scrape tab then closes it — **Virgil · Agent** is created only on **Run agent**.

## Agent-continue vs park (URL-first last resort)

**Continue as agent** when links are readable: shared folders/docs, thread bodies, job pages — `openTab` (agent) → observe → read/summarize; mint **agent** children for multi-closure.

**Park You only when:** login/CAPTCHA/auth/challenge wall; forbidden send/connect/pay/sign/submit; hostile/empty Eyes when human action is still required; or stuck after re-observe. Soft-help = `mint_item` → You (keywords/draft/checklist).

**URL-first park** — mint You with `source.url` (+ `park_kind` / `resume` for gates). Desk panel shows a clickable URL / Open. Do **not** `openTab placement=human`.

```bash
desk-browser --run-id RUN --op mint_item --params '{
  "parent_id": "PARENT_ID",
  "column": "you",
  "title": "Clear login at destination",
  "park_kind": "auth_gate",
  "resume": true,
  "source": {"url": "https://destination.example/path"}
}'
```

- **`park_kind: auth_gate`** — parent → `awaiting_human` until human Marks done → **Resume agent**. Use this for auth/challenge walls (not bare `Partial:`).
- **`park_kind: human_remainder`** — agent may Complete verified facts **and** leave You for human view; never claim “no further action” without acknowledging the remainder.
- Challenge patience: wait/settle/re-observe once on bot interstitials; prefer **one** You for the destination URL. On Resume, honor Packet `resume.cleared_gates`.

Do not claim Observed success from blank scrape. If Eyes return **`eyes_mode: 1`**, trust the promoted excerpt. If Eyes **verify a terminal** outcome, stop with Completed — do not mint You. If **`eyes_empty`** / **`eyes_mode: 2`** with no usable fact, do not invent page copy from the URL alone — use `eyes_hints.url_path_hint` only as a soft signal, then `Partial:` or last-resort park when human action remains. On **Resume**, Packet may include `resume.cleared_gates` — do not remint those URLs; continue past the gate.

## Observe–act–observe

CLI stdout is a **thin Eyes/Hands envelope** (no screenshot base64 — `screenshot.omitted: true`; targets stripped to id/ref/kind/label/frame_id).

**Extension:** act by `target_id` only. Re-observe after navigation. Use probes when the target map is insufficient.

Loop until the task is done (host also enforces `hermes.execute_max_turns`):

```
observe → act (target_id) → verify (url + act_resolved + thin post-action result)
```

Check `act_resolved.url_before` vs `url_after` when opening threads or navigating. Events may include `driver: extension`.

## Inbox / thread success criteria

- **Must open** the matching message/thread and re-observe body/URL before claiming progress.
- **List / search snippets are not done.**
- Prefer row `target_id`s. **Forbidden:** bare list-row CSS instead of `target_id`.
- **Done** = agent-safe work finished (incl. following readable links as agent), **or** `Partial:`, **or** last-resort URL-first park. Host rejects bare “Observed …” / “Opened …”. Host also rejects “Reviewed …” after a failed `openTab`.
- **Stop only when Done is met.** Turn ceiling is backup; ceiling without Done → `Partial:`.
- After open, **follow relevant in-body links as agent** before parking. Empty `probe_links` ≠ links checked.

## Mid-flight subtasks

When Eyes / non-empty probes show **multiple actionable closures**, **must** `mint_item` before success stop (not for terminal verified dead-ends). Prefer **agent** column for readable follow-ups; You/Waiting only under last-resort park. Host blocks parent `done` while agent children are open. Truly one closure or verified terminal: say “Single closure: …” / “Verified expired …; no further action.” after finishing. If a You remainder remains, acknowledge parked remainder instead of “no further action.”

## Forbidden

- outbound social send/connect/InMail-class actions, public posts, payment/sign submits
- send email without human Accept (email **drafts** are allowed)
- any browser op on `human_tab_id` (except snapshot at user gesture)
- **`openTab` + `placement:human`** (use URL-first You mint)
- bare list-row CSS instead of `target_id`

**Search / navigation Enter is allowed** — use `press_key: "Enter"` on fill or `key`.

## Proposals

Calendar / drafts → **Accept** or **Deny** via Host; no auto-commit.

## Agent execution

Operator clicks **Run agent** / **Resume agent** on Agent column **root** items. Hermes uses `desk-browser` + this skill during execute. Mark done on an `auth_gate` You unblocks the parent (`proposed` + Resume) — no auto-Hermes.

## Evidence

`command_result` (host) may include screenshots; **`desk-browser` CLI strips base64** and fat target geometry before Hermes sees it. Failed ops log `error` / `tab_id` / `url` in `desk_events.jsonl`. Optional usage/cost may appear on execute/decompose events when the agent backend exposes it.

## Budget

Host caps `browser.screenshot_max_per_run` per `run_id`. Execute also passes Hermes `--max-turns` from `hermes.execute_max_turns` (default 40) — prefer self-stop when criteria are met. If the ceiling is hit without opening/reading, emit a one-line `Partial:` summary and stop. If the provider aborts/stalls mid-turn, stop with `Partial:` rather than thrashing observes.
