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
4. Post-act `command_result` includes `tab_id` / `url` / optional scrape excerpt; Path B **observe** defaults to **no** screenshot (`skip_screenshot`)
5. **Run agent** on one Agent **root** → provisions that item’s tab only → `browser.command` events in log
6. Mid-flight children: Agent accordion under parent; You/Waiting nest parks under **From: {parent}** groups (parent may live in Agent)
7. Human remainder / auth gate → `mint_item` You with **`source.url`** (panel Open / link). **Do not** `openTab placement=human` (host denies). Auth gates leave parent **`awaiting_human`** until Mark done → **Resume agent**.
8. Auth wall / empty Eyes with no verified fact (`eyes_empty` / `eyes_mode: 2`) → You mint + soft-help or `Partial:`; do not invent page copy from URL alone (`eyes_hints` soft only). Mode `1` promoted excerpt is authoritative. **Verified terminal** (expired / already submitted) after Eyes = Agent **Completed** — not park. Framework: [`ARCHITECTURE.md`](ARCHITECTURE.md).
9. Concurrent double **Run agent** on one item → HTTP 409. After Mark done on an auth gate, **Resume agent** gets Packet `resume.cleared_gates` — agent must not remint those URLs.
10. **Accept** on a Waiting calendar proposal
11. **Mark done** on a You item
12. Reload Chrome — board persists (`storage.local`)
13. Failed ops show `error` / `tab_id` / `url` in `desk-events --summary`
14. When backends expose usage, `desk-events --summary` may include rolled-up `cost_usd` / token totals (optional; omit when absent)

## 3. Wire Hermes (real agent)

```bash
DESK_AGENT_BACKEND=hermes desk-host
```

- Hermes profile `skills.external_dirs` → this repo's `skills/` ([`examples/hermes/config.snippet.yaml`](../examples/hermes/config.snippet.yaml))
- Load **`desk-browser-bridge`** skill
- Agent calls Host **`POST /v1/browser`** with `"wait": true`

Hermes live decompose is enabled when `DESK_AGENT_BACKEND=hermes` (see [`HERMES_SETUP.md`](HERMES_SETUP.md)).
