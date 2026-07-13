# Continuous Interaction Design

## Runtime ownership

`SystemController` is the lifecycle boundary. It starts and stops the media
source and workers idempotently, prevents a second active speech turn, freezes
the start-time slide and sensing context, and resumes a pending confirmation
using that frozen bundle. `LiveViewModel` does not create duplicate workers
on Streamlit reruns; it only requests start/stop, slide changes, confirmation,
or grounded-tutor selection.

## Turn sequence

```text
browser callback -> bounded BrowserMediaSource queue
  -> SensingWorker / AudioWorker
  -> turn start freezes slide and context window
  -> LiveTurnRunner builds PipelineInputBundle
  -> canonical resolver may return a pending confirmation
  -> SystemController.confirm resumes the same frozen bundle
  -> canonical tutor and JSONL logger complete the turn
```

The runner does not recreate reference resolution, tutor prompts, or provider
clients. It carries only transcript and timing metadata around the canonical
pipeline.

## Degradation and safety

- Stale or invalid sensing evidence downgrades to an explicit uncertain target.
- Audio overrun or STT failure yields a recoverable result and returns to
  monitoring without calling the tutor.
- Bounded queues retain recent data and release queued packets on stop,
  disconnect, component error, or deck reload.
- The master switch, browser disconnect, and component failure all converge on
  the same idempotent stop path.
- Gaze is displayed as coarse AOI evidence only; the UI makes no emotion,
  cognition, attention, or pixel-accurate eye-tracking claim.

## Release transport note

The Streamlit live UI uses `streamlit-webrtc` when browser WebRTC can play.
The same-origin single-port fallback is retained for AutoDL SSH TCP forwarding
because it proves camera/microphone packet transport and cleanup, but it is not
a substitute for the slide/tutor UI. Manual acceptance must record which
transport actually ran and must not claim a tutor interaction from fallback
alone.
