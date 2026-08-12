"""Jira metadata reader for metrics-report.json enrichment.

Loads epic/ticket metadata from inputs/jira.yaml and constructs
browse URLs using the Jira base URL found in the data itself.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

JIRA_BASE_URL = "https://issues.redhat.com/browse"


def _build_url(key: str, base_url: str = "") -> str:
    """Construct a Jira browse URL from a ticket key."""
    if not key:
        return ""
    base = base_url.rstrip("/") if base_url else JIRA_BASE_URL
    return f"{base}/{key}"


def _infer_base_url(data: dict[str, Any]) -> str:
    """Try to infer the Jira base browse URL from explicit URLs in the data."""
    for url_key in ("jira_url", "epic_url"):
        url = data.get(url_key, "")
        if url and "/browse/" in url:
            return url.rsplit("/browse/", 1)[0] + "/browse"
    return JIRA_BASE_URL


def _load_jira_yaml(change_dir: Path) -> dict[str, Any]:
    """Load and parse inputs/jira.yaml, returning raw data dict."""
    jira_path = change_dir / "inputs" / "jira.yaml"
    if not jira_path.exists():
        return {}
    try:
        import yaml
        data = yaml.safe_load(jira_path.read_text()) or {}
        return data if isinstance(data, dict) else {}
    except Exception as exc:
        logger.debug("Failed to read jira metadata: %s", exc)
        return {}


def read_jira_metadata(change_dir: Path) -> dict[str, Any]:
    """Load inputs/jira.yaml and normalize into a metadata dict.

    Constructs URLs from keys when explicit URLs are absent.
    Returns an empty dict if the file doesn't exist or can't be parsed.
    """
    data = _load_jira_yaml(change_dir)
    if not data:
        return {}

    jira_key = data.get("jira_key", "")
    epic_key = data.get("epic_key", "")
    base_url = _infer_base_url(data)

    return {
        "jira_key": jira_key,
        "jira_summary": data.get("jira_summary", ""),
        "jira_url": data.get("jira_url") or _build_url(jira_key, base_url),
        "epic_key": epic_key,
        "epic_name": data.get("epic_name", ""),
        "epic_url": data.get("epic_url") or _build_url(epic_key, base_url),
    }


def read_jira_report_fields(change_dir: Path) -> dict[str, str]:
    """Return top-level Jira fields for the metrics report.

    Output keys match the report schema::

        jira_epic_link, jira_epic_name, jira_task_name, Jira_task_link
    """
    meta = read_jira_metadata(change_dir)
    if not meta:
        return {}
    return {
        "jira_epic_link": meta.get("epic_url", ""),
        "jira_epic_name": meta.get("epic_name", ""),
        "jira_task_name": meta.get("jira_summary", ""),
        "Jira_task_link": meta.get("jira_url", ""),
    }


def enrich_run_metadata(run: dict[str, Any], change_dir: Path) -> dict[str, Any]:
    """Merge Jira metadata into the run dict (non-destructive).

    Only adds ``jira_key`` — other Jira fields live at the report top level.
    Returns the mutated run dict for convenience.
    """
    meta = read_jira_metadata(change_dir)
    if not meta:
        return run

    if meta.get("jira_key") and not run.get("jira_key"):
        run["jira_key"] = meta["jira_key"]

    return run
