"""The events file: which event becomes which row, and what the file survives.

No daemon and no SDK: :func:`ta_cascade.eventlog.record` is duck-typed on
purpose, so the interesting half — the mapping — is testable with stand-in
classes whose only relevant property is their name, which is what both the
daemon's filter and ours compare on (jaato #821).
"""
from __future__ import annotations

import json

from ta_cascade import eventlog


class AgentCreatedEvent:
    def __init__(self):
        self.session_id, self.profile_name, self.agent_name = "s1", "trader", "trader"


class ToolCallStartEvent:
    def __init__(self, args=None):
        self.session_id, self.call_id, self.tool_name = "s1", "c1", "get_price_history"
        self.tool_args = {"symbol": "NVDA", "start_date": "2026-01-01"} if args is None else args


class ToolCallEndEvent:
    def __init__(self, success=True, is_error_result=False, error_message=None):
        self.session_id, self.call_id, self.tool_name = "s1", "c1", "signal_completion"
        self.success, self.is_error_result = success, is_error_result
        self.error_message, self.duration_seconds = error_message, 1.25


class SessionTerminatedEvent:
    def __init__(self):
        self.session_id, self.reason = "s1", "budget_exhausted"
        self.error_type, self.error_summary = None, None


class TurnProgressEvent:
    def __init__(self):
        self.session_id = "s1"


def test_each_recorded_event_becomes_its_row():
    assert eventlog.record(AgentCreatedEvent()) == {
        "kind": "session", "session_id": "s1", "profile": "trader", "agent": "trader"}

    row = eventlog.record(ToolCallStartEvent())
    assert row["kind"] == "tool_start" and row["tool"] == "get_price_history"
    assert row["args"] == {"symbol": "NVDA", "start_date": "2026-01-01"}

    row = eventlog.record(SessionTerminatedEvent())
    assert row == {"kind": "session_end", "session_id": "s1",
                   "reason": "budget_exhausted", "error_type": None, "error": None}


def test_a_call_that_completed_with_an_error_result_is_not_a_call_that_failed():
    """The two outcomes are kept apart because a gate's refusal is the second.

    A completion gate rejects a payload by returning an error RESULT from a
    call that itself succeeded.  Or-ing the two together would render the most
    useful line in the drawer — why the gate sent the model back — as a
    transport failure.
    """
    ok = eventlog.record(ToolCallEndEvent())
    assert ok["success"] is True and ok["error_result"] is False

    refused = eventlog.record(ToolCallEndEvent(success=True, is_error_result=True,
                                               error_message="'motor1' is a required property"))
    assert refused["success"] is True and refused["error_result"] is True
    assert refused["error"] == "'motor1' is a required property"
    assert refused["seconds"] == 1.25


def test_an_event_we_do_not_record_returns_none():
    assert eventlog.record(TurnProgressEvent()) is None


def test_a_long_argument_is_shortened_and_a_non_mapping_is_not_guessed_at():
    row = eventlog.record(ToolCallStartEvent(args={"report": "x" * 500}))
    assert len(row["args"]["report"]) == eventlog.ARG_CHARS
    assert row["args"]["report"].endswith("…")
    # A tool whose arguments are not a mapping gets none rather than an
    # invented list: a list this code made up would be indistinguishable from
    # one the model sent.
    assert eventlog.record(ToolCallStartEvent(args="not a mapping"))["args"] == {}


def test_rows_round_trip_and_carry_a_timestamp(tmp_path):
    path = eventlog.path_for(tmp_path, "NVDA", "2026-01-15")
    eventlog.append(path, eventlog.record(AgentCreatedEvent()))
    eventlog.append(path, eventlog.note("observer_detached", why="no daemon"))

    rows = eventlog.read(path)
    assert [r["kind"] for r in rows] == ["session", "observer_detached"]
    assert rows[1]["why"] == "no daemon"
    assert all(r["at"] for r in rows)
    assert path.parent.name == "2026-01-15" and path.name == "events.jsonl"


def test_a_torn_last_line_loses_itself_and_nothing_else(tmp_path):
    """A driver killed mid-write still accounts for everything up to the kill."""
    path = tmp_path / "events.jsonl"
    path.write_text(json.dumps({"kind": "session", "session_id": "s1"}) + "\n"
                    + '{"kind": "tool_start", "sess')
    rows = eventlog.read(path)
    assert len(rows) == 1 and rows[0]["session_id"] == "s1"


def test_reading_a_file_that_is_not_there_is_empty_not_an_error(tmp_path):
    assert eventlog.read(tmp_path / "nothing.jsonl") == []


def test_appending_where_it_cannot_write_does_not_raise(tmp_path):
    """A display must never fail a run: losing a line of history is the better trade."""
    blocker = tmp_path / "blocker"
    blocker.write_text("i am a file, not a directory")
    eventlog.append(blocker / "events.jsonl", eventlog.note("observer_attached"))
