"""Tests for the pure-Python safe HTML table renderer."""

from __future__ import annotations

import unittest

from modules.system.safe_table import (
    normalize_table_records,
    records_to_html,
)


class DataFrameLike:
    def to_dict(
        self,
        orient: str = "dict",
    ):
        if orient != "records":
            raise ValueError(
                "Expected records orientation."
            )

        return [
            {
                "name": "first",
                "score": 0.8,
            },
            {
                "name": "second",
                "score": 0.6,
            },
        ]


class TestSafeTable(
    unittest.TestCase
):
    def test_list_of_records_is_preserved(
        self,
    ) -> None:
        rows = normalize_table_records(
            [
                {
                    "a": 1,
                    "b": "x",
                },
                {
                    "a": 2,
                    "b": "y",
                },
            ]
        )

        self.assertEqual(
            rows,
            [
                {
                    "a": 1,
                    "b": "x",
                },
                {
                    "a": 2,
                    "b": "y",
                },
            ],
        )

    def test_column_mapping_becomes_records(
        self,
    ) -> None:
        rows = normalize_table_records(
            {
                "a": [
                    1,
                    2,
                ],
                "b": [
                    "x",
                    "y",
                ],
            }
        )

        self.assertEqual(
            rows,
            [
                {
                    "a": 1,
                    "b": "x",
                },
                {
                    "a": 2,
                    "b": "y",
                },
            ],
        )

    def test_dataframe_like_object_uses_records(
        self,
    ) -> None:
        rows = normalize_table_records(
            DataFrameLike()
        )

        self.assertEqual(
            len(rows),
            2,
        )

        self.assertEqual(
            rows[0]["name"],
            "first",
        )

    def test_nested_values_are_rendered(
        self,
    ) -> None:
        rendered = records_to_html(
            [
                {
                    "source_ids": [
                        "source_1",
                        "source_2",
                    ],
                    "metadata": {
                        "valid": True,
                    },
                }
            ]
        )

        self.assertIn(
            "source_1",
            rendered,
        )

        self.assertIn(
            "valid",
            rendered,
        )

    def test_html_is_escaped(
        self,
    ) -> None:
        rendered = records_to_html(
            [
                {
                    "value": (
                        "<script>"
                        "alert('x')"
                        "</script>"
                    )
                }
            ]
        )

        self.assertNotIn(
            "<script>",
            rendered,
        )

        self.assertIn(
            "&lt;script&gt;",
            rendered,
        )

    def test_empty_table_has_message(
        self,
    ) -> None:
        rendered = records_to_html(
            [],
            empty_message=(
                "Nothing available."
            ),
        )

        self.assertIn(
            "Nothing available.",
            rendered,
        )

    def test_rows_are_bounded(
        self,
    ) -> None:
        rendered = records_to_html(
            [
                {
                    "index": index
                }
                for index in range(5)
            ],
            max_rows=2,
        )

        self.assertIn(
            "3 additional row",
            rendered,
        )

    def test_cell_content_is_bounded(
        self,
    ) -> None:
        rendered = records_to_html(
            [
                {
                    "text": "x" * 1000
                }
            ],
            max_cell_chars=40,
        )

        self.assertIn(
            "TRUNCATED",
            rendered,
        )


if __name__ == "__main__":
    unittest.main()
