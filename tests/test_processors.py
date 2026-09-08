import importlib.util
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1] / ".jaato" / "scripts" / "processors"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


CTX = SimpleNamespace(tool_calls=[], agent_params={}, workspace_path=None)


def test_analyst_gate_blocks_thin_reports():
    gate = _load("analyst_report")
    short = {"report": "too short", "stance": "bullish", "confidence": "low", "tools_used": [], "errors": [], "warnings": []}
    assert gate.validate(short, CTX)["errors"]
    long = dict(short, report="x" * 500)
    assert gate.validate(long, CTX)["errors"] == []
    gave_up = dict(short, errors=["no data"])
    assert gate.validate(gave_up, CTX)["errors"] == []
    assert "No report" in gate.render(gave_up, CTX)
    assert "**Stance**: bullish" in gate.render(long, CTX)


def test_price_gate():
    gate = _load("price_fields")
    ok = {"action": "Buy", "reasoning": "r", "entry_price": 100.0, "stop_loss": 92.0, "position_sizing": None, "errors": [], "warnings": []}
    assert gate.validate(ok, CTX)["errors"] == []
    bad_stop = dict(ok, stop_loss=110.0)
    assert any("below" in e for e in gate.validate(bad_stop, CTX)["errors"])
    negative = dict(ok, entry_price=-5)
    assert gate.validate(negative, CTX)["errors"]
    pct = dict(ok, stop_loss=15.0)
    assert gate.validate(pct, CTX)["warnings"]
    pm = {"rating": "Hold", "executive_summary": "s", "investment_thesis": "t", "price_target": None, "time_horizon": None, "errors": [], "warnings": []}
    assert gate.validate(pm, CTX)["errors"] == []
    assert "**Rating**: Hold" in gate.render(pm, CTX)
