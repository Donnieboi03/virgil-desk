# Agent backends

Set `DESK_AGENT_BACKEND=mock|hermes|openclaw`

Hermes: `DESK_HERMES_PROFILE`, `DESK_HERMES_HOME`

Point `skills.external_dirs` at this repo's `skills/` for `desk-browser-bridge`.

Memory: configure Graphiti MCP (or other) on the agent profile — Host does not own RAG.
