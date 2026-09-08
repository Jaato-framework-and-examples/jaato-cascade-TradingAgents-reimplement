import numpy as np
import pandas as pd

from ta_cascade import data


def _frame(n=260, seed=1):
    rng = np.random.default_rng(seed)
    close = 100 + np.cumsum(rng.normal(0, 1, n))
    idx = pd.bdate_range("2025-01-01", periods=n)
    return pd.DataFrame({"Open": close - 0.2, "High": close + 1, "Low": close - 1,
                         "Close": close, "Volume": rng.integers(1_000, 5_000, n)}, index=idx)


def test_indicator_columns_and_ranges():
    out = data.compute_indicators(_frame())
    for name in data.INDICATOR_CATALOG:
        assert name in out.columns
    tail = out.tail(50)
    assert tail["rsi_14"].between(0, 100).all()
    assert (tail["bb_upper"] >= tail["bb_mid"]).all() and (tail["bb_lower"] <= tail["bb_mid"]).all()
    assert (tail["atr_14"] > 0).all()
    assert np.isclose(tail["macd_hist"], tail["macd"] - tail["macd_signal"]).all()
    assert np.isclose(out["sma_20"].iloc[-1], out["Close"].tail(20).mean())


def test_unknown_indicator_is_a_sentence():
    text = data.indicators("X", ["sma_20", "bogus"], "2026-01-15")
    assert text.startswith(data.UNAVAILABLE) and "bogus" in text


def test_macro_without_key_is_a_sentence(monkeypatch):
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    text = data.macro("cpi", "2026-01-15")
    assert text.startswith(data.UNAVAILABLE) and "CPIAUCSL" in text


def test_news_window_filter():
    import datetime as dt
    items = [(dt.datetime(2026, 1, 14, tzinfo=dt.timezone.utc), "in", "src", ""),
             (dt.datetime(2026, 1, 20, tzinfo=dt.timezone.utc), "future", "src", "")]
    text = data._format_news(items, dt.date(2026, 1, 8), dt.date(2026, 1, 15), 10)
    assert "in" in text and "future" not in text
