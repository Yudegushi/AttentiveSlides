import unittest

from modules.realtime.realtime_contracts import TargetBinding
from modules.system.realtime_tutor_context import (
    RealtimeTutorContext,
    build_realtime_tutor_instructions,
)


class RealtimeTutorContextTests(unittest.TestCase):
    def test_instructions_bind_the_confirmed_target_and_slide(self) -> None:
        target = TargetBinding("deck", 3, "formula", "Loss formula", "L = prediction minus truth")
        instructions = build_realtime_tutor_instructions(
            RealtimeTutorContext("deck", 3, "This slide introduces training loss.", target)
        )
        self.assertIn("Slide number: 3", instructions)
        self.assertIn("Confirmed target: Loss formula", instructions)
        self.assertIn("L = prediction minus truth", instructions)
        self.assertIn("only about the confirmed target", instructions)
        self.assertIn("Do not claim to see content", instructions)

    def test_model_visual_observation_has_source_caution(self) -> None:
        target = TargetBinding("deck", 1, "chart", "Chart", "Native caption")
        instructions = build_realtime_tutor_instructions(
            RealtimeTutorContext(
                "deck",
                1,
                "Native slide text",
                target,
                visual_observation="A model reads a rising blue curve.",
                visual_observation_is_model_derived=True,
            )
        )
        self.assertIn("vision model", instructions)
        self.assertIn("transcription errors", instructions)
        self.assertIn("prefer the native text", instructions)
        self.assertIn("mental state", instructions)

    def test_context_fields_are_bounded(self) -> None:
        target = TargetBinding("deck", 1, "a", "A", "t" * 10_000)
        instructions = build_realtime_tutor_instructions(
            RealtimeTutorContext("deck", 1, "s" * 20_000, target, "v" * 10_000, True)
        )
        self.assertLess(len(instructions), 14_000)
        self.assertIn("…", instructions)


if __name__ == "__main__":
    unittest.main()
