---
name: /opsx-continue
id: opsx-continue
category: Workflow
description: Continue agile-workflow change - create next artifact (OPSX)
---

Continue working on a change by creating the **next** artifact (one per invocation).

**Input**: Optional change name after `/opsx-continue` (e.g. `/opsx-continue cm-830`).

## Steps

1. Select change (`openspec list --json` if name not given).
2. `openspec status --change "<name>" --json`
3. Read `openspec/changes/<name>/inputs/jira.yaml` (required).
4. **Resolve `target_repo` before repo-assessment** (see schema `target_repo`):
   - If the next ready artifact is `repo-assessment` (or `constitution`) and
     `target_repo` is absent or empty in `jira.yaml`:
     - Ask the user once: "Provide the URL of the target GitHub repository
       (e.g. https://github.com/org/repo)."
     - Persist `target_repo` to `inputs/jira.yaml`.
     - Verify the repository is accessible before creating repo-assessment.
     - **Do not** create repo-assessment or constitution until `target_repo` is recorded.
   - For earlier artifacts (`validation`, `specs`), `target_repo` is not required.
5. Pick first artifact with `status: "ready"`.
6. `openspec instructions <artifact-id> --change "<name>" --json` → create artifact at `outputPath`.
7. **STOP** after one artifact. Ask: "Approve / Reject with feedback?" before next continue.

## Artifact order (openspec-agile-workflow)

validation.json → specs.md → repo-assessment.md → constitution.md → plan.md → tasks.md

## Guardrails

- ONE artifact per invocation
- Do not skip gates
- `target_repo` required before repo-assessment — **not** at `/opsx-new`
- If user provided repo URL at `/opsx-new`, it should already be in `jira.yaml`
