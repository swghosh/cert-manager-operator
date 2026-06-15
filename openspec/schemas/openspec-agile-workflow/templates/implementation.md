# Implementation Phase Log

**Change**: [CHANGE_NAME]
**Jira**: [JIRA_KEY]
**Fork**: [FORK_REPO_URL]
**Branch**: [FEATURE_BRANCH]
**Started**: [DATE]

Append one section per approved phase during `/opsx:apply`. Code changes go to the fork working copy — not this file.

---

## Phase: [PHASE_NAME]

**Status**: [Approved | In Progress | Rejected]
**Tasks**: [T1_1, T1_2, …]

### Files Touched

- `relative/path/to/file`

### Test Results

| Test | Result | Notes |
|------|--------|-------|
| [test name] | PASSED / FAILED / SKIPPED | [brief detail] |

### Deviations

- **Task ID**: [description and rationale — omit section when none]

---

## Phase Log Notes

- Phases execute in dependency order from tasks.md §1–§2.
- Each phase requires user approval before advancing.
- On reject: re-generate FILE OPERATIONS, re-apply, repeat until approved.
