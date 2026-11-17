from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from event_driven_backtester.models import (
    BacktestConfig,
    SignalAction,
    SignalPayload,
    SignalSide,
    TradeTick,
)
from event_driven_backtester.validation import (
    ValidationMethod,
    purged_kfold_splits,
    run_validation,
    walk_forward_splits,
)

T0 = datetime(2024, 1, 1, tzinfo=UTC)


def _spans(n: int, horizon: int) -> tuple[list[int], list[int]]:
    return [max(0, i - horizon + 1) for i in range(n)], list(range(n))


def test_purged_kfold_partitions_tests_and_never_overlaps_train() -> None:
    n, horizon = 103, 4
    starts, ends = _spans(n, horizon)
    folds = purged_kfold_splits(starts, ends, n_splits=5, embargo_pct=0.02)
    tested = sorted(i for fold in folds for i in fold.test)
    assert tested == list(range(n))
    for fold in folds:
        first, last = fold.test[0], fold.test[-1]
        test_lo, test_hi = starts[first], ends[last]
        for j in fold.train:
            assert j not in fold.test
            # purged: no training span may intersect the test block's information span
            assert ends[j] < test_lo or starts[j] > test_hi
        after = [j for j in fold.train if j > last]
        if after:
            # embargo: ceil(103 * 0.02) = 3 samples after the block plus the purge
            assert min(after) > last + 3


def test_purged_kfold_without_overlap_or_embargo_is_plain_kfold() -> None:
    starts, ends = _spans(20, 1)
    folds = purged_kfold_splits(starts, ends, n_splits=4)
    for fold in folds:
        assert len(fold.train) + len(fold.test) == 20
        assert fold.purged == 0


def test_purged_kfold_rejects_bad_input() -> None:
    with pytest.raises(ValueError):
        purged_kfold_splits([0, 1], [0, 1], n_splits=3)
    with pytest.raises(ValueError):
        purged_kfold_splits([1, 0, 2], [1, 1, 2], n_splits=2)
    with pytest.raises(ValueError):
        purged_kfold_splits([0, 1, 2], [0, 1, 2], n_splits=2, embargo_pct=1.0)


def test_walk_forward_rolling_and_anchored() -> None:
    rolling = walk_forward_splits(100, train_size=40, test_size=20, label_horizon=3)
    assert len(rolling) == 3
    for fold in rolling:
        assert max(fold.train) < min(fold.test) - 2  # 2 bars purged before each test window
        assert len(fold.train) == 38
    anchored = walk_forward_splits(100, train_size=40, test_size=20, anchored=True)
    assert [fold.train[0] for fold in anchored] == [0, 0, 0]
    assert len(anchored[-1].train) == 80


def test_walk_forward_needs_enough_samples() -> None:
    with pytest.raises(ValueError):
        walk_forward_splits(10, train_size=8, test_size=5)


def _ticks(prices: list[float]) -> list[TradeTick]:
    return [
        TradeTick(
            symbol="BTCUSDT",
            trade_id=str(index),
            price=Decimal(str(price)),
            quantity=Decimal("1"),
            event_time=T0 + timedelta(hours=index),
        )
        for index, price in enumerate(prices)
    ]


def _signal(hour: int, action: SignalAction, name: str) -> SignalPayload:
    return SignalPayload(
        strategy_id=name,
        symbol="BTCUSDT",
        action=action,
        side=SignalSide.LONG,
        confidence=0.9,
        reason="test",
        event_time=T0 + timedelta(hours=hour, minutes=1),
    )


def _cycle_signals(name: str, every: int, hold: int, hours: int) -> list[SignalPayload]:
    signals: list[SignalPayload] = []
    for start in range(0, hours - hold - 1, every):
        signals.append(_signal(start, SignalAction.ENTER, name))
        signals.append(_signal(start + hold, SignalAction.EXIT, name))
    return signals


CONFIG = BacktestConfig(
    symbol="BTCUSDT",
    initial_cash=Decimal("10000"),
    position_size=Decimal("1"),
    commission_rate=Decimal("0"),
)


def test_validation_selects_the_candidate_that_trades_an_uptrend() -> None:
    hours = 240
    prices = [100.0 + 0.5 * h + (3.0 if h % 2 else -3.0) for h in range(hours)]
    candidates = {
        "long_trend": _cycle_signals("long_trend", every=6, hold=5, hours=hours),
        "idle": [],
    }
    report = run_validation(
        _ticks(prices),
        candidates,
        CONFIG,
        bar_seconds=3600,
        method=ValidationMethod.PURGED_KFOLD,
        n_splits=4,
        embargo_pct=0.02,
    )
    assert report.n_bars == hours
    assert report.label_horizon == 5
    assert len(report.returns_matrix) == hours
    assert all(fold.selected == "long_trend" for fold in report.folds)
    assert report.oos_total_return > 0
    assert all(fold.purged_bars > 0 for fold in report.folds)


def test_walk_forward_report_only_scores_after_first_window() -> None:
    hours = 200
    prices = [100.0 + h * 0.1 for h in range(hours)]
    report = run_validation(
        _ticks(prices),
        {"a": _cycle_signals("a", 4, 2, hours), "b": _cycle_signals("b", 10, 3, hours)},
        CONFIG,
        bar_seconds=3600,
        method=ValidationMethod.WALK_FORWARD,
        train_bars=100,
        test_bars=25,
    )
    assert len(report.folds) == 4
    assert len(report.oos_returns) == 100
    assert report.folds[0].test_start == T0 + timedelta(hours=100)


def test_cli_validate_writes_matrix_for_metrics(tmp_path: Path) -> None:
    hours = 120
    ticks = tmp_path / "ticks.jsonl"
    ticks.write_text(
        "\n".join(
            json.dumps(
                {
                    "symbol": "BTCUSDT",
                    "trade_id": str(h),
                    "price": str(100 + h),
                    "quantity": "1",
                    "event_time": (T0 + timedelta(hours=h)).isoformat(),
                }
            )
            for h in range(hours)
        ),
        encoding="utf-8",
    )
    paths: list[str] = []
    for name, every in (("fast", 3), ("slow", 9)):
        path = tmp_path / f"{name}.jsonl"
        rows = [
            {
                "strategy_id": name,
                "symbol": "BTCUSDT",
                "action": signal.action.value,
                "side": signal.side.value if signal.side else None,
                "confidence": 0.5,
                "reason": "x",
                "event_time": signal.event_time.isoformat(),
            }
            for signal in _cycle_signals(name, every, 2, hours)
        ]
        path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")
        paths += ["--candidate", f"{name}={path}"]
    output = tmp_path / "report.json"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "event_driven_backtester",
            "validate",
            "--ticks",
            str(ticks),
            "--symbol",
            "BTCUSDT",
            *paths,
            "--n-splits",
            "4",
            "--output",
            str(output),
        ],
        check=True,
    )
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["method"] == "purged-kfold"
    assert report["returns_matrix"]["strategies"] == ["fast", "slow"]
    assert len(report["returns_matrix"]["returns"]) == report["n_bars"]
    assert report["returns_matrix"]["periods_per_year"] == 8760
