# Relation to Virgil Hub

**Virgil Desk** is standalone — no Notion/tick runtime dependency.

**Virgil Hub** (Notion + tick + browser_queue) remains the operator control plane for cron Briefings and isolated `:9223` automation.

Optional: add Virgil Hub skills to agent `external_dirs`; no shared queue.

Repo: [github.com/Donnieboi03/virgil-desk](https://github.com/Donnieboi03/virgil-desk)

## Product direction (operator decision)

| If… | Then… |
|-----|--------|
| Desk feels good in daily browser use | Keep iterating on Desk; Hub stays for Notion/tick crons |
| Desk is experimental | Use `DESK_AGENT_BACKEND=mock`; don't migrate Hub workflows yet |
| You want one product | Pick **Desk** or **Hub** as primary — they are intentionally separate runtimes |

First dogfood: [`OPERATOR.md`](OPERATOR.md).
