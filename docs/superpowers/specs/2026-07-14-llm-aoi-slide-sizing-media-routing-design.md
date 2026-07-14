# LLM AOI, Adjustable Slide, and Media Routing Design

## Status and Delivery Context

This design is approved for planning on the existing AutoDL branch
`codex/ui-live-runtime-integration-v1`. The work will be implemented directly on
that branch; no additional feature branch or worktree is required.

The stage has three deliverables:

1. **Required fix:** restore Streamlit PDF thumbnails and other Streamlit media
   downloads through the single-port proxy.
2. **Required fix:** let the learner reduce or restore the displayed slide size
   without breaking AOI overlays, manual rectangles, or viewport geometry.
3. **Optional feature:** selectively integrate Member 1's latest LLM/VLM AOI
   extraction into the uploaded-PDF workflow while preserving every current
   deterministic AOI and runtime contract.

This is a course-project implementation. It should be demonstrable and robust
for a single-user session, but it must not grow into a distributed job system,
generic workflow engine, or production deployment platform.

## Audited Baselines

- AutoDL repository:
  `/root/autodl-tmp/workspace/AttentiveSlides-ui-live-integration`
- Delivery branch and audited HEAD:
  `codex/ui-live-runtime-integration-v1@63401f0`
- Member 1 source:
  `herry-sketch/AIAA3800HCAI`, branch `member1`, audited HEAD `263a604`
- Current app entrypoint: `apps/streamlit_attentive_slides.py`
- Current single-port launcher: `scripts/run_live_single_port.py`
- Current uploaded-deck storage:
  `/root/autodl-tmp/project_data/runtime/attentive_slides`
- One focused baseline run passed 40 tests covering the proxy, slide geometry,
  compact layout, uploaded deck service, and AOI manifest concurrency.

The Member 1 implementation adds useful LLM AOI behavior, but its files cannot
replace current files wholesale. It removes the current `RLock`, removes the
`allow_ocr` path, changes DPI-qualified image naming, does not preserve the UI's
required `whole_slide` control AOI, and does not integrate with the current
uploaded-deck cache or `RealSlideProvider` source filter.

## Selected Architecture

### 1. Preserve deterministic AOIs and store LLM AOIs as an optional variant

`AOIManager.process_slide(...)` remains the deterministic preparation path. It
continues to render the slide, extract PDF text, optionally use OCR, create the
existing rule/PDF/OCR AOIs, preserve `whole_slide`, and save the current top-level
`aois` payload.

Add a separate operation:

```python
AOIManager.process_llm_aoi(
    deck_id: str,
    slide_id: int,
    *,
    dpi: int = 250,
    allow_ocr: bool = True,
    force: bool = False,
) -> dict[str, Any]
```

This operation first ensures deterministic slide data exists, then sends the
complete rendered slide image plus deterministic PDF/OCR anchors to the Member 1
LLM/VLM generator. It validates and reconciles the result, but stores the result
under a separate `llm_aois` field instead of overwriting top-level `aois`.

The manifest record remains backward compatible and gains bounded metadata:

```json
{
  "aois": ["existing deterministic AOIs"],
  "llm_aois": ["validated LLM-guided AOIs"],
  "llm_aoi_status": "not_requested | used | fallback_used",
  "llm_aoi_model": "configured model name",
  "llm_aoi_profile": "non-secret profile fingerprint",
  "llm_aoi_error": "sanitized failure text or null"
}
```

`llm_aoi_profile` is a non-secret fingerprint of the model name, prompt/schema
version, maximum image side, and deterministic-anchor digest. A cached result is
eligible only when that fingerprint still matches. A changed anchor digest marks
the old LLM variant stale instead of serving AOIs grounded against different text
boxes.

API keys and authorization headers are never persisted or displayed. The UI
selects `llm_aois` only when the user enabled LLM AOI and the status is `used`.
Otherwise it continues to select deterministic `aois`. `whole_slide` is appended
to the selected effective set if it is not already present.

This separation provides three guarantees:

- unchecking LLM AOI immediately returns to the existing deterministic result;
- an API timeout or malformed result cannot destroy a valid deterministic AOI;
- repeated page navigation loads cached results without repeating API calls.

### 2. Keep all PDF, OCR, and LLM work in the existing native worker boundary

The Streamlit process must not import or execute heavy PDF/OCR/VLM preparation
directly. Extend `scripts/pdf_native_worker.py` with a `prepare-llm-aoi` action.
The action receives the existing data directory, deck ID, slide ID, DPI, and OCR
flag, invokes `AOIManager.process_llm_aoi`, and returns only a summary containing
status, model, AOI count, and sanitized error text.

`UploadedDeckWorkspace` owns the subprocess call and reloads `AOIManager` after
the worker exits, matching its current deterministic preparation behavior.
Each page is processed in a separate synchronous worker invocation. This bounds
memory and failure scope without adding threads, a queue, or a service daemon.

### 3. Current-page processing is primary; whole-deck processing is sequential

The UI adds an opt-in sidebar checkbox with explicit data-use wording:

> Enable LLM AOI (send slide images to the configured cloud model)

The control is available only for uploaded PDF decks. The built-in fixture deck
continues to use its existing AOIs.

When enabled:

- The main slide toolbar shows **Process current slide with LLM**.
- If the current page already has a successful result for the configured profile,
  enabling the checkbox loads it automatically and the toolbar reports
  **LLM AOIs loaded** without calling the API again.
- A failed result preserves deterministic AOIs, changes the toolbar action to
  **Retry current slide with LLM**, and retries only after that explicit click
  with `force=True`.
- After a successful worker call, Streamlit reruns once and the current page loads
  the cached `llm_aois` automatically.

The sidebar also shows **Process entire deck with LLM**. It processes page IDs in
ascending order, one page at a time. It skips cached successful pages for the same
LLM profile, updates a Streamlit progress bar and `completed / total` caption, and
continues after a page-level fallback. The final summary reports successful,
fallback, and skipped counts. There is no parallel batch mode, chunk scheduler,
resume database, cancellation protocol, or background thread in this stage.
Before processing, the sidebar states the deck page count and that pages run
sequentially; clicking the button is the only batch confirmation required.

The LLM AOI checkbox is independent of the existing Tutor permission. The AOI
checkbox authorizes slide-image transmission for extraction; the Tutor checkbox
continues to authorize selected text transmission for answer generation.

### 4. AOI activation invalidates stale interaction state

Switching between deterministic and LLM AOIs, or completing a new LLM extraction,
changes the target ID and bbox universe. The corresponding UI callback must:

- clear old selected AOI IDs and live proposals;
- clear confirmation and generated Tutor/XAI output;
- increment the canvas reset revision when the AOI set changes;
- bind the live provider to the newly selected effective AOIs before accepting a
  new proposal.

Page navigation and cached reloads do not call the LLM. Sequential IDs from the
Member 1 generator remain stable within a cached manifest result. Explicit retry
may replace that page's `llm_aois`, and therefore deliberately resets the turn.

## Member 1 Integration Boundary

### Import unchanged in intent

- `modules/slide/llm_aoi.py`: OpenAI-compatible vision request, image compression,
  response extraction, AOI validation, allowed types, and ID normalization.
- Prompt behavior: complete semantic learning units, flat AOI list, image as
  visual truth, PDF/OCR AOIs as anchors, no parent/child containers.

### Merge selectively into current modules

- `modules/slide/slide_parser.py`: add embedded PDF image bbox extraction while
  preserving `pymupdf` import style and DPI-qualified render filenames.
- `modules/slide/ocr.py`: add normalized region OCR and coordinate remapping.
- `modules/slide/aoi_manager.py`: add image-region AOIs, text deduplication,
  wrapped-line merging, LLM reconciliation, and the separate `llm_aois` storage.
- Preserve the current `RLock`, atomic temporary-file replacement, `children`
  grounding metadata, `allow_ocr=False` behavior, and current public methods.
- Embedded-image OCR runs only when `allow_ocr=True`; the whole rendered image can
  still be sent to the configured VLM when OCR is disabled.
- A deterministic save preserves a matching LLM variant. If its deterministic
  anchor digest changes, the save marks that LLM variant stale and the UI falls
  back to the newly saved deterministic AOIs.
- `modules/system/real_slide_provider.py`: accept `llm_guided` when explicitly
  selected and order new types (`diagram`, `table`, `formula`, `code`) without
  changing the deterministic default.

### Harden only integration-critical behavior

The imported implementation must keep fallback behavior but expose typed status
instead of silently losing all diagnostics. Validation must reject an empty LLM
set, invalid normalized bboxes, duplicate semantic objects, and insufficient text
coverage when deterministic text anchors are available. A visual-heavy page with
few text anchors may still use valid visual AOIs; this stage does not add object
detection or another vision model.

## Adjustable Slide Design

The component iframe remains full-width so Streamlit layout and component protocol
stay stable. Only the slide content inside the iframe changes width.

Add `main_slide_width_percent` to session defaults with:

- minimum: `50`
- maximum: `100`
- step: `5`
- default: `100`

Place a compact **Slide size** slider above the main slide. Pass the value through
`render_slide_viewport(..., display_width_percent=...)`. Inside the component:

- `#root` remains `width: 100%`;
- `#slide` uses the requested percentage and `margin-inline: auto`;
- the image remains `width: 100%; height: auto` inside `#slide`;
- overlay and manual rectangle remain positioned relative to `#slide`.

The existing geometry reporter already measures the image's actual browser rect.
Therefore a size change produces a new geometry signature and layout revision,
and gaze/AOI viewport coordinates remain correct. The normalized manual bbox is
preserved across a pure size change; changing deck, slide, AOI profile, or explicit
canvas reset still clears it.

No drag handle is included in this stage. A cross-iframe drag interaction would
add rerun and state synchronization complexity without improving the course demo
enough to justify it.

## Streamlit Media Routing Fix

The current proxy sends every `/media/*` request to the browser capture ingress.
Streamlit 1.59.1 also uses `/media/<hash>.<ext>` for `st.image` and download-button
assets. In the audited live page, all seven thumbnail URLs returned 404 with
`naturalWidth == 0`, while the underlying PNG files were valid.

Move browser capture endpoints to the private namespace:

```text
/attentive-media/start
/attentive-media/video
/attentive-media/audio
/attentive-media/heartbeat
/attentive-media/stop
/attentive-media/stats
```

Keep `/capture` routed to ingress. Route `/attentive-media/*` to ingress and all
other paths, including `/media/*`, to Streamlit. Update the generated capture HTML,
aiohttp routes, proxy selection, and focused routing tests together.

Do not replace thumbnails with custom base64 HTML. That would hide the thumbnail
symptom while leaving Streamlit download assets broken.

## Error Handling and User Feedback

- Missing LLM configuration: keep deterministic AOIs and show `LLM AOI is not
  configured` without exposing environment values.
- API timeout, HTTP error, malformed JSON, or reconciliation failure: store
  `fallback_used`, retain deterministic AOIs, and allow explicit retry.
- Worker crash: use the existing worker stderr-tail error path and keep the active
  page on deterministic AOIs.
- Batch page failure: record it in the batch summary and continue with the next
  page.
- Thumbnail/media failure after routing changes: show existing Streamlit fallback;
  acceptance requires browser console 404 errors to be absent.
- Slide size input is clamped to `50..100` before crossing the component boundary.

## File-Level Scope

### Create

- `modules/slide/llm_aoi.py`
- focused LLM AOI integration tests, using the existing test naming conventions
- `docs/plans/UI-integration/2026-07-14-llm-aoi-slide-media-execution.md`
- `docs/plans/UI-integration/handoffs/llm-aoi-slide-media-log.md`

### Modify

- `modules/slide/aoi_manager.py`
- `modules/slide/slide_parser.py`
- `modules/slide/ocr.py`
- `modules/system/uploaded_deck_service.py`
- `modules/system/real_slide_provider.py`
- `modules/system/main_ui_state.py`
- `modules/ui/slide_viewport_component/__init__.py`
- `modules/ui/slide_viewport_component/index.html`
- `apps/streamlit_attentive_slides.py`
- `scripts/pdf_native_worker.py`
- `scripts/run_live_single_port.py`
- `modules/media/single_port_transport.py`
- directly related existing tests

### Explicitly out of scope

- another Git branch or worktree
- a background job queue, task broker, database, or multi-user worker service
- parallel LLM calls or API-rate optimization
- point-gaze, calibration, object detection, or a new AOI schema hierarchy
- automatic deck processing immediately after upload
- LLM AOI for the built-in fixture deck
- a drag-resize component
- changes to Tutor prompting or model selection unrelated to AOI extraction

## Checkpoints and Verification Budget

Implementation will use four reviewable checkpoints:

1. Streamlit media namespace and thumbnail/download restoration.
2. Adjustable slide width with correct viewport geometry.
3. Current-page LLM AOI preparation, caching, activation, fallback, and reset.
4. Sidebar whole-deck sequential processing and final integration acceptance.

Testing is intentionally bounded:

- Run one focused test group at the end of each checkpoint.
- Do not rerun the full suite after individual two-to-five-minute edits.
- Use fake LLM responses for automated success, malformed-output, fallback,
  caching, and batch-continuation tests.
- Use at most one real configured LLM call on one text-heavy page and one
  visual-heavy page during manual acceptance.
- Run the full repository test suite once after all four checkpoints are green.
- Perform one final browser smoke session covering thumbnail natural dimensions,
  slide widths `50`, `75`, and `100`, AOI overlay/manual drawing alignment,
  current-page LLM loading, and a short multi-page batch.

No additional refactor or test expansion is permitted unless a checkpoint cannot
be completed safely without it.

## Acceptance Criteria

- Uploaded-PDF thumbnails load through the public single port, and Streamlit media
  and download URLs no longer return ingress 404 responses.
- The user can set slide size from 50% to 100%; overlay, manual bbox, and reported
  viewport AOI geometry remain aligned at all accepted sizes.
- With LLM AOI disabled, behavior and deterministic AOIs remain unchanged.
- With LLM AOI enabled, the current uploaded page can be processed and its cached
  `llm_aois` load after completion without overwriting deterministic `aois`.
- The sidebar deck button processes pages sequentially, skips cached successes,
  continues after page fallback, and reports a final summary.
- Missing keys, timeout, malformed output, or worker failure never remove the
  deterministic page result or block navigation.
- `whole_slide` remains available in both deterministic and LLM modes.
- Existing AOI manifest concurrency, native worker isolation, confirmation gates,
  live proposal binding, and Tutor behavior remain intact.
- No new dependency, service, branch, worktree, queue, or database is introduced.
