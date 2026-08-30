# Dual-focus research — Virgil Desk

**Audience:** Donovan (operator / CS founder).  
**Status:** Research synthesis (Aug 29, 2026). Not a build plan until feasibility atoms pass.  
**Product stake:** Desk’s value is **dual-work** — agent finishes Gmail (or similar) while you do homework. Focus-steal fights that promise.

**Eyes / Hands taxonomy** (DOM vs CDP Input vs OS, costs, pros/cons): [`INTERACTION_LAYERS.md`](INTERACTION_LAYERS.md).

Swarm lenses: CDP background semantics, MV3 `chrome.debugger`, prior-art contradictions, architecture cuts, Desk/harness activate audit ([codebase TT](0c3f3098-7253-49c4-903e-5fdb3e1f625a)).

---

## 1. Problem statement

When Desk execute drives Chrome via **browser-harness on everyday Chrome**, each op typically **activates** the agent tab (`Target.activateTarget` via default `switch_tab`). Chrome then pulls **tab and often OS window focus** to the agent. You cannot stay in a homework tab/window without fighting the agent. Dual-focus fails even when clicks are “smoother.”

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
| **chrome-devtools-mcp [#1254](https://github.com/ChromeDevTools/chrome-devtools-mcp/issues/1254)** | One report: OS focus was stolen on macOS even with `activateTarget`/`bringToFront` **filtered out at the proxy** — implying the raw remote-debugging-port **WebSocket transport itself** may trigger `NSApplication` activation, independent of which CDP command is sent | **Not yet tested against `chrome.debugger`'s in-process transport** — this is the actual crux of the "extension avoids focus-steal" theory and remains unresolved either way |

**Implication:** Treat “extension debugger unlocks dual-focus trusted clicks” as **unproven / likely false** for macOS headed Chrome until you measure it. Extension still helps for **attach transport** and product UX — not magic for Input.

---

## 3. Problem dissection (atoms)

| Atom | Question | Why it matters | Depends on |
|------|----------|----------------|------------|
| **P0** | Does Desk execute today steal tab and/or OS focus? | Baseline metric | — |
| **A1** | Can CDP `Page.captureScreenshot` succeed on a never-activated headed tab? | Eyes without steal | P0 |
| **A2** | Can `Input.dispatchMouseEvent` affect a non-active tab without activate/bringToFront? | Trusted Hands without steal | P0 |
| **A3** | On macOS, does `activateTarget` bring **Chrome.app** to front? | Homework in another app/window | P0 |
| **T1** | Does the raw CDP WebSocket transport itself (not a specific command) trigger OS app activation? | Determines if `chrome.debugger`'s in-process transport is a real fix or a red herring | P0 |
| **B3** | Does `chrome.debugger` Input alone force-activate, independent of T1's transport-level steal? | Extension path hypothesis | A2, T1 |
| **B4** | Operational cost of `chrome.debugger`: mandatory infobar (no suppression API besides `--silent-debugger-extension-api` or enterprise force-install), exclusive single-attach (fails if DevTools/another debugger already attached), and non-recursive OOPIF handling (needs `Target.setAutoAttach{flatten:true}`, Chrome 125+) | Even if B3 passes technically, these gate whether it's usable day-to-day on a personal everyday Chrome | B3 |
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
| **P0** | Run Desk agent; stay in homework tab; log whether agent tab becomes selected and whether Chrome becomes frontmost app | Desk harness on everyday Chrome, Gmail agent tab | Human tab stays selected **and** another app can stay frontmost | Either flips | 0.5h | Low |
| **C2** | Patch/spike harness script: `switch_tab(tid, activate=False)` then `click_at_xy`; watch focus | Same as P0 | Click lands **and** no tab/OS steal | Click no-op **or** steal | 2–4h | Med — may need harness env `BH_NO_ACTIVATE` |
| **A1** | Attach CDP, never activate, `captureScreenshot` on agent tab | Harness or small Python | PNG returns &lt;2s | Hang/timeout | 1–2h | Med |
| **A2** | Same as C2 but isolate Input only (no Desk) | Minimal harness script | Event changes DOM without activate | No effect until activate | 1–2h | Low |
| **A3** | From Terminal (Chrome not front): `activateTarget` on a tab | CDP only | Frontmost stays Terminal | Chrome jumps forward | 0.5h | Low |
| **T1** | From Terminal, open raw CDP WS to remote-debugging-port and send a no-op command (e.g. `Target.getTargets`) on a background tab — **never** call `activateTarget`/`bringToFront` | CDP only, everyday Chrome | Frontmost app unchanged | Chrome/frontmost jumps forward on *any* command | 0.5–1h | Low |
| **C3** | Gmail: synthetic DOM click vs CDP Input on same control | Agent tab | DOM path opens thread reliably | Gmail ignores untrusted | 2–4h | Med — site-specific |
| **B3/C4** | Extension `chrome.debugger` Input with tab inactive — re-run the **same** frontmost-app probe as T1 but via in-process `chrome.debugger` transport | Dev unpacked + debugger perm | Input works, tab stays inactive, **and** frontmost app matches T1's passing case | Auto-focus, no-op, or frontmost jumps like raw CDP | 4–8h | High — infobar always shown (B4), CWS review later if ever published |
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
 ├── T1 (transport-level steal, no command at all)
 │     ├── pass (no steal) → raw CDP background path is viable; B3 optional
 │     └── fail (steal on any command) → extension in-process transport is the
 │           ONLY remaining technical lever; run B3 to see if it also fails
 └── only if still need same-window trusted Input:
       B3 (+ B4 operational cost check) extension debugger spike → else accept W2 as product shape
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
- **T1/B3 crux, unresolved by documentation alone:** is the reported macOS focus-steal a property of specific CDP commands (`activateTarget`/`bringToFront`), or of the raw remote-debugging-port WebSocket transport itself (per chrome-devtools-mcp#1254)? If it's transport-level, `chrome.debugger`'s in-process extension transport is the only thing that could plausibly differ from raw CDP — but no source tested that directly. Needs the T1 → B3 spike pair, not more reading.
- Whether recent Chrome (post the referenced Puppeteer #14922-style fixes) has changed background-tab `captureScreenshot`/Input behavior on headed macOS Chrome versus the mostly-older reports surveyed here — re-verify against Donovan's actual Chrome version before trusting any single report.
- Whether Stage Manager (macOS 13+) changes W3's Spaces dynamics — no authoritative source found either way.

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
- [chrome-devtools-mcp #1254](https://github.com/ChromeDevTools/chrome-devtools-mcp/issues/1254) (possible transport-level, not command-level, focus steal)
- CWS review policy: [permissions](https://developer.chrome.com/docs/webstore/program-policies/permissions), [review process](https://developer.chrome.com/docs/webstore/review-process) — `debugger` is a "sensitive execution permission" (extra scrutiny), not a documented outright ban
- [chrome.debugger infobar has no suppression API](https://stackoverflow.com/questions/63441002/chrome-extension-clear-infobar-label-after-debug-mode) short of `--silent-debugger-extension-api` or enterprise `ExtensionInstallForcelist`
- Prior art (products): [Cua background delivery](https://cua.ai/docs/concepts/browser-targeting-and-background-delivery), [chrome-bridge-mcp](https://github.com/ShalomObongo/chrome-bridge-mcp), [krawlify-relay](https://github.com/kamenarov/krawlify-relay), [Midscene bridge mode](https://midscenejs.com/bridge-mode), [Stagehand #2258](https://github.com/browserbase/stagehand/issues/2258)
- macOS window/Spaces: [chrome.tabs `active` ≠ window focus](https://sunnyzhou-1024.github.io/chrome-extension-docs/extensions/tabs.html), [NSWindow.orderFrontRegardless()](https://developer.apple.com/documentation/appkit/nswindow/orderfrontregardless()) (own-app only, not applicable to controlling Chrome), [Hammerspoon hs.window](https://www.hammerspoon.org/docs/hs.window.html) (cross-Space needs private APIs — yabai/Spaceballs precedent, fragile across macOS versions)
- [Cua background delivery](https://cua.ai/docs/concepts/browser-targeting-and-background-delivery)
- [chrome-bridge-mcp](https://github.com/ShalomObongo/chrome-bridge-mcp)
- [Stagehand activate / macOS](https://github.com/browserbase/stagehand/issues/2258)
- [Browserbase foreground tab tracking](https://www.browserbase.com/blog/cdp-foreground-tab-tracking)
- Local: `~/Developer/browser-harness/src/browser_harness/helpers.py` (`switch_tab`), `virgil-desk/.../harness_backend.py`, `packages/extension/src/background.js` (`screenshotTab`)
- Desk browser layer: [`BROWSER_LAYER.md`](BROWSER_LAYER.md)

---

## 9. Executive summary

1. **Dual-focus is the product**; harness activate-on-every-op fights it.
2. **Trusted CDP Input on inactive tabs is disputed / often false on macOS** — extension debugger is not a free escape hatch, and one report (chrome-devtools-mcp#1254) suggests the focus-steal may be at the raw CDP **transport** level, not just specific commands — meaning `chrome.debugger` may or may not differ; this is untested, not settled.
3. **Desk already has levers:** `activate=False` / `BH_NO_ACTIVATE` unused; extension already restores tab after screenshots.
4. **Atomic path:** measure P0 → spike C2/A1/A2/T1 → if fail, ship **W2 second window (same cookies)** as the dual-focus shape; treat same-window trusted Input (incl. `chrome.debugger`) as R&D gated by T1's result.
5. **Your leverage:** run the feasibility battery and package W2/W3 UX; learn compositor/Input/macOS focus before betting months on a Chromium-shaped miracle.
