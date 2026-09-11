# Virgil Desk — Backlog

Items intentionally deferred. **[`NEXTSTEPS.md`](NEXTSTEPS.md)** is the active checklist. **This file is the parking lot.**

When you pick something up, move it into `NEXTSTEPS.md` (or a focused plan) and delete or shrink the entry here.

## Honest scope (keep claims tight)

Desk today allocates work from **bounded intake** — viewport handoff (excerpt + links + screenshot + intent chips), not a central CRM of your whole life. “Unknown” means **latent closures on the page you handed off**, not omniscient discovery. Path B = live Eyes/`target_id` Hands (no debugger). A **procedure catalog** is not Path B; it is a later library of known recipes that may *use* Path B. App connectors (Sheets/CRM) stay out of MVP — agent browser work first. Hub owns briefing / Contacts×Opps / cross-session reconcile.

Spine: hand off → You / Agent / Waiting → agent closes safe subwork without debugger → human remainder. Optional gas (right-click, chips, procedures, vault) must not become a Bardeen-style playbook marketplace.

---

## Near / high fit

### Right-click / selection handoff

- **What:** Chrome `contextMenus` — “Hand off to Virgil” on `page` / `selection` / `link` → same snapshot + decompose path as the panel Hand off. Selection/link scopes intent (“this item”).
- **Why deferred:** Panel handoff is enough for dogfood; menu is a latch, not a new intake model.
- **When to revisit:** After unprompted panel handoffs feel boring; or operators ask for stay-on-page latch without opening the side panel.
- **Not this:** Right-click scrape → Sheets / LinkedIn playbooks (Bardeen lane).

### Feasibility battery (forms, drafts, upload=park)

- **What:** Scored Pass / Partial / Fail / N/A battery — fixture form fill/click/probe; Gmail draft-only (no send); file upload expected Fail or park You until vault/`upload` op exists. Playwright + manual checklist; see conversation plan (F1–F15).
- **Why deferred:** CI smoke (`form.spec.ts`) ≠ product feasibility. Upload cannot piggyback string `fill` (browsers block `input[type=file]` path assignment).
- **When to revisit:** Before claiming Hands coverage beyond text fill; before any resume-vault work.
- **Related:** [`TESTING.md`](TESTING.md), [`packages/e2e/playwright/README.md`](../packages/e2e/playwright/README.md), [`BROWSER_LAYER.md`](BROWSER_LAYER.md).

### Claude-like permission / notify when You needs you

- **What:** Clearer permission ladder language (manual vs auto-with-safety-check vs skip) aligned with Desk policy; OS/`chrome.notifications` (or badge) when a **You** / Waiting card needs the operator — not only a quiet panel update.
- **Why deferred:** Board + Mark done / Accept already work; notify is UX polish after trust in the split.
- **When to revisit:** After dogfood shows missed You cards; or after Claude-in-Chrome comparison where ping-on-remainder is the gap.
- **Steal carefully:** Claude’s modes + consequential-action check — **not** debugger-as-default Hands.

### Optional “I know what I want” chip → one Agent card (scripted lane, not spine)

- **What:** Intent chip / free-text that skips broad decompose and mints **one** Agent item with a clear brief (known chore). Spine stays opportunistic page split; this is the optional scripted lane.
- **Why deferred:** Chips already steer decompose (`All visible` / `This item`); a full bypass risks turning Desk into chat-commanded automation.
- **When to revisit:** When operators repeatedly rewrite decompose output into a single known task; keep labeled as non-spine.

---

## Mid — procedure-ish (not Bardeen clone)

### Mine procedures from obs (Gmail-class) after real Runs

- **What:** Offline (then Host) mining from `desk_events.jsonl` → versioned procedures with Eyes-rebind — contract in [`PROCEDURES.md`](PROCEDURES.md). Goal: cheap one-pass on known loops; AI interprets remainder only.
- **Why deferred:** No runtime router this ship; need trusted Runs + stamps (`item_id` / `op_seq` / `site_fingerprint`) before mining quality exists.
- **When to revisit:** After feasibility + several successful Gmail-class executes; never blind-replay ephemeral `target_id`s.
- **Not this:** Ship a 1000-playbook marketplace.

### Shortcuts to re-run a named procedure on current page

- **What:** `/`-style or command shortcuts that bind a mined/saved procedure to the active tab (re-observe + rebind Hands).
- **Why deferred:** Depends on procedure store existing; Claude/Bardeen shortcuts are command-first — Desk shortcuts should mean “run known recipe,” not replace handoff.
- **When to revisit:** After at least one mined procedure is operator-trusted.

### Document vault for uploads

- **What:** Extension-owned vault (operator uploads resume/PDF/etc.) → agent `upload` / `set_files` injects via `DataTransfer` + owned bytes (Simplify/Jobright pattern), or harness `DOM.setFileInputFiles` on rollback. Eyes mark `kind: file`. Until then: park You / human_remainder for attachments.
- **Why deferred:** String `fill` cannot set file inputs; vault + new op is product surface, not a one-line Hands fix.
- **When to revisit:** After feasibility F11 documents the gap; prefer vault+DataTransfer over debugger file-chooser unless measured otherwise.
- **Not this:** Extend `fill` to accept filesystem paths.

---

## Later / Hub-shaped (don’t pretend Desk has this alone)

### Richer context into decompose (Hub facts, semantic memory already partial)

- **What:** Feed Hub / Graphiti / richer semantic facts into decompose so splits use standing prefs and known people — beyond viewport + thin Desk semantic slice ([`MEMORY.md`](MEMORY.md)).
- **Why deferred:** Desk must prove page-bounded allocation first; Hub remains SoT for life context.
- **When to revisit:** When wrong splits are clearly from missing CRM context, not from bad Eyes.

### App connectors (Sheets / CRM)

- **What:** Push evidence or scraped rows to Sheets, HubSpot, Notion, etc.
- **Why deferred:** Agent browser ops are the MVP actuator; connectors are Bardeen/Lindy/Hub packs.
- **When to revisit:** Only when a concrete dogfood loop requires export — not as a catalog pitch.

### Cross-session “reconcile connections” agent

- **What:** Propose next use of Contacts × Opportunities × Notes across sessions (Hub `NEXTSTEPS` reconcile agent) — distinct from Desk page decompose.
- **Why deferred:** Needs Hub graph + durable identity; Desk handoff is single-page bounded intake.
- **When to revisit:** After Hub reconcile sketch is real; Desk may surface a card, not own the graph.

---

## Explicitly out of spine

- Sales/lead scrape factories, paywall removers, cold WhatsApp/email send packs
- Competing with Claude-in-Chrome as a debugger clicker
- Inventing chores from model imagination (unbounded discovery)

## Links

- [`PRODUCT.md`](PRODUCT.md) — what Desk is / is not
- [`NEXTSTEPS.md`](NEXTSTEPS.md) — active follow-ups
- [`PROCEDURES.md`](PROCEDURES.md) — mine contract only
- [`HANDOFF_CAPTURE.md`](HANDOFF_CAPTURE.md) — viewport-bounded intake
- Virgil Hub backlog (sibling): `Virgil/BACKLOG.md` — Desk pitch + Hub parking lot
