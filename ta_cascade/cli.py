"""``python -m ta_cascade analyze TICKER DATE [options]``.

Exit codes: 0 finished; 1 a node failed (the journal keeps what was
produced, re-run to resume); 2 the daemon could not be reached or started.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import shutil
import sys
from pathlib import Path

from .config import ANALYST_KEYS, RunConfig
from .pipeline import StageFailed, run


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="ta_cascade", description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    a = sub.add_parser("analyze", help="run the pipeline for one ticker and date")
    a.add_argument("ticker")
    a.add_argument("trade_date", help="ISO date the analysis is as of")
    a.add_argument("--asset-type", choices=["stock", "crypto"], default="stock")
    a.add_argument("--analysts", default=",".join(ANALYST_KEYS),
                   help="comma-separated subset of " + ",".join(ANALYST_KEYS))
    a.add_argument("--debate-rounds", type=int, default=1)
    a.add_argument("--risk-rounds", type=int, default=1)
    a.add_argument("--workspace", type=Path, default=Path.cwd())
    a.add_argument("--env-file", type=Path, default=None)
    a.add_argument("--socket", default="/tmp/jaato.sock")
    a.add_argument("--no-journal", action="store_true", help="disable resume journaling")
    a.add_argument("--clear-journal", action="store_true", help="delete all journals first")
    a.add_argument("--no-memory", action="store_true",
                   help="neither score pending decisions nor record this one")
    a.add_argument("-v", "--verbose", action="store_true")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(levelname)s %(name)s: %(message)s")
    cfg = RunConfig(
        ticker=args.ticker, trade_date=args.trade_date, asset_type=args.asset_type,
        analysts=[s.strip() for s in args.analysts.split(",") if s.strip()],
        max_debate_rounds=args.debate_rounds, max_risk_rounds=args.risk_rounds,
        workspace=args.workspace, env_file=args.env_file, socket=args.socket,
    )
    if args.clear_journal and cfg.journal_dir.exists():
        shutil.rmtree(cfg.journal_dir)
    if args.no_journal:
        cfg.journal_dir = None  # type: ignore[assignment]
    try:
        state = asyncio.run(run(cfg, record_decision=not args.no_memory,
                                resolve_pending=not args.no_memory))
    except ConnectionError as exc:
        print(f"could not reach or start the daemon: {exc}\n"
              f"run: jaato-doctor --workspace {cfg.workspace} --env-file {cfg.env_file}",
              file=sys.stderr)
        return 2
    except StageFailed as exc:
        print(f"pipeline stopped: {exc}\nre-run the same command to resume from the journal.",
              file=sys.stderr)
        return 1
    decision = state.portfolio_decision or {}
    print(f"{cfg.ticker} {cfg.trade_date}: {decision.get('rating', 'REVIEW')}")
    print(decision.get("executive_summary", ""))
    print(f"report: {cfg.results_dir / cfg.ticker / cfg.trade_date / 'report.md'}")
    return 0
