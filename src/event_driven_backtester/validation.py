"""Out-of-sample validation: walk-forward and purged k-fold cross-validation with embargo.

Every candidate (one signal stream per strategy/parameter set) is replayed once through the
event-driven engine. Its equity curve is sampled on a regular bar grid, giving one return per
bar. Each fold then chooses the candidate with the best Sharpe on its *training* bars only and
scores that choice on the *test* bars it never saw.

Bar ``i``'s return depends on decisions taken up to ``label_horizon - 1`` bars earlier (an open
position carries information from when it was entered), so each sample is treated as the span
``[i - h + 1, i]``. Training samples whose span overlaps the test block are purged, and an
embargo drops the samples right after the test block to stop serial correlation leaking back.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from enum import StrEnum

from event_driven_backtester.engine import BacktestEngine
from event_driven_backtester.models import (
    BacktestConfig,
    BacktestResult,
    OrderSide,
    SignalPayload,
    TradeTick,
)

SECONDS_PER_YEAR = 365 * 24 * 3600


class ValidationMethod(StrEnum):
    WALK_FORWARD = "walk-forward"
    PURGED_KFOLD = "purged-kfold"


@dataclass(frozen=True, slots=True)
class Fold:
    index: int
    train: tuple[int, ...]
    test: tuple[int, ...]
    purged: int = 0


def walk_forward_splits(
    n_samples: int,
    *,
    train_size: int,
    test_size: int,
    step: int | None = None,
    anchored: bool = False,
    label_horizon: int = 1,
) -> list[Fold]:
    """Rolling (or anchored) train window followed by a test window.

    The last ``label_horizon - 1`` training samples are purged because their returns overlap
    the first test sample's information set.
    """
    if train_size <= 0 or test_size <= 0:
        raise ValueError("train_size and test_size must be positive")
    if label_horizon < 1:
        raise ValueError("label_horizon must be at least 1")
    stride = step or test_size
    if stride <= 0:
        raise ValueError("step must be positive")
    purge = label_horizon - 1
    folds: list[Fold] = []
    test_start = train_size
    while test_start + test_size <= n_samples:
        train_start = 0 if anchored else test_start - train_size
        train_end = test_start - purge
        if train_end - train_start < 2:
            raise ValueError("label_horizon purges the whole training window")
        folds.append(
            Fold(
                index=len(folds),
                train=tuple(range(train_start, train_end)),
                test=tuple(range(test_start, test_start + test_size)),
                purged=purge,
            )
        )
        test_start += stride
    if not folds:
        raise ValueError("not enough samples for a single walk-forward fold")
    return folds


def purged_kfold_splits(
    label_starts: Sequence[int],
    label_ends: Sequence[int],
    *,
    n_splits: int,
    embargo_pct: float = 0.0,
) -> list[Fold]:
    """K-fold over contiguous blocks with purging and embargo (López de Prado, AFML ch. 7).

    ``label_starts[i]``/``label_ends[i]`` bound the information used by sample ``i`` (inclusive,
    non-decreasing starts). A training sample is kept only if its span ends before the test block
    starts, or starts after both the test block's last span and the embargo window.
    """
    n_samples = len(label_starts)
    if len(label_ends) != n_samples:
        raise ValueError("label_starts and label_ends must have the same length")
    if n_splits < 2 or n_splits > n_samples:
        raise ValueError("n_splits must be between 2 and the number of samples")
    if not 0.0 <= embargo_pct < 1.0:
        raise ValueError("embargo_pct must be in [0, 1)")
    if any(b < a for a, b in zip(label_starts, label_starts[1:], strict=False)):
        raise ValueError("label_starts must be non-decreasing")
    if any(end < start for start, end in zip(label_starts, label_ends, strict=True)):
        raise ValueError("every label must end at or after its start")

    embargo = math.ceil(n_samples * embargo_pct)
    base, extra = divmod(n_samples, n_splits)
    folds: list[Fold] = []
    start = 0
    for index in range(n_splits):
        size = base + (1 if index < extra else 0)
        first, last = start, start + size - 1
        start += size
        test_begin = label_starts[first]
        test_end = max(label_ends[first : last + 1])
        embargo_last = min(last + embargo, n_samples - 1)
        train: list[int] = []
        for candidate in range(n_samples):
            if first <= candidate <= last:
                continue
            ends_before = label_ends[candidate] < test_begin
            starts_after = label_starts[candidate] > test_end and candidate > embargo_last
            if ends_before or starts_after:
                train.append(candidate)
        folds.append(
            Fold(
                index=index,
                train=tuple(train),
                test=tuple(range(first, last + 1)),
                purged=n_samples - size - len(train),
            )
        )
    return folds


def bar_edges(start: datetime, end: datetime, bar_seconds: int) -> list[datetime]:
    """Bar boundaries ``start, start+bar, ...`` up to the first edge at or after ``end``."""
    if bar_seconds <= 0:
        raise ValueError("bar_seconds must be positive")
    if end <= start:
        raise ValueError("end must be after start")
    step = timedelta(seconds=bar_seconds)
    edges = [start]
    while edges[-1] < end:
        edges.append(edges[-1] + step)
    return edges


def sample_bar_returns(
    result: BacktestResult, edges: Sequence[datetime], initial_equity: Decimal
) -> list[float]:
    """Equity sampled at each bar close (last known value), turned into simple returns."""
    curve = result.equity_curve
    returns: list[float] = []
    cursor = 0
    previous = initial_equity
    for edge in edges[1:]:
        while cursor < len(curve) and curve[cursor].event_time < edge:
            cursor += 1
        current = curve[cursor - 1].equity if cursor > 0 else initial_equity
        returns.append(float((current - previous) / previous) if previous > 0 else 0.0)
        previous = current
    return returns


def holding_bars(result: BacktestResult, bar_seconds: int) -> list[int]:
    """Length in bars of every closed round trip (buy then sell)."""
    durations: list[int] = []
    opened: datetime | None = None
    for fill in result.fills:
        if fill.side is OrderSide.BUY and opened is None:
            opened = fill.filled_at
        elif fill.side is OrderSide.SELL and opened is not None:
            seconds = (fill.filled_at - opened).total_seconds()
            durations.append(max(1, math.ceil(seconds / bar_seconds)))
            opened = None
    return durations


def sharpe(values: Sequence[float]) -> float:
    """Per-period Sharpe of ``values``; 0 for fewer than two points or zero volatility."""
    n = len(values)
    if n < 2:
        return 0.0
    mean = math.fsum(values) / n
    variance = math.fsum((value - mean) ** 2 for value in values) / (n - 1)
    if variance <= 1e-30:
        return 0.0
    return mean / math.sqrt(variance)


def compound(values: Sequence[float]) -> float:
    total = 1.0
    for value in values:
        total *= 1.0 + value
    return total - 1.0


@dataclass(frozen=True, slots=True)
class FoldReport:
    index: int
    train_bars: int
    test_bars: int
    purged_bars: int
    test_start: datetime
    test_end: datetime
    selected: str
    in_sample_sharpe: float
    out_of_sample_sharpe: float
    out_of_sample_return: float
    candidate_oos_sharpe: dict[str, float]


@dataclass(frozen=True, slots=True)
class ValidationReport:
    method: ValidationMethod
    symbol: str
    bar_seconds: int
    n_bars: int
    label_horizon: int
    embargo_pct: float
    candidates: tuple[str, ...]
    full_sample_sharpe: dict[str, float]
    folds: tuple[FoldReport, ...]
    oos_returns: tuple[float, ...]
    oos_sharpe: float
    oos_total_return: float
    returns_matrix: tuple[tuple[float, ...], ...]
    bar_times: tuple[datetime, ...] = field(default_factory=tuple)

    @property
    def periods_per_year(self) -> int:
        return SECONDS_PER_YEAR // self.bar_seconds


def run_validation(
    ticks: Sequence[TradeTick],
    candidates: Mapping[str, Sequence[SignalPayload]],
    config: BacktestConfig,
    *,
    bar_seconds: int,
    method: ValidationMethod = ValidationMethod.PURGED_KFOLD,
    n_splits: int = 5,
    embargo_pct: float = 0.01,
    train_bars: int | None = None,
    test_bars: int | None = None,
    step_bars: int | None = None,
    anchored: bool = False,
    label_horizon: int | None = None,
) -> ValidationReport:
    if not candidates:
        raise ValueError("at least one candidate is required")
    relevant = sorted(
        (tick for tick in ticks if tick.symbol == config.symbol), key=lambda t: t.event_time
    )
    if len(relevant) < 2:
        raise ValueError("need at least two ticks for the configured symbol")
    edges = bar_edges(relevant[0].event_time, relevant[-1].event_time, bar_seconds)
    # Prices are known at a bar's close, so a tick stamped exactly on the last edge belongs to
    # the last bar: extend by one bar so it is sampled.
    if edges[-1] == relevant[-1].event_time:
        edges.append(edges[-1] + timedelta(seconds=bar_seconds))

    names = tuple(sorted(candidates))
    columns: dict[str, list[float]] = {}
    horizons: list[int] = []
    for name in names:
        result = BacktestEngine(config).run(list(relevant), list(candidates[name]))
        columns[name] = sample_bar_returns(result, edges, config.initial_cash)
        horizons.extend(holding_bars(result, bar_seconds))

    n_bars = len(edges) - 1
    horizon = label_horizon or _auto_horizon(horizons)
    if method is ValidationMethod.WALK_FORWARD:
        train = train_bars or max(n_bars // 2, 2)
        test = test_bars or max((n_bars - train) // n_splits, 1)
        folds = walk_forward_splits(
            n_bars,
            train_size=train,
            test_size=test,
            step=step_bars,
            anchored=anchored,
            label_horizon=horizon,
        )
    else:
        starts = [max(0, index - horizon + 1) for index in range(n_bars)]
        folds = purged_kfold_splits(
            starts, list(range(n_bars)), n_splits=n_splits, embargo_pct=embargo_pct
        )

    reports: list[FoldReport] = []
    oos: list[tuple[int, float]] = []
    for fold in folds:
        is_scores = {name: sharpe([columns[name][i] for i in fold.train]) for name in names}
        oos_scores = {name: sharpe([columns[name][i] for i in fold.test]) for name in names}
        selected = max(names, key=lambda name: (is_scores[name], name))
        test_returns = [columns[selected][i] for i in fold.test]
        oos.extend((i, columns[selected][i]) for i in fold.test)
        reports.append(
            FoldReport(
                index=fold.index,
                train_bars=len(fold.train),
                test_bars=len(fold.test),
                purged_bars=fold.purged,
                test_start=edges[fold.test[0]],
                test_end=edges[fold.test[-1] + 1],
                selected=selected,
                in_sample_sharpe=is_scores[selected],
                out_of_sample_sharpe=oos_scores[selected],
                out_of_sample_return=compound(test_returns),
                candidate_oos_sharpe=oos_scores,
            )
        )

    oos.sort(key=lambda item: item[0])
    oos_returns = tuple(value for _, value in oos)
    matrix = tuple(tuple(columns[name][i] for name in names) for i in range(n_bars))
    return ValidationReport(
        method=method,
        symbol=config.symbol,
        bar_seconds=bar_seconds,
        n_bars=n_bars,
        label_horizon=horizon,
        embargo_pct=embargo_pct if method is ValidationMethod.PURGED_KFOLD else 0.0,
        candidates=names,
        full_sample_sharpe={name: sharpe(columns[name]) for name in names},
        folds=tuple(reports),
        oos_returns=oos_returns,
        oos_sharpe=sharpe(oos_returns),
        oos_total_return=compound(oos_returns),
        returns_matrix=matrix,
        bar_times=tuple(edges[1:]),
    )


def _auto_horizon(durations: list[int]) -> int:
    """90th percentile of round-trip lengths in bars (1 when nothing traded)."""
    if not durations:
        return 1
    ordered = sorted(durations)
    return ordered[min(len(ordered) - 1, math.ceil(0.9 * len(ordered)) - 1)]
