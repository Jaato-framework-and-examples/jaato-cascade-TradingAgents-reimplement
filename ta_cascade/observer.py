"""What happens INSIDE a stage, rendered as it happens.

Between ``open_stage`` and the payload coming back, a driver-sequenced
cascade has nothing to say: it is blocked in ``complete()`` or ``ask()``.
On this pipeline that silence is 20-60 s per stage and the operator's only
recourse was ``-v``, which turned on every dependency's DEBUG stream.  The
daemon is emitting the whole time, though: every session a run opens is
stamped with the run's ``cascade_driver_id``, and an observer subscribed to
that id sees the stage work.

This module owns the RENDERING half and imports no SDK: it takes duck-typed
events and returns lines.  The subscription half lives in
:mod:`ta_cascade.sessions`, which is this package's only SDK importer.  The
split is what makes the interesting part — which event becomes which line,
and who it is attributed to — testable without a daemon.

ATTRIBUTION IS BY ``session_id``.  This pipeline runs two investment
debaters and three risk debaters CONCURRENTLY under one cascade id, so
several sessions are live at once and only ``session_id`` separates them.
``AgentCreatedEvent`` carries ``session_id`` and ``profile_name`` together,
so the observer builds the map itself and needs nothing from the driver.
(Measured on the live run of 2026-09-08: this pipeline's ``agent_id`` is the
profile name rather than the ``"main"`` the SDK warns about, because the
driver names an agent per stage — but that is a coincidence of how we open
sessions, not a guarantee, so it is not what we key on.)
"""
from __future__ import annotations

from typing import Any, Dict, List

OBSERVED_EVENT_TYPES = [
    "AgentCreatedEvent",
    "ToolCallStartEvent",
]
"""The two the daemon is asked for.

Narrow on purpose: the per-client event queue is bounded and lossy exactly
for high-volume traffic (``JAATO_IPC_EVENT_QUEUE_MAX``), so an observer that
subscribes to everything pays for events it will not draw.  These two answer
"which stage is live" and "what is it doing", which is the whole job — the
driver already knows when a stage finished, because it is the thing awaiting
the payload.
"""

_INDENT = "   · "


class StageObserver:
    """Turns one cascade event into zero or more lines, attributed to a stage.

    Stateful in one respect only: ``session_id -> profile``, learned from
    ``AgentCreatedEvent``.  An event whose session was never announced
    renders with ``?`` rather than being dropped — an unattributed line is
    still evidence, and discarding it would hide the one case most worth
    seeing, a session running under this run's id that the driver did not
    open.  (Seen for real while probing: attaching an observer mid-run
    renders the stages already in flight as ``?``.)
    """

    def __init__(self) -> None:
        self.sessions: Dict[str, str] = {}

    def render(self, event: Any) -> List[str]:
        kind = type(event).__name__
        if kind == "AgentCreatedEvent":
            return self._agent_created(event)
        if kind == "ToolCallStartEvent":
            return [f"{_INDENT}{self._who(event)} -> "
                    f"{getattr(event, 'tool_name', '') or '?'}"]
        return []

    # ------------------------------------------------------------------
    def _agent_created(self, event: Any) -> List[str]:
        sid = getattr(event, "session_id", "") or ""
        profile = getattr(event, "profile_name", "") or "?"
        if sid:
            self.sessions[sid] = profile
        return [f"{_INDENT}{profile} session open"]

    def _who(self, event: Any) -> str:
        """The stage an event belongs to, or ``?`` when it was never announced."""
        return self.sessions.get(getattr(event, "session_id", "") or "", "?")
