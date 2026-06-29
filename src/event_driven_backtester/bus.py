from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from event_driven_backtester.models import BacktestEvent


class EventHandler(Protocol):
    def handle(self, event: BacktestEvent) -> list[BacktestEvent]:
        ...


EventHandlerFn = Callable[[BacktestEvent], list[BacktestEvent]]


class EventBus:
    """Despacha eventos a handlers registrados y encola eventos derivados."""

    def __init__(self) -> None:
        self._handlers: dict[str, EventHandlerFn] = {}

    def register(self, event_type: str, handler: EventHandlerFn) -> None:
        if event_type in self._handlers:
            raise ValueError(f"handler already registered for {event_type}")
        self._handlers[event_type] = handler

    def dispatch(self, event: BacktestEvent) -> list[BacktestEvent]:
        handler = self._handlers.get(event.event_type.value)
        if handler is None:
            return []
        return handler(event)
