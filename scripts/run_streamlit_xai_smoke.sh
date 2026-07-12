#!/usr/bin/env bash
set -eo pipefail

source /root/miniconda3/etc/profile.d/conda.sh
conda activate attentive-app

cd /root/autodl-tmp/workspace/AttentiveSlides

OUTPUT_DIR="${1:?Usage: run_streamlit_xai_smoke.sh OUTPUT_DIR}"
PORT="${STREAMLIT_XAI_SMOKE_PORT:-8512}"

mkdir -p "${OUTPUT_DIR}"

LOG_PATH="${OUTPUT_DIR}/streamlit_server.log"
HEALTH_PATH="${OUTPUT_DIR}/streamlit_health.json"

python -m streamlit run \
  apps/streamlit_grounded_xai.py \
  --server.headless=true \
  --server.address=127.0.0.1 \
  --server.port="${PORT}" \
  > "${LOG_PATH}" \
  2>&1 &

SERVER_PID=$!

cleanup() {
  kill "${SERVER_PID}" 2>/dev/null || true
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

url = "http://127.0.0.1:${PORT}/_stcore/health"
deadline = time.time() + 45
last_error = None
body = None
status = None

while time.time() < deadline:
    try:
        with urllib.request.urlopen(
            url,
            timeout=3,
        ) as response:
            status = response.status
            body = response.read().decode(
                "utf-8",
                errors="replace",
            )
        break
    except Exception as exc:
        last_error = str(exc)
        time.sleep(1)

try:
    git_commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        text=True,
    ).strip()
except Exception:
    git_commit = None

payload = {
    "timestamp_utc": datetime.now(
        timezone.utc
    ).isoformat(),
    "url": url,
    "http_status": status,
    "response_body": body,
    "last_error": last_error,
    "git_commit": git_commit,
    "passed": (
        status == 200
        and body is not None
        and "ok" in body.casefold()
    ),
}

Path("${HEALTH_PATH}").write_text(
    json.dumps(
        payload,
        ensure_ascii=False,
        indent=2,
    ),
    encoding="utf-8",
)

print(json.dumps(
    payload,
    ensure_ascii=False,
    indent=2,
))

if not payload["passed"]:
    raise SystemExit(1)
PY

echo "Streamlit server smoke test passed."
