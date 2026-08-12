# agents.md — Operator Agent Routing (REQUIRED)

Replace this stub with your operator's documentation before Repro Verification.

If this file is absent, the target repository **must** contain `AGENTS.md` or `agents.md`.
See schema `agents_md.lookup_order`.

## Required sections

1. **Repository layout** — key packages and directories
2. **Architecture patterns** — controller frameworks, reconciliation flow
3. **Execution agent roster** — agent IDs and which paths/packages they own
4. **Test exemplar** — how unit/integration tests are structured
5. **Per-task verification matrix** — `make` targets and `go test` commands per task type

## Agent roster (example — replace)

| Agent ID | Owns |
|----------|------|
| `API_Agent` | API types, CRDs, validation |
| `OperatorController_Agent` | Controllers / reconcilers |
| `Testing_Agent` | Unit, envtest, e2e tests |

Assigned Agent values in `tasks.md` MUST match IDs defined here.
