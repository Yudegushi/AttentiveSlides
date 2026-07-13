"""Pure-Python HTML rendering for small public UI tables.

This module intentionally avoids Pandas and PyArrow. It is designed
for small Streamlit diagnostic, provenance, AOI and conversation tables.
"""

from __future__ import annotations

import html
import json
from collections.abc import Mapping, Sequence
from typing import Any


DEFAULT_MAX_ROWS = 100
DEFAULT_MAX_CELL_CHARS = 500


def normalize_table_records(
    data: Any,
) -> list[dict[str, Any]]:
    """Normalize common table-like objects into record dictionaries."""
    if data is None:
        return []

    if isinstance(data, Mapping):
        return _mapping_to_records(data)

    to_dict = getattr(
        data,
        "to_dict",
        None,
    )

    if callable(to_dict):
        converted: Any

        try:
            converted = to_dict(
                orient="records"
            )

        except TypeError:
            converted = to_dict()

        if converted is data:
            raise ValueError(
                "Table object's to_dict() returned itself."
            )

        return normalize_table_records(
            converted
        )

    if _is_non_string_sequence(data):
        records: list[
            dict[str, Any]
        ] = []

        for item in data:
            if isinstance(
                item,
                Mapping,
            ):
                records.append(
                    dict(item)
                )

            elif hasattr(
                item,
                "to_dict",
            ) and callable(
                item.to_dict
            ):
                converted_item = (
                    item.to_dict()
                )

                if not isinstance(
                    converted_item,
                    Mapping,
                ):
                    records.append(
                        {
                            "value": (
                                converted_item
                            )
                        }
                    )
                else:
                    records.append(
                        dict(
                            converted_item
                        )
                    )

            else:
                records.append(
                    {
                        "value": item
                    }
                )

        return records

    return [
        {
            "value": data
        }
    ]


def records_to_html(
    data: Any,
    *,
    max_rows: int = DEFAULT_MAX_ROWS,
    max_cell_chars: int = (
        DEFAULT_MAX_CELL_CHARS
    ),
    empty_message: str = "No records.",
) -> str:
    """Render table-like data as escaped, horizontally scrollable HTML."""
    if max_rows <= 0:
        raise ValueError(
            "max_rows must be positive."
        )

    if max_cell_chars <= 0:
        raise ValueError(
            "max_cell_chars must be positive."
        )

    records = normalize_table_records(
        data
    )

    if not records:
        return (
            '<p><em>'
            + html.escape(
                empty_message,
                quote=True,
            )
            + "</em></p>"
        )

    columns = _ordered_columns(
        records
    )

    visible_records = records[
        :max_rows
    ]

    header_html = "".join(
        (
            "<th style=\""
            "text-align:left;"
            "padding:0.5rem;"
            "border-bottom:1px solid "
            "rgba(128,128,128,0.35);"
            "white-space:nowrap;"
            "\">"
            f"{html.escape(str(column), quote=True)}"
            "</th>"
        )
        for column in columns
    )

    body_rows: list[str] = []

    for record in visible_records:
        cells = "".join(
            (
                "<td style=\""
                "vertical-align:top;"
                "padding:0.5rem;"
                "border-bottom:1px solid "
                "rgba(128,128,128,0.18);"
                "min-width:8rem;"
                "max-width:30rem;"
                "overflow-wrap:anywhere;"
                "\">"
                f"{_format_cell(record.get(column), max_cell_chars)}"
                "</td>"
            )
            for column in columns
        )

        body_rows.append(
            f"<tr>{cells}</tr>"
        )

    truncated_count = (
        len(records)
        - len(visible_records)
    )

    truncation_html = ""

    if truncated_count > 0:
        truncation_html = (
            "<p><em>"
            f"{truncated_count} additional "
            "row(s) were not displayed."
            "</em></p>"
        )

    return (
        "<div style=\""
        "overflow-x:auto;"
        "width:100%;"
        "margin:0.5rem 0 1rem 0;"
        "\">"
        "<table style=\""
        "border-collapse:collapse;"
        "width:100%;"
        "font-size:0.9rem;"
        "\">"
        f"<thead><tr>{header_html}</tr></thead>"
        f"<tbody>{''.join(body_rows)}</tbody>"
        "</table>"
        "</div>"
        f"{truncation_html}"
    )


def _mapping_to_records(
    value: Mapping[Any, Any],
) -> list[dict[str, Any]]:
    mapping = {
        str(key): item
        for key, item in value.items()
    }

    if not mapping:
        return []

    sequence_columns = {
        key: item
        for key, item in mapping.items()
        if _is_non_string_sequence(
            item
        )
    }

    if (
        len(sequence_columns)
        == len(mapping)
    ):
        lengths = {
            len(item)
            for item in sequence_columns.values()
        }

        if len(lengths) == 1:
            row_count = next(
                iter(lengths)
            )

            return [
                {
                    key: item[index]
                    for key, item
                    in sequence_columns.items()
                }
                for index in range(
                    row_count
                )
            ]

    return [
        mapping
    ]


def _ordered_columns(
    records: Sequence[
        Mapping[str, Any]
    ],
) -> list[str]:
    columns: list[str] = []
    seen: set[str] = set()

    for record in records:
        for key in record:
            normalized = str(key)

            if normalized in seen:
                continue

            seen.add(normalized)
            columns.append(
                normalized
            )

    return columns or [
        "value"
    ]


def _format_cell(
    value: Any,
    max_chars: int,
) -> str:
    if value is None:
        raw = "—"

    elif isinstance(
        value,
        (
            Mapping,
            list,
            tuple,
            set,
        ),
    ):
        raw = json.dumps(
            value,
            ensure_ascii=False,
            default=str,
            sort_keys=(
                isinstance(
                    value,
                    Mapping,
                )
            ),
        )

    else:
        raw = str(value)

    if len(raw) > max_chars:
        raw = (
            raw[
                : max_chars - 14
            ]
            + " … [TRUNCATED]"
        )

    return html.escape(
        raw,
        quote=True,
    )


def _is_non_string_sequence(
    value: Any,
) -> bool:
    return isinstance(
        value,
        Sequence,
    ) and not isinstance(
        value,
        (
            str,
            bytes,
            bytearray,
        ),
    )
