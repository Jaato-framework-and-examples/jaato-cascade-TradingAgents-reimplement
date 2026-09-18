import datetime as dt

import numpy as np
import pandas as pd
import pytest

from ta_cascade import chart, data
from ta_cascade.config import RunConfig
from ta_cascade.report import write_report
from ta_cascade.state import RunState

pytest.importorskip("matplotlib")

PNG = b"\x89PNG\r\n\x1a\n"


def _bars(start, n, seed=3):
    rng = np.random.default_rng(seed)
    close = 200 + np.cumsum(rng.normal(0, 2, n))
    idx = pd.bdate_range(start, periods=n)
    return pd.DataFrame({"Open": close - 0.5, "High": close + 2, "Low": close - 2,
                         "Close": close, "Volume": rng.integers(1_000_000, 5_000_000, n)}, index=idx)


def _state(**decision):
    s = RunState(ticker="NVDA", trade_date="2026-08-28", asset_type="stock", instrument_context="x")
    s.trader_proposal = {"action": "Buy", "entry_price": 217.5, "stop_loss": 208.0}
    s.portfolio_decision = {"rating": "Overweight", "price_target": 250.0, **decision}
    return s


def test_draw_writes_a_png_with_and_without_an_outcome(tmp_path):
    context = data.compute_indicators(_bars("2026-03-01", 130)).tail(85)
    outcome = _bars("2026-08-31", 5)
    for name, later in (("with", outcome), ("without", outcome.iloc[0:0])):
        out = chart.draw(context, later, _state(), tmp_path / name / "chart.png", holding_days=5)
        assert out.read_bytes()[:8] == PNG


def test_missing_levels_and_ratings_do_not_break_the_drawing(tmp_path):
    context = data.compute_indicators(_bars("2026-03-01", 130)).tail(85)
    s = _state(rating=None, price_target=None)
    s.trader_proposal = {"action": "Hold", "entry_price": None, "stop_loss": "n/a"}
    assert chart.draw(context, context.iloc[0:0], s, tmp_path / "chart.png", holding_days=5).exists()


def test_render_fetches_the_frames_and_never_raises(tmp_path, monkeypatch):
    frame = _bars("2025-06-01", 330)
    def history(symbol, start, end):
        df = frame[(frame.index.date >= start) & (frame.index.date <= end)]
        if df.empty:
            raise LookupError("no bars")
        return df
    monkeypatch.setattr(data, "_history", history)
    cfg = RunConfig("NVDA", "2026-08-28", workspace=tmp_path, results_dir=tmp_path / "results")
    out = chart.render(_state(), cfg)
    assert out == tmp_path / "results" / "NVDA" / "2026-08-28" / "chart.png" and out.exists()

    monkeypatch.setattr(data, "_history", lambda *a: (_ for _ in ()).throw(LookupError("no bars for X")))
    assert chart.render(_state(), cfg) is None                      # logged, not raised


def test_chart_frames_split_context_and_outcome(monkeypatch):
    frame = _bars("2025-06-01", 330)
    monkeypatch.setattr(data, "_history", lambda s, a, b: frame[(frame.index.date >= a) & (frame.index.date <= b)])
    context, outcome = data.chart_frames("NVDA", "2026-08-28", context_days=120, holding_days=5)
    assert context.index[-1].date() <= dt.date(2026, 8, 28)
    assert context.index[0].date() > dt.date(2026, 8, 28) - dt.timedelta(days=120)
    assert "sma_200" in context and context["sma_200"].notna().all()  # warmed up over the longer history
    assert len(outcome) == 5 and outcome.index[0].date() > dt.date(2026, 8, 28)


def test_report_links_the_chart_only_when_drawn(tmp_path):
    s = _state()
    root = write_report(s, tmp_path, chart=tmp_path / "NVDA" / "2026-08-28" / "chart.png")
    assert "![NVDA as of 2026-08-28: Overweight](chart.png)" in (root / "report.md").read_text()
    root = write_report(s, tmp_path / "plain")
    assert "chart.png" not in (root / "report.md").read_text()
