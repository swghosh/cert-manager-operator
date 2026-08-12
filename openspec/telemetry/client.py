"""Disk-only telemetry client for the OpenSpec pipeline.

Writes NDJSON events to ``openspec/changes/<change>/telemetry/events.jsonl``.
No HTTP, no database, no server dependency.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

CHANGES_DIR = Path("openspec/changes")


class TelemetryClient:
    """Writes NDJSON telemetry events to disk.

    Each event is appended to ``openspec/changes/<change>/telemetry/events.jsonl``.
    Works in any sandbox (Cursor, CI, containers) with no network required.
    """

    def __init__(self, change: str | None = None) -> None:
        self._change = change

    def _write_event(self, event: dict[str, Any]) -> None:
        change = event.get("change") or self._change
        if not change:
            return
        telemetry_dir = CHANGES_DIR / change / "telemetry"
        try:
            telemetry_dir.mkdir(parents=True, exist_ok=True)
            event_line = json.dumps(event, default=str) + "\n"
            with open(telemetry_dir / "events.jsonl", "a") as f:
                f.write(event_line)
        except OSError as exc:
            logger.debug("Failed to write telemetry event to disk: %s", exc)

    def create_run(self, change_name: str, jira_key: str, branch: str = "", metadata: dict[str, Any] | None = None) -> str:
        local_id = str(uuid.uuid4())
        event: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "type": "run_create",
            "change": self._change or "",
            "id": local_id,
            "change_name": change_name,
            "jira_key": jira_key,
            "branch": branch,
        }
        if metadata:
            event["metadata"] = metadata
        self._write_event(event)
        return local_id

    def end_run(self, run_id: str, status: str = "completed") -> None:
        self._write_event({
            "ts": datetime.now(timezone.utc).isoformat(),
            "type": "run_end",
            "change": self._change or "",
            "run_id": run_id,
            "status": status,
        })

    def start_phase(
        self,
        run_id: str,
        phase_number: int,
        phase_name: str,
        model_id: str = "",
    ) -> str:
        local_id = str(uuid.uuid4())
        self._write_event({
            "ts": datetime.now(timezone.utc).isoformat(),
            "type": "phase_start",
            "change": self._change or "",
            "id": local_id,
            "run_id": run_id,
            "phase_number": phase_number,
            "phase_name": phase_name,
            "model_id": model_id,
        })
        return local_id

    def end_phase(
        self,
        phase_id: str,
        status: str = "passed",
        *,
        tokens_in: int = 0,
        tokens_out: int = 0,
        quality_score: float = 0,
        quality_label: str = "",
        duration_s: float | None = None,
        processing_time_s: float | None = None,
        iteration_count: int = 1,
        batch_mode: bool = False,
    ) -> None:
        event: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "type": "phase_end",
            "change": self._change or "",
            "phase_id": phase_id,
            "status": status,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "quality_score": quality_score,
            "quality_label": quality_label,
            "iteration_count": iteration_count,
        }
        if duration_s is not None:
            event["duration_s"] = duration_s
        if processing_time_s is not None:
            event["processing_time_s"] = processing_time_s
        if batch_mode:
            event["batch_mode"] = True
        self._write_event(event)

    def update_phase(
        self,
        phase_id: str,
        *,
        status: str | None = None,
        tokens_in: int = 0,
        tokens_out: int = 0,
        quality_score: float = 0,
        quality_label: str = "",
        iteration_count: int = 1,
        duration_s: float | None = None,
    ) -> None:
        event: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "type": "phase_progress",
            "change": self._change or "",
            "phase_id": phase_id,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "quality_score": quality_score,
            "quality_label": quality_label,
            "iteration_count": iteration_count,
        }
        if status is not None:
            event["status"] = status
        if duration_s is not None:
            event["duration_s"] = duration_s
        self._write_event(event)

    def start_task(
        self,
        run_id: str,
        phase_id: str,
        task_id: str,
        task_title: str = "",
        agent_id: str = "",
    ) -> str:
        local_id = str(uuid.uuid4())
        self._write_event({
            "ts": datetime.now(timezone.utc).isoformat(),
            "type": "task_start",
            "change": self._change or "",
            "id": local_id,
            "run_id": run_id,
            "phase_id": phase_id,
            "task_id": task_id,
            "task_title": task_title,
            "agent_id": agent_id,
        })
        return local_id

    def end_task(
        self,
        task_pk: str,
        status: str = "passed",
        *,
        tokens_in: int = 0,
        tokens_out: int = 0,
        cost_usd: float = 0,
        self_correction_loops: int = 0,
        processing_time_s: float | None = None,
        verification_pass: bool | None = None,
        verification_command: str = "",
        verification_result: str = "",
        verification_output: str = "",
        attribution: str | None = None,
    ) -> None:
        event: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "type": "task_end",
            "change": self._change or "",
            "task_pk": task_pk,
            "status": status,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "cost_usd": cost_usd,
            "self_correction_loops": self_correction_loops,
        }
        if processing_time_s is not None:
            event["processing_time_s"] = processing_time_s
        if verification_pass is not None:
            event["verification_pass"] = verification_pass
        if verification_command:
            event["verification_command"] = verification_command
        if verification_result:
            event["verification_result"] = verification_result
        if verification_output:
            event["verification_output"] = verification_output
        if attribution:
            event["attribution"] = attribution
        self._write_event(event)

    def log_event(
        self,
        run_id: str,
        agent_id: str,
        event_type: str,
        message: str,
        *,
        task_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        local_id = str(uuid.uuid4())
        self._write_event({
            "ts": datetime.now(timezone.utc).isoformat(),
            "type": "log_event",
            "change": self._change or "",
            "id": local_id,
            "run_id": run_id,
            "task_id": task_id,
            "agent_id": agent_id,
            "event_type": event_type,
            "message": message,
            "metadata_json": metadata,
        })
        return local_id

    def close(self) -> None:
        pass
