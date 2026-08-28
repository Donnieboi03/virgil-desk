# Virgil Desk — follow-up queue

Portable checklist for Desk work not in the current MVP slice. Check items off as they ship.

## Active

### Auto-execute Agent items

After decompose, automatically run Hermes execute for Agent column items with `status: running` — **off by default** until shipped.

- Config: `hermes.auto_execute_agent` (proposed) in `config/desk.yaml`
- Requires stable execute path + operator escape hatch
- Until then: operator clicks **Run agent** in the panel

### Real calendar commit on Accept

Replace `booked_stub` with Hermes `gws` calendar create (or equivalent L1 path).

### Inbox scroll depth

Optional multi-page Gmail scroll beyond `handoff_scroll_loops` (config-driven).

## Done (reference)

- Rich handoff: duplicate agent tab + excerpt + screenshot for decompose
- Manual **Run agent** + `POST /v1/items/{id}/execute`
- **`desk-browser`** CLI for Hermes terminal
- **Mark done** for You column items

## Links

- [`PRODUCT.md`](PRODUCT.md) — primary flows
- [`HERMES_SETUP.md`](HERMES_SETUP.md) — live Hermes wiring
- [`OPERATOR.md`](OPERATOR.md) — dogfood checklist
