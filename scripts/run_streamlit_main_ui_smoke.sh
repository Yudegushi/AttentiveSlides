#!/usr/bin/env bash

set -euo pipefail

source /root/miniconda3/etc/profile.d/conda.sh
conda activate attentive-app

REPOSITORY_ROOT="/root/autodl-tmp/workspace/AttentiveSlides"

cd "${REPOSITORY_ROOT}"

OUTPUT_DIR="${1:?Usage: run_streamlit_main_ui_smoke.sh OUTPUT_DIR}"
PORT="${STREAMLIT_MAIN_UI_SMOKE_PORT:-8513}"

mkdir -p "${OUTPUT_DIR}"

LOG_PATH="${OUTPUT_DIR}/streamlit_server.log"
HEALTH_PATH="${OUTPUT_DIR}/streamlit_health.json"

python -m streamlit run \
  apps/streamlit_attentive_slides.py \
  --server.headless=true \
  --server.address=127.0.0.1 \
  --server.port="${PORT}" \
  --server.fileWatcherType=none \
  --browser.gatherUsageStats=false \
  > "${LOG_PATH}" \
  2>&1 &

SERVER_PID=$!

cleanup() {
  if kill -0 "${SERVER_PID}" 2>/dev/null; then
    kill "${SERVER_PID}" 2>/dev/null || true
  fi

  wait "${SERVER_PID}" 2>/dev/null || true
}

trap cleanup EXIT

python - <<PY
import json
import subprocess
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


health_url = (
    "http://127.0.0.1:${PORT}"
    "/_stcore/health"
)

deadline = time.time() + 45
last_error = None
response_body = None
http_status = None

while time.time() < deadline:
    try:
        with urllib.request.urlopen(
            health_url,
            timeout=3,
        ) as response:
            http_status = response.status
            response_body = (
                response
                .read()
                .decode(
                    "utf-8",
                    errors="replace",
                )
            )

        break

    except Exception as exc:
        last_error = (
            f"{type(exc).__name__}: {exc}"
        )
        time.sleep(1)

try:
    git_commit = subprocess.check_output(
        [
            "git",
            "rev-parse",
            "HEAD",
        ],
        text=True,
    ).strip()
except Exception:
    git_commit = None

passed = (
    http_status == 200
    and response_body is not None
    and "ok" in response_body.casefold()
)

payload = {
    "timestamp_utc": datetime.now(
        timezone.utc
    ).isoformat(),
    "url": health_url,
    "http_status": http_status,
    "response_body": response_body,
    "last_error": last_error,
    "git_commit": git_commit,
    "passed": passed,
}

Path("${HEALTH_PATH}").write_text(
    json.dumps(
        payload,
        ensure_ascii=False,
        indent=2,
    ),
    encoding="utf-8",
)

print(
    json.dumps(
        payload,
        ensure_ascii=False,
        indent=2,
    )
)

if not passed:
    raise SystemExit(1)
PY
