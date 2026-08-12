"""Parse iteration and edit metrics from OpenSpec change directories on disk."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

ARTIFACT_PHASE_MAP: dict[str, tuple[int, str, bool]] = {
    "validation": (1, "spec_understanding", False),
    "specs": (1, "spec_understanding", True),
    "repo-assessment": (2, "repo_assessment", True),
    "constitution": (2, "repo_assessment", False),
    "plan": (3, "arch_planning", True),
    "tasks": (4, "subtask_creation", True),
}

PHASE_ARTIFACTS: dict[int, list[str]] = {}
for artifact_id, (phase_num, _name, _is_last) in ARTIFACT_PHASE_MAP.items():
    PHASE_ARTIFACTS.setdefault(phase_num, []).append(artifact_id)


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = yaml.safe_load(path.read_text()) or {}
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _eval_path(change_dir: Path, artifact_id: str) -> Path:
    return change_dir / "eval-results" / f"{artifact_id}.yaml"


def read_eval_refinement_round(change_dir: Path, artifact_id: str) -> int:
    """Extra eval-gate refinements beyond the initial draft (0 = first pass only).

    ``refinement_round`` / ``refinement_rounds`` in eval YAML is 1-indexed pass
    number (1 = first eval, 2 = one refinement). This returns pass - 1.
    """
    data = _load_yaml(_eval_path(change_dir, artifact_id))
    for key in ("refinement_round", "refinement_rounds"):
        val = data.get(key)
        if val is not None:
            try:
                return max(0, int(val) - 1)
            except (TypeError, ValueError):
                pass
    return 0


def read_task_refinement_rounds(change_dir: Path, task_id: str) -> int:
    """Code-generation eval refinement rounds for a task."""
    path = change_dir / "eval-results" / f"code-generation-{task_id}.yaml"
    data = _load_yaml(path)
    val = data.get("refinement_rounds", data.get("refinement_round"))
    if val is not None:
        try:
            return max(0, int(val))
        except (TypeError, ValueError):
            pass
    return 0


def count_feedback_rounds(change_dir: Path, artifact_id: str) -> int:
    """User rejection feedback rounds from feedback_stage_artifacts/."""
    feedback_dir = change_dir / "feedback_stage_artifacts" / artifact_id
    if not feedback_dir.is_dir():
        joint = change_dir / "feedback_stage_artifacts" / "repo-assessment+constitution"
        if artifact_id in ("repo-assessment", "constitution") and joint.is_dir():
            return len(list(joint.glob("round-*.yaml")))
        return 0
    return len(list(feedback_dir.glob("round-*.yaml")))


def artifact_edit_count(change_dir: Path, artifact_id: str) -> int:
    """Total edits = eval refinements + user feedback rounds."""
    return read_eval_refinement_round(change_dir, artifact_id) + count_feedback_rounds(
        change_dir, artifact_id
    )


def phase_iteration_count(change_dir: Path, phase_number: int) -> int:
    """Eval pass count for phase waterfall (1 = first pass only)."""
    artifacts = PHASE_ARTIFACTS.get(phase_number, [])
    if not artifacts:
        return 1
    edit_counts = [artifact_edit_count(change_dir, a) for a in artifacts]
    if not edit_counts:
        return 1
    return max(1, max(edit_counts) + 1)


def total_refinement_iterations(change_dir: Path) -> int:
    """Sum of (iteration_count - 1) across phases 1-4 for human-rejection proxy."""
    total = 0
    for phase_num in PHASE_ARTIFACTS:
        ic = phase_iteration_count(change_dir, phase_num)
        total += max(0, ic - 1)
    return total


def _parse_scored_at(data: dict[str, Any]) -> datetime | None:
    raw = data.get("scored_at")
    if not raw:
        return None
    try:
        if isinstance(raw, datetime):
            return raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def phase_duration_s(change_dir: Path, phase_number: int) -> float:
    """Duration from earliest to latest eval scored_at in phase, or file mtime fallback."""
    artifacts = PHASE_ARTIFACTS.get(phase_number, [])
    timestamps: list[datetime] = []
    for artifact_id in artifacts:
        data = _load_yaml(_eval_path(change_dir, artifact_id))
        ts = _parse_scored_at(data)
        if ts:
            timestamps.append(ts)
        else:
            for ext in (".md", ".json"):
                p = change_dir / f"{artifact_id}{ext}"
                if p.exists():
                    timestamps.append(
                        datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc)
                    )
                    break
    if len(timestamps) >= 2:
        return max(0.0, (max(timestamps) - min(timestamps)).total_seconds())
    if len(timestamps) == 1:
        return 60.0
    return 0.0


def parse_task_ids_from_tasks_md(change_dir: Path) -> list[str]:
    """Extract task IDs from tasks.md section 2 linear execution order."""
    tasks_md = change_dir / "tasks.md"
    if not tasks_md.exists():
        return []
    content = tasks_md.read_text()
    task_ids = re.findall(r"\d+\.\s+(T\d+_\d+)\s*[—–-]", content)
    if not task_ids:
        task_ids = re.findall(r"- \[[ x]\]\s+\*?\*?(T\d+_\d+)", content)
    if not task_ids:
        task_ids = re.findall(r"\b(T\d+_\d+)\b", content)
        task_ids = list(dict.fromkeys(task_ids))
    return task_ids


def phase5_should_close(
    change_dir: Path,
    *,
    close_on: str = "implementation_report",
) -> tuple[bool, str]:
    """Return (should_close, quality_label) for code_generation phase."""
    task_ids = parse_task_ids_from_tasks_md(change_dir)
    reports_dir = change_dir / "implementation" / "task-reports"
    existing = {f.stem for f in reports_dir.glob("*.md")} if reports_dir.exists() else set()
    report_count = len(existing)

    impl_report = change_dir / "implementation-report.md"
    if impl_report.exists():
        return True, f"implementation report complete ({report_count} task reports)"

    if close_on == "all_tasks" and task_ids and all(tid in existing for tid in task_ids):
        return True, f"{len(task_ids)}/{len(task_ids)} tasks approved"

    if task_ids and all(tid in existing for tid in task_ids):
        return True, f"{len(task_ids)}/{len(task_ids)} tasks approved"

    if report_count > 0 and task_ids:
        return True, f"{report_count}/{len(task_ids)} tasks approved"

    return False, "code generation in progress"


def phase5_iteration_count(change_dir: Path) -> int:
    """Max code-gen refinement rounds + 1 across tasks with reports."""
    reports_dir = change_dir / "implementation" / "task-reports"
    if not reports_dir.exists():
        return 1
    rounds = [
        read_task_refinement_rounds(change_dir, f.stem)
        for f in reports_dir.glob("*.md")
    ]
    if not rounds:
        return 1
    return max(1, max(rounds) + 1)
