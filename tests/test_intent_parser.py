import unittest

from modules.interaction.intent_parser import parse_intent


class IntentParserTest(unittest.TestCase):
    def test_parse_deictic_explain_chinese(self):
        result = parse_intent("解释这个")

        self.assertEqual(result.intent, "explain")
        self.assertTrue(result.has_deictic_reference)
        self.assertIsNone(result.explicit_target_hint)

    def test_parse_explicit_right_figure(self):
        result = parse_intent("解释右边这个图")

        self.assertEqual(result.intent, "explain")
        self.assertTrue(result.has_deictic_reference)
        self.assertEqual(result.explicit_target_hint, "right_figure")

    def test_parse_summarize_whole_slide(self):
        result = parse_intent("总结这一页")

        self.assertEqual(result.intent, "summarize")
        self.assertEqual(result.explicit_target_hint, "whole_slide")

    def test_parse_stt_induced_chinese_variants(self):
        cases = [
            ("解释一下这个", "explain", True, None),
            ("讲讲右边这个图", "explain", True, "right_figure"),
            ("这个图是什么意思", "explain", True, None),
            ("总结一下这一页", "summarize", False, "whole_slide"),
            ("考我一下这个概念", "quiz", True, None),
        ]

        for text, intent, has_deictic_reference, explicit_target_hint in cases:
            with self.subTest(text=text):
                result = parse_intent(text)

                self.assertEqual(result.intent, intent)
                self.assertEqual(result.has_deictic_reference, has_deictic_reference)
                self.assertEqual(result.explicit_target_hint, explicit_target_hint)

    def test_parse_english_audio_eval_paraphrases(self):
        cases = [
            ("What does this chart mean?", "explain", True),
            ("Please provide intuitive explanation.", "simplify", False),
        ]

        for text, intent, has_deictic_reference in cases:
            with self.subTest(text=text):
                result = parse_intent(text)

                self.assertEqual(result.intent, intent)
                self.assertEqual(result.has_deictic_reference, has_deictic_reference)


if __name__ == "__main__":
    unittest.main()
