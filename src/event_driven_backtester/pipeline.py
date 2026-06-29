from __future__ import annotations

from decimal import Decimal
from typing import Any

from event_driven_backtester.engine import BacktestEngine
from event_driven_backtester.ingest import load_signals, load_trade_ticks
from event_driven_backtester.models import BacktestConfig, BacktestResult


def serialize_backtest_result(result: BacktestResult) -> dict[str, Any]:
    return {
        "symbol": result.config.symbol,
        "initial_cash": str(result.config.initial_cash),
        "final_cash": str(result.final_cash),
        "final_equity": str(result.final_equity),
        "processed_events": result.processed_events,
        "fill_count": len(result.fills),
        "fills": [
            {
                "order_id": fill.order_id,
                "symbol": fill.symbol,
                "side": fill.side.value,
                "quantity": str(fill.quantity),
                "price": str(fill.price),
                "commission": str(fill.commission),
                "filled_at": fill.filled_at.isoformat(),
            }
            for fill in result.fills
        ],
        "equity_curve": [
            {
                "event_time": point.event_time.isoformat(),
                "cash": str(point.cash),
                "equity": str(point.equity),
                "position_value": str(point.position_value),
            }
            for point in result.equity_curve
        ],
    }


def run_backtest_pipeline(
    ticks_path: str,
    signals_path: str,
    symbol: str,
    initial_cash: Decimal,
    position_size: Decimal,
    commission_rate: Decimal,
) -> BacktestResult:
    ticks = load_trade_ticks(ticks_path, default_symbol=symbol)
    signals = load_signals(signals_path, default_symbol=symbol)
    config = BacktestConfig(
        symbol=symbol,
        initial_cash=initial_cash,
        position_size=position_size,
        commission_rate=commission_rate,
    )
    engine = BacktestEngine(config)
    return engine.run(ticks, signals)
