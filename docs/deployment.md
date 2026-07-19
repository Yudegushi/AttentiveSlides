# Deployment Guide

The public [README](../README.md) contains the portable setup path. This guide
records the deployment details that are specific to the currently tested
Lenovo RTX 4060 environment and explains remote browser access with EyeTheia.

## Tested environment

The maintained deployment has been exercised with:

- Ubuntu Linux on the Lenovo RTX 4060 host;
- Python 3.10 in the Conda environment `pyboe`;
- PyTorch 2.5.1 with CUDA 12.1 wheels;
- the pinned dependency snapshot in [`requirements.txt`](../requirements.txt);
- AttentiveSlides bound to loopback port 8501; and
- EyeTheia available as a separate loopback WebSocket service on port 8001.

Other operating systems, GPU combinations, and Python versions have not been
validated by this repository.

## Advanced remote deployment

The active checkout on the 4060 is:

```text
/home/charles/repos/AttentiveSlides-eyetheia-local-gaze-integration
```

Install the pinned environment from that checkout when dependencies need to be
refreshed:

```bash
cd /home/charles/repos/AttentiveSlides-eyetheia-local-gaze-integration
/home/charles/miniconda3/bin/conda run -n pyboe \
  python -m pip install -r requirements.txt
```

Start the supported one-port launcher on loopback:

```bash
cd /home/charles/repos/AttentiveSlides-eyetheia-local-gaze-integration
/home/charles/miniconda3/bin/conda run -n pyboe \
  python scripts/run_live_single_port.py \
  --host 127.0.0.1 \
  --port 8501
```

The launcher keeps Streamlit on 8502 and media ingress on 8503 internally. It
publishes the application, browser media, voice WebSockets, and slide previews
through port 8501.

Start the separately managed EyeTheia service according to its
[upstream repository](https://github.com/patherstevenson/EyeTheia). The current
browser integration expects this endpoint on the 4060:

```text
ws://127.0.0.1:8001/ws/predict_gaze
```

From the client computer, forward both loopback ports:

```bash
ssh -N \
  -L 8501:127.0.0.1:8501 \
  -L 8001:127.0.0.1:8001 \
  LenovoLinux_Dorm
```

Then open <http://127.0.0.1:8501> in the client browser.

### Why two ports are required

Port 8501 is the AttentiveSlides public proxy. EyeTheia is deliberately not
routed through that proxy: browser JavaScript connects to
`ws://127.0.0.1:8001/ws/predict_gaze`. For a remote browser, the second SSH
tunnel makes its local port 8001 reach the EyeTheia service on the 4060.

If port 8001 is unavailable, AttentiveSlides remains usable. Point gaze becomes
unavailable and targeting falls back to the configured grid/manual path.

## 4060 model locations

The application runtime data defaults to:

```text
/home/charles/.local/share/attentive_slides
```

The maintained local model artifacts currently use:

```text
/home/charles/.local/share/attentiveslides/models/learner_state/emotieff/
/home/charles/.local/share/attentiveslides/models/fatigue/mobilevitv2/best_model.pt
```

The relevant overrides are:

```bash
export ATTENTIVE_EMOTIEFF_MODEL_PATH="/home/charles/.local/share/attentiveslides/models/learner_state/emotieff/enet_b0_8_best_vgaf_features.ts"
export ATTENTIVE_EMOTIEFF_ENGAGEMENT_PATH="/home/charles/.local/share/attentiveslides/models/learner_state/emotieff/engagement_single_attention.pt"
export ATTENTIVE_FATIGUE_MODEL_PATH="/home/charles/.local/share/attentiveslides/models/fatigue/mobilevitv2/best_model.pt"
```

These paths are deployment details, not portable defaults for other machines.

## Operational notes

- Keep application, EyeTheia, and internal service ports on loopback. Use SSH
  forwarding instead of exposing them directly to the network.
- Browser camera and microphone permissions are granted on the client machine.
- The browser loads MediaPipe Face Mesh from jsDelivr for the current Live
  capture component; restricted networks must allow that asset request.
- Configure provider credentials in the process environment. The application
  does not automatically load a `.env` file.
- Runtime PDFs, rendered pages, model artifacts, logs, audio caches, and Study
  Review data belong outside the Git checkout.
