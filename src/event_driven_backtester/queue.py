from __future__ import annotations

import heapq
from collections.abc import Iterable, Iterator

from event_driven_backtester.models import BacktestEvent


class EventQueue:
    """Cola de prioridad que garantiza reproducción cronológica determinista."""

    def __init__(self) -> None:
        self._heap: list[BacktestEvent] = []
        self._sequence = 0

    def push(self, event: BacktestEvent) -> None:
        heapq.heappush(self._heap, event)

    def push_many(self, events: Iterable[BacktestEvent]) -> None:
        for event in events:
            self.push(event)

    def next_sequence(self) -> int:
        value = self._sequence
        self._sequence += 1
        return value

    def __len__(self) -> int:
        return len(self._heap)

    def __iter__(self) -> Iterator[BacktestEvent]:
        while self._heap:
            yield heapq.heappop(self._heap)
