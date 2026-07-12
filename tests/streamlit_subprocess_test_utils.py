"""Run Streamlit AppTest in an isolated Python process.

Streamlit AppTest can trigger native-level crashes when multiple apps
are executed sequentially inside the same unittest process. Running
each AppTest in its own subprocess prevents one app test from
terminating the complete regression suite.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Iterable


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def run_isolated_apptest(
    *,
    app_path: str,
    expected_title: str,
    required_subheaders: Iterable[str] = (),
    required_buttons: Iterable[str] = (),
    forbidden_buttons: Iterable[str] = (),
    required_selectboxes: Iterable[str] = (),
    required_radios: Iterable[str] = (),
    required_text_areas: Iterable[str] = (),
    timeout_seconds: int = 75,
) -> subprocess.CompletedProcess[str]:
    """Execute one Streamlit AppTest in a fresh interpreter."""
    configuration = {
        "app_path": app_path,
        "expected_title": expected_title,
        "required_subheaders": list(required_subheaders),
        "required_buttons": list(required_buttons),
        "forbidden_buttons": list(forbidden_buttons),
        "required_selectboxes": list(required_selectboxes),
        "required_radios": list(required_radios),
        "required_text_areas": list(required_text_areas),
        "run_timeout": 30,
    }

    child_code = r'''
import json
import sys

from streamlit.testing.v1 import AppTest


configuration = json.loads(sys.stdin.read())

app = AppTest.from_file(
    configuration["app_path"]
)

app.run(
    timeout=configuration["run_timeout"]
)

exceptions = [
    getattr(exception, "message", str(exception))
    for exception in app.exception
]

if exceptions:
    raise AssertionError(
        f"Streamlit exceptions: {exceptions}"
    )

titles = {
    item.value
    for item in app.title
}

if configuration["expected_title"] not in titles:
    raise AssertionError(
        "Expected title was not rendered. "
        f"Expected={configuration['expected_title']!r}, "
        f"actual={sorted(titles)!r}"
    )

subheaders = {
    item.value
    for item in app.subheader
}

missing_subheaders = (
    set(configuration["required_subheaders"])
    - subheaders
)

if missing_subheaders:
    raise AssertionError(
        "Missing subheaders: "
        f"{sorted(missing_subheaders)!r}"
    )

buttons = {
    item.label
    for item in app.button
}

missing_buttons = (
    set(configuration["required_buttons"])
    - buttons
)

if missing_buttons:
    raise AssertionError(
        "Missing buttons: "
        f"{sorted(missing_buttons)!r}"
    )

unexpected_buttons = (
    set(configuration["forbidden_buttons"])
    & buttons
)

if unexpected_buttons:
    raise AssertionError(
        "Unexpected buttons: "
        f"{sorted(unexpected_buttons)!r}"
    )

selectboxes = {
    item.label
    for item in app.selectbox
}

missing_selectboxes = (
    set(configuration["required_selectboxes"])
    - selectboxes
)

if missing_selectboxes:
    raise AssertionError(
        "Missing selectboxes: "
        f"{sorted(missing_selectboxes)!r}"
    )

radios = {
    item.label
    for item in app.radio
}

missing_radios = (
    set(configuration["required_radios"])
    - radios
)

if missing_radios:
    raise AssertionError(
        "Missing radios: "
        f"{sorted(missing_radios)!r}"
    )

text_areas = {
    item.label
    for item in app.text_area
}

missing_text_areas = (
    set(configuration["required_text_areas"])
    - text_areas
)

if missing_text_areas:
    raise AssertionError(
        "Missing text areas: "
        f"{sorted(missing_text_areas)!r}"
    )

print("ISOLATED_APPTEST_PASS")
'''

    environment = os.environ.copy()

    existing_pythonpath = environment.get(
        "PYTHONPATH",
        "",
    )

    environment["PYTHONPATH"] = os.pathsep.join(
        part
        for part in [
            str(REPOSITORY_ROOT),
            existing_pythonpath,
        ]
        if part
    )

    environment[
        "STREAMLIT_BROWSER_GATHER_USAGE_STATS"
    ] = "false"

    return subprocess.run(
        [
            sys.executable,
            "-c",
            child_code,
        ],
        input=json.dumps(configuration),
        text=True,
        capture_output=True,
        cwd=REPOSITORY_ROOT,
        env=environment,
        timeout=timeout_seconds,
        check=False,
    )


def format_subprocess_failure(
    result: subprocess.CompletedProcess[str],
) -> str:
    """Return useful diagnostics for unittest failures."""
    return "\n".join(
        [
            f"Return code: {result.returncode}",
            "----- STDOUT -----",
            result.stdout or "<empty>",
            "----- STDERR -----",
            result.stderr or "<empty>",
        ]
    )
