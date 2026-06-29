# event-driven-backtester

**Event-driven historical simulator** that replays market ticks and strategy signals second by second to evaluate realistic execution paths. Sixth module of the [quant-core-infra](https://github.com/juanmmm21/quant-core-infra) ecosystem.

Repository: [github.com/juanmmm21/event-driven-backtester](https://github.com/juanmmm21/event-driven-backtester)

---

## Objective

This project demonstrates:

- Event-driven simulation instead of naive vectorized loops
- Strict chronological replay with deterministic ordering
- Decimal-based portfolio accounting
- JSONL integration with `websocket-feed-handler`, `alpha-signal-generator`

---

## Event model

| Event | Source | Effect |
|-------|--------|--------|
| `new_tick` | Trade JSONL | Updates mark price and equity |
| `signal` | Signal JSONL | Submits market order via simulated broker |
| `order_filled` | Internal | Updates cash and position state |

Events are ordered by `(event_time, sequence)` to break ties deterministically.

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
   ├─ SimulatedBroker (market fills at last price)
   └─ EventBus (extensible handler registry)
        │
        ▼
BacktestResult (fills, equity curve, final PnL)
```

### Core components

| Module | Responsibility |
|--------|----------------|
| `models.py` | Events, orders, fills, portfolio state |
| `queue.py` | Chronological event priority queue |
| `portfolio.py` | Decimal cash/position tracking |
| `broker.py` | Signal-to-order translation and fills |
| `engine.py` | Main event replay loop |
| `ingest.py` | JSONL parsing for ticks and signals |
| `pipeline.py` | End-to-end run and serialization |

### Technical decisions

- **Decimal** for balances, prices, commissions
- **Ticks processed before signals** at identical timestamps
- **Immediate market fills** at last known price (latency/slippage deferred to `market-condition-simulator`)
- **Silent rejection** of invalid fills (e.g. insufficient cash) to keep the replay loop resilient

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
  --position-size 0.01
```

---

## JSONL formats

### Trade ticks (`websocket-feed-handler` compatible)

```json
{
  "symbol": "BTCUSDT",
  "trade_id": "12345",
  "price": "102.0",
  "quantity": "0.01",
  "event_time": "2024-01-01T12:02:00Z"
}
```

### Strategy signals (`alpha-signal-generator` compatible)

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

engine = BacktestEngine(
    BacktestConfig(
        symbol="BTCUSDT",
        initial_cash=Decimal("10000"),
        position_size=Decimal("0.01"),
    )
)
```

---

## Development

```bash
pytest -q
ruff check src tests
mypy src
```

---

## Ecosystem integration

```text
websocket-feed-handler ──► ticks JSONL ──┐
alpha-signal-generator ──► signals JSONL ──► event-driven-backtester ──► quant-metrics-calculator
```

---

## License

MIT
