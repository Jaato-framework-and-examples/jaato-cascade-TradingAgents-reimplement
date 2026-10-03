"""The append-only account of a run's sessions.

What this pins down is the difference between *unmeasured* and *zero*. A run
whose daemon could not be asked must not quietly report a bill of nothing —
that is how a cost report understates itself and nobody notices.
"""
import json

from ta_cascade import sessionlog
from ta_cascade.config import RunConfig


def _cfg(tmp_path):
    return RunConfig("NVDA", "2026-09-29", workspace=tmp_path, results_dir=tmp_path / "results")


def test_lines_accumulate_in_order_and_carry_the_cell(tmp_path):
    cfg = _cfg(tmp_path)
    assert sessionlog.read(cfg) == []
    sessionlog.write(cfg, "started", "s1", stage="market_analyst")
    sessionlog.write(cfg, "ended", "s1", stage="market_analyst", consumption={"totals": {"output_tokens": 7}})
    lines = sessionlog.read(cfg)
    assert [l["event"] for l in lines] == ["started", "ended"]
    assert all(l["ticker"] == "NVDA" and l["trade_date"] == "2026-09-29" for l in lines)
    assert lines[1]["consumption"]["totals"]["output_tokens"] == 7
    assert lines[0]["at"] <= lines[1]["at"]


def test_an_unmeasured_session_says_so_instead_of_reporting_zero(tmp_path):
    cfg = _cfg(tmp_path)
    sessionlog.write(cfg, "ended", "s1", stage="trader", consumption_error="TimeoutError: no answer")
    line = sessionlog.read(cfg)[0]
    assert "consumption" not in line
    assert line["consumption_error"].startswith("TimeoutError")


def test_it_lives_beside_the_report_tree(tmp_path):
    """Not under the driver's runtime state: a jaato-eval arm materialises its
    own workspace, and only what the run wrote into results travels with
    --keep-workspaces. The pilot's sixty arms were lost for want of this."""
    cfg = _cfg(tmp_path)
    assert sessionlog.path_for(cfg) == tmp_path / "results" / "NVDA" / "2026-09-29" / "sessions.jsonl"


def test_accounting_never_fails_a_run(tmp_path, monkeypatch):
    """A lost line of history is a better trade than a lost run."""
    cfg = _cfg(tmp_path)
    monkeypatch.setattr(sessionlog.Path, "mkdir", lambda *a, **k: (_ for _ in ()).throw(OSError("read-only")))
    sessionlog.write(cfg, "started", "s1", stage="trader")       # must not raise
    assert sessionlog.read(cfg) == []


def test_a_torn_last_line_does_not_lose_the_rest(tmp_path):
    """A driver killed mid-write leaves a partial line; the history before it
    is still the history."""
    cfg = _cfg(tmp_path)
    sessionlog.write(cfg, "started", "s1", stage="market_analyst")
    with sessionlog.path_for(cfg).open("a") as fh:
        fh.write('{"event": "ended", "sess')
    lines = sessionlog.read(cfg)
    assert len(lines) == 1 and lines[0]["event"] == "started"


def test_unpriced_and_unmeasured_are_different_states(tmp_path):
    """Three money states, not two, and a reader must keep them apart.

    A subscription provider (MiniMax here) reports tokens and no cost: that
    session is MEASURED and UNPRICED, and rendering it as $0.00 understates
    every total it joins. A session the daemon could not be asked about is
    UNMEASURED and reports nothing at all. Only the first state carries money.
    """
    cfg = _cfg(tmp_path)
    sessionlog.write(cfg, "ended", "priced", stage="trader",
                     consumption={"totals": {"output_tokens": 9, "cost_usd": 0.0123}})
    sessionlog.write(cfg, "ended", "unpriced", stage="trader",
                     consumption={"totals": {"output_tokens": 9, "cost_usd": None}})
    sessionlog.write(cfg, "ended", "unmeasured", stage="trader",
                     consumption_error="TimeoutError: no answer")
    by_id = {l["session_id"]: l for l in sessionlog.read(cfg)}

    priced = by_id["priced"]["consumption"]["totals"]
    assert priced["cost_usd"] == 0.0123

    unpriced = by_id["unpriced"]["consumption"]["totals"]
    assert unpriced["cost_usd"] is None          # NOT 0.0 — the provider does not price
    assert unpriced["output_tokens"] == 9        # effort is still known

    unmeasured = by_id["unmeasured"]
    assert "consumption" not in unmeasured       # nothing is known, not even effort
    assert unmeasured["consumption_error"]
