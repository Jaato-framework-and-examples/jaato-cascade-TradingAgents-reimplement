"""The stop-placement conformance check, and the evidence it reads.

The check is the deterministic half of the reference `stop-placement`: it
attests that a proposal conforms to the rule, never that the rule is sound.
Every case here is a cell written to disk, because that is the only thing the
check is allowed to read — no network, no prose.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

from ta_cascade import data
from ta_cascade.state import RunState

CHECK = Path(__file__).resolve().parents[1] / "knowledge" / "checks" / "check-stop-placement" / "check.py"


def _cell(tmp_path, *, action, entry, stop, atr=6.0, ticker="NVDA", date="2026-09-29"):
    d = tmp_path / ticker / date
    d.mkdir(parents=True, exist_ok=True)
    state = {"ticker": ticker, "trade_date": date,
             "trader_proposal": {"action": action, "entry_price": entry, "stop_loss": stop}}
    if atr is not None:
        state["evidence"] = {"snapshots": [{"symbol": ticker, "as_of": date, "atr_14": atr}]}
    (d / "state.json").write_text(json.dumps(state))
    return d


def _run(cell):
    out = subprocess.run([sys.executable, str(CHECK), str(cell)],
                         capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_a_stop_a_full_atr_away_on_the_invalidating_side_conforms(tmp_path):
    r = _run(_cell(tmp_path, action="Sell", entry=228.87, stop=238.0, atr=6.25))
    assert r["status"] == "compliant" and r["violations"] == []


def test_a_stop_inside_one_atr_is_refused(tmp_path):
    r = _run(_cell(tmp_path, action="Sell", entry=228.87, stop=234.76, atr=6.2482))
    assert r["status"] == "non_compliant"
    assert any("rule 3" in v and "inside one ATR" in v for v in r["violations"])


def test_a_stop_on_the_wrong_side_is_refused(tmp_path):
    r = _run(_cell(tmp_path, action="Buy", entry=230.0, stop=240.0, atr=7.0))
    assert r["status"] == "non_compliant"
    assert any("rule 2" in v for v in r["violations"])


def test_a_hold_carrying_a_stop_is_refused(tmp_path):
    """The live defect this rule was written from: results/NVDA/2026-09-29."""
    r = _run(_cell(tmp_path, action="Hold", entry=None, stop=217.0))
    assert r["status"] == "non_compliant"
    assert any("rule 1" in v for v in r["violations"])


def test_a_proposal_with_neither_entry_nor_stop_is_not_applicable(tmp_path):
    r = _run(_cell(tmp_path, action="Hold", entry=None, stop=None))
    assert r["status"] == "not_applicable"


def test_a_run_without_captured_evidence_cannot_be_verified(tmp_path):
    """It refuses rather than recomputing: a check that reaches for live data
    answers differently on different days and stops being a check."""
    r = _run(_cell(tmp_path, action="Sell", entry=228.87, stop=234.76, atr=None))
    assert r["status"] == "cannot_verify"
    assert any("rule 3" in v and "captured no verified snapshot" in v for v in r["violations"])


def test_a_missing_cell_cannot_be_verified(tmp_path):
    r = _run(tmp_path / "NOPE" / "2026-09-29")
    assert r["status"] == "cannot_verify"


@pytest.mark.parametrize("bad", ["REVIEW", None])
def test_an_action_outside_the_vocabulary_cannot_be_verified(tmp_path, bad):
    r = _run(_cell(tmp_path, action=bad, entry=100.0, stop=90.0))
    assert r["status"] == "cannot_verify"


def test_record_snapshot_keeps_the_numbers_in_call_order():
    st = RunState(ticker="NVDA", trade_date="2026-09-29", asset_type="stock", instrument_context="NVIDIA")
    assert st.evidence == {}
    st.record_snapshot({"symbol": "NVDA", "atr_14": 6.0})
    st.record_snapshot({"symbol": "NVDA", "atr_14": 6.1})
    assert [s["atr_14"] for s in st.evidence["snapshots"]] == [6.0, 6.1]
    assert RunState.from_dict(st.to_dict()).evidence == st.evidence


def test_snapshot_records_on_success_and_not_on_failure(monkeypatch):
    """The recorder sees the facts the model sees, and a failed fetch records
    nothing while still reaching the model as a sentence."""
    seen = []
    facts = {"symbol": "NVDA", "atr_14": 6.0}
    monkeypatch.setattr(data, "render_snapshot", lambda f: "VERIFIED " + json.dumps(f))

    monkeypatch.setattr(data, "compute_indicators", lambda df: (_ for _ in ()).throw(RuntimeError("no bars")))
    text = data.snapshot("NVDA", "2026-09-29", 30, max_stale_days=7, record=seen.append)
    assert text.startswith("DATA_UNAVAILABLE") and seen == []
