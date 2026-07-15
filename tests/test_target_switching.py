import unittest

from modules.realtime.realtime_contracts import TargetBinding
from modules.system.target_switching import SwitchIntent, TargetSwitchController


def target(target_id: str, *, slide_id: int = 1) -> TargetBinding:
    return TargetBinding("deck", slide_id, target_id, target_id.upper(), f"text {target_id}")


class TargetSwitchingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.controller = TargetSwitchController()
        self.a = target("a")
        self.b = target("b")
        self.c = target("c")
        self.controller.bind(self.a)

    def test_gaze_candidates_never_change_active_target(self) -> None:
        self.controller.observe_candidate(self.b)
        self.controller.observe_candidate(self.c)
        decision = self.controller.handle_transcript("为什么？")
        self.assertEqual(decision.intent, SwitchIntent.KEEP)
        self.assertTrue(decision.should_create_response)
        self.assertEqual(decision.active_target, self.a)

    def test_strong_and_weak_language_propose_only_a_different_candidate(self) -> None:
        self.controller.observe_candidate(self.b)
        strong = self.controller.handle_transcript("换到这个")
        self.assertEqual(strong.intent, SwitchIntent.PROPOSE)
        self.assertFalse(strong.should_create_response)
        self.assertEqual(strong.pending.candidate, self.b)

        self.controller.reject()
        self.controller.observe_candidate(self.a)
        same = self.controller.handle_transcript("这个呢")
        self.assertEqual(same.intent, SwitchIntent.KEEP)
        self.assertTrue(same.should_create_response)

        self.controller.observe_candidate(self.b)
        weak = self.controller.handle_transcript("what about this?")
        self.assertEqual(weak.intent, SwitchIntent.PROPOSE)

    def test_pending_suppresses_response_and_confirmation_uses_frozen_candidate(self) -> None:
        self.controller.observe_candidate(self.b)
        self.controller.handle_transcript("讲这里")
        self.controller.observe_candidate(self.c)
        still_pending = self.controller.handle_transcript("再说一点")
        self.assertEqual(still_pending.intent, SwitchIntent.PROPOSE)
        self.assertFalse(still_pending.should_create_response)

        confirmed = self.controller.handle_transcript("是的")
        self.assertEqual(confirmed.intent, SwitchIntent.CONFIRM)
        self.assertEqual(confirmed.active_target, self.b)
        self.assertIsNone(confirmed.pending)

    def test_reject_keeps_old_target_and_bind_new_scope_clears_pending(self) -> None:
        self.controller.observe_candidate(self.b)
        self.controller.handle_transcript("switch to this")
        rejected = self.controller.handle_transcript("不用换")
        self.assertEqual(rejected.intent, SwitchIntent.REJECT)
        self.assertEqual(rejected.active_target, self.a)

        self.controller.observe_candidate(self.b)
        self.controller.handle_transcript("看这个")
        new_page = target("page-two", slide_id=2)
        self.controller.bind(new_page)
        self.assertEqual(self.controller.active_target, new_page)
        self.assertIsNone(self.controller.pending)
        self.assertIsNone(self.controller.candidate)

    def test_strong_switch_without_candidate_requests_selection(self) -> None:
        decision = self.controller.handle_transcript("look at this")
        self.assertEqual(decision.intent, SwitchIntent.KEEP)
        self.assertFalse(decision.should_create_response)
        self.assertIn("选择", decision.user_message)


if __name__ == "__main__":
    unittest.main()
