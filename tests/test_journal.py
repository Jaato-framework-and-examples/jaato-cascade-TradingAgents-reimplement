from ta_cascade.journal import Journal
from ta_cascade.state import DebateTurn, RunState


def _state():
    s = RunState(ticker="T", trade_date="2026-01-15", asset_type="stock", instrument_context="T — test")
    s.reports["market"] = {"report": "r", "stance": "bullish"}
    s.investment_debate.append(DebateTurn("Bull", "hello"))
    return s


def test_roundtrip_and_clear(tmp_path):
    j = Journal(tmp_path / "journal", "abc")
    assert j.load() is None
    j.save(_state())
    back = j.load()
    assert back.reports["market"]["stance"] == "bullish"
    assert back.investment_debate[0] == DebateTurn("Bull", "hello")
    j.clear()
    assert j.load() is None and not j.path.exists()


def test_disabled_journal_is_a_noop():
    j = Journal(None, "abc")
    j.save(_state()); j.clear()
    assert j.load() is None and j.path is None
