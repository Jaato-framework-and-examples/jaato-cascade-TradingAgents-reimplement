"""``python -m ta_cascade.score`` — grade one backtest cell against realised returns.

The deterministic half of a backtest.  A cell is one ``analyze`` run of
this driver for ``(ticker, trade_date)``; its output is the report tree,
and the only fact that can grade it is what the market did afterwards.  So
this reads ``results/<ticker>/<date>/state.json`` under the working
directory (the arm's workspace, when run as a jaato-eval ``script``
grader), takes the portfolio manager's rating, and asks
:func:`ta_cascade.data.return_after` for the return over the holding
period against the benchmark — the same function, period and benchmark
the decision log uses to resolve a live decision.

No model judges its own call.  The rule is code::

    Buy / Overweight     right when alpha > 0
    Underweight / Sell   right when alpha < 0
    Hold                 right when |alpha| <= hold band (default 1%)

where alpha is the instrument's holding-period return minus the
benchmark's.  The band is the one arbitrary number here and is a flag.

Exit codes, the contract a ``script`` grader reads: ``0`` the call was
right (PASS); ``1`` it was wrong (FAIL); ``75`` the cell cannot be graded
— no state, a rating outside the vocabulary, or not enough bars after the
trade date yet — which the engine records as BLOCKED, not as a wrong
call.  One JSON line of the facts goes to stdout so the verdict carries
the numbers, not only the bit.

Inputs come from the contract's exported params (``JAATO_EVAL_PARAM_TICKER``,
``JAATO_EVAL_PARAM_TRADE_DATE`` — the SAME variables the driver was given),
or from the command line for a run outside jaato-eval.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import fields
from pathlib import Path
from typing import Optional

from . import data
from .config import RATINGS, RunConfig
from .contract import EX_TEMPFAIL, params

#: A rating's direction: +1 long, -1 short, 0 flat.  Keyed on the shared
#: vocabulary so a rating outside it is a grading fault, not a silent 0.
DIRECTION = {"Buy": 1, "Overweight": 1, "Hold": 0, "Underweight": -1, "Sell": -1}
assert set(DIRECTION) == set(RATINGS)

_DEFAULTS = {f.name: f.default for f in fields(RunConfig)}


def grade(rating: str, alpha: float, hold_band: float) -> bool:
    """Was ``rating`` right, given ``alpha``?  See the module docstring."""
    direction = DIRECTION[rating]
    if direction == 0:
        return abs(alpha) <= hold_band
    return direction * alpha > 0


def score(ticker: str, trade_date: str, *, results_dir: Path, holding_days: int,
          benchmark: str, hold_band: float) -> int:
    """Grade one cell; print the facts; return the exit code."""
    state_path = results_dir / ticker / trade_date / "state.json"
    try:
        state = json.loads(state_path.read_text())
    except (OSError, ValueError) as exc:
        return _fault(f"no gradeable state at {state_path}: {exc}")
    rating = (state.get("portfolio_decision") or {}).get("rating")
    if rating not in DIRECTION:
        return _fault(f"rating {rating!r} is not one of {RATINGS}")
    got = data.return_after(ticker, trade_date, holding_days)
    bench = data.return_after(benchmark, trade_date, holding_days)
    if got is None or bench is None:
        return _fault(f"not enough bars after {trade_date} to resolve {holding_days} "
                      f"holding days for {ticker} and {benchmark}")
    raw, resolved_on = got
    alpha = raw - bench[0]
    right = grade(rating, alpha, hold_band)
    print(json.dumps({
        "ticker": ticker, "trade_date": trade_date, "rating": rating,
        "direction": DIRECTION[rating], "holding_days": holding_days,
        "resolved_on": resolved_on, "raw_return": round(raw, 6),
        "benchmark": benchmark, "benchmark_return": round(bench[0], 6),
        "alpha": round(alpha, 6), "hold_band": hold_band,
        "verdict": "PASS" if right else "FAIL",
    }))
    return 0 if right else 1


def _fault(message: str) -> int:
    print(json.dumps({"verdict": "BLOCKED", "reason": message}))
    return EX_TEMPFAIL


def main(argv: Optional[list] = None) -> int:
    given = params()
    p = argparse.ArgumentParser(prog="python -m ta_cascade.score", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("ticker", nargs="?", default=given.get("TICKER"))
    p.add_argument("trade_date", nargs="?", default=given.get("TRADE_DATE"))
    p.add_argument("--results-dir", type=Path, default=Path.cwd() / "results",
                   help="the driver's results tree (default: ./results, the arm workspace)")
    p.add_argument("--holding-days", type=int, default=_DEFAULTS["holding_days"])
    p.add_argument("--benchmark", default=_DEFAULTS["benchmark"])
    p.add_argument("--hold-band", type=float, default=0.01,
                   help="a Hold is right when |alpha| is within this (default 0.01 = 1%%)")
    args = p.parse_args(argv)
    if not args.ticker or not args.trade_date:
        return _fault("ticker and trade_date: pass them, or run under a jaato-eval contract "
                      "whose input.params carry TICKER and TRADE_DATE")
    return score(args.ticker.upper(), args.trade_date, results_dir=args.results_dir,
                 holding_days=args.holding_days, benchmark=args.benchmark,
                 hold_band=args.hold_band)


if __name__ == "__main__":
    sys.exit(main())
