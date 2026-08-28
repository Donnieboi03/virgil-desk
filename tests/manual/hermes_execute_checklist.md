# Manual Hermes execute checklist

Live proof that **Run agent** invokes Hermes → `desk-browser` → extension browser ops.

## Prerequisites

- `DESK_AGENT_BACKEND=hermes desk-host`
- Extension loaded (`packages/extension/dist`), **WS connected**
- Hermes profile with `terminal` + `desk-browser-bridge` skill
- `export PATH="$VIRGIL_DESK_REPO/scripts:$PATH"`

## Steps

1. Open Gmail (or any logged-in heavy UI) in Chrome
2. **Hand off this tab** — note `run_id` in panel
3. Confirm Agent column item with `running` or `proposed` status
4. Click **Run agent**
5. Watch Host terminal / extension for agent tab activity
6. Optional CLI smoke:
   ```bash
   desk-browser --run-id <run_id> --op observe --human-tab-id HUMAN --tab-id AGENT --wait
   desk-browser --run-id <run_id> --op click --human-tab-id HUMAN --tab-id AGENT \
     --params '{"target_id": 1}' --wait
   ```
   Expect `interact_targets` on observe and `act_resolved.used` on click.

## Expected events

```bash
desk-events --run-id <run_id> --summary
```

| Event | When |
|-------|------|
| `handoff.snapshot` | After handoff — `flags.has_screenshot: true` |
| `handoff.decomposed` | Board populated — `live: true` |
| `agent.execute_started` | Run agent clicked |
| `browser.command` | Hermes called `desk-browser` |
| `browser.command_result` | Extension returned scrape/screenshot |
| `agent.executed` | Item marked done |

## Failure signals

| Symptom | Likely cause |
|---------|----------------|
| No `browser.command` | Hermes didn't invoke `desk-browser` — check terminal toolset + skill |
| `agent.execute_failed` | Hermes timeout or CLI error — check Host logs |
| `screenshot_cap` | Too many ops — new handoff / raise cap for debug |
| Item stays `running` | Execute never completed — check WS connection |

## Rollback

- Deny Waiting proposals if needed
- Close duplicate agent tabs via extension tab group cleanup
- Restart Host with `DESK_AGENT_BACKEND=mock` for stub-only testing
