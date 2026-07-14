# Lenovo Local Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Do not dispatch subagents.

**Goal:** Deploy the existing `codex/eyetheia-local-gaze-integration` branch on `LenovoLinux_Dorm` so AttentiveSlides, media ingress, EyeTheia, Whisper, and runtime data execute locally while Qwen continues to use DashScope APIs.

**Architecture:** Preserve the current branch and commit history with a Git bundle instead of pushing or merging. Reuse Lenovo's `pyboe` Conda environment, add only its five missing or mismatched packages, keep EyeTheia on `127.0.0.1:8001`, and run the existing single-port launcher as a user systemd service on `127.0.0.1:8501`.

**Tech Stack:** Python 3.10.20, Conda `pyboe`, Streamlit 1.59.1, aiohttp 3.14.1, faster-whisper 1.2.1, CTranslate2 4.8.1, CUDA 12/cuDNN 9, user systemd, Git bundle, DashScope.

## Global Constraints

- Source worktree: `/root/autodl-tmp/workspace/AttentiveSlides-eyetheia-local-gaze-integration` on `AutoDL`.
- Source and deployed branch: `codex/eyetheia-local-gaze-integration`; do not create another development branch.
- Lenovo deployment directory: `/home/charles/repos/AttentiveSlides-eyetheia-local-gaze-integration`.
- Reuse `/home/charles/miniconda3/envs/pyboe`; do not create another Conda environment unless the compatibility gate fails.
- Keep Qwen on DashScope with the existing `qwen3.7-plus` and `qwen3-vl-plus` configuration.
- Keep EyeTheia at `ws://127.0.0.1:8001/ws/predict_gaze` and do not retrain or replace its checkpoint.
- Start Whisper with the cached `faster-whisper-small` snapshot, CUDA, and `float16`.
- Do not run baseline tests or RED tests.
- Run one focused GREEN test group for the portability change and the full unit suite once after deployment.
- Do not run browser tests, browser smoke tests, lint, type checks, security scans, or performance suites.
- Do not use subagents.
- Do not push or merge.
- Do not stop the AutoDL launcher; retain it as the rollback target until manual acceptance succeeds.
- Never print or commit secret values.

---

## File Responsibility Map

| File | Responsibility |
|---|---|
| `apps/streamlit_attentive_slides.py` | Read the runtime data directory from `ATTENTIVE_RUNTIME_DATA_DIR` while retaining the AutoDL path as the default. |
| `tests/test_streamlit_attentive_slides.py` | Protect the environment override and legacy default path as a static UI contract. |
| `docs/superpowers/plans/2026-07-15-lenovo-local-deployment.md` | Record the exact migration, environment, service, verification, and rollback procedure. |
| `/home/charles/.config/attentiveslides/dashscope.env` | Hold the transferred API configuration with mode `0600`; it is not a repository file. |
| `/home/charles/.config/systemd/user/attentiveslides-local.service` | Run the local launcher with the `pyboe` interpreter and local model/data paths. |

---

### Task 1: Make the Runtime Data Directory Portable

**Files:**
- Modify: `apps/streamlit_attentive_slides.py:132`
- Modify: `tests/test_streamlit_attentive_slides.py`

**Interfaces:**
- Consumes: optional environment variable `ATTENTIVE_RUNTIME_DATA_DIR`.
- Produces: `RUNTIME_DATA_DIR: pathlib.Path`, defaulting to the existing AutoDL directory when the variable is absent.

- [ ] **Step 1: Add the GREEN-only static contract**

Add this method to `TestStreamlitAttentiveSlides` without running it separately:

```python
def test_runtime_data_dir_is_environment_configurable(
    self,
) -> None:
    self.assertIn(
        '"ATTENTIVE_RUNTIME_DATA_DIR"',
        self.source,
    )
    self.assertIn(
        '"/root/autodl-tmp/project_data/runtime/attentive_slides"',
        self.source,
    )
```

- [ ] **Step 2: Replace the hard-coded assignment**

Use exactly:

```python
RUNTIME_DATA_DIR = Path(
    os.environ.get(
        "ATTENTIVE_RUNTIME_DATA_DIR",
        "/root/autodl-tmp/project_data/runtime/attentive_slides",
    )
)
```

- [ ] **Step 3: Run the focused GREEN group once**

Run on AutoDL:

```bash
cd /root/autodl-tmp/workspace/AttentiveSlides-eyetheia-local-gaze-integration
/root/miniconda3/bin/conda run -n attentive-app \
  python -m unittest tests.test_streamlit_attentive_slides -v
```

Expected: every test in `tests.test_streamlit_attentive_slides` passes.

- [ ] **Step 4: Commit the portability change**

```bash
git add apps/streamlit_attentive_slides.py \
  tests/test_streamlit_attentive_slides.py
git commit -m "fix: make runtime data directory configurable"
```

---

### Task 2: Transfer the Exact Existing Branch to Lenovo

**Files:**
- Create on AutoDL: `/tmp/AttentiveSlides-eyetheia-local-gaze-integration.bundle`
- Create on Lenovo: `/home/charles/.cache/attentiveslides/AttentiveSlides-eyetheia-local-gaze-integration.bundle`
- Create on Lenovo: `/home/charles/repos/AttentiveSlides-eyetheia-local-gaze-integration/`

**Interfaces:**
- Consumes: the clean source branch after Task 1's commit.
- Produces: a Lenovo checkout of the same branch and exact HEAD; it does not create a new feature branch.

- [ ] **Step 1: Verify the source branch and create the bundle**

```bash
ssh AutoDL 'cd /root/autodl-tmp/workspace/AttentiveSlides-eyetheia-local-gaze-integration && git status --short --branch && git bundle create /tmp/AttentiveSlides-eyetheia-local-gaze-integration.bundle codex/eyetheia-local-gaze-integration && git bundle verify /tmp/AttentiveSlides-eyetheia-local-gaze-integration.bundle'
```

Require a clean `codex/eyetheia-local-gaze-integration` branch and a successful bundle verification.

- [ ] **Step 2: Transfer the bundle without GitHub**

```bash
ssh LenovoLinux_Dorm 'mkdir -p /home/charles/.cache/attentiveslides'
scp -3 AutoDL:/tmp/AttentiveSlides-eyetheia-local-gaze-integration.bundle \
  LenovoLinux_Dorm:/home/charles/.cache/attentiveslides/AttentiveSlides-eyetheia-local-gaze-integration.bundle
```

- [ ] **Step 3: Clone and verify the same branch**

```bash
ssh LenovoLinux_Dorm 'git clone --branch codex/eyetheia-local-gaze-integration /home/charles/.cache/attentiveslides/AttentiveSlides-eyetheia-local-gaze-integration.bundle /home/charles/repos/AttentiveSlides-eyetheia-local-gaze-integration && cd /home/charles/repos/AttentiveSlides-eyetheia-local-gaze-integration && git status --short --branch && git rev-parse HEAD'
```

Compare the printed HEAD with AutoDL. They must be identical before continuing.

---

### Task 3: Reuse and Complete the `pyboe` Environment

**Files:**
- Modify in place: `/home/charles/miniconda3/envs/pyboe`
- Create: `/home/charles/.config/attentiveslides/dashscope.env`
- Create: `/home/charles/.local/share/attentiveslides/project_data/`

**Interfaces:**
- Consumes: existing Python 3.10.20, Streamlit 1.59.1, faster-whisper 1.2.1, CTranslate2 4.8.1, and CUDA libraries in `pyboe`.
- Produces: all imports required by the five project requirement files, local runtime data, and API environment variables.

- [ ] **Step 1: Install only missing or mismatched packages**

```bash
ssh LenovoLinux_Dorm '/home/charles/miniconda3/bin/conda run -n pyboe python -m pip install streamlit-webrtc==0.75.0 aiohttp==3.14.1 "easyocr>=1.7.0" "dashscope>=1.24.5,<2.0" webrtcvad-wheels==2.0.14'
```

- [ ] **Step 2: Verify imports and package consistency**

```bash
ssh LenovoLinux_Dorm '/home/charles/miniconda3/bin/conda run -n pyboe python -c "import streamlit_webrtc,aiohttp,easyocr,dashscope,webrtcvad,faster_whisper,ctranslate2; print(aiohttp.__version__); print(ctranslate2.get_cuda_device_count())" && /home/charles/miniconda3/bin/conda run -n pyboe python -m pip check'
```

Require aiohttp `3.14.1`, one CUDA device, and `No broken requirements found`.

- [ ] **Step 3: Transfer secrets without displaying them**

```bash
ssh LenovoLinux_Dorm 'mkdir -p /home/charles/.config/attentiveslides && chmod 700 /home/charles/.config/attentiveslides'
scp -3 AutoDL:/root/autodl-tmp/secrets/dashscope.env \
  LenovoLinux_Dorm:/home/charles/.config/attentiveslides/dashscope.env
ssh LenovoLinux_Dorm 'chmod 600 /home/charles/.config/attentiveslides/dashscope.env'
```

- [ ] **Step 4: Transfer the existing project data**

```bash
ssh LenovoLinux_Dorm 'mkdir -p /home/charles/.local/share/attentiveslides'
scp -3 -r AutoDL:/root/autodl-tmp/project_data \
  LenovoLinux_Dorm:/home/charles/.local/share/attentiveslides/
```

Verify both sides report approximately `198M`:

```bash
ssh AutoDL 'du -sh /root/autodl-tmp/project_data'
ssh LenovoLinux_Dorm 'du -sh /home/charles/.local/share/attentiveslides/project_data'
```

---

### Task 4: Configure and Cut Over the Local Service

**Files:**
- Create: `/home/charles/.config/systemd/user/attentiveslides-local.service`

**Interfaces:**
- Consumes: `pyboe`, the imported checkout, DashScope environment file, local Whisper snapshot, and existing EyeTheia service.
- Produces: AttentiveSlides on `http://127.0.0.1:8501` with internal ports 8502 and 8503.

- [ ] **Step 1: Create the user service unit**

Create this exact file with `apply_patch` in a writable temporary location, then copy it to Lenovo:

```ini
[Unit]
Description=AttentiveSlides local live system
After=network-online.target

[Service]
Type=simple
WorkingDirectory=/home/charles/repos/AttentiveSlides-eyetheia-local-gaze-integration
ExecStart=/bin/bash -lc 'source /home/charles/.config/attentiveslides/dashscope.env; export ATTENTIVE_RUNTIME_DATA_DIR=/home/charles/.local/share/attentiveslides/project_data/runtime/attentive_slides; export ATTENTIVE_WHISPER_MODEL=/home/charles/.cache/huggingface/hub/models--Systran--faster-whisper-small/snapshots/536b0662742c02347bc0e980a01041f333bce120; export ATTENTIVE_WHISPER_DEVICE=cuda; export ATTENTIVE_WHISPER_COMPUTE_TYPE=float16; export LD_LIBRARY_PATH=/home/charles/miniconda3/envs/pyboe/lib/python3.10/site-packages/nvidia/cublas/lib:/home/charles/miniconda3/envs/pyboe/lib/python3.10/site-packages/nvidia/cudnn/lib; exec /home/charles/miniconda3/envs/pyboe/bin/python scripts/run_live_single_port.py --host 127.0.0.1 --port 8501 --streamlit-port 8502 --ingress-port 8503'
Restart=on-failure
RestartSec=3

[Install]
WantedBy=default.target
```

Copy and reload:

```bash
ssh LenovoLinux_Dorm 'mkdir -p /home/charles/.config/systemd/user'
scp /private/tmp/attentiveslides-local.service \
  LenovoLinux_Dorm:/home/charles/.config/systemd/user/attentiveslides-local.service
ssh LenovoLinux_Dorm 'systemctl --user daemon-reload'
```

- [ ] **Step 2: Confirm EyeTheia immediately before cutover**

```bash
ssh LenovoLinux_Dorm 'curl --fail --silent http://127.0.0.1:8001/api/health && systemctl --user is-active eyetheia-personalized.service'
```

Require `status=ok`, `personalized=true`, CUDA available, and service state `active`.

- [ ] **Step 3: Stop only the old AutoDL tunnel occupying port 8501**

```bash
ssh LenovoLinux_Dorm 'TUNNEL_PID=$(ss -ltnp | awk "/127.0.0.1:8501/ && /ssh/ {match(\$0,/pid=[0-9]+/); print substr(\$0,RSTART+4,RLENGTH-4); exit}"); test -n "$TUNNEL_PID"; ps -p "$TUNNEL_PID" -o pid=,args=; kill "$TUNNEL_PID"'
```

Require the displayed command to be the existing `ssh -fN ... -L 8501:127.0.0.1:8501 AutoDL` tunnel before accepting the kill.

- [ ] **Step 4: Start the local service**

```bash
ssh LenovoLinux_Dorm 'systemctl --user enable --now attentiveslides-local.service && systemctl --user --no-pager --full status attentiveslides-local.service | sed -n "1,45p"'
```

Require `active (running)`.

---

### Task 5: Run the Bounded Final Verification

**Files:** No repository changes.

**Interfaces:**
- Consumes: the running Lenovo deployment.
- Produces: fresh unit, model, HTTP, and service evidence for handoff.

- [ ] **Step 1: Run the full unit suite once on Lenovo**

```bash
ssh LenovoLinux_Dorm 'cd /home/charles/repos/AttentiveSlides-eyetheia-local-gaze-integration && /home/charles/miniconda3/bin/conda run -n pyboe python -m unittest discover -s tests -v'
```

Record the exact pass/fail count. The previously observed unrelated failure in `test_required_static_keys_exist` may remain; do not change the removed `main_thumbnail_window_previous/next` UI solely to satisfy that stale assertion, and do not rerun the full suite for it.

- [ ] **Step 2: Load Whisper on GPU and transcribe the known voiced fixture**

Run with the same dynamic library path as the service:

```bash
ssh LenovoLinux_Dorm 'cd /home/charles/repos/AttentiveSlides-eyetheia-local-gaze-integration && LD_LIBRARY_PATH=/home/charles/miniconda3/envs/pyboe/lib/python3.10/site-packages/nvidia/cublas/lib:/home/charles/miniconda3/envs/pyboe/lib/python3.10/site-packages/nvidia/cudnn/lib /home/charles/miniconda3/bin/conda run -n pyboe python -c "from modules.audio.faster_whisper_transcriber import FasterWhisperTranscriber; from modules.audio.transcriber import TranscriptionConfig; p=\"/home/charles/.local/share/attentiveslides/project_data/outputs/voice_stage3/20260713T185001Z/input_audio/voice_question_16k.wav\"; t=FasterWhisperTranscriber(TranscriptionConfig(model_size=\"/home/charles/.cache/huggingface/hub/models--Systran--faster-whisper-small/snapshots/536b0662742c02347bc0e980a01041f333bce120\",device=\"cuda\",compute_type=\"float16\")).transcribe(p); print(len(t.text), t.language)"'
```

Require a positive transcript length. Do not print or retain raw audio.

- [ ] **Step 3: Verify all local endpoints and GPU processes**

```bash
ssh LenovoLinux_Dorm 'curl --fail --silent http://127.0.0.1:8501/_stcore/health; curl --fail --silent http://127.0.0.1:8503/health; curl --fail --silent http://127.0.0.1:8001/api/health; ss -ltnp | grep -E "127.0.0.1:(8001|8501|8502|8503)"; nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv,noheader'
```

- [ ] **Step 4: Hand off for manual acceptance**

Ask the user to open `http://127.0.0.1:8501` and manually verify slide loading, camera permission, EyeTheia gaze, speech transcription, AOI behavior, and Qwen generation. Do not run an automated browser test.

- [ ] **Step 5: Preserve the rollback path**

If local acceptance fails, stop only the local service and restore the existing tunnel:

```bash
ssh LenovoLinux_Dorm 'systemctl --user stop attentiveslides-local.service; ssh -fN -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -L 8501:127.0.0.1:8501 AutoDL'
```

Do not delete the imported checkout, Conda packages, data copy, or AutoDL launcher during rollback.
