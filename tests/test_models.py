from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest

from event_driven_backtester.models import BacktestConfig, TradeTick


def test_backtest_config_validation() -> None:
    with pytest.raises(ValueError):
        BacktestConfig(
            symbol="BTCUSDT",
            initial_cash=Decimal("0"),
            position_size=Decimal("0.01"),
        )


def test_trade_tick_requires_timezone() -> None:
    with pytest.raises(ValueError):
        TradeTick(
            symbol="BTCUSDT",
            trade_id="1",
            price=Decimal("100"),
            quantity=Decimal("0.01"),
            event_time=datetime(2024, 1, 1, 12, 0),
        )
