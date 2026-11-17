from __future__ import annotations

from decimal import Decimal
from typing import Any

from event_driven_backtester.engine import BacktestEngine
from event_driven_backtester.ingest import load_signals, load_trade_ticks
from event_driven_backtester.models import BacktestConfig, BacktestResult
from event_driven_backtester.validation import (
    ValidationMethod,
    ValidationReport,
    run_validation,
)


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


def serialize_validation_report(report: ValidationReport) -> dict[str, Any]:
    return {
        "method": report.method.value,
        "symbol": report.symbol,
        "bar_seconds": report.bar_seconds,
        "n_bars": report.n_bars,
        "label_horizon_bars": report.label_horizon,
        "embargo_pct": report.embargo_pct,
        "candidates": list(report.candidates),
        "full_sample_sharpe": report.full_sample_sharpe,
        "oos_sharpe": report.oos_sharpe,
        "oos_total_return": report.oos_total_return,
        "oos_bars": len(report.oos_returns),
        "folds": [
            {
                "index": fold.index,
                "train_bars": fold.train_bars,
                "test_bars": fold.test_bars,
                "purged_bars": fold.purged_bars,
                "test_start": fold.test_start.isoformat(),
                "test_end": fold.test_end.isoformat(),
                "selected": fold.selected,
                "in_sample_sharpe": fold.in_sample_sharpe,
                "out_of_sample_sharpe": fold.out_of_sample_sharpe,
                "out_of_sample_return": fold.out_of_sample_return,
                "candidate_oos_sharpe": fold.candidate_oos_sharpe,
            }
            for fold in report.folds
        ],
        "returns_matrix": {
            "strategies": list(report.candidates),
            "returns": [list(row) for row in report.returns_matrix],
            "periods_per_year": report.periods_per_year,
            "bar_times": [moment.isoformat() for moment in report.bar_times],
        },
    }


def run_validation_pipeline(
    ticks_path: str,
    candidate_paths: dict[str, str],
    symbol: str,
    initial_cash: Decimal,
    position_size: Decimal,
    commission_rate: Decimal,
    *,
    bar_seconds: int,
    method: ValidationMethod,
    n_splits: int = 5,
    embargo_pct: float = 0.01,
    train_bars: int | None = None,
    test_bars: int | None = None,
    step_bars: int | None = None,
    anchored: bool = False,
    label_horizon: int | None = None,
) -> ValidationReport:
    ticks = load_trade_ticks(ticks_path, default_symbol=symbol)
    candidates = {
        name: load_signals(path, default_symbol=symbol) for name, path in candidate_paths.items()
    }
    config = BacktestConfig(
        symbol=symbol,
        initial_cash=initial_cash,
        position_size=position_size,
        commission_rate=commission_rate,
    )
    return run_validation(
        ticks,
        candidates,
        config,
        bar_seconds=bar_seconds,
        method=method,
        n_splits=n_splits,
        embargo_pct=embargo_pct,
        train_bars=train_bars,
        test_bars=test_bars,
        step_bars=step_bars,
        anchored=anchored,
        label_horizon=label_horizon,
    )
