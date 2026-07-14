"""Run unittest in an isolated child process.

By default this supervisor always exits with code zero so an interactive
shell is not closed by a failing or crashing child process. Test status
is stored in JSON and log files. Use --strict only in an outer CI process.
"""

from __future__ import annotations

import argparse
import json
import os

os.environ.setdefault(
    "ATTENTIVE_DISABLE_REALTIME_VOICE_FOR_APPTEST",
    "1",
)

os.environ.setdefault(
    "ATTENTIVE_DISABLE_MICROPHONE_FOR_APPTEST",
    "1",
)
import signal
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(
    __file__
).resolve().parents[1]


def disable_core_dump() -> None:
    try:
        import resource

        resource.setrlimit(
            resource.RLIMIT_CORE,
            (
                0,
                0,
            ),
        )

    except (
        ImportError,
        OSError,
        ValueError,
    ):
        pass


def decode_signal(
    return_code: int,
) -> str | None:
    if return_code < 0:
        number = -return_code

    elif 128 <= return_code <= 255:
        number = return_code - 128

    else:
        return None

    try:
        return signal.Signals(
            number
        ).name

    except ValueError:
        return f"SIGNAL_{number}"


def build_environment() -> dict[str, str]:
    environment = os.environ.copy()

    environment.pop(
        "DASHSCOPE_API_KEY",
        None,
    )

    environment.update(
        {
            "ATTENTIVE_ENABLE_OCR": "0",
            "STREAMLIT_BROWSER_GATHER_USAGE_STATS": (
                "false"
            ),
            "OMP_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
            "OPENBLAS_NUM_THREADS": "1",
            "NUMEXPR_NUM_THREADS": "1",
            "TOKENIZERS_PARALLELISM": "false",
            "PYTHONFAULTHANDLER": "1",
            "MPLBACKEND": "Agg",
        }
    )

    return environment


def write_json(
    path: Path,
    payload: dict[str, Any],
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    path.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--output-dir",
        required=True,
    )

    parser.add_argument(
        "--name",
        required=True,
    )

    parser.add_argument(
        "--timeout",
        type=int,
        default=300,
    )

    parser.add_argument(
        "--discover-start",
    )

    parser.add_argument(
        "--pattern",
    )

    parser.add_argument(
        "--strict",
        action="store_true",
    )

    parser.add_argument(
        "modules",
        nargs="*",
    )

    arguments = parser.parse_args()

    output_directory = Path(
        arguments.output_dir
    )

    output_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    log_path = (
        output_directory
        / f"{arguments.name}.log"
    )

    json_path = (
        output_directory
        / f"{arguments.name}.json"
    )

    if arguments.discover_start:
        command = [
            sys.executable,
            "-X",
            "faulthandler",
            "-m",
            "unittest",
            "discover",
            "-s",
            arguments.discover_start,
        ]

        if arguments.pattern:
            command.extend(
                [
                    "-p",
                    arguments.pattern,
                ]
            )

        command.append("-v")

    else:
        if not arguments.modules:
            parser.error(
                "Provide unittest modules or "
                "--discover-start."
            )

        command = [
            sys.executable,
            "-X",
            "faulthandler",
            "-m",
            "unittest",
            *arguments.modules,
            "-v",
        ]

    started_at = datetime.now(
        timezone.utc
    )

    process = subprocess.Popen(
        command,
        cwd=ROOT,
        env=build_environment(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        shell=False,
        start_new_session=True,
        preexec_fn=disable_core_dump,
    )

    timed_out = False

    try:
        stdout, stderr = (
            process.communicate(
                timeout=arguments.timeout
            )
        )

    except subprocess.TimeoutExpired:
        timed_out = True

        try:
            os.killpg(
                process.pid,
                signal.SIGKILL,
            )
        except ProcessLookupError:
            pass

        stdout, stderr = (
            process.communicate()
        )

    return_code = (
        process.returncode
        if process.returncode
        is not None
        else 124
    )

    finished_at = datetime.now(
        timezone.utc
    )

    signal_name = decode_signal(
        return_code
    )

    passed = bool(
        return_code == 0
        and not timed_out
    )

    log_path.write_text(
        "\n".join(
            [
                "Safe unittest supervisor",
                (
                    "Command: "
                    + " ".join(command)
                ),
                (
                    f"Return code: "
                    f"{return_code}"
                ),
                (
                    f"Signal: "
                    f"{signal_name}"
                ),
                (
                    f"Timed out: "
                    f"{timed_out}"
                ),
                "----- STDOUT -----",
                stdout or "",
                "----- STDERR -----",
                stderr or "",
            ]
        ),
        encoding="utf-8",
    )

    payload = {
        "passed": passed,
        "supervisor_survived": True,
        "return_code": return_code,
        "signal": signal_name,
        "timed_out": timed_out,
        "started_at_utc": (
            started_at.isoformat()
        ),
        "finished_at_utc": (
            finished_at.isoformat()
        ),
        "command": command,
        "log_path": str(log_path),
    }

    write_json(
        json_path,
        payload,
    )

    print(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        )
    )

    if (
        arguments.strict
        and not passed
    ):
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
