from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum


class EventType(StrEnum):
    NEW_TICK = "new_tick"
    SIGNAL = "signal"
    ORDER_SUBMITTED = "order_submitted"
    ORDER_FILLED = "order_filled"
    BACKTEST_END = "backtest_end"


class OrderSide(StrEnum):
    BUY = "buy"
    SELL = "sell"


class OrderStatus(StrEnum):
    PENDING = "pending"
    FILLED = "filled"
    REJECTED = "rejected"


class PositionSide(StrEnum):
    FLAT = "flat"
    LONG = "long"


class SignalAction(StrEnum):
    ENTER = "enter"
    EXIT = "exit"
    HOLD = "hold"


class SignalSide(StrEnum):
    LONG = "long"
    SHORT = "short"


@dataclass(frozen=True, slots=True)
class TradeTick:
    symbol: str
    trade_id: str
    price: Decimal
    quantity: Decimal
    event_time: datetime

    def __post_init__(self) -> None:
        if not self.symbol:
            raise ValueError("symbol must not be empty")
        if not self.trade_id:
            raise ValueError("trade_id must not be empty")
        if self.price <= Decimal("0"):
            raise ValueError("price must be positive")
        if self.quantity <= Decimal("0"):
            raise ValueError("quantity must be positive")
        if self.event_time.tzinfo is None:
            raise ValueError("event_time must be timezone-aware")


@dataclass(frozen=True, slots=True)
class SignalPayload:
    strategy_id: str
    symbol: str
    action: SignalAction
    side: SignalSide | None
    confidence: float
    reason: str
    event_time: datetime
    reference_price: Decimal | None = None

    def __post_init__(self) -> None:
        if not self.strategy_id:
            raise ValueError("strategy_id must not be empty")
        if not self.symbol:
            raise ValueError("symbol must not be empty")
        if not self.reason:
            raise ValueError("reason must not be empty")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        if self.event_time.tzinfo is None:
            raise ValueError("event_time must be timezone-aware")
        if self.action in {SignalAction.ENTER, SignalAction.EXIT} and self.side is None:
            raise ValueError("side is required for enter and exit actions")


@dataclass(frozen=True, slots=True)
class Order:
    order_id: str
    symbol: str
    side: OrderSide
    quantity: Decimal
    status: OrderStatus
    submitted_at: datetime
    signal_id: str
    fill_price: Decimal | None = None
    filled_at: datetime | None = None
    commission: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        if not self.order_id:
            raise ValueError("order_id must not be empty")
        if self.quantity <= Decimal("0"):
            raise ValueError("quantity must be positive")
        if self.submitted_at.tzinfo is None:
            raise ValueError("submitted_at must be timezone-aware")
        if self.commission < Decimal("0"):
            raise ValueError("commission must be non-negative")


@dataclass(frozen=True, slots=True)
class Fill:
    order_id: str
    symbol: str
    side: OrderSide
    quantity: Decimal
    price: Decimal
    commission: Decimal
    filled_at: datetime

    def __post_init__(self) -> None:
        if self.price <= Decimal("0"):
            raise ValueError("price must be positive")
        if self.quantity <= Decimal("0"):
            raise ValueError("quantity must be positive")
        if self.commission < Decimal("0"):
            raise ValueError("commission must be non-negative")
        if self.filled_at.tzinfo is None:
            raise ValueError("filled_at must be timezone-aware")


@dataclass(frozen=True, slots=True)
class Position:
    symbol: str
    side: PositionSide
    quantity: Decimal
    average_price: Decimal

    def __post_init__(self) -> None:
        if self.side is PositionSide.FLAT:
            if self.quantity != Decimal("0"):
                raise ValueError("flat position must have zero quantity")
            return
        if self.quantity <= Decimal("0"):
            raise ValueError("open position quantity must be positive")
        if self.average_price <= Decimal("0"):
            raise ValueError("average_price must be positive")


@dataclass(frozen=True, slots=True)
class EquityPoint:
    event_time: datetime
    cash: Decimal
    equity: Decimal
    position_value: Decimal

    def __post_init__(self) -> None:
        if self.event_time.tzinfo is None:
            raise ValueError("event_time must be timezone-aware")


@dataclass(frozen=True, slots=True)
class BacktestConfig:
    symbol: str
    initial_cash: Decimal
    position_size: Decimal
    commission_rate: Decimal = Decimal("0.001")

    def __post_init__(self) -> None:
        if not self.symbol:
            raise ValueError("symbol must not be empty")
        if self.initial_cash <= Decimal("0"):
            raise ValueError("initial_cash must be positive")
        if self.position_size <= Decimal("0"):
            raise ValueError("position_size must be positive")
        if self.commission_rate < Decimal("0"):
            raise ValueError("commission_rate must be non-negative")


@dataclass(frozen=True, slots=True)
class BacktestResult:
    config: BacktestConfig
    fills: tuple[Fill, ...]
    equity_curve: tuple[EquityPoint, ...]
    final_cash: Decimal
    final_equity: Decimal
    processed_events: int


@dataclass(order=True, slots=True)
class BacktestEvent:
    sort_index: tuple[datetime, int]
    event_type: EventType
    payload: TradeTick | SignalPayload | Order | Fill | None

    @classmethod
    def from_tick(cls, tick: TradeTick, sequence: int) -> BacktestEvent:
        return cls(
            sort_index=(tick.event_time, sequence),
            event_type=EventType.NEW_TICK,
            payload=tick,
        )

    @classmethod
    def from_signal(cls, signal: SignalPayload, sequence: int) -> BacktestEvent:
        return cls(
            sort_index=(signal.event_time, sequence),
            event_type=EventType.SIGNAL,
            payload=signal,
        )

    @classmethod
    def end_marker(cls, event_time: datetime, sequence: int) -> BacktestEvent:
        return cls(
            sort_index=(event_time, sequence),
            event_type=EventType.BACKTEST_END,
            payload=None,
        )


def utc_from_iso8601(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def decimal_from_value(value: object, field_name: str) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float, str)):
        return Decimal(str(value))
    raise ValueError(f"{field_name} must be numeric")


def parse_signal_action(value: str) -> SignalAction:
    try:
        return SignalAction(value)
    except ValueError as exc:
        raise ValueError(f"unsupported signal action: {value}") from exc


def parse_signal_side(value: str | None) -> SignalSide | None:
    if value is None:
        return None
    try:
        return SignalSide(value)
    except ValueError as exc:
        raise ValueError(f"unsupported signal side: {value}") from exc
