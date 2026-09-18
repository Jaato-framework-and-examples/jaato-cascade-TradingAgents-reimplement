"""``python -m ta_cascade analyze TICKER DATE [options]``.

Exit codes: 0 finished; 1 a node failed (the journal keeps what was
produced, re-run to resume); 2 the daemon could not be reached or started.

Under a jaato-eval driver contract (:mod:`ta_cascade.contract`) the run
takes its workspace, config root, socket and cascade id from the
environment, and an unreachable daemon exits 75 instead of 2 — the code the
contract reserves for "the environment, not the run", which the engine
records as BLOCKED.  ``backtest-tasks`` writes the manifests such a sweep
runs (:mod:`ta_cascade.backtest`).
"""
from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import logging
import shutil
import sys
from pathlib import Path

from .backtest import date_grid, write_tasks
from .board import NullBoard
from .config import ANALYST_KEYS, RunConfig
from .contract import EX_TEMPFAIL, UnknownContract, from_environment
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
    a.add_argument("--display", choices=["auto", "board", "lines"], default="auto",
                   help="auto: draw the live board when stdout is a terminal, "
                        "plain lines otherwise; board/lines force one")
    b = sub.add_parser("backtest-tasks",
                       help="write jaato-eval tasks for tickers × a date grid under backtests/<name>/")
    b.add_argument("name", help="the matrix's name: backtests/<name>/tasks/<TICKER>-<DATE>/task.yaml")
    b.add_argument("--tickers", required=True, help="comma-separated symbols")
    b.add_argument("--from", dest="start", required=True, help="first analysis date, ISO")
    b.add_argument("--to", dest="end", required=True, help="last analysis date, ISO (inclusive)")
    b.add_argument("--every", type=int, default=7, help="calendar days between dates (default 7)")
    b.add_argument("--repeats", type=int, default=1, help="arms per cell; 5 for a determinism study")
    b.add_argument("--analysts", default="market",
                   help="comma-separated subset of " + ",".join(ANALYST_KEYS)
                        + " (default market: the news and social sources serve recent items only)")
    b.add_argument("--profile-set", default="openrouter_sonnet")
    b.add_argument("--repo", type=Path, default=Path.cwd(),
                   help="the repository root holding .jaato/ (default: cwd)")
    return p


def _backtest_tasks(args) -> int:
    dates = date_grid(dt.date.fromisoformat(args.start), dt.date.fromisoformat(args.end), args.every)
    written = write_tasks(args.repo, args.name, args.tickers.split(","), dates,
                          repeats=args.repeats, analysts=args.analysts.split(","),
                          profile_set=args.profile_set)
    print(f"{len(written)} task(s) under {args.repo / 'backtests' / args.name / 'tasks'} "
          f"({len(dates)} date(s) × {len(args.tickers.split(','))} ticker(s), repeats {args.repeats})")
    print(f"run: jaato-eval run backtests/{args.name}/tasks --profile-set {args.profile_set} "
          f"--socket /tmp/jaato.sock --out backtests/{args.name}/results.jsonl "
          f"--workspaces /tmp/{args.name}-ws --arm-timeout 1200 --resume")
    return 0


class _BoardLogHandler(logging.Handler):
    """Routes log records into the board's trace panel.

    A drawing board owns the terminal: ``rich.Live`` redraws its region on
    every refresh, and a stream handler writing to the same terminal
    interleaves with that and corrupts both.  So when the board draws, the
    log does not go to the terminal — it goes INTO the board, which is also
    where an operator is already looking.
    """

    def __init__(self, board) -> None:
        super().__init__()
        self._board = board

    def emit(self, record: logging.LogRecord) -> None:
        self._board.trace(self.format(record))


def _build_board(mode: str):
    """Pick the display; return ``(board, draws)``.

    ``auto`` draws only when stdout is a real terminal.  Piped or redirected
    — ``| tee``, CI, a captured log — the plain lines are kept, because that
    output is the artifact people grep and a live view would either fight the
    pipe or emit nothing useful into it.
    """
    if mode == "lines" or (mode == "auto" and not sys.stdout.isatty()):
        return NullBoard(), False
    from .richboard import RichBoard
    return RichBoard(), True


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "backtest-tasks":
        return _backtest_tasks(args)
    try:
        contract = from_environment()
    except UnknownContract as exc:
        print(f"refusing the jaato-eval contract: {exc}", file=sys.stderr)
        return EX_TEMPFAIL
    board, draws = _build_board(args.display)
    # The root stays at INFO so a dependency's own DEBUG stream (yfinance and
    # its peewee cache emit hundreds of lines per fetch) can never bury the
    # pipeline.  ``-v`` deepens this package only: verbosity is about the
    # cascade, not about every library that happens to share the process.
    if draws:
        # rich.Live owns the terminal: anything else writing to it interleaves
        # with the redraw and corrupts both.  So the root gets a NullHandler
        # (nothing reaches the terminal) and THIS package's records go to the
        # trace panel instead.  Allowlisting our own namespace rather than
        # silencing libraries by name keeps it from needing an entry per
        # dependency, the same rule the -v fix follows.
        logging.basicConfig(level=logging.INFO, handlers=[logging.NullHandler()])
        handler = _BoardLogHandler(board)
        handler.setFormatter(logging.Formatter("%(message)s"))
        logging.getLogger(__package__).addHandler(handler)
    else:
        logging.basicConfig(level=logging.INFO,
                            format="%(levelname)s %(name)s: %(message)s")
    logging.getLogger(__package__).setLevel(
        logging.DEBUG if args.verbose else logging.INFO)
    cfg = RunConfig(
        ticker=args.ticker, trade_date=args.trade_date, asset_type=args.asset_type,
        analysts=[s.strip() for s in args.analysts.split(",") if s.strip()],
        max_debate_rounds=args.debate_rounds, max_risk_rounds=args.risk_rounds,
        # Under the contract the engine chose these; the flags describe a run
        # it did not start.
        workspace=contract.workspace if contract else args.workspace,
        env_file=args.env_file,
        socket=(contract.socket or args.socket) if contract else args.socket,
        config_root=contract.config_root if contract else None,
        cascade_id=contract.cascade_id if contract else None,
    )
    if args.clear_journal and cfg.journal_dir.exists():
        shutil.rmtree(cfg.journal_dir)
    if args.no_journal:
        cfg.journal_dir = None  # type: ignore[assignment]
    try:
        with board:
            state = asyncio.run(run(cfg, record_decision=not args.no_memory,
                                    resolve_pending=not args.no_memory, board=board))
    except ConnectionError as exc:
        print(f"could not reach or start the daemon: {exc}\n"
              f"run: jaato-doctor --workspace {cfg.workspace} --env-file {cfg.env_file}",
              file=sys.stderr)
        # An engine-run arm whose daemon is gone learned nothing about the
        # configuration under test: BLOCKED (75), not a failed run (2).
        return EX_TEMPFAIL if contract else 2
    except StageFailed as exc:
        print(f"pipeline stopped: {exc}\nre-run the same command to resume from the journal.",
              file=sys.stderr)
        return 1
    decision = state.portfolio_decision or {}
    print(f"{cfg.ticker} {cfg.trade_date}: {decision.get('rating', 'REVIEW')}")
    print(decision.get("executive_summary", ""))
    print(f"report: {cfg.results_dir / cfg.ticker / cfg.trade_date / 'report.md'}")
    return 0
