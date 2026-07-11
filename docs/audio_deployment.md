# Audio Deployment

This document covers the file-based and push-to-talk audio path for
AttentiveSlides Member 3. It does not cover streaming ASR, wake words,
diarization, cloud ASR, or model fine-tuning.

## Local Mock Path

Default unit tests and dry-run demos use the deterministic mock engine:

```bash
python scripts/transcribe_audio_file.py --audio data/audio_samples/explain_this.wav --engine mock
python scripts/demo_audio_to_tutor_loop.py --audio data/audio_samples/right_figure.wav --engine mock
```

The mock engine maps known filenames to transcripts and does not require real audio
files. This keeps ordinary development independent of faster-whisper, CUDA, and model
downloads.

The CLI now supports shared model profiles:

```bash
python scripts/transcribe_audio_file.py --audio data/audio_samples/explain_this.wav --engine mock --profile balanced
python scripts/demo_audio_to_tutor_loop.py --audio data/audio_samples/right_figure.wav --engine mock --profile fast --sensing-preset high_confidence_right_figure
```

Profiles:

| Profile | Model | Device | Compute type | Use |
|---|---|---|---|---|
| `fast` | `small` | `cuda` | `int8_float16` | quick fallback |
| `balanced` | `medium` | `cuda` | `int8_float16` | default interactive demo |
| `accurate` | `large-v3` | `cuda` | `int8_float16` | accuracy candidate |
| `cpu` | `small` | `cpu` | `int8` | no-CUDA fallback |

## Optional faster-whisper Dependency

Install audio dependencies only when running real STT:

```bash
pip install -r requirements-audio.txt
```

`faster-whisper` uses PyAV and usually does not require system `ffmpeg`, because PyAV
bundles FFmpeg libraries. If a local environment still reports media decoding errors,
installing system `ffmpeg` can be used as a troubleshooting step.

The first model load may download weights from Hugging Face Hub. Warm up the model
before a live demo so download and cache time do not affect the presentation.
On LenovoLinux_Dorm, the default Hugging Face Hub connection reset during the first
`small` model load. Using the mirror endpoint worked:

```bash
export HF_ENDPOINT=https://hf-mirror.com
```

## Recording And UI Demo

Record a short local wav for terminal smoke tests:

```bash
python scripts/record_audio_file.py --duration 4 --output data/audio_samples/recorded/smoke.wav
```

Then transcribe it with the default interactive profile:

```bash
python scripts/transcribe_audio_file.py \
  --audio data/audio_samples/recorded/smoke.wav \
  --engine faster_whisper \
  --profile balanced
```

Run the Streamlit demo:

```bash
python -m streamlit run apps/streamlit_demo.py \
  --server.headless true \
  --server.port 8501 \
  --browser.gatherUsageStats false
```

The sidebar input modes are:

- `Mock scenario text`: the deterministic text fallback.
- `Audio file upload`: use `st.audio_input` when available, otherwise upload an audio file.
- `Recorded wav path`: point to a local wav such as `data/audio_samples/recorded/smoke.wav`.

After clicking `Transcribe audio`, the transcript is copied into the existing
learner utterance text area. Edit the transcript if needed, then use the existing
AOI confirmation/correction flow before reading the tutor response.

For the current English user-recording workflow, the Streamlit transcription call
passes `language="en"`. The sidebar also displays the selected STT profile, measured
transcription latency, and whether the source was uploaded audio or a local recorded path.
The audio button remains manually triggered; there is no background recording or streaming.

For project-specific profile evaluation, use
[audio_usability_eval.md](audio_usability_eval.md).

## Recommended 4060 Settings

For the Lenovo Linux machine with an RTX 4060 Laptop GPU, the recommended
interactive command is:

```bash
python scripts/transcribe_audio_file.py \
  --audio data/audio_samples/recorded/smoke.wav \
  --engine faster_whisper \
  --profile balanced
```

Run the pipeline demo through the adapter boundary:

```bash
python scripts/demo_audio_to_tutor_loop.py \
  --audio data/audio_samples/recorded/smoke.wav \
  --engine faster_whisper \
  --profile balanced \
  --sensing-preset high_confidence_right_figure
```

Use `--profile accurate` only after warming up `large-v3`; keep `balanced` as the
default if `large-v3` is too slow or unstable.

## CPU Fallback

For CPU-only checks:

```bash
python scripts/transcribe_audio_file.py \
  --audio data/audio_samples/recorded/smoke.wav \
  --engine faster_whisper \
  --profile cpu
```

## LenovoLinux_Dorm Facts

Verified environment notes:

- Host is reachable through SSH config host `LenovoLinux_Dorm`.
- OS: Ubuntu Linux, kernel `6.8.0-134-generic`.
- Default `python3 --version`: `Python 3.12.3`.
- GPU: NVIDIA GeForce RTX 4060 Laptop GPU, driver `595.71.05`, memory `8188 MiB`.
- `/usr/bin/ffmpeg` and `/usr/bin/git` are present.
- `conda` is installed at `/home/charles/miniconda3`, but non-interactive `bash`
  needs the conda profile script sourced first.
- Use the existing `pyboe` conda environment for audio work:

```bash
source /home/charles/miniconda3/etc/profile.d/conda.sh
conda activate pyboe
python --version  # Python 3.10.20
which python      # /home/charles/miniconda3/envs/pyboe/bin/python
```

- `mamba` and `nvcc` were not found in the default PATH during the environment check.
- `faster-whisper==1.2.1` was installed in `pyboe` for the audio smoke test.
- `HF_ENDPOINT=https://hf-mirror.com` successfully loaded `faster-whisper` `small`
  with `device=cuda` and `compute_type=int8_float16`.
- On 2026-07-10, GPU check reported `8188 MiB` total, `602 MiB` used, and
  `7182 MiB` free before model load.
- On 2026-07-10, `medium` with `cuda` and `int8_float16` transcribed one
  existing public `minds14` sample successfully. The first run took about
  `550s` because it included model download/cache time.
- On 2026-07-10, `large-v3` with `cuda` and `int8_float16` transcribed the same
  public sample successfully. The first run took about `1519s` because it
  included model download/cache time.
- After model caching, one public sample took about `5.30s` with `medium` and
  about `4.58s` with `large-v3` in separate CLI processes. Treat this as a
  sanity check, not a final latency benchmark for project command recordings.
- The synced remote CLI accepted `--profile balanced` and `--profile accurate`
  successfully. Project-specific `data/audio_samples/recorded/smoke.wav` still
  needs a real user recording.

Avoid the default Python 3.12 environment for the first GPU demo unless dependency
compatibility is checked first.

## Real Smoke Phrases

Use [audio_usability_smoke_phrases.md](audio_usability_smoke_phrases.md) for the
next manual recording set. These recordings are for usability smoke tests only,
not fine-tuning or statistical ASR evaluation.

## Git Hygiene

Do not commit private recordings, generated logs, downloaded model weights, or local
cache directories. `data/audio_samples/` is ignored except for its README and `.gitkeep`.
Microphone use is user-triggered only. There is no wake word and no background
listening in this stage.
