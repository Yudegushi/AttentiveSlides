"""Bounded fan-out of realtime voice JSON and PCM events."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass


@dataclass(frozen=True)
class VoiceJSONEvent:
    sequence: int
    type: str
    payload: dict[str, object]


VoiceMessage = VoiceJSONEvent | bytes


@dataclass(eq=False)
class VoiceSubscription:
    session_id: str
    queue: asyncio.Queue[VoiceMessage]

    async def receive(self) -> VoiceMessage:
        return await self.queue.get()


class VoiceEventHub:
    """Broadcast without allowing slow audio playback to block provider IO."""

    def __init__(self, *, queue_size: int = 64) -> None:
        if queue_size < 2:
            raise ValueError("queue_size must be at least two")
        self._queue_size = queue_size
        self._subscriptions: set[VoiceSubscription] = set()
        self._sequence = 0
        self._lock = asyncio.Lock()

    async def subscribe(self, session_id: str) -> VoiceSubscription:
        subscription = VoiceSubscription(
            session_id=session_id,
            queue=asyncio.Queue(maxsize=self._queue_size),
        )
        async with self._lock:
            self._subscriptions.add(subscription)
        return subscription

    async def unsubscribe(self, subscription: VoiceSubscription) -> None:
        async with self._lock:
            self._subscriptions.discard(subscription)

    async def publish_json(self, type: str, payload: dict[str, object]) -> None:
        async with self._lock:
            self._sequence += 1
            message = VoiceJSONEvent(self._sequence, type, dict(payload))
            subscriptions = tuple(self._subscriptions)
        for subscription in subscriptions:
            self._put_json(subscription.queue, message)

    async def publish_audio(self, pcm: bytes) -> None:
        if not pcm:
            return
        async with self._lock:
            subscriptions = tuple(self._subscriptions)
        for subscription in subscriptions:
            self._put_audio(subscription.queue, bytes(pcm))

    async def clear_playback(self) -> None:
        async with self._lock:
            subscriptions = tuple(self._subscriptions)
        for subscription in subscriptions:
            retained = [item for item in self._drain(subscription.queue) if not isinstance(item, bytes)]
            for item in retained:
                subscription.queue.put_nowait(item)
        await self.publish_json("playback.clear", {})

    @staticmethod
    def _drain(queue: asyncio.Queue[VoiceMessage]) -> list[VoiceMessage]:
        items: list[VoiceMessage] = []
        while True:
            try:
                items.append(queue.get_nowait())
            except asyncio.QueueEmpty:
                return items

    def _put_audio(self, queue: asyncio.Queue[VoiceMessage], message: bytes) -> None:
        if not queue.full():
            queue.put_nowait(message)
            return
        items = self._drain(queue)
        for index, item in enumerate(items):
            if isinstance(item, bytes):
                del items[index]
                break
        else:
            for item in items:
                queue.put_nowait(item)
            return
        for item in items:
            queue.put_nowait(item)
        queue.put_nowait(message)

    def _put_json(self, queue: asyncio.Queue[VoiceMessage], message: VoiceJSONEvent) -> None:
        if not queue.full():
            queue.put_nowait(message)
            return
        items = self._drain(queue)
        remove_index = next(
            (index for index, item in enumerate(items) if isinstance(item, bytes)),
            0,
        )
        del items[remove_index]
        for item in items:
            queue.put_nowait(item)
        queue.put_nowait(message)
