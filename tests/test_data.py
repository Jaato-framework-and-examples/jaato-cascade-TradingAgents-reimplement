import datetime as dt
import json

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
    text = data.indicators("X", ["sma_20", "bogus"], "2026-01-15", max_stale_days=7)
    assert text.startswith(data.UNAVAILABLE) and "bogus" in text


def _serve(frame):
    """A ``_history`` stand-in serving ``frame`` between two dates, as the real one does."""
    def history(symbol, start, end):
        df = frame[(frame.index.date >= start) & (frame.index.date <= end)]
        if df.empty:
            raise LookupError(f"no bars for {symbol} between {start} and {end}")
        return df
    return history


def _facts(text):
    assert text.startswith("VERIFIED MARKET SNAPSHOT"), text
    return json.loads(text.split("\n", 1)[1])


def test_snapshot_window_is_calendar_days_and_levels_carry_dates(monkeypatch):
    f = _frame(n=300)
    as_of = f.index[-1].date()
    # 79 sessions before the last bar is ~110 calendar days: inside a 90-bar
    # window, outside a 90-day one -- the mislabel that quoted a May high as
    # the "90-day high" in September.
    spike = f.index[-80]
    f.loc[spike, "High"] = f["High"].max() + 50
    monkeypatch.setattr(data, "_history", _serve(f))
    facts = _facts(data.snapshot("X", as_of.isoformat(), 90, max_stale_days=7))

    window = f[f.index.date > as_of - dt.timedelta(days=90)]
    assert facts["window_90d"] == {"from": window.index[0].date().isoformat(),
                                   "to": as_of.isoformat(), "bars": len(window)}
    assert facts["high_90d"] == {"value": round(float(window["High"].max()), 4),
                                 "date": window["High"].idxmax().date().isoformat()}
    assert facts["high_90d"]["date"] != spike.date().isoformat()
    assert facts["low_90d"]["date"] == window["Low"].idxmin().date().isoformat()
    closes = facts["recent_closes"]
    assert len(closes) == data.RECENT_CLOSES and max(closes) == as_of.isoformat()
    assert facts["avg_volume_20d"] == int(f["Volume"].tail(20).mean())   # 20 sessions, whatever the window


def test_indicators_window_is_calendar_days(monkeypatch):
    f = _frame()
    as_of = f.index[-1].date()
    monkeypatch.setattr(data, "_history", _serve(f))
    csv = data.indicators("X", ["sma_20"], as_of.isoformat(), 30, max_stale_days=7)
    rows = [line for line in csv.splitlines() if line[:4].isdigit()]
    assert len(rows) == int((f.index.date > as_of - dt.timedelta(days=30)).sum())


def test_stale_bars_are_refused_not_quoted(monkeypatch):
    f = _frame()
    newest = f.index[-1].date()
    monkeypatch.setattr(data, "_history", _serve(f))
    at_limit = (newest + dt.timedelta(days=7)).isoformat()
    assert data.snapshot("X", at_limit, 30, max_stale_days=7).startswith("VERIFIED")

    past = (newest + dt.timedelta(days=8)).isoformat()
    for text in (data.snapshot("X", past, 30, max_stale_days=7),
                 data.indicators("X", ["sma_20"], past, 30, max_stale_days=7),
                 data.ohlcv("X", "2025-06-01", past, past, max_stale_days=7)):
        assert text.startswith(data.UNAVAILABLE) and "stale" in text, text


def test_an_empty_window_says_so(monkeypatch):
    f = _frame()
    newest = f.index[-1].date()
    monkeypatch.setattr(data, "_history", _serve(f))
    text = data.snapshot("X", (newest + dt.timedelta(days=6)).isoformat(), 5, max_stale_days=7)
    assert text.startswith(data.UNAVAILABLE) and "no bars in the 5 calendar days" in text


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
