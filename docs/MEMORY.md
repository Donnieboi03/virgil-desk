# Desk memory

Virgil Desk keeps a small, **capped** memory surface in the extension (`chrome.storage.local`) and injects a slice into each execute **Packet**. Hermes profile Memory/RAG (`USER.md` / `MEMORY.md` / providers) stays on the agent — Host does **not** own RAG. See [`ENV.md`](ENV.md).

Each **Run agent** starts a fresh Hermes chat, so Desk re-attaches Packet memory once per execute (not on every Eyes/Hands tool turn).

## Cognitive map

| Layer | Role | Storage | Packet field |
|-------|------|---------|--------------|
| **Working** | Per-handoff notepad (mission, decomposition, bullets) | `virgil_desk_memory_v1.by_run_id` | `run_notepad` (includes `decomposition`) |
| **Episodic (thin)** | Last-N execute summaries across runs | `virgil_desk_memory_v1.global_recent` | `recent_executions` |
| **Semantic** | Standing prefs / decisions (episode-agnostic) | `virgil_desk_semantic_v1.facts[]` | `semantic_facts` |
| **Procedural** | How to act | prompts + skills (authored) | — |

## Storage keys

### `virgil_desk_memory_v1`

```json
{
  "global_recent": [
    {
      "run_id": "…",
      "item_id": "…",
      "title": "…",
      "outcome": "done|partial|…",
      "summary": "…"
    }
  ],
  "by_run_id": {
    "<run_id>": {
      "decomposition": "…",
      "mission": "…",
      "bullets": ["…"]
    }
  }
}
```

### `virgil_desk_semantic_v1`

```json
{
  "facts": [
    {
      "id": "string",
      "key": "string",
      "value": "string",
      "tags": ["user", "decision"],
      "source": "manual|host",
      "updated_at": "ISO-8601"
    }
  ]
}
```

- Prefs: `tags` include `user` (e.g. concise replies).
- Standing decisions: `tags` include `decision` (e.g. do not false-close judgment items).
- Upsert is by **`key`** (stable supersede).

## Caps (`config/desk.yaml` → `memory:`)

| Key | Default | Meaning |
|-----|---------|---------|
| `recent_max` | 3 | Stored + injected episodic entries |
| `notepad_max_bullets` | 20 | Working notepad bullet count |
| `notepad_max_chars` | 4000 | Working notepad total chars |
| `semantic_max_facts` | 20 | Max facts stored |
| `semantic_packet_max_facts` | 10 | Max facts injected into Packet |
| `semantic_max_value_chars` | 200 | Per-fact value length |
| `semantic_max_key_chars` | 64 | Per-fact key length |

Pushed to the extension on WebSocket `registered` via `config_for_extension`.

## Protocol

- **`memory_get` → `memory_snapshot`**: `{ memory, semantic }` before execute (and REST GET).
- **`memory_patch` ops**: `seed_run` | `append_recent` | `append_bullet` | `upsert_fact` | `delete_fact`.
- **REST**: `GET /v1/desk-memory/semantic`, `PATCH /v1/desk-memory/semantic` with `{ "op": "upsert_fact"|"delete_fact", … }`.

Seed also from the extension **options** page (direct `chrome.storage.local` write — works when Host is down).

## Out of scope

- Desk SOUL / identity store
- Auto-promote episodic → semantic
- Vector RAG or Host-owned retrieval
- Long-lived Hermes session as the memory vehicle
- Procedural learning (skills stay authored)

## Related

[`ARCHITECTURE.md`](ARCHITECTURE.md) · [`PROTOCOL.md`](PROTOCOL.md) · [`STORE_PRIVACY.md`](STORE_PRIVACY.md) · [`ENV.md`](ENV.md)
