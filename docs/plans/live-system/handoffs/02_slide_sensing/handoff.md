# Slide and Sensing Handoff

Status: complete
Branch: codex/live-system-integration-v1
Scope: Checkpoints 2–3
Start commit: 2532838 (docs: finalize foundation media handoff)
End feature commit: ee3237e (feat: adapt live human sensing outputs)

## Delivered

### Checkpoint 2 — Real slide provider

Commit: 7b196ac (feat: add real slide provider).

- Added modules/system/real_slide_provider.py. Construct with
  RealSlideProvider(data_dir=...), then call
  load_deck(pdf_path_or_bytes, filename="uploaded_deck.pdf") to obtain the
  explicit deck_id before it is used by a deck store.
- The provider uses Member 1 SlideParser and AOIManager in one configurable
  data directory. It renders the requested PDF page, returns current text and
  adjacent-page text, and supports both a filesystem PDF and uploaded bytes.
- Canonical AOI selection prefers eligible pdf_text_semantic/OCR AOIs, filters
  footer and include_in_learning=False records, uses rule AOIs only when auto
  AOIs are unavailable, and appends whole_slide solely as the explicit fallback.
  AOI priority is deterministic: type priority, area, y/x position, then ID.
- ProviderBackedDeckStore now requires an explicit provider deck_id. Its former
  fixed get_slide_frame(5) probe was removed.
- Added tests/test_real_slide_provider.py. The tests build temporary PDFs and
  cover path/bytes input, one-, two-, and three-page boundaries, normalized
  deterministic AOIs, no fixed-slide deck lookup, and the existing confirmation
  gate.

### Checkpoint 3 — Canonical live sensing boundary

Commit: ee3237e (feat: adapt live human sensing outputs).

- Added HumanSensingAdapter in modules/system/human_sensing_adapter.py. Member 2
  AOIPrediction/LearningState are converted only at this boundary into canonical
  SensingFrame. Candidate scores become score-descending alternative_targets
  with AOI-ID tie breaking. no_face, unknown_grid, no_target, and low_confidence
  return no canonical target plus an explicit invalid reason.
- Added SensingSnapshot and SensingSnapshotStore in
  modules/system/sensing_snapshot_store.py. A snapshot records slide_id,
  source timestamp and clock label, processed_at (monotonic), canonical frame,
  validity, and invalid reason. APIs are snapshot(...), put(...),
  latest_valid_for_slide(...), snapshots_in_window(...), get_sensing_frame(...),
  and clear(). Default stale_after_seconds is 1.0. Latest queries reject stale,
  invalid, and slide-mismatched observations.
- Added SensingWorker in modules/system/sensing_worker.py. Call set_slide(id),
  then start()/stop(), or process_available_frame() for a single synthetic step.
  It drains BrowserMediaSource.video_queue and processes only the newest packet;
  it does not alter the BrowserMediaSource packet/queue contract and does not
  consume audio. whole_slide is excluded from Member 2 gaze competition.
- Default worker cadence is 0.1 seconds per inference with 0.02-second polling.
  FaceLandmarkExtractor, gaze estimator, face-state detector, and learning-state
  aggregator are initialized once per worker on first eligible frame. stop() and
  threaded errors release the extractor; errors remain visible in last_error.
  A slide change clears snapshots and rechecks the slide after inference, so an
  old-slide result cannot enter the new turn.
- Added tests/test_human_sensing_adapter.py,
  tests/test_sensing_snapshot_store.py, and tests/test_sensing_worker.py. They
  use Member 2 synthetic contracts and synthetic BrowserMediaSource frames only;
  no webcam, microphone, model API, or real browser media is requested.

## Decisions and deviations

- The Checkpoint 1 BrowserMediaSource public interface is unchanged. The worker
  reads its existing bounded video_queue through get_nowait() and drops any
  backlog by retaining only the latest packet.
- source_timestamp is intentionally preserved as supplied by the browser
  transport (for the fallback: browser_performance_seconds). Freshness uses the
  server monotonic processed_at clock, not the browser clock.
- Real slide tests create PDFs dynamically in temporary directories instead of
  committing a binary fixture. This covers the required page boundaries without
  sharing a production metadata manifest or requiring OCR/network resources.
- No Member 1 or Member 2 source algorithms were modified. The only preexisting
  adapter change removes the prohibited fixed-slide deck-ID inference.
- No VAD, STT, continuous turn runtime, tutor orchestration, product UI, real
  camera/microphone access, or live browser sensing integration was started.

## Verification evidence

All commands ran in /root/autodl-tmp/workspace/AttentiveSlides-live-system
through SSH host AutoDL.

- Preflight:
  git status --short --branch
  Result: clean on codex/live-system-integration-v1.

  git log --oneline --decorate -n 8
  Result: HEAD 2532838 before the work; Checkpoint 1 feature was 52edebb and
  baseline was 705f1a2.

  git fetch origin --prune
  Result: exit 0; no fetched-output errors.

- Checkpoint 2 baseline:
  /root/miniconda3/envs/attentive-app/bin/python -m unittest
  tests.test_system_adapters tests.test_system_pipeline -v
  Result: PASS, 14 tests.

- Checkpoint 2 targeted:
  /root/miniconda3/envs/attentive-app/bin/python -m unittest
  tests.test_real_slide_provider tests.test_system_adapters
  tests.test_system_pipeline -v
  Result: PASS, 19 tests.

- Checkpoint 2 full regression (run once):
  /root/miniconda3/envs/attentive-app/bin/python -m unittest discover -s tests -v
  Result: PASS, 181 tests. Existing bare-Streamlit context/deprecation warnings
  appeared but produced no failures.

- Checkpoint 3 baseline:
  /root/miniconda3/envs/attentive-app/bin/python -m unittest
  tests.test_browser_media_source tests.test_media_queue_policy
  tests.test_real_slide_provider -v
  Result: PASS, 19 tests.

- Checkpoint 3 targeted:
  /root/miniconda3/envs/attentive-app/bin/python -m unittest
  tests.test_human_sensing_adapter tests.test_sensing_snapshot_store
  tests.test_sensing_worker tests.test_browser_media_source
  tests.test_media_queue_policy tests.test_real_slide_provider
  tests.test_system_adapters tests.test_system_pipeline -v
  Result: PASS, 40 tests.

- Checkpoint 3 full regression (run once):
  /root/miniconda3/envs/attentive-app/bin/python -m unittest discover -s tests -v
  Result: PASS, 188 tests. The same existing bare-Streamlit context/deprecation
  warnings appeared without failures.

- Formatting:
  git diff --cached --check before both feature commits: no output.
  git diff --check after 7b196ac and after ee3237e: no output.

## Manual live-browser acceptance

Status: not verified.

No continuous runtime or browser product surface exists in Checkpoints 2–3, so
there is no in-scope UI that can bind a RealSlideProvider and SensingWorker
without beginning Checkpoint 4. No real camera or microphone permission was
requested.

Shortest future smoke, after the next conversation owns the runtime wiring:

1. Start the existing same-origin fallback from the isolated worktree with the
   attentive-app Python and a loopback port.
2. Bind a loaded RealSlideProvider, a SensingSnapshotStore, and a SensingWorker
   to that existing BrowserMediaSource; call worker.set_slide(current_slide_id)
   and worker.start().
3. Open the existing single SSH-forwarded localhost URL, grant media permission,
   switch capture ON, and observe changing source timestamps, canonical snapshot
   slide IDs, and bounded video depth; switch OFF and verify worker.stop().
4. Treat this only as lifecycle/update evidence, not gaze-accuracy validation.

## Known issues and risks

- The default real worker needs the installed MediaPipe backend and, for a
  Tasks-only installation, a configured face-landmarker task model. Synthetic
  tests inject all heavy dependencies and do not validate that environment.
- Browser fallback timestamps are browser-performance relative. They are retained
  for traceability; stale rejection relies on server monotonic processing time.
- Snapshots remain in-memory and bounded. A later runtime must set the current
  slide before starting the worker and must handle LookupError from
  get_sensing_frame as an explicit no-current-sensing downgrade.
- Manual browser/live-video lifecycle and coarse AOI update are not verified.
  No claim of gaze accuracy, emotion, cognition, or raw-media persistence is
  made here.

## Next conversation must read

1. Commits 7b196ac and ee3237e, plus the Checkpoint 1 transport commit 52edebb.
2. modules/system/real_slide_provider.py,
   modules/system/human_sensing_adapter.py,
   modules/system/sensing_snapshot_store.py, and
   modules/system/sensing_worker.py.
3. modules/media/browser_media_source.py, modules/media/media_packets.py, and
   modules/media/queue_policy.py.
4. tests/test_real_slide_provider.py, tests/test_human_sensing_adapter.py,
   tests/test_sensing_snapshot_store.py, tests/test_sensing_worker.py, and
   tests/test_browser_media_source.py.
5. docs/plans/live-system/03_continuous_runtime.md and this handoff.

## Workspace state

- Final feature HEAD before this handoff documentation commit: ee3237e.
- Branch: codex/live-system-integration-v1.
- Feature worktree was clean immediately after both feature commits.
- No media server, sensing worker, browser tunnel, camera, microphone, or other
  process was started by this conversation.
- Push: not pushed. No merge, pull request, reset, clean, or main-branch change
  occurred.
