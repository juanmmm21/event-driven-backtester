from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from event_driven_backtester.engine import BacktestEngine
from event_driven_backtester.execution import (
    load_external_fills,
    round_to_tick,
    signals_to_limit_orders,
)
from event_driven_backtester.models import (
    BacktestConfig,
    OrderSide,
    SignalAction,
    SignalPayload,
    SignalSide,
    TradeTick,
)

T0 = datetime(2026, 11, 17, 23, 0, tzinfo=UTC)
CONFIG = BacktestConfig(
    symbol="BTCUSDT", initial_cash=Decimal("10000"), position_size=Decimal("0.01"),
    commission_rate=Decimal("0.001"),
)


def _tick(seconds: int, price: str) -> TradeTick:
    return TradeTick("BTCUSDT", str(seconds), Decimal(price), Decimal("1"),
                     T0 + timedelta(seconds=seconds))


def _signal(seconds: int, action: SignalAction) -> SignalPayload:
    return SignalPayload("rsi", "BTCUSDT", action, SignalSide.LONG, 0.5, "test",
                         T0 + timedelta(seconds=seconds))


def test_round_to_tick_never_makes_orders_more_aggressive() -> None:
    assert round_to_tick(Decimal("100.019"), Decimal("0.01"), OrderSide.BUY) == Decimal("100.01")
    assert round_to_tick(Decimal("100.011"), Decimal("0.01"), OrderSide.SELL) == Decimal("100.02")


def test_signals_become_alternating_passive_orders() -> None:
    ticks = [_tick(0, "65000.00"), _tick(10, "65100.00"), _tick(20, "64900.00")]
    signals = [
        _signal(5, SignalAction.ENTER),
        _signal(6, SignalAction.ENTER),  # already long: ignored
        _signal(15, SignalAction.EXIT),
        _signal(25, SignalAction.EXIT),  # already flat: ignored
    ]
    orders = signals_to_limit_orders(
        ticks, signals, symbol="BTCUSDT", quantity=Decimal("0.001"), offset_bps=Decimal("1")
    )
    assert [(o["side"], o["price"]) for o in orders] == [
        ("buy", "64993.50"),
        ("sell", "65106.51"),
    ]
    assert orders[0]["time_in_force_seconds"] == 60.0


def test_engine_books_external_fills_instead_of_its_own(tmp_path: Path) -> None:
    fills_path = tmp_path / "fills.jsonl"
    rows = [
        {"order_id": "a", "side": "buy", "price": "65000", "quantity": "0.01",
         "commission": "0.65", "filled_at": (T0 + timedelta(seconds=3)).isoformat()},
        {"order_id": "b", "side": "sell", "price": "65200", "quantity": "0.01",
         "commission": "0.652", "filled_at": (T0 + timedelta(seconds=12)).isoformat()},
        {"order_id": "c", "side": "sell", "price": "65300", "quantity": "0.01",
         "commission": "0", "filled_at": (T0 + timedelta(seconds=13)).isoformat()},
    ]
    fills_path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    fills = load_external_fills(fills_path, "BTCUSDT")
    ticks = [_tick(0, "65000"), _tick(10, "65150"), _tick(20, "65250")]
    signals = [_signal(1, SignalAction.ENTER)]  # ignored when external fills are given
    result = BacktestEngine(CONFIG).run(ticks, signals, external_fills=fills)
    assert [f.order_id for f in result.fills] == ["a", "b"]
    assert result.rejected_fills == 1  # "c" sells without a position
    assert result.final_cash == Decimal("10000") - Decimal("650.65") + Decimal("651.348")
