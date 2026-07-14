# PDF Metadata-First Semantic AOI Grouping Design

**Date:** 2026-07-15

**Status:** Approved for implementation planning

**Target repository:** /home/charles/repos/AttentiveSlides-eyetheia-local-gaze-integration

**Target branch:** codex/eyetheia-local-gaze-integration

## Objective

Generate content AOIs at the visual-paragraph level rather than the rendered-line level.
A paragraph remains one AOI when it wraps across lines or contains multiple complete
sentences. Each bullet or numbered list item is a separate AOI. Slide titles, standalone
headings, recurring headers, footers, and page numbers are excluded from content AOIs.

The solution must use PDF-native layout metadata first, then deterministic cross-block
repair, a strengthened vision-LLM prompt, and a final provenance-aware reconciliation
pass.

## Confirmed Semantic Boundary

- One visual paragraph is one content AOI.
- Two or three complete sentences in the same visual paragraph remain one AOI.
- Automatic line wrapping never creates a new AOI.
- One bullet or numbered list item is one AOI, including all of its continuation lines.
- A new bullet or numbered marker starts a new AOI.
- Titles, standalone section headings, recurring headers, footers, and page numbers are
  not content AOIs.
- Excluded text remains available in slide text and debug data.
- whole_slide remains only as a technical gaze fallback and is not a content AOI.

## Evidence from the Existing Runtime

PyMuPDF returns blocks, lines, and spans from page.get_text("dict"), including block and
line bounding boxes, font name, font size, style flags, origin, writing mode, and text
direction.

On lecture_10_human_mind.pdf, page 8:

- The two lines beginning "Consciousness is the awareness..." and "circumstances." share
  PDF block 12.
- The two lines beginning "Unconscious mental process operates..." and "individual's
  awareness." share PDF block 16.
- Another bullet begins in block 13 while its continuation lines are in block 14.

Therefore PDF block membership is a strong signal but cannot be the only grouping rule.

The current SlideParser discards this structure and emits TextBox values containing only
text, bbox, confidence, and source. The current wrapped-line rule also requires an absolute
left-edge delta of at most 0.025. A real continuation indentation of approximately 0.027
therefore remains split. The LLM receives split grounding anchors and returns them as
separate AOIs. Reconciliation validates and deduplicates them but does not merge adjacent
text fragments.

## Chosen Architecture

Use a hierarchy-first hybrid pipeline:

1. Preserve PDF block, line, span-style, direction, and bullet metadata.
2. Classify and remove non-content text roles.
3. Group lines within each PDF block.
4. Repair false block boundaries using compatible typography and geometry.
5. Send paragraph-level anchors to the LLM with stable anchor identifiers.
6. Derive text AOI bounding boxes from referenced anchors.
7. Merge only provenance-compatible text fragments in the final reconciliation pass.

PDF structure is authoritative when it is consistent. Geometry and typography repair
known PDF-export artifacts. The LLM is not responsible for recreating line layout.

## Data Model

Extend the shared TextBox with optional PDF layout fields while preserving OCR callers:

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

PDF lines populate these fields. OCR boxes leave them unset and continue to use geometric
grouping.

When a PDF line contains multiple spans:

- Ignore Dingbats or symbol-only bullet spans when choosing the dominant body style.
- Choose the dominant font family and flags by visible character count.
- Compute representative font size from non-symbol text spans.
- Detect a bullet or numbered marker independently from the body font.
- Preserve the normalized block bbox and line bbox.

Introduce focused grouping types in modules/slide/aoi_grouping.py:

~~~python
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

## Deck and Page Layout Profile

Build a lightweight deck profile from PDF-native text, cached by PDF path and file
modification time for the life of the process.

Repeated margin text is a normalized string appearing in a consistent top or bottom band
on at least max(2, ceil(page_count * 0.30)) pages. The scan records only text and position;
it does not render pages or invoke OCR.

The page profile computes median body font size and median line height after removing
obvious margin text and page numbers. These values make thresholds relative to the slide's
actual typography rather than hard-coded normalized coordinates.

## Non-Content Role Classification

Classify lines before paragraph grouping:

- header: repeated top-band text.
- footer: repeated bottom-band text or a bottom-band line with footer typography.
- page_number: a bottom-band line matching a page-number form such as 7, 7/55, or 7 of 55.
- title: a standalone top-region line with title typography.
- heading: an independent bold or enlarged line separated from surrounding body text.
- paragraph: normal prose.
- list_item: a bullet or numbered item and its continuation lines.

Title and heading detection uses a combination of relative font size, bold flags, line
length, position, and surrounding vertical whitespace. Font size alone is not sufficient.
Inline bold spans inside an otherwise body-style line do not make that line a heading.

Excluded groups are stored in slide data under excluded_text_regions for diagnostics and
remain represented in slide_text. They are not passed as grounding anchors and cannot
become effective semantic AOIs.

## Paragraph Grouping

### Pass 1: Within-Block Segmentation

Lines with the same block_id are processed in PDF order. They remain in one group unless a
hard boundary occurs:

- a new bullet or numbered marker;
- a content-role transition;
- a large vertical gap relative to median line height;
- a significant dominant-font or relative-size change;
- a direction change;
- a column discontinuity.

Sentence-ending punctuation is not a hard boundary. This preserves multi-sentence
paragraphs.

### Pass 2: Cross-Block Repair

Adjacent groups from different block IDs merge when all required conditions hold:

- both are paragraph/list content roles;
- the second does not start a new bullet or number;
- dominant body font families are compatible;
- font-size ratio is within the configured body-style tolerance;
- directions match;
- vertical gap is within the page-relative continuation threshold;
- the groups occupy the same column;
- left alignment, horizontal overlap, or hanging indentation is compatible.

The continuation indentation threshold is derived from median line height. It replaces the
current absolute 0.025 left-edge rule.

Groups never merge merely because they are horizontally adjacent on the same row. This
removes the current failure in which a section heading in one column can be combined with
a bullet in another column.

### OCR Fallback

OCR lacks block and font metadata. Existing geometric grouping remains the fallback, but
it uses the same bullet boundaries, paragraph semantics, and role-exclusion contract when
the necessary signal is available.

## AOI Persistence and Versioning

Add an AUTO_AOI_SCHEMA_VERSION constant with value pdf-semantic-v2 and persist it as
auto_aoi_version in each slide record.

process_slide writes the version. process_llm_aoi and slide-data loading reprocess a slide
when:

- auto_aoi_version is absent or stale;
- the rendered image DPI is stale;
- the slide record is absent.

This is required because existing manifest entries otherwise keep old line-level anchors
after the code changes. Reprocessing invalidates the anchor digest and cached LLM variant.

Each content AOI keeps child line provenance:

~~~json
{
  "aoi_id": "pdf_paragraph_3",
  "type": "text",
  "role": "list_item",
  "text": "A complete wrapped list item.",
  "bbox": [0.48, 0.31, 0.98, 0.46],
  "source": "pdf_text_semantic",
  "children": [
    {
      "text": "A complete wrapped",
      "bbox": [0.48, 0.31, 0.92, 0.36],
      "block_id": 13,
      "line_id": 0,
      "font_size": 8.52,
      "font_family": "NimbusSanL-Regu",
      "starts_bullet": true
    }
  ]
}
~~~

AOI gains optional role and anchor_ids fields. type remains the existing broad content
category used by downstream consumers; role records paragraph, list_item, or another
layout role without expanding ALLOWED_AOI_TYPES.

Rule regions remain internal coarse hints. Effective semantic AOI selection prefers content
anchors and uses rule regions only when no semantic content exists. title/header/footer
rules are never surfaced as content AOIs. whole_slide is appended only as the technical
fallback.

## LLM Input and Prompt Version 2

Pass compact paragraph-level grounding anchors:

~~~json
{
  "anchor_id": "pdf_paragraph_3",
  "role": "list_item",
  "text": "A complete wrapped list item.",
  "bbox": [0.48, 0.31, 0.98, 0.46],
  "line_count": 3
}
~~~

Do not send raw font metadata to the LLM. The deterministic grouping layer consumes it,
and omitting it reduces tokens and prevents the model from treating individual lines as
separate objects.

Prompt version 2 states:

- the semantic unit is a visual paragraph or one list item;
- a rendered line break is never an AOI boundary;
- multiple sentences in one paragraph remain one AOI;
- grounding anchors are preferred provenance;
- title, heading, header, footer, and page number content must not be returned;
- text AOIs return anchor_ids;
- visual AOIs without text anchors may return a model bbox.

Include one positive wrapped-paragraph example and one forbidden line-per-AOI example.
Set PROMPT_SCHEMA_VERSION to attentive-llm-aoi-v2 so cached version-1 results are not
reused.

## Provenance-Aware LLM Output

Text AOIs return:

~~~json
{
  "aoi_id": "llm_aoi_1",
  "type": "text",
  "anchor_ids": ["pdf_paragraph_3"],
  "text": "A complete wrapped list item.",
  "confidence": 0.92
}
~~~

For text-like AOIs:

- every anchor ID must exist and refer to content;
- model bbox is optional and ignored when anchor provenance resolves;
- bbox is the union of referenced anchor bboxes;
- text is checked against referenced anchor text;
- excluded anchor references are rejected;
- ambiguous unanchored text is discarded rather than trusting an invented bbox.

Visual AOIs such as figures, diagrams, tables, formulas, and code panels require and retain
validated model-generated bounding boxes.

## Final Reconciliation

After validation:

1. Resolve text bboxes from anchor provenance.
2. Deduplicate identical anchor sets.
3. Merge adjacent text outputs only when their referenced grounding groups are consecutive
   and the shared deterministic continuation predicate says they belong together.
4. Never merge across a new bullet, excluded role, column boundary, or incompatible style.
5. Recompute text, bbox union, confidence, and stable AOI numbering.
6. Preserve the current text-coverage safeguard and whole-slide-area rejection.

This pass is a guardrail, not a second page-layout parser.

## Error Handling and Compatibility

- Missing PDF metadata falls back to geometric behavior.
- Unknown or malformed LLM anchor_ids cause the individual text AOI to be rejected.
- If all LLM AOIs are rejected, retain the current fallback_used behavior.
- Existing OCR-only decks remain supported.
- Existing manifests are migrated by deterministic reprocessing, not in-place mutation.
- No new third-party dependency is required; PyMuPDF 1.24 or newer is already required.

## Verification Contract

Regression fixtures must cover:

- same-block wrapped paragraph;
- same-block paragraph containing multiple complete sentences;
- same-block multiple bullets;
- cross-block continuation using the real page-8 geometry;
- different columns that must not merge;
- title and standalone heading exclusion;
- repeated header, footer, and page-number exclusion;
- inline bold text retained as paragraph content;
- LLM text bbox derived from anchor_ids;
- split LLM outputs merged through provenance;
- visual AOI bbox retained;
- stale auto_aoi_version forces deterministic regeneration.

Execution follows the repository Lean Profile:

- no baseline suite;
- no RED run;
- one focused GREEN group after each checkpoint;
- one independent whole-change review after implementation;
- one full test suite after review fixes, if any.

## Out of Scope

- Tagged-PDF structure trees and accessibility reading order.
- Machine-learned paragraph classifiers.
- OCR engine replacement.
- Changes to gaze coordinate normalization.
- UI redesign.
