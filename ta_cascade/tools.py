"""Host-tool specs over the data layer, per analyst.

A host tool is ``{name, description, parameters, handler, auto_approve}``:
the agent calls it, the driver process runs the handler, the return value
goes back as the tool result.  Every handler closes over the run's as-of
date so the model cannot ask for anything after it, and every one returns a
string (the data layer's contract), so a failure reaches the model as a
sentence rather than a stack trace.  Every handler's DEADLINE is derived from
the daemon's own budget for the call it serves (:func:`handler_deadline_s`),
so a slow dependency reaches the model as that sentence rather than as the
daemon's timeout error.
"""
from __future__ import annotations

import datetime as dt
from typing import Any, Callable, Dict, List, Optional

from jaato_sdk.client_tool_timeout import resolve_client_tool_timeout

from . import data
from .config import RunConfig

Spec = Dict[str, Any]

Recorder = Callable[[Dict[str, Any]], None]
"""Given the verified snapshot's facts, keeps them in the run state."""


HANDOFF_MARGIN_S = 5.0
"""How far OUR deadline fires before the daemon's budget for the same call.

The daemon holds each host-tool call to a budget and, on expiry, hands the
model ``{"error": "Client tool <name> timed out after <N>s"}`` — a transport
error where this repository's whole data contract is a sentence the model can
read.  So our deadline must fire first, and the margin covers the result
event's trip back: the handler returns, the string is encoded, the event
reaches the daemon.  That trip is NOT measured here; five seconds is chosen as
comfortably larger than a local socket round trip, and it is the only number
in this file, which is the point — see :func:`handler_deadline_s`.
"""


def handler_deadline_s(spec: Spec) -> float:
    """Seconds this spec's handler may take, derived from the daemon's budget.

    The budget is not ours to pick and is not written down here: it comes from
    ``jaato_sdk.client_tool_timeout``, the module the DAEMON's registration
    path also calls, so "the budget a client is told and the budget the daemon
    enforces cannot be two answers" (its docstring).  A spec that declares no
    ``timeout`` gets the framework's default, and if that default ever moves
    this follows it.  :func:`ta_cascade.sessions.check_tool_budgets` then
    checks the derived number against what the daemon REPORTS for the session,
    so the derivation is verified per run rather than trusted.  (jaato#1625.)
    """
    budget_s = resolve_client_tool_timeout(spec).timeout_s
    deadline = budget_s - HANDOFF_MARGIN_S
    if deadline <= 0:
        raise ValueError(
            f"{spec.get('name')}: the daemon's budget is {budget_s:.1f}s, which "
            f"leaves no room for a handler under the {HANDOFF_MARGIN_S:.1f}s "
            f"handoff margin — declare a larger `timeout` (ms) on the spec")
    return deadline


def declared_budgets(specs: List[Spec]) -> Dict[str, float]:
    """``{name: seconds}`` these specs expect the daemon to hold them to."""
    return {s["name"]: resolve_client_tool_timeout(s).timeout_s for s in specs}


def _spec(name: str, description: str, properties: Dict[str, Any], required: List[str],
          handler: Callable[[Dict[str, Any]], str]) -> Spec:
    spec: Spec = {
        "name": name,
        "description": description,
        "parameters": {
            "type": "object",
            "properties": properties,
            "required": required,
            "additionalProperties": False,
        },
        "auto_approve": True,
    }

    # Derived from the spec as the daemon will read it, so the handler cannot
    # outlive the call it serves.  `handler` is one of the lambdas below and
    # contains only OUR code, so `with_deadline` re-raises a NameError or
    # AttributeError from it instead of rendering it as DATA_UNAVAILABLE — see
    # its docstring for why that distinction is drawn here and not inside the
    # data layer.
    deadline = handler_deadline_s(spec)

    def guarded(args: Dict[str, Any]) -> str:
        return data.with_deadline(deadline, handler, args)

    guarded.__name__ = name
    spec["handler"] = guarded
    return spec


_DATE = {"type": "string", "description": "ISO date, YYYY-MM-DD"}
_LOOKBACK = {"type": "integer", "minimum": 5, "maximum": 120,
             "description": "calendar days up to the as-of date (default 30)"}


def market_tools(cfg: RunConfig, record: Optional[Recorder] = None) -> List[Spec]:
    as_of = cfg.trade_date
    stale = cfg.max_stale_days
    default_start = (dt.date.fromisoformat(as_of) - dt.timedelta(days=120)).isoformat()
    return [
        _spec(
            "get_price_history",
            f"Daily OHLCV bars for a symbol as CSV. Dates after {as_of} are never returned.",
            {"symbol": {"type": "string"}, "start_date": _DATE, "end_date": _DATE},
            ["symbol"],
            lambda a: data.ohlcv(a["symbol"], a.get("start_date", default_start),
                                 a.get("end_date", as_of), as_of, max_stale_days=stale),
        ),
        _spec(
            "get_indicators",
            "Technical indicators for every bar in the last N calendar days. Indicator "
            "periods (sma_20, rsi_14, ...) count trading sessions. Pass indicator names "
            "as a list; available: " + ", ".join(data.INDICATOR_CATALOG) + ".",
            {"symbol": {"type": "string"},
             "indicators": {"type": "array", "items": {"type": "string"}},
             "lookback_days": _LOOKBACK},
            ["symbol", "indicators"],
            lambda a: data.indicators(a["symbol"], a["indicators"], as_of, a.get("lookback_days", 30),
                                      max_stale_days=stale),
        ),
        _spec(
            "get_verified_snapshot",
            "The verified price facts a report may quote as exact numbers: last close, the "
            "window's high and low with their dates, change, moving averages, RSI, ATR and "
            "the latest closes with their dates. Call it before writing.",
            {"symbol": {"type": "string"}, "lookback_days": _LOOKBACK},
            ["symbol"],
            lambda a: data.snapshot(a["symbol"], as_of, a.get("lookback_days", 30),
                                    max_stale_days=stale, record=record),
        ),
    ]


def _week_before(as_of: str) -> str:
    """The default window's start: seven calendar days back from the as-of date."""
    return (dt.date.fromisoformat(as_of) - dt.timedelta(days=7)).isoformat()


def _company_news_spec(as_of: str) -> Spec:
    """``get_company_news`` — built here because TWO stages are given it.

    The news analyst reads it for events; the sentiment analyst reads it to say
    what the crowd is reacting to.  Sharing the BUILDER rather than the spec
    keeps one description and one default window while each stage still gets
    its own dict and its own closure.
    """
    week_ago = _week_before(as_of)
    return _spec(
        "get_company_news",
        f"Recent articles about a symbol, dated on or before {as_of}.",
        {"symbol": {"type": "string"}, "start_date": _DATE, "end_date": _DATE,
         "limit": {"type": "integer", "minimum": 1, "maximum": 50}},
        ["symbol"],
        lambda a: data.news(a["symbol"], a.get("start_date", week_ago),
                            a.get("end_date", as_of), as_of, a.get("limit", 20)),
    )


def _global_news_spec(as_of: str) -> Spec:
    """``get_global_news`` — shared by the news and sentiment stages, as above."""
    return _spec(
        "get_global_news",
        "Market-wide and macro headlines for the last N days.",
        {"lookback_days": {"type": "integer", "minimum": 1, "maximum": 30},
         "limit": {"type": "integer", "minimum": 1, "maximum": 50}},
        [],
        lambda a: data.global_news(as_of, a.get("lookback_days", 7), a.get("limit", 10)),
    )


def news_tools(cfg: RunConfig) -> List[Spec]:
    as_of = cfg.trade_date
    return [
        _company_news_spec(as_of),
        _global_news_spec(as_of),
        _spec(
            "get_insider_transactions",
            "Reported insider buys and sells for a symbol.",
            {"symbol": {"type": "string"}},
            ["symbol"],
            lambda a: data.insider_transactions(a["symbol"], as_of),
        ),
        _spec(
            "get_macro_series",
            "A macroeconomic series from FRED as it was known on the analysis date. "
            "Aliases: " + ", ".join(data.MACRO_SERIES) + "; or any FRED series id.",
            {"series": {"type": "string"},
             "lookback_days": {"type": "integer", "minimum": 30, "maximum": 3650}},
            ["series"],
            lambda a: data.macro(a["series"], as_of, a.get("lookback_days", 180)),
        ),
    ]


def fundamentals_tools(cfg: RunConfig) -> List[Spec]:
    as_of = cfg.trade_date
    stale = cfg.max_stale_days
    freq = {"type": "string", "enum": ["quarterly", "annual"]}
    return [
        _spec(
            "get_fundamentals",
            "Headline valuation, margin, growth and leverage ratios for a symbol.",
            {"symbol": {"type": "string"}},
            ["symbol"],
            lambda a: data.fundamentals(a["symbol"], as_of, max_stale_days=stale),
        ),
        _spec(
            "get_balance_sheet",
            "Balance sheet, periods ending on or before the analysis date.",
            {"symbol": {"type": "string"}, "freq": freq},
            ["symbol"],
            lambda a: data.statement(a["symbol"], "balance_sheet", a.get("freq", "quarterly"), as_of),
        ),
        _spec(
            "get_cashflow",
            "Cash-flow statement, periods ending on or before the analysis date.",
            {"symbol": {"type": "string"}, "freq": freq},
            ["symbol"],
            lambda a: data.statement(a["symbol"], "cashflow", a.get("freq", "quarterly"), as_of),
        ),
        _spec(
            "get_income_statement",
            "Income statement, periods ending on or before the analysis date.",
            {"symbol": {"type": "string"}, "freq": freq},
            ["symbol"],
            lambda a: data.statement(a["symbol"], "income", a.get("freq", "quarterly"), as_of),
        ),
    ]


def sentiment_tools(cfg: RunConfig) -> List[Spec]:
    """The crowd's material, and the news to read it against.

    The stage's job is to say where declared mood and reported events disagree,
    which needs both in one session — hence the two shared news specs beside
    the two social ones.

    Until 2026-10-17 these same four sources were fetched by a persona prefetch
    script instead (``{{!py?:scripts/prefetch_sentiment.py}}``), which ran
    inside the RUNNER and so required ``ta_cascade`` to be importable in the
    DAEMON's environment — the one workspace of thirteen that installed a
    driver package there.  As host tools they run in the driver process, out of
    this repository's own venv, which is also where the other three analysts'
    tools have always run.  See ``docs/gaps.md``, 2026-10-17.
    """
    as_of = cfg.trade_date
    week_ago = _week_before(as_of)
    return [
        _company_news_spec(as_of),
        _global_news_spec(as_of),
        _spec(
            "get_stocktwits_messages",
            "StockTwits messages for a symbol, with a tally of the user-applied "
            "Bullish/Bearish labels. The public symbol stream serves RECENT messages "
            "only, so a historical window is reported as quiet, never as unavailable.",
            {"symbol": {"type": "string"}, "start_date": _DATE, "end_date": _DATE,
             "limit": {"type": "integer", "minimum": 1, "maximum": 100}},
            ["symbol"],
            lambda a: data.stocktwits_messages(
                a["symbol"], a.get("start_date", week_ago), a.get("end_date", as_of),
                as_of, a.get("limit", 30)),
        ),
        _spec(
            "get_reddit_posts",
            "Posts mentioning a symbol in " + ", ".join(data.DEFAULT_SUBREDDITS) +
            ", inside the window. Each subreddit is reported as unavailable or as "
            "quiet separately, so one blocked feed is not read as silence.",
            {"symbol": {"type": "string"}, "start_date": _DATE, "end_date": _DATE},
            ["symbol"],
            lambda a: data.reddit_posts(
                a["symbol"], a.get("start_date", week_ago), a.get("end_date", as_of),
                as_of),
        ),
    ]


def host_tools(cfg: RunConfig, record: Optional[Recorder] = None) -> Dict[str, List[Spec]]:
    """Tool lists keyed by analyst key — every analyst has them.

    ``record`` is handed the verified snapshot's facts each time the market
    analyst asks for them, so the run keeps the numbers themselves and not
    only the report's retelling of them.
    """
    return {
        "market": market_tools(cfg, record),
        "news": news_tools(cfg),
        "fundamentals": fundamentals_tools(cfg),
        "sentiment": sentiment_tools(cfg),
    }
