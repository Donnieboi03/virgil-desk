# Dual-focus research — Virgil Desk

**Audience:** Donovan (operator / CS founder).  
**Status:** Research synthesis (Aug 29, 2026). Not a build plan until feasibility atoms pass.  
**Product stake:** Desk’s value is **dual-work** — agent finishes Gmail (or similar) while you do homework. Focus-steal fights that promise.

Swarm lenses: CDP background semantics, MV3 `chrome.debugger`, prior-art contradictions, architecture cuts, Desk/harness activate audit ([codebase TT](0c3f3098-7253-49c4-903e-5fdb3e1f625a)).

---

## 1. Problem statement

When Desk execute drives everyday Chrome via **browser-harness Way 1**, each op typically **activates** the agent tab (`Target.activateTarget` via default `switch_tab`). Chrome then pulls **tab and often OS window focus** to the agent. You cannot stay in a homework tab/window without fighting the agent. Dual-focus fails even when clicks are “smoother.”

**Core question:** Can we keep **real-session cookies + reliable act/observe** without making the agent tab (or Chrome app) frontmost on every step?

---

## 2. What already exists

### Local code (build-on)

| Surface | Behavior today | Dual-focus impact |
|---------|----------------|-------------------|
| Desk `harness_backend.py` | Generated scripts call `switch_tab(tid)` **without** `activate=False` before every op + screenshot | Forces activate path |
| browser-harness `switch_tab(..., activate=True)` default | Calls `Target.activateTarget` | Tab to front |
| browser-harness `activate=False` / `BH_NO_ACTIVATE` | Attach without activate; createTarget background | Exists — **Desk does not use it yet** |
| Extension `screenshotTab` | `tabs.update(active:true)` → `captureVisibleTab` → restore prior tab | Brief flicker; restores human tab |
| Extension agent provisioning | `duplicate` / `create` with `active: false` | Good for creation; not for CDP execute |
| Extension manifest | No `debugger` permission | Board/handoff only for dual-focus CDP |

### Prior art (conflicting)

| Claim / product | Says | Caveat |
|-----------------|------|--------|
| Marketing / some bridges (dev.to, krawlify-relay) | Background tabs / `active:false` → focus never stolen | Often about **creating** tabs, not trusted Input on already-background tabs |
| chrome-bridge-mcp | Chrome **auto-focuses** before synthesized Input or click no-ops | Directly contradicts “debugger = no steal” |
| Chromium [devtools-protocol#89](https://github.com/ChromeDevTools/devtools-protocol/issues/89) | `Input.dispatchMouseEvent` to inactive tabs not really supported | Long-standing |
| Cua Driver | Partial “full-background” via nav / DOM / ref text; trusted pointer **activates on macOS/Linux** | Closest honest doc; platform-gated |
| Stagehand | `activateTarget` raises Chrome on macOS | Skip redundant activate ≠ background drive |
| Playwright MCP extension | Often `tabs.update(active)` + window focus | Steal by design in places |
| browser-harness PR / `BH_NO_ACTIVATE` | Reduce activate on create/switch | Not a proof that `click_at_xy` works quiet |

**Implication:** Treat “extension debugger unlocks dual-focus trusted clicks” as **unproven / likely false** for macOS headed Chrome until you measure it. Extension still helps for **attach transport** and product UX — not magic for Input.

---

## 3. Problem dissection (atoms)

| Atom | Question | Why it matters | Depends on |
|------|----------|----------------|------------|
| **P0** | Does Desk execute today steal tab and/or OS focus? | Baseline metric | — |
| **A1** | Can CDP `Page.captureScreenshot` succeed on a never-activated headed tab? | Eyes without steal | P0 |
| **A2** | Can `Input.dispatchMouseEvent` affect a non-active tab without activate/bringToFront? | Trusted Hands without steal | P0 |
| **A3** | On macOS, does `activateTarget` bring **Chrome.app** to front? | Homework in another app/window | P0 |
| **B3** | Does `chrome.debugger` Input alone force-activate? | Extension path hypothesis | A2 |
| **C2** | Does harness `switch_tab(tid, activate=False)` + `click_at_xy` work without steal? | Cheapest Desk change | A2, harness |
| **C3** | Is DOM/`Runtime.evaluate` click (`isTrusted:false`) enough for Gmail? | Fallback if trusted Input needs activate | A2 fail |
| **W1** | Same-window background create/attach only | Softens but may not fix Input | A1–A2 |
| **W2** | Second Chrome **window** same profile | Human window never selected | Cookies shared |
| **W3** | Park agent window on another macOS Space | High dual-focus UX | W2 |
| **W4** | Isolated Desk profile | Max isolation; cookies diverge | Product choice |
| **B2** | Yellow debugger infobar acceptable? | UX tax if extension debugger | Product |
| **E1** | Extension restore-after-screenshot enough for dual-focus? | Already partially true for handoff | P0 |

Atoms are **testable**; do not bundle “fix dual-focus” as one epic.

---

## 4. Feasibility test battery

Run these as **manual or scripted spikes** with pass/fail written down. Prefer macOS headed everyday Chrome (your real dual-focus machine).

| ID | Experiment | Setup | Pass | Fail | Est. | Risk |
|----|------------|-------|------|------|------|------|
| **P0** | Run Desk agent; stay in homework tab; log whether agent tab becomes selected and whether Chrome becomes frontmost app | Desk harness Way 1, Gmail agent tab | Human tab stays selected **and** another app can stay frontmost | Either flips | 0.5h | Low |
| **C2** | Patch/spike harness script: `switch_tab(tid, activate=False)` then `click_at_xy`; watch focus | Same as P0 | Click lands **and** no tab/OS steal | Click no-op **or** steal | 2–4h | Med — may need harness env `BH_NO_ACTIVATE` |
| **A1** | Attach CDP, never activate, `captureScreenshot` on agent tab | Harness or small Python | PNG returns &lt;2s | Hang/timeout | 1–2h | Med |
| **A2** | Same as C2 but isolate Input only (no Desk) | Minimal harness script | Event changes DOM without activate | No effect until activate | 1–2h | Low |
| **A3** | From Terminal (Chrome not front): `activateTarget` on a tab | CDP only | Frontmost stays Terminal | Chrome jumps forward | 0.5h | Low |
| **C3** | Gmail: synthetic DOM click vs CDP Input on same control | Agent tab | DOM path opens thread reliably | Gmail ignores untrusted | 2–4h | Med — site-specific |
| **B3/C4** | Optional: extension `chrome.debugger` Input with tab inactive | Dev unpacked + debugger perm | Input works, tab stays inactive | Auto-focus or no-op | 4–8h | High — CWS later |
| **W2** | Agent in second window same profile; human window focused | Chrome → New Window; harness sticky target in agent window | Homework window never loses selection during Run | Focus jumps to agent window | 2–4h | Low eng, med product |
| **W3** | Put agent window on Space 2; homework Space 1 | Manual Spaces | You never see agent Space during Run | Mission Control thrash / focus | 1–2h + checklist | Flaky automation |
| **E1** | Time extension screenshot flicker (activate+restore) during handoff only | Extension path | Homework restored &lt;300ms; acceptable | Stays on agent / OS steal | 1h | Low |

**Do not** start a dual-focus rewrite until **P0 + C2 + A1** are logged.

---

## 5. Recommended build order (DAG)

```text
P0 (measure steal)
 ├── C2 / A2 (activate=False + trusted click)
 │     ├── pass → wire Desk harness to activate=False; re-measure P0
 │     └── fail → C3 (DOM Hands) and/or W2 (second window)
 ├── A1 (background screenshot)
 │     ├── pass → Eyes without activate
 │     └── fail → keep CDP shot after rare activate, or canvas/DOM eyes, or W2
 ├── A3 (macOS app focus)
 │     └── if steal-app → W2/W3 even if tab-level activate=False works
 └── only if still need same-window trusted Input:
       B3 extension debugger spike → else accept W2 as product shape
```

**Product sequencing (honest):**

1. **Ship dual-focus via W2 (+ optional W3)** if C2 fails — still same cookies, different window. Matches “homework while Gmail” without lying about Chromium Input.
2. **Use C2/C3** to reduce steal when same-window is required.
3. **Treat same-window trusted CDP as R&D**, not a near-term milestone.

---

## 6. Hints for Donovan (background: CS BS/MS, Engevity cofounder)

### Cleanly tackle now (your wheelhouse)

- **Instrument P0** — you already live in Desk events / `run_id`; add focus probes (frontmost app, selected tab id) around execute. Product-minded measurement.
- **C2 harness flag** — small, local, reversible (`activate=False` in `harness_backend` scripts / `BH_NO_ACTIVATE`). Classic systems spike.
- **W2 second window** — product + ops design you already use for Virgil Chrome lanes; less Chromium theology, more UX packaging (“Agent window” vs “Homework window”).
- **C3 Gmail DOM vs Input** — domain experiment on *your* workflow; Engevity/ops taste for “good enough.”
- **Read and map** `helpers.py` `switch_tab` / Desk `harness_backend.py` — code is already in-tree; no new framework.

### Learn more before deep diving

| Topic | Why | How to learn efficiently |
|-------|-----|---------------------------|
| CDP **compositor / occluded tabs** | Explains A1 hangs | Puppeteer #12712, Playwright screenshot issues, Browserbase foreground-tab blog |
| **Input trust + inactive tabs** | Explains A2/C2 | Chromium issue #89; Cua “background delivery” docs |
| **macOS app activation** | A3 / Spaces | NSWorkspace frontmost; Stagehand #2258 |
| **MV3 `debugger` + CWS** | If you bet on extension CDP | Chrome debugger API docs; Store permissions policy — learn *after* B3 spike, not before |
| **Compositor vs DOM Eyes** | If screenshots need foreground | When to use AX/DOM text vs pixels (Stagehand default vs harness vision) |

### Where *not* to invent early

- Don’t build a custom Chromium.
- Don’t assume Store-ready `debugger` extension before atoms pass.
- Don’t merge “better clicks” (already partly shipped) with “dual-focus” in one narrative to users.

### Founder framing

Dual-focus is a **wedge** if you can demo homework uninterrupted for a full Run. The **defensible** near-term story is likely **same cookies + agent window (W2/W3)** plus **measured** activate reduction — not “we solved Chromium background Input.” Your CS edge is running the atom battery yourself and killing false paths fast; your Engevity edge is packaging the window/Space UX humans understand.

---

## 7. Open questions / non-goals

**Open**

- Reconcile marketing “no focus steal” vs chrome-bridge-mcp / #89 on **your** Chrome version.
- Whether `Emulation.setFocusEmulationEnabled` helps screenshots without OS steal.
- Whether agent-window + human-window in one profile still SSO-conflicts for school vs personal (policy, not CDP).

**Non-goals (this research)**

- Gmail OAuth / API recipes.
- Stagehand adoption.
- Anthropic computer-use as default Hands.
- Auto-clicking Allow remote debugging.
- Multi-agent N-way same-window trusted Input.

---

## 8. Sources / refs

- Chromium: [devtools-protocol#89](https://github.com/ChromeDevTools/devtools-protocol/issues/89) (Input + background tabs)
- CDP: [Page.captureScreenshot](https://chromedevtools.github.io/devtools-protocol/tot/Page/#method-captureScreenshot), [Target.activateTarget](https://chromedevtools.github.io/devtools-protocol/tot/Target/#method-activateTarget), [Page.bringToFront](https://chromedevtools.github.io/devtools-protocol/tot/Page/#method-bringToFront)
- [chrome.debugger API](https://developer.chrome.com/docs/extensions/reference/api/debugger)
- [Cua background delivery](https://cua.ai/docs/concepts/browser-targeting-and-background-delivery)
- [chrome-bridge-mcp](https://github.com/ShalomObongo/chrome-bridge-mcp)
- [Stagehand activate / macOS](https://github.com/browserbase/stagehand/issues/2258)
- [Browserbase foreground tab tracking](https://www.browserbase.com/blog/cdp-foreground-tab-tracking)
- Local: `~/Developer/browser-harness/src/browser_harness/helpers.py` (`switch_tab`), `virgil-desk/.../harness_backend.py`, `packages/extension/src/background.js` (`screenshotTab`)
- Desk browser layer: [`BROWSER_LAYER.md`](BROWSER_LAYER.md)

---

## 9. Executive summary

1. **Dual-focus is the product**; Way 1 activate-on-every-op fights it.
2. **Trusted CDP Input on inactive tabs is disputed / often false on macOS** — extension debugger is not a free escape hatch.
3. **Desk already has levers:** `activate=False` / `BH_NO_ACTIVATE` unused; extension already restores tab after screenshots.
4. **Atomic path:** measure P0 → spike C2/A1/A2 → if fail, ship **W2 second window (same cookies)** as the dual-focus shape; treat same-window trusted Input as R&D.
5. **Your leverage:** run the feasibility battery and package W2/W3 UX; learn compositor/Input/macOS focus before betting months on a Chromium-shaped miracle.
