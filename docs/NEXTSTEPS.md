# Virgil Desk — follow-up queue

Portable checklist for Desk work not in the current MVP slice. Check items off as they ship.

**North star (success test):** see [`PRODUCT.md`](PRODUCT.md) — hand off → Agent custody tabs while you leave → ping for auth/decide/file → Mark done → Resume, without reconstructing state in chat. Effort bands ~3h / ~6h / ~9h with AI (not calendar).

Deferred product bets (browser-localized Desk, procedures, Hub-shaped context, multi-profile WS): [`BACKLOG.md`](BACKLOG.md).

## Active

### Dual-focus (agent browse + human homework)

Research notes (archive): [`archive/DUAL_FOCUS_RESEARCH.md`](archive/DUAL_FOCUS_RESEARCH.md), [`archive/INTERACTION_LAYERS.md`](archive/INTERACTION_LAYERS.md). Not scheduled until measured spikes.

### Run tab vs per-card cost

Dogfood A/B on a ≥5-item same-site board: Arm A = per-card **Run agent**; Arm B = **Run tab**. Compare `desk-events --summary` cost/tokens/outcomes — results live in chat/PR.

### Real calendar commit on Accept

Replace `booked_stub` with Hermes `gws` calendar create (or equivalent L1 path).

### Inbox / list depth beyond the viewport

Default handoff is **viewport-only** (`handoff_scroll_loops: 0`). Seeing more = change what’s on screen (search / open), not a bigger excerpt. Virtualization + JS-heap limits: [`HANDOFF_CAPTURE.md`](HANDOFF_CAPTURE.md). Optional multi-window harvest or network-list adapters are research — not the product spine.

### Hermes fallback hygiene for Desk

When provider fallbacks fail mid-execute, board `last_error` should show the real API failure (not a bare session id). Keep fallback_providers / model paths healthy for Desk execute models.

- [ ] Audit Hermes profile fallback chain for Desk execute models
- [ ] Confirm board `last_error` surfaces real API failures after fallbacks

### Host-owned rolling execute history

**Shipped (flagged):** `execute.runtime: host_loop` — Host owns the tool transcript, thins Eyes, and **prunes** older tool results (`eyes_keep_last`). Model steps go through **`ModelClient`** (OpenRouter today). Default remains `hermes_oneshot` for Q/A rollback.

- [ ] Gemini-direct `ModelClient` adapter (protocol ready)
- [ ] Default dogfood cutover to `host_loop` after cost A/B

Enable: `execute.runtime: host_loop` in [`config/desk.yaml`](../config/desk.yaml) or `DESK_EXECUTE_RUNTIME=host_loop`. Requires `OPENROUTER_API_KEY`.

### Progress-stop heuristics

Mission-progress stop (URL unchanged K acts / repeated targets) — parked (easy to overfit). Prefer max-turns + stall.

## Done (reference)

- Dual loop UX: notify (`execute.notify_human_attention`), auto Run tab (`execute.auto_run_tab`), Waiting Accept → Agent tab (non-calendar), vault + `upload`/`set_files`, right-click handoff, [`FEASIBILITY.md`](FEASIBILITY.md), `desk-events --summary` execute_run rollup
- Rich handoff: viewport excerpt + screenshot on human tab by default; decompose without leaving agent collage
- Manual **Run agent** + `POST /v1/items/{id}/execute`; **Run tab** one `host_loop` over Agent roots
- **`desk-browser`** CLI for Hermes terminal
- **Mark done** for You column items
- **Agent tab provisioning:** deferred until **Run agent** / Accept (non-calendar) — one tab per running item
- **Shared desk memory:** notepad + last-3 execute summaries injected into execute
- **Decompose hints** + agent status coerced to `proposed`
- **Tab cleanup** on execute end + **off-origin popup quarantine**
- **Act stall detection** (`browser.act_stall_max`)
- **Model cast:** decompose + execute `gemini-3.7-flash`; execute hooks off
- **Slim observe** / clearer Hermes `last_error` / thin desk-browser envelope / `hermes.execute_max_turns`
- **Execute Eyes/Hands (extension)** (`browser.driver: extension`); rollback `harness` CDP

## Links

- [`PRODUCT.md`](PRODUCT.md) — primary flows
- [`BACKLOG.md`](BACKLOG.md) — parking lot (near / mid / Hub-shaped)
- [`HERMES_SETUP.md`](HERMES_SETUP.md) — live Hermes wiring
- [`OPERATOR.md`](OPERATOR.md) — live operator checklist
