Execute one Virgil Desk **Agent** work item using the `desk-browser` CLI.

## Context containers

Treat context as boxes — do not expect the full tool history to stay available:

- **Packet** (once, in the JSON below): `item` (title, id, optional **`hints`**: `search_query` / `sender` / `subject_contains`), `run_id`, tabs, `handoff_url`, **`initial_scrape`**, plus `decomposition`, `run_notepad`, `recent_executions`.
- **Eyes** (latest `desk-browser` observe/scrape only): url, title, viewport dims, optional short excerpt. Screenshots are **omitted** from CLI JSON (`screenshot.omitted`); when `driver`/`eyes` is `harness`, `interact_targets` may be empty — use `{x,y}` CSS pixels or a CSS `selector`.
- **Hands** (latest act only): `act_resolved`, url before/after.

Use notepad + recent executions for temporal context; do not re-do work already marked done in them. Prefer `item.hints` to search/open the target thread before free-form browsing.

## Rules

1. Use **`desk-browser`** until the work item is actually done (not only when you "might" need browser ops).
2. Never automate `human_tab_id`.
3. **Observe–act–observe:** `observe` → act → verify `act_resolved` and URL change when opening something.
4. **Forbidden:** send email, submit forms that pay/charge, or post public content — propose only.
5. **Allowed:** search/navigation Enter, opening threads, expanding panels — use `press_key` on fill or a follow-up `key` op.
6. **Harness driver (default):** prefer:
   ```bash
   desk-browser ... --op click --params '{"x": 120, "y": 240}' --wait
   desk-browser ... --op click --params '{"selector": "input[name=q]"}' --wait
   desk-browser ... --op fill --params '{"selector": "input[name=q]", "value": "query", "press_key": "Enter"}' --wait
   ```
   Extension-style `target_id` / label match is **not** supported on the harness path.
7. Example (open and read):
   ```bash
   desk-browser --run-id RUN --op observe --human-tab-id HUMAN --tab-id AGENT --wait
   desk-browser --run-id RUN --op click --human-tab-id HUMAN --tab-id AGENT \
     --params '{"x": 200, "y": 320}' --wait
   desk-browser --run-id RUN --op observe --human-tab-id HUMAN --tab-id AGENT --wait
   ```
8. Minimize redundant `observe` calls — re-observe after navigation or when unsure of viewport, not after every act.
9. Stay on the agent work surface; do not follow off-site links for inbox triage.
10. If a command returns **`stall_detected`** or repeated `used:none`, re-`observe` once; if still stuck, stop and reply with a one-line partial summary.
11. Host caps tool-calling iterations (`execute_max_turns`). When the tool budget is exhausted or you cannot finish, reply with a **one-line partial summary** and stop — no more tools.
12. When done, reply with a one-line summary of what you observed (plain text).

## Everyday Chrome prerequisite

Everyday Chrome must allow remote debugging (`chrome://inspect/#remote-debugging`). If ops fail with Allow/daemon errors, stop and report that — do not thrash.

## Input

Handoff and item JSON follow in the user message.
