# Environment variables

Host reads `.env` from cwd if present. Extension Host URL is in Chrome options (`chrome.storage.sync`).

| Variable | Default | Purpose |
|----------|---------|---------|
| `DESK_AGENT_BACKEND` | `mock` | `mock` \| `hermes` \| `openclaw` |
| `DESK_HOST` | `127.0.0.1` | Bind address |
| `DESK_PORT` | `8787` | Bind port |
| `DESK_CONFIG` | `config/desk.yaml` | Limits YAML path |
| `DESK_SCREENSHOT_MAX_PER_RUN` | from YAML | Override screenshot cap |
| `DESK_HERMES_DECOMPOSE` | `1` when hermes | Set `0` to force stub decompose |
| `DESK_HERMES_PROFILE` | *(local default often `virgil-executor`)* | Hermes profile name — not product identity |
| `DESK_HERMES_HOME` | `~/.hermes/profiles/{profile}` | Hermes home |
| `DESK_PERSIST_SCREENSHOTS` | `0` | Set `1` to write PNGs under `~/.virgil-desk/runs/` |
| `DESK_LOG_DIR` | `~/.virgil-desk/logs` | Event log directory |
| `DESK_EXECUTE_RUNTIME` | from YAML (`hermes_oneshot`) | Override `execute.runtime`: `hermes_oneshot` \| `host_loop` |
| `DESK_AUTO_RUN_TAB` | from YAML (`false`) | `1`/`0` → `execute.auto_run_tab` (auto Run tab after decompose; `host_loop` only) |
| `DESK_NOTIFY_HUMAN` | from YAML (`false`) | `1`/`0` → `execute.notify_human_attention` (badge/OS notify on You/Waiting) |
| `OPENROUTER_API_KEY` | *(required for host_loop)* | OpenRouter key for Host-owned execute ModelClient |

**Run tab ceilings** (when `host_loop`): `execute.run_max_steps` (flat session, default 200), `execute.run_steps_per_item` (soft Partial+advance, default 20). Per-card **Run agent** still uses `execute.max_steps` (40).

**Loop UX flags (off by default):** `execute.auto_run_tab`, `execute.notify_human_attention` in [`config/desk.yaml`](../config/desk.yaml). Extension Options can also toggle local notify override and manage the **document vault** (operator-supplied files for `upload`).

Hermes agents call Host **`POST /v1/browser`** (via `desk-browser` / skill) with a `BrowserOp`; Host forwards to the extension over WebSocket. Point profile `skills.external_dirs` at this repo’s `skills/` for `desk-browser-bridge`. Hermes Memory/RAG stays on the agent profile — Host does not own RAG. Desk’s separate capped memory (notepad / recent / semantic) is documented in [`MEMORY.md`](MEMORY.md). Wire-up steps: [`HERMES_SETUP.md`](HERMES_SETUP.md).

**Host-loop execute** (`execute.runtime: host_loop`) does **not** use Hermes tool memory: Host calls OpenRouter with tools and prunes older Eyes in the transcript. Decompose can still use Hermes.

Never commit filled `.env` files.
