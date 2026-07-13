# Foundation and Browser Media Handoff

Status: complete
Branch: codex/live-system-integration-v1
Start commit: 5859d8add528e08b4db62b63bab88a7683db5b55
End commit: 52edebb6ec74148fb9e3cd0e7fb9d84cf8ef0cec
Scope: Checkpoints 0–1

## Checkpoint commits

- Checkpoint 0 — AutoDL preflight and safe branch:
  9d653ed (chore: audit AutoDL integration baseline).
- Checkpoint 1 — browser video/audio transport:
  52edebb (feat: add browser media transport).
- This handoff is committed immediately after the feature commit as a documentation
  record; it deliberately references the immutable feature SHA above.

## Delivered

### Checkpoint 0

- Preserved the shared branch and existing user changes; no main merge, reset, clean,
  destructive checkout, torch upgrade, or CUDA build upgrade occurred.
- Audited AutoDL Git state, Python/conda, GPU/CUDA, disk, dependencies, baseline
  tests, demo, and reference/scene evaluations.
- Recorded that PROJECT_PROGRESS.md and legacy audio documents describe the obsolete
  LenovoLinux_Dorm environment; this stage used AutoDL.

### Checkpoint 1

- Added a transport-only Streamlit WebRTC probe:
  apps/media_transport_probe.py.
- Added a selected single-origin, single-port HTTP fallback:
  apps/single_port_media_fallback.py and
  modules/media/single_port_transport.py.
- Added the reusable media contract:
  modules/media/media_packets.py,
  modules/media/queue_policy.py, and
  modules/media/browser_media_source.py.
- Added synthetic media tests:
  tests/test_browser_media_source.py,
  tests/test_media_queue_policy.py,
  tests/test_media_transport_probe.py, and
  tests/test_single_port_transport.py.
- Added dependency/runtime documentation:
  requirements-media.txt and docs/browser_media_runtime.md.

## Public media interface

BrowserMediaSource provides idempotent start(), stop(reason=...), video_queue,
audio_queue, handle_disconnect(), handle_component_error(), accept_video_frame(),
and accept_audio_samples().

- VideoPacket: immutable contiguous BGR uint8 ndarray with shape
  (height, width, 3). Fallback input is bounded JPEG, browser-limited to about
  five frames per second and server-limited to 320×240.
- AudioPacket: immutable interleaved int16 PCM with shape (samples, 1), 16 kHz
  mono in the fallback.
- Fallback timestamps share browser performance.now()/1000 and are labelled
  browser_performance_seconds. WebRTC packets retain media time when PyAV
  provides it, otherwise use process-monotonic time.
- Default video queue retains three newest packets. Audio retains at most 100
  chunks and 4 MiB. BoundedMediaQueue exposes push(), get_nowait(), qsize(),
  empty(), clear(), current_bytes, accepted_count, last_timestamp, dropped_count,
  and overrun_count.

Media callbacks and HTTP ingestion only decode/convert, attach timestamps, and
perform non-blocking bounded enqueue. They run no sensing, VAD, Whisper, LLM,
Streamlit calls, or raw-media persistence.

## Transport decision and deviations

- Primary streamlit-webrtc was implemented and tested first. In the real AutoDL
  plus single SSH TCP forward smoke, camera and microphone permission succeeded,
  but the component never reached playing after 30 seconds; FPS, audio chunks,
  and queues remained zero. This is reproducible ICE/RTP transport-gate failure,
  not a camera permission or queue bug.
- The selected AutoDL path is the same-origin HTTP fallback. The page captures
  both browser tracks, uploads JPEG and 16 kHz mono PCM using relative
  /media/* paths, and reuses the same BrowserMediaSource queue contract.
- Browser master OFF posts /media/stop. Page hide sends a stop beacon. A
  two-second server watchdog stops inactive sessions. A new session replaces an
  old one; stale sessions cannot enqueue or stop the active session.
- Remote port 8501 was already occupied by an unrelated original-worktree
  Streamlit process and was not touched. The isolated probe used remote 8502
  with the single local forward:

~~~bash
ssh -N -L 8501:127.0.0.1:8502 AutoDL
~~~

The browser still used only http://localhost:8501.

## Environment and dependencies

- AutoDL conda environment: /root/miniconda3/envs/attentive-app, Python 3.10.20.
- GPU: Tesla V100S-PCIE-32GB. torch remained 2.7.1+cu118 with CUDA build 11.8.
- Streamlit 1.59.1; streamlit-webrtc 0.75.0; aiortc 1.14.0; av 16.1.0;
  aiohttp 3.14.1; OpenCV 4.13.0.92.
- No raw video/audio file was created.

Launch the selected fallback from the isolated worktree:

~~~bash
/root/miniconda3/envs/attentive-app/bin/python +  apps/single_port_media_fallback.py --host 127.0.0.1 --port 8501
~~~

Use port 8502 plus the mapped local 8501 command above only while the unrelated
8501 process continues to occupy the remote port.

## Verification evidence

Automated, all executed on AutoDL after the fallback implementation:

- Focused:

~~~bash
/root/miniconda3/envs/attentive-app/bin/python -m unittest +  tests.test_single_port_transport +  tests.test_browser_media_source +  tests.test_media_queue_policy -v
~~~

Result: PASS, 20 tests.

- Full regression:

~~~bash
/root/miniconda3/envs/attentive-app/bin/python -m compileall -q +  apps/single_port_media_fallback.py modules/media
/root/miniconda3/envs/attentive-app/bin/python -m pip check
/root/miniconda3/envs/attentive-app/bin/python -m unittest discover -s tests -v
git diff --check
~~~

Result: compile PASS; pip check reported no broken requirements; 176 tests passed;
diff check had no output. Existing bare-Streamlit runtime/deprecation warnings were
emitted by unrelated UI tests but did not produce test failures.

Manual real-browser evidence through the single local SSH forward:

- WebRTC failure evidence: browser camera and microphone opened, but after 30
  seconds it stayed in negotiation with zero FPS, zero audio chunks, and zero
  queues.
- Fallback ON: user measured about 4.06 video FPS and 11.48 audio chunks/s,
  with running source, non-zero timestamps, and bounded depths of 3 video /
  100 audio.
- OFF: user measured active_session false, is_running false, both queue depths
  zero, and cleanup_state "stopped: browser stopped".
- Refresh while ON: user observed automatic cleanup_state
  "stopped: browser stopped".
- Three-minute acceptance: user explicitly confirmed ON for at least three
  minutes. Video depth stayed 3; audio grew to 100 then remained bounded.
  Drops and audio overruns remained visible as designed.

## Known issues and risks

- This checkpoint intentionally has no consumer worker. Therefore queues will fill
  and report drops/overruns while monitoring runs; Checkpoint 2 must consume video
  packets promptly, and the later audio/VAD checkpoint must consume audio without
  treating accumulated chunks as an unbounded recording.
- WebRTC remains a diagnostic probe but is not the selected AutoDL transport
  without TURN/ICE infrastructure.
- The fallback uses ScriptProcessor for broad browser compatibility. It is adequate
  for this probe; a future implementation may move capture to AudioWorklet without
  changing the packet contract.
- The fallback process and local SSH tunnel used for smoke were stopped at stage
  close. Temporary text logs may remain at
  /tmp/attentive_media_probe_8502.log and
  /tmp/attentive_single_port_fallback_8502.log. They contain no raw media.
- Ignored baseline runtime output data/logs/demo_interactions.jsonl may remain.

## Next conversation must read

Read this handoff, Checkpoint 1 commit 52edebb, and only the next-stage documents
required by the global contract:

1. docs/plans/live-system/00_global_contract.md;
2. docs/plans/live-system/02_slide_sensing.md;
3. modules/media/browser_media_source.py;
4. modules/media/media_packets.py;
5. modules/media/queue_policy.py;
6. modules/media/single_port_transport.py;
7. docs/browser_media_runtime.md;
8. tests/test_single_port_transport.py and tests/test_browser_media_source.py.

Do not begin continuous audio/VAD, tutor orchestration, or product UI work in the
next conversation. Checkpoint 2–3 must preserve this media contract and the
selected same-origin fallback.

## Workspace state

- Branch: codex/live-system-integration-v1.
- Remote smoke fallback PID 10270 was stopped at stage close; no raw media worker
  remains from this stage.
- The only planned new temporary artifacts are the two /tmp text logs and the
  ignored demo JSONL named above.
- Push: not pushed. No merge or pull request was created.
