"""One run's stages, as state a renderer can draw, read from disk alone.

The third member of the family.  :mod:`ta_cascade.board` models one run's
progress for a terminal while the driver is alive and holding it;
:mod:`ta_cascade.sweep` models a sweep of hundreds of arms; this models one
run the way a reader finds it afterwards — or mid-flight — with nothing but
its results directory and the workspace the daemon saved its sessions into.

**Disk is the truth, and the daemon is never asked.**  Everything here is
computed by reading files, so a run renders whether or not anything is still
running, the reader is never on a run's critical path, and a run that finished
last week renders exactly like the one running now.  Four sources, each
answering a different question:

* ``results/<ticker>/<date>/sessions.jsonl`` — which stages ran, in what
  order, what each cost and whether the daemon could measure it
  (:mod:`ta_cascade.sessionlog`).
* ``results/<ticker>/<date>/events.jsonl`` — what happened INSIDE a stage:
  each tool call, its outcome and its duration (:mod:`ta_cascade.eventlog`).
* ``results/<ticker>/<date>/state.json`` — the payloads the stages produced,
  and so the run's verdict.
* ``<workspace>/.jaato/sessions/<id>.json`` — the record the DAEMON saves per
  session: the full history, the persona as it was actually rendered, and the
  profile as it was actually resolved.

**The capability set decides what a card offers, and it is read, never
assumed.**  A stage shows an affordance only for an artefact it has: a
completion schema, a gate, a rendered section, references, host tools.  Those
are properties of the resolved profile, and both sources above spell them with
the same keys — ``profile_snapshot`` in the session record uses the profile
schema's own names — so :func:`capabilities` reads either.  The record is
preferred where it exists, because it is what the session actually resolved
rather than what the tree currently declares; a stage still in flight has no
record yet, and for it the workspace's ``_base_<agent>.yaml`` answers.  That
file is the right one to read: a profile set "swaps the BINDING, never the
stage determinism", so provider and model are the only things the set adds and
none of them is a capability.

**The binding budget dimension is derived, not chosen.**  ``fraction_used`` is
a single number and a ceiling has four dimensions; the one that produced the
number is the one worth tuning, and it falls out of ``used`` over ``limits``.
On the run this module was first written against, the analysts and the
reflector bound on ``turns`` and every debater and judge on ``tool_calls``,
and nothing came within half its ceiling — which is a fact about the ceilings,
and exactly what the card is for.

**Money keeps the three states** :mod:`ta_cascade.sessionlog` defines: priced,
measured-but-unpriced, unmeasured.  A total is withheld unless every session
in it is priced, and ``measured`` is reported as a fraction, so a reader can
see how much of an aggregate to trust.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from . import eventlog

#: The pipeline's shape, as bands of stages in run order.
#:
#: This mirrors :func:`ta_cascade.pipeline.plan_of`, which is the authority on
#: the order; the two cannot be derived from one another because the plan
#: speaks in step keys (``analyst:market``) and a session log speaks in profile
#: names (``market_analyst``).  ``tests/test_runview.py`` asserts that every
#: persona under ``.jaato/agents/`` appears here exactly once, so a stage added
#: to the pipeline and not to this table fails a test rather than rendering
#: somewhere arbitrary.
BANDS: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    ("memory", ("reflector",)),
    ("analysts", ("market_analyst", "sentiment_analyst", "news_analyst", "fundamentals_analyst")),
    ("investment debate", ("bull_researcher", "bear_researcher")),
    ("judges", ("research_manager", "trader")),
    ("risk debate", ("risk_aggressive", "risk_conservative", "risk_neutral")),
    ("decision", ("portfolio_manager",)),
)

_BAND_OF = {stage: name for name, stages in BANDS for stage in stages}

RUNNING, DONE, FAILED = "running", "done", "failed"


# ----------------------------------------------------------------- capabilities

def capabilities(profile: Dict[str, Any]) -> Dict[str, Any]:
    """What one stage's resolved profile says it has.

    Takes either a session record's ``profile_snapshot`` or a parsed
    ``_base_<agent>.yaml``: the profile schema's key names are the same in
    both, which is why one reader serves.

    ``references`` is read from ``plugins``, whose entries carry their
    configuration inline (``references(preload, tools:[...])``), so the test is
    the plugin's name at the head of the entry rather than a substring that
    would also match a comment.
    """
    processors = profile.get("completion_processors") or []
    plugins = profile.get("plugins") or []
    return {
        "description": (profile.get("description") or "").strip(),
        "schema": profile.get("completion_payload_schema") or None,
        "gates": [str(p.get("script", "")).rsplit("/", 1)[-1]
                  for p in processors if isinstance(p, dict) and p.get("script")],
        "sections": [p["output"] for p in processors
                     if isinstance(p, dict) and p.get("output")],
        "references": any(str(p).split("(", 1)[0].strip() == "references" for p in plugins),
        "limits": ((profile.get("budget_control") or {}).get("limits") or {}),
    }


def declared(config_root: Path, stage: str) -> Dict[str, Any]:
    """The stage's base profile as the workspace declares it, or ``{}``.

    For a stage with no session record yet — one in flight, or one from a run
    killed before the daemon saved anything.  Needs PyYAML, which the
    ``board`` extra declares; without it this returns ``{}`` and the caller
    reports the capability set as unknown rather than as empty, because an
    empty set and an unreadable one are different facts.
    """
    path = Path(config_root) / "profiles" / f"_base_{stage}.yaml"
    if not path.is_file():
        return {}
    try:
        import yaml
    except ImportError:
        return {}
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


# ------------------------------------------------------------------- the record

def _record_path(workspace: Path, session_id: str) -> Path:
    return Path(workspace) / ".jaato" / "sessions" / f"{session_id}.json"


def _load_record(workspace: Path, session_id: str) -> Optional[Dict[str, Any]]:
    path = _record_path(workspace, session_id)
    if not session_id or not path.is_file():
        return None
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return loaded if isinstance(loaded, dict) else None


def _parts_from_record(record: Dict[str, Any]) -> List[Dict[str, Any]]:
    """The session's history as drawable parts, in the order it happened.

    One part per thing that was said or done: the prompt a turn was given, the
    model's thinking, the model's words, and each tool call with a short view
    of its arguments and its outcome.  ``ok`` is ``None`` for a call the
    record holds no response for — a call still in flight when the record was
    written, which is a third state and not a failure.
    """
    history = record.get("history") or []
    responses = {p.get("call_id"): p
                 for message in history for p in (message.get("parts") or [])
                 if p.get("type") == "function_response"}
    out: List[Dict[str, Any]] = []
    for message in history:
        for part in message.get("parts") or []:
            kind = part.get("type")
            if kind == "text" and part.get("text"):
                out.append({"kind": "prompt" if message.get("role") == "user" else "text",
                            "text": part["text"]})
            elif kind == "thought" and part.get("thought"):
                out.append({"kind": "thought", "text": part["thought"]})
            elif kind == "function_call":
                response = responses.get(part.get("id")) or {}
                result = response.get("result")
                error = None
                if isinstance(result, dict):
                    error = result.get("error") or None
                if error is None and response.get("is_error"):
                    error = str(result)[:400]
                detail = []
                if isinstance(result, dict) and error:
                    detail = [str(x)[:400] for x in
                              (result.get("processor_errors") or [result.get("message", "")])[:3] if x]
                out.append({
                    "kind": "tool", "tool": part.get("name") or "?",
                    "args": {k: eventlog.short_arg(v)
                             for k, v in (part.get("args") or {}).items()},
                    "ok": None if part.get("id") not in responses else not error,
                    "error": error, "detail": detail,
                    "untrusted": bool(response.get("untrusted")),
                })
    return out


def _parts_from_events(rows: List[Dict[str, Any]], session_id: str) -> List[Dict[str, Any]]:
    """The same, assembled from this run's events, for a session with no record.

    The daemon writes a session's record at tool calls and turn ends, so a
    stage that has called nothing yet has no record at all while it runs.
    What the events can give is the tool-call skeleton with outcomes — never
    the model's words, which this pipeline deliberately does not record (see
    :mod:`ta_cascade.eventlog`).
    """
    ends = {r.get("call_id"): r for r in rows
            if r.get("kind") == "tool_end" and r.get("session_id") == session_id}
    out: List[Dict[str, Any]] = []
    for row in rows:
        if row.get("kind") != "tool_start" or row.get("session_id") != session_id:
            continue
        end = ends.get(row.get("call_id"))
        ok = None
        if end is not None:
            ok = bool(end.get("success")) and not end.get("error_result")
        out.append({"kind": "tool", "tool": row.get("tool") or "?",
                    "args": row.get("args") or {}, "ok": ok,
                    "error": (end or {}).get("error"), "detail": [],
                    "seconds": (end or {}).get("seconds"), "untrusted": False})
    return out


def session(workspace: Path, session_id: str, events: List[Dict[str, Any]]) -> Dict[str, Any]:
    """One session for the drawer, and a plain statement of where it came from.

    ``source`` is the point: ``record`` is the daemon's own complete history,
    ``events`` is the tool-call skeleton this run wrote down while the record
    did not exist yet, and ``none`` means neither — which is a thing to show,
    not a thing to render as an empty conversation.
    """
    record = _load_record(workspace, session_id)
    if record is not None:
        return {"session_id": session_id, "source": "record",
                "parts": _parts_from_record(record),
                "end_reason": record.get("end_reason"),
                "agent_params": record.get("agent_params") or {},
                "persona": record.get("rendered_instructions") or "",
                "profile": record.get("profile_snapshot") or {},
                "turns": record.get("turn_count")}
    parts = _parts_from_events(events, session_id)
    return {"session_id": session_id, "source": "events" if parts else "none",
            "parts": parts, "end_reason": None, "agent_params": {},
            "persona": "", "profile": {}, "turns": None}


# -------------------------------------------------------------------- the survey

def _binding(budget: Dict[str, Any], turns_recorded: Optional[int] = None) -> Dict[str, Any]:
    """Which ceiling dimension produced ``fraction_used``, and every dimension.

    Reported as a list so a reader sees the headroom as well as the pinch: on
    a run whose stages all sat under half their ceilings, the headroom is the
    finding.  A dimension the daemon did not price (``usd`` on a subscription
    provider) has no ratio and is reported as unpriced rather than as zero.

    ``turns`` carries a second number, and the disagreement is the point.  To
    the ceiling a "turn" is one provider binding: measured 2026-10-25 across
    one run's ten sessions, ``budget_usage.turns`` was 1.0 for every one of
    them, and ``turn_accounting`` held a single ``{"turn": 0}`` entry listing
    all of a session's calls — while the session record's own ``turn_count``
    ran from 1 to 7.  The trader reached ``turn_count`` 7 against ``turns: 6``
    with ``budget_exhausted_reason: None``.  So this dimension cannot bound a
    model's tool loop, and a reader told only "turns 1/6" would go and tune a
    ceiling that does nothing.  Both numbers are reported, and
    ``turns_disagree`` says when they differ, because two measurements that
    disagree are a fact and picking one would be a guess.
    """
    used, limits = (budget.get("used") or {}), (budget.get("limits") or {})
    dims = []
    for name, limit in sorted(limits.items()):
        amount = used.get(name)
        ratio = None
        if isinstance(amount, (int, float)) and isinstance(limit, (int, float)) and limit:
            ratio = amount / limit
        dims.append({"name": name, "used": amount, "limit": limit, "ratio": ratio})
    priced = [d for d in dims if d["ratio"] is not None]
    binds = max(priced, key=lambda d: d["ratio"])["name"] if priced else None
    counted = (used or {}).get("turns")
    return {"dimensions": dims, "binds": binds,
            "fraction_used": budget.get("fraction_used"),
            "turns_counted": counted, "turns_recorded": turns_recorded,
            "turns_disagree": (turns_recorded is not None and counted is not None
                               and float(counted) != float(turns_recorded)),
            "next_rung": budget.get("next_rung") or {}}


def _calls(rows: List[Dict[str, Any]], session_id: str,
           host_tools: Tuple[str, ...]) -> Dict[str, Any]:
    """This session's tool calls, counted BY NAME.

    Deliberately not bucketed into a taxonomy of our own: a stage's calls are
    whatever the model actually called, and a classification table invented
    here would go stale the moment the framework adds a tool and would present
    a guess as a fact.  The one distinction that is ours to make is whether we
    registered the tool (``host``), because that is knowable from
    :mod:`ta_cascade.tools` and is the difference between the data layer
    working and the model groping for a surface it has none of.
    """
    names = Counter(r.get("tool") or "?" for r in rows
                    if r.get("kind") == "tool_start" and r.get("session_id") == session_id)
    failed = sum(1 for r in rows
                 if r.get("kind") == "tool_end" and r.get("session_id") == session_id
                 and (not r.get("success") or r.get("error_result")))
    return {"total": sum(names.values()), "failed": failed,
            "by_tool": [{"tool": name, "n": n, "host": name in host_tools}
                        for name, n in names.most_common()]}


def _money(sessions: List[Dict[str, Any]]) -> Dict[str, Any]:
    """The run's money, in the three states, never collapsed.

    A cost is summed only when every measured session priced itself; one
    unpriced session withholds the total, because a part-priced sum reads as a
    bill and is not one.
    """
    measured = [s for s in sessions if s.get("consumption")]
    costs = [((s["consumption"].get("totals") or {}).get("cost_usd")) for s in measured]
    priced = [c for c in costs if isinstance(c, (int, float))]
    return {"sessions": len(sessions), "measured": len(measured),
            "priced": len(priced),
            "cost_usd": round(sum(priced), 4) if priced and len(priced) == len(costs) else None}


def _verdict(state: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "rating": (state.get("portfolio_decision") or {}).get("rating"),
        "plan": (state.get("research_plan") or {}).get("recommendation"),
        "trade": (state.get("trader_proposal") or {}).get("action"),
        "analysts": sorted((state.get("reports") or {})),
        "investment_turns": len(state.get("investment_debate") or []),
        "risk_turns": len(state.get("risk_debate") or []),
    }


def _host_tool_names(ticker: str, trade_date: str) -> Dict[str, Tuple[str, ...]]:
    """Which host tools each stage registers, asked of the code that registers them.

    Built from :func:`ta_cascade.tools.host_tools` rather than written down, so
    a tool added to an analyst appears here without this module being touched.
    Constructing the specs is pure — they are dicts closing over a config, and
    nothing is called — so this reaches no network and needs no daemon.
    """
    from .config import RunConfig
    from .tools import host_tools
    cfg = RunConfig(ticker, trade_date)
    return {f"{key}_analyst": tuple(spec["name"] for spec in specs)
            for key, specs in host_tools(cfg).items()}


def survey(results_dir: Path, ticker: str, trade_date: str, *,
           workspace: Path, config_root: Optional[Path] = None) -> Dict[str, Any]:
    """One run as drawable state.

    ``results_dir`` is the tree the run wrote (``results/`` beside the driver,
    or an arm's kept workspace); ``workspace`` is where the daemon saved the
    session records; ``config_root`` is the ``.jaato/`` tree whose profiles
    answer for a stage that has no record yet, defaulting under the workspace.

    Stages come out in the order they STARTED, which is what happened, rather
    than in the order a plan predicted.  A stage this module has no band for
    is appended under its own name rather than dropped — the same choice
    :class:`ta_cascade.board.BoardState` makes, and for the same reason: an
    unplanned stage is the thing most worth seeing.
    """
    base = Path(results_dir) / ticker / trade_date
    config_root = Path(config_root) if config_root else Path(workspace) / ".jaato"

    lines = _read_jsonl(base / "sessions.jsonl")
    events = eventlog.read(eventlog.path_for(results_dir, ticker, trade_date))
    state = _read_json(base / "state.json")
    hosts = _host_tool_names(ticker, trade_date)

    started = [line for line in lines if line.get("event") == "started"]
    ended = {line.get("session_id"): line for line in lines if line.get("event") == "ended"}

    stages: List[Dict[str, Any]] = []
    for line in started:
        stage = line.get("stage") or "?"
        sid = line.get("session_id") or ""
        end = ended.get(sid)
        record = _load_record(workspace, sid)

        # The record is what the session resolved; the workspace profile is
        # what the tree declares now.  Prefer the first, say which was used.
        if record is not None and record.get("profile_snapshot"):
            caps, source = capabilities(record["profile_snapshot"]), "record"
        else:
            profile = declared(config_root, stage)
            caps, source = (capabilities(profile), "profile") if profile else ({}, "unknown")

        consumption = (end or {}).get("consumption") or {}
        totals = consumption.get("totals") or {}
        stages.append({
            "stage": stage,
            "agent": line.get("agent") or stage,
            "band": _BAND_OF.get(stage, stage),
            "session_id": sid,
            "state": DONE if end and not end.get("failed") else FAILED if end else RUNNING,
            "started_at": line.get("at"),
            "ended_at": (end or {}).get("at"),
            "reason": (end or {}).get("reason"),
            "failed": (end or {}).get("failed"),
            "capabilities": caps,
            "capability_source": source,
            "mode": "complete()" if caps.get("schema") else "ask()" if caps else None,
            "host_tools": list(hosts.get(stage, ())),
            "seconds": consumption.get("elapsed_seconds"),
            "tool_calls": consumption.get("tool_calls"),
            "turns": totals.get("turns"),
            "tokens": totals.get("total_tokens"),
            "cost_usd": totals.get("cost_usd"),
            "measured": bool(consumption) if end else None,
            "consumption_error": (end or {}).get("consumption_error"),
            "turns_recorded": (record or {}).get("turn_count"),
            "budget": _binding(consumption.get("budget") or {},
                               (record or {}).get("turn_count")),
            "completion": consumption.get("completion") or {},
            "calls": _calls(events, sid, hosts.get(stage, ())),
            "has_record": record is not None,
        })

    order = [name for name, _ in BANDS]
    bands = [{"name": name,
              "stages": [s for s in stages if s["band"] == name]} for name in order]
    bands += [{"name": s["band"], "stages": [s]} for s in stages
              if s["band"] not in order]

    detached = [r for r in events if r.get("kind") == "observer_detached"]
    return {
        "ticker": ticker, "trade_date": trade_date,
        "paths": {"results": str(base), "workspace": str(workspace),
                  "config_root": str(config_root)},
        "verdict": _verdict(state),
        "money": _money([ended[s] for s in ended]),
        "effort": {"seconds": round(sum(s["seconds"] or 0 for s in stages), 1),
                   "tokens": sum(s["tokens"] or 0 for s in stages),
                   "tool_calls": sum(s["tool_calls"] or 0 for s in stages)},
        "stages": stages,
        "bands": [b for b in bands if b["stages"]],
        "counts": {"planned": len(started), "done": sum(1 for s in stages if s["state"] == DONE),
                   "running": sum(1 for s in stages if s["state"] == RUNNING),
                   "failed": sum(1 for s in stages if s["state"] == FAILED)},
        # Silence is not success: an observer that never attached means the
        # events file is empty for a reason, and the page must say which.
        "observer": ("detached" if detached else "attached" if events else "no events recorded"),
        "report": str(base / "report.md") if (base / "report.md").is_file() else None,
        "chart": str(base / "chart.png") if (base / "chart.png").is_file() else None,
    }


def runs(results_dir: Path) -> List[Dict[str, str]]:
    """Every run under a results tree, newest trade date first.

    Identified by the directories the report tree writes, not by a naming
    convention: a run exists here when it wrote a session log, which is the
    one file written before any stage finishes.
    """
    root = Path(results_dir)
    if not root.is_dir():
        return []
    out = []
    for ticker_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        for date_dir in sorted((p for p in ticker_dir.iterdir() if p.is_dir()), reverse=True):
            if (date_dir / "sessions.jsonl").is_file():
                out.append({"ticker": ticker_dir.name, "trade_date": date_dir.name})
    return out


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    return eventlog.read(path)


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return loaded if isinstance(loaded, dict) else {}
