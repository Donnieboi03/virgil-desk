# Virgil Desk

**Virgil Desk** is a Chrome extension + local Host that allocates work between **you** and **agents** in the browser you already use.

## Problem

Work arrives in the browser. You need a desk—not another chat—that shows what the agent did and what only you can close, on the page where you work.

## Board

Three columns: **You** | **Agent** | **Waiting**. Board state lives in `chrome.storage.local`. The Host routes handoffs to a configurable agent backend (Hermes, OpenClaw, mock).

## Quick start

```bash
# Host
cd packages/host
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
desk-host

# Extension (separate terminal, from repo root)
npm install
npm run build -w @virgil-desk/extension
# Chrome → chrome://extensions → Load unpacked → packages/extension/dist
```

Default Host: `http://127.0.0.1:8787`

Set agent backend: `DESK_AGENT_BACKEND=mock|hermes|openclaw`

## Docs

- [docs/PRODUCT.md](docs/PRODUCT.md) — product scope and boundaries
- [docs/OPERATOR.md](docs/OPERATOR.md) — first dogfood + Hermes wiring
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- [docs/PROTOCOL.md](docs/PROTOCOL.md)
- [docs/BROWSER_LAYER.md](docs/BROWSER_LAYER.md)
- [docs/AGENT_BACKENDS.md](docs/AGENT_BACKENDS.md)
- [docs/HERMES_SETUP.md](docs/HERMES_SETUP.md) — Hermes profile, decompose, browser tools

## License

MIT
