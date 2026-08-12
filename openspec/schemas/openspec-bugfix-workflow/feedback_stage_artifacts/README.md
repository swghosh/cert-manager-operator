# Feedback stage artifacts — user rejection loop

When the user **rejects with feedback** at an artifact approval gate (`/opsx-continue`),
the agent runs the feedback stage (`user_approval_feedback_gate` in `schema.yaml`,
`stage-gate/USER_FEEDBACK_PROMPT.md`).

## Runtime summaries (per change)

Write one file per feedback round:

```
openspec/changes/<change-name>/feedback_stage_artifacts/<artifact-id>/round-<N>.yaml
```

## Round file schema

```yaml
round: 1
artifact_ids: [repro-verification]
timestamp: <ISO8601>
user_feedback: |
  Verbatim rejection feedback from the user.

context:
  prior_artifacts_read_only:
    - openspec/changes/<change>/bug-report.md
  current_artifacts:
    - openspec/changes/<change>/repro-verification-report.md
  template: templates/repro-verification-template.md

template_update:
  required: false
  path: templates/repro-verification-template.md
  summary: |
    Optional — only when feedback requires a durable template change.

artifact_regeneration:
  paths:
    - openspec/changes/<change>/repro-verification-report.md
  summary: |
    Regenerated repro steps with captured failure signature.

eval_gate:
  rerun: true
  results_path: openspec/changes/<change>/eval-results/repro-verification.yaml
  overall_score: 88
  overall_pass: true

feedback_addressed:
  - "User: missing pod logs → Added operator log excerpts per step"
```

## This directory

The `feedback_stage_artifacts/` folder under `{schema_root}` holds this README and format
spec only. **Do not** store change-specific summaries here — they live under each change
(see paths above) so they survive schema reinstall.
