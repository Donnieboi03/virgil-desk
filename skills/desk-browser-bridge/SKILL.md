---
name: desk-browser-bridge
description: >-
  Virgil Desk browser bridge: desk-browser CLI, extension Eyes/Hands
  (default) or harness CDP rollback. Done/park/clump policy lives in the execute Packet prompt.
version: 1.16.0
metadata:
  hermes:
    tags: [virgil-desk, browser, handoff]
    keywords: [mint_item, subtask, auth_wall, soft_help, park_last_resort, url_first_park, awaiting_human, eyes_empty, eyes_mode, verified_terminal, human_remainder, homogeneous_clump]
---

# Desk browser bridge

Use when executing a **Virgil Desk** handoff via Host `POST /v1/browser` or the **`desk-browser`** CLI.

**Primary model = DOM Eyes → `target_id` Hands.** URL open/construct is a **secondary workaround** (hostile/empty Eyes). **Done / park / clump / failure-isolation criteria:** follow the execute Packet prompt (`execute_agent_item.md`) — this skill is the CLI reference only.

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
- If the initial `agent_tab_id` observe times out or hangs (e.g. fresh background tab), use `openTab --url <handoff_or_search_url>` to initialize an active agent tab.
- **`--wait`** blocks until host returns `command_result` (extension or harness).
- **Extension driver (default / extension):** no remote-debugging required for execute; extension WS required.
- Rollback: `browser.driver: harness` (or `DESK_BROWSER_DRIVER=harness`) uses CDP `{x,y}` / `selector`.

Script: [`scripts/desk-browser`](../scripts/desk-browser)

## Drivers

See [`docs/BROWSER_LAYER.md`](../docs/BROWSER_LAYER.md).

| Driver | Eyes | Hands |
|--------|------|-------|
| **`extension` (default)** | slim `interact_targets`, optional `page_tree`, excerpt omit on same URL; fail-only `eyes_mode` 0→1→2 | `target_id` via content script |
| `harness` | url/title/viewport; empty targets | `{x,y}`, `selector` via CDP |

## Tab rules

- **`openTab`** (default / agent) — different URL than handoff; stays in **Virgil · Agent**.
- **`openTab` + `placement:human`** — **denied** (`human_park_tab_denied`). Park = URL-first You mint only.
- **`duplicateTab`** — same page as human (extension).
- **`closeTab`** — requires `--tab-id`; missing id is rejected.
- **Virgil · Agent** is created only on **Run agent**.

## Observe–act–observe

CLI stdout is a **thin Eyes/Hands envelope** (no screenshot base64 — `screenshot.omitted: true`; targets stripped to id/ref/kind/label/frame_id).

```
observe → act (target_id) → verify (url + act_resolved + thin post-action result)
```

- Act by `target_id` only on extension. Re-observe after navigation.
- **`probe_links` / `probe_form` / `probe_table`:** only when Eyes targets lack the link/form structure you need — not a ritual after every open. Prefer visible link `target_id`s or `openTab --url` when the URL is already known. Empty `probe_links` ≠ “links checked.”
- Check `act_resolved.url_before` vs `url_after` when opening threads.

## Mint / park (syntax)

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

When to park, Done language, clump failure isolation, and human_remainder rules: **execute Packet prompt**.

## Forbidden (quick)

- outbound social send/connect, public posts, payment/sign submits; send email without Accept (drafts OK)
- any browser op on `human_tab_id` (except snapshot at user gesture)
- **`openTab` + `placement:human`**; bare list-row CSS instead of `target_id`

## Evidence

Host may require ≥1 successful `browser` result before Done (`hermes.execute_require_browser_evidence`). Prefer finishing when Done criteria in the Packet prompt are met; `hermes.execute_max_turns` is backup.
