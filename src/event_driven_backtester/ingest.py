from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from event_driven_backtester.models import (
    SignalAction,
    SignalPayload,
    TradeTick,
    decimal_from_value,
    parse_signal_action,
    parse_signal_side,
    utc_from_iso8601,
)


def load_trade_ticks(path: str | Path, default_symbol: str) -> list[TradeTick]:
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"tick file not found: {file_path}")

    ticks: list[TradeTick] = []
    with file_path.open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid json on line {line_number}") from exc
            if not isinstance(payload, dict):
                raise ValueError(f"line {line_number} must contain a JSON object")
            ticks.append(parse_trade_tick(payload, default_symbol))

    if not ticks:
        raise ValueError("tick file is empty")
    return ticks


def load_signals(path: str | Path, default_symbol: str) -> list[SignalPayload]:
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"signal file not found: {file_path}")

    signals: list[SignalPayload] = []
    with file_path.open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid json on line {line_number}") from exc
            if not isinstance(payload, dict):
                raise ValueError(f"line {line_number} must contain a JSON object")
            signals.append(parse_signal_payload(payload, default_symbol))

    return signals


def parse_trade_tick(payload: dict[str, Any], default_symbol: str) -> TradeTick:
    required = ("price", "quantity", "event_time")
    for field in required:
        if field not in payload:
            raise ValueError(f"missing required field: {field}")

    symbol = str(payload.get("symbol", default_symbol))
    trade_id = str(payload.get("trade_id", f"tick-{symbol}-{payload['event_time']}"))
    if not symbol:
        raise ValueError("symbol must not be empty")

    return TradeTick(
        symbol=symbol,
        trade_id=trade_id,
        price=decimal_from_value(payload["price"], "price"),
        quantity=decimal_from_value(payload["quantity"], "quantity"),
        event_time=utc_from_iso8601(str(payload["event_time"])),
    )


def parse_signal_payload(payload: dict[str, Any], default_symbol: str) -> SignalPayload:
    required = ("strategy_id", "action", "reason", "event_time")
    for field in required:
        if field not in payload:
            raise ValueError(f"missing required field: {field}")

    symbol = str(payload.get("symbol", default_symbol))
    if not symbol:
        raise ValueError("symbol must not be empty")

    action = parse_signal_action(str(payload["action"]))
    side = parse_signal_side(payload.get("side"))
    reference_price = payload.get("reference_price")
    parsed_reference = (
        decimal_from_value(reference_price, "reference_price")
        if reference_price is not None
        else None
    )

    confidence_raw = payload.get("confidence", 0.0)
    confidence = float(confidence_raw)

    if action is SignalAction.HOLD and side is not None:
        side = None

    return SignalPayload(
        strategy_id=str(payload["strategy_id"]),
        symbol=symbol,
        action=action,
        side=side,
        confidence=confidence,
        reason=str(payload["reason"]),
        event_time=utc_from_iso8601(str(payload["event_time"])),
        reference_price=parsed_reference,
    )
