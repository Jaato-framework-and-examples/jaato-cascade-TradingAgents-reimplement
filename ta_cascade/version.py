"""What revision this process is running, and what the checkout says now.

A deployment that has drifted from its pin looks identical to one that has
not, until something breaks.  This answers the question a dashboard tile asks
-- "which commit is this?" -- in the one way that cannot quietly lie.

**Two revisions, not one.**  ``loaded`` is read ONCE, when this module is
first imported, so it describes the checkout as it stood when this process
started: that is what the process imported and is still serving.  ``checkout``
is read per call, so it describes the tree right now.  They differ exactly
when someone has pulled or edited under a running server, and ``drifted`` says
so.

Reporting only the second -- the obvious implementation, and the one a reader
expects -- would be worse than reporting nothing in the case that matters
most.  A server left running across a pull would answer with the NEW pin while
serving the OLD code, which is the failure this exists to catch, stated
backwards and with more confidence.  That case is real: it cost the operator
of this repository's VPS1 deployment a hunt for a route that was present in
the file and absent from the process.

**Absence is reported, never guessed.**  No git, no checkout, a tarball
deployment: each yields ``None`` and a ``reason``, because "I cannot tell"
and "there are no uncommitted changes" are different answers and only one of
them is safe to act on.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Dict, Optional

#: The repository this package was imported from.  ``parents[1]`` is the tree
#: root beside ``ta_cascade/``; a wheel install has no ``.git`` there and says
#: so rather than walking upward into somebody else's repository.
ROOT = Path(__file__).resolve().parents[1]

_GIT_TIMEOUT_S = 5.0


def _git(*args: str, root: Path = ROOT) -> Optional[str]:
    """One git command's first line, or ``None`` when git cannot answer.

    Every failure mode collapses to ``None`` deliberately -- git absent, the
    path not a repository, a timeout -- because the caller's next move is the
    same for all of them: say it could not tell.  The distinction a caller
    DOES need, between "could not tell" and "clean", is kept by the caller.
    """
    try:
        out = subprocess.run(["git", "-C", str(root), *args],
                             capture_output=True, text=True, timeout=_GIT_TIMEOUT_S)
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    first = out.stdout.strip().splitlines()
    return first[0].strip() if first and first[0].strip() else None


def _revision(root: Path = ROOT) -> Dict[str, Any]:
    """The checkout's description, or ``None`` fields and a reason.

    ``describe --tags --always --dirty`` is one call that answers the pin, the
    commit and the dirty flag together, so the three cannot disagree with each
    other the way three separate calls could.
    """
    described = _git("describe", "--tags", "--always", "--dirty", root=root)
    if described is None:
        return {"pin": None, "commit": None, "branch": None, "dirty": None,
                "reason": f"no git answer for {root} (not a checkout, or git is absent)"}
    return {
        "pin": described,
        "commit": _git("rev-parse", "--short", "HEAD", root=root),
        "branch": _git("rev-parse", "--abbrev-ref", "HEAD", root=root),
        # A string ending in `-dirty` is git's own statement that tracked files
        # have uncommitted changes, so the flag is READ from it rather than
        # computed by a second command that could disagree.
        "dirty": described.endswith("-dirty"),
        "reason": None,
    }


#: Captured at import: the checkout as it stood when this process started.
#: Not a hash of the bytes actually loaded -- nothing cheap is -- but it is
#: the revision this process imported, which is the question being asked.
LOADED: Dict[str, Any] = _revision()


def sdk_version() -> Dict[str, Any]:
    """The installed jaato-sdk, or ``None`` with the reason.

    A board-only deployment installs starlette, uvicorn and PyYAML and no SDK
    at all, which is supported: runs render from disk without it.  So an
    absent SDK is a fact to report, not a failure.
    """
    try:
        import importlib.metadata as md
        return {"version": md.version("jaato-sdk"), "reason": None}
    except Exception as exc:                      # PackageNotFoundError and friends
        return {"version": None, "reason": f"{type(exc).__name__}: {exc}"}


def report(root: Path = ROOT) -> Dict[str, Any]:
    """What this process is running, what the tree says now, and whether they differ.

    ``drifted`` is ``None`` when either side could not be read: a comparison
    with an unknown is unknown, and answering ``False`` there would assert the
    one thing this module exists to avoid asserting.
    """
    now = _revision(root)
    loaded, current = LOADED.get("commit"), now.get("commit")
    drifted = None if (loaded is None or current is None) else (loaded != current)
    return {
        "loaded": {k: LOADED[k] for k in ("pin", "commit", "branch", "dirty", "reason")},
        "checkout": now,
        "drifted": drifted,
        "sdk": sdk_version(),
    }
