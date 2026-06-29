# event-driven-backtester

Simulador histórico **guiado por eventos** que reproduce ticks de mercado y señales de estrategia segundo a segundo para evaluar rutas de ejecución realistas. Sexto módulo del ecosistema [quant-core-infra](https://github.com/juanmmm21/quant-core-infra).

Repositorio: [github.com/juanmmm21/event-driven-backtester](https://github.com/juanmmm21/event-driven-backtester)

---

## Qué es y qué problema resuelve

Los backtesters vectorizados (aplicar una regla a toda una columna de precios de golpe) son rápidos pero **irreales**: asumen ejecución instantánea al cierre de la vela, sin orden temporal entre ticks y señales, y sin estado de cartera intermedio.

Este módulo simula el paso del tiempo como en producción:

1. Llega un tick → se actualiza el precio de mercado
2. Llega una señal → se envía una orden al broker simulado
3. La orden se ejecuta al último precio conocido
4. La cartera registra cash, posición y curva de equity

Cada paso es un **evento** procesado en orden cronológico estricto.

---

## Rol en quant-core-infra

```text
websocket-feed-handler ──► ticks JSONL ──┐
alpha-signal-generator ──► signals JSONL ──► event-driven-backtester
                                                    │
                                          market-condition-simulator (fricciones)
                                                    │
                                          quant-metrics-calculator (métricas)
```

Valida si las señales de `alpha-signal-generator` habrían sido rentables con contabilidad decimal rigurosa.

---

## Objetivo

Demuestra:

- Simulación event-driven vs bucles vectorizados
- Replay cronológico determinista
- Contabilidad de cartera con `Decimal`
- Integración JSONL con módulos upstream

---

## Modelo de eventos

| Evento | Origen | Efecto |
|--------|--------|--------|
| `new_tick` | JSONL de trades | Actualiza mark price y equity |
| `signal` | JSONL de señales | Crea orden de mercado |
| (interno) fill | Broker simulado | Actualiza cash y posición |

Ordenación: `(event_time, sequence)` — los ticks se encolan antes que las señales con el mismo timestamp.

---

## Cómo funciona

1. **Carga:** ticks y señales desde JSONL.
2. **Cola:** `EventQueue` (heap) ordena todos los eventos cronológicamente.
3. **Tick:** actualiza precio en broker y marca la cartera a mercado.
4. **Señal `enter`:** broker crea orden BUY si no hay posición long.
5. **Señal `exit`:** broker crea orden SELL si hay posición long.
6. **Fill:** se aplica al portfolio (cash ± notional ± comisión).
7. **Resultado:** `BacktestResult` con fills, equity curve y PnL final.

### Parámetros de `BacktestConfig`

| Campo | Descripción | Ejemplo |
|-------|-------------|---------|
| `initial_cash` | Capital inicial | `10000` |
| `position_size` | Cantidad fija por operación | `0.01` BTC |
| `commission_rate` | Comisión proporcional | `0.001` (0.1 %) |

---

## Arquitectura

```text
Ticks JSONL + Signals JSONL
        │
        ▼
EventQueue (priority heap)
        │
        ▼
BacktestEngine
   ├─ Portfolio (cash, posiciones, equity curve)
   ├─ SimulatedBroker (fills a mercado)
   └─ EventBus (registro extensible de handlers)
        │
        ▼
BacktestResult
```

### Componentes

| Módulo | Responsabilidad |
|--------|----------------|
| `queue.py` | Cola de prioridad cronológica |
| `portfolio.py` | Cash, posiciones, curva de equity |
| `broker.py` | Traducción señal → orden → fill |
| `engine.py` | Bucle principal de replay |
| `ingest.py` | Parsing JSONL |
| `pipeline.py` | Run end-to-end + serialización |

### Decisiones técnicas

- **Decimal** en balances, precios y comisiones
- **Ticks antes que señales** en timestamps idénticos
- **Fills inmediatos** a último precio (latencia/slippage en `market-condition-simulator`)
- **Rechazo silencioso** de fills inválidos (cash insuficiente) para robustez del loop

---

## Requisitos

- Python **3.11+**

---

## Instalación

```bash
cd event-driven-backtester
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

---

## Uso CLI

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

### Salida esperada (extracto)

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

## Formatos JSONL

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

### Señales

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

## Uso programático

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

## Desarrollo

```bash
pytest -q
ruff check src tests
mypy src
```

---

## Roadmap

- [ ] Soporte short selling y margin
- [ ] Integración directa con `market-condition-simulator`
- [ ] Múltiples símbolos en un mismo backtest

---

## Licencia

MIT
