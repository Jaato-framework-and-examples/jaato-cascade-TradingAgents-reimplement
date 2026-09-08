"""Write the report tree for a finished run.

Layout under ``<results_dir>/<ticker>/<trade_date>/``::

    1_analysts/<key>.md        one file per analyst that ran
    2_research/debate.md       the bull/bear transcript
    2_research/plan.md         the research manager's plan
    3_trading/proposal.md      the trader's proposal
    4_risk/debate.md           the risk transcript
    5_portfolio/decision.md    the portfolio manager's decision
    report.md                  everything, in order
    state.json                 the raw run state

Sections are written only when their content exists, so a run with two
analysts produces two analyst files and no empty placeholders.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import List, Tuple

from .state import RunState

_ANALYST_TITLES = {
    "market": "Market analysis", "sentiment": "Sentiment analysis",
    "news": "News and macro analysis", "fundamentals": "Fundamentals analysis",
}


def _payload_md(payload: dict, skip=("errors", "warnings")) -> str:
    lines = []
    for k, v in payload.items():
        if k in skip or v in (None, "", []):
            continue
        if isinstance(v, str) and "\n" in v:
            lines.append(f"**{k.replace('_', ' ').title()}**\n\n{v}\n")
        else:
            lines.append(f"**{k.replace('_', ' ').title()}**: {v}\n")
    warn = payload.get("warnings") or []
    if warn:
        lines.append("_Warnings_: " + "; ".join(map(str, warn)) + "\n")
    return "\n".join(lines)


def sections(state: RunState) -> List[Tuple[str, str, str]]:
    """``(relative_path, title, markdown)`` for every section with content."""
    out: List[Tuple[str, str, str]] = []
    for key, payload in state.reports.items():
        out.append((f"1_analysts/{key}.md", _ANALYST_TITLES.get(key, key), _payload_md(payload)))
    if state.investment_debate:
        out.append(("2_research/debate.md", "Investment debate", RunState.transcript(state.investment_debate)))
    if state.research_plan:
        out.append(("2_research/plan.md", "Research manager's plan", _payload_md(state.research_plan)))
    if state.trader_proposal:
        out.append(("3_trading/proposal.md", "Trader's proposal", _payload_md(state.trader_proposal)))
    if state.risk_debate:
        out.append(("4_risk/debate.md", "Risk debate", RunState.transcript(state.risk_debate)))
    if state.portfolio_decision:
        out.append(("5_portfolio/decision.md", "Portfolio decision", _payload_md(state.portfolio_decision)))
    return out


def write_report(state: RunState, results_dir: Path) -> Path:
    root = Path(results_dir) / state.ticker / state.trade_date
    root.mkdir(parents=True, exist_ok=True)
    full = [f"# Analysis report: {state.ticker} as of {state.trade_date}\n",
            f"_{state.instrument_context}_\n"]
    for rel, title, body in sections(state):
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# {title}\n\n{body}\n", encoding="utf-8")
        full.append(f"## {title}\n\n{body}\n")
    (root / "report.md").write_text("\n".join(full), encoding="utf-8")
    (root / "state.json").write_text(json.dumps(state.to_dict(), indent=1), encoding="utf-8")
    return root
