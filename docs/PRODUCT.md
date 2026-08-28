# Product notes

Virgil Desk is a **browser allocation desk**: you hand off the active tab, an agent backend decomposes work into three columns, and browser ops run through the extension under explicit policy.

## What it is

- Side-panel board (**You / Agent / Waiting**) backed by `chrome.storage.local`
- Local Host (FastAPI) for handoff, browser commands, proposals, and observability
- Pluggable agent backends: mock (default), Hermes, OpenClaw stub
- Extension-driven browser layer: scrape text + `captureVisibleTab` screenshots

## What it is not

- Not a general workflow engine or CRM
- Not a Chrome Web Store product (load unpacked for now)
- Not an unattended “send/submit/pay” agent — proposals require Accept
- Not multi-user

## Primary flows

1. **Hand off** — snapshot active tab → backend decomposes → board patch
2. **Agent browser ops** — `POST /v1/browser` → extension executes on agent tab → scrape + screenshot evidence
3. **Waiting proposals** — calendar slots (etc.) → Accept or Deny in the panel

## Configuration

Central limits: [`config/desk.yaml`](../config/desk.yaml). See [`ENV.md`](ENV.md) and [`LIMITS.md`](LIMITS.md).

## Observability

Structured events in `~/.virgil-desk/logs/desk_events.jsonl`. Query with `desk-events --run-id <id>`.
