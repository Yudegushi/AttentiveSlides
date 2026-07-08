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


if __name__ == "__main__":
    unittest.main()
