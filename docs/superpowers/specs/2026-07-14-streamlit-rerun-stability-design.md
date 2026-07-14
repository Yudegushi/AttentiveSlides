# Streamlit Rerun Stability Design

## Problem

The official UI visibly fades because two independent mechanisms rerender visible content:

1. The slide viewport component reports geometry on every render, scroll, resize, and `ResizeObserver` callback. Every `streamlit:setComponentValue` starts a full Streamlit rerun. The component increments `layout_revision` before every report, so unchanged geometry is never deduplicated.
2. Live mode installs a `run_every=0.5` fragment even while camera/microphone are disabled. That continually rerenders an idle interaction panel.

The HTTP proxy, Streamlit service, and ingress remain healthy during the symptom. This is a client/UI rerun problem, not a reconnect or backend restart.

## Considered approaches

### A. Deduplicate geometry and gate polling — selected

Keep browser-coordinate geometry, but compute a stable geometry signature. Send a component value only when that signature changes. Debounce parent scroll/resize reporting so one settled change produces one report. Run periodic proposal polling only while Live media is enabled; render the same Live panel once when disabled.

This preserves the integration contract and removes the two unnecessary rerun sources with no dependency or architecture change.

### B. Remove parent viewport reporting

This would eliminate scroll reruns, but would also discard the browser-coordinate AOI contract needed for future point-gaze work. Rejected.

### C. Only increase timers

Increasing the fragment interval or adding a scroll throttle without deduplication would make fading less frequent but retain the feedback loop. Rejected as symptom treatment.

## Component behavior

- Maintain `lastReportedSignature` in the component.
- The signature includes deck/slide IDs, viewport size, slide rect, AOI rects, device pixel ratio, and manual bbox, rounded to stable CSS-pixel precision.
- `layout_revision` increments only immediately before sending a geometry value whose signature differs from the last sent value.
- Initial image load sends one value.
- Parent scroll and resize callbacks use a trailing 180 ms debounce. `ResizeObserver` uses the same path.
- A Streamlit render with identical arguments/geometry does not create another component value.
- Manual rectangle completion remains immediate and always changes the signature.

## Live polling behavior

- Keep `_render_live_periodic` as the only 0.5-second proposal poller.
- Call it only when `main_live_master_enabled` is true.
- When Live mode is selected but media is off, call the non-fragment `_render_live_interaction` once. No proposal can arrive while the runtime is stopped, so polling would provide no value.
- Do not change speech/gaze proposal latency while media is enabled.

## Testing and acceptance

- Static component contract tests require signature deduplication and debounced geometry listeners, and reject unconditional revision increments before deduplication.
- Main UI source tests require the periodic fragment to be gated by `main_live_master_enabled` and the disabled path to render once without calling the fragment.
- Existing geometry, component, Main UI, launcher, ingress, and proposal tests remain green.
- Browser acceptance verifies that an idle Manual page and Live-with-media-off page settle without a persistent Running state; enabling media continues to reach `Media: ready` and receives speech proposals.

## Scope

No change to the single-port proxy, media lifecycle, STT, gaze algorithm, session architecture, or LLM path. No new dependency.
