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

Open any page → Virgil Desk side panel → **Hand off this tab**. Board columns **You / Agent / Waiting** should populate. Hand off duplicates the page into **Virgil · Agent**, scrolls (config), scrapes, and captures a screenshot for Hermes decompose.

**Run agent** (Agent column) triggers Hermes execute via Host. **Mark done** closes You items. **Accept/Deny** on Waiting proposals.

Events: `~/.virgil-desk/logs/desk_events.jsonl`

```bash
desk-events --run-id <run_id>
```

## 2. Manual checklist (M2+)

Run once with a real tab ([`packages/e2e/README.md`](../packages/e2e/README.md)):

1. Handoff duplicates agent tab first — snapshot (excerpt + screenshot) from agent tab, not human tab only
2. Different URL → `openTab` in **Virgil · Agent** group
3. Same page work → `duplicateTab`; human tab untouched
4. Post-click `command_result` includes scrape + screenshot
5. **Run agent** on Agent column → `browser.command` events in log
6. **Accept** on a Waiting calendar proposal
7. **Mark done** on a You item
8. Reload Chrome — board persists (`storage.local`)

## 3. Wire Hermes (real agent)

```bash
DESK_AGENT_BACKEND=hermes desk-host
```

- Hermes profile `skills.external_dirs` → this repo's `skills/` ([`examples/hermes/config.snippet.yaml`](../examples/hermes/config.snippet.yaml))
- Load **`desk-browser-bridge`** skill
- Agent calls Host **`POST /v1/browser`** with `"wait": true`

Hermes live decompose is enabled when `DESK_AGENT_BACKEND=hermes` (see [`HERMES_SETUP.md`](HERMES_SETUP.md)).
