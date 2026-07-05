# event-driven-backtester

**Event-driven** historical simulator that replays market ticks and strategy signals second by second to evaluate realistic execution paths. Sixth module of the [quant-core-infra](https://github.com/juanmmm21/quant-core-infra) ecosystem.

Repository: [github.com/juanmmm21/event-driven-backtester](https://github.com/juanmmm21/event-driven-backtester)

---

## What it is and what problem it solves

Vectorized backtesters (applying a rule to an entire column of prices at once) are fast but **unrealistic**: they assume instant execution at candle close, with no temporal ordering between ticks and signals, and no intermediate portfolio state.

This module simulates the passage of time as in production:

1. A tick arrives → the market price is updated
2. A signal arrives → an order is sent to the simulated broker
3. The order is executed at the last known price
4. The portfolio records cash, position, and the equity curve

Each step is an **event** processed in strict chronological order.

---

## Role in quant-core-infra

```text
websocket-feed-handler ──► ticks JSONL ──┐
alpha-signal-generator ──► signals JSONL ──► event-driven-backtester
                                                    │
                                          market-condition-simulator (friction)
                                                    │
                                          quant-metrics-calculator (metrics)
```

Validates whether the signals from `alpha-signal-generator` would have been profitable with rigorous decimal accounting.

---

## Objective

Demonstrates:

- Event-driven simulation vs. vectorized loops
- Deterministic chronological replay
- Portfolio accounting with `Decimal`
- JSONL integration with upstream modules

---

## Event model

| Event | Origin | Effect |
|--------|--------|--------|
| `new_tick` | Trades JSONL | Updates mark price and equity |
| `signal` | Signals JSONL | Creates a market order |
| (internal) fill | Simulated broker | Updates cash and position |

Ordering: `(event_time, sequence)` — ticks are queued before signals with the same timestamp.

---

## How it works

1. **Load:** ticks and signals from JSONL.
2. **Queue:** `EventQueue` (heap) orders all events chronologically.
3. **Tick:** updates the price in the broker and marks the portfolio to market.
4. **`enter` signal:** the broker creates a BUY order if there is no long position.
5. **`exit` signal:** the broker creates a SELL order if there is a long position.
6. **Fill:** applied to the portfolio (cash ± notional ± commission).
7. **Result:** `BacktestResult` with fills, equity curve, and final PnL.

### `BacktestConfig` parameters

| Field | Description | Example |
|-------|-------------|---------|
| `initial_cash` | Initial capital | `10000` |
| `position_size` | Fixed amount per trade | `0.01` BTC |
| `commission_rate` | Proportional commission | `0.001` (0.1 %) |

---

## Architecture

```text
Ticks JSONL + Signals JSONL
        │
        ▼
EventQueue (priority heap)
        │
        ▼
BacktestEngine
   ├─ Portfolio (cash, positions, equity curve)
   ├─ SimulatedBroker (market fills)
   └─ EventBus (extensible handler registry)
        │
        ▼
BacktestResult
```

### Components

| Module | Responsibility |
|--------|----------------|
| `queue.py` | Chronological priority queue |
| `portfolio.py` | Cash, positions, equity curve |
| `broker.py` | Signal → order → fill translation |
| `engine.py` | Main replay loop |
| `ingest.py` | JSONL parsing |
| `pipeline.py` | End-to-end run + serialization |

### Technical decisions

- **Decimal** for balances, prices, and commissions
- **Ticks before signals** at identical timestamps
- **Immediate fills** at last price (latency/slippage handled in `market-condition-simulator`)
- **Silent rejection** of invalid fills (insufficient cash) for loop robustness

---

## Requirements

- Python **3.11+**

---

## Installation

```bash
cd event-driven-backtester
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

---

## CLI usage

```bash
event-driven-backtester run \
  --ticks samples/btcusdt_ticks.jsonl \
  --signals samples/btcusdt_signals.jsonl \
  --symbol BTCUSDT \
  --initial-cash 10000 \
  --position-size 0.01 \
  --commission-rate 0.001 \
  --output result.json
```

### Expected output (excerpt)

```json
{
  "symbol": "BTCUSDT",
  "initial_cash": "10000",
  "final_equity": "10002.45",
  "fill_count": 2,
  "fills": [
    {
      "side": "buy",
      "price": "102.0",
      "quantity": "0.01",
      "commission": "0.00102"
    }
  ],
  "equity_curve": [...]
}
```

---

## JSONL formats

### Ticks

```json
{
  "symbol": "BTCUSDT",
  "trade_id": "12345",
  "price": "102.0",
  "quantity": "0.01",
  "event_time": "2024-01-01T12:02:00Z"
}
```

### Signals

```json
{
  "strategy_id": "rsi_mean_reversion",
  "symbol": "BTCUSDT",
  "action": "enter",
  "side": "long",
  "confidence": 0.8,
  "reason": "rsi oversold",
  "event_time": "2024-01-01T12:02:00Z",
  "reference_price": "102.0"
}
```

---

## Programmatic usage

```python
from decimal import Decimal

from event_driven_backtester import BacktestConfig, BacktestEngine, run_backtest_pipeline

result = run_backtest_pipeline(
    ticks_path="ticks.jsonl",
    signals_path="signals.jsonl",
    symbol="BTCUSDT",
    initial_cash=Decimal("10000"),
    position_size=Decimal("0.01"),
    commission_rate=Decimal("0.001"),
)

print(f"fills: {len(result.fills)}, equity: {result.final_equity}")
```

---

## Development

```bash
pytest -q
ruff check src tests
mypy src
```

---

## Roadmap

- [ ] Short selling and margin support
- [ ] Direct integration with `market-condition-simulator`
- [ ] Multiple symbols in a single backtest

---

## License

MIT
