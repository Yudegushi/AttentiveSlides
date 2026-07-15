# Single-Slide Visual AOI Context Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan checkpoint-by-checkpoint. Steps use checkbox (`- [ ]`) syntax for tracking. Do not dispatch subagents unless the user explicitly requests them.

**Goal:** Make one explicit per-slide VLM call produce cached semantic AOIs plus bounded visual context for formulas, charts, diagrams, tables, code, and meaningful images, then supply that context to the grounded tutor.

**Architecture:** Extend the existing `LLMAOIGenerator` response into a typed dual result while keeping AOIs mandatory and visual metadata optional. Persist linked visual observations beside the cached LLM AOIs, automatically select an eligible per-slide cache, and convert visual observations into provenance-marked tutor sources. Remove all global/deck-batch LLM AOI behavior.

**Tech Stack:** Python 3.11, dataclasses, existing urllib OpenAI-compatible VLM client, JSON manifest persistence, Streamlit, `unittest`.

## Global Constraints

- Follow the project Lean Execution Profile supplied in the task context.
- Do not run a baseline suite or an expected-failing RED test.
- After each checkpoint, run exactly one focused GREEN test group covering that checkpoint.
- On failure, diagnose and rerun only the smallest affected module after the fix.
- Perform one whole-change diff review after all checkpoints and one full unit suite after review fixes.
- Do not add a second LLM request or automatic LLM processing during slide navigation.
- Do not process an entire deck with LLM AOI.
- Do not let visual-context parsing failure invalidate valid AOIs.
- Do not expose raw provider responses, credentials, endpoints, or unsanitized exceptions.
- Do not infer learner confusion, attention, cognition, or intent from slide content.
- Keep formula transcription separate from natural-language visual description.
- Keep a maximum of six visual observations and eight visual AOIs per slide.
- Preserve valid cached per-slide results until the existing model/prompt/anchor profile becomes ineligible.

---

## File Structure

Create no new production module. Keep the feature within existing boundaries:

- `modules/common/schemas.py`
  - Add the canonical cross-layer `VisualContextItem` dataclass.
- `modules/slide/llm_aoi.py`
  - Define the typed dual-generation result, prompt contract, independent visual validation, deduplication, and limits.
- `modules/slide/aoi_manager.py`
  - Reconcile AOIs, link visual observations to final AOIs, and persist both outputs atomically without coupling their validation outcomes.
- `modules/system/uploaded_deck_service.py`
  - Remove deck batching/global browser mode and expose cached visual context on each slide.
- `apps/streamlit_attentive_slides.py`
  - Remove global/deck controls and render only per-slide enhancement/status.
- `modules/system/main_ui_state.py`, `modules/system/adapters.py`, `modules/system/active_deck_slide_provider.py`
  - Carry visual context through UI and live-provider boundaries.
- `modules/system/main_tutor_integration.py`
  - Prefer linked visual context over whole-slide fallback for an empty visual AOI.
- `modules/common/llm_schemas.py`, `modules/tutor/tutor_request_adapter.py`, `modules/tutor/grounded_prompt.py`
  - Add provenance-marked `visual_observation` sources and prompt policy.

Tests stay in the existing modules:

- `tests/test_llm_aoi.py`
- `tests/test_uploaded_deck_service.py`
- `tests/test_streamlit_attentive_slides.py`
- `tests/test_main_ui_widget_inventory.py`
- `tests/test_main_ui_state.py`
- `tests/test_active_deck_slide_provider.py`
- `tests/test_system_adapters.py`
- `tests/test_main_tutor_integration.py`
- `tests/test_llm_schemas.py`
- `tests/test_tutor_request_adapter.py`
- `tests/test_grounded_prompt.py`

Do not create a generic metadata framework or a separate slide-summary service.

---

### Checkpoint 1: Dual VLM Result, Validation, Linking, and Cache

**Files:**

- Modify: `modules/common/schemas.py`
- Modify: `modules/slide/llm_aoi.py`
- Modify: `modules/slide/aoi_manager.py`
- Modify: `tests/test_llm_aoi.py`

**Interfaces:**

- Produces `VisualContextItem` for all later system and tutor layers.
- Changes `LLMAOIGenerator.generate(...)` from `list[dict[str, Any]]` to `LLMAOIResult`.
- Keeps `AOIManager.get_effective_aois(...)` unchanged.
- Extends `AOIManager.get_llm_aoi_state(...)` with `visual_count` and `visual_context_status`.

- [ ] **Step 1: Add the canonical visual-context type and dual-generation type**

Add this dataclass near `AOI` in `modules/common/schemas.py`:

```python
@dataclass(frozen=True)
class VisualContextItem:
    visual_id: str
    type: str
    bbox: list[float]
    description: str
    transcription: str = ""
    confidence: float = 0.7
    linked_aoi_id: str | None = None
    provenance: str = "llm_visual_analysis"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
```

In `modules/slide/llm_aoi.py`, import `Literal` and `VisualContextItem`, bump:

```python
PROMPT_SCHEMA_VERSION = "attentive-llm-aoi-v3-visual-context"
```

and add:

```python
VisualContextStatus = Literal["used", "empty", "invalid"]

@dataclass(frozen=True)
class LLMAOIResult:
    aois: tuple[dict[str, Any], ...]
    visual_context: tuple[VisualContextItem, ...]
    visual_context_status: VisualContextStatus
```

- [ ] **Step 2: Update test fixtures and add checkpoint coverage without running them yet**

Change `FakeLLMGenerator` in `tests/test_llm_aoi.py` to return `LLMAOIResult` and add a helper:

```python
def visual_item(
    *,
    item_type="formula",
    bbox=None,
    description="Conditional probability formula.",
    transcription="p(y | x)",
    confidence=0.9,
):
    return {
        "type": item_type,
        "bbox": bbox or [0.2, 0.3, 0.7, 0.45],
        "description": description,
        "transcription": transcription,
        "confidence": confidence,
    }
```

Cover these exact behaviors with methods named `test_generator_returns_aois_and_formula_visual_context`, `test_malformed_visual_context_does_not_reject_valid_aois`, `test_visual_context_filters_tiny_low_confidence_and_duplicate_items`, `test_visual_context_is_capped_at_six_items`, `test_reconciliation_links_visual_item_to_final_visual_aoi`, `test_unmatched_visual_item_remains_without_linked_aoi`, `test_visual_aoi_candidates_are_deduplicated_and_capped_at_eight`, `test_successful_cache_persists_visual_context_and_status`, `test_aoi_fallback_clears_visual_context_without_leaking_error_details`, and `test_cached_profile_returns_visual_count_without_second_generation`.

The assertions must prove: AOI count is unchanged by malformed metadata; the retained formula has both exact strings; every retained bbox passes the size rules; duplicate IoU is below `0.80`; list lengths are at most six/eight; linked items contain the final renumbered AOI ID; unmatched items contain `None`; cached generation call count remains one; fallback fields are empty; and persisted errors contain no secret fixture token.

Use a mocked provider body containing one formula in both `aois` and `visual_context.items`; assert formula transcription and description remain separate.

- [ ] **Step 3: Expand the one-call prompt**

Keep the existing paragraph rules verbatim and append instructions equivalent to:

```python
"In the same JSON object, optionally return visual_context.items. "
"Describe only meaningful visible formulas, charts, diagrams, tables, code, and instructional images. "
"Exclude logos, headers, footers, backgrounds, decorative icons, and tiny fragments. "
"For each item return type,bbox,description,transcription,confidence. "
"For formulas and readable code, preserve the visible content in transcription and explain its visible role separately in description. "
"For each self-contained targetable visual item, also return one matching visual AOI with the same region. "
"Do not duplicate overlapping visual items or AOIs. "
```

Update the example to show both top-level keys. Keep temperature `0.1`, one image, one user message, and one HTTP call.

- [ ] **Step 4: Validate visual metadata independently from AOIs**

Refactor `generate(...)` so AOIs remain mandatory, then validate visual context in a non-throwing branch:

```python
aois = data.get("aois")
if not isinstance(aois, list):
    raise ValueError("LLM AOI response must contain an 'aois' list")

validated_aois = tuple(self._validate_aois(aois))
visual_items, visual_status = self._validate_visual_context(
    data.get("visual_context"),
    field_present="visual_context" in data,
)
return LLMAOIResult(
    aois=validated_aois,
    visual_context=visual_items,
    visual_context_status=visual_status,
)
```

Implement `_validate_visual_context(...)` with the design constants:

```python
ALLOWED_VISUAL_CONTEXT_TYPES = {
    "formula", "chart", "diagram", "table", "image", "code", "other",
}
MAX_VISUAL_CONTEXT_ITEMS = 6
MIN_VISUAL_CONFIDENCE = 0.55
MIN_VISUAL_WIDTH = 0.04
MIN_VISUAL_HEIGHT = 0.025
MIN_VISUAL_AREA = 0.002
VISUAL_CONTEXT_DEDUPE_IOU = 0.80
```

Rules:

1. absent field -> `(), "empty"`;
2. non-object `visual_context` or non-list `items` -> `(), "invalid"`;
3. normalize allowed type, bbox, description, transcription, and confidence;
4. reject blank descriptions, undersized boxes, and confidence below `0.55`;
5. truncate description to 600 characters and transcription to 1,200;
6. sort by descending confidence;
7. discard a later compatible item with IoU `>= 0.80`;
8. retain at most six and assign sequential local IDs beginning with `visual_1`;
9. valid empty input -> `"empty"`; non-empty input with no valid item -> `"invalid"`.

Do not put visual parsing inside a catch that rethrows `LLM AOI request failed` after AOIs have already validated.

- [ ] **Step 5: Link and persist visual context after AOI reconciliation**

Refactor `AOIManager.build_llm_guided_aois(...)` into a method that preserves the complete `LLMAOIResult` while converting only `result.aois` into internal `AOI` objects.

In `process_llm_aoi(...)`:

```python
generation = self.build_llm_guided_slide(
    str(slide_data.get("slide_image_path", "")),
    str(slide_data.get("ocr_text", "")),
    rule_aois,
    anchor_aois,
)
llm_aois = self.reconcile_llm_aois(
    generation.aois,
    anchor_aois,
)
visual_context = self._link_visual_context(
    generation.visual_context,
    llm_aois,
)
```

Implement `_link_visual_context(...)` using the compatibility table from the design and the highest same-category IoU `>= 0.65`. Create linked values with `dataclasses.replace(item, linked_aoi_id=...)`.

Before final AOI reading-order sort, reject visual AOI candidates whose width is below `0.04`, height is below `0.025`, or area is below `0.002`; then retain all text candidates and only the top eight remaining visual candidates after the existing confidence sort and same-category IoU dedupe. These targetability filters must not apply to text AOIs.

Persist successful results together:

```python
current.update({
    "llm_aois": [aoi.to_dict() for aoi in llm_aois],
    "llm_visual_context": [item.to_dict() for item in visual_context],
    "llm_visual_context_status": generation.visual_context_status,
    "llm_aoi_status": "used",
    "llm_aoi_model": str(self.llm_aoi_generator.config.model),
    "llm_aoi_profile": expected_profile,
    "llm_aoi_anchor_digest": anchor_digest,
    "llm_aoi_error": None,
})
```

On AOI fallback set `llm_visual_context=[]` and `llm_visual_context_status="empty"` while preserving the existing sanitized AOI error.

Include both fields in stale-profile cleanup. Extend `get_llm_aoi_state(...)` with:

```python
"visual_count": len(slide_data.get("llm_visual_context", [])),
"visual_context_status": str(
    slide_data.get("llm_visual_context_status", "empty")
),
```

Add `visual_count=0` and `visual_context_status="empty"` to the missing-slide early return as well, so callers receive a stable state shape before any slide processing.

- [ ] **Step 6: Run the focused GREEN group once**

Run:

```bash
cd /home/charles/repos/AttentiveSlides-eyetheia-local-gaze-integration
/home/charles/miniconda3/envs/pyboe/bin/python -m unittest tests.test_llm_aoi -v
```

Expected: all `tests.test_llm_aoi` tests pass. If not, fix the cause and rerun only `tests.test_llm_aoi`.

- [ ] **Step 7: Commit checkpoint 1**

```bash
git add modules/common/schemas.py modules/slide/llm_aoi.py modules/slide/aoi_manager.py tests/test_llm_aoi.py
git commit -m "feat: capture visual context with LLM AOIs"
```

Record only: checkpoint status, focused test result, commit, blocker, next step.

---

### Checkpoint 2: Single-Slide-Only Cache Selection and UI

**Files:**

- Modify: `modules/system/uploaded_deck_service.py`
- Modify: `apps/streamlit_attentive_slides.py`
- Modify: `tests/test_uploaded_deck_service.py`
- Modify: `tests/test_streamlit_attentive_slides.py`
- Modify: `tests/test_main_ui_widget_inventory.py`

**Interfaces:**

- Consumes the extended `get_llm_aoi_state(...)` from checkpoint 1.
- Produces an `UploadedDeckBrowser` that always prefers an eligible per-slide cache but never generates one during lookup.
- Removes `UploadedDeckWorkspace.prepare_llm_deck(...)` completely.

- [ ] **Step 1: Replace global/deck behavior tests with per-slide cache tests without running them yet**

Delete tests that assert the checkbox, deck-batch button, batch progress, batch summary, and `prepare_llm_deck(...)` behavior.

Add or update methods named `test_uploaded_browser_automatically_uses_eligible_cached_llm_aoi`, `test_uploaded_browser_uses_deterministic_aoi_when_page_has_no_eligible_cache`, `test_slide_lookup_never_calls_prepare_llm_aoi`, `test_main_contains_no_global_llm_checkbox_or_deck_batch_action`, `test_current_slide_action_is_available_without_global_opt_in`, `test_eligible_slide_renders_compact_aoi_and_visual_status`, and `test_invalid_visual_context_status_does_not_hide_valid_llm_aoi_status`.

Assert the selected `aoi_profile`, selected AOI IDs, zero calls to `prepare_llm_aoi` during lookup, absence of both removed widget keys/function calls, presence of the current-slide key, and exact compact status fragments for used and invalid visual metadata.

Remove `main_llm_aoi_enabled` and `main_process_deck_llm_aoi` from the required widget inventory. Keep `main_process_current_llm_aoi`.

- [ ] **Step 2: Remove deck batching and the global browser mode**

In `modules/system/uploaded_deck_service.py`:

- remove `Callable` if unused;
- remove `UploadedDeckBrowser.use_llm_aoi` and its constructor argument;
- make `UploadedDeckBrowser.get_slide(...)` call `workspace.get_slide(..., use_llm_aoi=True)`;
- remove the `use_llm_aoi` argument from `UploadedDeckWorkspace.open_browser(...)`;
- delete `UploadedDeckWorkspace.prepare_llm_deck(...)`.

Do not remove `AOIManager.get_effective_aois(..., use_llm_aoi=...)`, because other providers still use the explicit manager-level boundary.

The automatic `use_llm_aoi=True` lookup is safe because `get_effective_aois(...)` already returns deterministic AOIs when the current slide has no eligible cache. It must not call `prepare_llm_aoi(...)`.

- [ ] **Step 3: Remove global and whole-deck Streamlit state/UI**

In `apps/streamlit_attentive_slides.py`:

- remove the `_render_llm_aoi_opt_in()` call and function;
- remove `_on_llm_aoi_mode_change()`;
- remove `_render_llm_aoi_deck_batch(...)` and its call;
- remove `main_llm_aoi_enabled` and `main_llm_aoi_deck_summary` defaults/normalization;
- simplify `_resolve_active_browser(...)` to `workspace.open_browser(deck_id)`;
- remove the global-enabled guard from `_render_current_slide_llm_aoi_action(...)`.

Do not alter upload, navigation, live binding, confirmation, or tutor-generation ordering beyond deleting the obsolete calls.

- [ ] **Step 4: Render the per-slide action and compact status**

Keep `get_llm_aoi_state(...)` side-effect free. Use this behavior:

```python
if eligible:
    visual_status = str(state.get("visual_context_status", "empty"))
    if visual_status == "invalid":
        st.caption(
            f"LLM-enhanced · {state.get('aoi_count', 0)} AOIs · "
            "visual context unavailable"
        )
    else:
        st.caption(
            f"LLM-enhanced · {state.get('aoi_count', 0)} AOIs · "
            f"{state.get('visual_count', 0)} visual notes"
        )
    return
```

For an unprocessed configured slide, render `Enhance this slide with LLM`. For `fallback_used`, render `Retry this slide with LLM` and call `prepare_llm_aoi(..., force=True)`. Keep the existing sanitized configuration and failure copy.

Successful processing resets turn state, updates the active AOI signature, and reruns once. Revisiting the page uses the cache without a call.

- [ ] **Step 5: Run the focused GREEN group once**

Run:

```bash
cd /home/charles/repos/AttentiveSlides-eyetheia-local-gaze-integration
/home/charles/miniconda3/envs/pyboe/bin/python -m unittest \
  tests.test_uploaded_deck_service \
  tests.test_streamlit_attentive_slides \
  tests.test_main_ui_widget_inventory -v
```

Expected: all three modules pass and no static UI test finds the removed global/deck controls.

- [ ] **Step 6: Commit checkpoint 2**

```bash
git add modules/system/uploaded_deck_service.py apps/streamlit_attentive_slides.py tests/test_uploaded_deck_service.py tests/test_streamlit_attentive_slides.py tests/test_main_ui_widget_inventory.py
git commit -m "refactor: make LLM AOI enhancement slide scoped"
```

---

### Checkpoint 3: Carry Visual Observations into the Grounded Tutor

**Files:**

- Modify: `modules/system/main_ui_state.py`
- Modify: `modules/system/uploaded_deck_service.py`
- Modify: `modules/system/adapters.py`
- Modify: `modules/system/active_deck_slide_provider.py`
- Modify: `modules/system/main_tutor_integration.py`
- Modify: `modules/common/schemas.py`
- Modify: `modules/common/llm_schemas.py`
- Modify: `modules/tutor/tutor_request_adapter.py`
- Modify: `modules/tutor/grounded_prompt.py`
- Modify: `tests/test_main_ui_state.py`
- Modify: `tests/test_active_deck_slide_provider.py`
- Modify: `tests/test_system_adapters.py`
- Modify: `tests/test_main_tutor_integration.py`
- Modify: `tests/test_llm_schemas.py`
- Modify: `tests/test_tutor_request_adapter.py`
- Modify: `tests/test_grounded_prompt.py`

**Interfaces:**

- Consumes persisted `llm_visual_context` only for an eligible cached profile.
- Adds `visual_context` to `MainUISlide`, `SlideFrame`, and `TutorContext` with empty defaults.
- Adds `visual_observation` to `SourceKind`.
- Produces stable tutor source IDs `slide_{slide_id:03d}_visual_{index:02d}`.

- [ ] **Step 1: Add propagation and tutor-source tests without running them yet**

Add fixtures using:

```python
VisualContextItem(
    visual_id="visual_1",
    type="formula",
    bbox=[0.2, 0.3, 0.7, 0.45],
    description="A conditional-probability formula.",
    transcription="p(y | x)",
    confidence=0.91,
    linked_aoi_id="llm_aoi_4",
)
```

Cover methods named `test_uploaded_slide_exposes_visual_context_only_for_eligible_cache`, `test_main_ui_and_live_slide_frames_preserve_visual_context`, `test_linked_visual_context_precedes_whole_slide_fallback_for_visual_aoi`, `test_visual_observation_source_contains_description_transcription_and_provenance`, `test_unlinked_visual_observation_has_no_aoi_id`, `test_visual_observation_source_id_is_stable`, `test_grounded_prompt_marks_visual_observation_as_model_derived`, and `test_existing_text_only_context_still_builds_the_same_source_set`.

Assert dataclass equality across boundaries; exact confirmed-context ordering; exact source ID `slide_007_visual_01`; description and transcription both appear in source text; metadata contains bbox/confidence/provenance; unlinked source `aoi_id is None`; prompt contains the visual-source caution; and a text-only context still produces only confirmed/current/neighbor sources.

Use dataclass defaults so existing text-only test constructors require no changes unless they assert exact serialized dictionaries.

- [ ] **Step 2: Carry typed visual context through slide boundaries**

Add empty-default fields:

```python
# MainUISlide
visual_context: tuple[VisualContextItem, ...] = ()

# SlideFrame
visual_context: tuple[VisualContextItem, ...] = ()

# TutorContext, after adaptive_strategy
visual_context: list[VisualContextItem] = field(default_factory=list)
```

Include visual context in `MainUISlide.to_dict()`, `ProviderBackedDeckStore.get_slide(...)`, and `ActiveDeckSlideProvider.get_slide_frame(...)`.

In `UploadedDeckWorkspace.get_slide(...)`, after `get_effective_aois(...)`, populate visual context only when the returned `aoi_profile` is not `"deterministic"` and the cached visual status is `"used"`:

```python
visual_context = tuple(
    VisualContextItem(**item)
    for item in slide_data.get("llm_visual_context", [])
)
```

Invalid item loading must be defensive: skip malformed persisted items rather than breaking slide loading, because persistence may outlive code versions.

- [ ] **Step 3: Use linked visual content for an empty confirmed visual AOI**

In `modules/system/main_tutor_integration.py`, add a focused helper:

```python
def _linked_visual_context_text(
    slide: MainUISlide,
    aoi_id: str,
) -> str:
    for item in slide.visual_context:
        if item.linked_aoi_id != aoi_id:
            continue
        parts = []
        if item.transcription.strip():
            parts.append(f"Visible transcription: {item.transcription.strip()}")
        if item.description.strip():
            parts.append(f"Visual description: {item.description.strip()}")
        return "\n".join(parts)
    return ""
```

Change the confirmed-context precedence to:

```python
confirmed_context = (
    wrapper_context
    or metadata_context
    or current_aoi.text.strip()
    or _linked_visual_context_text(slide, current_aoi.aoi_id)
    or slide.slide_text.strip()
)
```

Pass `visual_context=list(slide.visual_context)` into `TutorContext`.

- [ ] **Step 4: Add visual observations to the typed tutor request**

In `modules/common/llm_schemas.py`, add `"visual_observation"` to `SourceKind` and `_ALLOWED_SOURCE_KINDS`.

In `TutorRequestAdapter._build_sources(...)`, append one source per canonical item:

```python
for index, item in enumerate(context.visual_context, start=1):
    text_parts = [f"Description: {item.description.strip()}"]
    if item.transcription.strip():
        text_parts.append(
            f"Visible transcription: {item.transcription.strip()}"
        )
    sources.append(ContextSource(
        source_id=(
            f"slide_{context.slide_id:03d}_visual_{index:02d}"
        ),
        slide_id=context.slide_id,
        source_kind="visual_observation",
        text="\n".join(text_parts),
        aoi_id=item.linked_aoi_id,
        title=f"Visual observation {index}",
        metadata={
            "visual_type": item.type,
            "bbox": list(item.bbox),
            "confidence": item.confidence,
            "provenance": item.provenance,
        },
    ))
```

The list is already capped at six by checkpoint 1. Do not regenerate, summarize, or expand it in the adapter.

- [ ] **Step 5: Add visual-source precedence and caution to the grounded prompt**

Add `visual_observation` to `_SOURCE_PRIORITY` after `current_slide` and before `neighbor_slide`.

Extend the system evidence policy with concise rules equivalent to:

```text
A visual_observation source is a model-derived reading of the slide image and may contain transcription errors.
Prefer confirmed AOI or PDF-native/current-slide text when it conflicts with a visual observation.
Use the supplied confidence and express uncertainty when a visual detail is not reliable.
Never interpret a visual observation as evidence of the learner's mental state.
```

Do not change the output JSON contract or grounding-validator citation rules.

- [ ] **Step 6: Run the focused GREEN group once**

Run:

```bash
cd /home/charles/repos/AttentiveSlides-eyetheia-local-gaze-integration
/home/charles/miniconda3/envs/pyboe/bin/python -m unittest \
  tests.test_main_ui_state \
  tests.test_active_deck_slide_provider \
  tests.test_system_adapters \
  tests.test_main_tutor_integration \
  tests.test_llm_schemas \
  tests.test_tutor_request_adapter \
  tests.test_grounded_prompt -v
```

Expected: all seven modules pass, including text-only regressions and visual-source provenance tests.

- [ ] **Step 7: Commit checkpoint 3**

```bash
git add modules/system/main_ui_state.py modules/system/uploaded_deck_service.py modules/system/adapters.py modules/system/active_deck_slide_provider.py modules/system/main_tutor_integration.py modules/common/schemas.py modules/common/llm_schemas.py modules/tutor/tutor_request_adapter.py modules/tutor/grounded_prompt.py tests/test_main_ui_state.py tests/test_active_deck_slide_provider.py tests/test_system_adapters.py tests/test_main_tutor_integration.py tests/test_llm_schemas.py tests/test_tutor_request_adapter.py tests/test_grounded_prompt.py
git commit -m "feat: ground tutor with cached visual observations"
```

---

### Checkpoint 4: Whole-Change Review, Full Suite, and Deployment Handoff

**Files:**

- Review all files changed in checkpoints 1-3.
- Modify only files required by a bounded Critical/Important review fix.

**Interfaces:**

- No new interfaces.
- Produces final verification evidence and a launcher-ready branch.

- [ ] **Step 1: Perform one independent whole-change review**

Review:

```bash
cd /home/charles/repos/AttentiveSlides-eyetheia-local-gaze-integration
git status --short
git diff --check HEAD~3..HEAD
git diff --stat HEAD~3..HEAD
git diff HEAD~3..HEAD -- modules/common modules/slide modules/system modules/tutor apps tests
```

Check only:

- valid AOIs survive malformed/absent visual metadata;
- no navigation path calls the VLM;
- old global/deck-batch state and service code are fully removed;
- cached profile invalidation includes the prompt-version bump;
- duplicate/size/count limits apply only to visual candidates, not required text coverage;
- visual items cannot load for a deterministic/ineligible profile;
- empty visual AOIs use linked visual content before whole-slide fallback;
- `visual_observation` provenance and caution reach the actual grounded prompt;
- raw provider/error details remain hidden.

If Critical or Important issues exist, fix them in one bounded wave and run only the directly affected checkpoint test group. Do not perform another review wave.

- [ ] **Step 2: Run the full unit suite once**

Run only after review fixes:

```bash
cd /home/charles/repos/AttentiveSlides-eyetheia-local-gaze-integration
/home/charles/miniconda3/envs/pyboe/bin/python -m unittest discover -s tests -v
```

Expected: full-suite exit code `0`. Do not rerun a passing suite because of a later commit, handoff, or documentation-only change.

- [ ] **Step 3: Commit any bounded review fix**

Skip this step when the review required no code change. Otherwise:

Stage only the known feature surface; unchanged paths are harmless:

```bash
git add modules/common/schemas.py modules/common/llm_schemas.py modules/slide/llm_aoi.py modules/slide/aoi_manager.py modules/system/uploaded_deck_service.py modules/system/main_ui_state.py modules/system/adapters.py modules/system/active_deck_slide_provider.py modules/system/main_tutor_integration.py modules/tutor/tutor_request_adapter.py modules/tutor/grounded_prompt.py apps/streamlit_attentive_slides.py tests/test_llm_aoi.py tests/test_uploaded_deck_service.py tests/test_streamlit_attentive_slides.py tests/test_main_ui_widget_inventory.py tests/test_main_ui_state.py tests/test_active_deck_slide_provider.py tests/test_system_adapters.py tests/test_main_tutor_integration.py tests/test_llm_schemas.py tests/test_tutor_request_adapter.py tests/test_grounded_prompt.py
git commit -m "fix: address visual AOI context review"
```

- [ ] **Step 4: Restart the existing launcher service after successful verification**

```bash
systemctl --user restart attentiveslides-local.service
systemctl --user is-active attentiveslides-local.service
journalctl --user -u attentiveslides-local.service -n 80 --no-pager
```

Expected: service state `active`; no startup traceback; unified launcher remains on remote `127.0.0.1:8501`.

- [ ] **Step 5: Perform one user-driven single-slide acceptance**

Use an image-heavy or image-PDF page containing a formula or chart:

1. Open the page without clicking enhancement and verify deterministic AOIs load without a cloud call.
2. Click `Enhance this slide with LLM` once.
3. Verify the page shows `LLM-enhanced · N AOIs · M visual notes`.
4. Verify at least one meaningful formula/chart/diagram is an AOI when it is large and self-contained.
5. Confirm formula transcription and description appear as separate cached fields in the slide manifest.
6. Navigate away and back; verify the same cached status appears without another call.
7. Ask for an explanation of the linked visual and verify the tutor request XAI/source list includes `slide_NNN_visual_XX` with `provenance=llm_visual_analysis`.

This is the only real-provider acceptance call required by the plan. Do not process the deck.

## Execution Ledger Template

Keep the ledger concise:

| Checkpoint | Focused result | Commit | Blocker | Next |
|---|---|---|---|---|
| 1. Dual result/cache | pending | pending | none | single-slide UI |
| 2. Single-slide UI | pending | pending | none | tutor context |
| 3. Tutor propagation | pending | pending | none | review/full suite |
| 4. Review/full suite | pending | optional fix | none | deploy/acceptance |

## Definition of Done

- The implementation satisfies every acceptance criterion in `docs/superpowers/specs/2026-07-15-single-slide-visual-aoi-context-design.md`.
- All three focused checkpoint groups passed at their checkpoint.
- The one final whole-change review has no unresolved Critical or Important issue.
- The one final full suite exits `0`.
- The existing launcher service is active.
- One user-driven image-heavy slide confirms AOI promotion, visual metadata caching, cache reuse, and tutor-source propagation.
