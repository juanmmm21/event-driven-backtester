from __future__ import annotations

import argparse
import json
import logging
from decimal import Decimal

from event_driven_backtester.pipeline import run_backtest_pipeline, serialize_backtest_result


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
    run.add_argument("--output", default=None)

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

    raise RuntimeError(f"unsupported command: {args.command}")


if __name__ == "__main__":
    main()
