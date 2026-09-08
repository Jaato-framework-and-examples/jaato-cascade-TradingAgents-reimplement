from ta_cascade.report import write_report
from ta_cascade.state import DebateTurn, RunState


def test_report_tree(tmp_path):
    s = RunState(ticker="T", trade_date="2026-01-15", asset_type="stock", instrument_context="T — test")
    s.reports["market"] = {"report": "trend up", "stance": "bullish", "confidence": "high", "tools_used": ["x"], "errors": [], "warnings": ["w"]}
    s.investment_debate = [DebateTurn("Bull", "up"), DebateTurn("Bear", "down")]
    s.portfolio_decision = {"rating": "Buy", "executive_summary": "go", "investment_thesis": "t", "price_target": None, "time_horizon": None, "errors": [], "warnings": []}
    root = write_report(s, tmp_path)
    assert (root / "1_analysts" / "market.md").exists()
    assert (root / "2_research" / "debate.md").exists()
    assert not (root / "3_trading").exists()
    text = (root / "report.md").read_text()
    assert "Portfolio decision" in text and "**Rating**: Buy" in text and "_Warnings_: w" in text
