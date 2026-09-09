# Product notes

Virgil Desk is a **browser allocation desk**: you hand off the active tab, an agent backend decomposes work into three columns, and browser ops run through the extension under explicit policy.

## What it is

- Side-panel board (**You / Agent / Waiting**) backed by `chrome.storage.local`
- Local Host (FastAPI) for handoff, browser commands, proposals, and observability
- Pluggable agent backends: mock (default), Hermes, OpenClaw stub
- **Path B (default):** DOM **Eyes** (slim `interact_targets`, fail-only `eyes_mode` ladder, optional AX/`page_tree`, probes) → **Hands** by `target_id` — see [`BROWSER_LAYER.md`](BROWSER_LAYER.md), [`INTERACTION_LAYERS.md`](INTERACTION_LAYERS.md), and the Eyes/Done framework in [`ARCHITECTURE.md`](ARCHITECTURE.md)
- URL open/construct is a **secondary workaround** (hostile Eyes, human park) — not the primary operating model
- **Verified terminal** page state (expired / already submitted) after Eyes read = **Completed** for review goals — not automatic You mint

## What it is not

- Not a general workflow engine or CRM
- Not a Chrome Web Store product (load unpacked for now)
- Not an unattended “send/submit/pay” agent — proposals require Accept
- Not a URL-first or stealth LinkedIn messaging bot
- Not multi-user

## Primary flows

1. **Hand off** — short-lived ungrouped scrape tab (excerpt + optional screenshot) → backend decomposes → board patch (no Virgil · Agent yet)
2. **Agent browser ops** — `desk-browser` / `POST /v1/browser` → extension **observe → act(`target_id`) → observe** on the agent tab (screenshots skipped by default on Path B execute)
3. **Agent execution** — manual **Run agent** button on Agent column (auto-run planned — see [`NEXTSTEPS.md`](NEXTSTEPS.md))
4. **Waiting proposals** — calendar slots (etc.) → Accept or Deny in the panel
5. **You column** — **Mark done** when human closes the loop (auth walls / soft-help park here). Do **not** expect You cards for agent-verified expired/already-submitted links — those complete on Agent.

## Configuration

Central limits: [`config/desk.yaml`](../config/desk.yaml). See [`ENV.md`](ENV.md) and [`LIMITS.md`](LIMITS.md).

## Observability

Structured events in `~/.virgil-desk/logs/desk_events.jsonl`. Query with `desk-events --run-id <id>`. See [`OBSERVABILITY.md`](OBSERVABILITY.md).
