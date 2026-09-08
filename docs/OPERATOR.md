# Operator guide — first live check

## 1. Local smoke test (~30 min)

```bash
# Terminal 1 — Host
cd packages/host
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
desk-host

# Terminal 2 — Extension (repo root)
npm install && npm run build -w @virgil-desk/extension
```

Chrome → `chrome://extensions` → **Load unpacked** → `packages/extension/dist`.

Open any page → Virgil Desk side panel → **Hand off this tab**. Board columns **You / Agent / Waiting** should populate. Hand off briefly duplicates an **ungrouped** tab for scroll/scrape/screenshot, then **closes** it — **Virgil · Agent** appears only when you click **Run agent**.

**Run agent** (Agent column) provisions that item’s agent tab (duplicate into **Virgil · Agent**), then triggers Hermes execute via Host. Default execute driver is **extension Path B** (slim targets + `target_id`; no CDP — see [`BROWSER_LAYER.md`](BROWSER_LAYER.md)). Rollback to harness CDP: `browser.driver: harness` or `DESK_BROWSER_DRIVER=harness` (then enable `chrome://inspect/#remote-debugging` — [`tests/manual/harness_everyday_chrome_checklist.md`](../tests/manual/harness_everyday_chrome_checklist.md)). Cross-branch compare: [`tests/manual/path_compare_checklist.md`](../tests/manual/path_compare_checklist.md).

**Mark done** closes You items. **Accept/Deny** on Waiting proposals.

Events: `~/.virgil-desk/logs/desk_events.jsonl`

```bash
desk-events --run-id <run_id>
```

## 2. Manual checklist (M2+)

Run once with a real tab ([`packages/e2e/README.md`](../packages/e2e/README.md)):

1. Handoff scrapes via a short-lived agent duplicate, then closes it — board cards without open agent tabs until **Run agent**
2. Different URL → `openTab` in **Virgil · Agent** group (default `placement: agent`)
3. Same page work → `duplicateTab`; human tab untouched
4. Post-click `command_result` includes scrape + screenshot
5. **Run agent** on one Agent **root** → provisions that item’s tab only → `browser.command` events in log
6. Mid-flight children: accordion under parent; You/Waiting show minted remainder (`from:` meta)
7. Human remainder URL → `openTab` with `placement: human` (tab outside **Virgil · Agent**, not focused)
8. **Accept** on a Waiting calendar proposal
9. **Mark done** on a You item
10. Reload Chrome — board persists (`storage.local`)

## Hub Q-mapping (Desk)

Virgil Hub allocate-then-handoff (Q1 Do / Q2 Schedule / Q3 Delegate) maps here as **You / Waiting / Agent**. Desk execute mints mid-flight children (Hub Drafts analogue); parent stays open until agent children finish or human remainder is parked.

## 3. Wire Hermes (real agent)

```bash
DESK_AGENT_BACKEND=hermes desk-host
```

- Hermes profile `skills.external_dirs` → this repo's `skills/` ([`examples/hermes/config.snippet.yaml`](../examples/hermes/config.snippet.yaml))
- Load **`desk-browser-bridge`** skill
- Agent calls Host **`POST /v1/browser`** with `"wait": true`

Hermes live decompose is enabled when `DESK_AGENT_BACKEND=hermes` (see [`HERMES_SETUP.md`](HERMES_SETUP.md)).
