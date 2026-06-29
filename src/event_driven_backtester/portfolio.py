from __future__ import annotations

from decimal import Decimal

from event_driven_backtester.models import EquityPoint, Fill, Position, PositionSide


class Portfolio:
    """Gestiona cash, posiciones y curva de equity con precisión decimal."""

    def __init__(self, initial_cash: Decimal, symbol: str) -> None:
        if initial_cash <= Decimal("0"):
            raise ValueError("initial_cash must be positive")
        self._symbol = symbol
        self._cash = initial_cash
        self._position = Position(
            symbol=symbol,
            side=PositionSide.FLAT,
            quantity=Decimal("0"),
            average_price=Decimal("0"),
        )
        self._last_price: Decimal | None = None
        self._equity_curve: list[EquityPoint] = []
        self._fills: list[Fill] = []

    @property
    def cash(self) -> Decimal:
        return self._cash

    @property
    def position(self) -> Position:
        return self._position

    @property
    def fills(self) -> tuple[Fill, ...]:
        return tuple(self._fills)

    @property
    def equity_curve(self) -> tuple[EquityPoint, ...]:
        return tuple(self._equity_curve)

    def update_mark_price(self, price: Decimal, event_time: object) -> None:
        if price <= Decimal("0"):
            raise ValueError("price must be positive")
        self._last_price = price
        self._record_equity(event_time)

    def apply_fill(self, fill: Fill) -> None:
        notional = fill.price * fill.quantity
        if fill.side.value == "buy":
            total_cost = notional + fill.commission
            if self._cash < total_cost:
                raise ValueError("insufficient cash for buy fill")
            self._cash -= total_cost
            self._open_long(fill.quantity, fill.price)
        else:
            if self._position.side is not PositionSide.LONG:
                raise ValueError("cannot sell without an open long position")
            if fill.quantity > self._position.quantity:
                raise ValueError("sell quantity exceeds position size")
            proceeds = notional - fill.commission
            self._cash += proceeds
            remaining = self._position.quantity - fill.quantity
            if remaining == Decimal("0"):
                self._position = Position(
                    symbol=self._symbol,
                    side=PositionSide.FLAT,
                    quantity=Decimal("0"),
                    average_price=Decimal("0"),
                )
            else:
                self._position = Position(
                    symbol=self._symbol,
                    side=PositionSide.LONG,
                    quantity=remaining,
                    average_price=self._position.average_price,
                )

        self._fills.append(fill)
        self._record_equity(fill.filled_at)

    def equity(self) -> Decimal:
        position_value = self._position_value()
        return self._cash + position_value

    def _open_long(self, quantity: Decimal, price: Decimal) -> None:
        if self._position.side is PositionSide.FLAT:
            self._position = Position(
                symbol=self._symbol,
                side=PositionSide.LONG,
                quantity=quantity,
                average_price=price,
            )
            return

        total_quantity = self._position.quantity + quantity
        weighted_price = (
            (self._position.average_price * self._position.quantity) + (price * quantity)
        ) / total_quantity
        self._position = Position(
            symbol=self._symbol,
            side=PositionSide.LONG,
            quantity=total_quantity,
            average_price=weighted_price,
        )

    def _position_value(self) -> Decimal:
        if self._position.side is PositionSide.FLAT or self._last_price is None:
            return Decimal("0")
        return self._position.quantity * self._last_price

    def _record_equity(self, event_time: object) -> None:
        from datetime import datetime

        if not isinstance(event_time, datetime):
            raise TypeError("event_time must be a datetime")
        if event_time.tzinfo is None:
            raise ValueError("event_time must be timezone-aware")

        position_value = self._position_value()
        self._equity_curve.append(
            EquityPoint(
                event_time=event_time,
                cash=self._cash,
                equity=self._cash + position_value,
                position_value=position_value,
            )
        )
