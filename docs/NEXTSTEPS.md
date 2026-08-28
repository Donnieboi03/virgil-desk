# Virgil Desk — follow-up queue

Portable checklist for Desk work not in the current MVP slice. Check items off as they ship.

## Active

### Auto-execute Agent items

After decompose, automatically run Hermes execute for Agent column items with `status: running` — **off by default** until shipped.

- Config: `hermes.auto_execute_agent` (proposed) in `config/desk.yaml`
- Requires stable execute path + operator escape hatch
- Until then: operator clicks **Run agent** in the panel

### Waiting column — agent tabs on Accept (future)

When the operator **Accept**s a **Waiting** item that needs browser work, provision **one agent duplicate tab** from the handoff human tab (same model as Agent column items).

**For now (MVP):** Accept must **not** create tabs or run browser automation for Waiting items. Current behavior only commits the proposal (e.g. calendar stub) and marks the item done — **intentional no-op** for tab provisioning until this ships.

- [ ] Extension: on Accept, duplicate from `human_tab_id` + `PATCH /v1/items/{id}` with `agent_tab_id` (only when proposal kind needs UI)
- [ ] Host: define which proposal kinds trigger tab provision vs calendar-only commit
- [ ] Tests: accept today creates **zero** new tabs; e2e when shipped

### Real calendar commit on Accept

Replace `booked_stub` with Hermes `gws` calendar create (or equivalent L1 path).

### Inbox scroll depth

Optional multi-page Gmail scroll beyond `handoff_scroll_loops` (config-driven).

## Done (reference)

- Rich handoff: duplicate agent tab + excerpt + screenshot for decompose
- Manual **Run agent** + `POST /v1/items/{id}/execute`
- **`desk-browser`** CLI for Hermes terminal
- **Mark done** for You column items
- **Agent tab provisioning:** one tab per agent item — first item reuses handoff snapshot tab; deduped lock prevents double-provision from `board_patch` + `handoff_result` race

## Links

- [`PRODUCT.md`](PRODUCT.md) — primary flows
- [`HERMES_SETUP.md`](HERMES_SETUP.md) — live Hermes wiring
- [`OPERATOR.md`](OPERATOR.md) — dogfood checklist
