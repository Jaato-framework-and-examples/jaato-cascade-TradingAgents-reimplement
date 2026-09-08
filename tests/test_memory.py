from ta_cascade.memory import DecisionLog


def test_record_resolve_and_context(tmp_path):
    log = DecisionLog(tmp_path / "d.jsonl")
    assert log.past_context("NVDA") == ""
    log.record("NVDA", "2026-01-15", "Overweight", "thesis A", holding_days=5)
    log.record("NVDA", "2026-01-15", "Buy", "duplicate", holding_days=5)  # idempotent
    log.record("AAPL", "2026-01-10", "Hold", "thesis B", holding_days=5)
    assert [d.rating for d in log.pending("NVDA")] == ["Overweight"]
    assert log.past_context("NVDA") == ""          # pending entries never surface

    log.resolve("NVDA", "2026-01-15", raw_return=0.04, alpha=0.02, benchmark="SPY",
                resolved_on="2026-01-23", lesson="held", call_was_correct=True)
    log.resolve("AAPL", "2026-01-10", raw_return=-0.01, alpha=-0.03, benchmark="SPY",
                resolved_on="2026-01-18", lesson="stale", call_was_correct=False)
    assert log.pending("NVDA") == []
    ctx = log.past_context("NVDA")
    assert "Overweight" in ctx and "+2.00%" in ctx and "AAPL" in ctx and "stale" in ctx
    # point in time: nothing resolved on or before the 20th for NVDA
    assert "Overweight" not in log.past_context("NVDA", as_of="2026-01-20")
    assert "stale" in log.past_context("NVDA", as_of="2026-01-20")
