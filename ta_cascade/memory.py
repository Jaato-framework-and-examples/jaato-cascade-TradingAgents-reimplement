"""The decision log: what was decided, how it turned out, what was learned.

An append-only JSONL file of decisions.  A decision is recorded ``pending``
at the end of a run; on a later run for the same ticker, once enough bars
exist after the trade date, it is scored (raw return and alpha against the
benchmark), a reflector agent writes a short lesson, and the entry becomes
``resolved``.  The portfolio manager's persona receives
:meth:`DecisionLog.past_context`: the most recent resolved same-ticker
decisions in full plus a few cross-ticker lessons, filtered to entries
resolved on or before the analysis date so a backtest cannot learn from its
own future.

No embeddings, no similarity search — recency is the selection rule.
"""
from __future__ import annotations

import datetime as dt
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import List, Optional


@dataclass
class Decision:
    ticker: str
    trade_date: str
    rating: str
    summary: str
    status: str = "pending"          # pending | resolved
    recorded_at: str = field(default_factory=lambda: dt.datetime.now(dt.timezone.utc).isoformat())
    holding_days: Optional[int] = None
    raw_return: Optional[float] = None
    alpha: Optional[float] = None
    benchmark: Optional[str] = None
    resolved_on: Optional[str] = None
    lesson: Optional[str] = None
    call_was_correct: Optional[bool] = None

    @property
    def key(self) -> tuple:
        return (self.ticker, self.trade_date)


class DecisionLog:
    """Read/write the decision log at ``path`` (created on first write)."""

    def __init__(self, path: Path):
        self.path = Path(path)

    # ---- storage ----

    def all(self) -> List[Decision]:
        if not self.path.exists():
            return []
        out = []
        with self.path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    out.append(Decision(**json.loads(line)))
        return out

    def _write_all(self, entries: List[Decision]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".jsonl.tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            for e in entries:
                fh.write(json.dumps(asdict(e), sort_keys=True) + "\n")
        tmp.replace(self.path)

    # ---- lifecycle ----

    def record(self, ticker: str, trade_date: str, rating: str, summary: str,
               holding_days: int) -> Decision:
        """Append a pending decision; idempotent on (ticker, trade_date)."""
        entries = self.all()
        for e in entries:
            if e.key == (ticker, trade_date):
                return e
        d = Decision(ticker=ticker, trade_date=trade_date, rating=rating,
                     summary=summary, holding_days=holding_days)
        entries.append(d)
        self._write_all(entries)
        return d

    def pending(self, ticker: Optional[str] = None) -> List[Decision]:
        return [e for e in self.all()
                if e.status == "pending" and (ticker is None or e.ticker == ticker)]

    def resolve(self, ticker: str, trade_date: str, *, raw_return: float, alpha: float,
                benchmark: str, resolved_on: str, lesson: str,
                call_was_correct: Optional[bool]) -> Optional[Decision]:
        entries = self.all()
        for e in entries:
            if e.key == (ticker, trade_date) and e.status == "pending":
                e.status = "resolved"
                e.raw_return, e.alpha, e.benchmark = raw_return, alpha, benchmark
                e.resolved_on, e.lesson, e.call_was_correct = resolved_on, lesson, call_was_correct
                self._write_all(entries)
                return e
        return None

    # ---- what the portfolio manager reads ----

    def past_context(self, ticker: str, *, as_of: Optional[str] = None,
                     n_same: int = 5, n_cross: int = 3) -> str:
        resolved = [e for e in self.all() if e.status == "resolved"
                    and (as_of is None or (e.resolved_on or "") <= as_of)]
        same = [e for e in resolved if e.ticker == ticker][-n_same:]
        cross = [e for e in resolved if e.ticker != ticker][-n_cross:]
        if not same and not cross:
            return ""
        parts = []
        if same:
            parts.append(f"Previous decisions on {ticker} and how they turned out:")
            for e in reversed(same):
                parts.append(
                    f"- {e.trade_date}: rated {e.rating}; {e.holding_days}-day return "
                    f"{_pct(e.raw_return)}, alpha vs {e.benchmark} {_pct(e.alpha)}. "
                    f"Lesson: {e.lesson or '(none recorded)'}"
                )
        if cross:
            parts.append("Lessons from other instruments:")
            for e in reversed(cross):
                parts.append(f"- {e.ticker} {e.trade_date} ({e.rating}, alpha {_pct(e.alpha)}): {e.lesson or '(none recorded)'}")
        return "\n".join(parts)


def _pct(v: Optional[float]) -> str:
    return "n/a" if v is None else f"{v * 100:+.2f}%"
