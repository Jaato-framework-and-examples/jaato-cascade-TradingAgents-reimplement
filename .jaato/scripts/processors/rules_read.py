"""Completion gate: the binding rules for this stage were actually read.

Selecting a reference only authorises readonly access to its path; nothing is
injected (measured 2026-10-03, docs/gaps.md).  So a stage can hold a rule in
its catalogue, be told by its persona to consult it, and still signal a
completion having never opened it — and the proposal would look exactly the
same.

``context.tool_calls`` is the paired ledger of what the session ACTUALLY did,
so the duty is checkable rather than hoped for: every catalogue entry tagged
with ``REQUIRED_TAG`` must appear as the ``path`` of a ``readFile`` call.
Which rules apply is read from the catalogue itself, so adding a rule tagged
``trader`` makes it required here with no change to this file.
"""
import json
import os
from pathlib import Path

REQUIRED_TAG = "trader"
CATALOG = ".jaato/references"
READ_TOOL = "readFile"


def _required(workspace: Path):
    """(id, resolved path) for every catalogue entry tagged REQUIRED_TAG."""
    out = []
    root = workspace / CATALOG
    if not root.is_dir():
        return out
    for entry in sorted(root.glob("*/*.json")):
        if entry.name == "bundle.json":
            continue
        try:
            d = json.loads(entry.read_text())
        except (OSError, ValueError):
            continue
        if REQUIRED_TAG not in (d.get("tags") or []) or not d.get("path"):
            continue
        out.append((d.get("id") or entry.stem,
                    os.path.normpath(str((entry.parent / d["path"]).resolve()))))
    return out


def _read_paths(tool_calls, workspace: Path):
    """Every path this session passed to readFile, absolute and normalised."""
    paths = []
    for call in tool_calls or []:
        if call.get("name") != READ_TOOL:
            continue
        raw = str((call.get("args") or {}).get("path", ""))
        if not raw:
            continue
        p = Path(raw)
        paths.append(os.path.normpath(str(p if p.is_absolute() else (workspace / p).resolve())))
    return paths


def validate(payload, context):
    if payload.get("errors"):
        return {"errors": [], "faults": [], "warnings": [], "incomplete": []}
    workspace = Path(context.workspace_path)
    required = _required(workspace)
    if not required:
        return {"errors": [], "faults": [], "warnings": [], "incomplete": []}
    read = set(_read_paths(context.tool_calls, workspace))
    missing = [rid for rid, path in required if path not in read]
    if missing:
        names = ", ".join(sorted(missing))
        return {"errors": [f"these binding rules were not read: {names}. Call listReferences for the "
                           f"rules tagged {REQUIRED_TAG!r}, selectReferences to authorise them, then "
                           f"readFile each path before signalling. A rule you did not read still "
                           f"applies to your proposal."],
                "faults": [], "warnings": [], "incomplete": []}
    return {"errors": [], "faults": [], "warnings": [], "incomplete": []}
