# Testing

| Layer | Command |
|-------|---------|
| Protocol | `npm run test -w @virgil-desk/protocol` |
| Host unit | `cd packages/host && pytest tests/unit` |
| Host integration | `cd packages/host && pytest tests/integration` |

Milestone gates require tests green before commit.
