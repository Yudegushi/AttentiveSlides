#!/usr/bin/env bash
set -eo pipefail

source /root/miniconda3/etc/profile.d/conda.sh
conda activate attentive-app

cd /root/autodl-tmp/workspace/AttentiveSlides

RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)"
RUN_DIR="/root/autodl-tmp/project_data/outputs/llm_tests/${RUN_ID}"

mkdir -p "${RUN_DIR}"

echo "Output directory: ${RUN_DIR}"

python - <<PY
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

output = Path("${RUN_DIR}") / "environment.json"

def git_value(*args):
    try:
        return subprocess.check_output(
            ["git", *args],
            text=True,
        ).strip()
    except Exception:
        return None

payload = {
    "timestamp_utc": datetime.now(
        timezone.utc
    ).isoformat(),
    "python": sys.version,
    "platform": platform.platform(),
    "git_commit": git_value("rev-parse", "HEAD"),
    "git_branch": git_value(
        "branch",
        "--show-current",
    ),
}

output.write_text(
    json.dumps(payload, indent=2),
    encoding="utf-8",
)
PY

python -m unittest \
  tests.test_llm_schemas \
  -v \
  2>&1 | tee "${RUN_DIR}/unit_llm_schemas.log"

python -m unittest \
  tests.test_grounded_prompt \
  -v \
  2>&1 | tee "${RUN_DIR}/unit_grounded_prompt.log"

python -m unittest \
  tests.test_response_parser \
  -v \
  2>&1 | tee "${RUN_DIR}/unit_response_parser.log"

python -m unittest \
  tests.test_grounding_validator \
  -v \
  2>&1 | tee "${RUN_DIR}/unit_grounding_validator.log"

python scripts/smoke_test_llm_schemas.py \
  --output "${RUN_DIR}/schema_smoke.json"

python scripts/smoke_test_grounded_prompt.py \
  --output "${RUN_DIR}/grounded_prompt_smoke.json"

python scripts/smoke_test_parser_validator.py \
  --output "${RUN_DIR}/parser_validator_smoke.json"

# 按要求，完整 discover 只运行，不额外保存输出。
python -m unittest discover -s tests -v

echo "${RUN_DIR}" \
  > /root/autodl-tmp/project_data/outputs/llm_tests/latest_run.txt

echo "Recorded LLM checks completed."
echo "Results: ${RUN_DIR}"
