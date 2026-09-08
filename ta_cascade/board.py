"""The run's progress, as state a renderer can draw.

Kept separate from any renderer, and pure: whether the diagram tells the
truth is decided here, and decided without a terminal.  The split follows
the framework's own note that the pipeline produces structured data and the
client decides presentation.

WHY A DIAGRAM IS POSSIBLE.  This pipeline's shape is a function of
``RunConfig`` alone — the analysts, ``2 * max_debate_rounds`` investment
turns, ``3 * max_risk_rounds`` risk turns, four fixed judges — so the whole
plan is known before the first session opens and can be drawn up front and
filled in.  That is the one thing a stream of log lines cannot show: how
much is left.

Structure comes from the driver, which is the only thing that knows the
graph; what happens *inside* a stage comes from the daemon's event stream
(see :mod:`ta_cascade.observer`).  Neither knows the other's half.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple

PENDING, RUNNING, DONE, FAILED = "pending", "running", "done", "failed"


@dataclass
class Step:
    """One row of the diagram.

    ``key`` identifies it for transitions; ``depth`` nests a debate turn
    under the debate it belongs to.  ``detail`` is the short verdict a
    finished step carries (``Overweight``, ``3 warnings``) — never a second
    sentence, because the trace panel is where prose belongs.
    """

    key: str
    label: str
    depth: int = 0
    state: str = PENDING
    detail: str = ""
    started: Optional[float] = None
    elapsed: Optional[float] = None


class BoardState:
    """Ordered steps plus the transitions the driver reports.

    Unknown keys are APPENDED rather than dropped.  The plan is complete by
    construction here, so an unplanned key means the driver did something
    the plan did not predict — exactly the thing worth seeing, not hiding.
    """

    def __init__(self, now: Callable[[], float] = time.monotonic) -> None:
        self._now = now
        self.steps: List[Step] = []
        self._by_key: Dict[str, Step] = {}
        self.verdict: str = ""

    # ---------------------------------------------------------------- writes
    def declare(self, key: str, label: str = "", depth: int = 0) -> Step:
        """Add a step if it is new; return it either way (idempotent)."""
        step = self._by_key.get(key)
        if step is not None:
            return step
        step = Step(key=key, label=label or key, depth=depth)
        self.steps.append(step)
        self._by_key[key] = step
        return step

    def plan(self, steps: List[Tuple[str, str, int]]) -> None:
        for key, label, depth in steps:
            self.declare(key, label, depth)

    def start(self, key: str, label: str = "", depth: int = 0) -> None:
        step = self.declare(key, label, depth)
        step.state = RUNNING
        step.started = self._now()

    def finish(self, key: str, detail: str = "", failed: bool = False,
               label: str = "", depth: int = 0) -> None:
        step = self.declare(key, label, depth)
        step.state = FAILED if failed else DONE
        step.detail = detail
        if step.started is not None:
            step.elapsed = self._now() - step.started

    def close(self, verdict: str) -> None:
        """Record the outcome, and stop claiming anything is still running.

        A run that ended with a step in RUNNING did not finish that step —
        saying so is the difference between a display and a lie.
        """
        self.verdict = verdict
        for step in self.steps:
            if step.state == RUNNING:
                step.state = FAILED

    # ----------------------------------------------------------------- reads
    @property
    def running(self) -> Optional[Step]:
        for step in self.steps:
            if step.state == RUNNING:
                return step
        return None

    def children(self, key: str) -> List[Step]:
        """The steps nested directly under ``key``.

        Used to draw a debate's exchange from its turns, so the lane needs no
        state of its own and cannot disagree with the rows above it.
        """
        parent = self._by_key.get(key)
        if parent is None:
            return []
        out: List[Step] = []
        for step in self.steps[self.steps.index(parent) + 1:]:
            if step.depth <= parent.depth:
                break
            if step.depth == parent.depth + 1:
                out.append(step)
        return out

    def counts(self) -> Dict[str, int]:
        out = {PENDING: 0, RUNNING: 0, DONE: 0, FAILED: 0}
        for step in self.steps:
            out[step.state] += 1
        return out


class NullBoard:
    """Records nothing and draws nothing — the default, so neither a caller
    nor a test has a display imposed on it."""

    def __init__(self) -> None:
        self.state = BoardState()

    def plan(self, steps: List[Tuple[str, str, int]]) -> None: ...
    def start(self, key: str, label: str = "", depth: int = 0) -> None: ...
    def finish(self, key: str, detail: str = "", failed: bool = False,
               label: str = "", depth: int = 0) -> None: ...
    def close(self, verdict: str) -> None: ...
    def trace(self, line: str) -> None: ...
    def __enter__(self): return self
    def __exit__(self, *exc): return False


class RecordingBoard(NullBoard):
    """A :class:`NullBoard` that keeps the state, for tests and renderers."""

    def plan(self, steps: List[Tuple[str, str, int]]) -> None:
        self.state.plan(steps)

    def start(self, key: str, label: str = "", depth: int = 0) -> None:
        self.state.start(key, label, depth)

    def finish(self, key: str, detail: str = "", failed: bool = False,
               label: str = "", depth: int = 0) -> None:
        self.state.finish(key, detail, failed, label, depth)

    def close(self, verdict: str) -> None:
        self.state.close(verdict)
