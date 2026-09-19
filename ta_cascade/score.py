"""``python -m ta_cascade.score`` — grade one backtest cell against realised returns.

The deterministic half of a backtest.  A cell is one ``analyze`` run of
this driver for ``(ticker, trade_date)``; its output is the report tree,
and the only fact that can grade it is what the market did afterwards.  So
this reads ``results/<ticker>/<date>/state.json`` under the working
directory (the arm's workspace, when run as a jaato-eval ``script``
grader), takes the portfolio manager's rating, and asks
:mod:`ta_cascade.data` for the holding period that followed — the same
period and benchmark the decision log uses to resolve a live decision.

No model judges its own call.  The rule is code::

    Buy / Overweight     right when alpha > 0
    Underweight / Sell   right when alpha < 0
    Hold                 right when |alpha| <= the hold band

where alpha is the instrument's holding-period return minus the
benchmark's.  Three things the first pilot taught (docs/gaps.md,
2026-09-19), each now part of the rule:

* **The hold band is the instrument's own volatility** — one ATR over the
  holding period, as a fraction of price (:func:`ta_cascade.data.hold_band`)
  — about 2 % a week for the index and 6–18 % for a volatile stock.  A
  fixed ±1 % failed nearly every Hold on a stock that moves 8 % a day,
  which made the headline hit rate a fact about the ruler.  ``--hold-band``
  still takes a number for anyone who wants a fixed rule.
* **A cell whose ticker IS the benchmark is scored on its raw return.**
  Index against index is alpha ≡ 0, under which Hold is always right and
  everything else always wrong — four cells that measured nothing.
* **A directional call with a stop is scored along the path.**  If a
  session's low (long) or high (short) crosses the trader's stop inside
  the holding period, the position is scored as stopped out at the stop,
  not at the period's close: an investor who set that stop was out.

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
from typing import Any, Dict, Optional

from . import data
from .config import RATINGS, RunConfig
from .contract import EX_TEMPFAIL, params

#: A rating's direction: +1 long, -1 short, 0 flat.  Keyed on the shared
#: vocabulary so a rating outside it is a grading fault, not a silent 0.
DIRECTION = {"Buy": 1, "Overweight": 1, "Hold": 0, "Underweight": -1, "Sell": -1}
assert set(DIRECTION) == set(RATINGS)

_DEFAULTS = {f.name: f.default for f in fields(RunConfig)}


def grade(rating: str, alpha: float, hold_band: float) -> bool:
    """Was ``rating`` right, given ``alpha`` and the band a Hold is allowed?"""
    direction = DIRECTION[rating]
    if direction == 0:
        return abs(alpha) <= hold_band
    return direction * alpha > 0


def _num(value) -> Optional[float]:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if f == f else None


def realised(path, entry: float, direction: int, stop: Optional[float]) -> Dict[str, Any]:
    """The holding period's return for a position opened at ``entry``, honouring ``stop``.

    ``path`` is the period's bars.  A long is stopped when a session's Low
    reaches the stop, a short when a High does; the return is then taken at
    the stop and the session named.  A flat call has no stop to honour.
    """
    close = float(path["Close"].iloc[-1])
    out: Dict[str, Any] = {"return": close / entry - 1, "stopped_out": False, "stopped_on": None}
    if direction == 0 or stop is None:
        return out
    for day, row in path.iterrows():
        hit = (direction > 0 and float(row["Low"]) <= stop) or (direction < 0 and float(row["High"]) >= stop)
        if hit:
            out.update({"return": stop / entry - 1, "stopped_out": True, "stopped_on": day.date().isoformat()})
            break
    return out


def score(ticker: str, trade_date: str, *, results_dir: Path, holding_days: int,
          benchmark: str, hold_band: Optional[float]) -> int:
    """Grade one cell; print the facts; return the exit code.

    ``hold_band=None`` means the instrument's own volatility band.
    """
    state_path = results_dir / ticker / trade_date / "state.json"
    try:
        state = json.loads(state_path.read_text())
    except (OSError, ValueError) as exc:
        return _fault(f"no gradeable state at {state_path}: {exc}")
    rating = (state.get("portfolio_decision") or {}).get("rating")
    if rating not in DIRECTION:
        return _fault(f"rating {rating!r} is not one of {RATINGS}")
    direction = DIRECTION[rating]
    path = data.path_after(ticker, trade_date, holding_days)
    if path is None:
        return _fault(f"not enough bars after {trade_date} to resolve {holding_days} holding days for {ticker}")
    entry = data.return_after(ticker, trade_date, holding_days)
    if entry is None:
        return _fault(f"no as-of close for {ticker} on {trade_date}")
    as_of_close = float(path["Close"].iloc[-1]) / (1 + entry[0])
    stop = _num((state.get("trader_proposal") or {}).get("stop_loss"))
    got = realised(path, as_of_close, direction, stop)

    against = None if ticker.upper() == benchmark.upper() else benchmark
    if against:
        bench = data.return_after(against, trade_date, holding_days)
        if bench is None:
            return _fault(f"not enough bars after {trade_date} to resolve {holding_days} holding days for {against}")
        alpha = got["return"] - bench[0]
    else:
        bench = None
        alpha = got["return"]
    band = hold_band if hold_band is not None else data.hold_band(ticker, trade_date, holding_days)
    right = grade(rating, alpha, band)
    print(json.dumps({
        "ticker": ticker, "trade_date": trade_date, "rating": rating, "direction": direction,
        "holding_days": holding_days, "resolved_on": entry[1],
        "raw_return": round(got["return"], 6), "stopped_out": got["stopped_out"], "stopped_on": got["stopped_on"],
        "stop": stop,
        "benchmark": against, "benchmark_return": round(bench[0], 6) if bench else None,
        "alpha": round(alpha, 6), "hold_band": round(band, 6),
        "hold_band_rule": "fixed" if hold_band is not None else "atr",
        "verdict": "PASS" if right else "FAIL",
    }))
    return 0 if right else 1


def _fault(message: str) -> int:
    print(json.dumps({"verdict": "BLOCKED", "reason": message}))
    return EX_TEMPFAIL


def _band_arg(text: str) -> Optional[float]:
    if text.lower() == "atr":
        return None
    return float(text)


def main(argv: Optional[list] = None) -> int:
    given = params()
    p = argparse.ArgumentParser(prog="python -m ta_cascade.score", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("ticker", nargs="?", default=given.get("TICKER"))
    p.add_argument("trade_date", nargs="?", default=given.get("TRADE_DATE"))
    p.add_argument("--results-dir", type=Path, default=Path.cwd() / "results",
                   help="the driver's results tree (default: ./results, the arm workspace)")
    p.add_argument("--holding-days", type=int, default=_DEFAULTS["holding_days"])
    p.add_argument("--benchmark", default=_DEFAULTS["benchmark"],
                   help="alpha is measured against it; a cell whose ticker is the benchmark scores its raw return")
    p.add_argument("--hold-band", type=_band_arg, default=None,
                   help="how far a Hold may move and be right: 'atr' (default: one ATR over the holding "
                        "period, as a fraction of price) or a fixed fraction such as 0.01")
    args = p.parse_args(argv)
    if not args.ticker or not args.trade_date:
        return _fault("ticker and trade_date: pass them, or run under a jaato-eval contract "
                      "whose input.params carry TICKER and TRADE_DATE")
    return score(args.ticker.upper(), args.trade_date, results_dir=args.results_dir,
                 holding_days=args.holding_days, benchmark=args.benchmark, hold_band=args.hold_band)


if __name__ == "__main__":
    sys.exit(main())
