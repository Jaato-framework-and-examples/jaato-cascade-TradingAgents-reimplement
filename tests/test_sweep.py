"""The sweep projection: what a monitor may say about hundreds of arms.

Every case here is files on disk, because that is all the projection is allowed
to read — a sweep must render whether or not anything is still running.
"""
import json

from ta_cascade import sweep


def _tasks(tmp_path, cells):
    d = tmp_path / "tasks"
    for c in cells:
        (d / c).mkdir(parents=True)
    return d


def _results(tmp_path, arms):
    p = tmp_path / "results.jsonl"
    p.write_text("".join(json.dumps(a) + "\n" for a in arms))
    return p


def _arm(ticker, date, state, cost=None, repeat=0, seconds=10.0, turns=9):
    return {"task_id": f"backtest/x/{ticker}/{date}", "arm_id": f"backtest/x/{ticker}/{date}@s#{repeat}",
            "repeat": repeat, "state": state, "duration_seconds": seconds, "turns": turns,
            "usage": {"cost_usd": cost}, "session_ids": ["a", "b"]}


def test_a_planned_cell_with_no_arm_is_pending(tmp_path):
    s = sweep.survey(_tasks(tmp_path, ["NVDA-2026-01-05", "AMD-2026-01-05"]),
                     _results(tmp_path, [_arm("NVDA", "2026-01-05", "PASS")]))
    by = {c["cell"]: c for c in s["cells"]}
    assert by["NVDA/2026-01-05"]["state"] == "PASS"
    assert by["AMD/2026-01-05"]["state"] == sweep.PENDING
    assert s["counts"] == {"PASS": 1, sweep.PENDING: 1}
    assert s["settled"] == 1 and s["progress"] == 0.5


def test_money_and_effort_count_ARMS_not_cells(tmp_path):
    """The bug this test exists for: keying results by cell kept only the last
    arm of each, and the pilot's spend read $9.16 against a real $47."""
    arms = [_arm("NVDA", "2026-01-05", "PASS", cost=1.0, repeat=r) for r in range(5)]
    s = sweep.survey(_tasks(tmp_path, ["NVDA-2026-01-05"]), _results(tmp_path, arms))
    assert s["total"] == 1                      # one cell
    assert s["money"]["arms"] == 5              # five arms
    assert s["money"]["cost_usd"] == 5.0        # not 1.0
    assert s["effort"]["turns"] == 45
    assert s["cells"][0]["arms"] == 5           # and the row says so


def test_a_partial_cost_is_withheld_entirely(tmp_path):
    """A subscription provider reports effort and no money. Summing only the
    priced arms would understate the bill and look authoritative doing it."""
    arms = [_arm("NVDA", "2026-01-05", "PASS", cost=1.0),
            _arm("AMD", "2026-01-05", "PASS", cost=None)]
    s = sweep.survey(_tasks(tmp_path, ["NVDA-2026-01-05", "AMD-2026-01-05"]), _results(tmp_path, arms))
    assert s["money"]["arms"] == 2 and s["money"]["priced"] == 1
    assert s["money"]["cost_usd"] is None


def test_a_rerun_arm_decides_the_cell(tmp_path):
    """--resume re-runs what failed; the re-run is the answer, and the arm
    count keeps the first attempt visible."""
    arms = [_arm("NVDA", "2026-01-05", "FAIL", repeat=0),
            _arm("NVDA", "2026-01-05", "PASS", repeat=1)]
    s = sweep.survey(_tasks(tmp_path, ["NVDA-2026-01-05"]), _results(tmp_path, arms))
    assert s["cells"][0]["state"] == "PASS" and s["cells"][0]["arms"] == 2


def test_an_open_session_makes_a_cell_running(tmp_path):
    ws = tmp_path / "ws" / "arm1" / "results" / "NVDA" / "2026-01-05"
    ws.mkdir(parents=True)
    (ws / "sessions.jsonl").write_text(
        json.dumps({"event": "started", "session_id": "s1", "ticker": "NVDA",
                    "trade_date": "2026-01-05", "stage": "market_analyst"}) + "\n")
    s = sweep.survey(_tasks(tmp_path, ["NVDA-2026-01-05"]), _results(tmp_path, []),
                     workspaces_dir=tmp_path / "ws")
    row = s["cells"][0]
    assert row["state"] == sweep.RUNNING and row["stage"] == "market_analyst"


def test_a_finished_arm_outranks_a_leftover_workspace(tmp_path):
    """--keep-workspaces leaves the workspace behind; the result is the truth."""
    ws = tmp_path / "ws" / "arm1" / "results" / "NVDA" / "2026-01-05"
    ws.mkdir(parents=True)
    (ws / "sessions.jsonl").write_text(
        json.dumps({"event": "started", "session_id": "s1", "ticker": "NVDA",
                    "trade_date": "2026-01-05", "stage": "trader"}) + "\n")
    s = sweep.survey(_tasks(tmp_path, ["NVDA-2026-01-05"]),
                     _results(tmp_path, [_arm("NVDA", "2026-01-05", "FAIL")]),
                     workspaces_dir=tmp_path / "ws")
    assert s["cells"][0]["state"] == "FAIL"


def test_a_torn_line_does_not_lose_the_run(tmp_path):
    p = tmp_path / "results.jsonl"
    p.write_text(json.dumps(_arm("NVDA", "2026-01-05", "PASS")) + "\n" + '{"task_id": "back')
    s = sweep.survey(_tasks(tmp_path, ["NVDA-2026-01-05"]), p)
    assert s["cells"][0]["state"] == "PASS"


def test_an_empty_sweep_is_all_pending_not_an_error(tmp_path):
    s = sweep.survey(_tasks(tmp_path, ["NVDA-2026-01-05"]), tmp_path / "nothing.jsonl")
    assert s["cells"][0]["state"] == sweep.PENDING
    assert s["progress"] == 0.0 and s["money"]["cost_usd"] is None
