"""Conformance check of the rule `stop-placement`.

Reads one run's cell — ``results/<TICKER>/<DATE>/state.json`` — and decides
whether the trader's proposal places its stop the way the rule requires.  It
attests conformance of a proposal to the rule.  It does not and cannot
attest that the rule is any good: the same hand wrote both, so no blind
answer key stands behind it (see the reference's ``origin`` note).

The numbers come from the run's own captured evidence
(``state.evidence.snapshots``), never from the network and never from the
report's prose.  A run made before the driver captured evidence reports
``cannot_verify`` rather than recomputing: a check that reaches for live data
would answer differently on different days and stop being a check.

Run:
    python3 check.py <cell_dir>

Python 3.11+, standard library only. Reads files; never writes, runs or
connects.  One JSON object on stdout, exit code 0:

    {"rule": "stop-placement", "cell": "<TICKER>/<DATE>", "status": "<status>",
     "evidence": [{"field": "<what was read>", "value": <v>, "note": "<what was seen>"}],
     "violations": ["<rule n>: <what is wrong>"]}

status:
    compliant      every applicable clause holds
    non_compliant  at least one clause is broken
    not_applicable the proposal carries neither an entry nor a stop
    cannot_verify  the cell lacks what the rule is measured against
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

RULE = "stop-placement"
DIRECTION = {"Buy": 1, "Sell": -1, "Hold": 0}


def _out(cell, status, evidence, violations):
    print(json.dumps({"rule": RULE, "cell": cell, "status": status,
                      "evidence": evidence, "violations": violations}))
    return 0


def check(cell_dir: Path) -> int:
    state_path = cell_dir / "state.json"
    cell = "/".join(cell_dir.resolve().parts[-2:])
    try:
        state = json.loads(state_path.read_text())
    except (OSError, ValueError) as exc:
        return _out(cell, "cannot_verify", [], [f"no readable state at {state_path}: {exc}"])

    proposal = state.get("trader_proposal") or {}
    action = proposal.get("action")
    entry = proposal.get("entry_price")
    stop = proposal.get("stop_loss")
    evidence = [{"field": "trader_proposal.action", "value": action, "note": "the proposal's action"},
                {"field": "trader_proposal.entry_price", "value": entry, "note": "entry as proposed"},
                {"field": "trader_proposal.stop_loss", "value": stop, "note": "stop as proposed"}]
    violations = []

    # Rule 1 — a stop belongs to a position.
    if stop is not None and (entry is None or action == "Hold"):
        violations.append("rule 1: a stop is stated with no position to abandon "
                          f"(action {action!r}, entry {entry!r})")
        return _out(cell, "non_compliant", evidence, violations)

    if stop is None and entry is None:
        return _out(cell, "not_applicable", evidence, [])
    if stop is None:
        return _out(cell, "compliant", evidence, [])

    direction = DIRECTION.get(action)
    if direction is None:
        return _out(cell, "cannot_verify", evidence,
                    [f"action {action!r} is outside the vocabulary {sorted(DIRECTION)}"])
    if direction == 0:
        return _out(cell, "compliant", evidence, [])

    # Rule 2 — the stop sits where the thesis is invalidated.
    if (direction > 0 and stop >= entry) or (direction < 0 and stop <= entry):
        side = "below" if direction > 0 else "above"
        violations.append(f"rule 2: a {action} is invalidated {side} entry, "
                          f"but the stop ({stop}) is on the other side of {entry}")

    # Rule 3 — at least one ATR away, from the run's own captured snapshot.
    snapshots = (state.get("evidence") or {}).get("snapshots") or []
    atr = next((s.get("atr_14") for s in reversed(snapshots)
                if s.get("symbol") == state.get("ticker") and s.get("atr_14") is not None), None)
    if atr is None:
        evidence.append({"field": "evidence.snapshots", "value": len(snapshots),
                         "note": "no captured snapshot carries atr_14 for this ticker"})
        return _out(cell, "cannot_verify", evidence,
                    violations + ["rule 3: not measurable — the run captured no verified snapshot"])

    distance = abs(float(entry) - float(stop))
    evidence.append({"field": "evidence.snapshots[].atr_14", "value": atr,
                     "note": f"stop stands {distance:.4f} from entry"})
    if distance < atr:
        violations.append(f"rule 3: the stop stands {distance:.4f} from entry, "
                          f"inside one ATR(14) of {atr}")

    return _out(cell, "non_compliant" if violations else "compliant", evidence, violations)


def main(argv=None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print(json.dumps({"rule": RULE, "cell": None, "status": "cannot_verify", "evidence": [],
                          "violations": ["usage: check.py <cell_dir>"]}))
        return 0
    return check(Path(args[0]))


if __name__ == "__main__":
    sys.exit(main())
