"""Generate metrics-report.json from events.jsonl and filesystem artifacts.

Reconstructs run, phases, tasks, events, global_health, and artifact_edits
entirely from local files — no database, no server.
"""
from __future__ import annotations

import json
import logging
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .change_metrics import (
    ARTIFACT_PHASE_MAP,
    count_feedback_rounds,
    phase5_iteration_count,
    phase5_should_close,
    phase_duration_s,
    phase_iteration_count,
    read_eval_refinement_round,
    read_task_refinement_rounds,
)

logger = logging.getLogger(__name__)

CHANGES_DIR = Path("openspec/changes")

# Approximate per-token pricing (USD per 1M tokens).
# Uses Claude Sonnet-class rates as the default since Cursor primarily routes
# through Claude. Override by editing this table if your setup differs.
PRICE_TABLE: dict[str, dict[str, float]] = {
    "default": {"input": 3.0, "output": 15.0},
    "claude-sonnet": {"input": 3.0, "output": 15.0},
    "claude-opus": {"input": 15.0, "output": 75.0},
    "gpt-4o": {"input": 2.5, "output": 10.0},
}


def _normalize_model_key(model: str) -> str:
    """Map a raw model name to a PRICE_TABLE key."""
    if not model:
        return "default"
    if model in PRICE_TABLE:
        return model
    lowered = model.lower()
    if "opus" in lowered:
        return "claude-opus"
    if "sonnet" in lowered:
        return "claude-sonnet"
    if "gpt-4o" in lowered or "gpt4o" in lowered:
        return "gpt-4o"
    if "composer" in lowered:
        return "claude-sonnet"
    return "default"


def _estimate_cost(tokens_in: int, tokens_out: int, model: str = "default") -> float:
    """Estimate USD cost from token counts using the price table."""
    rates = PRICE_TABLE.get(_normalize_model_key(model), PRICE_TABLE["default"])
    return (tokens_in * rates["input"] + tokens_out * rates["output"]) / 1_000_000


def _detect_operator_name() -> str:
    """Extract the operator/repo name from ``git remote get-url origin``."""
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True, text=True, timeout=5,
        )
        url = result.stdout.strip()
        if not url:
            return ""
        name = url.rstrip("/").rsplit("/", 1)[-1]
        if name.endswith(".git"):
            name = name[:-4]
        return name
    except Exception:
        return ""


def _read_events(change_dir: Path) -> list[dict[str, Any]]:
    events_file = change_dir / "telemetry" / "events.jsonl"
    if not events_file.exists():
        return []
    events = []
    for line in events_file.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return events


def _reconstruct_run(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Build run object from the first run_create event."""
    for ev in events:
        if ev.get("type") == "run_create":
            metadata = ev.get("metadata") or {}
            run: dict[str, Any] = {
                "id": ev.get("id", ""),
                "change_name": ev.get("change_name", ""),
                "jira_key": ev.get("jira_key", ""),
                "branch": ev.get("branch", ""),
                "primary_model": metadata.get("model_id", ""),
                "status": "running",
                "started_at": ev.get("ts", ""),
                "completed_at": None,
                "total_tokens_in": 0,
                "total_tokens_out": 0,
            }
            break
    else:
        return {}

    for ev in events:
        if ev.get("type") == "run_end":
            run["status"] = ev.get("status", "completed")
            run["completed_at"] = ev.get("ts")
    return run


def _reconstruct_phases(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build phase objects from phase_start / phase_end / phase_progress events."""
    phases: dict[str, dict[str, Any]] = {}
    order: list[str] = []

    for ev in events:
        etype = ev.get("type", "")
        if etype == "phase_start":
            pid = ev.get("id", "")
            if pid and pid not in phases:
                order.append(pid)
            phases[pid] = {
                "id": pid,
                "run_id": ev.get("run_id", ""),
                "phase_number": ev.get("phase_number", 0),
                "phase_name": ev.get("phase_name", ""),
                "status": "running",
                "started_at": ev.get("ts", ""),
                "completed_at": None,
                "tokens_in": 0,
                "tokens_out": 0,
                "quality_score": 0,
                "quality_label": "",
                "iteration_count": 1,
                "duration_s": 0.0,
                "processing_time_s": 0.0,
            }
        elif etype == "phase_end":
            pid = ev.get("phase_id", "")
            if pid in phases:
                phases[pid].update({
                    "status": ev.get("status", "passed"),
                    "completed_at": ev.get("ts"),
                    "tokens_in": ev.get("tokens_in", phases[pid]["tokens_in"]),
                    "tokens_out": ev.get("tokens_out", phases[pid]["tokens_out"]),
                    "quality_score": ev.get("quality_score", phases[pid]["quality_score"]),
                    "quality_label": ev.get("quality_label", phases[pid]["quality_label"]),
                    "iteration_count": ev.get("iteration_count", phases[pid]["iteration_count"]),
                })
                if ev.get("duration_s") is not None:
                    phases[pid]["duration_s"] = ev["duration_s"]
                if ev.get("processing_time_s") is not None:
                    phases[pid]["processing_time_s"] = ev["processing_time_s"]
        elif etype == "phase_progress":
            pid = ev.get("phase_id", "")
            if pid in phases:
                if ev.get("status"):
                    phases[pid]["status"] = ev["status"]
                    if ev["status"] == "running":
                        phases[pid]["completed_at"] = None
                for key in ("tokens_in", "tokens_out", "quality_score", "quality_label", "iteration_count"):
                    if ev.get(key) is not None:
                        phases[pid][key] = ev[key]
                if ev.get("duration_s") is not None:
                    phases[pid]["duration_s"] = ev["duration_s"]

    result = [phases[pid] for pid in order if pid in phases]

    # Fix #3: Compute duration_s from event timestamps when the filesystem
    # fallback returned 0 or a placeholder.
    for p in result:
        if p.get("started_at") and p.get("completed_at"):
            try:
                t0 = datetime.fromisoformat(str(p["started_at"]).replace("Z", "+00:00"))
                t1 = datetime.fromisoformat(str(p["completed_at"]).replace("Z", "+00:00"))
                event_dur = max(0.0, (t1 - t0).total_seconds())
                if p["duration_s"] in (0.0, 60.0, 300.0) or event_dur > p["duration_s"]:
                    p["duration_s"] = round(event_dur, 1)
            except (TypeError, ValueError):
                pass

    # Fix #5: Auto-close orphan "running" phases when later phases are already
    # passed (the on-artifact-complete hook was likely skipped).
    max_passed = max(
        (p["phase_number"] for p in result if p.get("status") == "passed"),
        default=0,
    )
    for p in result:
        if p.get("status") == "running" and p["phase_number"] < max_passed:
            p["status"] = "passed"
            if not p.get("completed_at"):
                next_phases = [
                    q for q in result
                    if q["phase_number"] > p["phase_number"] and q.get("started_at")
                ]
                if next_phases:
                    p["completed_at"] = next_phases[0]["started_at"]
                    try:
                        t0 = datetime.fromisoformat(str(p["started_at"]).replace("Z", "+00:00"))
                        t1 = datetime.fromisoformat(str(p["completed_at"]).replace("Z", "+00:00"))
                        p["duration_s"] = round(max(0.0, (t1 - t0).total_seconds()), 1)
                    except (TypeError, ValueError):
                        pass

    return result


def _reconstruct_tasks(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build task objects from task_start / task_end events.

    Deduplicates by ``task_id``: when a task is started multiple times (e.g.
    agent retry), keep the entry that reached ``passed`` or, failing that,
    the latest one.  This prevents stale "running" duplicates from inflating
    ``tasks_total``.
    """
    tasks: dict[str, dict[str, Any]] = {}
    order: list[str] = []

    for ev in events:
        etype = ev.get("type", "")
        if etype == "task_start":
            tid = ev.get("id", "")
            if tid and tid not in tasks:
                order.append(tid)
            tasks[tid] = {
                "id": tid,
                "run_id": ev.get("run_id", ""),
                "phase_id": ev.get("phase_id", ""),
                "task_id": ev.get("task_id", ""),
                "task_title": ev.get("task_title", ""),
                "agent_id": ev.get("agent_id", ""),
                "status": "running",
                "started_at": ev.get("ts", ""),
                "completed_at": None,
                "tokens_in": 0,
                "tokens_out": 0,
                "self_correction_loops": 0,
                "processing_time_s": 0.0,
                "attribution": None,
            }
        elif etype == "task_end":
            tpk = ev.get("task_pk", "")
            if tpk in tasks:
                update: dict[str, Any] = {
                    "status": ev.get("status", "passed"),
                    "completed_at": ev.get("ts"),
                    "tokens_in": ev.get("tokens_in", 0),
                    "tokens_out": ev.get("tokens_out", 0),
                    "self_correction_loops": ev.get("self_correction_loops", 0),
                }
                if ev.get("processing_time_s") is not None:
                    update["processing_time_s"] = ev["processing_time_s"]
                if "verification_pass" in ev:
                    update["verification_pass"] = ev["verification_pass"]
                if ev.get("verification_command"):
                    update["verification_command"] = ev["verification_command"]
                if ev.get("verification_result"):
                    update["verification_result"] = ev["verification_result"]
                if ev.get("verification_output"):
                    update["verification_output"] = ev["verification_output"]
                if ev.get("attribution"):
                    update["attribution"] = ev["attribution"]
                tasks[tpk].update(update)

    all_tasks = [tasks[tid] for tid in order if tid in tasks]
    deduped = _dedupe_tasks(all_tasks)
    return deduped


def _dedupe_tasks(tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep one entry per ``task_id``, preferring passed > completed > latest."""
    by_task_id: dict[str, list[dict[str, Any]]] = {}
    for t in tasks:
        by_task_id.setdefault(t["task_id"], []).append(t)

    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for t in tasks:
        tid = t["task_id"]
        if tid in seen:
            continue
        seen.add(tid)
        candidates = by_task_id[tid]
        passed = [c for c in candidates if c["status"] == "passed"]
        best = passed[-1] if passed else candidates[-1]
        deduped.append(best)
    return deduped


def _enrich_tasks_from_filesystem(tasks: list[dict[str, Any]], change_dir: Path) -> None:
    """Enrich tasks with verification data from filesystem sources.

    Fills in missing verification fields from:
    1. implementation/state.yaml completed[] entries
    2. implementation/task-reports/<task-id>.md ## Verification table
    """
    import re

    # Source 1: state.yaml completed entries
    state_path = change_dir / "implementation" / "state.yaml"
    completed_by_id: dict[str, dict[str, Any]] = {}
    if state_path.exists():
        try:
            import yaml
            data = yaml.safe_load(state_path.read_text()) or {}
            current = data.get("current_task_result") or {}
            if current.get("task_id"):
                completed_by_id[current["task_id"]] = current
            for entry in data.get("completed", []):
                tid = entry.get("task_id")
                if tid:
                    completed_by_id[tid] = entry
        except Exception:
            pass

    for task in tasks:
        tid = task.get("task_id", "")
        all_populated = (
            task.get("verification_pass") is not None
            and task.get("verification_command")
            and task.get("verification_result")
            and task.get("verification_output")
        )
        if all_populated:
            continue

        # Try state.yaml completed entry for any missing fields
        state_entry = completed_by_id.get(tid)
        if state_entry:
            if task.get("verification_pass") is None and "verification_pass" in state_entry:
                task["verification_pass"] = bool(state_entry["verification_pass"])
            if not task.get("verification_command") and "test_command" in state_entry:
                task["verification_command"] = str(state_entry["test_command"])
            if "test_result" in state_entry:
                if not task.get("verification_result"):
                    task["verification_result"] = str(state_entry["test_result"])
                if task.get("verification_pass") is None:
                    task["verification_pass"] = state_entry["test_result"].upper() in ("PASS", "PASSED")
            if not task.get("verification_output") and "test_output_summary" in state_entry:
                task["verification_output"] = str(state_entry["test_output_summary"])[:2000]

        # Try task-reports/<task-id>.md for any still-missing fields
        all_populated = (
            task.get("verification_pass") is not None
            and task.get("verification_command")
            and task.get("verification_result")
            and task.get("verification_output")
        )
        if all_populated:
            continue

        report_path = change_dir / "implementation" / "task-reports" / f"{tid}.md"
        if not report_path.exists():
            continue
        try:
            content = report_path.read_text()
        except OSError:
            continue

        verif_match = re.search(r'##\s+Verification\s*\n(.*?)(?=\n##|\Z)', content, re.DOTALL)
        if verif_match:
            table_text = verif_match.group(1)
            rows = re.findall(r'\|\s*(.+?)\s*\|\s*(PASSED|FAILED|PASS|FAIL)\s*\|', table_text, re.IGNORECASE)
            if rows:
                all_passed = all(r[1].upper() in ("PASSED", "PASS") for r in rows)
                any_failed = any(r[1].upper() in ("FAILED", "FAIL") for r in rows)
                checks = [f"{r[0].strip()}: {r[1].strip()}" for r in rows]
                if task.get("verification_pass") is None:
                    task["verification_pass"] = all_passed and not any_failed
                if not task.get("verification_result"):
                    task["verification_result"] = "PASS" if (all_passed and not any_failed) else "FAIL"
                if not task.get("verification_output"):
                    task["verification_output"] = "; ".join(checks)[:2000]

        if not task.get("verification_command"):
            cmd_match = re.search(r'`((?:go\s+(?:test|build|vet)|make\s+\S+|bash\s+-n)[^`]*)`', content)
            if cmd_match:
                task["verification_command"] = cmd_match.group(1)[:512]


def _collect_log_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Extract log_event entries."""
    return [
        {
            "id": ev.get("id", ""),
            "ts": ev.get("ts", ""),
            "run_id": ev.get("run_id", ""),
            "task_id": ev.get("task_id"),
            "agent_id": ev.get("agent_id", ""),
            "event_type": ev.get("event_type", ""),
            "message": ev.get("message", ""),
            "metadata_json": ev.get("metadata_json"),
        }
        for ev in events
        if ev.get("type") == "log_event"
    ]


def _compute_global_health(
    run: dict[str, Any],
    phases: list[dict[str, Any]],
    tasks: list[dict[str, Any]],
    change_dir: Path,
) -> dict[str, Any]:
    """Compute global health metrics from in-memory data.

    Token counting uses **phase totals only**.  Phase 5 (code_generation)
    already aggregates task-level tokens via ``on-apply-complete``, so adding
    task tokens on top would double-count.
    """
    total_in = sum(p.get("tokens_in", 0) for p in phases)
    total_out = sum(p.get("tokens_out", 0) for p in phases)
    total_tokens = total_in + total_out
    if total_tokens == 0:
        total_tokens = run.get("total_tokens_in", 0) + run.get("total_tokens_out", 0)

    wall_time = 0.0
    started_at = run.get("started_at", "")
    if started_at:
        try:
            start = datetime.fromisoformat(str(started_at).replace("Z", "+00:00"))
            end_raw = run.get("completed_at")
            if end_raw:
                end = datetime.fromisoformat(str(end_raw).replace("Z", "+00:00"))
            else:
                end = datetime.now(timezone.utc)
            wall_time = max(0.0, (end - start).total_seconds())
        except (TypeError, ValueError):
            pass

    total_phases = len(phases)
    first_pass = sum(
        1 for p in phases
        if p.get("iteration_count", 1) == 1 and p.get("status") == "passed"
    )

    scored_phases = [p for p in phases if p.get("quality_score", 0) > 0]
    compliance = (
        sum(p["quality_score"] for p in scored_phases) / len(scored_phases)
        if scored_phases
        else 0.0
    )
    gate_passing = (first_pass / total_phases * 100) if total_phases > 0 else 100.0
    total_refinement = sum(max(0, p.get("iteration_count", 1) - 1) for p in phases)
    human_rejection = (total_refinement / total_phases * 100) if total_phases > 0 else 0.0

    phase_duration = sum(p.get("duration_s", 0) for p in phases)
    if phase_duration > wall_time:
        wall_time = phase_duration

    tasks_total = len(tasks)
    tasks_passed = sum(1 for t in tasks if t.get("status") == "passed")
    success_rate = (tasks_passed / tasks_total * 100) if tasks_total > 0 else 100.0

    estimated_cost = _estimate_cost(total_in, total_out, run.get("primary_model", ""))

    # Fix #2: populate run.total_tokens_in/out so top-level summary is useful
    run["total_tokens_in"] = total_in
    run["total_tokens_out"] = total_out

    agent_proc_time = sum(p.get("processing_time_s", 0) for p in phases)

    return {
        "total_tokens_consumed": total_tokens,
        "estimated_cost_usd": round(estimated_cost, 4),
        "cumulative_wall_time_s": round(wall_time, 1),
        "agent_processing_time_s": round(agent_proc_time, 1),
        "compliance_index": round(compliance, 1),
        "gate_passing_rate": round(gate_passing, 1),
        "human_rejection_rate": round(human_rejection, 1),
        "total_refinement_iterations": total_refinement,
        "agent_success_rate": round(success_rate, 1),
        "tasks_passed": tasks_passed,
        "tasks_total": tasks_total,
    }


def _compute_artifact_edits(change_dir: Path) -> dict[str, Any]:
    """Compute artifact edit metrics from filesystem."""
    entries: list[dict[str, Any]] = []

    for artifact_id, (_phase_num, phase_name, _is_last) in ARTIFACT_PHASE_MAP.items():
        artifact_path = change_dir / f"{artifact_id}.md"
        if not artifact_path.exists():
            artifact_path = change_dir / f"{artifact_id}.json"
        if not artifact_path.exists():
            continue
        eval_ref = read_eval_refinement_round(change_dir, artifact_id)
        fb = count_feedback_rounds(change_dir, artifact_id)
        entries.append({
            "artifact_id": artifact_id,
            "phase_name": phase_name,
            "eval_refinements": eval_ref,
            "feedback_rounds": fb,
            "total_edits": eval_ref + fb,
        })

    return {
        "artifacts": entries,
        "total_edits": sum(e["total_edits"] for e in entries),
    }


def generate_report(change: str) -> Path:
    """Generate metrics-report.json for a single change.

    Returns the path to the written report.
    """
    from .jira_metadata import enrich_run_metadata, read_jira_report_fields

    change_dir = CHANGES_DIR / change
    events = _read_events(change_dir)

    run = _reconstruct_run(events)
    phases = _reconstruct_phases(events)
    tasks = _reconstruct_tasks(events)
    _enrich_tasks_from_filesystem(tasks, change_dir)
    log_events = _collect_log_events(events)

    if run:
        enrich_run_metadata(run, change_dir)

    global_health = _compute_global_health(run, phases, tasks, change_dir) if run else {
        "total_tokens_consumed": 0,
        "estimated_cost_usd": 0.0,
        "cumulative_wall_time_s": 0.0,
        "agent_processing_time_s": 0.0,
        "compliance_index": 0.0,
        "gate_passing_rate": 100.0,
        "human_rejection_rate": 0.0,
        "total_refinement_iterations": 0,
        "agent_success_rate": 100.0,
        "tasks_passed": 0,
        "tasks_total": 0,
    }
    artifact_edits = _compute_artifact_edits(change_dir)

    verified_entries = []
    for t in tasks:
        if t.get("verification_pass") is None and not t.get("verification_command"):
            continue
        verified_entries.append({
            "task_id": t.get("task_id", ""),
            "task_title": t.get("task_title", ""),
            "verification_pass": t.get("verification_pass"),
            "verification_command": t.get("verification_command", ""),
            "verification_result": t.get("verification_result", ""),
            "verification_output": t.get("verification_output", ""),
        })
    verification_summary = {
        "entries": verified_entries,
        "total_verified": len(verified_entries),
        "total_passed": sum(1 for e in verified_entries if e.get("verification_pass") is True),
        "total_failed": sum(1 for e in verified_entries if e.get("verification_pass") is False),
    }

    jira_fields = read_jira_report_fields(change_dir)

    report: dict[str, Any] = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "operator_name": _detect_operator_name(),
        **jira_fields,
        "run": run,
        "phases": phases,
        "tasks": tasks,
        "events": log_events,
        "global_health": global_health,
        "artifact_edits": artifact_edits,
        "verification_summary": verification_summary,
    }

    report_path = change_dir / "telemetry" / "metrics-report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, default=str) + "\n")
    logger.info("Wrote metrics report: %s", report_path)
    return report_path


def main() -> None:
    """CLI entry point: python -m openspec.telemetry.report --change <name>"""
    import argparse
    parser = argparse.ArgumentParser(description="Generate metrics report for an OpenSpec change")
    parser.add_argument("--change", required=True, help="Change slug (e.g. cm-830)")
    args = parser.parse_args()
    path = generate_report(args.change)
    print(json.dumps({"ok": True, "path": str(path)}))


if __name__ == "__main__":
    main()
