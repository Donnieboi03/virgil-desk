# Virgil Desk — follow-up queue

Portable checklist for Desk work not in the current MVP slice. Check items off as they ship.

Deferred product bets (right-click handoff, feasibility battery, procedures, vault, Hub-shaped context): [`BACKLOG.md`](BACKLOG.md).

## Active

### Dual-focus (agent browse + human homework)

Research notes (archive): [`archive/DUAL_FOCUS_RESEARCH.md`](archive/DUAL_FOCUS_RESEARCH.md), [`archive/INTERACTION_LAYERS.md`](archive/INTERACTION_LAYERS.md). Not scheduled until measured spikes.

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

### Inbox / list depth beyond the viewport

Default handoff is **viewport-only** (`handoff_scroll_loops: 0`). Seeing more = change what’s on screen (search / open), not a bigger excerpt. Virtualization + JS-heap limits: [`HANDOFF_CAPTURE.md`](HANDOFF_CAPTURE.md). Optional multi-window harvest or network-list adapters are research — not the product spine.

### Hermes fallback hygiene for Desk

When provider fallbacks fail mid-execute, board `last_error` should show the real API failure (not a bare session id). Keep fallback_providers / model paths healthy for Desk execute models.

- [ ] Audit Hermes profile fallback chain for Desk execute models
- [ ] Confirm board `last_error` surfaces real API failures after fallbacks

### Host-owned rolling execute history

True Packet/Eyes/Hands rebuild each Hermes call (host loop or mid-session history rewrite) — not shipped. Today: thin CLI envelopes + `execute_max_turns` only.

- [ ] Host re-prompt loop or Hermes compression profile dedicated to Desk
- [ ] Drop/collapse prior tool messages inside one session

### Progress-stop heuristics

Mission-progress stop (URL unchanged K acts / repeated targets) — parked (easy to overfit). Prefer max-turns + stall.

## Done (reference)

- Rich handoff: viewport excerpt + screenshot on human tab by default (no duplicate unless scroll loops > 0); decompose without leaving agent collage
- Manual **Run agent** + `POST /v1/items/{id}/execute`
- **`desk-browser`** CLI for Hermes terminal
- **Mark done** for You column items
- **Agent tab provisioning:** deferred until **Run agent** — one tab per running item; no board_patch-time duplicates; no handoff snapshot reuse
- **Shared desk memory:** `virgil_desk_memory_v1` notepad + last-3 execute summaries injected into execute
- **Decompose hints** + agent status coerced to `proposed` (no fake done)
- **Tab cleanup** on execute end + **off-origin popup quarantine** during execute
- **Act stall detection** (`browser.act_stall_max`) to stop click spirals
- **Model cast:** decompose + execute `gemini-3.7-flash`; execute hooks off
- **Slim observe:** same-URL omit full excerpt; URL-change capped follow-up
- **Clearer execute `last_error`** from Hermes stderr / API snippets
- **Thin desk-browser CLI envelope** (no screenshot base64 into Hermes transcript)
- **Execute `--max-turns`** via `hermes.execute_max_turns` (default 40)
- **Execute Path B** (`browser.driver: extension`) — slim targets / AX `page_tree` / probes; Hands `target_id`; rollback `harness` CDP on everyday Chrome

## Links

- [`PRODUCT.md`](PRODUCT.md) — primary flows
- [`BACKLOG.md`](BACKLOG.md) — parking lot (near / mid / Hub-shaped)
- [`HERMES_SETUP.md`](HERMES_SETUP.md) — live Hermes wiring
- [`OPERATOR.md`](OPERATOR.md) — live operator checklist
