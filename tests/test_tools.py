from ta_cascade import data
from ta_cascade.config import RunConfig
from ta_cascade.tools import host_tools


def test_specs_are_well_formed(tmp_path):
    cfg = RunConfig("NVDA", "2026-01-15", workspace=tmp_path)
    tools = host_tools(cfg)
    assert set(tools) == {"market", "news", "fundamentals", "sentiment"} and tools["sentiment"] == []
    for specs in tools.values():
        for spec in specs:
            assert spec["auto_approve"] is True and callable(spec["handler"])
            assert spec["parameters"]["type"] == "object"
            assert set(spec["parameters"]["required"]) <= set(spec["parameters"]["properties"])


def test_handlers_clamp_to_trade_date(tmp_path, monkeypatch):
    seen = {}

    def fake_ohlcv(symbol, start, end, as_of):
        seen.update(symbol=symbol, start=start, end=end, as_of=as_of)
        return "ok"

    monkeypatch.setattr(data, "ohlcv", fake_ohlcv)
    cfg = RunConfig("NVDA", "2026-01-15", workspace=tmp_path)
    tool = next(t for t in host_tools(cfg)["market"] if t["name"] == "get_price_history")
    assert tool["handler"]({"symbol": "NVDA", "start_date": "2025-12-01", "end_date": "2026-03-01"}) == "ok"
    assert seen["as_of"] == "2026-01-15"
