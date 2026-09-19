import json

import pandas as pd
import pytest

from ta_cascade import data, score
from ta_cascade.contract import EX_TEMPFAIL


@pytest.mark.parametrize("rating, alpha, band, right", [
    ("Buy", 0.02, 0.01, True), ("Overweight", 0.0001, 0.01, True), ("Buy", -0.01, 0.01, False),
    ("Sell", -0.03, 0.01, True), ("Underweight", 0.03, 0.01, False),
    ("Hold", 0.005, 0.01, True), ("Hold", 0.011, 0.01, False), ("Hold", 0.05, 0.08, True),   # a wider band
])
def test_grade_is_the_documented_rule(rating, alpha, band, right):
    assert score.grade(rating, alpha, band) is right


def _path(closes, lows=None, highs=None):
    idx = pd.bdate_range("2026-08-31", periods=len(closes))
    return pd.DataFrame({"Close": closes, "Low": lows or [c - 1 for c in closes],
                         "High": highs or [c + 1 for c in closes]}, index=idx)


def test_realised_honours_a_stop_on_the_path():
    path = _path([102, 97, 104, 106, 108], lows=[101, 94, 103, 105, 107])
    assert score.realised(path, 100.0, +1, stop=None)["return"] == pytest.approx(0.08)
    hit = score.realised(path, 100.0, +1, stop=95.0)
    assert hit["stopped_out"] and hit["stopped_on"] == "2026-09-01" and hit["return"] == pytest.approx(-0.05)
    assert score.realised(path, 100.0, 0, stop=95.0)["stopped_out"] is False        # a flat call has no stop
    short = score.realised(_path([98, 96, 103, 90, 88], highs=[99, 97, 105, 91, 89]), 100.0, -1, stop=104.0)
    assert short["stopped_out"] and short["return"] == pytest.approx(0.04)


def _state(results, ticker, date, rating, stop=None):
    d = results / ticker / date
    d.mkdir(parents=True, exist_ok=True)
    (d / "state.json").write_text(json.dumps({"ticker": ticker, "trade_date": date,
                                              "trader_proposal": {"action": "Buy", "stop_loss": stop},
                                              "portfolio_decision": {"rating": rating}}))


def _market(monkeypatch, *, returns, paths, bands=None):
    """Stub the data layer: symbol -> (return, resolved_on) | None, symbol -> path frame, symbol -> band."""
    monkeypatch.setattr(data, "return_after", lambda symbol, date, n: returns[symbol])
    monkeypatch.setattr(data, "path_after", lambda symbol, date, n: paths.get(symbol))
    monkeypatch.setattr(data, "hold_band", lambda symbol, date, n: (bands or {}).get(symbol, 0.05))


def _run(tmp_path, ticker, **kw):
    kw = {"results_dir": tmp_path, "holding_days": 5, "benchmark": "SPY", "hold_band": None, **kw}
    return score.score(ticker, "2026-08-28", **kw)


def test_a_right_call_passes_and_prints_the_facts(tmp_path, monkeypatch, capsys):
    _state(tmp_path, "NVDA", "2026-08-28", "Overweight")
    _market(monkeypatch, returns={"NVDA": (0.05, "2026-09-05"), "SPY": (0.01, "2026-09-05")},
            paths={"NVDA": _path([101, 102, 103, 104, 105])})
    rc = _run(tmp_path, "NVDA")
    facts = json.loads(capsys.readouterr().out)
    assert rc == 0 and facts["verdict"] == "PASS" and facts["hold_band_rule"] == "atr"
    assert facts["alpha"] == pytest.approx(0.04) and facts["stopped_out"] is False


def test_the_hold_band_is_the_instruments_volatility_unless_fixed(tmp_path, monkeypatch, capsys):
    _state(tmp_path, "NVDA", "2026-08-28", "Hold")
    _market(monkeypatch, returns={"NVDA": (0.05, "x"), "SPY": (0.01, "x")},
            paths={"NVDA": _path([101, 102, 103, 104, 105])}, bands={"NVDA": 0.07})
    assert _run(tmp_path, "NVDA") == 0                       # |alpha| 4% within a 7% band: right
    assert _run(tmp_path, "NVDA", hold_band=0.01) == 1       # the old fixed rule: wrong
    assert json.loads(capsys.readouterr().out.splitlines()[-1])["hold_band_rule"] == "fixed"


def test_a_cell_whose_ticker_is_the_benchmark_scores_its_raw_return(tmp_path, monkeypatch, capsys):
    _state(tmp_path, "SPY", "2026-08-28", "Overweight")
    _market(monkeypatch, returns={"SPY": (0.02, "x")}, paths={"SPY": _path([101, 101, 102, 102, 102])})
    assert _run(tmp_path, "SPY") == 0
    facts = json.loads(capsys.readouterr().out)
    assert facts["benchmark"] is None and facts["alpha"] == pytest.approx(0.02)


def test_a_stopped_out_long_is_scored_at_the_stop(tmp_path, monkeypatch, capsys):
    _state(tmp_path, "NVDA", "2026-08-28", "Buy", stop=95.0)
    _market(monkeypatch, returns={"NVDA": (0.08, "x"), "SPY": (0.0, "x")},
            paths={"NVDA": _path([102, 97, 104, 106, 108], lows=[101, 94, 103, 105, 107])})
    assert _run(tmp_path, "NVDA") == 1                       # the week closed +8%, but the stop took it out at -5%
    facts = json.loads(capsys.readouterr().out)
    assert facts["stopped_out"] and facts["stopped_on"] == "2026-09-01" and facts["alpha"] == pytest.approx(-0.05)


def test_ungradeable_cells_are_blocked_not_wrong(tmp_path, monkeypatch, capsys):
    _market(monkeypatch, returns={"NVDA": None, "SPY": (0.01, "x")}, paths={})
    assert _run(tmp_path, "NVDA") == EX_TEMPFAIL                                  # no state at all
    _state(tmp_path, "NVDA", "2026-08-28", "Overweight")
    assert _run(tmp_path, "NVDA") == EX_TEMPFAIL                                  # not enough bars yet
    assert "not enough bars" in capsys.readouterr().out
    _state(tmp_path, "AMD", "2026-08-28", "REVIEW")
    assert _run(tmp_path, "AMD") == EX_TEMPFAIL                                   # outside the vocabulary


def test_main_reads_the_contract_params(tmp_path, monkeypatch):
    _state(tmp_path, "NVDA", "2026-08-28", "Buy")
    _market(monkeypatch, returns={"NVDA": (0.05, "x"), "SPY": (0.01, "x")}, paths={"NVDA": _path([1, 2, 3, 4, 5])})
    monkeypatch.setenv("JAATO_EVAL_PARAM_TICKER", "nvda")
    monkeypatch.setenv("JAATO_EVAL_PARAM_TRADE_DATE", "2026-08-28")
    assert score.main(["--results-dir", str(tmp_path)]) == 0
    monkeypatch.delenv("JAATO_EVAL_PARAM_TICKER")
    assert score.main(["--results-dir", str(tmp_path)]) == EX_TEMPFAIL            # nothing names the cell
