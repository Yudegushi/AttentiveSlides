# Live UI Usage

## Purpose

`apps/streamlit_live.py` is the Streamlit surface for the existing continuous
runtime. The UI owns only session/resource reuse and controller commands. VAD,
STT, sensing, frozen-turn aggregation, canonical reference resolution, tutor
generation, and JSONL logging remain outside the UI.

The view shows the loaded PDF, a canonical AOI overlay, browser transport state,
runtime state, coarse gaze evidence, transcript/timing, confirmation candidates,
tutor response, and an optional developer trace. Gaze is presented only as
coarse AOI evidence; observable face signals are not claims about attention,
emotion, cognition, confusion, or fatigue.

## AutoDL setup

Use the existing application environment; do not use the SSH shell's missing
`python` alias.

```bash
cd /root/autodl-tmp/workspace/AttentiveSlides-live-system
/root/miniconda3/envs/attentive-app/bin/python -m streamlit run   apps/streamlit_live.py --server.address 127.0.0.1 --server.port 8501
```

On the browser machine, forward the same server port:

```bash
ssh -N -L 8501:127.0.0.1:8501 AutoDL
```

Open <http://localhost:8501>, upload a real PDF, select its slide, then enable
the **Master switch** and grant camera/microphone permission. The controller
starts only after the browser component reports both tracks playing. Switch OFF,
a disconnect, reload, or component failure stops the controller and clears
workers/queues through the existing idempotent lifecycle.

## Interaction behaviour

1. Speak a short deictic request such as “explain this”.
2. The audio worker detects the speech end, transcribes it, and the controller
   freezes the start-time slide/AOI context.
3. A high-confidence target yields a tutor response. An uncertain target shows
   confirmation candidates instead; no AOI-specific final answer is generated
   until the user selects one.
4. Selecting a different candidate is routed to
   `SystemController.confirm(query_id, confirmed_aoi_id)`; the canonical
   pipeline records it as a correction, which overrides the predicted target.
5. Use the developer trace only for queue/drop/cleanup diagnosis. It contains no
   raw media, secrets, raw provider payloads, or hidden reasoning.

The existing `apps/streamlit_demo.py` and
`apps/streamlit_grounded_xai.py` remain the explicit manual-transcript and
grounded-XAI regression surfaces.

## AutoDL transport limitation

The selected AutoDL same-origin media fallback remains
`apps/single_port_media_fallback.py`: previous SSH TCP forwarding could load
the page and request permissions but did not reach WebRTC playing. That fallback
proves bounded browser transport and cleanup over one forwarded HTTP port; it is
not a substitute for the live tutor UI. Record the transport used and whether
the WebRTC live flow reached playing in each manual acceptance run rather than
claiming that the fallback completed the tutor interaction.

## Automated checks

Automated tests use fakes or synthetic packets only. They do not request a
camera/microphone and do not call a real STT or LLM provider.

```bash
/root/miniconda3/envs/attentive-app/bin/python -m unittest   tests.test_live_view_model tests.test_streamlit_live   tests.test_system_controller tests.test_live_turn_runner -v
```

## Grounded tutor and logging

The **Use grounded API tutor** switch starts in deterministic mode. Enabling it
lazily constructs the existing GroundedTutorAgent; unavailable configuration
or recoverable provider failure retains deterministic behavior. The interface
shows only the sanitized grounded XAI view. Each completed canonical event is
written through LiveTelemetryLogger to data/logs/live_interactions.jsonl with
safe provider/model/usage, AOI, context-source, validation, and fallback
metadata. It never writes raw media, prompts, request identifiers, or provider
payloads.

## 2026-07-13 manual status

On the retry, Chrome file-URL access was enabled and the standard file chooser
loaded the valid two-page `attentiveslides-manual-acceptance.pdf` into the live
page.

Commit `383f393` replaces the React-Aria `st.toggle` Master switch with a
standard Streamlit button backed by session state. The controlled page rendered
the `Stop live runtime` state across the deck-upload rerun.

Over the loopback SSH forwarding route, `streamlit-webrtc` received an SDP
answer and emitted ICE candidates, then repeatedly changed from `connecting`
