# Virgil Desk — Backlog

Items intentionally deferred. **[`NEXTSTEPS.md`](NEXTSTEPS.md)** is the active checklist. **This file is the parking lot.**

When you pick something up, move it into `NEXTSTEPS.md` (or a focused plan) and delete or shrink the entry here.

## Honest scope (keep claims tight)

Desk today allocates work from **bounded intake** — viewport handoff (excerpt + links + screenshot + intent chips), not a central CRM of your whole life. “Unknown” means **latent closures on the page you handed off**, not omniscient discovery. Default Hands = live Eyes/`target_id` Hands (no debugger). A **procedure catalog** is not the Eyes/Hands driver; it is a later library of known recipes that may *use* Eyes/Hands. App connectors (Sheets/CRM) stay out of MVP — agent browser work first. Hub owns briefing / Contacts×Opps / cross-session reconcile.

Spine: hand off → You / Agent / Waiting → agent closes safe subwork without debugger → human remainder. Optional gas (right-click, chips, procedures, vault) must not become a Bardeen-style playbook marketplace.

---

## Near / high fit

### Browser-localized Desk (optional Host-less path)

- **What:** Keep SoT in the extension (`chrome.storage.local` board/memory/vault/logs) and run the tool loop **in-browser**: OpenRouter `fetch` from an **offscreen document** (loop owner), service worker for Eyes/Hands + policy gate. Host (`:8787` / Hermes CLI / JSONL on disk) becomes optional packaging, not required for the spine.
- **Why deferred:** Current dogfood is Host + `host_loop`; MV3 needs an explicit offscreen owner (SW alone suspends). Port of `host_loop` / policy / prune / caps is a real project; observability export replaces `desk-events` CLI.
- **When to revisit:** When portability (no local daemon) matters more than Hermes CLI + file logs; or after multi-profile WS pain makes “each profile is its own Desk” the preferred model.
- **Not this:** Put a 200-step run only in the service worker; fake SW immortality hacks for CWS.

### Optional “I know what I want” chip → one Agent card (scripted lane, not spine)

- **What:** Intent chip / free-text that skips broad decompose and mints **one** Agent item with a clear brief (known chore). Spine stays opportunistic page split; this is the optional scripted lane.
- **Why deferred:** Chips already steer decompose (`All visible` / `This item`); a full bypass risks turning Desk into chat-commanded automation.
- **When to revisit:** When operators repeatedly rewrite decompose output into a single known task; keep labeled as non-spine.

### Multi-profile Host WS routing

- **What:** Host keeps one WebSocket per extension `client_id` and routes browser/board/memory by `run_owner[run_id]` so School + Personal Chrome profiles don’t steal each other’s socket.
- **Why deferred:** Ops workaround exists (one profile connected at a time); code fix is small but not shipped yet.
- **When to revisit:** Before regular dual-profile dogfood against one Host; or when browser-localized Desk makes Host WS moot.
- **Ops until then:** Only one Chrome profile with Desk loaded / connected to `:8787` (disable or remove the extension on the other profile, or quit that Chrome entirely).

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
