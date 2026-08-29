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

### Hermes fallback hygiene for Desk

OpenRouter in-flight **402** (budget) and native Gemini fallback **404** currently leave a weak board `last_error` / useless `session_id`-only stdout. Desk now surfaces stderr snippets when present; still need provider/fallback config hygiene so execute does not silently fall through broken fallbacks.

- [ ] Audit `virgil-executor` fallback_providers for Desk `-m` models
- [ ] Avoid OpenRouter 402 mid-run without a working Gemini native path
- [ ] Confirm board `last_error` shows the real API failure after fallbacks

### Host-owned rolling execute history

True Packet/Eyes/Hands rebuild each Hermes call (host loop or mid-session history rewrite) — not shipped. Today: thin CLI envelopes + `execute_max_turns` only.

- [ ] Host re-prompt loop or Hermes compression profile dedicated to Desk
- [ ] Drop/collapse prior tool messages inside one session

### Progress-stop heuristics

Mission-progress stop (URL unchanged K acts / repeated targets) — parked (easy to overfit). Prefer max-turns + stall.

## Done (reference)

- Rich handoff: duplicate agent tab + excerpt + screenshot for decompose
- Manual **Run agent** + `POST /v1/items/{id}/execute`
- **`desk-browser`** CLI for Hermes terminal
- **Mark done** for You column items
- **Agent tab provisioning:** one tab per agent item — first item reuses handoff snapshot tab; deduped lock prevents double-provision from `board_patch` + `handoff_result` race
- **Shared desk memory:** `virgil_desk_memory_v1` notepad + last-3 execute summaries injected into execute
- **Decompose hints** + agent status coerced to `proposed` (no fake done)
- **Tab cleanup** on execute end + **off-origin popup quarantine** during execute
- **Act stall detection** (`browser.act_stall_max`) to stop click spirals
- **Model cast:** decompose `gemini-3.1-flash-lite` / execute `gemini-3.7-flash`; execute hooks off
- **Slim observe:** same-URL omit full excerpt; URL-change capped follow-up
- **Clearer execute `last_error`** from Hermes stderr / API snippets
- **Thin desk-browser CLI envelope** (no screenshot base64 into Hermes transcript)
- **Execute `--max-turns`** via `hermes.execute_max_turns` (default 12)
- **Execute via browser-harness Way 1** (`browser.driver: harness`) — everyday Chrome cookies; sticky CDP target; rollback `extension`

## Links

- [`PRODUCT.md`](PRODUCT.md) — primary flows
- [`HERMES_SETUP.md`](HERMES_SETUP.md) — live Hermes wiring
- [`OPERATOR.md`](OPERATOR.md) — live operator checklist
