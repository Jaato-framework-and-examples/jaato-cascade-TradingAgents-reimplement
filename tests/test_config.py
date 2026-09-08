import pytest

from ta_cascade.config import RunConfig


def test_run_key_depends_on_shape(tmp_path):
    a = RunConfig("nvda", "2026-01-15", workspace=tmp_path)
    b = RunConfig("NVDA", "2026-01-15", workspace=tmp_path)
    c = RunConfig("NVDA", "2026-01-15", analysts=["market"], workspace=tmp_path)
    assert a.ticker == "NVDA" and a.run_key == b.run_key
    assert a.run_key != c.run_key
    assert a.config_root == tmp_path / ".jaato"


def test_rejects_bad_inputs(tmp_path):
    with pytest.raises(ValueError):
        RunConfig("X", "2026-01-15", analysts=["weather"], workspace=tmp_path)
    with pytest.raises(ValueError):
        RunConfig("X", "2026-01-15", analysts=[], workspace=tmp_path)
    with pytest.raises(ValueError):
        RunConfig("X", "2026-01-15", asset_type="bond", workspace=tmp_path)
