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
| `DESK_HERMES_PROFILE` | `virgil-executor` | Hermes profile name |
| `DESK_HERMES_HOME` | `~/.hermes/profiles/{profile}` | Hermes home |
| `DESK_PERSIST_SCREENSHOTS` | `0` | Set `1` to write PNGs under `~/.virgil-desk/runs/` |
| `DESK_LOG_DIR` | `~/.virgil-desk/logs` | Event log directory |

Never commit filled `.env` files.
