# Operator guide — first dogfood

## 1. Local dogfood (~30 min)

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

Open any page → Virgil Desk side panel → **Hand off this tab**. Board columns **You / Agent / Waiting** should populate.

Events: `~/.virgil-desk/logs/desk_events.jsonl`

```bash
desk-events --run-id <run_id>
```

## 2. Manual checklist (M2+)

Run once with a real tab ([`packages/e2e/README.md`](../packages/e2e/README.md)):

1. Handoff = snapshot only — no agent tab until the agent needs the page
2. Different URL → `openTab` in **Virgil · Agent** group
3. Same page work → `duplicateTab`; human tab untouched
4. Post-click `command_result` includes scrape + screenshot
5. **Accept** on a Waiting calendar proposal (no Notion)
6. Reload Chrome — board persists (`storage.local`)

## 3. Wire Hermes (real agent)

```bash
DESK_AGENT_BACKEND=hermes desk-host
```

- Hermes profile `skills.external_dirs` → this repo's `skills/` ([`examples/hermes/config.snippet.yaml`](../examples/hermes/config.snippet.yaml))
- Load **`desk-browser-bridge`** skill
- Agent calls Host **`POST /v1/browser`** with `"wait": true`

Hermes `decompose` is still structured/stub — live “think and act” on handoff is the next code slice if dogfood feels too thin.
