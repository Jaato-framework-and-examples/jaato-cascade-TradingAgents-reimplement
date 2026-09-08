"""The event->line half, against duck-typed events — no daemon involved.

The shapes asserted here are the ones the live probe of 2026-09-08 observed
on this pipeline's own cascade stream, not guesses: ``AgentCreatedEvent``
carrying ``session_id`` and ``profile_name``, and ``ToolCallStartEvent``
carrying ``tool_name`` for HOST tools that execute in the driver process.
"""
from types import SimpleNamespace

from ta_cascade.observer import OBSERVED_EVENT_TYPES, StageObserver


def _ev(kind, **kw):
    """A duck-typed event: the observer keys on type(event).__name__."""
    return type(kind, (SimpleNamespace,), {})(**kw)


def test_subscription_uses_class_names_not_wire_values():
    """A filter entry that is an EventType VALUE ('agent.created') registers
    successfully and then yields nothing, silently, forever."""
    assert all(n.endswith("Event") and "." not in n for n in OBSERVED_EVENT_TYPES)


def test_attribution_is_learned_from_the_stream():
    obs = StageObserver()
    obs.render(_ev("AgentCreatedEvent", session_id="s1", profile_name="market_analyst"))
    lines = obs.render(_ev("ToolCallStartEvent", session_id="s1", tool_name="get_indicators"))
    assert lines == ["   · market_analyst -> get_indicators"]


def test_concurrent_sessions_are_told_apart_by_session_id():
    """This pipeline runs three risk debaters at once under one cascade id,
    so several sessions are live together and only session_id separates
    them."""
    obs = StageObserver()
    for sid, prof in (("s1", "risk_aggressive"), ("s2", "risk_conservative"),
                      ("s3", "risk_neutral")):
        obs.render(_ev("AgentCreatedEvent", session_id=sid, profile_name=prof))
    got = [obs.render(_ev("ToolCallStartEvent", session_id=s, tool_name="signal_completion"))[0]
           for s in ("s3", "s1", "s2")]
    assert [g.split(" -> ")[0].strip(" ·") for g in got] == \
        ["risk_neutral", "risk_aggressive", "risk_conservative"]


def test_an_unannounced_session_renders_rather_than_disappearing():
    """Attaching mid-run leaves earlier stages unannounced.  An unattributed
    line is still evidence; dropping it would hide a session running under
    this run's id that the driver did not open."""
    obs = StageObserver()
    assert obs.render(_ev("ToolCallStartEvent", session_id="ghost",
                          tool_name="get_price_history")) == \
        ["   · ? -> get_price_history"]


def test_signal_completion_is_rendered_like_any_other_tool():
    """A gate can REJECT a payload and re-prompt (max_refusals: 2).  Showing
    every attempt is how a rejected completion becomes visible instead of
    being inferred from a silent gap."""
    obs = StageObserver()
    obs.render(_ev("AgentCreatedEvent", session_id="s", profile_name="trader"))
    assert obs.render(_ev("ToolCallStartEvent", session_id="s",
                          tool_name="signal_completion")) == ["   · trader -> signal_completion"]


def test_unobserved_event_types_render_nothing():
    obs = StageObserver()
    assert obs.render(_ev("TurnCompletedEvent", session_id="s")) == []
