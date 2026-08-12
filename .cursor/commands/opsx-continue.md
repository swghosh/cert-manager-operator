---
name: /opsx-continue
id: opsx-continue
category: Workflow
description: Continue bugfix-workflow change - create next artifact, eval gate, refine, approve (OPSX)
---

Continue working on a bug-fix change by creating the **next** artifact, then **eval → refine artifact → user approval**. `bugfix-plan.md` is the one exception — see step 5a: it is generated silently with no eval gate and no approval.

**Input**: Optional change name after `/opsx-continue` (e.g. `/opsx-continue cm-830`).

## Schema package (resolve first existing path)

| Role | Installed | Distribution |
|------|-----------|--------------|
| Schema root | `openspec/schemas/openspec-bugfix-workflow/` | `schemas/openspec-bugfix-workflow/` |
| Stage gate | `{schema_root}/stage-gate/` | same |
| Stage evals | `{schema_root}/evals/<stage>_eval.yaml` | same |
| Templates | `{schema_root}/templates/` | same |

## Steps

1. Select change (`openspec list --json` if name not given).
2. `openspec status --change "<name>" --json`
3. Read `openspec/changes/<name>/inputs/jira.yaml` (required).
4. **Resolve repo target and agents.md before Repro Verification** (see schema `target_repo`, `agents_md`, and `working_folder_repo`):
   - **Working-folder mode:** If the user directs using the working folder as the repo,
     set `use_working_folder_as_repo: true` in `inputs/jira.yaml`, record
     `working_folder_path`, analyze cwd — do not ask for GitHub URL or clone separately.
   - **Default mode:** If the next ready artifact is `repro-verification` and
     `target_repo` is absent or empty in `jira.yaml`:
     - Ask the user once: "Provide the URL of the target GitHub repository
       (e.g. https://github.com/org/repo)."
     - Persist `target_repo` to `inputs/jira.yaml`.
     - Verify the repository is accessible before creating repro-verification-report.md.
   - **agents.md (REQUIRED):** Resolve via schema `agents_md.lookup_order` — prefer
     `openspec/inputs/agents.md`; else `AGENTS.md`/`agents.md` in the target repo.
     STOP and ask the user to provide it if unresolved. Do not create
     repro-verification-report.md (or any later artifact) until resolved.
   - For earlier artifacts (`bug-validation`, `bug-report`), `target_repo` and
     `agents.md` are not required.
5. Pick first artifact with `status: "ready"`.
5a. **Hidden bugfix-plan handoff** (ONLY when next ready artifact is `bugfix-plan`):
    - Generate `bugfix-plan.md` per schema artifact `bugfix-plan` instruction —
      **no eval gate, no evaluation report, no user approval**. Mark it done
      automatically (see `artifact-eval-map.yaml` → `bugfix-plan.gate: skip`).
    - Do NOT present bugfix-plan.md content to the user, and do NOT ask them to
      approve it.
    - Immediately continue in this same invocation: `tasks` is now the next
      ready artifact. Read `bugfix-plan.md` §8 Open Questions and ask the user
      any clarifying questions needed to scope the backlog (combine with the
      task sizing prompt in step 5b below into a single question turn). Wait
      for the user's answer before generating `tasks.md`.
    - Once answered (or the user has none), proceed with `tasks` generation
      per the normal flow (steps 6–11) — this covers both `bugfix-plan` and
      `tasks` in one `/opsx-continue` invocation, since bugfix-plan has no
      user-facing checkpoint of its own.
5b. **Task sizing prompt** (ONLY when next ready artifact is `tasks`):
    - Read `config.yaml → flags.task_sizing`.
    - If `prompt_user` is true:
      - ASK the user ONCE (combine with any bugfix-plan.md §8 open questions
        from step 5a into a single message):
        ```
        Bug fix plan is ready internally. How many tasks should the backlog target?
        Enter a range: min max (e.g. "3 8")
        Press Enter to use defaults ({default_min}–{default_max}).
        ```
      - Parse response. Empty → defaults from config.
      - Inject into generation context as metadata field:
        `task_sizing: { min: X, max: Y, consolidation_threshold: Z }`
    - If `prompt_user` is false: inject defaults silently (no prompt).
    - **Do NOT re-prompt during eval gate, feedback loop, or regeneration.**
      The task_sizing metadata persists for the lifetime of this artifact generation.
6. **Telemetry — signal artifact start** (silent, non-blocking):
   ```bash
   python -m openspec.telemetry.auto on-artifact-start --change "<name>" --artifact "<artifact-id>"
   ```
7. `openspec instructions <artifact-id> --change "<name>" --json` → create artifact at `outputPath` (**v1**).
   - Generation uses **`{schema_root}/templates/`** (from openspec instructions).
   - For `tasks` artifact: pass `task_sizing` metadata to the template.
8. **Telemetry — signal artifact written** (silent, non-blocking):
   ```bash
   python -m openspec.telemetry.auto on-artifact-created --change "<name>" --artifact "<artifact-id>"
   ```
9. **Stage eval gate** (skip entirely for `bugfix-plan` — see step 5a) — read and follow
   **`{schema_root}/stage-gate/STAGE_EVAL_GATE_PROMPT.md`** Steps 1–5 exactly.
   This is the single source of truth for eval scoring, artifact refinement, evaluation report
   generation, and user approval. Key paths used by the prompt:
   - Artifact-to-eval mapping: `{schema_root}/stage-gate/artifact-eval-map.yaml`
   - Stage eval cases: `{schema_root}/evals/<stage>_eval.yaml`
   - Eval results output: `openspec/changes/<name>/eval-results/<artifact-id>.yaml`
   - Evaluation report output: `openspec/changes/<name>/eval-results/<artifact-id>_evaluation_report.md`
   - On user rejection: follow **`{schema_root}/stage-gate/USER_FEEDBACK_PROMPT.md`**
   - On `bug-report` rejection: **exit workflow** (schema `exit_on_reject.bug-report`) — do NOT regenerate; STOP
10. **Telemetry — signal waiting for approval** (silent, non-blocking; skip for `bugfix-plan`):
    ```bash
    python -m openspec.telemetry.auto on-waiting-approval --change "<name>" --artifact "<artifact-id>" --score <eval_score>
    ```
11. **After user approves or rejects**, signal the outcome:
    ```bash
    python -m openspec.telemetry.auto on-artifact-complete --change "<name>" --artifact "<artifact-id>" --status passed --score <eval_score> --label "<quality_label>"
    ```
    Use `--status failed` if the user rejects the artifact.

## Artifact order (openspec-bugfix-workflow)

```
bug-validation.json → bug-report.md → repro-verification-report.md → rca-report.md
  → bugfix-plan.md (internal — no approval) → tasks.md → /opsx-apply → archive
```

## Eval gate by artifact

| Artifact | Stage eval file (under `{schema_root}/`) |
|----------|--------------------------------------------|
| bug-validation | Rubric in `templates/bug-validation-template.md` only |
| bug-report | `evals/bug-report_eval.yaml` |
| repro-verification | `evals/repro-verification_eval.yaml` |
| rca | `evals/rca_eval.yaml` |
| bugfix-plan | **Skip — internal artifact, no eval gate, no approval** |
| tasks | `evals/tasks_eval.yaml` |

## Guardrails

- ONE user-visible artifact per invocation, except `bugfix-plan` + `tasks` which
  are combined in one invocation per step 5a (bugfix-plan has no checkpoint)
- Do not skip eval gate for artifacts with `gate: stage_evals`
- Do not skip user approval for user-visible artifacts
- Never present bugfix-plan.md content or ask for its approval
- Do not refine **templates** during eval gate — refine the **change artifact** only
- User rejection feedback loop **may** patch `{schema_root}/templates/` when required; write summaries to `feedback_stage_artifacts/`
- `target_repo` and `agents.md` required before repro-verification — **not** at `/opsx-new`
- Do not create the next user-visible artifact until the user approves the current one
- **No background sub-agents** — Do NOT launch background sub-agents, background shells, or Task-tool agents with `run_in_background=true` during `/opsx-continue`. Telemetry hooks execute in the main agent session only; background work cannot be metered and produces missing or incorrect metrics.

## Batch / Continue-All Telemetry

When the user requests "continue all" or approves multiple artifacts in a single session, use `--batch` flags on telemetry hooks so tokens are attributed consistently:

- `python -m openspec.telemetry.auto on-artifact-start --change "<name>" --artifact "<artifact-id>" --batch`
- `python -m openspec.telemetry.auto on-artifact-created --change "<name>" --artifact "<artifact-id>" --batch`
- `python -m openspec.telemetry.auto on-artifact-complete --change "<name>" --artifact "<artifact-id>" --status passed --score <eval_score> --label "<quality_label>" --batch`
