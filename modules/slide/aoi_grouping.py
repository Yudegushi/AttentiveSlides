from __future__ import annotations

import re
from dataclasses import dataclass
from statistics import median

from .ocr import TextBox


CONTENT_ROLES = frozenset({"paragraph", "list_item"})
EXCLUDED_ROLES = frozenset({"title", "heading", "header", "footer", "page_number"})

BULLET_PREFIXES = ("•", "❒", "▪", "◦", "‣", "–", "—")
NUMBERED_LIST_PATTERN = re.compile(r"^\s*\d+[.)](?:\s|$)")
PAGE_NUMBER_PATTERN = re.compile(r"^\s*\d+(?:\s*(?:/|of)\s*\d+)?\s*$", re.IGNORECASE)

TOP_MARGIN_BAND = 0.12
BOTTOM_MARGIN_BAND = 0.88
TITLE_REGION_BOTTOM = 0.25
TITLE_FONT_RATIO = 1.30
HEADING_FONT_RATIO = 1.18
BOLD_FONT_FLAG = 16
BOLD_HEADING_MIN_RATIO = 1.05
STYLE_SIZE_RATIO = 0.82
WITHIN_BLOCK_GAP_MULTIPLIER = 1.65
CROSS_BLOCK_GAP_MULTIPLIER = 1.80
COLUMN_OVERLAP_RATIO = 0.25
ALIGNMENT_LINE_HEIGHT_MULTIPLIER = 2.75
DIRECTION_TOLERANCE = 0.05
BODY_FONT_SAMPLE_RATIO = 0.70


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


def normalize_text(text: str) -> str:
    return " ".join(
        "".join(character.casefold() if character.isalnum() else " " for character in text).split()
    )


def starts_list_marker(text: str) -> bool:
    stripped = text.lstrip()
    return stripped.startswith(BULLET_PREFIXES) or bool(NUMBERED_LIST_PATTERN.match(text))


def _is_page_number(line: TextBox) -> bool:
    return line.y_min >= BOTTOM_MARGIN_BAND and bool(PAGE_NUMBER_PATTERN.match(line.text))


def build_page_layout_profile(
    lines: list[TextBox],
    repeated_top_text: frozenset[str],
    repeated_bottom_text: frozenset[str],
) -> PageLayoutProfile:
    normalized_top = frozenset(normalize_text(text) for text in repeated_top_text)
    normalized_bottom = frozenset(normalize_text(text) for text in repeated_bottom_text)
    body_candidates = [
        line
        for line in lines
        if normalize_text(line.text) not in normalized_top | normalized_bottom
        and not _is_page_number(line)
        and line.y_min < BOTTOM_MARGIN_BAND
    ]
    sizes = sorted(float(line.font_size) for line in body_candidates if line.font_size and line.font_size > 0)
    body_sample_size = max(1, int(len(sizes) * BODY_FONT_SAMPLE_RATIO)) if sizes else 0
    body_sizes = sizes[:body_sample_size]
    heights = [line.height for line in body_candidates if line.height > 0]
    if not heights:
        heights = [line.height for line in lines if line.height > 0]
    return PageLayoutProfile(
        median_font_size=float(median(body_sizes)) if body_sizes else 1.0,
        median_line_height=float(median(heights)) if heights else 0.03,
        repeated_top_text=normalized_top,
        repeated_bottom_text=normalized_bottom,
    )


def classify_line_role(line: TextBox, profile: PageLayoutProfile) -> str:
    normalized = normalize_text(line.text)
    if line.y_min <= TOP_MARGIN_BAND and normalized in profile.repeated_top_text:
        return "header"
    if line.y_min >= BOTTOM_MARGIN_BAND and normalized in profile.repeated_bottom_text:
        return "footer"
    if _is_page_number(line):
        return "page_number"

    font_ratio = (line.font_size or profile.median_font_size) / max(profile.median_font_size, 1e-6)
    is_bold = bool((line.font_flags or 0) & BOLD_FONT_FLAG)
    heading_style = font_ratio >= HEADING_FONT_RATIO or (
        is_bold and font_ratio >= BOLD_HEADING_MIN_RATIO
    )
    if heading_style:
        return "title" if line.y_min < TITLE_REGION_BOTTOM else "heading"
    if line.y_min >= BOTTOM_MARGIN_BAND and font_ratio <= 0.85:
        return "footer"
    if line.starts_bullet or starts_list_marker(line.text):
        return "list_item"
    return "paragraph"


def _directions_compatible(first: TextBox, second: TextBox) -> bool:
    if first.direction is None or second.direction is None:
        return True
    return all(abs(left - right) <= DIRECTION_TOLERANCE for left, right in zip(first.direction, second.direction))


def _styles_compatible(first: TextBox, second: TextBox) -> bool:
    first_family = (first.font_family or "").casefold().strip()
    second_family = (second.font_family or "").casefold().strip()
    if first_family and second_family and first_family != second_family:
        return False
    if first.font_size and second.font_size:
        size_ratio = min(first.font_size, second.font_size) / max(first.font_size, second.font_size)
        if size_ratio < STYLE_SIZE_RATIO:
            return False
    return True


def _horizontal_overlap(first: list[float], second: list[float]) -> float:
    overlap = max(0.0, min(first[2], second[2]) - max(first[0], second[0]))
    minimum_width = max(1e-6, min(first[2] - first[0], second[2] - second[0]))
    return overlap / minimum_width


def _same_column(first: list[float], second: list[float], profile: PageLayoutProfile) -> bool:
    if _horizontal_overlap(first, second) >= COLUMN_OVERLAP_RATIO:
        return True
    alignment_tolerance = max(0.018, profile.median_line_height * ALIGNMENT_LINE_HEIGHT_MULTIPLIER)
    return abs(first[0] - second[0]) <= alignment_tolerance


def _lines_are_continuous(
    first: TextBox,
    second: TextBox,
    profile: PageLayoutProfile,
    *,
    gap_multiplier: float,
) -> bool:
    vertical_gap = second.y_min - first.y_max
    if vertical_gap < -0.15 * profile.median_line_height:
        return False
    if vertical_gap > gap_multiplier * profile.median_line_height:
        return False
    return (
        _directions_compatible(first, second)
        and _styles_compatible(first, second)
        and _same_column(first.bbox, second.bbox, profile)
    )


def text_groups_are_continuous(
    first: TextGroup,
    second: TextGroup,
    profile: PageLayoutProfile,
) -> bool:
    if first.role not in CONTENT_ROLES or second.role not in CONTENT_ROLES:
        return False
    if not first.lines or not second.lines or starts_list_marker(second.lines[0].text):
        return False
    return _lines_are_continuous(
        first.lines[-1],
        second.lines[0],
        profile,
        gap_multiplier=CROSS_BLOCK_GAP_MULTIPLIER,
    )


def _group_block(lines: list[TextBox], profile: PageLayoutProfile) -> list[TextGroup]:
    groups: list[TextGroup] = []
    for line in sorted(lines, key=lambda value: (value.line_id if value.line_id is not None else 10**9, value.y_min, value.x_min)):
        role = classify_line_role(line, profile)
        if not groups:
            groups.append(TextGroup(role, [line]))
            continue
        current = groups[-1]
        inherited_role = "list_item" if current.role == "list_item" and role == "paragraph" else role
        new_marker = starts_list_marker(line.text)
        continuous = _lines_are_continuous(
            current.lines[-1],
            line,
            profile,
            gap_multiplier=WITHIN_BLOCK_GAP_MULTIPLIER,
        )
        if new_marker or inherited_role != current.role or not continuous:
            groups.append(TextGroup(role, [line]))
        else:
            current.lines.append(line)
    return groups


def group_pdf_text(
    lines: list[TextBox],
    repeated_top_text: frozenset[str] = frozenset(),
    repeated_bottom_text: frozenset[str] = frozenset(),
) -> GroupingResult:
    if not lines:
        return GroupingResult([], [])
    profile = build_page_layout_profile(lines, repeated_top_text, repeated_bottom_text)
    blocks: dict[tuple[str, int], list[TextBox]] = {}
    for fallback_id, line in enumerate(lines):
        key = ("pdf", line.block_id) if line.block_id is not None else ("line", fallback_id)
        blocks.setdefault(key, []).append(line)

    grouped_blocks = [_group_block(block_lines, profile) for block_lines in blocks.values()]
    groups = [group for block in grouped_blocks for group in block]
    groups.sort(key=lambda group: (group.bbox[1], group.bbox[0]))

    repaired: list[TextGroup] = []
    for candidate in groups:
        if repaired and text_groups_are_continuous(repaired[-1], candidate, profile):
            repaired[-1].lines.extend(candidate.lines)
            if repaired[-1].role == "paragraph" and candidate.role == "list_item":
                repaired[-1].role = "list_item"
        else:
            repaired.append(candidate)

    return GroupingResult(
        content_groups=[group for group in repaired if group.role in CONTENT_ROLES],
        excluded_groups=[group for group in repaired if group.role in EXCLUDED_ROLES],
    )
