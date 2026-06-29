from __future__ import annotations

from event_driven_backtester.broker import SimulatedBroker
from event_driven_backtester.models import (
    BacktestConfig,
    BacktestEvent,
    BacktestResult,
    EventType,
    Fill,
    SignalAction,
    SignalPayload,
    TradeTick,
)
from event_driven_backtester.portfolio import Portfolio
from event_driven_backtester.queue import EventQueue


class BacktestEngine:
    """Motor guiado por eventos que reproduce ticks y señales en orden temporal."""

    def __init__(self, config: BacktestConfig) -> None:
        self._config = config
        self._portfolio = Portfolio(config.initial_cash, config.symbol)
        self._broker = SimulatedBroker(config)
        self._processed_events = 0

    @property
    def portfolio(self) -> Portfolio:
        return self._portfolio

    def run(
        self,
        ticks: list[TradeTick],
        signals: list[SignalPayload],
    ) -> BacktestResult:
        if not ticks:
            raise ValueError("ticks must not be empty")

        queue = self._build_queue(ticks, signals)
        for event in queue:
            self._processed_events += 1
            if event.event_type is EventType.NEW_TICK:
                self._on_tick(event)
            elif event.event_type is EventType.SIGNAL:
                self._on_signal(event)

        return BacktestResult(
            config=self._config,
            fills=self._portfolio.fills,
            equity_curve=self._portfolio.equity_curve,
            final_cash=self._portfolio.cash,
            final_equity=self._portfolio.equity(),
            processed_events=self._processed_events,
        )

    def _build_queue(
        self,
        ticks: list[TradeTick],
        signals: list[SignalPayload],
    ) -> EventQueue:
        queue = EventQueue()
        for tick in ticks:
            if tick.symbol != self._config.symbol:
                continue
            queue.push(BacktestEvent.from_tick(tick, queue.next_sequence()))

        for signal in signals:
            if signal.symbol != self._config.symbol:
                continue
            if signal.action is SignalAction.HOLD:
                continue
            queue.push(BacktestEvent.from_signal(signal, queue.next_sequence()))

        return queue

    def _on_tick(self, event: BacktestEvent) -> None:
        payload = event.payload
        if not isinstance(payload, TradeTick):
            raise TypeError("new_tick event requires TradeTick payload")
        self._broker.update_market_price(payload.price)
        self._portfolio.update_mark_price(payload.price, payload.event_time)

    def _on_signal(self, event: BacktestEvent) -> None:
        payload = event.payload
        if not isinstance(payload, SignalPayload):
            raise TypeError("signal event requires SignalPayload payload")

        position_side = self._portfolio.position.side
        order = self._broker.create_order_from_signal(payload, position_side)
        if order is None:
            return

        fill = self._broker.fill_order(order)
        self._apply_fill(fill)

    def _apply_fill(self, fill: Fill) -> None:
        try:
            self._portfolio.apply_fill(fill)
        except ValueError:
            return
