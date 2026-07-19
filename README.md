# AttentiveSlides

AttentiveSlides is a human-centered AI learning assistant for slide-based
study. It combines uploaded PDFs, explicit text or voice intent, coarse gaze
evidence, user confirmation, and a source-grounded tutor to support natural
questions such as "explain this."

The production interface is `apps/streamlit_attentive_slides.py`. Start it on
the 4060 through the one-port launcher:

```bash
/home/charles/miniconda3/bin/conda run -n pyboe \
  python scripts/run_live_single_port.py \
  --host 127.0.0.1 \
  --port 8501
```

Then forward the public port when remote access is required:

```bash
ssh -N -L 8501:127.0.0.1:8501 LenovoLinux_Dorm
```

The application supports Manual and Live study, PDF/AOI processing, typed and
voice intent, confirmation-gated gaze targeting, grounded tutoring, XAI,
persistent realtime voice, learner-state status, and Study Review with gaze
heatmaps.

See [SYSTEM_FEATURES.md](SYSTEM_FEATURES.md) for the canonical module-level
feature inventory, architecture, privacy boundaries, model dependencies, and
current validation limits. A complete public-facing README can be derived from
that document without relying on historical progress or execution plans.

## Claim boundary

AttentiveSlides does not claim clinical or psychological diagnosis,
research-grade eye tracking, or ground-truth emotion, cognition, attention, or
comprehension. Gaze and learner-state estimates are uncertain interface
signals. Learners retain explicit target confirmation and correction control.

## Current acceptance boundary

The latest code has automated regression coverage, but browser hardware,
microphone/speaker, concurrent GPU-model, real-provider, and participant-level
accuracy acceptance remain separate physical-environment evaluation tasks.
