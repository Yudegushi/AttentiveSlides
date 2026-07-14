# AttentiveSlides

AttentiveSlides is a human-centered AI slide learning assistant. The system uses coarse webcam-based gaze/head-pose signals as implicit visual reference, voice or text input as explicit learning intent, and a slide-grounded tutor loop to answer questions such as "解释这个" or "explain this" without requiring the learner to manually describe the slide region.

This repository currently starts from the planning documents in:

- `attentive_slides_project_plan_initial.md`
- `division.md`
- `member3_4_first_step_plan.md`

## Project Claim

The project is not a generic slide QA tool and should not claim accurate emotion, cognition, or pixel-level eye tracking. The core claim is:

> We design and evaluate a low-cost gaze-and-voice interaction loop for slide-based AI tutoring, with explicit uncertainty display and user correction.

## First Milestone

The first implementation milestone is a deterministic, mock-driven pipeline for Member 3 and Member 4:

```text
Mock Slide / AOI
+ Mock GazePrediction
+ Mock LearningState
+ Text Transcript
-> IntentResult
-> ResolvedQuery
-> TutorContext
-> TutorResponse
-> InteractionLog
```

This milestone intentionally excludes real webcam capture, real speech-to-text, real slide parsing, full UI, and real LLM API requirements. Those components can replace mock inputs after the contracts are stable.

## Initial Work Plan

1. Define stable dataclasses in `modules/common/schemas.py`.
2. Implement Member 3 logic:
   - `modules/interaction/intent_parser.py`
   - `modules/interaction/reference_resolver.py`
   - `modules/interaction/adaptive_policy.py`
   - `modules/interaction/interaction_history.py`
3. Implement Member 4 logic:
   - `modules/tutor/context_retriever.py`
   - `modules/tutor/prompt_template.py`
   - `modules/tutor/llm_tutor.py`
   - `modules/tutor/tutor_agent.py`
   - `modules/logging/interaction_logger.py`
4. Add `scripts/demo_tutor_loop.py` with five fixed demo cases from `member3_4_first_step_plan.md`.
5. Add focused tests for parsing, reference resolution, context retrieval, and tutor response behavior.

## Repository Layout

```text
modules/
  common/
  interaction/
  tutor/
  logging/
data/
  mock_deck/
  logs/
scripts/
tests/
evaluation/
```

## Development Notes

- Keep AOI bounding boxes normalized as `[x1, y1, x2, y2]`.
- Keep uncertainty explicit: use `confirm_one`, `choose_top2`, or `click_required` instead of silently assuming the target.
- Tutor responses must be grounded in provided slide context.
- Adaptive policy may respond to observable learning-state signals, but should not claim true emotion, fatigue, confusion, or attention.
- The first stage can be developed on this Mac. Later webcam, gaze calibration, Whisper, and final demo work should be validated on the configured 4060 Linux laptop.

## Current Verification Commands

```bash
python -m unittest discover -s tests -v
python scripts/demo_tutor_loop.py
```

## Official Manual + Live UI

`apps/streamlit_attentive_slides.py` is the production UI. Manual mode keeps
the uploaded-deck workflow; Live mode adds browser camera/microphone capture,
VAD/STT, and coarse 3×3 viewport gaze targeting. The user confirms or corrects
the proposed target before the same grounded Main Tutor path runs. Optional
confidence-based auto-confirm must be selected explicitly.

On AutoDL, start the one-port launcher with the attentive-app interpreter:

    /root/miniconda3/envs/attentive-app/bin/python \
      scripts/run_live_single_port.py --host 127.0.0.1 --port 8501
    ssh -N -L 8501:127.0.0.1:8501 AutoDL

`apps/streamlit_live.py` remains available only as a runtime diagnostic via
`--streamlit-app apps/streamlit_live.py`.

For the browser transport fallback and its limitation, see
[docs/browser_media_runtime.md](docs/browser_media_runtime.md). For live UI
steps and the current manual-acceptance status, see
[docs/live_ui_usage.md](docs/live_ui_usage.md).
