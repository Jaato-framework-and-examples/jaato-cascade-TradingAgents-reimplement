"""Run configuration.

A ``RunConfig`` is everything a single analysis run needs that is not the
model's business: the instrument, the date, which analysts to run, how many
debate rounds, and where the workspace, socket, journal and decision log live.
Model, provider and per-stage ceilings are NOT here — they belong to the
profile set selected by ``JAATO_PROFILE_SET`` in the workspace ``.env``.
"""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

ANALYST_KEYS = ("market", "sentiment", "news", "fundamentals")
"""The four analysts, in the order they run when all are selected."""

RATINGS = ("Buy", "Overweight", "Hold", "Underweight", "Sell")
"""The five-tier rating vocabulary shared by the research manager and the
portfolio manager (mirrored in the completion schemas)."""


@dataclass
class RunConfig:
    """One analysis run.

    Attributes:
        ticker: the instrument symbol as the data layer expects it (``NVDA``,
            ``BTC-USD``).
        trade_date: ISO date the analysis is "as of".  Every data tool is
            bounded by it, so a backtest never sees the future.
        asset_type: ``stock`` or ``crypto``; only changes prompt wording and
            which fundamentals make sense.
        analysts: subset of :data:`ANALYST_KEYS`, in run order.
        max_debate_rounds: bull/bear rounds; each round is one turn per side.
        max_risk_rounds: risk rounds; each round is one turn per debater.
        workspace: directory holding ``.jaato/`` (framework assets) and
            ``.env``; the driver's own state goes under ``.ta_cascade/``.
        env_file: the workspace ``.env`` (the SESSION env — ``JAATO_PROFILE_SET``
            and the provider credential are read from it daemon-side).
        socket: the daemon's IPC socket.
        auto_start: start a daemon on ``socket`` when none answers (the SDK's
            autostart); off when something else owns the daemon's lifecycle.
        journal_dir: where per-run resume journals go; ``None`` disables.
            Defaults under ``<workspace>/.ta_cascade/``, never under
            ``.jaato/``: that directory is the framework's ``config_root``
            and holds framework assets only (profiles, personas, schemas,
            scripts) plus the framework's own runtime state (``logs/``,
            ``sessions/``).  A driver product written there would be a
            tenant writing into the framework's tree.
        results_dir: where the report tree is written.
        decision_log: the decision log path (see :mod:`ta_cascade.memory`).
        holding_days: bars after the trade date used to score a decision.
        benchmark: the symbol a decision's return is measured against.
    """

    ticker: str
    trade_date: str
    asset_type: str = "stock"
    analysts: List[str] = field(default_factory=lambda: list(ANALYST_KEYS))
    max_debate_rounds: int = 1
    max_risk_rounds: int = 1
    workspace: Path = field(default_factory=lambda: Path.cwd())
    env_file: Optional[Path] = None
    socket: str = "/tmp/jaato.sock"
    journal_dir: Optional[Path] = None
    results_dir: Optional[Path] = None
    decision_log: Optional[Path] = None
    holding_days: int = 5
    benchmark: str = "SPY"
    connect_timeout: float = 120.0
    auto_start: bool = True

    def __post_init__(self) -> None:
        self.ticker = self.ticker.strip().upper()
        unknown = [a for a in self.analysts if a not in ANALYST_KEYS]
        if unknown:
            raise ValueError(f"unknown analyst(s): {unknown}; choose from {ANALYST_KEYS}")
        if not self.analysts:
            raise ValueError("at least one analyst must be selected")
        if self.asset_type not in ("stock", "crypto"):
            raise ValueError("asset_type must be 'stock' or 'crypto'")
        self.workspace = Path(self.workspace).resolve()
        self.env_file = Path(self.env_file or self.workspace / ".env").resolve()
        self.journal_dir = Path(self.journal_dir or self.workspace / ".ta_cascade" / "journal")
        self.results_dir = Path(self.results_dir or self.workspace / "results")
        self.decision_log = Path(
            self.decision_log
            or os.environ.get("TA_CASCADE_DECISION_LOG")
            or Path.home() / ".ta_cascade" / "decisions.jsonl"
        )

    @property
    def config_root(self) -> Path:
        """The ``.jaato`` directory: profiles, agents, schemas, scripts.

        Framework territory.  The daemon resolves profiles and personas from
        here and writes its own ``logs/`` and ``sessions/`` into it; nothing
        this driver produces belongs here (see :attr:`journal_dir`).
        """
        return self.workspace / ".jaato"

    @property
    def run_signature(self) -> str:
        """What makes two runs the *same* run for resume purposes.

        Analyst selection, debate depths and asset type change the shape of
        the pipeline, so a journal written under one signature must not be
        replayed under another.
        """
        return (
            f"analysts={','.join(self.analysts)}|debate={self.max_debate_rounds}"
            f"|risk={self.max_risk_rounds}|asset={self.asset_type}"
        )

    @property
    def run_key(self) -> str:
        """Stable id of this run: ticker, date and signature, hashed."""
        raw = f"{self.ticker}:{self.trade_date}:{self.run_signature}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]
