"""The run's sessions as they happened — append-only, never cleared.

Deliberately NOT :mod:`ta_cascade.journal`.  That one exists so a failed run
can resume, and it is deleted the moment a run succeeds; a successful run
leaves no trace of how it went.  This one is the opposite: one line per
session event, kept, so a run can be accounted for afterwards — what each
stage cost, how long it took, how many tool calls it made, and whether the
daemon could measure it at all.

Three things it is shaped by:

* **Disk is the truth.**  A dashboard, a cost report or a post-mortem reads
  these lines and nothing else; no live object has to be alive for a run to
  be explicable.  A driver killed mid-run still leaves everything up to the
  kill.
* **Money is only available while the session is attached.**  The daemon
  answers ``get_diagnostics()`` for a session it still holds; once the
  context exits there is nobody to ask.  So the ``ended`` line is written
  from inside :func:`ta_cascade.sessions.open_stage`, before it lets go.
* **Unmeasured is not zero, and unpriced is neither.**  There are three
  money states and a reader must keep them apart.  *Measured and priced*:
  ``consumption.totals.cost_usd`` is a number.  *Measured and unpriced*: the
  session reports tokens and ``cost_usd`` is ``None`` — a subscription plan
  or a provider with no pricing table, where effort is known and money does
  not apply; rendering it as ``$0.00`` understates every total it joins.
  *Unmeasured*: the daemon could not be asked, the line carries
  ``consumption_error`` with the reason, and nothing is known — not even
  effort.  Aggregates should say "measured 7 of 12" and withhold a partial
  cost entirely rather than sum what they have.

It lives beside the report tree (``results/<ticker>/<date>/sessions.jsonl``)
rather than under the driver's runtime state, because that is the directory
that survives: a jaato-eval arm materialises its own workspace, and only what
the run wrote into its results travels with ``--keep-workspaces``.  The
pilot's sixty arms were lost for exactly this reason.
"""
from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path
from typing import Any

from .config import RunConfig

FILENAME = "sessions.jsonl"


def path_for(cfg: RunConfig) -> Path:
    """Where this run's session lines live."""
    return Path(cfg.results_dir) / cfg.ticker / cfg.trade_date / FILENAME


def write(cfg: RunConfig, event: str, session_id: str, **fields: Any) -> None:
    """Append one line.  Never raises: accounting must not fail a run.

    A failure here loses a line of history, which is a worse trade than
    losing the run that produced it.
    """
    line = {"at": dt.datetime.now(dt.timezone.utc).isoformat(), "event": event,
            "session_id": session_id, "ticker": cfg.ticker, "trade_date": cfg.trade_date, **fields}
    try:
        p = path_for(cfg)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(line, default=str) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
    except OSError:
        pass


def read(cfg: RunConfig) -> list:
    """Every line for this run, in order; empty when there is no log."""
    p = path_for(cfg)
    if not p.is_file():
        return []
    out = []
    for raw in p.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            out.append(json.loads(raw))
        except ValueError:
            continue          # a torn last line after a kill: the rest still reads
    return out
