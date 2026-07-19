# AttentiveSlides

AttentiveSlides is a human-centered AI learning assistant for slide-based
study. It combines uploaded PDFs, explicit text or voice intent, coarse gaze
evidence, user confirmation, and a source-grounded tutor to support natural
questions such as "explain this."

The production interface is `apps/streamlit_attentive_slides.py`. Start it on
the 4060 from the verified `pyboe` environment. The canonical dependency file
also documents each model and its external artifact boundary:

```bash
/home/charles/miniconda3/bin/conda run -n pyboe \
  python -m pip install -r requirements.txt
```

Then run the one-port launcher:

```bash
/home/charles/miniconda3/bin/conda run -n pyboe \
  python scripts/run_live_single_port.py \
  --host 127.0.0.1 \
  --port 8501
```

Then forward the AttentiveSlides public port and the separate EyeTheia
loopback port when remote browser access needs local point gaze:

```bash
ssh -N \
  -L 8501:127.0.0.1:8501 \
  -L 8001:127.0.0.1:8001 \
  LenovoLinux_Dorm
```

Port 8501 contains the Streamlit, media-ingress, voice, and preview routes.
Port 8001 is not part of that application proxy: browser JavaScript connects
to `ws://127.0.0.1:8001/ws/predict_gaze`, so the second tunnel is required
when EyeTheia runs on the Lenovo host. Without it, the UI remains usable and
point gaze degrades to the configured grid/manual targeting path.

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
