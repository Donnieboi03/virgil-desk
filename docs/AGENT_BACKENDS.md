# Agent backends

Set `DESK_AGENT_BACKEND=mock|hermes|openclaw`

Hermes: `DESK_HERMES_PROFILE`, `DESK_HERMES_HOME`

Point `skills.external_dirs` at this repo's `skills/` for `desk-browser-bridge`.

Hermes agents call Host **`POST /v1/browser`** (`desk_browser` tool) with a `BrowserOp`; Host forwards to the extension over WebSocket and returns `command_id`.

Memory: configure Graphiti MCP (or other) on the agent profile — Host does not own RAG.
