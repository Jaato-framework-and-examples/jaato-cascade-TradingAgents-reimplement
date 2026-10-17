from ta_cascade import data, tools
from ta_cascade.config import RunConfig
from ta_cascade.tools import host_tools


def test_specs_are_well_formed(tmp_path):
    cfg = RunConfig("NVDA", "2026-01-15", workspace=tmp_path)
    tools = host_tools(cfg)
    assert set(tools) == {"market", "news", "fundamentals", "sentiment"}
    assert all(specs for specs in tools.values()), "every analyst gets host tools"
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


def test_handler_deadline_comes_from_the_framework_not_from_here(tmp_path):
    """The deadline is the daemon's budget minus the handoff margin.

    Nothing in `tools.py` states the budget: `resolve_client_tool_timeout` is
    the module the daemon's own registration path calls, so if the framework's
    default moves, every handler here follows it.  The assertion that matters
    is the INEQUALITY — ours must fire first, or the model gets
    `{"error": "Client tool <name> timed out after <N>s"}` instead of the
    data layer's sentence, which is how five arms of the third batch died
    (jaato#1625, docs/gaps.md 2026-10-11).
    """
    from jaato_sdk.client_tool_timeout import resolve_client_tool_timeout

    cfg = RunConfig("NVDA", "2026-01-15", workspace=tmp_path)
    specs = [s for v in host_tools(cfg).values() for s in v]
    assert specs
    for spec in specs:
        budget = resolve_client_tool_timeout(spec).timeout_s
        assert tools.handler_deadline_s(spec) == budget - tools.HANDOFF_MARGIN_S
        assert tools.handler_deadline_s(spec) < budget


def test_a_declared_timeout_moves_the_deadline_with_it():
    """A spec that names its own budget (ms) gets a deadline under THAT."""
    assert tools.handler_deadline_s({"name": "t", "timeout": 60000}) == 55.0
    assert tools.handler_deadline_s({"name": "t"}) < 30.0        # the framework default


def test_a_budget_too_small_for_a_handler_is_refused():
    """No silent clamp: a budget under the margin leaves no handler at all."""
    import pytest
    with pytest.raises(ValueError, match="no room for a handler"):
        tools.handler_deadline_s({"name": "t", "timeout": 2000})


def test_the_sentiment_analyst_fetches_through_host_tools(tmp_path):
    """Its four sources are host tools, so the data layer runs HERE.

    Until 2026-10-17 the same four were fetched by a persona prefetch script
    running inside the runner, which forced `ta_cascade` to be installed in the
    DAEMON's venv.  Asserting the names keeps that from coming back unnoticed.
    """
    cfg = RunConfig("NVDA", "2026-01-15", workspace=tmp_path)
    names = [s["name"] for s in host_tools(cfg)["sentiment"]]
    assert names == ["get_company_news", "get_global_news",
                     "get_stocktwits_messages", "get_reddit_posts"]


def test_the_social_handlers_clamp_to_the_trade_date(tmp_path, monkeypatch):
    seen = {}

    def fake(symbol, start, end, as_of, *a, **kw):
        seen[symbol] = (start, end, as_of)
        return "ok"

    monkeypatch.setattr(data, "stocktwits_messages", fake)
    monkeypatch.setattr(data, "reddit_posts", fake)
    specs = {s["name"]: s for s in host_tools(RunConfig("NVDA", "2026-01-15",
                                                        workspace=tmp_path))["sentiment"]}
    for name in ("get_stocktwits_messages", "get_reddit_posts"):
        seen.clear()
        assert specs[name]["handler"]({"symbol": "NVDA", "end_date": "2026-06-01"}) == "ok"
        # The window's start defaults to a week back and the as-of date is the
        # run's, never the model's: it cannot ask past the date being analysed.
        assert seen["NVDA"] == ("2026-01-08", "2026-06-01", "2026-01-15")
