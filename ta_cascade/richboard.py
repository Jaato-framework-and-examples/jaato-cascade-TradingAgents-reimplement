"""The live view: the pipeline diagram above, the stage trace below.

The renderer, and the ONLY module that imports ``rich``.  :class:`BoardState`
decides what is true; this decides what it looks like, so the diagram can be
tested without a terminal and this file stays replaceable.

Chosen only when stdout is a real terminal.  Piped or redirected — ``| tee``,
CI, a captured log — the driver keeps its plain lines, because that output is
also the artifact people grep and a live view would either fight the pipe or
emit nothing useful into it.

THE EXCHANGE LANE is the one thing here that is not in the general shape of a
progress diagram.  Two of this pipeline's phases are debates, not steps: the
driver relays each side's last turn to the other, and rendered as a flat list
of rows a debate is indistinguishable from a chain.  The lane draws the relay
under a running debate — who has spoken, who holds the floor, which way it
goes round — and derives it entirely from the debate's child steps, so it
owns no state and cannot disagree with the rows above it.
"""
from __future__ import annotations

from collections import deque
from typing import Callable, List, Optional, Tuple

from .board import DONE, FAILED, PENDING, RUNNING, RecordingBoard, Step

_GLYPH = {PENDING: ("·", "grey42"), RUNNING: ("●", "yellow"),
          DONE: ("✓", "green"), FAILED: ("✗", "red")}

_LANE_WINDOW = 6
"""Turns shown in an exchange lane before it elides from the left.

A debate is ``2 * rounds`` or ``3 * rounds`` turns; at the default depths
that is 2 and 3, but the lane must not grow without bound when someone runs
``--risk-rounds 4``.  The window keeps the present visible, which is what the
lane is for; the rows above it still carry every turn.
"""


class RichBoard(RecordingBoard):
    """Live two-panel display, driven by the same calls every board takes.

    Inherits state handling from :class:`RecordingBoard` and adds only the
    drawing, so a bug in what the diagram CLAIMS is a bug in ``BoardState``,
    which has its own tests and needs no terminal to run them.

    The trace panel keeps the last ``trace_lines`` lines in a deque, not the
    whole run: it is a window on the present, and an unbounded buffer in a
    long cascade is a memory leak with a scrollbar.
    """

    def __init__(self, *, trace_lines: int = 200, refresh_per_second: float = 8,
                 height: Optional[Callable[[], int]] = None) -> None:
        super().__init__()
        self._traces: deque = deque(maxlen=trace_lines)
        # The last line and how many times it has repeated, so a run of
        # identical lines collapses into a count instead of scrolling the
        # panel.  Tracked rather than parsed back off the rendered string:
        # the suffix is presentation, and re-reading it would make the
        # counter depend on how it happens to be formatted.
        self._last: Optional[str] = None
        self._repeats = 1
        self._refresh = refresh_per_second
        self._live = None
        # How tall the view may be.  Injectable so the budgeting is testable
        # without a terminal; live, it asks the console on each render so a
        # resized pane is honoured on the next frame.
        self._height = height or self._console_height

    # Two borders per panel plus the top panel's title row: spent whatever
    # the content is, so subtracted before anything is given a budget.
    _CHROME = 5

    def _console_height(self) -> int:
        if self._live is not None:
            return self._live.console.size.height
        return 24

    def _budget(self) -> Tuple[int, int]:
        """Split the console between the two panels.

        MUST fit.  A ``rich.Live`` renderable taller than the console cannot
        be redrawn in place with ``screen=False`` — rich rewrites the whole
        region on every refresh, which reads as flicker.  So the diagram is
        capped at half the height and the trace takes the rest, each with a
        floor so neither is squeezed to nothing on a short terminal.

        Both panels then show their TAIL: the frontier of the diagram is the
        part still in play and the end of the trace is the present.  The
        header carries the global counts, which is what a scrolled-off top
        row would otherwise have told you.
        """
        available = max(8, self._height() - self._CHROME)
        diagram = max(3, min(len(self._rows()), available // 2))
        return diagram, max(3, available - diagram)

    # ------------------------------------------------------------- lifecycle
    def __enter__(self):
        from rich.console import Console
        from rich.live import Live
        self._live = Live(self._render(), console=Console(),
                          refresh_per_second=self._refresh,
                          screen=False, transient=False)
        self._live.__enter__()
        return self

    def __exit__(self, *exc):
        if self._live is not None:
            self._live.update(self._render())
            self._live.__exit__(*exc)
            self._live = None
        return False

    # ---------------------------------------------------------------- writes
    def _refreshed(self) -> None:
        if self._live is not None:
            self._live.update(self._render())

    def plan(self, steps) -> None:
        super().plan(steps); self._refreshed()

    def start(self, key: str, label: str = "", depth: int = 0) -> None:
        super().start(key, label, depth); self._refreshed()

    def finish(self, key: str, detail: str = "", failed: bool = False,
               label: str = "", depth: int = 0) -> None:
        super().finish(key, detail, failed, label, depth); self._refreshed()

    def close(self, verdict: str) -> None:
        super().close(verdict); self._refreshed()

    def trace(self, line: str) -> None:
        """Append a line, or fold it into the one above if it repeats.

        A stage that re-prepares its completion emits the same line over and
        over, and each one pushes the rest of the trace off the panel.  Shown
        as ``×N`` the repetition becomes the signal it actually is: an agent
        going round the same loop is exactly what a watcher wants to see, and
        N identical rows say it worse than one row and a number.

        Only CONSECUTIVE repeats fold.  The same line later in the stage,
        after something else happened in between, is a new fact.
        """
        if line == self._last:
            self._repeats += 1
            self._traces[-1] = f"{line}  ×{self._repeats}"
        else:
            self._last, self._repeats = line, 1
            self._traces.append(line)
        self._refreshed()

    # --------------------------------------------------------------- drawing
    def _rows(self) -> List[Tuple[Step, Optional[str]]]:
        """The diagram's rows: every step, plus a lane under a live debate.

        Built before budgeting so a lane row is counted like any other and
        cannot push the renderable past the console height.
        """
        rows: List[Tuple[Step, Optional[str]]] = []
        for step in self.state.steps:
            rows.append((step, None))
            if step.state == RUNNING:
                lane = self._lane(step)
                if lane:
                    rows.append((step, lane))
        return rows

    def _lane(self, parent: Step) -> str:
        """The relay under a running debate, or "" when it is not one."""
        turns = self.state.children(parent.key)
        if len(turns) < 2:
            return ""
        shown = turns[-_LANE_WINDOW:]
        parts = []
        for turn in shown:
            colour = _GLYPH[turn.state][1]
            name = turn.label.split()[0]
            parts.append(f"[{colour}]{name}[/{colour}]"
                         if turn.state != RUNNING else
                         f"[reverse {colour}] {name} [/reverse {colour}]")
        lead = "… " if len(turns) > len(shown) else ""
        return lead + " ─> ".join(parts)

    def _render(self):
        from rich.console import Group
        from rich.panel import Panel
        diagram_rows, trace_rows = self._budget()
        return Group(
            Panel(self._diagram(diagram_rows), title=self._title(), border_style="cyan"),
            Panel(self._trace(trace_rows), title="stage trace", border_style="grey42"))

    def _title(self) -> str:
        c = self.state.counts()
        head = f"{c[DONE]} done"
        if c[FAILED]:
            head += f", {c[FAILED]} failed"
        head += f", {c[PENDING]} to go"
        return f"{head} — {self.state.verdict}" if self.state.verdict else head

    def _diagram(self, rows: int):
        from rich.table import Table
        table = Table.grid(padding=(0, 1))
        table.add_column(width=2)
        table.add_column(ratio=1)
        table.add_column(justify="right", width=8)
        for step, lane in self._rows()[-rows:]:
            if lane is not None:
                table.add_row("", ("  " * (step.depth + 1)) + lane, "")
                continue
            glyph, colour = _GLYPH[step.state]
            label = ("  " * step.depth) + step.label
            timing = f"{step.elapsed:.0f}s" if step.elapsed else ""
            detail = f"  [dim]{step.detail}[/dim]" if step.detail else ""
            table.add_row(f"[{colour}]{glyph}[/{colour}]",
                          f"[{colour}]{label}[/{colour}]{detail}",
                          f"[dim]{timing}[/dim]")
        return table

    def _trace(self, rows: int):
        from rich.text import Text
        # `no_wrap` because a wrapped line costs more rows than the budget
        # counted, which puts the overflow — and the flicker — straight back.
        return Text("\n".join(list(self._traces)[-rows:]) or "(waiting)",
                    no_wrap=True, overflow="ellipsis")
