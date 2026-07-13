"""Regression test for isolated Streamlit interaction scenarios."""

from __future__ import annotations

import json
import os

os.environ.setdefault(
    "ATTENTIVE_DISABLE_MICROPHONE_FOR_APPTEST",
    "1",
)
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(
    __file__
).resolve().parents[1]


class TestStreamlitWidgetInteractions(
    unittest.TestCase
):
    def test_isolated_widget_scenarios(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output_path = (
                Path(directory)
                / "interaction_smoke.json"
            )

            environment = os.environ.copy()

            environment.pop(
                "DASHSCOPE_API_KEY",
                None,
            )

            environment.update(
                {
                    "ATTENTIVE_ENABLE_OCR": "0",
                    "ATTENTIVE_DISABLE_CANVAS_FOR_APPTEST": "1",
                    "STREAMLIT_BROWSER_GATHER_USAGE_STATS": "false",
                    "OMP_NUM_THREADS": "1",
                    "MKL_NUM_THREADS": "1",
                    "OPENBLAS_NUM_THREADS": "1",
                    "NUMEXPR_NUM_THREADS": "1",
                    "TOKENIZERS_PARALLELISM": "false",
                    "PYTHONFAULTHANDLER": "1",
                    "MPLBACKEND": "Agg",
                }
            )

            result = subprocess.run(
                [
                    sys.executable,
                    (
                        "scripts/"
                        "smoke_test_main_ui_interactions.py"
                    ),
                    "--output",
                    str(output_path),
                    "--timeout-per-scenario",
                    "240",
                    "--strict",
                ],
                cwd=ROOT,
                env=environment,
                text=True,
                capture_output=True,
                timeout=1500,
                check=False,
                shell=False,
                start_new_session=True,
            )

            diagnostic = "\n".join(
                [
                    (
                        "Supervisor return code: "
                        f"{result.returncode}"
                    ),
                    "----- STDOUT -----",
                    result.stdout or "",
                    "----- STDERR -----",
                    result.stderr or "",
                ]
            )

            self.assertTrue(
                output_path.is_file(),
                diagnostic,
            )

            payload = json.loads(
                output_path.read_text(
                    encoding="utf-8"
                )
            )

            failed = [
                {
                    "scenario": item[
                        "scenario"
                    ],
                    "return_code": item[
                        "return_code"
                    ],
                    "signal": item[
                        "signal"
                    ],
                    "timed_out": item[
                        "timed_out"
                    ],
                    "worker_payload": item[
                        "worker_payload"
                    ],
                }
                for item in payload[
                    "results"
                ]
                if not item["passed"]
            ]

            self.assertTrue(
                payload[
                    "supervisor_survived"
                ],
                payload,
            )

            self.assertEqual(
                result.returncode,
                0,
                diagnostic
                + "\n"
                + json.dumps(
                    failed,
                    ensure_ascii=False,
                    indent=2,
                ),
            )

            self.assertTrue(
                payload["passed"],
                failed,
            )

            self.assertEqual(
                payload[
                    "scenario_count"
                ],
                5,
            )

            self.assertEqual(
                payload[
                    "passed_scenario_count"
                ],
                5,
            )

            self.assertGreaterEqual(
                payload[
                    "completed_step_count"
                ],
                15,
            )


if __name__ == "__main__":
    unittest.main()
