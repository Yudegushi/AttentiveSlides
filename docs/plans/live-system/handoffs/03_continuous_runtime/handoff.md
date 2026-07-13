# Continuous Runtime Handoff

Status: complete
Branch: codex/live-system-integration-v1
Scope: Checkpoints 4–5
Start commit: 9ccd5f3
Checkpoint 4 commit: e4fc28e (feat: add continuous speech turn detection)
End feature commit: 8fc4caa (feat: orchestrate live runtime lifecycle)

## Delivered

- Checkpoint 4: bounded AudioRingBuffer; injectable WebRTC-compatible VAD protocol with optional WebRTC adapter and local energy fallback; fixed 16k PCM VoiceTurnDetector with 300ms pre-roll, 150ms start, 800ms end silence, 300ms minimum, 20s cap, cancel and explicit overrun degradation; AudioWorker normalizes browser PCM, anchors source clocks to worker monotonic time, writes temporary WAV only for STT, deletes it, and exposes recoverable STT errors.
- Checkpoint 5: SystemController owns media/sensing/audio lifecycle and RuntimeState transitions. It freezes deck/slide/AOI-manifest identity at speech start, uses start-time slide on navigation, applies busy-ignore policy during processing/confirmation, and resumes the existing confirmation gate without recomputing context.
- TurnContextCollector aggregates only valid, matching-manifest snapshots by confidence × bounded dwell; ties are AOI-ID deterministic; stale/invalid/legacy snapshots downgrade to no target. SensingWorker writes optional manifest_identity while existing stale/window APIs remain compatible.
- LiveTurnRunner reuses build_pipeline_input_bundle() and run_interaction_from_bundle() (which invokes run_interaction()) plus existing tutor/logging logic. No Member dataclass enters canonical pipeline.

## State and lifecycle

STOPPED → STARTING → MONITORING → SPEECH_ACTIVE → FINALIZING_AUDIO → PROCESSING_TURN → WAITING_CONFIRMATION or MONITORING. start()/stop() and disconnect cleanup are idempotent. One active turn only; later speech while busy is discarded with busy_turn_count. STT failure returns MONITORING; disconnect follows ERROR → STOPPED.

## Verification evidence

All commands ran via AutoDL in /root/autodl-tmp/workspace/AttentiveSlides-live-system.

- C4 baseline: unittest media/audio targeted suite — PASS, 27 tests.
- C4 targeted: unittest media/audio/new tests — PASS, 45 tests.
- C4 full: unittest discover -s tests -v — PASS, 206 tests.
- C5 targeted: unittest browser/media/audio/sensing/context/runner/controller/E2E/system suites — PASS, 56 tests.
- C5 full: unittest discover -s tests -v — PASS, 216 tests.
- Deterministic E2E: dynamic real PDF + synthetic snapshot + synthetic PCM + mock transcriber/template tutor → pending confirmation → correction → JSONL → MONITORING — PASS.
- git diff --check before both feature commits: no output.

## Risks and manual acceptance

- webrtcvad is not installed on AutoDL; the deterministic energy fallback is used unless the optional backend is installed. Real faster-whisper/model performance is not verified.
- Browser live/camera/microphone acceptance: not verified; no permission was requested.

Shortest manual smoke (not run): start the existing same-origin fallback, instantiate loaded RealSlideProvider, SensingWorker, AudioWorker and SystemController, call set_slide()/start(), grant browser media, speak one short deictic request, confirm the target, then switch OFF and verify STOPPED with empty queues.

## Next conversation must read

e4fc28e and this end commit; modules/system/controller.py, live_turn_runner.py, turn_context.py, runtime_state.py, audio_worker.py; modules/audio/voice_turn_detector.py; modules/system/sensing_snapshot_store.py and sensing_worker.py; tests/test_live_integrated_turn.py, test_system_controller.py, test_live_turn_runner.py, test_turn_context.py.

## Workspace state

Final status, processes, and push state are recorded after the end commit. Push: not pushed. No merge, PR, reset, clean, or main change.
