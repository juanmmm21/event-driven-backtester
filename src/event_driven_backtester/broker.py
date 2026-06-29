from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

from event_driven_backtester.models import (
    BacktestConfig,
    Fill,
    Order,
    OrderSide,
    OrderStatus,
    PositionSide,
    SignalAction,
    SignalPayload,
    SignalSide,
)


class SimulatedBroker:
    """Ejecuta órdenes de mercado al último precio conocido."""

    def __init__(self, config: BacktestConfig) -> None:
        self._config = config
        self._last_price: Decimal | None = None

    def update_market_price(self, price: Decimal) -> None:
        if price <= Decimal("0"):
            raise ValueError("price must be positive")
        self._last_price = price

    def create_order_from_signal(
        self,
        signal: SignalPayload,
        open_position: PositionSide,
    ) -> Order | None:
        if signal.symbol != self._config.symbol:
            return None
        if signal.action is SignalAction.HOLD:
            return None

        if signal.action is SignalAction.ENTER:
            if signal.side is not SignalSide.LONG:
                return None
            if open_position is PositionSide.LONG:
                return None
            return self._build_order(OrderSide.BUY, signal)

        if signal.action is SignalAction.EXIT:
            if open_position is not PositionSide.LONG:
                return None
            return self._build_order(OrderSide.SELL, signal)

        return None

    def fill_order(self, order: Order) -> Fill:
        if self._last_price is None:
            raise ValueError("cannot fill order without a market price")
        if order.status is not OrderStatus.PENDING:
            raise ValueError("only pending orders can be filled")

        notional = self._last_price * order.quantity
        commission = notional * self._config.commission_rate
        return Fill(
            order_id=order.order_id,
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,
            price=self._last_price,
            commission=commission,
            filled_at=order.submitted_at,
        )

    def _build_order(self, side: OrderSide, signal: SignalPayload) -> Order:
        return Order(
            order_id=str(uuid4()),
            symbol=signal.symbol,
            side=side,
            quantity=self._config.position_size,
            status=OrderStatus.PENDING,
            submitted_at=signal.event_time,
            signal_id=signal.strategy_id,
        )
