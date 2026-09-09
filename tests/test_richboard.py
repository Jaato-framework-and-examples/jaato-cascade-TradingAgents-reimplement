"""The drawing: the exchange lane, and the height budget that must fit.

No terminal — the console height is injected and the renderable is measured
with rich's own measurement, which is the thing that actually decides
whether ``Live`` can redraw in place.
"""
from rich.console import Console

from ta_cascade.board import RUNNING
from ta_cascade.config import RunConfig
from ta_cascade.pipeline import plan_of
from ta_cascade.richboard import RichBoard


def _rendered(board, width=100):
    console = Console(width=width, force_terminal=False, no_color=True)
    with console.capture() as cap:
        console.print(board._render())
    return cap.get()


def _board(height=40, **kw):
    cfg = RunConfig("NVDA", "2026-09-04", analysts=["market"], workspace="/tmp", **kw)
    board = RichBoard(height=lambda: height)
    board.plan(plan_of(cfg))
    return board


def test_lane_appears_only_under_a_running_debate():
    board = _board()
    assert "─>" not in _rendered(board)          # nothing running yet
    board.start("debate:risk")
    assert "─>" in _rendered(board)
    board.finish("debate:risk", "3 turns")
    assert "─>" not in _rendered(board)          # a finished debate is just a row


def test_lane_shows_the_relay_and_who_holds_the_floor():
    board = _board()
    board.start("debate:risk")
    board.start("debate:risk:0")
    board.finish("debate:risk:0")
    board.start("debate:risk:1")
    lane = next(l for l in _rendered(board).splitlines() if "─>" in l)
    # The live speaker is drawn in reverse video, which pads it with spaces —
    # so compare the names and their order, not the spacing.
    assert " ".join(lane.split()).strip("│ ") == "Aggressive ─> Conservative ─> Neutral"
    assert board.state.children("debate:risk")[1].state == RUNNING   # the padded one
    assert " Conservative " in lane                                  # highlighted, not plain


def test_lane_elides_from_the_left_when_a_debate_is_long():
    """--risk-rounds 4 is twelve turns; the lane is a window on the present,
    and the rows above it still carry every turn."""
    board = _board(max_risk_rounds=4)
    board.start("debate:risk")
    lane = board._lane(board.state._by_key["debate:risk"])
    assert lane.startswith("… ")
    assert lane.count("─>") == 5                 # a 6-turn window


def test_a_step_row_is_not_mistaken_for_a_debate():
    board = _board()
    board.start("stage:trader")
    assert board._lane(board.state._by_key["stage:trader"]) == ""


def test_the_renderable_fits_the_console(height=20):
    """A Live renderable taller than the console cannot be redrawn in place
    with screen=False: rich rewrites the whole region and it reads as
    flicker.  The budget exists to make that impossible."""
    board = _board(height=height, max_risk_rounds=4, max_debate_rounds=3)
    board.start("debate:risk")
    for i in range(200):
        board.trace(f"line {i}")
    lines = [l for l in _rendered(board).splitlines() if l.strip()]
    assert len(lines) <= height, f"{len(lines)} rows drawn into a {height}-row console"


def test_consecutive_repeats_fold_into_a_count():
    """An agent going round the same loop is the signal; seventeen identical
    rows say it worse than one row and a number."""
    board = _board()
    for _ in range(17):
        board.trace("   · trader -> signal_completion")
    assert "×17" in _rendered(board)
    board.trace("   · trader -> get_indicators")
    board.trace("   · trader -> signal_completion")
    out = _rendered(board)
    assert "×17" in out and out.count("signal_completion") == 2   # a new fact, own line
