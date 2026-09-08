import pytest

from ta_cascade.config import RunConfig


def test_run_key_depends_on_shape(tmp_path):
    a = RunConfig("nvda", "2026-01-15", workspace=tmp_path)
    b = RunConfig("NVDA", "2026-01-15", workspace=tmp_path)
    c = RunConfig("NVDA", "2026-01-15", analysts=["market"], workspace=tmp_path)
    assert a.ticker == "NVDA" and a.run_key == b.run_key
    assert a.run_key != c.run_key
    assert a.config_root == tmp_path / ".jaato"


def test_driver_products_stay_out_of_config_root(tmp_path):
    """``.jaato/`` is the framework's config_root; nothing we write goes there.

    The daemon resolves profiles and personas from that tree and writes its own
    ``logs/`` and ``sessions/`` into it.  Driver state belongs beside it, under
    ``.ta_cascade/``, so the ownership boundary survives future refactors.
    """
    cfg = RunConfig("NVDA", "2026-01-15", workspace=tmp_path)
    assert cfg.journal_dir == tmp_path / ".ta_cascade" / "journal"
    for path in (cfg.journal_dir, cfg.results_dir):
        assert cfg.config_root not in path.parents


def test_rejects_bad_inputs(tmp_path):
    with pytest.raises(ValueError):
        RunConfig("X", "2026-01-15", analysts=["weather"], workspace=tmp_path)
    with pytest.raises(ValueError):
        RunConfig("X", "2026-01-15", analysts=[], workspace=tmp_path)
    with pytest.raises(ValueError):
        RunConfig("X", "2026-01-15", asset_type="bond", workspace=tmp_path)
