# Run tab cost A/B

Compare **per-card Run agent** (control) vs **Run tab** (one `host_loop` session) on the same site/board shape.

## Setup

1. `DESK_EXECUTE_RUNTIME=host_loop` + `OPENROUTER_API_KEY`.
2. Reload extension; confirm WS connected.
3. Prefer ≥5 Agent roots from one handoff (Gmail or other same-site board).

## Arms

| Arm | Action | `run_id` |
|-----|--------|----------|
| **A** | Hand off → for each proposed Agent root click **Run agent** | note after handoff |
| **B** | Fresh handoff (or new run) same site → **Run tab** once | note after handoff |

Keep item count and site comparable. Do not mix Hermes oneshot into either arm for this A/B.

## Metrics (`desk-events --run-id <id> --summary`)

1. Total `cost_usd` and `prompt_tokens` (decomp + execute events)
2. $/item and mean prompt tokens/item
3. Outcomes: done / failed / You parks / false Partial rate
4. Wall time (first execute_started → last execute finished)

## Pass bar

- **B ≤ ~70% of A** total execute cost on a ≥5-item same-site board, **or**
- Short write-up why not (thrash, Partial, model skipped `complete_item`).

Record both `run_id`s and the summary table in the PR description when deciding merge.
