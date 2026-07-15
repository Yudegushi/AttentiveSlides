import unittest

from modules.realtime.realtime_contracts import (
    OmniSessionState,
    SpeechMode,
    TargetBinding,
    VoiceEngine,
    VoicePreferences,
)


class RealtimeContractsTests(unittest.TestCase):
    def test_enum_values_and_default_preferences_are_stable(self) -> None:
        self.assertEqual(VoiceEngine.SINGLE_TURN.value, "single_turn")
        self.assertEqual(VoiceEngine.OMNI.value, "omni")
        self.assertEqual(SpeechMode.PUSH_TO_TALK.value, "push_to_talk")
        self.assertEqual(SpeechMode.CONTINUOUS.value, "continuous")
        self.assertEqual(OmniSessionState.SWITCH_PENDING.value, "switch_pending")
        self.assertEqual(VoicePreferences(), VoicePreferences(answer_audio_enabled=True))

    def test_target_signature_uses_normalized_ids(self) -> None:
        target = TargetBinding(" deck ", 2, " chart ", "Chart", "Revenue", (0, 0.1, 1, 0.9))
        self.assertEqual(target.signature, "deck:2:chart")
        self.assertEqual(target.bbox, (0.0, 0.1, 1.0, 0.9))

    def test_invalid_target_identity_and_bbox_are_rejected(self) -> None:
        cases = [
            dict(deck_id=" ", slide_id=1, target_id="a", bbox=None),
            dict(deck_id="d", slide_id=0, target_id="a", bbox=None),
            dict(deck_id="d", slide_id=1, target_id=" ", bbox=None),
            dict(deck_id="d", slide_id=1, target_id="a", bbox=(0, 0, 1)),
            dict(deck_id="d", slide_id=1, target_id="a", bbox=(0.5, 0, 0.5, 1)),
            dict(deck_id="d", slide_id=1, target_id="a", bbox=(-0.1, 0, 1, 1)),
            dict(deck_id="d", slide_id=1, target_id="a", bbox=(0, 0, float("inf"), 1)),
        ]
        for values in cases:
            with self.subTest(values=values), self.assertRaises(ValueError):
                TargetBinding(label="A", text="text", **values)


if __name__ == "__main__":
    unittest.main()
