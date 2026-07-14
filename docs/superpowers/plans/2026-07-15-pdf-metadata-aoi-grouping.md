# PDF Metadata-First Semantic AOI Grouping Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan checkpoint by checkpoint. Do not dispatch subagents unless the user explicitly requests them.

**Goal:** Produce paragraph-level text AOIs from PDF layout metadata, exclude non-content text, strengthen LLM grouping with anchor provenance, and merge compatible LLM fragments safely.

**Architecture:** Preserve PyMuPDF block, line, and span metadata in TextBox; classify roles and group text with a hierarchy-first deterministic grouper; then pass paragraph anchors to prompt version 2. Text-like LLM AOIs reference anchor_ids and receive program-derived bounding boxes, while visual AOIs retain validated model boxes.

**Tech Stack:** Python 3.10, dataclasses, PyMuPDF 1.24+, unittest, existing OpenAI-compatible vision endpoint.

## Global Constraints

- Target repository: /home/charles/repos/AttentiveSlides-eyetheia-local-gaze-integration
- Target branch: codex/eyetheia-local-gaze-integration
- Semantic unit: one visual paragraph or one list item.
- Multiple complete sentences in one paragraph remain one AOI.
- Rendered line breaks never create AOI boundaries.
- Titles, standalone headings, recurring headers, footers, and page numbers are excluded from content AOIs.
- Excluded text remains in slide_text and debug metadata.
- whole_slide remains only as a technical fallback.
- Do not add dependencies.
- Do not run a baseline suite or expected-failing RED tests.
- After each checkpoint, run exactly the listed focused GREEN group.
- Perform one independent whole-change review after all implementation checkpoints.
- Run the full suite once after implementation and any bounded review-fix wave.
- No subagents unless explicitly requested by the user.

## Target File Map

- Modify modules/slide/ocr.py: extend TextBox with optional PDF layout metadata.
- Modify modules/slide/slide_parser.py: preserve PDF metadata and compute cached repeated-margin text.
- Create modules/slide/aoi_grouping.py: role classification, block segmentation, and cross-block continuation.
- Modify modules/slide/aoi_manager.py: integrate grouping, excluded regions, schema versioning, effective AOI filtering, and LLM reconciliation.
- Modify modules/slide/llm_aoi.py: prompt version 2, anchor_ids schema, and validation.
- Create tests/test_pdf_aoi_grouping.py: deterministic extraction and grouping regression coverage.
- Modify tests/test_llm_aoi.py: prompt, provenance, output merge, and cache invalidation coverage.
- Modify tests/test_real_slide_provider.py only if effective-AOI assertions require explicit exclusion coverage.
- Modify tests/test_uploaded_deck_service.py only if stale deterministic-version regeneration changes service expectations.

---

### Checkpoint 1: Preserve PDF Layout Metadata

**Files:**

- Modify: modules/slide/ocr.py
- Modify: modules/slide/slide_parser.py
- Create: tests/test_pdf_aoi_grouping.py

**Interfaces:**

- Produces: TextBox optional fields block_id, line_id, block_bbox, font_size, font_family, font_flags, direction, starts_bullet.
- Produces: SlideParser.extract_pdf_margin_profile(deck_id: str) -> tuple[frozenset[str], frozenset[str]].
- Preserves: all existing four-argument TextBox construction.

- [ ] **Step 1: Extend TextBox without breaking OCR callers**

Add these defaulted fields after source in modules/slide/ocr.py:

~~~python
@dataclass
class TextBox:
    text: str
    bbox: list[float]
    confidence: float
    source: str
    block_id: int | None = None
    line_id: int | None = None
    block_bbox: list[float] | None = None
    font_size: float | None = None
    font_family: str | None = None
    font_flags: int | None = None
    direction: tuple[float, float] | None = None
    starts_bullet: bool = False
~~~

Keep all current geometry properties unchanged.

- [ ] **Step 2: Extract dominant line metadata from PyMuPDF spans**

Add focused helpers to modules/slide/slide_parser.py:

~~~python
BULLET_PREFIXES = ("•", "❒", "▪", "◦", "‣", "–", "—")


def _normalized_bbox(
    bbox: list[float] | tuple[float, ...],
    page_width: float,
    page_height: float,
) -> list[float]:
    x1, y1, x2, y2 = (float(value) for value in bbox)
    return [
        clamp(x1 / page_width),
        clamp(y1 / page_height),
        clamp(x2 / page_width),
        clamp(y2 / page_height),
    ]


def _dominant_text_span(spans: list[dict[str, Any]]) -> dict[str, Any] | None:
    candidates = [
        span
        for span in spans
        if str(span.get("text", "")).strip()
        and "dingbat" not in str(span.get("font", "")).casefold()
        and not str(span.get("text", "")).strip().startswith(BULLET_PREFIXES)
    ]
    if not candidates:
        candidates = [span for span in spans if str(span.get("text", "")).strip()]
    return max(
        candidates,
        key=lambda span: len(str(span.get("text", "")).strip()),
        default=None,
    )
~~~

Refactor extract_pdf_text_boxes so each emitted line records:

~~~python
TextBox(
    text=text,
    bbox=line_bbox,
    confidence=1.0,
    source="pdf_text",
    block_id=int(block.get("number", block_index)),
    line_id=line_index,
    block_bbox=_normalized_bbox(block["bbox"], page_width, page_height),
    font_size=float(dominant.get("size", 0.0)) if dominant else None,
    font_family=str(dominant.get("font", "")) if dominant else None,
    font_flags=int(dominant.get("flags", 0)) if dominant else None,
    direction=tuple(float(value) for value in line.get("dir", (1.0, 0.0))),
    starts_bullet=_starts_list_marker(text),
)
~~~

Use the line bbox from PyMuPDF rather than recomputing it only from text spans. Fall back
to the current span union if line bbox is missing.

- [ ] **Step 3: Add cached recurring margin extraction**

Implement a private cache keyed by resolved PDF path and file modification time. Scan
page.get_text("dict") without rendering. Normalize candidate text and count strings in the
top 0.12 and bottom 0.12 page bands.

The public method has the exact signature
SlideParser.extract_pdf_margin_profile(deck_id: str) ->
tuple[frozenset[str], frozenset[str]]. It validates deck_id through the existing metadata
lookup, resolves the PDF path and mtime, and delegates to the cached scanner.

A string is repeated when it appears on at least:

~~~python
max(2, math.ceil(page_count * 0.30))
~~~

Return separate top and bottom normalized-text sets. Do not write them into
deck_metadata.json.

- [ ] **Step 4: Add focused metadata tests**

Create tests/test_pdf_aoi_grouping.py with a PDF-page dictionary fixture containing:

- a Dingbats bullet span followed by regular body spans;
- two lines sharing a block;
- line and block bboxes;
- font size, font family, flags, and direction.

Add these tests:

~~~python
class PDFMetadataExtractionTest(unittest.TestCase):
    def test_text_box_defaults_preserve_ocr_construction(self):
        box = TextBox("body", [0.1, 0.2, 0.4, 0.3], 0.9, "ocr")
        self.assertIsNone(box.block_id)
        self.assertFalse(box.starts_bullet)

    def test_pdf_line_keeps_block_style_direction_and_bullet_metadata(self):
        boxes = extract_with_mock_page(PDF_PAGE_DICT)
        first = boxes[0]
        self.assertEqual(first.block_id, 12)
        self.assertEqual(first.line_id, 0)
        self.assertEqual(first.font_family, "NimbusSanL-Regu")
        self.assertAlmostEqual(first.font_size, 8.432389, places=5)
        self.assertEqual(first.direction, (1.0, 0.0))
        self.assertTrue(first.starts_bullet)
        self.assertIsNotNone(first.block_bbox)

    def test_margin_profile_requires_recurrence_in_same_band(self):
        top, bottom = margin_profile_with_mock_pages()
        self.assertIn("course header", top)
        self.assertIn("7/55", bottom)
        self.assertNotIn("unique slide body", top | bottom)
~~~

- [ ] **Step 5: Run the checkpoint GREEN group**

Run:

~~~bash
/home/charles/miniconda3/envs/pyboe/bin/python -m unittest tests.test_pdf_aoi_grouping.PDFMetadataExtractionTest -v
~~~

Expected: all PDFMetadataExtractionTest tests pass.

- [ ] **Step 6: Commit checkpoint 1**

~~~bash
git add modules/slide/ocr.py modules/slide/slide_parser.py tests/test_pdf_aoi_grouping.py
git commit -m "feat: preserve PDF layout metadata for AOI grouping"
~~~

---

### Checkpoint 2: Deterministic Paragraph Grouping and Role Exclusion

**Files:**

- Create: modules/slide/aoi_grouping.py
- Modify: modules/slide/aoi_manager.py
- Modify: tests/test_pdf_aoi_grouping.py

**Interfaces:**

- Consumes: enriched TextBox and SlideParser.extract_pdf_margin_profile.
- Produces: group_pdf_text(lines, repeated_top_text, repeated_bottom_text) -> GroupingResult.
- Produces: text_groups_are_continuous(first: TextGroup, second: TextGroup, profile: PageLayoutProfile) -> bool.
- Produces: AUTO_AOI_SCHEMA_VERSION = "pdf-semantic-v2".
- Produces: AOI.role: str | None for paragraph/list layout provenance.

- [ ] **Step 1: Add grouping data types and role constants**

Create modules/slide/aoi_grouping.py:

~~~python
from __future__ import annotations

from dataclasses import dataclass
from statistics import median

from .ocr import TextBox


CONTENT_ROLES = frozenset({"paragraph", "list_item"})
EXCLUDED_ROLES = frozenset(
    {"title", "heading", "header", "footer", "page_number"}
)


@dataclass(frozen=True)
class PageLayoutProfile:
    median_font_size: float
    median_line_height: float
    repeated_top_text: frozenset[str]
    repeated_bottom_text: frozenset[str]


@dataclass
class TextGroup:
    role: str
    lines: list[TextBox]

    @property
    def text(self) -> str:
        return " ".join(line.text.strip() for line in self.lines if line.text.strip())

    @property
    def bbox(self) -> list[float]:
        return [
            min(line.x_min for line in self.lines),
            min(line.y_min for line in self.lines),
            max(line.x_max for line in self.lines),
            max(line.y_max for line in self.lines),
        ]


@dataclass
class GroupingResult:
    content_groups: list[TextGroup]
    excluded_groups: list[TextGroup]
~~~

- [ ] **Step 2: Implement deterministic role classification**

Add these exact functions:

- normalize_text(text: str) -> str normalizes case, punctuation, and whitespace for
  recurrence matching.
- starts_list_marker(text: str) -> bool recognizes the configured glyph bullets and
  numbered markers matching ^[0-9]+[.)].
- build_page_layout_profile(lines: list[TextBox], repeated_top_text:
  frozenset[str], repeated_bottom_text: frozenset[str]) -> PageLayoutProfile computes
  median non-zero font size and line height after removing repeated margins and page
  numbers.
- classify_line_role(line: TextBox, profile: PageLayoutProfile) -> str returns exactly one
  of header, footer, page_number, title, heading, list_item, or paragraph.

Required decisions:

- repeated normalized top text is header;
- repeated normalized bottom text is footer;
- page-number patterns in the bottom band are page_number;
- an independent bold/enlarged line is title when it is in the top quarter and heading
  otherwise;
- ordinary text is list_item when starts_bullet is true, paragraph otherwise;
- inline bold does not trigger heading because TextBox stores the dominant body span.

Use relative font size and line-height values from PageLayoutProfile. Keep threshold
constants named at module scope so regression tests can document them.

- [ ] **Step 3: Implement block-first grouping**

Add group_pdf_text(lines: list[TextBox], repeated_top_text:
frozenset[str] = frozenset(), repeated_bottom_text: frozenset[str] = frozenset()) ->
GroupingResult. It builds the profile, assigns a role to every sorted line, performs
within-block segmentation, performs one cross-block repair pass, and partitions the final
groups into content_groups and excluded_groups.

Within a block, keep consecutive body lines together. Split on:

- a new list marker after the first line;
- role transition;
- direction change;
- incompatible dominant style;
- vertical gap greater than the profile-relative paragraph threshold;
- column discontinuity.

Do not split on sentence-ending punctuation.

- [ ] **Step 4: Implement cross-block continuation**

Add the reusable predicate text_groups_are_continuous(first: TextGroup, second:
TextGroup, profile: PageLayoutProfile) -> bool.

It returns true only when:

- both roles are in CONTENT_ROLES;
- second does not begin a new list marker;
- directions and dominant body styles are compatible;
- vertical gap is within the configured multiple of median line height;
- the groups occupy the same column;
- left alignment, horizontal overlap, or hanging indentation is compatible.

Never merge groups only because they share a horizontal row. Remove the old
_semantic_pair_confidence horizontal-pair behavior from the PDF semantic path.

- [ ] **Step 5: Integrate grouping and excluded regions in AOIManager**

In modules/slide/aoi_manager.py:

~~~python
AUTO_AOI_SCHEMA_VERSION = "pdf-semantic-v2"
~~~

Extend SlideAOIData with defaulted fields:

~~~python
excluded_text_regions: list[dict[str, Any]] | None = None
auto_aoi_version: str = AUTO_AOI_SCHEMA_VERSION
~~~

Add a defaulted role: str | None = None field to AOI. Update _aoi_from_dict and all
explicit AOI reconstruction paths to preserve role. AOI.to_dict already uses asdict and
therefore persists non-None role.

Update process_slide to:

1. obtain repeated top/bottom sets from SlideParser;
2. call group_pdf_text for PDF text;
3. convert only content_groups to pdf_text_semantic AOIs;
4. store excluded_groups under excluded_text_regions;
5. keep all lines in slide_text;
6. persist auto_aoi_version.

Update _text_box_child to retain optional layout fields. Omit fields whose value is None.

Update effective deterministic AOI selection:

- prefer semantic content AOIs;
- exclude title, heading, header, footer, and page_number;
- use coarse rule AOIs only when semantic content is empty;
- append whole_slide exactly once.

Update process_llm_aoi and _ensure_slide_data to call process_slide when
auto_aoi_version is missing or differs from AUTO_AOI_SCHEMA_VERSION.

- [ ] **Step 6: Add deterministic grouping regressions**

Add PDFParagraphGroupingTest tests named:

- test_same_block_wrapped_lines_form_one_paragraph;
- test_multiple_sentences_in_same_block_remain_one_paragraph;
- test_new_bullet_in_same_block_starts_new_aoi;
- test_real_slide_8_cross_block_continuation_merges;
- test_adjacent_columns_do_not_merge;
- test_title_heading_header_footer_and_page_number_are_excluded;
- test_inline_bold_body_text_is_retained;
- test_stale_auto_aoi_version_forces_reprocessing.

Each test asserts the exact content-group count, group role, joined text, union bbox, and
excluded roles relevant to its fixture. The stale-version test patches process_slide,
loads a record without pdf-semantic-v2, calls process_llm_aoi, and asserts one reprocess
call before LLM generation.

Use the recorded page-8 normalized coordinates:

~~~python
first = TextBox(
    "❒ It encompasses a wide variety of states, such as",
    [0.4813228811, 0.3113853053, 0.9228071452, 0.3662475159],
    1.0,
    "pdf_text",
    block_id=13,
    line_id=0,
    font_size=8.518,
    font_family="NimbusSanL-Regu",
    font_flags=4,
    direction=(1.0, 0.0),
    starts_bullet=True,
)
second = TextBox(
    "perception, thinking, fantasizing, dreaming, and altered",
    [0.5083544846, 0.3689701320, 0.9759829030, 0.4100],
    1.0,
    "pdf_text",
    block_id=14,
    line_id=0,
    font_size=8.518,
    font_family="NimbusSanL-Regu",
    font_flags=4,
    direction=(1.0, 0.0),
)
~~~

Assert one list_item group with union bbox and joined text.

- [ ] **Step 7: Run the checkpoint GREEN group**

Run:

~~~bash
/home/charles/miniconda3/envs/pyboe/bin/python -m unittest tests.test_pdf_aoi_grouping -v
~~~

Expected: all metadata and grouping tests pass.

- [ ] **Step 8: Commit checkpoint 2**

~~~bash
git add modules/slide/aoi_grouping.py modules/slide/aoi_manager.py tests/test_pdf_aoi_grouping.py
git commit -m "feat: group PDF text into semantic paragraph AOIs"
~~~

---

### Checkpoint 3: Prompt Version 2 and Anchor Provenance

**Files:**

- Modify: modules/slide/llm_aoi.py
- Modify: modules/slide/aoi_manager.py
- Modify: tests/test_llm_aoi.py

**Interfaces:**

- Consumes: paragraph-level content AOIs.
- Produces: raw LLM text AOIs with anchor_ids: list[str].
- Produces: AOI.anchor_ids: list[str] | None.
- Changes prompt cache version to attentive-llm-aoi-v2.

- [ ] **Step 1: Extend AOI and LLM validation with anchor IDs**

Add a defaulted field to AOI after role:

~~~python
anchor_ids: list[str] | None = None
~~~

In LLMAOIGenerator._validate_aois, preserve unique non-empty string anchor IDs:

~~~python
anchor_ids = list(dict.fromkeys(
    str(value).strip()
    for value in item.get("anchor_ids", [])
    if str(value).strip()
))
~~~

Change validation order:

- text-like items are retained when anchor_ids is non-empty, even when bbox is absent;
- a valid text bbox may be retained temporarily but is not required;
- visual items require a valid bbox and are rejected without one;
- build_llm_guided_aois skips _validate_bbox only for anchored text-like items;
- _aoi_from_dict preserves role and anchor_ids.

- [ ] **Step 2: Send compact content anchors**

Change _llm_prompt_aoi output for grounding AOIs to:

~~~python
{
    "anchor_id": aoi.aoi_id,
    "role": aoi.role or aoi.type,
    "text": aoi.text,
    "bbox": [float(value) for value in aoi.bbox],
    "line_count": len(aoi.children or []),
}
~~~

Do not send excluded regions, raw font metadata, or child lines.

- [ ] **Step 3: Replace the prompt with the approved paragraph contract**

Set:

~~~python
PROMPT_SCHEMA_VERSION = "attentive-llm-aoi-v2"
~~~

The prompt must explicitly contain:

- "One visual paragraph or one list item equals one text AOI."
- "Rendered line wrapping is never an AOI boundary."
- "Keep multiple complete sentences together when they share one visual paragraph."
- "Do not return titles, headings, headers, footers, or page numbers."
- "Every text-like AOI must return anchor_ids."
- "Visual AOIs without text anchors may return bbox."

Include a positive example where three wrapped lines become one AOI and a forbidden example
showing three line-level AOIs.

- [ ] **Step 4: Add prompt and validation tests**

Add LLMAOIPromptV2Test tests named:

- test_prompt_defines_visual_paragraph_not_sentence_or_line;
- test_prompt_excludes_non_content_roles;
- test_prompt_requires_anchor_ids_for_text_aois;
- test_validation_preserves_clean_anchor_ids;
- test_prompt_schema_version_invalidates_v1_profile.

The first three inspect the generated prompt for the exact required contract sentences.
The validation test supplies blank and duplicate IDs and asserts only unique non-empty
strings remain. The profile test compares v1-equivalent and v2 profile inputs and asserts
the persisted v1 profile is not eligible.

Also add:

- test_anchored_text_without_bbox_is_valid;
- test_visual_item_without_bbox_is_rejected.

Update the llm_item helper to accept anchor_ids and use the seeded paragraph anchor by
default.

- [ ] **Step 5: Run the checkpoint GREEN group**

Run:

~~~bash
/home/charles/miniconda3/envs/pyboe/bin/python -m unittest tests.test_llm_aoi -v
~~~

Expected: all LLM AOI tests pass.

- [ ] **Step 6: Commit checkpoint 3**

~~~bash
git add modules/slide/llm_aoi.py modules/slide/aoi_manager.py tests/test_llm_aoi.py
git commit -m "feat: ground LLM text AOIs with paragraph anchors"
~~~

---

### Checkpoint 4: Provenance-Aware Reconciliation and Output Merge

**Files:**

- Modify: modules/slide/aoi_manager.py
- Modify: tests/test_llm_aoi.py
- Modify if required by changed effective selection: tests/test_real_slide_provider.py
- Modify if required by regeneration: tests/test_uploaded_deck_service.py

**Interfaces:**

- Consumes: LLM AOIs containing anchor_ids and paragraph grounding AOIs.
- Produces: reconciled text AOIs whose bbox is derived from grounding anchors.
- Preserves: validated model bboxes for visual AOIs.

- [ ] **Step 1: Resolve text AOIs from anchor provenance**

Add helpers:

~~~python
TEXT_AOI_TYPES = frozenset(
    {"title", "text", "caption", "footer", "axis_label"}
)
VISUAL_AOI_TYPES = frozenset(
    {"code", "diagram", "figure", "table", "formula", "mixed"}
)


def _resolve_text_aoi_anchors(
    self,
    aoi: AOI,
    grounding_by_id: dict[str, AOI],
) -> AOI | None:
    anchor_ids = list(dict.fromkeys(aoi.anchor_ids or []))
    anchors = [grounding_by_id[value] for value in anchor_ids if value in grounding_by_id]
    if len(anchors) != len(anchor_ids) or not anchors:
        return None
    aoi.anchor_ids = anchor_ids
    aoi.text = " ".join(anchor.text.strip() for anchor in anchors if anchor.text.strip())
    aoi.bbox = self._merged_aoi_bbox(anchors)
    return aoi
~~~

Add the exact bbox helper:

~~~python
@staticmethod
def _merged_aoi_bbox(aois: list[AOI]) -> list[float]:
    return [
        min(aoi.bbox[0] for aoi in aois),
        min(aoi.bbox[1] for aoi in aois),
        max(aoi.bbox[2] for aoi in aois),
        max(aoi.bbox[3] for aoi in aois),
    ]
~~~

Required behavior:

- reject text AOIs without anchor_ids;
- reject unknown or excluded-role anchors and deduplicate repeated anchor IDs;
- preserve anchor order from grounding_aois, not model order;
- derive bbox by union of referenced anchors;
- derive canonical text by joining referenced anchor text;
- retain normalized model text only when it agrees with canonical anchor tokens;
- retain visual AOIs through existing bbox validation.

- [ ] **Step 2: Merge compatible split text outputs**

Add:

~~~python
def _merge_llm_text_fragments(
    self,
    aois: list[AOI],
    grounding_aois: list[AOI],
) -> list[AOI]:
    grounding_order = {
        aoi.aoi_id: index for index, aoi in enumerate(grounding_aois)
    }
    return self._merge_ordered_text_candidates(aois, grounding_aois, grounding_order)
~~~

_merge_ordered_text_candidates is a private loop that appends the first candidate, tests
each later candidate against the last appended candidate, and either appends it or replaces
the last item with their union. It uses the exact merge conditions below; it must not
contain an additional fuzzy-text or punctuation-only merge path.

Merge when:

- both AOIs are text-like;
- their anchor sets are consecutive in grounding order;
- they do not introduce a new list marker;
- the underlying child TextBox metadata satisfies text_groups_are_continuous;
- neither references an excluded role.

Always merge AOIs that reference the same anchor set. Recompute bbox, canonical text,
anchor_ids, and confidence. Keep the lower confidence of merged fragments.

- [ ] **Step 3: Rebuild reconciliation order**

reconcile_llm_aois performs:

1. provenance resolution for text AOIs;
2. visual AOI bbox validation and area filtering;
3. same-anchor deduplication;
4. compatible text-fragment merge;
5. high-IoU category deduplication;
6. stable spatial ordering;
7. text coverage check;
8. stable llm_aoi numbering.

Remove the current exact-full-text bbox snapping path after provenance resolution replaces
it. Keep the existing fallback_used behavior when no usable result remains.

- [ ] **Step 4: Add reconciliation regressions**

Add LLMAOIProvenanceReconciliationTest tests named:

- test_text_bbox_is_union_of_referenced_anchors;
- test_unknown_or_excluded_anchor_is_rejected;
- test_same_anchor_split_outputs_collapse_to_one_aoi;
- test_continuous_anchor_outputs_merge;
- test_new_bullet_anchor_outputs_remain_separate;
- test_visual_aoi_keeps_valid_model_bbox;
- test_low_grounding_coverage_still_falls_back.

Each test constructs explicit grounding AOIs with child layout metadata. Assert exact
anchor_ids, canonical text, bbox union, final count, and fallback state rather than only
asserting truthiness.

Update provider or workspace tests only where their asserted effective AOI lists now
exclude non-content regions or trigger version regeneration.

- [ ] **Step 5: Run the checkpoint GREEN group**

Run:

~~~bash
/home/charles/miniconda3/envs/pyboe/bin/python -m unittest tests.test_llm_aoi tests.test_real_slide_provider tests.test_uploaded_deck_service -v
~~~

Expected: all listed tests pass.

- [ ] **Step 6: Commit checkpoint 4**

~~~bash
git add modules/slide/aoi_manager.py tests/test_llm_aoi.py tests/test_real_slide_provider.py tests/test_uploaded_deck_service.py
git commit -m "fix: reconcile LLM AOIs by anchor provenance"
~~~

If either optional test file is unchanged, omit it from git add.

---

### Checkpoint 5: Whole-Change Review and Final Verification

**Files:**

- Review all files changed by checkpoints 1 through 4.
- Modify only files required by Critical or Important review findings.

**Interfaces:**

- Consumes: the complete implementation.
- Produces: reviewed, verified branch ready for handoff.

- [ ] **Step 1: Perform one independent whole-change review**

Review the complete diff against:

- the confirmed semantic boundary;
- the design specification;
- cache and manifest invalidation;
- two-column separation;
- bullet boundaries;
- title/header/footer exclusion;
- OCR compatibility;
- text versus visual LLM AOI behavior;
- accidental API or persisted-schema breakage.

Record findings as Critical, Important, or Minor. Do not dispatch a subagent unless the
user explicitly requests one.

- [ ] **Step 2: Apply one bounded fix wave if required**

Address all Critical and Important findings in one wave. Do not broaden scope. If code
changes, run only the directly affected focused module once.

- [ ] **Step 3: Run the full suite once**

Run:

~~~bash
/home/charles/miniconda3/envs/pyboe/bin/python -m unittest discover -s tests -v
~~~

Expected: the full discovered test suite passes.

If the full suite fails due to a final-review change, fix only the affected module and
rerun the full suite at most once, as allowed by the Lean Profile.

- [ ] **Step 4: Inspect final repository state**

Run:

~~~bash
git status --short --branch
git log -6 --oneline --decorate
~~~

Expected: no unintended files; checkpoint commits are present; the branch remains
codex/eyetheia-local-gaze-integration.

- [ ] **Step 5: Commit final-review fixes if any**

~~~bash
git add modules/slide/ocr.py modules/slide/slide_parser.py modules/slide/aoi_grouping.py modules/slide/aoi_manager.py modules/slide/llm_aoi.py tests/test_pdf_aoi_grouping.py tests/test_llm_aoi.py tests/test_real_slide_provider.py tests/test_uploaded_deck_service.py
git commit -m "fix: address semantic AOI review findings"
~~~

Skip this commit when the review finds no Critical or Important issues.

## Execution Ledger Template

Maintain only:

~~~text
Checkpoint N: complete | focused GREEN: command and count | commit: hash
Blocker: none
Next: Checkpoint N+1
~~~

Do not repeat passing tests after commits, compacting, or documentation-only changes.
