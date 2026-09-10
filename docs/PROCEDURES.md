# Procedures (contract only)

Versioned **procedure** sketch for future mining from Desk JSONL. **No Host router or procedure store runtime in this ship** — mining jobs and replay stay out of process until a later plan.

## Join shape (mine-ready events)

Mine a candidate procedure from one Agent execute window:

1. Anchor on `agent.execute_started` / `agent.executed` | `agent.execute_failed` with `item_id`.
2. Collect `browser.command` + `browser.command_result` for that `item_id` ordered by `op_seq` (prefer over wall-clock alone).
3. Use binding hints on `browser.command` (`url`, `target_id` / `ref` / `text`|`contains` / `selector`, `tab_id`) as **hints**, not replay keys.
4. Attach `site_fingerprint` from results (`netloc` + first path segment) for clustering same-site patterns.
5. Terminal label from `flags.outcome` on execute end (`done` / `empty_output` / `awaiting_human` / …).

**Eyes-rebind rule:** ephemeral refs (`t14`, inject-session `target_id`) are not durable. A stored procedure must re-observe and rebind Hands — never blind-replay JSONL refs.

## Versioned procedure sketch (future)

```json
{
  "procedure_id": "proc_…",
  "version": 1,
  "site_fingerprint": "mail.google.com/mail",
  "intent_class": "open_observe_verified_terminal",
  "steps": [
    {"op": "observe", "bind": "eyes"},
    {"op": "click", "bind": "label_or_text_hint"},
    {"op": "observe", "bind": "eyes"},
    {"terminal": "verified_terminal|done|park_you"}
  ],
  "failure_policy": "isolate_subgoal"
}
```

Host does **not** load or route these yet. Obs fields exist so offline mining can invent the first drafts.

## Related

- Event fields: [`OBSERVABILITY.md`](OBSERVABILITY.md)
- Board / clump product policy: [`PRODUCT.md`](PRODUCT.md)
- Path B Eyes: [`BROWSER_LAYER.md`](BROWSER_LAYER.md)
