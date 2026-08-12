"""Automatic telemetry hooks for the OpenSpec pipeline.

Wraps key openspec CLI lifecycle events so telemetry is emitted transparently.
After each hook, auto-generates ``metrics-report.json``.

Usage:

    python -m openspec.telemetry.auto on-new    --change cm-830 --jira-key CM-830 --model claude-opus-4.6
    python -m openspec.telemetry.auto on-artifact-complete --change cm-830 --artifact specs --status passed --score 91
    python -m openspec.telemetry.auto on-task-start --change cm-830 --task-id T1_1 --agent API_Agent
    python -m openspec.telemetry.auto on-task-complete --change cm-830 --task-id T1_1 --status passed
    python -m openspec.telemetry.auto on-apply-complete --change cm-830
    python -m openspec.telemetry.auto sync --change cm-830
    python -m openspec.telemetry.auto report --change cm-830
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

from datetime import datetime, timezone

from .change_metrics import (
    ARTIFACT_PHASE_MAP,
    phase5_iteration_count,
    phase5_should_close,
    phase_duration_s,
    phase_iteration_count,
    read_task_refinement_rounds,
)

logger = logging.getLogger(__name__)

CHANGES_DIR = Path("openspec/changes")
STATE_FILE = ".dashboard.json"


def _resolve_model(args: argparse.Namespace | None, state: dict[str, Any] | None) -> str:
    """Resolve the active model from CLI arg, persisted state, or environment."""
    if args is not None:
        cli_model = getattr(args, "model", "") or ""
        if cli_model.strip():
            return cli_model.strip()
    if state and state.get("model_id"):
        return str(state["model_id"]).strip()
    for env_var in ("CURSOR_MODEL", "CURSOR_ACTIVE_MODEL", "OPENSPEC_MODEL"):
        env_model = os.environ.get(env_var, "").strip()
        if env_model:
            return env_model
    return ""


def _persist_model(state: dict[str, Any], model_id: str) -> None:
    if model_id:
        state["model_id"] = model_id


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _elapsed_since(iso_ts: str) -> float:
    """Seconds elapsed since the given ISO timestamp."""
    try:
        start = datetime.fromisoformat(iso_ts.replace("Z", "+00:00"))
        return max(0.0, (datetime.now(timezone.utc) - start).total_seconds())
    except (TypeError, ValueError):
        return 0.0


def _regenerate_report(change: str) -> None:
    """Re-generate the metrics report after a hook fires."""
    try:
        from .report import generate_report
        generate_report(change)
    except Exception as exc:
        logger.warning("Report generation failed: %s", exc, exc_info=True)


def _state_path(change: str) -> Path:
    return CHANGES_DIR / change / STATE_FILE


def _load_state(change: str) -> dict[str, Any]:
    p = _state_path(change)
    if p.exists():
        return json.loads(p.read_text())
    return {}


def _save_state(change: str, state: dict[str, Any]) -> None:
    p = _state_path(change)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(state, indent=2) + "\n")


def _client(change: str | None = None):
    from .client import TelemetryClient
    return TelemetryClient(change=change)


def _read_verification(change: str, task_id: str) -> dict[str, Any]:
    """Read verification fields from multiple sources (best-effort).

    Sources checked in order:
    1. implementation/state.yaml → current_task_result (live, pre-clear)
    2. implementation/state.yaml → completed[] (post-clear fallback)
    3. implementation/task-reports/<task-id>.md → ## Verification table
    """
    out: dict[str, Any] = {}

    # Source 1 & 2: state.yaml
    import yaml as _yaml
    state_path = CHANGES_DIR / change / "implementation" / "state.yaml"
    if state_path.exists():
        try:
            data = _yaml.safe_load(state_path.read_text()) or {}
            result = data.get("current_task_result") or {}
            if result.get("task_id") != task_id:
                result = {}
                for completed in data.get("completed", []):
                    if completed.get("task_id") == task_id:
                        result = completed
                        break
            if result:
                if "verification_pass" in result:
                    out["verification_pass"] = bool(result["verification_pass"])
                if "test_command" in result:
                    out["verification_command"] = str(result["test_command"])
                if "test_result" in result:
                    out["verification_result"] = str(result["test_result"])
                    if "verification_pass" not in out:
                        out["verification_pass"] = result["test_result"].upper() in ("PASS", "PASSED")
                if "test_output_summary" in result:
                    out["verification_output"] = str(result["test_output_summary"])[:2000]
        except Exception:
            pass

    all_populated = (
        out.get("verification_pass") is not None
        and out.get("verification_command")
        and out.get("verification_result")
        and out.get("verification_output")
    )
    if all_populated:
        return out

    # Source 3: task-reports/<task-id>.md — fill in any gaps
    report_data = _read_verification_from_report(change, task_id)
    for key in ("verification_pass", "verification_command", "verification_result", "verification_output"):
        if not out.get(key) and report_data.get(key):
            out[key] = report_data[key]

    return out


def _read_verification_from_report(change: str, task_id: str) -> dict[str, Any]:
    """Parse verification results from a task report markdown file."""
    report_path = CHANGES_DIR / change / "implementation" / "task-reports" / f"{task_id}.md"
    if not report_path.exists():
        return {}
    try:
        content = report_path.read_text()
    except OSError:
        return {}

    import re
    out: dict[str, Any] = {}

    # Look for ## Verification section and parse the table
    verif_match = re.search(r'##\s+Verification\s*\n(.*?)(?=\n##|\Z)', content, re.DOTALL)
    if not verif_match:
        return {}

    table_text = verif_match.group(1)
    rows = re.findall(r'\|\s*(.+?)\s*\|\s*(PASSED|FAILED|PASS|FAIL)\s*\|', table_text, re.IGNORECASE)
    if rows:
        all_passed = all(r[1].upper() in ("PASSED", "PASS") for r in rows)
        any_failed = any(r[1].upper() in ("FAILED", "FAIL") for r in rows)
        out["verification_pass"] = all_passed and not any_failed

        checks = [f"{r[0].strip()}: {r[1].strip()}" for r in rows]
        out["verification_result"] = "PASS" if out["verification_pass"] else "FAIL"
        out["verification_output"] = "; ".join(checks)[:2000]

    # Try to find make/test commands in the content
    cmd_match = re.search(r'`((?:go\s+(?:test|build|vet)|make\s+\S+|bash\s+-n)[^`]*)`', content)
    if cmd_match:
        out["verification_command"] = cmd_match.group(1)[:512]

    return out


def _estimate_artifact(change: str, artifact_id: str) -> tuple[int, int]:
    from .tokens import estimate_artifact_tokens
    return estimate_artifact_tokens(CHANGES_DIR / change, artifact_id)


def _estimate_task(change: str, task_id: str) -> tuple[int, int]:
    from .tokens import estimate_task_tokens
    return estimate_task_tokens(CHANGES_DIR / change, task_id)


def _emit_phase_progress(
    change: str,
    state: dict[str, Any],
    phase_key: str,
    client,
    *,
    tokens_in: int = 0,
    tokens_out: int = 0,
    quality_score: float = 0,
    quality_label: str = "",
    iteration_count: int = 1,
    duration_s: float | None = None,
) -> None:
    """Emit a phase_progress event and update cumulative phase state."""
    phases = state.get("phases", {})
    phase_info = phases.get(phase_key)
    if not phase_info or phase_info.get("ended"):
        return

    cum_in = phase_info.get("tokens_in", 0) + tokens_in
    cum_out = phase_info.get("tokens_out", 0) + tokens_out
    phase_info["tokens_in"] = cum_in
    phase_info["tokens_out"] = cum_out

    client.update_phase(
        phase_info["id"],
        tokens_in=cum_in,
        tokens_out=cum_out,
        quality_score=quality_score,
        quality_label=quality_label,
        iteration_count=iteration_count,
        duration_s=duration_s,
    )
    _save_state(change, state)


def _out(data: dict[str, Any]) -> None:
    print(json.dumps(data))


def _is_batch_mode(state: dict[str, Any], phase_key: str) -> bool:
    """Check if a phase is running in batch mode."""
    phase_info = state.get("phases", {}).get(phase_key)
    return bool(phase_info and phase_info.get("batch_mode"))


def _set_batch_mode(state: dict[str, Any], phase_key: str) -> None:
    """Mark a phase as running in batch mode."""
    phase_info = state.get("phases", {}).get(phase_key)
    if phase_info:
        phase_info["batch_mode"] = True
        phase_info["batch_detected_at"] = datetime.now(timezone.utc).isoformat()


def _read_plan_phase(change: str) -> dict[str, int]:
    """Read current_plan_phase / total_plan_phases from implementation/state.yaml."""
    import yaml as _yaml
    state_path = CHANGES_DIR / change / "implementation" / "state.yaml"
    if not state_path.exists():
        return {}
    try:
        data = _yaml.safe_load(state_path.read_text()) or {}
        result: dict[str, int] = {}
        if "current_plan_phase" in data:
            result["current"] = int(data["current_plan_phase"])
        if "total_plan_phases" in data:
            result["total"] = int(data["total_plan_phases"])
        return result
    except Exception:
        return {}


def _toggle_phases(
    change: str,
    state: dict[str, Any],
    client,
    plan_phase: int,
    mode: str,
) -> None:
    """Toggle Phase 4 (subtask_creation) / Phase 5 (code_generation) statuses.

    Modes:
      task_gen_start  — Phase 4 running, Phase 5 passed
      task_gen_end    — Phase 4 passed
      impl_start      — Phase 5 running, Phase 4 stays passed
      impl_end        — Phase 5 passed
    """
    phases = state.setdefault("phases", {})
    p4 = phases.get("4")
    p5 = phases.get("5")

    if mode == "task_gen_start":
        if p4:
            p4["ended"] = False
            client.update_phase(
                p4["id"],
                status="running",
                quality_label=f"Plan Phase {plan_phase} task generation",
                tokens_in=p4.get("tokens_in", 0),
                tokens_out=p4.get("tokens_out", 0),
            )
        if p5 and not p5.get("ended"):
            p5["ended"] = True
            client.update_phase(
                p5["id"],
                status="passed",
                quality_label=p5.get("quality_label_last", ""),
                tokens_in=p5.get("tokens_in", 0),
                tokens_out=p5.get("tokens_out", 0),
            )
    elif mode == "task_gen_end":
        if p4:
            p4["ended"] = True
    elif mode == "impl_start":
        if p5:
            p5["ended"] = False
            client.update_phase(
                p5["id"],
                status="running",
                quality_label=f"Plan Phase {plan_phase} implementation",
                tokens_in=p5.get("tokens_in", 0),
                tokens_out=p5.get("tokens_out", 0),
            )
    elif mode == "impl_end":
        if p5:
            p5["ended"] = True
            p5["quality_label_last"] = f"Plan Phase {plan_phase} complete"
            client.update_phase(
                p5["id"],
                status="passed",
                quality_label=f"Plan Phase {plan_phase} complete",
                tokens_in=p5.get("tokens_in", 0),
                tokens_out=p5.get("tokens_out", 0),
            )

    pp = state.setdefault("plan_phase", {})
    pp["current"] = plan_phase
    _save_state(change, state)


def on_new(args: argparse.Namespace) -> None:
    """Called after a new change directory is created."""
    existing = _load_state(args.change)
    if existing.get("run_id"):
        _out({"ok": True, "run_id": existing["run_id"], "already_exists": True})
        return

    # Read jira metadata if available (enriched by MCP fetch in opsx-new)
    from .jira_metadata import read_jira_metadata
    change_dir = CHANGES_DIR / args.change
    jira_meta = read_jira_metadata(change_dir)
    model_id = _resolve_model(args, None)

    client = _client(args.change)
    try:
        change_label = f"{args.jira_key} — {args.change}"
        metadata: dict[str, Any] = dict(jira_meta) if jira_meta else {}
        if model_id:
            metadata["model_id"] = model_id
        run_id = client.create_run(
            change_name=change_label,
            jira_key=args.jira_key,
            branch=getattr(args, "branch", "") or f"feature/{args.change}",
            metadata=metadata if metadata else None,
        )
        state: dict[str, Any] = {
            "run_id": run_id,
            "jira_key": args.jira_key,
            "change": args.change,
            "phases": {},
            "tasks": {},
        }
        _persist_model(state, model_id)
        _save_state(args.change, state)
        _out({"ok": True, "run_id": run_id})
    finally:
        client.close()
    _regenerate_report(args.change)


def on_artifact_start(args: argparse.Namespace) -> None:
    """Called when an artifact creation begins."""
    state = _load_state(args.change)
    run_id = state.get("run_id")
    if not run_id:
        _out({"skip": True, "reason": "no run_id"})
        return

    mapping = ARTIFACT_PHASE_MAP.get(args.artifact)
    if not mapping:
        _out({"skip": True, "reason": f"unknown artifact: {args.artifact}"})
        return

    phase_number, phase_name, _ = mapping
    key = str(phase_number)
    phases = state.setdefault("phases", {})
    batch = getattr(args, "batch", False)
    plan_phase = getattr(args, "phase", None)

    if key in phases and not phases[key].get("ended"):
        if batch and not phases[key].get("batch_mode"):
            _set_batch_mode(state, key)
            _save_state(args.change, state)
        _out({"ok": True, "phase_id": phases[key]["id"], "already_running": True})
        return

    if key in phases and phases[key].get("ended"):
        client = _client(args.change)
        try:
            phases[key]["ended"] = False
            phases[key]["agent_started_at"] = _now_iso()
            if plan_phase is not None:
                _toggle_phases(args.change, state, client, plan_phase, "task_gen_start")
            else:
                client.update_phase(phases[key]["id"], status="running")
                _save_state(args.change, state)
            _out({"ok": True, "phase_id": phases[key]["id"], "reopened": True})
        finally:
            client.close()
        _regenerate_report(args.change)
        return

    client = _client(args.change)
    try:
        model_id = _resolve_model(args, state)
        _persist_model(state, model_id)
        phase_id = client.start_phase(run_id, phase_number, phase_name, model_id=model_id)
        phases[key] = {"id": phase_id, "name": phase_name, "ended": False, "agent_started_at": _now_iso()}
        if batch:
            _set_batch_mode(state, key)
        if plan_phase is not None and args.artifact == "tasks":
            _toggle_phases(args.change, state, client, plan_phase, "task_gen_start")
        else:
            _save_state(args.change, state)
        _out({"ok": True, "phase_id": phase_id})
    finally:
        client.close()
    _regenerate_report(args.change)


def on_artifact_created(args: argparse.Namespace) -> None:
    """Called when an artifact file is first written to disk (before eval/approval)."""
    state = _load_state(args.change)
    run_id = state.get("run_id")
    if not run_id:
        _out({"skip": True, "reason": "no run_id"})
        return

    mapping = ARTIFACT_PHASE_MAP.get(args.artifact)
    phase_key = str(mapping[0]) if mapping else None
    change_dir = CHANGES_DIR / args.change
    batch = getattr(args, "batch", False) or (phase_key and _is_batch_mode(state, phase_key))

    if batch and phase_key:
        _set_batch_mode(state, phase_key)

    tokens_in, tokens_out = _estimate_artifact(args.change, args.artifact)
    iteration_count = phase_iteration_count(change_dir, mapping[0]) if mapping else 1
    duration_s = phase_duration_s(change_dir, mapping[0]) if mapping else None

    client = _client(args.change)
    try:
        client.log_event(
            run_id=run_id,
            agent_id="Pipeline",
            event_type="state_machine",
            message=f"Artifact '{args.artifact}' created — awaiting eval gate",
        )
        if phase_key and not batch:
            _emit_phase_progress(
                args.change, state, phase_key, client,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                quality_label="artifact_created",
                iteration_count=iteration_count,
                duration_s=duration_s,
            )
        if batch:
            _save_state(args.change, state)
        _out({"ok": True, "tokens_in": tokens_in, "tokens_out": tokens_out, "batch_mode": bool(batch)})
    finally:
        client.close()
    _regenerate_report(args.change)


def on_waiting_approval(args: argparse.Namespace) -> None:
    """Called when an artifact is presented to the user for approval."""
    state = _load_state(args.change)
    run_id = state.get("run_id")
    if not run_id:
        _out({"skip": True, "reason": "no run_id"})
        return

    mapping = ARTIFACT_PHASE_MAP.get(args.artifact)
    phase_key = str(mapping[0]) if mapping else None
    change_dir = CHANGES_DIR / args.change

    iteration_count = phase_iteration_count(change_dir, mapping[0]) if mapping else 1
    duration_s = phase_duration_s(change_dir, mapping[0]) if mapping else None

    score_text = f" (eval score: {args.score}%)" if getattr(args, "score", 0) else ""
    client = _client(args.change)
    try:
        client.log_event(
            run_id=run_id,
            agent_id="Pipeline",
            event_type="state_machine",
            message=f"Artifact '{args.artifact}' ready for approval{score_text} — waiting for human decision",
        )
        if phase_key:
            _emit_phase_progress(
                args.change, state, phase_key, client,
                quality_score=getattr(args, "score", 0) or 0,
                quality_label="awaiting_approval",
                iteration_count=iteration_count,
                duration_s=duration_s,
            )
        _out({"ok": True})
    finally:
        client.close()
    _regenerate_report(args.change)


def on_artifact_complete(args: argparse.Namespace) -> None:
    """Called after an artifact is approved by the user."""
    state = _load_state(args.change)
    mapping = ARTIFACT_PHASE_MAP.get(args.artifact)
    if not mapping:
        _out({"skip": True, "reason": f"unknown artifact: {args.artifact}"})
        return

    phase_number, phase_name, is_last = mapping
    key = str(phase_number)
    phases = state.get("phases", {})
    phase_info = phases.get(key)

    if not phase_info:
        _out({"skip": True, "reason": f"phase {key} not started"})
        return

    plan_phase = getattr(args, "phase", None)
    run_id = state.get("run_id", "")
    change_dir = CHANGES_DIR / args.change
    batch = getattr(args, "batch", False) or _is_batch_mode(state, key)
    iteration_count = phase_iteration_count(change_dir, phase_number)
    duration_s = phase_duration_s(change_dir, phase_number)

    if batch:
        from .tokens import estimate_artifact_phase_tokens
        cum_in, cum_out = estimate_artifact_phase_tokens(change_dir, phase_number)
    else:
        tokens_in, tokens_out = _estimate_artifact(args.change, args.artifact)
        cum_in = phase_info.get("tokens_in", 0) + tokens_in
        cum_out = phase_info.get("tokens_out", 0) + tokens_out

    status_verb = "approved" if args.status == "passed" else "rejected"
    client = _client(args.change)
    try:
        client.log_event(
            run_id=run_id,
            agent_id="Pipeline",
            event_type="state_machine",
            message=f"Human {status_verb} artifact '{args.artifact}'",
        )
        client.log_event(
            run_id=run_id,
            agent_id="Pipeline",
            event_type="state_machine",
            message=f"Artifact '{args.artifact}' completed with status: {args.status}",
        )

        if is_last or args.status == "failed":
            if plan_phase is not None and args.artifact == "tasks" and args.status == "passed":
                _toggle_phases(args.change, state, client, plan_phase, "task_gen_end")
                _out({"ok": True, "phase_ended": False, "toggled": True, "plan_phase": plan_phase,
                      "tokens_in": cum_in, "tokens_out": cum_out, "batch_mode": batch})
            else:
                phase_proc = phase_info.get("processing_time_s", 0.0)
                if phase_info.get("agent_started_at"):
                    phase_proc += _elapsed_since(phase_info["agent_started_at"])
                client.end_phase(
                    phase_info["id"],
                    status="passed" if args.status == "passed" else "failed",
                    quality_score=getattr(args, "score", 0) or 0,
                    quality_label=getattr(args, "label", "") or "",
                    tokens_in=cum_in,
                    tokens_out=cum_out,
                    iteration_count=iteration_count,
                    duration_s=duration_s,
                    processing_time_s=round(phase_proc, 1),
                    batch_mode=batch,
                )
                phases[key]["ended"] = True
                phases[key]["processing_time_s"] = round(phase_proc, 1)
                _save_state(args.change, state)
                _out({"ok": True, "phase_ended": True, "tokens_in": cum_in, "tokens_out": cum_out, "batch_mode": batch})
        else:
            if not batch:
                phases[key]["tokens_in"] = cum_in
                phases[key]["tokens_out"] = cum_out

            from .change_metrics import PHASE_ARTIFACTS
            sibling_ids = PHASE_ARTIFACTS.get(phase_number, [])
            all_siblings_done = all(
                (change_dir / f"{aid}.md").exists() or (change_dir / f"{aid}.json").exists()
                for aid in sibling_ids
            )

            if all_siblings_done:
                phase_proc = phase_info.get("processing_time_s", 0.0)
                if phase_info.get("agent_started_at"):
                    phase_proc += _elapsed_since(phase_info["agent_started_at"])
                client.end_phase(
                    phase_info["id"],
                    status="passed",
                    quality_score=getattr(args, "score", 0) or 0,
                    quality_label=getattr(args, "label", "") or "",
                    tokens_in=cum_in,
                    tokens_out=cum_out,
                    iteration_count=iteration_count,
                    duration_s=duration_s,
                    processing_time_s=round(phase_proc, 1),
                    batch_mode=batch,
                )
                phases[key]["ended"] = True
                phases[key]["processing_time_s"] = round(phase_proc, 1)
                _save_state(args.change, state)
                _out({"ok": True, "phase_ended": True, "all_siblings_done": True,
                      "tokens_in": cum_in, "tokens_out": cum_out, "batch_mode": batch})
            else:
                if not batch:
                    client.update_phase(
                        phase_info["id"],
                        tokens_in=cum_in,
                        tokens_out=cum_out,
                        quality_score=getattr(args, "score", 0) or 0,
                        quality_label=getattr(args, "label", "") or "",
                        iteration_count=iteration_count,
                        duration_s=duration_s,
                    )
                _save_state(args.change, state)
                _out({"ok": True, "phase_ended": False, "tokens_in": cum_in, "tokens_out": cum_out, "batch_mode": batch})
    finally:
        client.close()
    _regenerate_report(args.change)


def on_apply_start(args: argparse.Namespace) -> None:
    """Called when the task loop begins (phase 5)."""
    state = _load_state(args.change)
    run_id = state.get("run_id")
    if not run_id:
        _out({"skip": True, "reason": "no run_id"})
        return

    batch = getattr(args, "batch", False)
    plan_phase = getattr(args, "phase", None)
    phases = state.setdefault("phases", {})

    if "5" in phases and phases["5"].get("ended"):
        if plan_phase is not None:
            client = _client(args.change)
            try:
                _toggle_phases(args.change, state, client, plan_phase, "impl_start")
                if batch:
                    _set_batch_mode(state, "5")
                    _save_state(args.change, state)
                _out({"ok": True, "phase_id": phases["5"]["id"], "reopened": True, "plan_phase": plan_phase})
            finally:
                client.close()
            _regenerate_report(args.change)
            return
        _out({"ok": True, "phase_id": phases["5"]["id"], "already_completed": True})
        return

    if "5" in phases and not phases["5"].get("ended"):
        if batch and not phases["5"].get("batch_mode"):
            _set_batch_mode(state, "5")
            _save_state(args.change, state)
        _out({"ok": True, "phase_id": phases["5"]["id"], "already_running": True})
        return

    client = _client(args.change)
    try:
        model_id = _resolve_model(args, state)
        _persist_model(state, model_id)
        phase_id = client.start_phase(run_id, 5, "code_generation", model_id=model_id)
        phases["5"] = {"id": phase_id, "name": "code_generation", "ended": False, "agent_started_at": _now_iso()}
        if batch:
            _set_batch_mode(state, "5")
        if plan_phase is not None:
            _toggle_phases(args.change, state, client, plan_phase, "impl_start")
        else:
            _save_state(args.change, state)
        _out({"ok": True, "phase_id": phase_id})
    finally:
        client.close()
    _regenerate_report(args.change)


def on_task_start(args: argparse.Namespace) -> None:
    """Called before each task execution."""
    state = _load_state(args.change)
    run_id = state.get("run_id")
    if not run_id:
        _out({"skip": True, "reason": "no run_id"})
        return

    phase_info = state.get("phases", {}).get("5")
    phase_id = phase_info["id"] if phase_info else ""

    client = _client(args.change)
    try:
        task_pk = client.start_task(
            run_id=run_id,
            phase_id=phase_id,
            task_id=args.task_id,
            task_title=getattr(args, "title", "") or "",
            agent_id=getattr(args, "agent", "") or "",
        )
        tasks = state.setdefault("tasks", {})
        tasks[args.task_id] = task_pk
        task_times = state.setdefault("task_times", {})
        task_times[args.task_id] = _now_iso()
        _save_state(args.change, state)
        _out({"ok": True, "task_pk": task_pk})
    finally:
        client.close()
    _regenerate_report(args.change)


def on_task_complete(args: argparse.Namespace) -> None:
    """Called after a task is approved."""
    state = _load_state(args.change)
    tasks = state.get("tasks", {})
    task_pk = tasks.get(args.task_id)

    if not task_pk:
        _out({"skip": True, "reason": f"task {args.task_id} not tracked"})
        return

    batch = getattr(args, "batch", False) or _is_batch_mode(state, "5")
    if batch:
        _set_batch_mode(state, "5")

    loops = read_task_refinement_rounds(CHANGES_DIR / args.change, args.task_id)
    verif = _read_verification(args.change, args.task_id)

    task_times = state.get("task_times", {})
    task_start_ts = task_times.get(args.task_id)
    task_proc = round(_elapsed_since(task_start_ts), 1) if task_start_ts else None

    phase_info_5 = state.get("phases", {}).get("5")
    if task_proc and phase_info_5:
        phase_info_5["processing_time_s"] = phase_info_5.get("processing_time_s", 0.0) + task_proc

    client = _client(args.change)
    try:
        if batch:
            client.end_task(
                task_pk,
                status=args.status,
                tokens_in=0,
                tokens_out=0,
                cost_usd=0,
                self_correction_loops=loops,
                processing_time_s=task_proc,
                attribution="phase_aggregate",
                **verif,
            )
            run_id = state.get("run_id", "")
            client.log_event(
                run_id=run_id,
                agent_id="Pipeline",
                event_type="state_machine",
                message=f"Task {args.task_id} completed (batch mode — tokens attributed at phase level)",
            )
            _save_state(args.change, state)
            _out({"ok": True, "task_pk": task_pk, "tokens_in": 0, "tokens_out": 0, "batch_mode": True})
        else:
            tokens_in, tokens_out = _estimate_task(args.change, args.task_id)
            client.end_task(
                task_pk,
                status=args.status,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                cost_usd=0,
                self_correction_loops=loops,
                processing_time_s=task_proc,
                **verif,
            )
            phase_info = state.get("phases", {}).get("5")
            if phase_info and not phase_info.get("ended"):
                _emit_phase_progress(
                    args.change, state, "5", client,
                    tokens_in=tokens_in,
                    tokens_out=tokens_out,
                    quality_label=f"task_{args.task_id}_{args.status}",
                )
            _out({"ok": True, "task_pk": task_pk, "tokens_in": tokens_in, "tokens_out": tokens_out})
    finally:
        client.close()
    _regenerate_report(args.change)


def _detect_batch_from_tasks(change: str, state: dict[str, Any]) -> bool:
    """Auto-detect batch mode when --batch was not passed explicitly.

    If 2+ tasks were completed and all have near-identical per-task estimates
    (within 5%), the tokens were almost certainly from a shared session.
    """
    task_ids = list(state.get("tasks", {}).keys())
    if len(task_ids) < 2:
        return False
    estimates = [_estimate_task(change, tid)[0] for tid in task_ids]
    if not estimates or estimates[0] == 0:
        return False
    ref = estimates[0]
    return all(abs(e - ref) / ref <= 0.05 for e in estimates[1:])


def on_phase_complete(args: argparse.Namespace) -> None:
    """Called when all tasks for a plan phase N are done (phase_iterative mode)."""
    state = _load_state(args.change)
    phases = state.get("phases", {})
    phase_info = phases.get("5")

    if not phase_info:
        _out({"skip": True, "reason": "phase 5 not tracked"})
        return

    plan_phase = getattr(args, "phase", None)
    if plan_phase is None:
        pp = _read_plan_phase(args.change)
        plan_phase = pp.get("current", 1)

    client = _client(args.change)
    try:
        _toggle_phases(args.change, state, client, plan_phase, "impl_end")
        _out({"ok": True, "plan_phase": plan_phase, "phase_5_passed": True})
    finally:
        client.close()
    _regenerate_report(args.change)


def on_apply_complete(args: argparse.Namespace) -> None:
    """Called after all tasks are approved (phase 5 done)."""
    state = _load_state(args.change)
    phases = state.get("phases", {})
    phase_info = phases.get("5")

    if not phase_info:
        _out({"skip": True, "reason": "phase 5 not tracked"})
        return

    plan_phase_arg = getattr(args, "phase", None)
    pp_info = _read_plan_phase(args.change)
    is_iterative = pp_info.get("total", 0) > 0
    is_final_phase = (pp_info.get("current", 0) >= pp_info.get("total", 0)) if is_iterative else True

    if is_iterative and not is_final_phase:
        plan_phase = plan_phase_arg or pp_info.get("current", 1)
        client = _client(args.change)
        try:
            _toggle_phases(args.change, state, client, plan_phase, "impl_end")
            _out({"ok": True, "plan_phase": plan_phase, "iterative_continue": True})
        finally:
            client.close()
        _regenerate_report(args.change)
        return

    change_dir = CHANGES_DIR / args.change
    batch = _is_batch_mode(state, "5")

    if not batch and _detect_batch_from_tasks(args.change, state):
        batch = True
        _set_batch_mode(state, "5")

    if batch:
        from .tokens import estimate_phase5_tokens
        total_tokens_in, total_tokens_out = estimate_phase5_tokens(change_dir)
    else:
        total_tokens_in = phase_info.get("tokens_in", 0)
        total_tokens_out = phase_info.get("tokens_out", 0)
        if total_tokens_in == 0 and total_tokens_out == 0:
            for task_id in state.get("tasks", {}):
                ti, to = _estimate_task(args.change, task_id)
                total_tokens_in += ti
                total_tokens_out += to

    run_id = state.get("run_id", "")
    iteration_count = phase5_iteration_count(change_dir)
    should_close, label = phase5_should_close(change_dir)
    quality_label = getattr(args, "label", "") or (label if should_close else "all tasks approved")
    if batch and "batch" not in quality_label:
        quality_label = f"batch: {quality_label}"

    client = _client(args.change)
    try:
        if batch:
            client.log_event(
                run_id=run_id,
                agent_id="Pipeline",
                event_type="state_machine",
                message="Phase 5 completing in batch mode — tokens estimated at phase level",
            )
        client.end_phase(
            phase_info["id"],
            status="passed",
            quality_label=quality_label,
            tokens_in=total_tokens_in,
            tokens_out=total_tokens_out,
            iteration_count=iteration_count,
            batch_mode=batch,
        )
        phases["5"]["ended"] = True

        client.end_run(run_id, status="completed")
        _save_state(args.change, state)
        _out({"ok": True, "tokens_in": total_tokens_in, "tokens_out": total_tokens_out, "batch_mode": batch})
    finally:
        client.close()
    _regenerate_report(args.change)


def sync(args: argparse.Namespace) -> None:
    """Sync filesystem state — re-scan artifacts and update phases."""
    state = _load_state(args.change)
    run_id = state.get("run_id")
    if not run_id:
        _out({"skip": True, "reason": "no run_id — run on-new first"})
        return

    change_dir = CHANGES_DIR / args.change
    updated = []

    for artifact_id, (phase_number, phase_name, is_last) in ARTIFACT_PHASE_MAP.items():
        artifact_path = change_dir / f"{artifact_id}.md"
        if not artifact_path.exists():
            artifact_path = change_dir / f"{artifact_id}.json"
        if not artifact_path.exists():
            continue

        key = str(phase_number)
        phases = state.setdefault("phases", {})
        if key in phases and phases[key].get("ended"):
            continue

        tokens_in, tokens_out = _estimate_artifact(args.change, artifact_id)

        client = _client(args.change)
        try:
            model_id = _resolve_model(args, state)
            _persist_model(state, model_id)
            if key not in phases:
                phase_id = client.start_phase(run_id, phase_number, phase_name, model_id=model_id)
                phases[key] = {"id": phase_id, "name": phase_name, "ended": False}

            if is_last:
                eval_path = change_dir / "eval-results" / f"{artifact_id}.yaml"
                score = 0
                if eval_path.exists():
                    import yaml
                    eval_data = yaml.safe_load(eval_path.read_text()) or {}
                    score = eval_data.get("overall_score", 0)

                iteration_count = phase_iteration_count(change_dir, phase_number)
                duration_s = phase_duration_s(change_dir, phase_number)

                client.end_phase(
                    phases[key]["id"],
                    status="passed",
                    quality_score=score,
                    tokens_in=tokens_in,
                    tokens_out=tokens_out,
                    iteration_count=iteration_count,
                    duration_s=duration_s,
                )
                phases[key]["ended"] = True
                updated.append(f"phase {key} ({phase_name})")
        finally:
            client.close()

    phases = state.setdefault("phases", {})
    if not phases.get("5", {}).get("ended"):
        should_close, label = phase5_should_close(change_dir)

        if should_close or (change_dir / "tasks.md").exists():
            if "5" not in phases:
                client = _client(args.change)
                try:
                    model_id = _resolve_model(args, state)
                    _persist_model(state, model_id)
                    phase_id = client.start_phase(run_id, 5, "code_generation", model_id=model_id)
                    phases["5"] = {"id": phase_id, "name": "code_generation", "ended": False}
                except Exception:
                    pass
                finally:
                    client.close()

            if should_close and "5" in phases and not phases["5"].get("ended"):
                from .tokens import estimate_phase5_tokens

                total_in, total_out = estimate_phase5_tokens(change_dir)
                iteration_count = phase5_iteration_count(change_dir)

                client = _client(args.change)
                try:
                    client.end_phase(
                        phases["5"]["id"],
                        status="passed",
                        quality_label=label,
                        tokens_in=total_in,
                        tokens_out=total_out,
                        iteration_count=iteration_count,
                    )
                    phases["5"]["ended"] = True
                    updated.append("phase 5 (code_generation)")

                    client.end_run(run_id, status="completed")
                    updated.append("run completed")
                except Exception:
                    pass
                finally:
                    client.close()

    _save_state(args.change, state)
    _out({"ok": True, "updated": updated})
    _regenerate_report(args.change)


def report_cmd(args: argparse.Namespace) -> None:
    """On-demand report regeneration."""
    from .report import generate_report
    path = generate_report(args.change)
    _out({"ok": True, "path": str(path)})


def _add_model_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--model",
        default="",
        help="AI model identifier (e.g. claude-opus-4.6, composer-2.5-fast)",
    )


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="openspec-telemetry",
        description="Automatic telemetry hooks for OpenSpec pipeline",
    )
    sub = p.add_subparsers(dest="command", required=True)

    r = sub.add_parser("on-new", help="Register a new pipeline run")
    r.add_argument("--change", required=True)
    r.add_argument("--jira-key", required=True)
    r.add_argument("--branch", default="")
    _add_model_arg(r)

    sa = sub.add_parser("on-artifact-start", help="Signal artifact creation started")
    sa.add_argument("--change", required=True)
    sa.add_argument("--artifact", required=True)
    sa.add_argument("--phase", type=int, default=None, help="Plan phase number (phase_iterative mode)")
    sa.add_argument("--batch", action="store_true", help="Batch mode — skip per-artifact token attribution")
    _add_model_arg(sa)

    acr = sub.add_parser("on-artifact-created", help="Signal artifact file written to disk")
    acr.add_argument("--change", required=True)
    acr.add_argument("--artifact", required=True)
    acr.add_argument("--phase", type=int, default=None, help="Plan phase number (phase_iterative mode)")
    acr.add_argument("--batch", action="store_true", help="Batch mode — skip token-bearing phase_progress")

    wa = sub.add_parser("on-waiting-approval", help="Signal artifact presented for user approval")
    wa.add_argument("--change", required=True)
    wa.add_argument("--artifact", required=True)
    wa.add_argument("--phase", type=int, default=None, help="Plan phase number (phase_iterative mode)")
    wa.add_argument("--score", type=float, default=0)

    ac = sub.add_parser("on-artifact-complete", help="Signal artifact approved/rejected")
    ac.add_argument("--change", required=True)
    ac.add_argument("--artifact", required=True)
    ac.add_argument("--status", required=True, choices=["passed", "failed"])
    ac.add_argument("--phase", type=int, default=None, help="Plan phase number (phase_iterative mode)")
    ac.add_argument("--score", type=float, default=0)
    ac.add_argument("--label", default="")
    ac.add_argument("--iterations", type=int, default=1)
    ac.add_argument("--batch", action="store_true", help="Batch mode — use phase-level token estimate")

    ap = sub.add_parser("on-apply-start", help="Signal task loop started")
    ap.add_argument("--change", required=True)
    ap.add_argument("--phase", type=int, default=None, help="Plan phase number (phase_iterative mode)")
    ap.add_argument("--batch", action="store_true", help="Batch mode — skip per-task token attribution")
    _add_model_arg(ap)

    ts = sub.add_parser("on-task-start", help="Signal task execution started")
    ts.add_argument("--change", required=True)
    ts.add_argument("--task-id", required=True)
    ts.add_argument("--phase", type=int, default=None, help="Plan phase number (phase_iterative mode)")
    ts.add_argument("--title", default="")
    ts.add_argument("--agent", default="")

    tc = sub.add_parser("on-task-complete", help="Signal task approved/failed")
    tc.add_argument("--change", required=True)
    tc.add_argument("--task-id", required=True)
    tc.add_argument("--status", required=True, choices=["passed", "failed"])
    tc.add_argument("--phase", type=int, default=None, help="Plan phase number (phase_iterative mode)")
    tc.add_argument("--loops", type=int, default=0)
    tc.add_argument("--batch", action="store_true", help="Batch mode — zero-token task end, phase-level attribution")

    pc = sub.add_parser("on-phase-complete", help="Signal plan phase N tasks done (phase_iterative)")
    pc.add_argument("--change", required=True)
    pc.add_argument("--phase", type=int, default=None, help="Plan phase number just completed")
    pc.add_argument("--pr-raised", default="false", help="Whether a PR was raised for this phase")

    apc = sub.add_parser("on-apply-complete", help="Signal all tasks done, end phase 5 + run")
    apc.add_argument("--change", required=True)
    apc.add_argument("--phase", type=int, default=None, help="Plan phase number (phase_iterative mode)")
    apc.add_argument("--label", default="")

    sy = sub.add_parser("sync", help="Sync filesystem state to telemetry")
    sy.add_argument("--change", required=True)
    _add_model_arg(sy)

    rp = sub.add_parser("report", help="Regenerate metrics-report.json")
    rp.add_argument("--change", required=True)

    return p


_DISPATCH = {
    "on-new": on_new,
    "on-artifact-start": on_artifact_start,
    "on-artifact-created": on_artifact_created,
    "on-waiting-approval": on_waiting_approval,
    "on-artifact-complete": on_artifact_complete,
    "on-apply-start": on_apply_start,
    "on-task-start": on_task_start,
    "on-task-complete": on_task_complete,
    "on-phase-complete": on_phase_complete,
    "on-apply-complete": on_apply_complete,
    "sync": sync,
    "report": report_cmd,
}


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    handler = _DISPATCH.get(args.command)
    if not handler:
        parser.print_help()
        sys.exit(1)
    try:
        handler(args)
    except Exception as exc:
        print(
            json.dumps({"warning": f"Auto-telemetry unavailable: {exc}"}),
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
