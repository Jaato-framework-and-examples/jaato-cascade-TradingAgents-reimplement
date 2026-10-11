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

    def fake_ohlcv(symbol, start, end, as_of, *, max_stale_days):
        seen.update(symbol=symbol, start=start, end=end, as_of=as_of, max_stale_days=max_stale_days)
        return "ok"

    monkeypatch.setattr(data, "ohlcv", fake_ohlcv)
    cfg = RunConfig("NVDA", "2026-01-15", workspace=tmp_path)
    tool = next(t for t in host_tools(cfg)["market"] if t["name"] == "get_price_history")
    assert tool["handler"]({"symbol": "NVDA", "start_date": "2025-12-01", "end_date": "2026-03-01"}) == "ok"
    assert seen["as_of"] == "2026-01-15"
    assert seen["max_stale_days"] == cfg.max_stale_days == 7        # the run's limit reaches the tool


def _arg_for(name: str, schema: dict):
    """A value the schema accepts, so a handler can be CALLED, not just shaped."""
    kind = schema.get("type")
    if kind == "array":
        item = schema.get("items", {})
        return [(item.get("enum") or ["sma_20"])[0]]
    if kind == "integer":
        return schema.get("minimum", 10)
    if schema.get("enum"):
        return schema["enum"][0]
    return {"symbol": "NVDA", "series": "cpi"}.get(name, "x")


def test_every_handler_can_actually_be_called(tmp_path, monkeypatch):
    """Every tool's handler runs once, with the data layer stubbed out.

    `test_specs_are_well_formed` asserts the handler is callable and stops
    there, which is why `get_fundamentals` closed over an unbound name for six
    days: the lambda is only compiled when it RUNS, and until 2026-10-09
    `with_deadline` turned the resulting NameError into a DATA_UNAVAILABLE
    sentence that read exactly like a dead endpoint.  So the assertion that
    matters is not that a handler exists but that calling it reaches the data
    layer — for every tool, including the ones added after this was written.
    """
    # Everything in the data layer EXCEPT the deadline wrapper: stubbing that
    # would make `guarded` return without ever running the lambda, and the
    # test would pass with the NameError still in place — it did, the first
    # time this was written.
    for name in dir(data):
        fn = getattr(data, name)
        if (not name.startswith("_") and callable(fn)
                and getattr(fn, "__module__", "") == data.__name__
                and "deadline" not in name):
            monkeypatch.setattr(data, name, lambda *a, **k: "stub")

    cfg = RunConfig("NVDA", "2026-01-15", workspace=tmp_path)
    called = 0
    for specs in host_tools(cfg).values():
        for spec in specs:
            props = spec["parameters"]["properties"]
            args = {k: _arg_for(k, props[k]) for k in spec["parameters"]["required"]}
            assert spec["handler"](args) == "stub", f"{spec['name']} did not reach the data layer"
            called += 1
    assert called >= 10        # the four analysts' tools, whatever they grow to
