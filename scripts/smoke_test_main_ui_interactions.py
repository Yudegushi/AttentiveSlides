"""Native-crash-safe supervisor for Main UI interaction scenarios."""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(
    __file__
).resolve().parents[1]

WORKER_PATH = (
    ROOT
    / "scripts"
    / "_main_ui_interaction_worker.py"
)

SCENARIOS = (
    "sidebar",
    "overlay",
    "manual_region",
    "intent",
    "reset",
)


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


def signal_name(
    return_code: int,
) -> str | None:
    if return_code < 0:
        signal_number = (
            -return_code
        )

    elif return_code >= 128:
        signal_number = (
            return_code - 128
        )

    else:
        return None

    try:
        return signal.Signals(
            signal_number
        ).name

    except ValueError:
        return (
            f"SIGNAL_{signal_number}"
        )


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
            "TOKENIZERS_PARALLELISM": (
                "false"
            ),
            "PYTHONFAULTHANDLER": "1",
            "MPLBACKEND": "Agg",
        }
    )

    return environment


def run_scenario(
    *,
    scenario: str,
    output_directory: Path,
    timeout_seconds: int,
) -> dict[str, Any]:
    scenario_json = (
        output_directory
        / f"{scenario}.json"
    )

    scenario_log = (
        output_directory
        / f"{scenario}.log"
    )

    command = [
        sys.executable,
        "-X",
        "faulthandler",
        str(WORKER_PATH),
        "--scenario",
        scenario,
        "--output",
        str(scenario_json),
    ]

    started_at = datetime.now(
        timezone.utc
    )

    try:
        completed = subprocess.run(
            command,
            cwd=ROOT,
            env=build_environment(),
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
            shell=False,
            start_new_session=True,
        )

        return_code = (
            completed.returncode
        )

        stdout = (
            completed.stdout or ""
        )

        stderr = (
            completed.stderr or ""
        )

        timed_out = False

    except subprocess.TimeoutExpired as exc:
        return_code = 124

        stdout = (
            exc.stdout.decode(
                errors="replace"
            )
            if isinstance(
                exc.stdout,
                bytes,
            )
            else (
                exc.stdout or ""
            )
        )

        stderr = (
            exc.stderr.decode(
                errors="replace"
            )
            if isinstance(
                exc.stderr,
                bytes,
            )
            else (
                exc.stderr or ""
            )
        )

        timed_out = True

    finished_at = datetime.now(
        timezone.utc
    )

    scenario_log.write_text(
        "\n".join(
            [
                (
                    f"Scenario: {scenario}"
                ),
                (
                    f"Return code: "
                    f"{return_code}"
                ),
                (
                    f"Signal: "
                    f"{signal_name(return_code)}"
                ),
                (
                    f"Timed out: "
                    f"{timed_out}"
                ),
                "----- STDOUT -----",
                stdout,
                "----- STDERR -----",
                stderr,
            ]
        ),
        encoding="utf-8",
    )

    worker_payload: dict[
        str,
        Any
    ] | None = None

    if scenario_json.is_file():
        try:
            worker_payload = json.loads(
                scenario_json.read_text(
                    encoding="utf-8"
                )
            )
        except (
            json.JSONDecodeError,
            OSError,
        ):
            worker_payload = None

    passed = bool(
        return_code == 0
        and worker_payload
        and worker_payload.get(
            "passed"
        )
        is True
    )

    return {
        "scenario": scenario,
        "passed": passed,
        "return_code": return_code,
        "signal": signal_name(
            return_code
        ),
        "timed_out": timed_out,
        "started_at_utc": (
            started_at.isoformat()
        ),
        "finished_at_utc": (
            finished_at.isoformat()
        ),
        "worker_output_available": (
            worker_payload is not None
        ),
        "worker_payload": (
            worker_payload
        ),
        "log_path": str(
            scenario_log
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--output",
        required=True,
    )

    parser.add_argument(
        "--timeout-per-scenario",
        type=int,
        default=240,
    )

    parser.add_argument(
        "--strict",
        action="store_true",
        help=(
            "Return a non-zero exit code when "
            "any scenario fails. Intended for "
            "the isolated unittest wrapper."
        ),
    )

    arguments = parser.parse_args()

    if (
        arguments.timeout_per_scenario
        <= 0
    ):
        raise ValueError(
            "timeout-per-scenario must "
            "be positive."
        )

    output_path = Path(
        arguments.output
    )

    parts_directory = (
        output_path.parent
        / (
            output_path.stem
            + "_parts"
        )
    )

    parts_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    results: list[
        dict[str, Any]
    ] = []

    for scenario in SCENARIOS:
        print(
            f"Running isolated scenario: "
            f"{scenario}",
            flush=True,
        )

        result = run_scenario(
            scenario=scenario,
            output_directory=(
                parts_directory
            ),
            timeout_seconds=(
                arguments
                .timeout_per_scenario
            ),
        )

        results.append(result)

        status = (
            "PASS"
            if result["passed"]
            else "FAIL"
        )

        print(
            f"{scenario}: {status}; "
            f"return_code="
            f"{result['return_code']}; "
            f"signal="
            f"{result['signal']}",
            flush=True,
        )

    completed_step_count = 0

    for result in results:
        worker_payload = (
            result.get(
                "worker_payload"
            )
            or {}
        )

        completed_step_count += len(
            worker_payload.get(
                "completed_steps",
                [],
            )
        )

    payload = {
        "passed": all(
            result["passed"]
            for result in results
        ),
        "supervisor_survived": True,
        "strict_mode": bool(
            arguments.strict
        ),
        "scenario_count": len(
            results
        ),
        "passed_scenario_count": sum(
            result["passed"]
            for result in results
        ),
        "completed_step_count": (
            completed_step_count
        ),
        "results": results,
    }

    write_json(
        output_path,
        payload,
    )

    print(
        "\nInteraction smoke summary",
        flush=True,
    )

    print(
        json.dumps(
            {
                "passed": (
                    payload["passed"]
                ),
                "supervisor_survived": (
                    payload[
                        "supervisor_survived"
                    ]
                ),
                "passed_scenarios": (
                    payload[
                        "passed_scenario_count"
                    ]
                ),
                "scenario_count": (
                    payload[
                        "scenario_count"
                    ]
                ),
                "completed_steps": (
                    payload[
                        "completed_step_count"
                    ]
                ),
            },
            indent=2,
        ),
        flush=True,
    )

    # Default diagnostic mode always returns zero, so a native worker
    # crash cannot close a shell configured with `set -e`.
    if (
        arguments.strict
        and not payload["passed"]
    ):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
