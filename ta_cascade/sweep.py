"""A sweep's progress, as state a renderer can draw.

The sibling of :mod:`ta_cascade.board`, for the other unit of work.  That one
models ONE run's stages; this models a jaato-eval sweep of hundreds of arms,
each its own cascade in its own workspace.  Pure, and separate from any
renderer, for the same reason: whether the picture tells the truth is decided
here and decided without a browser.

**Disk is the truth.**  Everything below is computed by reading files, so a
sweep renders whether or not anything is still running, the dashboard is never
on a run's critical path, and a driver killed mid-arm still accounts for what
it did.  Three sources, each answering a different question:

* ``tasks/`` — the denominator.  Every cell that was planned.
* ``results.jsonl`` — what jaato-eval finished, one line per arm, with its
  verdict, duration, turns and ``usage.cost_usd``.
* the arm workspaces — what is happening NOW.  Each carries our own
  ``results/<ticker>/<date>/sessions.jsonl``, whose last line says which stage
  is open.  Needs ``--keep-workspaces``; without it an arm's workspace is
  removed when it finishes and only the finished view survives.

Workspace directories are not parsed for names: every session line carries its
own ``ticker`` and ``trade_date``, so a cell is identified by what the run
wrote rather than by a naming convention that may change.

**Money follows the same three states as a single run** (see
:mod:`ta_cascade.sessionlog`): priced, measured-but-unpriced, unmeasured.  A
total is withheld entirely unless every arm in it is priced — a half-priced sum
reads as a bill and is not one — and ``measured`` is always reported as a
fraction so a reader can see how much of an aggregate to trust.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

#: An arm that finished carries one of these from jaato-eval.
FINISHED = ("PASS", "FAIL", "BLOCKED", "ERROR")
PENDING, RUNNING = "pending", "running"


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    """Every parseable line; a torn last line is dropped, the rest kept."""
    if not path.is_file():
        return []
    out = []
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            out.append(json.loads(raw))
        except ValueError:
            continue
    return out


def planned(tasks_dir: Path) -> List[Dict[str, str]]:
    """Every cell the matrix declares, from the task directory names."""
    cells = []
    for d in sorted(p for p in Path(tasks_dir).glob("*") if p.is_dir()):
        ticker, _, date = d.name.partition("-")
        if ticker and date:
            cells.append({"cell": f"{ticker}/{date}", "ticker": ticker, "date": date})
    return cells


def _arms(results_path: Path) -> List[Dict[str, Any]]:
    """Every finished ARM, in file order.

    One line per arm, not per cell: a sweep with ``repeats: 5`` writes five
    lines for one cell, and money and effort are properties of arms.  Keying
    this by cell quietly dropped four fifths of the pilot's spend — it reported
    $9.16 against a real $51 — because only the last arm of each cell survived.
    Cell STATE is a different question and is folded separately, below.
    """
    arms = []
    for row in _read_jsonl(Path(results_path)):
        task = str(row.get("task_id") or "")
        parts = task.split("/")
        if len(parts) < 2:
            continue
        usage = row.get("usage") or {}
        arms.append({
            "cell": f"{parts[-2]}/{parts[-1]}",
            "arm_id": row.get("arm_id"),
            "repeat": row.get("repeat"),
            "state": row.get("state") or "ERROR",
            "seconds": row.get("duration_seconds"),
            "turns": row.get("turns"),
            "cost_usd": usage.get("cost_usd"),
            "error": row.get("error"),
            "blocked_reason": row.get("blocked_reason"),
            "verdicts": row.get("verdicts") or [],
            "sessions": len(row.get("session_ids") or []),
        })
    return arms


def _fold_cells(arms: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """A cell's state from its arms: the last one decides, and the count is kept.

    Last-write-wins because ``--resume`` re-runs an arm that failed, and the
    re-run is the answer.  ``arms`` on the row says how many stand behind it, so
    a repeats sweep does not look like a single-arm one.
    """
    out: Dict[str, Dict[str, Any]] = {}
    for a in arms:
        row = dict(a)
        row["arms"] = out.get(a["cell"], {}).get("arms", 0) + 1
        out[a["cell"]] = row
    return out


def _in_flight(workspaces_dir: Optional[Path]) -> Dict[str, Dict[str, Any]]:
    """Cells with an open session right now, and the stage they are in.

    Read from each arm's own session log rather than from workspace names: the
    lines carry their ticker and date, so this survives a change in how
    jaato-eval names a materialised workspace.
    """
    out: Dict[str, Dict[str, Any]] = {}
    if not workspaces_dir or not Path(workspaces_dir).is_dir():
        return out
    for log in Path(workspaces_dir).glob("*/results/*/*/sessions.jsonl"):
        lines = _read_jsonl(log)
        if not lines:
            continue
        last = lines[-1]
        cell = f"{last.get('ticker')}/{last.get('trade_date')}"
        started = sum(1 for l in lines if l.get("event") == "started")
        ended = sum(1 for l in lines if l.get("event") == "ended")
        out[cell] = {"stage": last.get("stage"), "open": last.get("event") == "started",
                     "stages_started": started, "stages_ended": ended}
    return out


def _money(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Cost over a set of arms, withholding a partial total.

    ``cost_usd`` is ``None`` unless EVERY arm here is priced.  A subscription
    provider reports effort and no money, so summing what happens to be priced
    would understate the bill and look authoritative doing it.
    """
    priced = [r["cost_usd"] for r in rows if r.get("cost_usd") is not None]
    return {"arms": len(rows), "priced": len(priced),
            "cost_usd": sum(priced) if rows and len(priced) == len(rows) else None}


def survey(tasks_dir, results_path, workspaces_dir=None) -> Dict[str, Any]:
    """The whole sweep: every cell, its state, and what it cost."""
    cells = planned(tasks_dir)
    arms = _arms(Path(results_path))
    done = _fold_cells(arms)
    live = _in_flight(Path(workspaces_dir) if workspaces_dir else None)

    rows = []
    for c in cells:
        key = c["cell"]
        row = dict(c)
        if key in done:
            row.update(done[key])
        elif key in live and live[key]["open"]:
            row.update(state=RUNNING, **{k: v for k, v in live[key].items() if k != "open"})
        else:
            row["state"] = PENDING
        rows.append(row)

    counts: Dict[str, int] = {}
    for r in rows:
        counts[r["state"]] = counts.get(r["state"], 0) + 1

    settled = [r for r in rows if r["state"] in FINISHED]
    graded = [r for r in rows if r["state"] in ("PASS", "FAIL")]
    # money and effort are per ARM; states are per cell
    spent = [a for a in arms if a["state"] in FINISHED]
    return {
        "cells": rows,
        "counts": counts,
        "total": len(rows),
        "settled": len(settled),
        "progress": (len(settled) / len(rows)) if rows else 0.0,
        "money": _money(spent),
        "effort": {
            "seconds": sum(a.get("seconds") or 0 for a in spent),
            "turns": sum(a.get("turns") or 0 for a in spent),
            "sessions": sum(a.get("sessions") or 0 for a in spent),
        },
        # The experiment's own arithmetic, not a verdict on it: the
        # pre-registration decides what any of this means.
        "graded": {"pass": sum(r["state"] == "PASS" for r in graded),
                   "fail": sum(r["state"] == "FAIL" for r in graded),
                   "of": len(graded)},
    }
