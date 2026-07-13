# AttentiveSlides project progress

This is the current engineering snapshot. Completed planning documents live in
[docs/archive/completed-plans](docs/archive/completed-plans/README.md).

## Execution environment

- Primary execution environment: `LenovoLinux_Dorm`.
- Repository: `/home/charles/repos/AttentiveSlides`.
- Conda environment: `pyboe` (Python 3.10.20).
- GPU: NVIDIA RTX 4060 Laptop GPU.

## Verified system capabilities

- The adapter-backed interaction pipeline combines a transcript, mock gaze, AOI manifest,
  and learning-state signals into `InteractionResult`.
- Ambiguous AOI references remain confirmation-gated: the system hides the final
  AOI-specific tutor answer until the user confirms or corrects the target.
- The Streamlit demo supports editable text plus file-based audio transcription,
  then reuses the same AOI confirmation and tutor response flow.
- File-based STT supports mock transcriptions and lazy faster-whisper on CUDA. Current
  profiles use English by default; `fast` is the interactive demo default.
- Project-specific audio evaluation uses a reviewed CSV manifest and records transcript
  usability, CER, semantic agreement, and latency without committing private recordings.

## Latest verified audio result

On the reviewed 10 English recordings on the 4060:

| Profile | Semantic metrics | Mean end-to-end latency |
|---|---:|---:|
| `fast` | 1.000 | 348.4 ms |
| `balanced` | 1.000 | 476.8 ms |

`fast` is the recommended demo default. Full evidence and merge gates are in
[docs/audio_merge_readiness.md](docs/audio_merge_readiness.md).

## Current documentation

- [Audio deployment](docs/audio_deployment.md): file-based STT setup and 4060 commands.
- [Audio usability evaluation](docs/audio_usability_eval.md): reviewed-manifest workflow.
- [Audio merge readiness](docs/audio_merge_readiness.md): verification evidence and merge
  checklist.
- [Completed planning archive](docs/archive/completed-plans/README.md): historical plans.

## Deferred system-design work

Continuous/background microphone monitoring, voice activity detection, speech-end
decisioning, automatic turn submission, and automatic lecture start are intentionally not
implemented in the file-based audio module. They must be designed as a future system-level
feature that combines audio events with gaze/AOI confirmation.

## Continuous live release (Checkpoints 6–7)

The AutoDL worktree now includes the continuous controller, a Streamlit live
surface, and an optional grounded tutor mode without duplicating the canonical
pipeline. The default is deterministic; the UI enables the existing grounded
tutor only when the user opts in and configuration is available.

- LiveViewModel keeps Streamlit reruns at the controller-command boundary.
- LiveTelemetryLogger adds safe grounded provider/model/validation metadata
  to existing JSONL interaction events; it does not store raw media or raw
  provider payloads.
- Automated verification on AutoDL passed 227 tests, compilation, the
  deterministic demo, and both eight-scenario evaluations.
- Browser manual status is partial: the live UI opened through an SSH tunnel,
  and the same-origin fallback captured camera/microphone and cleaned queues;
  the controlled browser could not inject the required PDF file, so the real
  live deictic/confirmation/JSONL path remains outstanding.

See [Live UI usage](docs/live_ui_usage.md),
[continuous interaction design](docs/continuous_interaction_design.md), and
the [live release handoff](docs/plans/live-system/handoffs/04_live_release/handoff.md).
