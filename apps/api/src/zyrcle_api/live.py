"""In-process fan-out of session updates to WebSocket subscribers.

Single-instance only. With several API replicas this becomes Postgres LISTEN/NOTIFY or Redis
pub/sub; the interface stays the same.
"""

import asyncio
from collections import defaultdict
from typing import Any


class LiveHub:
    def __init__(self, queue_size: int = 100):
        self._subs: dict[str, set[asyncio.Queue[dict[str, Any]]]] = defaultdict(set)
        self._queue_size = queue_size

    def subscribe(self, session_id: str) -> asyncio.Queue[dict[str, Any]]:
        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue(self._queue_size)
        self._subs[session_id].add(q)
        return q

    def unsubscribe(self, session_id: str, q: asyncio.Queue[dict[str, Any]]) -> None:
        self._subs[session_id].discard(q)
        if not self._subs[session_id]:
            del self._subs[session_id]

    def publish(self, session_id: str, event: dict[str, Any]) -> None:
        for q in list(self._subs.get(session_id, ())):
            if q.full():  # a slow client loses old updates rather than blocking device traffic
                q.get_nowait()
            q.put_nowait(event)
