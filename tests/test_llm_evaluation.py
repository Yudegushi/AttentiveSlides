"""Tests for the grounded tutor LLM evaluation dataset and runner."""

from __future__ import annotations

import unittest
from pathlib import Path

from evaluation.eval_llm_responses import (
    FixtureResponseProvider,
    evaluate_case,
)
from evaluation.llm_dataset import (
    load_llm_cases,
)
from modules.tutor.grounded_prompt import (
    GroundedPromptBuilder,
)
from modules.tutor.grounding_validator import (
    GroundingValidator,
)
from modules.tutor.response_parser import (
    StructuredResponseParser,
)


DATASET_PATH = Path(
    "evaluation/llm_cases.json"
)


class TestLLMEvaluationDataset(unittest.TestCase):
    def setUp(self) -> None:
        self.cases = load_llm_cases(
            DATASET_PATH
        )

    def test_dataset_has_initial_coverage(self) -> None:
        self.assertGreaterEqual(
            len(self.cases),
            8,
        )

        categories = {
            case.category
            for case in self.cases
        }

        self.assertTrue({
            "compare",
            "explain",
            "summarize",
            "quiz",
            "simplify",
            "insufficient_context",
            "prompt_injection",
            "break",
        }.issubset(categories))

    def test_case_ids_are_unique(self) -> None:
        case_ids = [
            case.case_id
            for case in self.cases
        ]

        self.assertEqual(
            len(case_ids),
            len(set(case_ids)),
        )

    def test_fixture_responses_pass_evaluation(
        self,
    ) -> None:
        provider = FixtureResponseProvider()
        prompt_builder = GroundedPromptBuilder()
        parser = StructuredResponseParser()
        validator = GroundingValidator()

        for case in self.cases:
            with self.subTest(case_id=case.case_id):
                result = evaluate_case(
                    case,
                    provider,
                    prompt_builder,
                    parser,
                    validator,
                )

                self.assertTrue(
                    result["overall_pass"],
                    result,
                )

    def test_required_sources_exist_in_request(
        self,
    ) -> None:
        for case in self.cases:
            with self.subTest(case_id=case.case_id):
                self.assertTrue(
                    set(
                        case.expectations
                        .required_source_ids
                    )
                    <= case.request.source_ids()
                )


if __name__ == "__main__":
    unittest.main()
