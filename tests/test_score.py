import json

import pytest

from ta_cascade import data, score
from ta_cascade.contract import EX_TEMPFAIL


@pytest.mark.parametrize("rating, alpha, right", [
    ("Buy", 0.02, True), ("Overweight", 0.0001, True), ("Buy", -0.01, False), ("Overweight", 0.0, False),
    ("Sell", -0.03, True), ("Underweight", 0.03, False),
    ("Hold", 0.005, True), ("Hold", -0.01, True), ("Hold", 0.011, False),
])
def test_grade_is_the_documented_rule(rating, alpha, right):
    assert score.grade(rating, alpha, hold_band=0.01) is right


def _state(results, ticker, date, rating):
    d = results / ticker / date
    d.mkdir(parents=True)
    (d / "state.json").write_text(json.dumps({"ticker": ticker, "trade_date": date,
                                              "portfolio_decision": {"rating": rating}}))


def _returns(monkeypatch, table):
    """``table``: symbol -> (return, resolved_on) or None."""
    monkeypatch.setattr(data, "return_after", lambda symbol, date, n: table[symbol])


def test_a_right_call_passes_and_prints_the_facts(tmp_path, monkeypatch, capsys):
    _state(tmp_path, "NVDA", "2026-08-28", "Overweight")
    _returns(monkeypatch, {"NVDA": (0.05, "2026-09-05"), "SPY": (0.01, "2026-09-05")})
    rc = score.score("NVDA", "2026-08-28", results_dir=tmp_path, holding_days=5,
                     benchmark="SPY", hold_band=0.01)
    facts = json.loads(capsys.readouterr().out)
    assert rc == 0 and facts["verdict"] == "PASS"
    assert facts["alpha"] == pytest.approx(0.04) and facts["resolved_on"] == "2026-09-05"


def test_a_wrong_call_fails(tmp_path, monkeypatch):
    _state(tmp_path, "NVDA", "2026-08-28", "Sell")
    _returns(monkeypatch, {"NVDA": (0.05, "2026-09-05"), "SPY": (0.01, "2026-09-05")})
    assert score.score("NVDA", "2026-08-28", results_dir=tmp_path, holding_days=5,
                       benchmark="SPY", hold_band=0.01) == 1


def test_ungradeable_cells_are_blocked_not_wrong(tmp_path, monkeypatch, capsys):
    _returns(monkeypatch, {"NVDA": None, "SPY": (0.01, "2026-09-05")})
    kw = dict(results_dir=tmp_path, holding_days=5, benchmark="SPY", hold_band=0.01)
    assert score.score("NVDA", "2026-08-28", **kw) == EX_TEMPFAIL         # no state at all
    _state(tmp_path, "NVDA", "2026-08-28", "Overweight")
    assert score.score("NVDA", "2026-08-28", **kw) == EX_TEMPFAIL         # not enough bars yet
    assert "not enough bars" in capsys.readouterr().out
    _state(tmp_path, "AMD", "2026-08-28", "REVIEW")
    _returns(monkeypatch, {"AMD": (0.05, "x"), "SPY": (0.01, "x")})
    assert score.score("AMD", "2026-08-28", **kw) == EX_TEMPFAIL          # outside the vocabulary


def test_main_reads_the_contract_params(tmp_path, monkeypatch):
    _state(tmp_path, "NVDA", "2026-08-28", "Buy")
    _returns(monkeypatch, {"NVDA": (0.05, "x"), "SPY": (0.01, "x")})
    monkeypatch.setenv("JAATO_EVAL_PARAM_TICKER", "nvda")
    monkeypatch.setenv("JAATO_EVAL_PARAM_TRADE_DATE", "2026-08-28")
    assert score.main(["--results-dir", str(tmp_path)]) == 0
    monkeypatch.delenv("JAATO_EVAL_PARAM_TICKER")
    assert score.main(["--results-dir", str(tmp_path)]) == EX_TEMPFAIL    # nothing names the cell
