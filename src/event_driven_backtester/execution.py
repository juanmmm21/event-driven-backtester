"""Limit orders out, external fills in.

The backtester's own broker fills market orders instantly at the last price. For passive limit
orders the fill depends on the order book queue, which is modelled elsewhere
(``market-condition-simulator queue-fill``). This module keeps the two decoupled through files:

* ``signals_to_limit_orders`` turns signals into limit orders (JSONL) priced off the last trade;
* ``load_external_fills`` reads the simulator's fills so ``BacktestEngine.run(...,
  external_fills=...)`` books exactly those executions instead of its own.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal
from pathlib import Path
from typing import Any

from event_driven_backtester.models import (
    Fill,
    OrderSide,
    SignalAction,
    SignalPayload,
    SignalSide,
    TradeTick,
    decimal_from_value,
    utc_from_iso8601,
)


def round_to_tick(price: Decimal, tick_size: Decimal, side: OrderSide) -> Decimal:
    """Buys round down and sells round up, so rounding never makes an order more aggressive."""
    rounding = ROUND_FLOOR if side is OrderSide.BUY else ROUND_CEILING
    return (price / tick_size).to_integral_value(rounding=rounding) * tick_size


def signals_to_limit_orders(
    ticks: Sequence[TradeTick],
    signals: Sequence[SignalPayload],
    *,
    symbol: str,
    quantity: Decimal,
    offset_bps: Decimal = Decimal("0"),
    tick_size: Decimal = Decimal("0.01"),
    time_in_force_seconds: float | None = 60.0,
) -> list[dict[str, Any]]:
    """One passive limit order per long entry/exit signal, priced off the last trade."""
    if quantity <= 0 or tick_size <= 0 or offset_bps < 0:
        raise ValueError("quantity and tick_size must be positive, offset_bps non-negative")
    ordered_ticks = sorted((t for t in ticks if t.symbol == symbol), key=lambda t: t.event_time)
    orders: list[dict[str, Any]] = []
    index = 0
    last_price: Decimal | None = None
    in_position = False
    for signal in sorted(signals, key=lambda s: s.event_time):
        if signal.symbol != symbol or signal.action is SignalAction.HOLD:
            continue
        while index < len(ordered_ticks) and ordered_ticks[index].event_time <= signal.event_time:
            last_price = ordered_ticks[index].price
            index += 1
        if last_price is None:
            continue
        is_long_entry = signal.action is SignalAction.ENTER and signal.side is SignalSide.LONG
        if is_long_entry and not in_position:
            side = OrderSide.BUY
            raw = last_price * (1 - offset_bps / Decimal(10_000))
            in_position = True
        elif signal.action is SignalAction.EXIT and in_position:
            side = OrderSide.SELL
            raw = last_price * (1 + offset_bps / Decimal(10_000))
            in_position = False
        else:
            continue
        orders.append(
            {
                "order_id": f"{signal.strategy_id}-{len(orders)}",
                "symbol": symbol,
                "side": side.value,
                "price": str(round_to_tick(raw, tick_size, side)),
                "quantity": str(quantity),
                "submitted_at": signal.event_time.isoformat(),
                "time_in_force_seconds": time_in_force_seconds,
                "reason": signal.reason,
            }
        )
    return orders


def load_external_fills(path: str | Path, default_symbol: str) -> list[Fill]:
    fills: list[Fill] = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            payload = json.loads(line)
            if not isinstance(payload, dict):
                raise ValueError(f"line {line_number} must contain a JSON object")
            fills.append(
                Fill(
                    order_id=str(payload["order_id"]),
                    symbol=str(payload.get("symbol", default_symbol)),
                    side=OrderSide(str(payload["side"])),
                    quantity=decimal_from_value(payload["quantity"], "quantity"),
                    price=decimal_from_value(payload["price"], "price"),
                    commission=decimal_from_value(payload.get("commission", "0"), "commission"),
                    filled_at=utc_from_iso8601(str(payload["filled_at"])),
                )
            )
    return fills
