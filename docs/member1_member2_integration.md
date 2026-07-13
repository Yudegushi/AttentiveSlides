# Member 1/2 Integration Boundary

## Canonical flow

The live release does not introduce a second interaction or LLM path. Every
completed live turn is converted by `LiveTurnRunner` into the existing
`PipelineInputBundle`, then executed by the canonical
`run_interaction_from_bundle` flow:

```text
BrowserMediaSource -> workers -> TurnContextCollector -> LiveTurnRunner
  -> canonical intent / reference / confirmation / tutor / logger pipeline
```

`SystemController` owns the single active turn, frozen start-time context,
confirmation resume, and idempotent cleanup. The UI only issues controller
commands and polls rendering-safe state. Media callbacks only convert,
timestamp, and enqueue packets; they never run VAD, STT, sensing, LLM, or
Streamlit work.

## Tutor boundary

The default live tutor is the deterministic `TutorAgent`. A user may opt in
to the grounded path from the live UI. `LiveTutorAdapter` lazily creates the
existing `GroundedTutorAgent`, which continues to use
`OpenAICompatibleLLMClient`, the current request adapter, prompt builder,
parser, validator, and fallback behavior. It returns the compatible legacy
`TutorResponse` to the canonical pipeline and exposes only the sanitized
XAI view to the UI.

Missing configuration or a recoverable provider error keeps or returns the
turn to deterministic behavior. The adapter never exposes raw provider
responses, prompts, request identifiers, secrets, or hidden reasoning.

## Confirmation and logs

A pending `confirm_one`, `choose_top2`, or `click_required` result
continues to gate AOI-specific tutor generation. A correction calls
`SystemController.confirm(query_id, confirmed_aoi_id)`; the confirmed AOI
therefore replaces the prediction before the canonical tutor call.

`LiveTelemetryLogger` wraps the existing `InteractionLogger`. It preserves
canonical JSONL fields and adds safe provider/model/latency/usage, resolved and
confirmed AOI, context-source IDs, validation, and fallback telemetry. No raw
media or raw provider payload is persisted.
