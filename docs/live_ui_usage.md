# Live UI Usage

## Purpose and ownership

`apps/streamlit_attentive_slides.py` is the official Manual + Live UI.
`apps/streamlit_live.py` remains a diagnostic entrypoint. The official page
owns rendering, confirmation, the single Main Tutor call, history, XAI, and
JSONL logging. One cached Live resource graph owns exactly one
`BrowserMediaSource`, `SystemController`, audio worker, sensing worker, and a
latest-only proposal inbox. The same source is injected into
`FallbackMediaIngress`.

HTTP handlers only validate, decode, timestamp, and enqueue bounded packets.
Sensing, VAD, and STT remain in worker/controller boundaries. Background
workers never call Streamlit or the LLM. No raw camera or microphone data is
persisted.

## AutoDL prerequisites

Use the project interpreter because the SSH shell has no reliable `python`
alias:

```bash
cd /path/to/AttentiveSlides-checkout
/root/miniconda3/envs/attentive-app/bin/python -m pip install \
  -r requirements-audio.txt -r requirements-media.txt
```

MediaPipe 0.10.35 exposes the Tasks API in the accepted AutoDL environment.
Install its Ubuntu GL runtime and download the official model bundle once:

```bash
apt-get install -y libgles2 libegl1
mkdir -p data/models
curl -fL --retry 3 \
  https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/latest/face_landmarker.task \
  -o data/models/face_landmarker.task
```

The accepted model is 3,758,596 bytes with SHA-256
`64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff`.

AutoDL could not connect to `huggingface.co`, while `hf-mirror.com` was
reachable. Pre-fetch the unchanged Systran `faster-whisper-small` model and
keep the returned local snapshot path:

```bash
HF_ENDPOINT=https://hf-mirror.com HF_HUB_DISABLE_XET=1 \
  /root/miniconda3/envs/attentive-app/bin/python -c \
  'from faster_whisper.utils import download_model; print(download_model("small"))'
```

Set `ATTENTIVE_WHISPER_MODEL` to that absolute snapshot path when launching.
An explicit local path prevents a cached model from blocking on an online
revision check. This changes neither the STT implementation nor model.

## One-port launch

Start the formal launcher on AutoDL. The launcher uses `sys.executable`, waits
for both internal health checks, inherits child output, fails on port conflicts,
and exits if either internal service later fails.

```bash
cd /path/to/AttentiveSlides-checkout
ATTENTIVE_WHISPER_MODEL=/absolute/path/to/faster-whisper-small/snapshot \
/root/miniconda3/envs/attentive-app/bin/python \
  scripts/run_live_single_port.py \
  --host 127.0.0.1 \
  --port 8501 \
  --streamlit-port 8502 \
  --ingress-port 8503
```

Forward exactly one port from the browser machine:

```bash
ssh -N -L 8501:127.0.0.1:8501 AutoDL
```

Open <http://localhost:8501>. The public aiohttp listener routes `/capture` and
`/media/*` to the internal ingress and routes the page, upload, assets, health,
and Streamlit WebSocket to internal Streamlit. The browser never accesses an
internal port.

## Master and media lifecycle

1. Upload a real PDF, switch to **Live**, then enable camera and microphone.
2. The Live media switch arms ingress and renders `/capture` outside the periodic
   Streamlit fragment. Capture automatically requests camera and microphone.
3. If browser policy blocks automatic capture, the component shows one
   **Grant camera/mic** recovery button. It is not a second master switch.
4. The controller starts only after fresh JPEG video and fresh 16 kHz mono PCM
   audio have both arrived for the active generation.
5. Replacement sessions stop the old runtime before activating and clearing
   readiness for the new generation.
6. Live media OFF, pagehide, heartbeat timeout, an ended track, persistent mute, or
   a stale track all stop controller, ingress, workers, browser tracks, and
   queues through the same idempotent cleanup.

Video is a bounded 320-pixel-wide JPEG stream at no more than five uploads per
second. Audio is little-endian signed-16 mono PCM at 16 kHz. The capture page
permits only one in-flight upload per track and uses only relative same-origin
URLs.

## Interaction behavior

Speak a short deictic request such as “解释一下这里”, then remain quiet so VAD
can finalize the turn. Empty STT output is recoverable and cannot create a
proposal. A valid transcript and the current coarse 3×3 gaze cell enter the
latest-only proposal inbox. The official UI resolves that cell against current
browser-coordinate AOI geometry, then lets the user confirm, correct, choose
the whole slide, or draw a manual rectangle.

Each canonical AOI is drawn with a numbered badge. The confirmation selector
uses the same number and includes the PDF-derived text excerpt, AOI type, and
internal ID. The full numbered mapping is available under **Canonical AOI
details**.

**Always confirm** is the default. **Confidence-based auto** is opt-in, defaults
to `0.80`, and never auto-confirms missing/low-confidence gaze, stale geometry,
or an existing pending interaction. The official UI calls only the existing
Main Tutor path after confirmation. Provider, parse, or grounding-validation
exhaustion is shown as a retryable error; no deterministic fallback answer is
presented. `/root/autodl-tmp/project_data/runtime/attentive_slides/logs/main_interactions.jsonl` is
written at most once per interaction ID and never contains raw media, secrets,
provider payloads, or hidden reasoning.

Point gaze and calibration are intentionally out of scope. Current production
targeting is coarse 3×3 viewport gaze plus browser-coordinate AOI/manual-region
geometry.

## Automated checks

Automated media tests use synthetic JPEG/PCM and deterministic fakes. They do
not request a physical camera/microphone, construct the default sensing model,
or call a real STT/LLM API.

```bash
/root/miniconda3/envs/attentive-app/bin/python -m unittest \
  tests.test_single_port_transport \
  tests.test_live_ingress_service \
  tests.test_live_single_port_launcher \
  tests.test_streamlit_live \
  tests.test_live_integrated_turn -v
```

## 2026-07-14 integrated UI acceptance status

The official one-port UI passed browser acceptance with the media switch on:
the capture iframe reported feeding, ingress reported active video/audio/
heartbeat freshness, and the periodic UI status updated to
`Runtime: speech_active · Media: ready`. Manual/Live switching, explicit
confidence-auto selection with a `0.80` slider, camera/mic OFF cleanup, and the
diagnostic entrypoint were also verified.

All 446 discovered tests, compileall, the demo tutor loop, and both eight-case
evaluation programs passed. Reference-resolution metrics and scenario-output
accuracy were all `1.0`. Real LLM acceptance was not run because no API key was
configured. Calibrated point gaze and a deliberate real human voice script
remain manual follow-up checks; synthetic media and integration tests cover the
same lifecycle contracts without claiming physical-device accuracy.

## 2026-07-13 diagnostic acceptance history

The formal path has passed the one-port technical gate: the real Streamlit UI
and WebSocket remained connected, the 13,499,116-byte course PDF crossed the
proxy without hash change, the embedded iframe obtained camera/microphone, and
both media counters were non-zero. Measured rates were approximately 4.6–4.9
video frames/s and 9.1–10.8 audio chunks/s with bounded queues.

The formal five-turn gate completed without restarting the app. Five
confirmation/final pairs produced deterministic tutor responses. Three final
records deliberately corrected the prediction:

- `pdf_semantic_block_4` -> `pdf_semantic_block_6`;
- `pdf_semantic_block_5` -> `whole_slide`;
- `pdf_semantic_block_4` -> `pdf_semantic_block_10`.

The other two retained `pdf_semantic_block_4`. Final response modes included
`step_by_step`, `review`, and `simplify`. JSONL grew from one pre-fix diagnostic
record to 14 records: five pending/final pairs, two earlier unfinished attempts,
and one ambient-noise pending turn after the five-turn gate. No raw media was
written.

Final Master OFF reported inactive/disarmed ingress, stopped source/controller,
both queue depths at zero, and cleanup state `stopped: master switch off`. The
capture iframe disappeared and pagehide released browser tracks. Final ON rates
were about 3.6 video frames/s and 9.3 audio chunks/s, with zero drops/overruns.

Known limitation: real-room VAD/STT can still create inaccurate or unwanted
transcripts; ambient noise produced an extra pending Russian transcript after
the five intended turns. OFF now clears unfinished confirmation UI. Numbered,
text-backed AOI choices fix the opaque `pdf_semantic_block_N` mapping, although
slides with many overlapping regions remain visually dense.

Do not count the earlier standalone fallback or pre-fix empty transcript as
formal completion evidence.
