"""The board's state and the plan it is drawn from — no terminal involved."""
import pytest

from ta_cascade.board import DONE, FAILED, PENDING, RUNNING, BoardState, NullBoard, RecordingBoard
from ta_cascade.config import RunConfig
from ta_cascade.pipeline import plan_of


def test_plan_is_a_function_of_the_config(tmp_path):
    """The whole diagram is known before any session opens — that is what
    lets the board say how much is LEFT rather than only what has happened."""
    cfg = RunConfig("NVDA", "2026-09-04", analysts=["market", "news"],
                    max_debate_rounds=2, max_risk_rounds=1, workspace=tmp_path)
    keys = [k for k, _, _ in plan_of(cfg)]
    assert keys == [
        "analyst:market", "analyst:news",
        "debate:investment",
        "debate:investment:0", "debate:investment:1",
        "debate:investment:2", "debate:investment:3",
        "stage:research_manager", "stage:trader",
        "debate:risk", "debate:risk:0", "debate:risk:1", "debate:risk:2",
        "stage:portfolio_manager",
    ]
    labels = {k: l for k, l, _ in plan_of(cfg)}
    assert labels["debate:investment:2"] == "Bull 2"      # round 2 opens with the bull
    assert labels["debate:risk:1"] == "Conservative 1"


def test_debate_turns_nest_under_their_debate(tmp_path):
    cfg = RunConfig("NVDA", "2026-09-04", analysts=["market"], workspace=tmp_path)
    board = RecordingBoard()
    board.plan(plan_of(cfg))
    kids = [s.label for s in board.state.children("debate:risk")]
    assert kids == ["Aggressive 1", "Conservative 1", "Neutral 1"]
    assert board.state.children("stage:trader") == []     # a step, not a debate


def test_transitions_and_counts():
    board = RecordingBoard()
    board.plan([("a", "A", 0), ("b", "B", 0)])
    assert board.state.counts()[PENDING] == 2
    board.start("a")
    assert board.state.running.key == "a"
    board.finish("a", "Overweight")
    assert board.state.counts() == {PENDING: 1, RUNNING: 0, DONE: 1, FAILED: 0}
    assert board.state.steps[0].detail == "Overweight"


def test_elapsed_is_measured_from_start():
    ticks = iter([100.0, 107.5])          # start() reads once, finish() once
    state = BoardState(now=lambda: next(ticks))
    state.start("a", "A")
    state.finish("a")
    assert state.steps[0].elapsed == pytest.approx(7.5)


def test_close_does_not_leave_a_step_claiming_to_run():
    """A run that ended with a step RUNNING did not finish it; saying so is
    the difference between a display and a lie."""
    board = RecordingBoard()
    board.plan([("a", "A", 0), ("b", "B", 0)])
    board.start("a")
    board.close("stopped: session could not be created")
    assert board.state.steps[0].state == FAILED
    assert board.state.steps[1].state == PENDING
    assert "stopped" in board.state.verdict


def test_unknown_keys_are_appended_not_dropped():
    board = RecordingBoard()
    board.plan([("a", "A", 0)])
    board.start("surprise", "a stage nobody planned")
    assert [s.key for s in board.state.steps] == ["a", "surprise"]


def test_null_board_records_nothing_and_accepts_everything():
    """The default must be inert: a display is never load-bearing."""
    board = NullBoard()
    board.plan([("a", "A", 0)])
    board.start("a"); board.trace("x"); board.finish("a"); board.close("done")
    assert board.state.steps == []
    with board as b:
        assert b is board
