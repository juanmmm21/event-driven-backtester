from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from event_driven_backtester.models import BacktestEvent, EventType, TradeTick
from event_driven_backtester.queue import EventQueue


def _tick(trade_id: str, minute: int) -> TradeTick:
    return TradeTick(
        symbol="BTCUSDT",
        trade_id=trade_id,
        price=Decimal("100"),
        quantity=Decimal("0.01"),
        event_time=datetime(2024, 1, 1, 12, minute, tzinfo=UTC),
    )


def test_event_queue_orders_by_time() -> None:
    queue = EventQueue()
    queue.push(BacktestEvent.from_tick(_tick("2", 2), queue.next_sequence()))
    queue.push(BacktestEvent.from_tick(_tick("1", 1), queue.next_sequence()))
    ordered = list(queue)
    assert ordered[0].event_type is EventType.NEW_TICK
    first_payload = ordered[0].payload
    assert isinstance(first_payload, TradeTick)
    assert first_payload.trade_id == "1"
