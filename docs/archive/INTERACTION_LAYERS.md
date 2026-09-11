# Eyes / Hands — interaction mental model

**Audience:** Operator + agents working on Virgil Desk (or Virgil Hub L2).  
**Status:** **Archive** — reference taxonomy (Aug 29, 2026). Not living product SoT. Living Eyes/Hands: [`../BROWSER_LAYER.md`](../BROWSER_LAYER.md).
**Related:** [`DUAL_FOCUS_RESEARCH.md`](DUAL_FOCUS_RESEARCH.md), [`../BROWSER_LAYER.md`](../BROWSER_LAYER.md).

Desk (and harness-style agents) split browser work into two jobs:

```text
Eyes  — what to hit / what changed     Hands — how to deliver the action
─────────────────────────────          ────────────────────────────────
DOM scrape / AX tree                   DOM synthetic click / fill
Screenshot + vision                    CDP Input (x,y / key)
interact_targets map                   OS mouse / keyboard (CUA)
```

**Decision** (Eyes) and **dispatch** (Hands) are independent. Vision does not click — it only chooses a target; something else must deliver. “CDP” is not one interaction type — it is a **pipe** that can carry Eyes (Page/AX/DOM) and Hands (Input) separately.

---

## 1. Stack overview

| Layer | What it is | Typical Desk / Virgil use |
|-------|------------|---------------------------|
| **DOM / page JS** | Content script or `Runtime.evaluate` → `el.click()`, synthetic `MouseEvent`, `set_field` | Extension driver (no debugger); fallback Hands |
| **CDP Input** | `Input.dispatchMouseEvent` / `KeyEvent` / `insertText` | browser-harness `click_at_xy`; Desk `driver: harness` |
| **CDP Eyes / structure** | `Page.captureScreenshot`, `Accessibility.*`, `DOM.getBoxModel` | Harness screenshots; optional AX (unused today) |
| **CDP Target / focus** | `activateTarget`, `bringToFront`, attach | Focus policy — not a click type |
| **Accessibility (AX)** | Computed role/name tree | Finder for Hands; Stagehand-style |
| **Vision** | Model reads PNG → `{x,y}` or Set-of-Marks id | Decision only |
| **OS / desktop** | Real pointer via Accessibility / computer-use | Virgil L3 last resort |

Trust / focus (rough):

| Hands | Input trust | Typical focus steal |
|-------|-------------|---------------------|
| DOM synthetic | Low (`isTrusted: false`) | Low |
| CDP Input | High | High (often needs active tab) |
| OS | Highest | Highest (frontmost app) |

---

## 2. Eyes systems (perception)

### 2.1 DOM scrape / text excerpt

| | |
|--|--|
| **Mechanism** | `innerText`, links, optional WebMarker / interact_targets labels |
| **Desk today** | Extension observe; harness returns short `page_info` + excerpt |
| **Pros** | Cheap tokens; works in background more often than screenshots; no vision model |
| **Cons** | Misses canvas/WebGL; brittle labels; 80-target caps; stale between observe and act |
| **Cost** | Low $ (text only); med latency if large excerpt; high thrash cost if agent re-observes forever |
| **Dual-focus** | Usually fine without activating tab |

### 2.2 Interact targets / Set-of-Marks (SoM)

| | |
|--|--|
| **Mechanism** | Numbered overlays on clickable elements → agent picks `target_id` |
| **Desk today** | Extension observe (`interact_targets`); harness path currently empty targets |
| **Pros** | Grounds clicks without raw coordinate guessing; good for dense text UIs |
| **Cons** | Cap (e.g. 80) drops off-screen/out-of-slice targets; text match is naive; needs fresh observe |
| **Cost** | Med — larger JSON every observe; no vision $ if screenshots stripped |
| **Dual-focus** | Building the map is JS — OK; screenshot-with-marks may need visible tab |

### 2.3 Accessibility tree (AX)

| | |
|--|--|
| **Mechanism** | CDP `Accessibility.getFullAXTree` / `queryAXTree` (needs debugger/CDP attach) |
| **Desk today** | Unused (DOM `aria-*` heuristics only) |
| **Pros** | Stable role + computed name; Stagehand moved here for noise reasons |
| **Cons** | Bad ARIA → empty names; canvas has no AX; solves **finding**, not clicking |
| **Cost** | Med — tree dump tokens; debugger attach cost (infobar if extension) |
| **Dual-focus** | Observe often works background; Hands still separate |

### 2.4 Screenshot / vision

| | |
|--|--|
| **Mechanism** | PNG via `captureVisibleTab` or CDP `Page.captureScreenshot` → VLM |
| **Desk today** | Extension handoff image; execute CLI strips base64 (dims only) |
| **Pros** | Site-agnostic; sees overlays humans see; SoM+vision is strong grounding |
| **Cons** | Occluded/background tabs may hang or return stale frames; DPR/CSS pixel math; token burn |
| **Cost** | High $ and latency per turn if model sees pixels; dim-only is cheap but blind |
| **Dual-focus** | Hard — compositor often wants active/visible tab |

### 2.5 Vision as decision (not Eyes alone)

Vision sits **on top** of screenshot Eyes: model emits coords or mark id. Cost is **vision tokens × turns**. Pair with CDP Input Hands for harness-style, or with DOM Hands if dual-focus wins over fidelity.

---

## 3. Hands systems (dispatch)

### 3.1 DOM synthetic (page JS)

| | |
|--|--|
| **Mechanism** | `el.click()`, `MouseEvent`, `elementFromPoint`, `fill` via DOM |
| **Desk today** | Extension `interactBundle` path |
| **Pros** | No debugger banner; no remote-debugging Allow; lower focus steal; fast |
| **Cons** | `isTrusted: false`; iframes/shadow/compositor miss; anti-bot / strict editors |
| **Cost** | Low $; low latency; high **miss rate** → more turns (hidden $) |
| **Dual-focus** | Best Hands candidate for same-window homework + Gmail **if** site accepts untrusted events |

### 3.2 CDP Input (compositor)

| | |
|--|--|
| **Mechanism** | `Input.dispatchMouseEvent` / key / `insertText` |
| **Desk today** | Harness `click_at_xy`, `press_key`, fill helpers |
| **Pros** | Trusted input; pierces many iframe/shadow cases; smoother than synthetic DOM |
| **Cons** | Inactive tab often no-ops; `activateTarget` steals focus; yellow banner if via `chrome.debugger` |
| **Cost** | Low $ per click; **high focus cost**; attach/Allow ops tax |
| **Dual-focus** | Main tension — fidelity vs steal (see [`DUAL_FOCUS_RESEARCH.md`](DUAL_FOCUS_RESEARCH.md)) |

### 3.3 CDP Runtime → DOM Hands

| | |
|--|--|
| **Mechanism** | CDP `Runtime.evaluate` runs the same synthetic click/fill as §3.1 |
| **Pros** | Same pipe as harness; can avoid Input domain |
| **Cons** | Still untrusted DOM events; not “CDP click” in the trusted sense |
| **Cost** | Low $; same miss profile as DOM |
| **Dual-focus** | Same as DOM Hands |

### 3.4 Fill / type variants (not “click” but Hands)

| Variant | Mechanism | When |
|---------|-----------|------|
| **DOM `set_field`** | Set `.value` + `input`/`change` | Fast; framework-friendly; preferred for plain fields |
| **CDP key typing** | `press_key` / `insertText` per char | Autocomplete, editors that need keystrokes |
| **AX-assisted fill** | Find by role/name → then set_field or type | Better finder, same Hands options |

Cost: `set_field` ≪ per-char typing (latency + turns).

### 3.5 OS / computer-use (L3)

| | |
|--|--|
| **Mechanism** | OS-level mouse/keyboard to frontmost window |
| **Desk today** | Not used; Virgil Hub L3 disabled for unattended |
| **Pros** | Native dialogs, non-DOM UI, last resort |
| **Cons** | Needs frontmost Chrome; pixel/DPR; slow; not dual-focus |
| **Cost** | High latency + vision loop $; high focus steal |
| **Dual-focus** | Antithetical — you are the OS cursor |

---

## 4. Cost matrix (compare before picking)

Rough orders of magnitude for **one observe→act cycle** on Desk-like work. “Hidden $” = extra turns from misses.

| System | $ / cycle | Latency | Focus steal | Reliability on hard UIs | Dual-focus fit |
|--------|-----------|---------|-------------|---------------------------|----------------|
| DOM Eyes + DOM Hands | Low | Low | Low | Low–med | **Best** |
| SoM / targets + DOM Hands | Low–med | Med | Low | Med | Good |
| AX Eyes + CDP Input Hands | Med | Med | High* | High | Poor* |
| Screenshot dims only + CDP Input | Low $ / blind | Med | High* | Med–high | Poor* |
| Vision Eyes + CDP Input | **High** | High | High* | High if clicks land | Poor* |
| Vision Eyes + OS Hands | **Highest** | Highest | Highest | High | Worst |

\*CDP Input often requires active tab → steal, unless spikes (`activate=False`) prove otherwise.

**Token trap:** Cheap Hands + blind Eyes → agent thrash (Desk dogfood: `used:none` until max-turns). Expensive vision every turn → OpenRouter shock. Prefer **cheap Eyes that are good enough** + **Hands that land**, then measure miss rate.

---

## 5. Pros / cons cheat sheet

| Pairing | Pros | Cons |
|---------|------|------|
| **DOM + DOM** (classic extension) | Dual-focus friendly; no debugger | Misses on Gmail-class UIs |
| **SoM + DOM** | Better grounding than raw text | Cap/stale targets; still untrusted click |
| **AX + CDP Input** | Strong finder + trusted click | Debugger/CDP + focus; AX gaps |
| **Vision + CDP Input** (harness-style) | Site-agnostic; smooth clicks | $ + focus steal; DPR math |
| **Any Eyes + OS** | Escapes browser limits | Not dual-work; L3 only |
| **Second window + CDP Input** | Same cookies; human window stays focused | Not same-window; product packaging |

---

## 6. Desk defaults (where we are)

| Phase | Eyes | Hands | Driver |
|-------|------|-------|--------|
| Handoff / decompose | Extension scrape + screenshot | — | Extension |
| Execute (default / extension) | slim targets + optional `page_tree` + excerpt omit | DOM `target_id` | `browser.driver: extension` |
| Execute (rollback) | dims / scrape; empty targets | CDP Input (`x,y` / selector) | `browser.driver: harness` |

**Focus policy** (`activateTarget`) applies to harness only. Eyes/Hands skips execute screenshots by default so `captureVisibleTab` does not steal the visible tab.

---

## 7. How to choose (short)

1. **Need dual-focus (homework + Gmail)?** Prefer DOM Hands and/or agent in a **second window**; only bet on CDP Input without activate after measured spikes.
2. **Need clicks to land on hard UI?** Prefer CDP Input; accept focus cost or isolate to another window/Space.
3. **Need site-agnostic grounding?** Vision or SoM Eyes — budget tokens and max-turns.
4. **Need native OS UI?** OS Hands — not Desk’s default path.

When comparing two `run_id`s after a Hands/Eyes change, look at: click miss rate (`act_resolved.used`), turns to done, focus steal (tab + frontmost app), and $ / run.
