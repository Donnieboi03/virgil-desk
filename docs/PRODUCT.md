# Product notes

Virgil Desk is a **browser allocation desk**: you hand off the active tab, an agent backend decomposes work into three columns, and browser ops run through the extension under explicit policy. Intake is **page-bounded** (viewport handoff), not a full-life CRM — see honest scope in [`BACKLOG.md`](BACKLOG.md).

## What it is

- Side-panel board (**You / Agent / Waiting**) backed by `chrome.storage.local`
- Local Host (FastAPI) for handoff, browser commands, proposals, and observability
- Pluggable agent backends: mock (default), Hermes, OpenClaw stub
- **Run tab** (primary when `execute.runtime: host_loop`) — one Host session walks all proposed Agent roots for the handoff; per-card **Run agent** remains for debug / A/B
- **Eyes/Hands (extension driver, default):** DOM **Eyes** (slim `interact_targets`, fail-only `eyes_mode` ladder, optional AX/`page_tree`, probes) → **Hands** by `target_id` — see [`BROWSER_LAYER.md`](BROWSER_LAYER.md) and Done/park in [`ARCHITECTURE.md`](ARCHITECTURE.md)
- URL open/construct is a **secondary workaround** (hostile Eyes) — not the primary operating model
- **Park You** — auth_gate is tab-first (`agent_tab_id` + Show tab) with URL fallback; **human_remainder** when you must still decide/reply/apply/use docs (not agent-only reads). Auth gates leave the parent **`awaiting_human`** until Mark done → Resume agent
- **Verified terminal** page state (expired / already submitted) after Eyes read = **Completed** for review goals — not automatic You mint
- **Pattern-class clumping** — merge **only** within a same-pattern class (same site + same open→observe→recipe + same human-remainder shape) so redundant fires cost less **without** dropping distinct topics. No target board size — correct coverage first; `decompose_items_max` is a ceiling only. Clump titles may stay short; **`hints.members[]`** carries the visible-row inventory execute must walk before Done. Split when remainders diverge (decide/match/apply vs verify-terminal vs bank check-in vs promo skim). Failure isolation: mint per-subgoal or Partial when one member hits `auth_gate` / empty-stdout / timeout — do not mark the whole clump Done. Gmail is a test surface, not the architecture. Procedure store/router is **docs-only** — [`PROCEDURES.md`](PROCEDURES.md).
## What it is not

- Not a general workflow engine or CRM
- Not a Chrome Web Store product (load unpacked for now)
- Not an unattended “send/submit/pay” agent — proposals require Accept
- Not a URL-first or stealth LinkedIn messaging bot
- Not a Gmail-specific bot (inbox is one test surface)
- Not multi-user
- Not a procedure-store runtime yet (mine contract only)
## Primary flows

1. **Hand off** — viewport excerpt + screenshot on the **human tab** by default (`handoff_scroll_loops: 0`, no duplicate); optional intent chips → backend decomposes → board patch (no Virgil · Agent yet). See [`HANDOFF_CAPTURE.md`](HANDOFF_CAPTURE.md).
2. **Agent browser ops** — `desk-browser` / `POST /v1/browser` → extension **observe → act(`target_id`) → observe** on the agent tab (screenshots skipped by default on extension-driver execute)
3. **Agent execution** — **Run tab** (Agent column header) runs all proposed Agent roots in one `host_loop` session when enabled; per-card **Run agent** / Retry remains for isolation and cost A/B. Auto-run after decompose is still planned — see [`NEXTSTEPS.md`](NEXTSTEPS.md).
4. **Waiting proposals** — calendar slots (etc.) → Accept or Deny in the panel
5. **You column** — **Mark done** when human clears auth/challenge or finishes remainder. Auth-gate Mark done unblocks the parent for **Resume agent** / **Resume tab**. Do **not** expect You cards for agent-verified expired/already-submitted links — those complete on Agent.

## Follow-ups

- Active checklist: [`NEXTSTEPS.md`](NEXTSTEPS.md)
- Parking lot (right-click handoff, feasibility, procedures, vault, Hub-shaped): [`BACKLOG.md`](BACKLOG.md)

## Configuration

Central limits: [`config/desk.yaml`](../config/desk.yaml). See [`ENV.md`](ENV.md) and [`LIMITS.md`](LIMITS.md).

## Observability

Structured events in `~/.virgil-desk/logs/desk_events.jsonl`. Query with `desk-events --run-id <id>`. See [`OBSERVABILITY.md`](OBSERVABILITY.md).
