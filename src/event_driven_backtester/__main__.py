from __future__ import annotations

import argparse
import json
import logging
from decimal import Decimal

from event_driven_backtester.execution import signals_to_limit_orders
from event_driven_backtester.ingest import load_signals, load_trade_ticks
from event_driven_backtester.pipeline import (
    run_backtest_pipeline,
    run_validation_pipeline,
    serialize_backtest_result,
    serialize_validation_report,
)
from event_driven_backtester.validation import ValidationMethod


def _parse_candidate(raw: str) -> tuple[str, str]:
    name, sep, path = raw.partition("=")
    if not sep or not name or not path:
        raise argparse.ArgumentTypeError("candidate must look like name=signals.jsonl")
    return name, path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Simulador histórico guiado por eventos para ticks y señales.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    run = subparsers.add_parser("run", help="Ejecuta un backtest sobre ticks y señales JSONL.")
    run.add_argument("--ticks", required=True)
    run.add_argument("--signals", required=True)
    run.add_argument("--symbol", required=True)
    run.add_argument("--initial-cash", default="10000")
    run.add_argument("--position-size", default="0.01")
    run.add_argument("--commission-rate", default="0.001")
    run.add_argument(
        "--executions",
        default=None,
        help="Fills JSONL externos (p. ej. market-condition-simulator queue-fill); "
        "sustituyen al broker inmediato.",
    )
    run.add_argument("--output", default=None)

    orders = subparsers.add_parser(
        "orders", help="Convierte señales en órdenes límite pasivas (JSONL)."
    )
    orders.add_argument("--ticks", required=True)
    orders.add_argument("--signals", required=True)
    orders.add_argument("--symbol", required=True)
    orders.add_argument("--quantity", default="0.01")
    orders.add_argument("--offset-bps", default="0")
    orders.add_argument("--tick-size", default="0.01")
    orders.add_argument("--time-in-force-seconds", type=float, default=60.0)
    orders.add_argument("--output", required=True)

    validate = subparsers.add_parser(
        "validate",
        help="Out-of-sample selection: walk-forward or purged k-fold with embargo.",
    )
    validate.add_argument("--ticks", required=True)
    validate.add_argument(
        "--candidate",
        action="append",
        required=True,
        type=_parse_candidate,
        help="name=signals.jsonl (repeat once per strategy/parameter set)",
    )
    validate.add_argument("--symbol", required=True)
    validate.add_argument("--initial-cash", default="10000")
    validate.add_argument("--position-size", default="0.01")
    validate.add_argument("--commission-rate", default="0.001")
    validate.add_argument("--bar-seconds", type=int, default=3600)
    validate.add_argument(
        "--method",
        choices=[method.value for method in ValidationMethod],
        default=ValidationMethod.PURGED_KFOLD.value,
    )
    validate.add_argument("--n-splits", type=int, default=5)
    validate.add_argument("--embargo-pct", type=float, default=0.01)
    validate.add_argument("--train-bars", type=int, default=None)
    validate.add_argument("--test-bars", type=int, default=None)
    validate.add_argument("--step-bars", type=int, default=None)
    validate.add_argument("--anchored", action="store_true")
    validate.add_argument(
        "--label-horizon",
        type=int,
        default=None,
        help="bars of look-back purged around each test block (default: p90 holding time)",
    )
    validate.add_argument("--output", default=None)

    return parser


def main() -> None:
    args = build_parser().parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )

    if args.command == "run":
        result = run_backtest_pipeline(
            ticks_path=args.ticks,
            signals_path=args.signals,
            symbol=args.symbol,
            initial_cash=Decimal(args.initial_cash),
            position_size=Decimal(args.position_size),
            commission_rate=Decimal(args.commission_rate),
            executions_path=args.executions,
        )
        payload = serialize_backtest_result(result)
        rendered = json.dumps(payload, indent=2)

        if args.output:
            with open(args.output, "w", encoding="utf-8") as handle:
                handle.write(rendered)
                handle.write("\n")
            logging.getLogger(__name__).info(
                "wrote backtest result fills=%s to %s",
                len(result.fills),
                args.output,
            )
            return

        print(rendered)
        return

    if args.command == "orders":
        limit_orders = signals_to_limit_orders(
            load_trade_ticks(args.ticks, default_symbol=args.symbol),
            load_signals(args.signals, default_symbol=args.symbol),
            symbol=args.symbol,
            quantity=Decimal(args.quantity),
            offset_bps=Decimal(args.offset_bps),
            tick_size=Decimal(args.tick_size),
            time_in_force_seconds=args.time_in_force_seconds,
        )
        with open(args.output, "w", encoding="utf-8") as handle:
            for order in limit_orders:
                handle.write(json.dumps(order) + "\n")
        logging.getLogger(__name__).info("wrote %s limit orders", len(limit_orders))
        return

    if args.command == "validate":
        report = run_validation_pipeline(
            ticks_path=args.ticks,
            candidate_paths=dict(args.candidate),
            symbol=args.symbol,
            initial_cash=Decimal(args.initial_cash),
            position_size=Decimal(args.position_size),
            commission_rate=Decimal(args.commission_rate),
            bar_seconds=args.bar_seconds,
            method=ValidationMethod(args.method),
            n_splits=args.n_splits,
            embargo_pct=args.embargo_pct,
            train_bars=args.train_bars,
            test_bars=args.test_bars,
            step_bars=args.step_bars,
            anchored=args.anchored,
            label_horizon=args.label_horizon,
        )
        rendered = json.dumps(serialize_validation_report(report), indent=2)
        if args.output:
            with open(args.output, "w", encoding="utf-8") as handle:
                handle.write(rendered)
                handle.write("\n")
            logging.getLogger(__name__).info(
                "wrote validation report folds=%s oos_sharpe=%.4f to %s",
                len(report.folds),
                report.oos_sharpe,
                args.output,
            )
            return
        print(rendered)
        return

    raise RuntimeError(f"unsupported command: {args.command}")


if __name__ == "__main__":
    main()
