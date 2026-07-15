# Single-Slide Visual AOI Context Design

**Status:** Approved on 2026-07-15

## Goal

Enhance one explicitly selected slide with a single vision-LLM call that returns both:

- the existing flat semantic AOI list used for gaze targeting; and
- a small, source-aware visual context describing meaningful formulas, charts, diagrams, tables, code, and instructional images that PDF text extraction may miss.

The feature is optimized for image-based PDFs and image-embedded formulas. It does not add a second LLM call, run across an entire deck, or replace the existing deterministic AOI fallback.

## Approved Product Decisions

- Use the dual-output design: AOIs and visual context are separate outputs from the same VLM response.
- Remove `Process entire deck with LLM` and its progress/summary behavior.
- Remove the global `Enable LLM AOI` checkbox and the global AOI-mode session state.
- Permit the VLM to add a new AOI for a self-contained formula, chart, diagram, table, code block, or meaningful image.
- Prevent duplicate or unbounded visual AOIs with deterministic local validation, overlap deduplication, size filters, and count limits.
- Preserve both formula transcription and a concise natural-language description.
- Processed slides automatically use their valid cached LLM AOIs on later visits.
- Unprocessed or ineligible slides continue using deterministic AOIs and never trigger the VLM automatically.
- Visual metadata failure must not invalidate otherwise valid AOIs.
- Display a concise per-slide LLM status.

## Non-Goals

This change does not generate or store:

- generic `main_topic`, `slide_role`, or `key_points` summaries;
- learner-state claims such as “the user may be confused”;
- free-form tutor recommendations;
- whole-deck preprocessing;
- a second enrichment request;
- a slide image in the final tutor request.

The final tutor remains text/source based in this scope. The visual context is a cached bridge for information that ordinary PDF text extraction cannot provide; it is not a substitute for a future multimodal tutor design.

## Alternatives Considered

### Selected: dual AOI and visual-context output

The VLM returns targetable AOIs and independent visual observations in one response. A meaningful visual can appear in both outputs, while a non-targetable but useful visual can remain metadata-only.

This preserves gaze targetability without forcing every decorative or contextual image to become an AOI.

### Rejected: visual metadata only

This would improve tutor background context but would not let gaze resolve “this formula” when the formula was absent from deterministic AOIs.

### Rejected: every visual becomes an AOI

This would create noisy targets for logos, icons, backgrounds, and decorative fragments, reducing gaze-selection stability.

## Single-Call Output Contract

The provider response remains one JSON object:

```json
{
  "aois": [
    {
      "aoi_id": "llm_aoi_1",
      "type": "formula",
      "bbox": [0.18, 0.31, 0.72, 0.46],
      "text": "",
      "confidence": 0.91
    }
  ],
  "visual_context": {
    "items": [
      {
        "type": "formula",
        "bbox": [0.18, 0.31, 0.72, 0.46],
        "description": "A conditional-probability formula used by the slide.",
        "transcription": "p(y \\mid x) = \\cdots",
        "confidence": 0.91
      }
    ]
  }
}
```

`aois` remains mandatory. `visual_context.items` is optional and independently validated.

The local canonical visual item is:

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
```

`visual_id` is assigned locally after validation and deduplication. The model is not trusted to create stable identifiers.

## Visual Types and Content

Allowed visual-context types are:

- `formula`: preserve a best-effort transcription and a separate description;
- `chart`: describe visible axes/legend when readable and only the most salient visible trend or comparison;
- `diagram`: describe the principal entities and explicit arrows or relationships;
- `table`: preserve headers and the main visible comparison, not a full cell dump;
- `image`: describe an instructionally relevant subject;
- `code`: preserve readable code in `transcription` and its role in `description`;
- `other`: use only for meaningful visual content that does not fit another type.

Logos, page furniture, decorative icons, backgrounds, and tiny fragments are excluded.

Descriptions must report visible content rather than introduce external explanations. Formula transcription is best effort and remains distinguishable from PDF-native text.

## Visual AOI Promotion

A visual observation is also requested as an AOI candidate when all of the following are true:

- it is a self-contained formula, chart, diagram, table, code block, or meaningful instructional image;
- a learner could naturally refer to it as “this” while looking at the region;
- it has a stable rectangular target large enough for gaze selection;
- it is not decorative page furniture;
- it occupies less than 90% of the slide.

Local reconciliation remains authoritative. The VLM cannot bypass bbox validation, text-anchor reconciliation, coverage checks, or AOI deduplication.

## Deterministic Validation and Bounds

Visual-context validation applies these exact bounds:

- normalized bbox with `0 <= x1 < x2 <= 1` and `0 <= y1 < y2 <= 1`;
- non-empty description, capped at 600 characters;
- optional transcription capped at 1,200 characters;
- confidence clamped to `[0, 1]` and items below `0.55` discarded;
- visual width at least `0.04`, height at least `0.025`, and area at least `0.002`;
- at most six canonical visual-context items per slide.

Items are processed by descending confidence. A later item is discarded when it has a compatible visual type and IoU of at least `0.80` with an already retained item.

Visual AOIs retain the existing same-category IoU deduplication and additionally keep at most eight visual AOIs after confidence ordering. Text AOIs are not subject to the visual count cap because text-coverage validation must remain intact.

After AOI reconciliation, each visual item is associated with the compatible final visual AOI having the highest IoU of at least `0.65`. The result is stored as `linked_aoi_id`. An item with no matching AOI remains valid background context with `linked_aoi_id=None`.

Compatibility mapping is:

- `formula` -> AOI `formula`;
- `chart` -> AOI `figure` or `diagram`;
- `diagram` -> AOI `diagram` or `figure`;
- `table` -> AOI `table`;
- `image` -> AOI `figure`;
- `code` -> AOI `code`;
- `other` -> AOI `mixed` or `figure`.

## Independent Failure Semantics

The generator returns a typed result containing `aois`, `visual_context`, and `visual_context_status`.

`visual_context_status` is one of:

- `used`: at least one valid item survived;
- `empty`: the field was absent or no meaningful visual was reported;
- `invalid`: the field was present but malformed or all reported items failed structural validation.

Failure rules:

- missing or unusable `aois` keeps the current whole-call fallback behavior;
- valid AOIs plus malformed visual metadata stores the AOIs with `visual_context_status="invalid"` and an empty visual list;
- an empty visual list is not an AOI error;
- an AOI failure stores no visual context, because it cannot be reliably coupled to the cached generation profile;
- external exception details remain sanitized at the existing trust boundary.

## Cache and Persistence

The AOI manifest stores, for each successfully enhanced slide:

```json
{
  "llm_aois": [],
  "llm_visual_context": [],
  "llm_visual_context_status": "used",
  "llm_aoi_status": "used",
  "llm_aoi_model": "qwen-vl-plus",
  "llm_aoi_profile": "4c96f3c7",
  "llm_aoi_anchor_digest": "fe32a199"
}
```

`PROMPT_SCHEMA_VERSION` is incremented so stale pre-visual-context caches are not treated as eligible for the new contract. After a successful new generation, cache reuse follows the existing model, prompt-profile, and anchor-digest rules. Revisiting a cached slide never calls the VLM.

## Per-Slide UI Behavior

Uploaded decks no longer expose a global LLM mode or deck-batch action.

For each slide:

- no eligible cache: show `Enhance this slide with LLM`;
- previous fallback: show `Retry this slide with LLM`;
- eligible cache: automatically use the cached LLM AOIs and show a non-interactive status such as `LLM-enhanced · 6 AOIs · 3 visual notes`;
- visual metadata invalid but AOIs valid: show `LLM-enhanced · 6 AOIs · visual context unavailable`;
- provider not configured: show the existing concise configuration message.

The page action remains the only path that initiates a cloud AOI call. Ordinary navigation performs only cache lookup and deterministic fallback.

## Tutor Context Flow

`MainUISlide`, the live `SlideFrame`, and `TutorContext` carry the canonical visual-context items.

Each item becomes a grounded tutor source:

```json
{
  "source_id": "slide_007_visual_01",
  "source_kind": "visual_observation",
  "slide_id": 7,
  "aoi_id": "llm_aoi_4",
  "text": "Description: A conditional-probability formula.\nTranscription: p(y | x)",
  "metadata": {
    "visual_type": "formula",
    "bbox": [0.18, 0.31, 0.72, 0.46],
    "confidence": 0.91,
    "provenance": "llm_visual_analysis"
  }
}
```

The source ID is stable within the cached generation. `aoi_id` is omitted when no final AOI is linked.

When the confirmed AOI has a linked visual item, formula transcription and visual description are used before the current whole-slide-text fallback. This prevents an empty visual AOI from being represented as though the entire slide text were its own content.

The grounded tutor prompt states that `visual_observation` sources are VLM-derived, may contain transcription errors, and must yield to PDF-native/AOI text when the sources conflict. The system must not convert a visual observation into a claim about learner attention, cognition, or confusion.

## Privacy and Observability

The feature does not change the existing cloud-image disclosure: the per-slide action sends the rendered slide image to the configured vision provider.

Persisted metadata contains descriptions, transcriptions, normalized boxes, confidence, model/profile identity, and link identifiers. It does not contain raw model reasoning.

The LLM state API adds only:

- `visual_count`;
- `visual_context_status`.

No provider response body or unsanitized exception is exposed in UI state.

## Verification Budget

Follow the repository Lean Execution Profile:

- no baseline run;
- no RED or expected-failing run;
- one focused GREEN group after each checkpoint;
- only the smallest affected test module is rerun after a failure;
- no browser automation, lint, type, security, or performance suite;
- one independent whole-change diff review after all checkpoints;
- one full unit suite after review and any bounded review-fix wave;
- no repeated passing full suite because of commits or documentation-only work.

## Acceptance Criteria

- One explicit single-slide action causes exactly one VLM request.
- The response can add a valid formula/chart/diagram/table/code/image AOI without requiring a PDF text anchor.
- Duplicate overlapping visual AOIs and visual observations are deterministically bounded.
- Formula transcription and description are separately preserved.
- A malformed visual-context field cannot turn valid AOIs into fallback AOIs.
- A cached enhanced slide is selected automatically on revisit without another VLM request.
- Unprocessed slides remain deterministic and never call the VLM during navigation.
- The global checkbox, deck-batch button, deck progress UI, and deck-batch service method are removed.
- Tutor requests contain `visual_observation` sources with bbox, confidence, provenance, and optional AOI linkage.
- A confirmed linked visual AOI uses its visual content before whole-slide fallback text.
- Existing grounding, privacy, confirmation, and sanitized-error behavior remains intact.
