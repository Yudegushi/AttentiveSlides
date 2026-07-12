# Foundation and Browser Media Handoff

Status: partial
Branch: `codex/live-system-integration-v1`
Start commit: `5859d8add528e08b4db62b63bab88a7683db5b55`
End commit: pending Checkpoint 1
Scope: Checkpoints 0–1

## Checkpoint commits

- Checkpoint 0 — AutoDL preflight and safe branch: this commit (`chore: audit AutoDL integration baseline`); final SHA will be recorded after creation.
- Checkpoint 1 — browser video/audio transport gate: pending.

## Delivered

### Checkpoint 0

- Verified the existing working branch without creating another branch or worktree.
- Confirmed the branch starts at `feature/api-llm-pipeline@705f1a2`; `HEAD` was one planning commit ahead of that ref at preflight.
- Audited Git, Python/conda, GPU/CUDA, disk, media/slide/audio dependencies, baseline tests, demo, and evaluations on AutoDL.
- Confirmed `PROJECT_PROGRESS.md` and the legacy audio documents still describe `LenovoLinux_Dorm`; those environment claims are historical and do not describe this stage's AutoDL runtime.

Checkpoint 1 interfaces and delivered files are pending.

## Decisions and deviations

- Kept the already-created `codex/live-system-integration-v1` branch as required. No branch, worktree, merge, reset, clean, or destructive checkout was created or run.
- Used the existing conda environment `/root/miniconda3/envs/attentive-app` (Python 3.10.20). Non-interactive SSH does not expose `python` or `conda` on `PATH`, so reproducible commands use the environment's absolute Python path or source `/root/miniconda3/etc/profile.d/conda.sh`.
- Did not alter torch or CUDA. Existing torch is `2.7.1+cu118`; CUDA is available on the Tesla V100S.
- Checkpoint 1 transport and fallback decision remain pending the real browser gate.

## Dependency and environment evidence

Measured on 2026-07-12 (Asia/Shanghai):

- GPU: Tesla V100S-PCIE-32GB, 32768 MiB; driver 550.107.02; `nvidia-smi` reports CUDA 12.4 compatibility; no GPU processes at audit time.
- Python: 3.10.20 in `attentive-app`; base is Python 3.12.3.
- Torch: 2.7.1+cu118; `torch.cuda.is_available()` returned `True`; device name was `Tesla V100S-PCIE-32GB`.
- Disk: `/root/autodl-tmp` 50G total, 23G used, 28G available (46%).
- Installed in `attentive-app`: Streamlit 1.59.1, PyAV 17.1.0, OpenCV headless 4.13.0.92 plus OpenCV contrib 5.0.0.93, MediaPipe 0.10.35, PyMuPDF 1.28.0, faster-whisper 1.2.1, NumPy 2.2.6, Pillow 12.2.0, sounddevice 0.5.5, soundfile 0.14.0.
- Missing at Checkpoint 0: `streamlit-webrtc`; `webrtcvad` is also absent but is not required until the later VAD checkpoint.
- External dependencies not exercised by mandatory baseline: real camera/microphone, Hugging Face model download/cache, and real API credentials.

## Verification evidence

Commands were executed from `/root/autodl-tmp/workspace/AttentiveSlides` on AutoDL.

- `git status --short --branch` — PASS; clean `## codex/live-system-integration-v1` at start.
- `git log --oneline --decorate -n 20` — PASS; start HEAD `5859d8a`, base `705f1a2`.
- `git fetch origin --prune` — PASS; remote refs remained `main@a90916b`, `integration-v100@353c033`, and `feature/api-llm-pipeline@705f1a2`.
- `git rev-list --left-right --count HEAD...origin/feature/api-llm-pipeline` — `1 0`; against integration `9 0`; against main `13 0`.
- `/root/miniconda3/envs/attentive-app/bin/python -V` — `Python 3.10.20`.
- `nvidia-smi` — PASS; V100S details above.
- `df -h . /root/autodl-tmp` — PASS; 28G available.
- `/root/miniconda3/envs/attentive-app/bin/python -m unittest discover -s tests -v` — PASS, 147 tests, 0 failures/errors, 1.345 s. No real camera, microphone, model download, or API call was requested.
- `/root/miniconda3/envs/attentive-app/bin/python scripts/demo_tutor_loop.py` — PASS; eight scenarios completed and wrote the ignored `data/logs/demo_interactions.jsonl` runtime log.
- `/root/miniconda3/envs/attentive-app/bin/python evaluation/eval_reference_resolution.py` — PASS; 8 scenarios, all four reported metrics `1.0`.
- `/root/miniconda3/envs/attentive-app/bin/python evaluation/eval_scenario_outputs.py` — PASS; 8 scenarios, output accuracy `1.0`.
- `git diff --check` — PASS with no output.

Manual browser media acceptance: not verified; Checkpoint 1 has not started.

## Known issues and risks

- `streamlit-webrtc` is absent, so the primary transport cannot be run until that dependency is added without disturbing torch/CUDA.
- Non-interactive SSH callers must explicitly select `attentive-app`.
- The current environment contains both OpenCV contrib 5.0.0.93 and OpenCV headless 4.13.0.92; imports work in the existing baseline, but this mixed install remains an environment risk and was not changed.
- Real WebRTC behavior through a single SSH-forwarded port is unverified.
- The demo created `data/logs/demo_interactions.jsonl`; it is runtime output and must remain uncommitted.

## Next conversation must read

Pending completion of Checkpoint 1. At minimum, the next conversation must read the final Checkpoint 0 and Checkpoint 1 commits, this handoff, `modules/media/`, `apps/media_transport_probe.py`, `docs/browser_media_runtime.md`, and the media tests that will be delivered.

## Workspace state

- At Checkpoint 0 start: clean branch `codex/live-system-integration-v1` at `5859d8a`.
- Runtime temporary data: ignored `data/logs/demo_interactions.jsonl` produced by the baseline demo; no raw audio/video created.
- Running processes: none started by Checkpoint 0.
- Push: not pushed by this conversation at this point.
