# Path compare checklist (way1 harness vs Path B extension)

Run the **same** scenario twice — once on each branch — and fill one metrics row per branch.

| Branch | Driver |
|--------|--------|
| `feat/desk-harness-way1` | `harness` (default on that branch after excerpt-cap commit) |
| `feat/desk-path-b-eyes` | `extension` (Path B default) |

Do **not** merge both methods onto one branch for this compare.

On **way1**, if these files are missing, pull them without switching drivers permanently:

```bash
git checkout feat/desk-path-b-eyes -- tests/manual/path_compare_checklist.md scripts/path_compare_metrics.py
```

## Scenario (fixed)

1. Everyday Chrome open; homework tab selected in window A (or Space 1).
2. Open a stable page (Gmail inbox **or** a local static HTML with links/buttons/form/table).
3. Virgil Desk side panel connected; **Hand off this tab**.
4. Wait for board You/Agent/Waiting.
5. **Run agent** on one Agent-column item (same item title both runs if possible).
6. Stay on homework tab/app during the Run; do not click Chrome.
7. When done or max-turns: note summary + collect metrics.

Optional helper (either branch, after a Run):

```bash
python scripts/path_compare_metrics.py --run-id <run_id>
```

## Metrics table

| Metric | way1 (harness) | path-b (extension) |
|--------|----------------|--------------------|
| Date / Chrome version | | |
| Test page URL | | |
| Observe JSON chars (first observe CLI or `scrape_bytes` + target_count) | | |
| Rough tokens (chars/4) | | |
| Turns used / max-turns hit? | | |
| `act_resolved.used=none` count | | |
| Successful acts | | |
| Homework tab stayed selected? (Y/N) | | |
| Frontmost app stayed yours? (Y/N) | | |
| Wall time (s) | | |
| Notes (misses, stalls) | | |

Frontmost app probe:

```bash
osascript -e 'tell application "System Events" to get name of first process whose frontmost is true'
```

## Pass / fail (operator judgment)

- Path B: no screenshot flicker on homework tab during execute observe.
- way1: may steal focus — record it; do not “fix” dual-focus on harness.
- Token: Path B steady-state observe should be clearly under way1’s uncapped-target / scrape envelope when both use 12k excerpt caps.
