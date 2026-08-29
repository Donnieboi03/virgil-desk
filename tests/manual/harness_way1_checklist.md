# Manual: Desk harness Way 1 execute

Live proof that **Run agent** / `desk-browser` uses **browser-harness** on everyday Chrome (same cookies), not Virgil `:9223`.

## Prerequisites

1. Everyday Chrome open on the profile with Desk + target logins.
2. `chrome://inspect/#remote-debugging` → tick **Allow remote debugging for this browser instance**.
3. First attach: click Chrome’s **Allow** popup (Chrome 144+).
4. Confirm (must **not** set `BU_CDP_URL` to `:9223`):

   ```bash
   BU_NAME=virgil-desk browser-harness --doctor
   ```

   Expect chrome ok / daemon path that can attach.

5. desk-host running with `browser.driver: harness` (default in `config/desk.yaml`).
6. Extension loaded and **WS connected** (board/handoff still extension).

## Steps

1. Hand off a page (decompose OK).
2. **Run agent** on an Agent item, or:

   ```bash
   desk-browser --run-id <run_id> --op observe --human-tab-id HUMAN --tab-id AGENT --wait
   desk-browser --run-id <run_id> --op click --human-tab-id HUMAN --tab-id AGENT \
     --params '{"x": 100, "y": 100}' --wait
   ```

3. Check `~/.virgil-desk/logs/desk_events.jsonl` for `driver: harness` on `browser.command` / `browser.command_result`.
4. Confirm `act_resolved.used` is `xy` or `selector` (not extension `target_id`), and URL/title look right.

## Rollback

`browser.driver: extension` or `DESK_BROWSER_DRIVER=extension`, restart desk-host.

## Failures

| Symptom | Likely cause |
|---------|----------------|
| Allow remote debugging / daemon FAIL | Way 1 not enabled or popup not clicked |
| Attached to wrong Chrome | `BU_CDP_URL` pointed at Virgil `:9223` — unset it for Desk |
| `click requires x/y or selector` | Hermes still sending `target_id` — harness path does not resolve SoM ids |
