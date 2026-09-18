"""The chart beside the report: the run's recommendation, drawn on the data it was made from.

A run's output is a rating and several thousand characters of reasoning.
Every claim the reasoning makes about price — "above all three moving
averages", "resistance at the May high", "stop at 208" — is a claim a
chart either shows or does not, so the driver draws one from the same
bars and indicators the verified snapshot was computed from, and links it
from ``report.md``.  The model never sees it: it is for the reader, and it
is drawn by code, not by a model, for the same reason the snapshot is.

What is on it:

* candlesticks over a 120-calendar-day context ending at the as-of date,
  the 20/50/200-session SMAs and the Bollinger band, volume below;
* the span's highest high and lowest low, each with its date — the levels
  a report calls "the May high" or "the June low";
* the trader's entry and stop and the portfolio manager's target as
  horizontal lines, when the payloads carry them;
* the final rating, in the corner;
* for a backtest cell, the bars after the as-of date that make up the
  holding period, shaded and labelled as what came after — the scorer's
  verdict, visible.

Drawing happens after the decision is made.  A chart that cannot be drawn
(no bars, a fetch that failed) is logged with its reason and the run is
still a finished run; :func:`render` returns ``None`` and the report
carries no link.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from . import data
from .config import RunConfig
from .state import RunState

log = logging.getLogger(__name__)

CONTEXT_DAYS = 120
"""Calendar days of price history on the chart, ending at the as-of date."""

FILENAME = "chart.png"

_UP, _DOWN = "#1e7a4c", "#a33a3d"
_SMA = {"sma_20": "#2f5f8f", "sma_50": "#7a6f3a", "sma_200": "#5c6b79"}


def _num(value) -> Optional[float]:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if f == f else None


def draw(context, outcome, state: RunState, out_path: Path, *, holding_days: int) -> Path:
    """Draw ``context`` (with indicator columns) and ``outcome`` bars for ``state`` to ``out_path``.

    Pure over its frames: the tests draw synthetic bars.  ``outcome`` may be
    empty.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt
    import pandas as pd
    from matplotlib.ticker import FuncFormatter

    bars = pd.concat([context, outcome]) if len(outcome) else context
    fig, (ax, vol) = plt.subplots(2, 1, figsize=(12, 7.2), dpi=110, sharex=True,
                                  gridspec_kw={"height_ratios": [4, 1], "hspace": 0.04})
    fig.patch.set_facecolor("white")

    # Candles: one thin line for the range, one thick line for the body.
    up = bars["Close"] >= bars["Open"]
    colours = [(_UP if u else _DOWN) for u in up]
    ax.vlines(bars.index, bars["Low"], bars["High"], color=colours, linewidth=0.8)
    ax.vlines(bars.index, bars[["Open", "Close"]].min(axis=1), bars[["Open", "Close"]].max(axis=1),
              color=colours, linewidth=4.0)
    vol.bar(bars.index, bars["Volume"], color=colours, width=0.7, alpha=0.6)

    for col, colour in _SMA.items():
        if col in context and context[col].notna().any():
            ax.plot(context.index, context[col], color=colour, linewidth=1.1, label=col.upper().replace("_", " "))
    if {"bb_upper", "bb_lower"} <= set(context.columns) and context["bb_upper"].notna().any():
        ax.fill_between(context.index, context["bb_lower"], context["bb_upper"], color="#2f5f8f", alpha=0.07, linewidth=0)

    # The span's extremes, dated: the levels the prose names.
    hi_at, lo_at = context["High"].idxmax(), context["Low"].idxmin()
    ax.annotate(f"high {context.at[hi_at, 'High']:.2f}\n{hi_at.date()}", (hi_at, context.at[hi_at, "High"]),
                textcoords="offset points", xytext=(0, 10), ha="center", fontsize=8, color="#1b232c")
    ax.annotate(f"low {context.at[lo_at, 'Low']:.2f}\n{lo_at.date()}", (lo_at, context.at[lo_at, "Low"]),
                textcoords="offset points", xytext=(0, -24), ha="center", fontsize=8, color="#1b232c")

    # The decision's levels, from the payloads that carry them.
    tp, pdn = state.trader_proposal or {}, state.portfolio_decision or {}
    levels = [("entry", _num(tp.get("entry_price")), "#1b232c", "-"),
              ("stop", _num(tp.get("stop_loss")), _DOWN, "--"),
              ("target", _num(pdn.get("price_target")), _UP, "--")]
    for name, value, colour, style in levels:
        if value is not None:
            ax.axhline(value, color=colour, linestyle=style, linewidth=1.0)
            ax.annotate(f"{name} {value:.2f}", (bars.index[-1], value), textcoords="offset points",
                        xytext=(6, 0), fontsize=8, color=colour, va="center")

    if len(outcome):
        ax.axvspan(context.index[-1], outcome.index[-1], color="#7a6f3a", alpha=0.08, linewidth=0)
        first, last = float(context["Close"].iloc[-1]), float(outcome["Close"].iloc[-1])
        # At the foot of the span, not the top: the span's high is often the
        # as-of high, and its dated label already sits up there.
        ax.annotate(f"after the as-of date: {holding_days} sessions, {100 * (last / first - 1):+.2f}%",
                    (outcome.index[0], ax.get_ylim()[0]), textcoords="offset points", xytext=(4, 6),
                    fontsize=8, color="#7a6f3a", va="bottom")

    rating = pdn.get("rating") or "no rating"
    ax.text(0.01, 0.97, f"{state.ticker} as of {state.trade_date}\n{rating}", transform=ax.transAxes,
            fontsize=11, fontweight="bold", va="top", ha="left", color="#1b232c")
    ax.legend(loc="lower left", fontsize=8, frameon=False)
    ax.set_ylabel("price"); vol.set_ylabel("volume")
    ax.grid(True, color="#e3e7eb", linewidth=0.6); vol.grid(True, color="#e3e7eb", linewidth=0.6)
    for a in (ax, vol):
        a.set_facecolor("white"); a.spines[["top", "right"]].set_visible(False)
    vol.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
    vol.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v / 1e6:.0f}M"))
    fig.autofmt_xdate()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, bbox_inches="tight")
    plt.close(fig)
    return out_path


def render(state: RunState, cfg: RunConfig) -> Optional[Path]:
    """Fetch the frames and draw the chart into the run's results directory.

    Returns the file written, or ``None`` with the reason logged: the chart
    is drawn after the decision, and a picture that cannot be drawn does not
    un-make a decision.
    """
    out = Path(cfg.results_dir) / state.ticker / state.trade_date / FILENAME
    try:
        context, outcome = data.chart_frames(state.ticker, state.trade_date,
                                             context_days=CONTEXT_DAYS, holding_days=cfg.holding_days)
        return draw(context, outcome, state, out, holding_days=cfg.holding_days)
    except Exception as exc:  # noqa: BLE001 — a missing picture is not a failed run
        log.warning("chart not drawn for %s %s: %s: %s", state.ticker, state.trade_date,
                    type(exc).__name__, exc)
        return None
