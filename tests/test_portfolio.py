from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from event_driven_backtester.models import Fill, OrderSide, PositionSide
from event_driven_backtester.portfolio import Portfolio


def _fill(side: OrderSide, price: str, quantity: str = "0.01") -> Fill:
    return Fill(
        order_id="order-1",
        symbol="BTCUSDT",
        side=side,
        quantity=Decimal(quantity),
        price=Decimal(price),
        commission=Decimal("0.01"),
        filled_at=datetime(2024, 1, 1, 12, 0, tzinfo=UTC),
    )


def test_portfolio_buy_and_sell_round_trip() -> None:
    portfolio = Portfolio(initial_cash=Decimal("10000"), symbol="BTCUSDT")
    portfolio.update_mark_price(Decimal("100"), datetime(2024, 1, 1, 12, 0, tzinfo=UTC))
    portfolio.apply_fill(_fill(OrderSide.BUY, "100"))
    assert portfolio.position.side is PositionSide.LONG

    portfolio.update_mark_price(Decimal("105"), datetime(2024, 1, 1, 12, 5, tzinfo=UTC))
    portfolio.apply_fill(_fill(OrderSide.SELL, "105"))
    assert portfolio.position.side is PositionSide.FLAT
    assert portfolio.cash > Decimal("10000")
