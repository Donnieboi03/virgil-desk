# Architecture

Extension (board SoT in `chrome.storage.local`) ↔ Host (policy + agent router) ↔ AgentBackend (Hermes / OpenClaw / mock).

Memory/RAG lives in agent config only.

## Control surfaces

| Surface | Role |
|---------|------|
| MV3 extension | Board UI, tab pairs, Path B Eyes/Hands inject, WS client |
| Host `:8787` | Handoff, `POST /v1/browser`, mint, execute, events |
| Hermes (default agent) | Decompose + execute via `desk-browser` CLI |
| Config | [`config/desk.yaml`](../config/desk.yaml) — limits pushed to extension on register |

Related: [`BROWSER_LAYER.md`](BROWSER_LAYER.md), [`INTERACTION_LAYERS.md`](INTERACTION_LAYERS.md), [`PROTOCOL.md`](PROTOCOL.md), [`PRODUCT.md`](PRODUCT.md), [`OBSERVABILITY.md`](OBSERVABILITY.md).

---

## Path B Eyes framework (escalation ladder)

Fail-only **Eyes modes** on observe/open/scrape (extension). Field: **`eyes_mode`** (`0|1|2`). This is **not** soft site tiers A–D in BROWSER_LAYER (those stay expectation-only).

```
T0 settle (innerText + targets/links)
  ├─ ready → eyes_mode 0, excerpt as today
  └─ empty → one-shot deep open-shadow text + DIY page_tree
        ├─ promote into scrape_excerpt (≥ min chars) → eyes_mode 1, eyes_empty false
        └─ still empty → eyes_mode 2, eyes_empty true, optional eyes_hints.url_path_hint
```

| Mode | Meaning | Hermes should |
|------|---------|----------------|
| `0` | Default slim Eyes | Act by `target_id` |
| `1` | Promoted deep text / tree excerpt | Treat excerpt as authoritative |
| `2` | Soft URL/title hints only | Do not invent body copy; Partial if no fact |

- Escalate **once** after settle fails — do not stack full HTML + tree + deep dump.
- No screenshot / tab focus in the ladder (`observe_skip_screenshot_default`).
- Implement: `eyesSettle.js`, `eyesEscalate.js`, `deskDeepText` / `deskPageTree` in `interactObserve.bundle.js`, wired in extension `background.js`.
- Caps: `eyes_settle_*`, `eyes_challenge_extra_ms`, `eyes_deep_text_max_chars`, `page_tree_max_*`, `scrape_excerpt_max_chars`.

Measure: `browser.command_result` flags `eyes_mode`, `eyes_empty`; measures `eyes_settle_ms` / `eyes_settle_attempts`; optional `detail.eyes_hints`.

---

## Execute Done semantics

| Outcome | When | Agent action |
|---------|------|--------------|
| **Completed** | Agent-safe work finished **or** Eyes **verified terminal** page (expired / already submitted / deadline passed / not found) for a review/check goal | One-line success summary; stop. **No** You mint |
| **`Partial:`** | Blocked without a verified terminal fact (auth, forbidden, stuck, blank Eyes) | One-line `Partial:`; stop |
| **`awaiting_human`** | Auth/challenge gate parked as You (`park_kind: auth_gate`) | Parent halted until human Marks done → **Resume agent** |
| **Park You (URL-first)** | Last resort — auth wall, forbidden human action still required, soft-help / human remainder | `mint_item` You/Waiting with **`source.url`** (+ `park_kind`). **Never** `openTab placement=human` (policy `human_park_tab_denied`) |

Host gate ([`execute_validation.py`](../packages/host/desk_host/execute_validation.py)):

- Rejects open-only summaries starting with `Observed` / `Opened` **unless** they also claim single-closure / parked / minted / **verified-terminal** language.
- Verified-terminal patterns include: `verified expired`, `already submitted`, `deadline passed`, `expired-or-not-found`, `screening … expired`, `no further action`, etc.
- Rejects “single closure / no further action” when an open You `auth_gate` / `human_remainder` still needs human (unless summary honestly acknowledges parked remainder).

### Resume after You Mark done

1. Agent mints You `auth_gate` → parent status **`awaiting_human`**.
2. Human opens URL from the panel (clickable link / Open) and clears the gate.
3. **Mark done** on that You → parent → **`proposed`** + `resume_ready` + notepad bullet; panel shows **Resume agent** (same execute endpoint). No auto-Hermes this ship.

Prompt/skill: [`prompts/execute_agent_item.md`](../prompts/execute_agent_item.md), [`skills/desk-browser-bridge/SKILL.md`](../skills/desk-browser-bridge/SKILL.md) **1.15.0**.

---

## Idempotency

### Mint (`POST /v1/items/mint`)

Dedupe key: **parent_id + column + normalized `source.url`** (fallback: same title when no URL). Open children only (`proposed`/`running`/`awaiting_human`).

- **Auth gates** (`park_kind: auth_gate`): normalize to **origin + pathname** (drop query) so Cloudflare vs login on the same destination collapses to one You card.
- Hit → return existing item, `idempotent: true`, event `item.minted` with `flags.idempotent_reuse`.
- Helper: [`mint_policy.py`](../packages/host/desk_host/mint_policy.py).

Prefer agents pass `"source": {"url": "…"}` when minting for a specific link. You parks with `park_kind` **require** `source.url`.

### Human park tab (`openTab` + `placement: human`)

**Denied** on the execute path (`human_park_tab_denied`). Extension may still have reuse helpers unused. Park surface is the You card URL in the panel.

---

## Challenge settle patience

During Eyes settle, if scrape url/title/text looks like Cloudflare / “Just a moment” / checking-your-browser, extend budget once by `eyes_challenge_extra_ms` (default 8000) before declaring empty. Measure still reports `eyes_settle_ms` / attempts. See [`BROWSER_LAYER.md`](BROWSER_LAYER.md).

---

## Execute concurrency lock

`POST /v1/items/{id}/execute` refuses a second call while the same `item_id` is in `_executing_item_ids` (**HTTP 409**). Cleared in `finally` after cleanup. Prevents double Hermes runs → double mint / double park (seen on `desk_ecd3c99b026e44ad`).

---

## Hands / tabs (short)

- Agent collage: Virgil · Agent group; act only on agent `tab_id`.
- Never automate `human_tab_id`.
- Park is URL-first You cards (panel Open / link); agent `openTab placement=human` is denied.
- See [`BROWSER_LAYER.md`](BROWSER_LAYER.md) for driver modes and soft site tiers A–D.

---

## How to expand / measure

1. **Eyes quality** — event rate of `eyes_mode` 0/1/2 and `eyes_empty` per host; sample mode-1 excerpts for SPA coverage.
2. **Done vs park** — count `item.minted` column=you vs `agent.executed` with verified-terminal language; expect park to drop for expired links. Track `awaiting_human` / `agent.resume_ready` for gate resume latency.
3. **Idempotency** — `flags.idempotent_reuse` on mint (incl. gate origin+path); policy `human_park_tab_denied` rate.
4. **Concurrency** — 409 rate on execute; should be rare after UI debounce.
5. **Challenge settle** — `eyes_settle_ms` vs budget when challenge markers present; challenge-extended settles.
6. **Ladder growth** — new escalate modes stay fail-only; never dump full HTML into CLI; document here + BROWSER_LAYER + PROTOCOL together.
