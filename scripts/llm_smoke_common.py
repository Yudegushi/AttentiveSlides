"""Shared utilities for recorded LLM smoke tests."""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _git_value(*args: str) -> str | None:
    try:
        return subprocess.check_output(
            ["git", *args],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def base_record(stage: str) -> dict[str, Any]:
    return {
        "stage": stage,
        "timestamp_utc": datetime.now(
            timezone.utc
        ).isoformat(),
        "git_commit": _git_value("rev-parse", "HEAD"),
        "git_branch": _git_value(
            "branch",
            "--show-current",
        ),
    }


def write_record(
    output_path: str | Path,
    payload: dict[str, Any],
) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    path.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(json.dumps(
        {
            "output": str(path),
            "passed": payload.get("passed"),
            "stage": payload.get("stage"),
        },
        ensure_ascii=False,
        indent=2,
    ))
