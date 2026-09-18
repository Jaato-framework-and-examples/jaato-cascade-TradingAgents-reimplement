"""The jaato-eval driver contract, read from the environment.

When jaato-eval runs this driver as an ARM (``harness.kind: driver``, jaato
#1110 / #1112) it does not call it with flags: it hands the arm over as
environment, versioned by name so a driver can refuse a table it does not
understand rather than guess at one::

    JAATO_EVAL_CONTRACT     "1" — the version of this table
    JAATO_EVAL_WORKSPACE    the materialised fixture; its .env carries JAATO_PROFILE_SET
    JAATO_EVAL_CONFIG_ROOT  the task's read-only .jaato/, OUTSIDE the workspace
    JAATO_EVAL_CASCADE_ID   the arm's cascade id — every session opens stamped with it
    JAATO_EVAL_SOCKET       the daemon; absent means the SDK's default
    JAATO_EVAL_PYTHON       the interpreter jaato-eval runs under (has jaato_sdk)
    JAATO_EVAL_PARAM_<KEY>  one per input.params entry — the cell's inputs

Three of those change how this driver runs.  The cascade id: the engine's
observer, the per-stage session records and any task pool all key on it, so
the run must use the id it was given rather than mint one.  The config
root: the daemon resolves profiles, personas and schemas there, and under
the contract it is not ``<workspace>/.jaato``.  The socket.
:func:`from_environment` reads them once; :mod:`ta_cascade.cli` applies them
and maps "the daemon could not be reached" to :data:`EX_TEMPFAIL`, the exit
code the contract reserves for *the environment, not the run* (BLOCKED),
where outside the contract the same failure exits 2.

Outside the contract — no ``JAATO_EVAL_CONTRACT`` in the environment —
nothing here applies and the CLI behaves exactly as before.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Mapping, Optional

#: Contract versions this driver understands.  A version it does not know
#: is refused (:class:`UnknownContract`), never read on a best guess.
CONTRACT_VERSIONS = ("1",)

#: ``sysexits.h``'s temporary-failure code: what a driver exits under the
#: contract to say "the environment, not the run" — the engine records the
#: arm BLOCKED rather than grading a tree nothing produced.
EX_TEMPFAIL = 75

PARAM_PREFIX = "JAATO_EVAL_PARAM_"


class UnknownContract(RuntimeError):
    """``JAATO_EVAL_CONTRACT`` names a version this driver does not know, or
    a variable the version requires is missing."""


@dataclass(frozen=True)
class Contract:
    """The arm, as jaato-eval handed it over."""

    version: str
    workspace: Path
    config_root: Path
    cascade_id: str
    socket: Optional[str]


def from_environment(env: Mapping[str, str] = os.environ) -> Optional[Contract]:
    """The contract in ``env``, or ``None`` when the driver is not under one.

    Raises:
        UnknownContract: the version is not in :data:`CONTRACT_VERSIONS`, or
            a required variable is absent.  The caller exits
            :data:`EX_TEMPFAIL`: a driver that half-understands its contract
            must not run under it.
    """
    version = env.get("JAATO_EVAL_CONTRACT")
    if version is None:
        return None
    if version not in CONTRACT_VERSIONS:
        raise UnknownContract(
            f"JAATO_EVAL_CONTRACT={version!r}; this driver understands {CONTRACT_VERSIONS}")
    missing = [k for k in ("JAATO_EVAL_WORKSPACE", "JAATO_EVAL_CONFIG_ROOT", "JAATO_EVAL_CASCADE_ID")
               if not env.get(k)]
    if missing:
        raise UnknownContract(f"contract {version} without {', '.join(missing)}")
    return Contract(
        version=version,
        workspace=Path(env["JAATO_EVAL_WORKSPACE"]),
        config_root=Path(env["JAATO_EVAL_CONFIG_ROOT"]),
        cascade_id=env["JAATO_EVAL_CASCADE_ID"],
        socket=env.get("JAATO_EVAL_SOCKET") or None,
    )


def params(env: Mapping[str, str] = os.environ) -> Dict[str, str]:
    """``input.params`` as the contract exported them: ``{KEY: value}``.

    The engine exports each key upper-cased with non-identifier characters
    replaced by ``_`` (``jaato_eval.params.env_name``); the driver and its
    scorer read the same variables, which is the point of the export.
    """
    return {k[len(PARAM_PREFIX):]: v for k, v in env.items() if k.startswith(PARAM_PREFIX)}
