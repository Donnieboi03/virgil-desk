# Handoff capture — viewport, virtualization, and “app memory”

How Desk **sees** a page at Hand off, why that is not the full site dataset, and what “looking at JS heap / app memory” would actually mean.

Related: [`BROWSER_LAYER.md`](BROWSER_LAYER.md) (Eyes/Hands), [`PRODUCT.md`](PRODUCT.md), [`config/desk.yaml`](../config/desk.yaml).

## Default product model (current)

| Layer | Default | Notes |
| :--- | :--- | :--- |
| **Capture** | Viewport **excerpt** + **links** + **screenshot**; **`handoff_scroll_loops: 0`** | Faithful “what’s on screen” |
| **Intent** | Panel chips: **All visible** / **This item** (+ optional detail) → `handoff.intent` | Steers decompose; not a time API |
| **Board budget** | `prompts.decompose_items_max` (ceiling) | Caps cards, not “how much of the inbox exists”; homogeneous clumps may use one Agent root for same-pattern visible rows |
| **Advanced** | `handoff_scroll_loops > 0`, nested-list scroll, site search via `hints.search_query` | Opt-in; easy to overfit mail UIs |

**Do not** treat past-day / unread / “full mailbox” as the product spine. Most sites are not temporal; common jobs are **everything visible** or **this one thing**. Mail time filters belong in **`hints.search_query`** (or a future site adapter), not first-class intent modes.

## Pipeline (what runs on Hand off)

1. **Default (`handoff_scroll_loops: 0`):** settle + scrape + screenshot the **human tab** directly — **no duplicate** (avoids empty SPA shells like a fresh Gmail dup).
2. **Only if scroll loops > 0:** duplicate an ungrouped scrape tab, scroll it, capture, then close — so the human viewport is not moved.
3. Slice text to `handoff_excerpt_max_chars` (~12k) → Hermes decompose gets **excerpt + links** in JSON and the PNG as vision (`--image`).

Observability: `handoff.snapshot` in `desk_events.jsonl` (`excerpt_chars`, `full_text_chars`, `handoff_excerpt_capped`, `scroll_loops_*`, `used_duplicate_tab`, `screenshot_bytes`).

### What each input is for

| Input | Purpose |
| :--- | :--- |
| `url` / `title` | Ground the board in “which page” |
| `intent` | Operator steer (all visible / this item / free detail) |
| `snapshot.excerpt` | Main **text** for triage (subjects, snippets, labels) |
| `snapshot.links` | Concrete http URLs from the mounted DOM |
| `snapshot.screenshot` | One **viewport** PNG for layout / spatial cues |
| `human_tab_id` | Your real tab for later Run agent provisioning |

Raising the excerpt cap only helps when `handoff_excerpt_capped: true` and the DOM already holds more text. It does **not** load off-screen virtualized rows.

## List virtualization (why “the page” ≠ “all rows”)

Long lists (mail, feeds, grids) often use **windowing / virtualization**:

- The app keeps a large dataset in **JavaScript memory** (or fetches pages of it).
- The **DOM** only mounts rows near the viewport (+ a small overscan buffer).
- On scroll, nodes are **recycled**: the same ~20–40 elements are rewritten; scrolled-away rows **leave the DOM**.
- A tall spacer keeps the scrollbar honest so it *feels* like the full list is there.

So “off-DOM” does **not** mean “another URL.” It means **still in the product’s front-end process, but not present as HTML nodes right now** — so `innerText` / link scrape cannot see it.

**How to recognize similar sites (DevTools):**

1. Count row nodes → scroll → count stays ~flat while text changes → virtualized.
2. Find-in-page fails for a subject you know is “below” → row not mounted.
3. Scroll often lives on an inner `overflow: auto` container (`window.scrollBy` is a no-op).
4. Network tab shows XHR/fetch filling the list as you scroll.
5. Sometimes `aria-rowcount` claims hundreds while only dozens of rows exist in the DOM.

**Implication for agents:** one scrape at the end after blind scroll **fails** on virtualized UIs — scrolled-away rows are already gone. You must harvest **each window while mounted**, or read **network/API** data, or change the view (search / open) so different rows mount.

## “Why not read app memory / the JS heap?”

The list **is** front-end data — but **not a documented, stable interface**.

| Layer | What it is | Desk today |
| :--- | :--- | :--- |
| DOM | Mounted HTML | **Yes** — excerpt + links |
| Pixels | Viewport bitmap | **Yes** — handoff screenshot |
| JS heap / closures | Private objects holding the full list | **No** — no public `window.getAllThreads()` |
| Framework trees | React fibers / internal stores | **No** — fragile, site-specific |
| Network JSON | Responses that *stocked* the heap | **No** (yet) — best “memory-adjacent” research path |
| Official APIs | Gmail API, etc. | **No** — separate product |

### Why heap dump is not the default

- **Private modules** — data lives in minified closures, not `window`.
- **Extension isolation** — content scripts share the DOM, not the page’s JS world by default; MAIN-world injection is required to see page `window`.
- **No schema** — heap objects lack a stable “Thread[]” contract across sites or even across app versions.
- **Security / ToS** — deep hooks (`chrome.debugger`, fiber walking) are brittle and look like reverse-engineering.
- **Product spine** — Desk is generic “page in front of you” Eyes, not a mail client.

### Practical doors (research order)

1. **Viewport capture** (shipped default) — arrange the view, then hand off.  
2. **Operator changes the surface** — search, folder, open thread, then hand off.  
3. **Network interception** — MAIN-world patch of `fetch`/XHR (or CDP) to read list JSON as the SPA loads it; structured rows; **site-specific**, auth-sensitive.  
4. **MAIN-world globals / Redux DevTools hooks** — rare on closed apps like Gmail.  
5. **`chrome.debugger` / heap snapshots** — possible in theory; poor product spine.  
6. **Official APIs** — correct long-term “all my mail,” not DOM Eyes.

Mental model: **DOM = conveyor in view**; **JS heap = warehouse behind locked doors**; **network responses = delivery trucks** that stock the warehouse (often the practical door for a specialized adapter).

## Flicker / seamless notes

- Scrape does not need tab focus.
- `captureVisibleTab` **activates** the target briefly (~`default_wait_ms`) then restores the prior tab — main focus flash.
- True no-flicker needs skip-PNG on handoff or a non-activate capture path (CDP / future) — Chrome’s visible-tab API is the bottleneck.

## Config knobs

| Key | Role |
| :--- | :--- |
| `browser.handoff_scroll_loops` | Default `0`. `>0` only for experiments. |
| `browser.handoff_excerpt_max_chars` | Text sent to decompose (~12k). |
| `browser.handoff_scroll_viewport_ratio` | Used when scroll loops > 0. |
| `prompts.decompose_items_max` | Max board cards after parse. |

Restart `desk-host` after YAML changes; reload the unpacked extension for panel/background defaults.
