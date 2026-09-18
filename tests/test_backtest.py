import datetime as dt

import pytest

from ta_cascade import backtest
from ta_cascade.cli import main

yaml = pytest.importorskip("yaml", reason="PyYAML (jaato-eval's manifest reader) is not installed")


def test_date_grid_is_inclusive_and_stepped():
    got = backtest.date_grid(dt.date(2026, 4, 3), dt.date(2026, 4, 24), 7)
    assert got == [dt.date(2026, 4, 3), dt.date(2026, 4, 10), dt.date(2026, 4, 17), dt.date(2026, 4, 24)]
    with pytest.raises(ValueError):
        backtest.date_grid(dt.date(2026, 4, 3), dt.date(2026, 4, 1), 7)


def test_tasks_are_manifests_jaato_eval_can_read(tmp_path):
    (tmp_path / ".jaato").mkdir()
    written = backtest.write_tasks(tmp_path, "pilot", ["nvda", "AMD"],
                                   [dt.date(2026, 4, 3), dt.date(2026, 4, 10)], repeats=3)
    assert len(written) == 4
    task = yaml.safe_load(written[0].read_text())
    assert task["id"] == "backtest/pilot/NVDA/2026-04-03"
    assert task["harness"]["kind"] == "driver" and task["repeats"] == 3
    assert "profile" not in task["harness"] and "prompt" not in task["input"]
    assert task["input"]["params"] == {"TICKER": "NVDA", "TRADE_DATE": "2026-04-03"}
    root = written[0].parent
    assert (root / task["environment"]["fixture"]).resolve().is_dir()
    assert (root / task["environment"]["config_root"]).resolve() == (tmp_path / ".jaato").resolve()
    assert "$JAATO_EVAL_PYTHON" in task["harness"]["run"] and "--no-memory" in task["harness"]["run"]
    assert "$JAATO_EVAL_PARAM_TICKER" in task["harness"]["run"]
    assert task["graders"] == [{"kind": "script", "run": '"$JAATO_EVAL_PYTHON" -m ta_cascade.score'}]
    assert "budget" not in task


def test_unknown_analyst_is_refused(tmp_path):
    with pytest.raises(ValueError, match="bogus"):
        backtest.write_tasks(tmp_path, "x", ["NVDA"], [dt.date(2026, 4, 3)], analysts=["bogus"])


def test_cli_subcommand(tmp_path, capsys):
    (tmp_path / ".jaato").mkdir()
    rc = main(["backtest-tasks", "pilot", "--tickers", "NVDA", "--from", "2026-04-03",
               "--to", "2026-04-17", "--repo", str(tmp_path)])
    out = capsys.readouterr().out
    assert rc == 0 and "3 task(s)" in out and "jaato-eval run backtests/pilot/tasks" in out
    assert (tmp_path / "backtests" / "pilot" / "tasks" / "NVDA-2026-04-17" / "task.yaml").exists()
