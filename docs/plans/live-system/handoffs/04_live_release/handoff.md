# Live UI and Release Handoff

Status: implementation, automated integration, and formal five-turn manual gate
complete; final regression/commit/push in progress.

Branch: `codex/live-system-integration-v1`

Start HEAD: `aaadb51bb5a1d01149a965bd340de7b4c1fa7d4f`

Scope: formal single-port HTTP media integration into the existing continuous
runtime. No main change, merge, or PR is authorized.

## Ownership and invariants

- `apps/streamlit_live.py` no longer imports or calls `streamlit-webrtc`.
- One cached `LiveResources` graph owns exactly one `BrowserMediaSource`,
  `SystemController`, audio worker, sensing worker, `LiveTurnRunner`, ingress,
  and lifecycle service. The controller and ingress share the identical source.
- HTTP handlers validate/decode/timestamp/enqueue only. They never run sensing,
  VAD, STT, LLM/tutor work, or Streamlit commands.
- Existing single-active-turn, frozen context, confirmation resume, correction
  override, `SensingSnapshotStore`, canonical pipeline, and bounded queue
  contracts remain in force.
- No raw audio/video persistence was added.

## Formal route and launcher

`scripts/run_live_single_port.py` exposes one loopback public port. `/capture`
and `/media/*` route to the internal aiohttp ingress; Streamlit page/upload,
assets, health, and WebSocket route to internal Streamlit. The browser uses one
`ssh -N -L` mapping only.

The launcher uses its own `sys.executable`, preserves WebSocket subprotocols and
binary/text frames, streams large HTTP bodies, preserves header multiplicity,
rewrites internal redirects, waits for both internal health endpoints, inherits
child output, fails fixed-port collisions, and exits if a healthy internal
service later dies.

## Media lifecycle

- Master ON arms ingress and renders the capture iframe outside the periodic
  fragment. Automatic capture has one permission-recovery button only.
- Browser video is bounded 320-pixel JPEG; audio is 16 kHz mono signed-16 PCM.
  Both use relative same-origin requests, one in-flight request per track, a
  heartbeat, track ended/mute handlers, and pagehide cleanup.
- The coordinator owns session replacement ordering: stop old runtime, activate
  the shared source for the pending generation, clear readiness, then require
  new fresh video and audio before starting the runtime.
- Freshness uses server monotonic receive times: 2.0 seconds per track and a
  3.0-second heartbeat timeout. OFF, disconnect, heartbeat loss, stale track,
  ended track, and persistent mute converge on idempotent controller/worker/
  source/queue cleanup.

## Test and browser evidence so far

The formal-path technical spike passed before lifecycle implementation:

- Streamlit 1.59.1 WebSocket stayed connected after forwarding its requested
  subprotocols.
- The embedded `/capture` iframe received camera and microphone permission.
- Real media reached roughly 4.6–4.9 video frames/s and 9.1–10.8 audio chunks/s.
- `lecture_11_human_ai_interaction.pdf` crossed the public proxy with exact
  13,499,116-byte size and SHA-256
  `9c3ea47a5746cb6681447b3a51fd125ddf17485412ec79629f3c2d20fd5601d8`.
- Page close/heartbeat cleanup stopped the source and cleared both queues.

Targeted transport/runtime tests passed before manual acceptance, including
shared-source identity, dual-track freshness, single-track refusal, OFF and
disconnect cleanup, replacement generation ordering, rerun idempotency,
multi-megabyte upload, WebSocket frames/subprotocols, confirmation, correction,
and OFF-to-ON restart. The integrated test uses a real PDF provider and real
controller/service/worker boundaries with injected deterministic sensing,
transcription, and tutor implementations; it never initializes MediaPipe or
calls a real API.

## Formal-path defects found and fixed during acceptance

1. Proxy WebSocket subprotocols were not relayed, preventing Streamlit from
   maintaining its session. Both proxy directions now preserve the selected
   protocol; a RED/GREEN test covers it.
2. A listener preflight falsely rejected a recently closed fixed port. The
   preflight now uses `SO_REUSEADDR`; a RED/GREEN test covers the TIME_WAIT case.
3. Periodic AOI rendering used `st.dataframe` and reproducibly segfaulted inside
   PyArrow after a real PDF upload. The stable slide panel now uses ordinary
   Streamlit text and an in-memory derived JPEG data URI, keeping the periodic
   path out of PyArrow and the proxy-owned `/media/*` route.
4. AutoDL MediaPipe Tasks lacked `face_landmarker.task`, `libGLESv2.so.2`, and
   `libEGL.so.1`. The accepted environment uses the official 3,758,596-byte
   bundle plus Ubuntu `libgles2` and `libegl1`; the extractor successfully
   initialized EGL/OpenGL ES and closed cleanly.
5. AutoDL could not reach `huggingface.co`. The unchanged
   Systran faster-whisper-small model was prefetched through `hf-mirror.com` and
   supplied via `ATTENTIVE_WHISPER_MODEL`; a local 1-second WAV completed STT.
6. The audio environment lacked the preferred PCM VAD and fell back to a
   peak-sensitive deterministic backend. `webrtcvad-wheels==2.0.14` is now an
   audio requirement, and `default_vad_backend()` selects `WebRtcVadBackend`.
   This package is local VAD only and is unrelated to ICE/STUN/TURN transport.
7. Empty STT output from ambient noise was incorrectly allowed into reference
   resolution and confirmation. `AudioWorker` now publishes it as recoverable
   `invalid/empty_transcript`, so the controller returns to monitoring without
   creating an interaction. Valid STT behavior is unchanged.
8. `st.image` generated a Streamlit `/media/<hash>.jpg` URL, conflicting with
   the formal proxy rule that owns `/media/*` for ingress. The derived overlay
   now uses a bounded in-memory JPEG data URI; nothing is persisted.
9. Loading a deck could stop the shared source while the service still believed
   the runtime was active. Reconciliation now resets that lifecycle and again
   requires fresh video plus audio before restart.
10. Manual acceptance showed that raw `pdf_semantic_block_N` choices could not
    be mapped to visible regions. Slide AOIs now have numbered badges and the
    selector uses the same number with PDF-derived text/type. OFF and disconnect
    also clear unfinished-turn UI state.
11. Launcher output captured an intermittent `dictionary changed size during
    iteration` while Streamlit and the sensing worker generated neighboring
    slide AOIs concurrently. `AOIManager` now serializes every in-process
    manifest mutation/write with one reentrant lock; a deterministic two-thread
    regression test covers the crash.

## Runtime prerequisites

- Python 3.10 in `/root/miniconda3/envs/attentive-app`.
- `requirements-audio.txt` and `requirements-media.txt`.
- Ubuntu `libgles2` and `libegl1` for MediaPipe Tasks.
- Official `data/models/face_landmarker.task` (SHA-256 above).
- A local faster-whisper-small snapshot supplied in
  `ATTENTIVE_WHISPER_MODEL` when Hugging Face is unreachable.
- Deterministic tutor for mandatory acceptance. No external provider/API is
  required or called by automated tests.

Exact setup, launcher, and single `ssh -L` commands are in
`docs/live_ui_usage.md` and `docs/browser_media_runtime.md`.

## Formal five-turn acceptance evidence

Five confirmation/final pairs completed without restarting the formal app:

1. right-corner explanation: `pdf_semantic_block_4` ->
   `pdf_semantic_block_6`, corrected, `step_by_step`;
2. “Thank you”: `pdf_semantic_block_5` -> `whole_slide`, corrected, `review`;
3. “Simplify this cost”: `pdf_semantic_block_4` retained, `review`;
4. “Explain this in Chinese”: `pdf_semantic_block_4` ->
   `pdf_semantic_block_10`, corrected, `simplify`;
5. “This confusing”: `pdf_semantic_block_4` retained, `simplify`.

JSONL grew from one excluded pre-fix diagnostic record to 14 records: five
pending/final pairs plus two earlier unfinished attempts and one ambient-noise
pending turn after the five completed turns. Final Master OFF reported
controller `stopped`, ingress inactive/disarmed, source not running, both queues
zero, zero drops/overruns, and cleanup state `stopped: master switch off`; the
removed iframe released browser tracks through pagehide.

Acceptance also exposed real usability limits: room audio/STT produced several
inaccurate transcripts and one spurious Russian pending transcript, and the
original internal-only AOI labels were not actionable. Numbered text-backed
choices address the latter; STT accuracy and dense overlapping AOIs remain
follow-up UX/model-quality work rather than transport regressions.

## Remaining release work

1. run compileall, full unittest discovery, demo loop, both evaluations, and
   `git diff --check` after the final AOI/OFF regression fix;
2. inspect the workspace, excluding `data/live_decks/` and `data/models/`;
3. create one scoped commit and push only
   `codex/live-system-integration-v1`.

Do not claim the standalone fallback as the live tutor acceptance, and do not
resume WebRTC/ICE/STUN/TURN investigation.
