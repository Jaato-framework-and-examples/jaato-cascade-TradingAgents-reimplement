"""The pipeline as it is CONFIGURED, before any run exists.

:mod:`ta_cascade.runview` answers "what did this run do"; this answers "what is
this workspace set up to do", which is a different question and has an answer
even when nothing has ever run.  A reader opening the board on a fresh
deployment should still see the thirteen stages and be able to check, stage by
stage, that the gate, schema, section, references and ceiling it will get are
the ones intended -- without spending a run to find out.

**The resolution comes from the daemon, and there is no disk fallback.**
:func:`ta_cascade.sessions.resolved_profiles` asks ``session.profiles``,
answered by the component that owns the inheritance rules.  Reading
``_base_<stage>.yaml`` here instead would be a second implementation of those
rules and would be wrong wherever a profile SET changes a capability, which is
exactly the case this view exists to show.  So a daemon that cannot be reached
produces an error the page states, never a plausible-looking plan.

**The stages come out in the shape :func:`ta_cascade.runview.survey` emits**,
with ``state`` set to ``PLANNED`` and the run-only fields left ``None``.  That
is deliberate: the board already has one card renderer driven by that shape, so
a configured-but-not-yet-run stage draws through the same code as a finished
one rather than through a second renderer that could disagree with it.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .runview import BANDS, _BAND_OF, _host_tool_names, capabilities

#: A stage the configuration declares and this run has not started.  The three
#: states :mod:`ta_cascade.runview` emits all mean a session existed.
PLANNED = "planned"

#: Host-tool NAMES do not depend on the run: a spec's name is a constant and
#: only its description and defaults close over the as-of date, so the plan can
#: ask for them without inventing a ticker that would read as real.
_PLACEHOLDER = ("-", "2026-01-01")


def profile_set_of(env_file: Any) -> Optional[str]:
    """``JAATO_PROFILE_SET`` as the workspace ``.env`` declares it, or ``None``.

    The workspace ``.env`` IS the session env, so this is the set the daemon
    will resolve against -- the driver's process environment is irrelevant to
    it and is deliberately not consulted here.
    """
    from pathlib import Path as _Path
    try:
        text = _Path(env_file).read_text(encoding="utf-8")
    except OSError:
        return None
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("JAATO_PROFILE_SET="):
            return line.split("=", 1)[1].strip() or None
    return None


def stages() -> List[str]:
    """The pipeline's stages, in band order.  One source: :data:`runview.BANDS`."""
    return [stage for _band, members in BANDS for stage in members]


def assemble(profiles: Dict[str, Dict[str, Any]], *,
             profile_set: Optional[str] = None) -> Dict[str, Any]:
    """The configured pipeline as drawable state.

    ``profiles`` is what :func:`ta_cascade.sessions.resolved_profiles` returned,
    keyed by profile name.  A stage the daemon did not list is reported in
    ``missing`` rather than dropped or drawn empty: a stage whose profile the
    daemon cannot see is a configuration fault worth showing, and an empty
    capability row would read as "this stage has no gate" instead.
    """
    hosts = _host_tool_names(*_PLACEHOLDER)
    out: List[Dict[str, Any]] = []
    missing: List[str] = []
    for stage in stages():
        profile = profiles.get(stage)
        if profile is None:
            missing.append(stage)
            continue
        caps = capabilities(profile)
        out.append({
            "stage": stage,
            "agent": profile.get("default_agent") or stage,
            "band": _BAND_OF.get(stage, stage),
            "session_id": None,
            "state": PLANNED,
            "started_at": None,
            "ended_at": None,
            "reason": None,
            "failed": None,
            "capabilities": caps,
            "capability_source": "daemon",
            "mode": "complete()" if caps.get("schema") else "ask()" if caps else None,
            "host_tools": list(hosts.get(stage, ())),
            "model": profile.get("model"),
            "provider": profile.get("provider"),
            "seconds": None,
            "tool_calls": None,
            "turns": None,
            "tokens": None,
        })
    return {"set": profile_set, "stages": out, "missing": missing}


def merge(planned: List[Dict[str, Any]], observed: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """The configured stages, with what a run actually did painted onto them.

    A planned stage the run reached is REPLACED by the observed one, which
    carries its state, cost and tool calls.  A stage the run has not reached
    stays planned, which is what makes a run in flight show its whole shape
    rather than only the part that has happened.

    An observed stage with no planned counterpart is appended rather than
    dropped -- the same choice :func:`runview.survey` makes, and for the same
    reason: an unplanned stage is the thing most worth seeing.  Order follows
    the plan, so a reader always finds a stage in the same place.
    """
    by_stage = {s["stage"]: s for s in observed}
    merged = [by_stage.pop(s["stage"], s) for s in planned]
    merged.extend(s for s in observed if s["stage"] in by_stage)
    return merged
