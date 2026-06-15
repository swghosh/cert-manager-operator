<!-- Companion artifact: repo-assessment.md (target files, reusable assets, risks) -->
# [PROJECT_NAME] Constitution

**AgentRoutingMode:** PROVIDED | PROVISIONAL
<!-- PROVIDED when AGENTS.md exists in repo; PROVISIONAL otherwise — downstream tasks MUST match this value -->

**Version**: [CONSTITUTION_VERSION] | **Ratified**: [RATIFICATION_DATE] | **Last Amended**: [LAST_AMENDED_DATE]

<!--
  QUALITY TARGET: ≥90% against Stage 2 constitution rubric.
  Self-check (all must pass):
  - Every principle cites observable repo evidence (file path or pattern), not generic best practices.
  - No file inventories, hook tables, or risk analysis — those belong in repo-assessment.md only.
  - No implementation sequencing — that belongs in plan.md (Stage 3).
  - AgentRoutingMode matches whether AGENTS.md was found and parsed.
  - Upstream operand vs Open: separate principles where the repo embeds upstream workloads.
  - Addon controllers: note controller-runtime exception if repo uses library-go for core + runtime for addons.
-->

## Core Principles

### I. [PRINCIPLE_NAME — e.g., Follow Existing Controller Patterns]
[PRINCIPLE_DESCRIPTION — what to do and why, grounded in repo evidence]

**Evidence:** `[path/to/file.go]` — [one-line observation from actual code, Makefile, or CI config]

### II. [PRINCIPLE_NAME — e.g., Upstream Operand Separation]
[PRINCIPLE_DESCRIPTION — operator reconciles CR + deploys embedded manifests; do not fork upstream controller logic in operator packages]

**Evidence:** `[path/to/bindata/or/controller/]` — [pattern observed]

### III. [PRINCIPLE_NAME — e.g., Test-First / Verification Gates]
[PRINCIPLE_DESCRIPTION — actual test commands and gates from Makefile, hack/verify-*, CI workflows]

**Evidence:** `Makefile` / `.github/workflows/` — [target names, e.g., `make test`, `hack/verify-*`]

### IV. [PRINCIPLE_NAME — e.g., Generated Code Discipline]
[PRINCIPLE_DESCRIPTION — what is generated, how to regenerate, what must not be hand-edited]

**Evidence:** `[path/to/generated/or/codegen]` — [tooling observed]

### V. [PRINCIPLE_NAME — e.g., RBAC / Security Posture]
[PRINCIPLE_DESCRIPTION — least privilege, secrets handling, cluster-scoped writes justification]

**Evidence:** `[path/to/rbac/or/manifests]` — [pattern observed]

### VI. [PRINCIPLE_NAME — e.g., OLM / Release Constraints]
[PRINCIPLE_DESCRIPTION — CSV ownership, relatedImages, feature gates, TechPreview markers if applicable]

**Evidence:** `[path/to/bundle/or/features.go]` — [pattern observed]

<!-- Add more principles only when repo evidence supports them. Prefer 5–8 substantive principles over padding. -->

## Additional Constraints

<!-- Tech stack, compliance, deployment policies, naming conventions — all evidence-backed -->

- **[Constraint category]:** [Rule derived from repo] — **Evidence:** `[path]`
- **[Constraint category]:** [Rule derived from repo] — **Evidence:** `[path]`

## Development Workflow

<!-- How work actually flows in this repo: review, CI, local verify, bundle generation -->

| Activity | Requirement | Evidence |
|----------|-------------|----------|
| Local unit tests | [e.g., `make test`] | `Makefile` |
| Full verify | [e.g., `make verify` or `hack/verify-*`] | `hack/` |
| Codegen refresh | [when required after API changes] | `[path]` |
| PR / review | [from CONTRIBUTING.md or team norm] | `[path]` |

## Agent Routing

<!-- Only when AgentRoutingMode is PROVIDED — summarize AGENTS.md agent IDs and when to use each.
     When PROVISIONAL: list provisional IDs and state that downstream tasks must use them exactly. -->

| Agent ID | Scope | When to route |
|----------|-------|---------------|
| [AGENT_ID] | [capability] | [task types] |

## Governance

- This constitution supersedes ad-hoc conventions for downstream Planning, Task Creation, and Code Generation agents.
- **Amendments:** require documented evidence of repo change; bump Version and Last Amended date.
- **Conflicts:** if spec contradicts constitution, escalate in plan.md §8 — do not silently override.
- **Companion docs:** AGENTS.md / CLAUDE.md / CONTRIBUTING.md — [which takes precedence for what].
- **Complexity:** new patterns must justify deviation from existing repo conventions with explicit rationale.
