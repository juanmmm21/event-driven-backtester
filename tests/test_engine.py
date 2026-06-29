from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from event_driven_backtester.engine import BacktestEngine
from event_driven_backtester.ingest import load_signals, load_trade_ticks
from event_driven_backtester.models import BacktestConfig, PositionSide
from event_driven_backtester.pipeline import run_backtest_pipeline


def test_engine_runs_sample_backtest() -> None:
    root = Path(__file__).resolve().parents[1]
    ticks = load_trade_ticks(root / "samples" / "btcusdt_ticks.jsonl", "BTCUSDT")
    signals = load_signals(root / "samples" / "btcusdt_signals.jsonl", "BTCUSDT")
    config = BacktestConfig(
        symbol="BTCUSDT",
        initial_cash=Decimal("10000"),
        position_size=Decimal("0.01"),
        commission_rate=Decimal("0.001"),
    )
    engine = BacktestEngine(config)
    result = engine.run(ticks, signals)

    assert result.processed_events > 0
    assert len(result.fills) == 2
    assert result.final_equity != config.initial_cash
    assert engine.portfolio.position.side is PositionSide.FLAT


def test_pipeline_serializes_result() -> None:
    root = Path(__file__).resolve().parents[1]
    result = run_backtest_pipeline(
        ticks_path=str(root / "samples" / "btcusdt_ticks.jsonl"),
        signals_path=str(root / "samples" / "btcusdt_signals.jsonl"),
        symbol="BTCUSDT",
        initial_cash=Decimal("10000"),
        position_size=Decimal("0.01"),
        commission_rate=Decimal("0.001"),
    )
    assert len(result.fills) == 2
