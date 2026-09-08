"""The state the pipeline nodes pass along.

Unlike a graph framework's shared state, nothing here is visible to a model
unless the driver puts it in a prompt.  ``RunState`` is a plain record the
driver fills node by node; :mod:`ta_cascade.journal` persists it.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class DebateTurn:
    """One spoken turn in a debate: who spoke and what they said."""

    speaker: str
    text: str


@dataclass
class RunState:
    """Everything produced by a run, in production order.

    ``reports`` is keyed by analyst key (``market``, ``sentiment``, ``news``,
    ``fundamentals``) and holds each analyst's typed payload.  The two debates
    are lists of turns; the three judges' payloads are stored whole.
    """

    ticker: str
    trade_date: str
    asset_type: str
    instrument_context: str
    past_context: str = ""
    reports: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    investment_debate: List[DebateTurn] = field(default_factory=list)
    research_plan: Optional[Dict[str, Any]] = None
    trader_proposal: Optional[Dict[str, Any]] = None
    risk_debate: List[DebateTurn] = field(default_factory=list)
    portfolio_decision: Optional[Dict[str, Any]] = None

    # ---- composition helpers the pipeline uses to build prompts ----

    def report_text(self, key: str) -> str:
        payload = self.reports.get(key) or {}
        return str(payload.get("report", "")).strip()

    def reports_block(self) -> str:
        """All analyst reports as one labelled block, in run order."""
        labels = {
            "market": "Market (technical) report",
            "sentiment": "Sentiment report",
            "news": "News and macro report",
            "fundamentals": "Fundamentals report",
        }
        parts = []
        for key, label in labels.items():
            text = self.report_text(key)
            if text:
                parts.append(f"## {label}\n\n{text}")
        return "\n\n".join(parts) or "(no analyst reports were produced)"

    @staticmethod
    def transcript(turns: List[DebateTurn]) -> str:
        return "\n\n".join(f"{t.speaker}: {t.text}" for t in turns) or "(no turns yet)"

    @staticmethod
    def last_by(turns: List[DebateTurn], speaker: str) -> Optional[str]:
        for t in reversed(turns):
            if t.speaker == speaker:
                return t.text
        return None

    # ---- persistence ----

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "RunState":
        d = dict(d)
        d["investment_debate"] = [DebateTurn(**t) for t in d.get("investment_debate", [])]
        d["risk_debate"] = [DebateTurn(**t) for t in d.get("risk_debate", [])]
        return cls(**d)
