"""Host-tool specs over the data layer, per analyst.

A host tool is ``{name, description, parameters, handler, auto_approve}``:
the agent calls it, the driver process runs the handler, the return value
goes back as the tool result.  Every handler closes over the run's as-of
date so the model cannot ask for anything after it, and every one returns a
string (the data layer's contract), so a failure reaches the model as a
sentence rather than a stack trace.
"""
from __future__ import annotations

import datetime as dt
from typing import Any, Callable, Dict, List

from . import data
from .config import RunConfig

Spec = Dict[str, Any]


TOOL_BUDGET_S = 45.0
"""Seconds a data tool may take before the model is told the data was unavailable."""


def _spec(name: str, description: str, properties: Dict[str, Any], required: List[str],
          handler: Callable[[Dict[str, Any]], str]) -> Spec:
    def guarded(args: Dict[str, Any]) -> str:
        return data.with_deadline(TOOL_BUDGET_S, handler, args)

    guarded.__name__ = name
    return {
        "name": name,
        "description": description,
        "parameters": {
            "type": "object",
            "properties": properties,
            "required": required,
            "additionalProperties": False,
        },
        "handler": guarded,
        "auto_approve": True,
    }


_DATE = {"type": "string", "description": "ISO date, YYYY-MM-DD"}


def market_tools(cfg: RunConfig) -> List[Spec]:
    as_of = cfg.trade_date
    default_start = (dt.date.fromisoformat(as_of) - dt.timedelta(days=120)).isoformat()
    return [
        _spec(
            "get_price_history",
            f"Daily OHLCV bars for a symbol as CSV. Dates after {as_of} are never returned.",
            {"symbol": {"type": "string"}, "start_date": _DATE, "end_date": _DATE},
            ["symbol"],
            lambda a: data.ohlcv(a["symbol"], a.get("start_date", default_start),
                                 a.get("end_date", as_of), as_of),
        ),
        _spec(
            "get_indicators",
            "Technical indicators for the last N bars. Pass indicator names as a list; "
            "available: " + ", ".join(data.INDICATOR_CATALOG) + ".",
            {"symbol": {"type": "string"},
             "indicators": {"type": "array", "items": {"type": "string"}},
             "lookback_days": {"type": "integer", "minimum": 5, "maximum": 120}},
            ["symbol", "indicators"],
            lambda a: data.indicators(a["symbol"], a["indicators"], as_of, a.get("lookback_days", 30)),
        ),
        _spec(
            "get_verified_snapshot",
            "The verified price facts (last close, range, change, moving averages, RSI, ATR) "
            "a report may quote as exact numbers. Call it before writing.",
            {"symbol": {"type": "string"},
             "lookback_days": {"type": "integer", "minimum": 5, "maximum": 120}},
            ["symbol"],
            lambda a: data.snapshot(a["symbol"], as_of, a.get("lookback_days", 30)),
        ),
    ]


def news_tools(cfg: RunConfig) -> List[Spec]:
    as_of = cfg.trade_date
    week_ago = (dt.date.fromisoformat(as_of) - dt.timedelta(days=7)).isoformat()
    return [
        _spec(
            "get_company_news",
            f"Recent articles about a symbol, dated on or before {as_of}.",
            {"symbol": {"type": "string"}, "start_date": _DATE, "end_date": _DATE,
             "limit": {"type": "integer", "minimum": 1, "maximum": 50}},
            ["symbol"],
            lambda a: data.news(a["symbol"], a.get("start_date", week_ago),
                                a.get("end_date", as_of), as_of, a.get("limit", 20)),
        ),
        _spec(
            "get_global_news",
            "Market-wide and macro headlines for the last N days.",
            {"lookback_days": {"type": "integer", "minimum": 1, "maximum": 30},
             "limit": {"type": "integer", "minimum": 1, "maximum": 50}},
            [],
            lambda a: data.global_news(as_of, a.get("lookback_days", 7), a.get("limit", 10)),
        ),
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
    freq = {"type": "string", "enum": ["quarterly", "annual"]}
    return [
        _spec(
            "get_fundamentals",
            "Headline valuation, margin, growth and leverage ratios for a symbol.",
            {"symbol": {"type": "string"}},
            ["symbol"],
            lambda a: data.fundamentals(a["symbol"], as_of),
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


def host_tools(cfg: RunConfig) -> Dict[str, List[Spec]]:
    """Tool lists keyed by analyst key. The sentiment analyst has none: its
    material is pre-fetched into its persona by a prefetch script."""
    return {
        "market": market_tools(cfg),
        "news": news_tools(cfg),
        "fundamentals": fundamentals_tools(cfg),
        "sentiment": [],
    }
