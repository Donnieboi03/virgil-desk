# Desk config

**Edit [`desk.yaml`](desk.yaml) only** — no duplicate defaults in Python, tests, or docs.

- Loaded by `desk_host.config.load_config()`
- Schema enforced by dataclasses in `packages/host/desk_host/config.py` (keys must match exactly)
- Optional env overrides: see [`docs/ENV.md`](../docs/ENV.md)
- Human-readable limits table: `python scripts/render-limits-doc.py`
