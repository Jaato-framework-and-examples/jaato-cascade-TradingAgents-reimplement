"""The run's cascade events, append-only, for a reader who was not there.

:mod:`ta_cascade.observer` renders the same events as LINES for whoever is
watching the terminal right now.  This module records them as STRUCTURED rows
instead, so the question "what was that stage doing between
``open_stage`` and the payload" can be answered after the run, by a reader
holding nothing but the results directory.

**Why a file rather than a live subscription.**  A reader could attach its own
observer to the daemon and watch a run as it happens.  That reader then holds
state no file can rebuild: nothing survives its restart, and it can say
nothing at all about a run that finished before it started — which is the
common case here, because the unit of work is a 564-cell sweep read
afterwards, not one run watched live.  Writing the events down inverts both:
every reader is stateless, re-reads the files, and sees a finished run and a
live one the same way.  It also keeps the reader off the run's critical path,
which is the property :mod:`ta_cascade.ui.api` exists to preserve.

**What is NOT recorded, and why that is the honest choice.**
``AgentOutputEvent`` carries the model's words as they are produced, and it is
the one event class this pipeline would emit in volume.  The daemon's
per-client queue is bounded — ``JAATO_IPC_EVENT_QUEUE_MAX``, default 2048 —
and past the bound "the oldest lossy chunks drop".  No event in
:mod:`jaato_sdk.events` carries a sequence number, so **a client cannot tell a
dropped chunk from a model that said nothing**: a transcript assembled from
that stream would be silently incomplete and would look complete.  So the
model's words are read from the session record the daemon itself saves
(:func:`ta_cascade.runview.session`), which is written whole, and this file
records only the four low-volume events — one per session, one per tool call —
whose loss a reader would notice because a tool call without its end is
visible as such.  The drawer therefore degrades to complete-but-delayed, never
to silently-missing.

Volume, for the record: this pipeline measured 40 tool calls across a whole
run, so a run's events file is tens of lines.  Nothing here needs a size cap,
and one is not imposed — an unexplained truncation would be the same silent
incompleteness this module exists to avoid.

Like :mod:`ta_cascade.observer`, this imports no SDK: :func:`record` takes a
duck-typed event and returns a row, which is what makes the interesting
half — which event becomes which row — testable without a daemon.
"""
from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

ARG_CHARS = 120
"""How much of one tool argument is kept.

Enough to tell two calls of the same tool apart (a ticker, a date window),
short of keeping the payload a model sent to ``signal_completion``, which can
be the whole report and is already on disk twice over — in the session record
and in the rendered section.
"""


def path_for(results_dir: Path, ticker: str, trade_date: str) -> Path:
    """Where this run's events go, beside its session log.

    Under ``results/`` rather than ``.ta_cascade/`` for the reason
    :mod:`ta_cascade.sessionlog` gives: a jaato-eval arm materialises its own
    workspace, and only what the run wrote into its results travels with
    ``--keep-workspaces``.
    """
    return Path(results_dir) / ticker / trade_date / "events.jsonl"


def short_arg(value: Any) -> str:
    text = value if isinstance(value, str) else json.dumps(value, default=str, ensure_ascii=False)
    return text if len(text) <= ARG_CHARS else text[: ARG_CHARS - 1] + "…"


def record(event: Any) -> Optional[Dict[str, Any]]:
    """One cascade event as a row, or ``None`` for an event not recorded.

    Attribution is by ``session_id`` for the reason
    :mod:`ta_cascade.observer` gives: this pipeline runs two investment
    debaters and three risk panellists concurrently under one cascade id, so
    several sessions are live at once and only ``session_id`` separates them.

    ``tool_args`` is read as a mapping and each value shortened; a tool whose
    arguments are not a mapping is recorded with none rather than guessed at,
    because an argument list this code invented would be indistinguishable
    from one the model sent.
    """
    kind = type(event).__name__
    sid = getattr(event, "session_id", "") or ""

    if kind == "AgentCreatedEvent":
        return {"kind": "session", "session_id": sid,
                "profile": getattr(event, "profile_name", "") or "",
                "agent": getattr(event, "agent_name", "") or ""}

    if kind == "ToolCallStartEvent":
        args = getattr(event, "tool_args", None)
        return {"kind": "tool_start", "session_id": sid,
                "call_id": getattr(event, "call_id", "") or "",
                "tool": getattr(event, "tool_name", "") or "?",
                "args": {k: short_arg(v) for k, v in args.items()} if isinstance(args, dict) else {}}

    if kind == "ToolCallEndEvent":
        # `success` is the call's own outcome; `is_error_result` is the result
        # being an error even though the call completed — a completion gate's
        # refusal arrives that way, and it is the single most useful thing in
        # the drawer, so the two are kept apart rather than or-ed together.
        return {"kind": "tool_end", "session_id": sid,
                "call_id": getattr(event, "call_id", "") or "",
                "tool": getattr(event, "tool_name", "") or "?",
                "success": bool(getattr(event, "success", False)),
                "error_result": bool(getattr(event, "is_error_result", False)),
                "error": (getattr(event, "error_message", None) or None),
                "seconds": getattr(event, "duration_seconds", None)}

    if kind == "SessionTerminatedEvent":
        return {"kind": "session_end", "session_id": sid,
                "reason": getattr(event, "reason", None),
                "error_type": getattr(event, "error_type", None),
                "error": getattr(event, "error_summary", None)}

    return None


def note(kind: str, **fields: Any) -> Dict[str, Any]:
    """A row the OBSERVER states about itself rather than relays.

    ``observer_detached`` is the one that matters: a silent display must never
    be mistaken for a stalled run, and the only way a reader can tell the
    difference afterwards is if the absence is written down.
    """
    return {"kind": kind, **fields}


def append(path: Path, row: Dict[str, Any]) -> None:
    """Append one row.  Never raises: a display must not fail a run.

    The same trade :mod:`ta_cascade.sessionlog` makes — losing a line of
    history is better than losing the run that produced it — and the stronger
    case here, since this file is read by a dashboard and nothing else.
    """
    line = {"at": dt.datetime.now(dt.timezone.utc).isoformat(), **row}
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(line, default=str) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
    except OSError:
        pass


def read(path: Path) -> list:
    """Every parseable row, in order; empty when there is no file.

    A torn last line is dropped and the rest kept: a driver killed mid-write
    still accounts for everything up to the kill.
    """
    p = Path(path)
    if not p.is_file():
        return []
    out = []
    for raw in p.read_text(encoding="utf-8", errors="replace").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            out.append(json.loads(raw))
        except ValueError:
            continue
    return out
