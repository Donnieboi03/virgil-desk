# Architecture

Extension (board SoT in `chrome.storage.local`) ↔ Host (policy + agent router) ↔ AgentBackend (Hermes / OpenClaw / mock).

**Hermes** Memory/RAG (`USER.md` / providers) lives in agent config only. **Desk** owns a separate capped memory surface (working notepad, thin episodic, semantic facts) in the extension — see [`MEMORY.md`](MEMORY.md). Host does not own RAG.

## Control surfaces

| Surface | Role |
|---------|------|
| MV3 extension | Board UI, tab pairs, Eyes/Hands inject, WS client, Desk memory SoT |
| Host `:8787` | Handoff, `POST /v1/browser`, mint, execute, desk-memory REST, events |
| Hermes (default agent) | Decompose (+ optional `hermes_oneshot` execute via `desk-browser` CLI) |
| Config | [`config/desk.yaml`](../config/desk.yaml) — limits pushed to extension on register |

**Execute runtime:** `execute.runtime` — `hermes_oneshot` (default) or **`host_loop`** (Host-owned messages + Eyes prune via `ModelClient`; backend-agnostic). With `host_loop`, **Run tab** (`POST /v1/runs/{run_id}/execute`) walks all proposed Agent roots in one session with flat ceilings (`run_max_steps` / `run_steps_per_item`); per-item `POST /v1/items/{id}/execute` remains (`max_steps`). See [`NEXTSTEPS.md`](NEXTSTEPS.md).

Related: [`MEMORY.md`](MEMORY.md), [`BROWSER_LAYER.md`](BROWSER_LAYER.md) (Eyes/Hands SoT), [`PROTOCOL.md`](PROTOCOL.md), [`PRODUCT.md`](PRODUCT.md), [`OBSERVABILITY.md`](OBSERVABILITY.md). Eyes/Hands taxonomy (archive): [`archive/INTERACTION_LAYERS.md`](archive/INTERACTION_LAYERS.md).

---

## Eyes/Hands

Fail-only **`eyes_mode`** `0|1|2` on observe/open/scrape. Ladder, settle/challenge budgets, and caps live in [`BROWSER_LAYER.md`](BROWSER_LAYER.md). This doc owns Done / park / mint / locks only.

Measure (on `browser.command_result`): flags `eyes_mode`, `eyes_empty`, optional `challenge_extended`; measures `eyes_settle_ms` / `eyes_settle_attempts`, optional `inject_ms` / `frame_count`; optional `detail.eyes_hints`. Mine-ready stamps (`item_id`, `op_seq`, `site_fingerprint`, binding hints): [`OBSERVABILITY.md`](OBSERVABILITY.md); procedure join sketch: [`PROCEDURES.md`](PROCEDURES.md).

---

## Execute Done semantics

| Outcome | When | Agent action |
|---------|------|--------------|
| **Completed** | Agent-safe work finished **or** Eyes **verified terminal** page (expired / already submitted / deadline passed / not found) for a review/check goal | One-line success summary; stop. **No** You mint |
| **`Partial:`** | Blocked without a verified terminal fact (auth, forbidden, stuck, blank Eyes) | One-line `Partial:`; stop |
| **`awaiting_human`** | Auth/challenge gate parked as You (`park_kind: auth_gate`) | Parent halted until human Marks done → **Resume agent**. Extension **lends** `agent_tab_id` (ungroup, inactive until Show tab) |
| **Park You (tab-first auth / URL-first remainder)** | Auth wall → same agent tab + `source.url` fallback; **human judgment/use** (decide, reply, apply, use docs) → `human_remainder`; forbidden human action / soft-help | `mint_item` You with **`source.url`** (+ `park_kind`). Auth_gate also stamps **`agent_tab_id`**. **Never** `openTab placement=human`. Host rejects “Single closure / no further action” after only reading **judgment/use** work; **promo/newsletter skim / FYI** may Complete alone |

Host gate ([`execute_validation.py`](../packages/host/desk_host/execute_validation.py)):

- Rejects open-only summaries starting with `Observed` / `Opened` **unless** they also claim single-closure / parked / minted / **verified-terminal** language.
- Verified-terminal patterns include: `verified expired`, `already submitted`, `deadline passed`, `expired-or-not-found`, `screening … expired`, `no further action`, etc.
- Rejects “single closure / no further action” when an open You `auth_gate` / `human_remainder` still needs human (unless summary honestly acknowledges parked remainder).
- Rejects false closure after read-only **judgment/use** (Review/Apply titles, or “Reviewed … picks/profiles …”); allows promo/newsletter **skim / FYI** Completes with no You park.

### Resume after You Mark done

1. Agent mints You `auth_gate` → parent status **`awaiting_human`**; host copies parent **`agent_tab_id`** onto the You card when present.
2. Extension ungroups that agent tab (stays inactive). Human uses panel **Show tab** / `reveal.html` (same tab — no duplicate), clears the gate. Opportunistic / reveal screenshots → `tab.custody`.
3. **Mark done** on that You (optional viewport shot if still on the agent tab) → parent → **`proposed`** + `resume_ready` + `cleared_gates[]` + notepad bullet; panel shows **Resume agent**.
4. **Resume agent** regroups the tab into **Virgil · Agent**. Next execute injects Packet **`resume.cleared_gates`** so Hermes must not remint those URLs. No auto-Hermes this ship.

Prompt/skill: [`prompts/execute_agent_item.md`](../prompts/execute_agent_item.md), [`skills/desk-browser-bridge/SKILL.md`](../skills/desk-browser-bridge/SKILL.md) **1.15.2**.

---

## Mint / park

You parks with `park_kind` **require** `source.url`. Prefer agents pass `"source": {"url": "…"}` when parking a specific link. **`auth_gate`** also receives parent `agent_tab_id` for Show-tab custody.

Host does **not** silently collapse remints — Resume continuity is **Packet state** (`resume.cleared_gates`), not mint idempotency.

### Human park tab (`openTab` + `placement: human`)

**Denied** on the execute path (`human_park_tab_denied`). Auth parks use **Show tab** on the existing agent tab; remainder parks use the You card page URL.

---

## Challenge settle patience

See [`BROWSER_LAYER.md`](BROWSER_LAYER.md) (`eyes_challenge_extra_ms`).

---

## Execute concurrency lock

`POST /v1/items/{id}/execute` refuses a second call while the same `item_id` is in `_executing_item_ids` (**HTTP 409**). Cleared in `finally` after cleanup. Prevents double Hermes runs → double mint / double park.

---

## Hands / tabs (short)

- Agent collage: Virgil · Agent group; act only on agent `tab_id`. Auth park lends that tab (ungroup → Show → Resume regroups).
- Never automate `human_tab_id`.
- Park: auth_gate = tab custody + URL fallback; human_remainder = URL-first You cards; agent `openTab placement=human` is denied.
- See [`BROWSER_LAYER.md`](BROWSER_LAYER.md) for driver modes and soft site tiers A–D.

---

## How to expand / measure

1. **Eyes quality** — event rate of `eyes_mode` 0/1/2 and `eyes_empty` per host; sample mode-1 excerpts for SPA coverage.
2. **Done vs park** — count `item.minted` column=you vs `agent.executed` with verified-terminal language; expect park to drop for expired links. Track `awaiting_human` / `agent.resume_ready` for gate resume latency.
3. **Resume state** — `resume.cleared_gates` on execute after You Mark done; expect remint rate to drop.
4. **Concurrency** — 409 rate on execute; should be rare after UI debounce.
5. **Challenge settle** — `eyes_settle_ms` vs budget when challenge markers present.
6. **Ladder growth** — new escalate modes stay fail-only; never dump full HTML into CLI; document in BROWSER_LAYER + PROTOCOL.
