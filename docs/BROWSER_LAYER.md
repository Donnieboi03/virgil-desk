# Browser layer

Virgil Desk drives Chrome via **extension APIs** only (MVP): `tabs`, `tabGroups`, `scripting`.

- **Not** browser-harness, **not** Playwright, **not** `:9223`.
- **Screenshot:** in-tab capture via injected script on `agent_tab_id` (one window).
- Optional: `DESK_SCREENSHOT_MODE=debugger` for CDP fallback (later).

Patterns ported from Virgil Hub browser-queue: observe–act–observe, scroll loops.
