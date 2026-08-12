"""Token estimation for OpenSpec artifacts using tiktoken.

Provides approximate token counts for input context and output artifacts.
Uses cl100k_base encoding (GPT-4/Claude-class) which gives ~5-10% accuracy
for most modern LLMs regardless of provider.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Sequence

logger = logging.getLogger(__name__)

_encoder = None


def _get_encoder():
    global _encoder
    if _encoder is None:
        try:
            import tiktoken
            _encoder = tiktoken.get_encoding("cl100k_base")
        except Exception as exc:
            logger.debug("tiktoken unavailable, falling back to char-based estimation: %s", exc)
    return _encoder


def count_tokens(text: str) -> int:
    """Count tokens in text. Uses tiktoken if available, otherwise char/4."""
    enc = _get_encoder()
    if enc is not None:
        return len(enc.encode(text))
    return max(1, len(text) // 4)


def estimate_file_tokens(path: Path) -> int:
    """Estimate token count for a single file."""
    try:
        if path.exists() and path.is_file():
            return count_tokens(path.read_text(errors="replace"))
    except Exception as exc:
        logger.debug("Could not read %s for token estimation: %s", path, exc)
    return 0


def estimate_tokens_for_files(paths: Sequence[Path]) -> int:
    """Sum token estimates across multiple files."""
    return sum(estimate_file_tokens(p) for p in paths)


def estimate_artifact_tokens(change_dir: Path, artifact_id: str) -> tuple[int, int]:
    """Estimate input and output tokens for an artifact creation.

    Input = dependency artifacts + inputs that the agent reads as context.
    Output = the artifact file that was generated.

    Returns (tokens_in, tokens_out).
    """
    input_files: list[Path] = []
    output_files: list[Path] = []

    inputs_dir = change_dir / "inputs"
    if inputs_dir.exists():
        for f in inputs_dir.iterdir():
            if f.is_file() and f.suffix in (".yaml", ".yml", ".md", ".txt", ".json"):
                input_files.append(f)

    dependency_map = {
        "bug-report": ["bug-validation.json"],
        "repro-verification": ["bug-report.md"],
        "rca": ["bug-report.md", "repro-verification-report.md"],
        "bugfix-plan": ["bug-report.md", "rca-report.md", "constitution.md"],
        "tasks": ["bug-report.md", "rca-report.md", "bugfix-plan.md", "constitution.md"],
    }

    for dep_name in dependency_map.get(artifact_id, []):
        dep_path = change_dir / dep_name
        if dep_path.exists():
            input_files.append(dep_path)

    # Generated filename doesn't always match artifact_id (e.g. "rca" → rca-report.md)
    output_filename_map = {
        "bug-validation": "bug-validation.json",
        "bug-report": "bug-report.md",
        "repro-verification": "repro-verification-report.md",
        "rca": "rca-report.md",
        "bugfix-plan": "bugfix-plan.md",
        "tasks": "tasks.md",
    }
    output_path = change_dir / output_filename_map.get(artifact_id, f"{artifact_id}.md")
    if not output_path.exists():
        output_path = change_dir / f"{artifact_id}.json"
    if output_path.exists():
        output_files.append(output_path)

    tokens_in = estimate_tokens_for_files(input_files)
    tokens_out = estimate_tokens_for_files(output_files)

    return tokens_in, tokens_out


def estimate_task_tokens(change_dir: Path, task_id: str, fork_dir: Path | None = None) -> tuple[int, int]:
    """Estimate input/output tokens for a code generation task (direct mode).

    Input = context artifacts read directly (no design bundle).
    Output = task report (as proxy for generated code volume).
    """
    input_files: list[Path] = []
    output_files: list[Path] = []

    for ctx_file in [
        "bug-report.md",
        "rca-report.md",
        "bugfix-plan.md",
        "constitution.md",
        "tasks.md",
        "repro-verification-report.md",
    ]:
        p = change_dir / ctx_file
        if p.exists():
            input_files.append(p)

    task_report = change_dir / "implementation" / "task-reports" / f"{task_id}.md"
    if task_report.exists():
        output_files.append(task_report)

    tokens_in = estimate_tokens_for_files(input_files)
    tokens_out = estimate_tokens_for_files(output_files)

    if tokens_out == 0:
        tokens_out = max(500, tokens_in // 10)

    return tokens_in, tokens_out


def estimate_phase5_tokens(change_dir: Path) -> tuple[int, int]:
    """Batch-safe token estimate for the entire implementation phase (direct mode).

    Counts shared context exactly once as input, and sums all task reports as
    output. Use this instead of summing per-task estimates when multiple tasks
    were completed in a single session.
    """
    input_files: list[Path] = []
    output_files: list[Path] = []

    for ctx_file in [
        "bug-report.md",
        "rca-report.md",
        "bugfix-plan.md",
        "constitution.md",
        "tasks.md",
        "repro-verification-report.md",
    ]:
        p = change_dir / ctx_file
        if p.exists():
            input_files.append(p)

    inputs_dir = change_dir / "inputs"
    if inputs_dir.exists():
        for f in inputs_dir.iterdir():
            if f.is_file() and f.suffix in (".yaml", ".yml", ".md", ".txt", ".json"):
                input_files.append(f)

    reports_dir = change_dir / "implementation" / "task-reports"
    if reports_dir.exists():
        for f in reports_dir.glob("*.md"):
            output_files.append(f)

    tokens_in = estimate_tokens_for_files(input_files)
    tokens_out = estimate_tokens_for_files(output_files)

    if tokens_out == 0:
        tokens_out = max(500, tokens_in // 10)

    return tokens_in, tokens_out


def estimate_artifact_phase_tokens(change_dir: Path, phase_number: int) -> tuple[int, int]:
    """Batch-safe token estimate for an artifact phase (phases 1-4).

    Like ``estimate_phase5_tokens`` but for artifact phases: counts shared
    inputs once and sums all artifact outputs in the phase.
    """
    from .change_metrics import PHASE_ARTIFACTS

    artifact_ids = PHASE_ARTIFACTS.get(phase_number, [])
    if not artifact_ids:
        return 0, 0

    input_files: list[Path] = []
    output_files: list[Path] = []

    inputs_dir = change_dir / "inputs"
    if inputs_dir.exists():
        for f in inputs_dir.iterdir():
            if f.is_file() and f.suffix in (".yaml", ".yml", ".md", ".txt", ".json"):
                input_files.append(f)

    dependency_map = {
        "specs": ["validation.json"],
        "repo-assessment": ["specs.md"],
        "constitution": ["specs.md", "repo-assessment.md"],
        "plan": ["specs.md", "repo-assessment.md", "constitution.md"],
        "tasks": ["specs.md", "plan.md", "constitution.md"],
    }
    seen_deps: set[str] = set()
    for artifact_id in artifact_ids:
        for dep_name in dependency_map.get(artifact_id, []):
            if dep_name not in seen_deps:
                dep_path = change_dir / dep_name
                if dep_path.exists():
                    input_files.append(dep_path)
                seen_deps.add(dep_name)

        for ext in (".md", ".json"):
            out_path = change_dir / f"{artifact_id}{ext}"
            if out_path.exists():
                output_files.append(out_path)
                break

    tokens_in = estimate_tokens_for_files(input_files)
    tokens_out = estimate_tokens_for_files(output_files)

    return tokens_in, tokens_out
