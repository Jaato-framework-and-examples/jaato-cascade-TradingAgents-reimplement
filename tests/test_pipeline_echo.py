"""End-to-end: the whole pipeline over a real jaato daemon on the ``echo`` set.

Zero cost, no credentials, no network: every stage is a deterministic test
double that either calls ``signal_completion`` with a canned payload or
answers with canned prose.  What this exercises is everything the driver
owns — session opening, host-tool registration, prompt composition, the two
debate loops, journaling and resume, the decision log — plus the daemon's
own profile contract (schemas, completion gates, spawn-param validation).

The daemon is started on a private socket with a private pid file and
stopped afterwards.  Skipped when ``server`` is not importable (the SDK is
installed without the daemon).
"""
from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

from ta_cascade import data, pipeline
from ta_cascade.config import RunConfig
from ta_cascade.memory import DecisionLog

REPO = Path(__file__).resolve().parents[1]
server = pytest.importorskip("server", reason="jaato-server (the daemon) is not installed")

pytestmark = pytest.mark.daemon


def _short_tmp() -> Path:
    """A directory whose socket path stays under the Unix limit (~104 chars)."""
    for base in (os.environ.get("TMPDIR"), tempfile.gettempdir(), "/tmp"):
        if base and len(base) < 60:
            return Path(tempfile.mkdtemp(prefix="tac-", dir=base))
    return Path(tempfile.mkdtemp(prefix="tac-"))


@pytest.fixture(scope="module")
def workspace():
    ws = _short_tmp()
    shutil.copytree(REPO / ".jaato", ws / ".jaato",
                    ignore=shutil.ignore_patterns("logs", "journal", "*.jsonl"))
    (ws / ".env").write_text("JAATO_PROFILE_SET=echo\n")
    sock, pid = ws / "d.sock", ws / "d.pid"
    subprocess.run([sys.executable, "-m", "server", "--ipc-socket", str(sock),
                    "--pid-file", str(pid), "--daemon"], check=True, timeout=180)
    # ``--daemon`` returns as soon as the process is forked; the socket appears
    # once plugin discovery finishes (a cold start), so wait for it here rather
    # than relying on the client's autostart wait.
    deadline = time.monotonic() + 180
    while not sock.exists():
        if time.monotonic() > deadline:
            raise RuntimeError(f"daemon did not bind {sock} within 180s")
        time.sleep(0.5)
    try:
        yield ws, sock
    finally:
        subprocess.run([sys.executable, "-m", "server", "--stop", "--pid-file", str(pid),
                        "--ipc-socket", str(sock)], timeout=60)
        shutil.rmtree(ws, ignore_errors=True)


@pytest.fixture
def cfg(workspace, monkeypatch):
    ws, sock = workspace
    # No network in the driver either: identity and outcomes are stubbed.
    monkeypatch.setattr(data, "instrument_context", lambda s, a: f"{s} — Echo Corp; asset type: {a}")
    monkeypatch.setattr(data, "return_after", lambda symbol, d, n: (0.05 if symbol == "ECHO" else 0.01, "2026-01-23"))
    return RunConfig("ECHO", "2026-01-15", analysts=["market", "sentiment"], workspace=ws,
                     socket=str(sock), journal_dir=ws / "journal", results_dir=ws / "results",
                     decision_log=ws / "decisions.jsonl", max_debate_rounds=1, max_risk_rounds=1,
                     connect_timeout=180.0, auto_start=False)


def test_full_run_then_resolution(cfg):
    state = asyncio.run(pipeline.run(cfg))

    assert set(state.reports) == {"market", "sentiment"}
    assert state.reports["market"]["stance"] == "bullish"
    assert [t.speaker for t in state.investment_debate] == ["Bull", "Bear"]
    assert state.investment_debate[0].text.startswith("Bull:")
    assert state.research_plan["recommendation"] == "Overweight"
    assert state.trader_proposal["action"] == "Buy"
    assert [t.speaker for t in state.risk_debate] == ["Aggressive", "Conservative", "Neutral"]
    assert state.portfolio_decision["rating"] == "Overweight"
    assert (cfg.results_dir / "ECHO" / "2026-01-15" / "report.md").exists()
    assert not (cfg.journal_dir / f"{cfg.run_key}.json").exists()      # cleared on success

    log = DecisionLog(cfg.decision_log)
    assert [d.status for d in log.all()] == ["pending"]

    # A later run on the same ticker scores the pending decision through the
    # reflector stage and hands the lesson to the portfolio manager.
    cfg2 = RunConfig("ECHO", "2026-02-15", analysts=["market"], workspace=cfg.workspace,
                     socket=cfg.socket, journal_dir=cfg.journal_dir, results_dir=cfg.results_dir,
                     decision_log=cfg.decision_log, connect_timeout=180.0, auto_start=False)
    state2 = asyncio.run(pipeline.run(cfg2))
    resolved = [d for d in log.all() if d.status == "resolved"]
    assert len(resolved) == 1 and resolved[0].alpha == pytest.approx(0.04)
    assert "keep sizing modest" in resolved[0].lesson
    assert "Overweight" in state2.past_context


def test_resume_skips_journaled_stages(cfg, monkeypatch):
    """Pre-seed a journal with the analysts done; the run must not reopen them."""
    from ta_cascade.journal import Journal
    from ta_cascade.state import RunState

    cfg.journal_dir = cfg.workspace / "journal-resume"
    seeded = RunState(ticker="ECHO", trade_date="2026-01-15", asset_type="stock",
                      instrument_context="seeded")
    seeded.reports["market"] = {"report": "seeded market", "stance": "bearish", "confidence": "high",
                                "tools_used": [], "errors": [], "warnings": []}
    seeded.reports["sentiment"] = {"report": "seeded sentiment", "stance": "neutral", "confidence": "low",
                                   "tools_used": [], "errors": [], "warnings": []}
    Journal(cfg.journal_dir, cfg.run_key).save(seeded)

    opened = []
    real = pipeline.open_stage

    def spy(cfg_, **kw):
        opened.append(kw["profile"])
        return real(cfg_, **kw)

    monkeypatch.setattr(pipeline, "open_stage", spy)
    state = asyncio.run(pipeline.run(cfg, record_decision=False, resolve_pending=False))
    assert state.reports["market"]["stance"] == "bearish"          # journaled, not re-run
    assert "market_analyst" not in opened and "sentiment_analyst" not in opened
    assert opened[:2] == ["bull_researcher", "bear_researcher"]
    assert state.portfolio_decision["rating"] == "Overweight"
