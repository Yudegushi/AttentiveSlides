import unittest

from modules.system.voice_event_hub import VoiceEventHub, VoiceJSONEvent


class VoiceEventHubTests(unittest.IsolatedAsyncioTestCase):
    async def test_json_events_are_ordered_for_each_subscriber(self) -> None:
        hub = VoiceEventHub(queue_size=4)
        first = await hub.subscribe("one")
        second = await hub.subscribe("two")
        await hub.publish_json("voice.state", {"state": "ready"})
        await hub.publish_json("assistant.text.delta", {"text": "hello"})
        for subscription in (first, second):
            messages = [await subscription.receive(), await subscription.receive()]
            self.assertEqual([item.sequence for item in messages], [1, 2])
            self.assertEqual([item.type for item in messages], ["voice.state", "assistant.text.delta"])

    async def test_slow_audio_drops_old_audio_without_losing_json(self) -> None:
        hub = VoiceEventHub(queue_size=3)
        subscription = await hub.subscribe("one")
        await hub.publish_json("voice.state", {"state": "playing"})
        await hub.publish_audio(b"old-audio")
        await hub.publish_audio(b"middle-audio")
        await hub.publish_audio(b"new-audio")
        messages = [await subscription.receive(), await subscription.receive(), await subscription.receive()]
        self.assertIsInstance(messages[0], VoiceJSONEvent)
        self.assertEqual(messages[1:], [b"middle-audio", b"new-audio"])

    async def test_clear_playback_removes_audio_then_broadcasts_marker(self) -> None:
        hub = VoiceEventHub(queue_size=5)
        subscription = await hub.subscribe("one")
        await hub.publish_json("assistant.text.delta", {"text": "kept"})
        await hub.publish_audio(b"drop")
        await hub.clear_playback()
        first = await subscription.receive()
        second = await subscription.receive()
        self.assertEqual(first.type, "assistant.text.delta")
        self.assertEqual(second.type, "playback.clear")

    async def test_unsubscribe_stops_future_delivery(self) -> None:
        hub = VoiceEventHub()
        subscription = await hub.subscribe("one")
        await hub.unsubscribe(subscription)
        await hub.publish_json("voice.state", {})
        self.assertTrue(subscription.queue.empty())


if __name__ == "__main__":
    unittest.main()
