"""Per-run resume journal.

jaato persists *sessions*; where a run is in its pipeline is the driver's to
remember.  The journal is one JSON file per run key holding the ``RunState``
as it stood after the last completed unit of work (a stage, a debate turn).
On restart the pipeline loads it and skips what is already there; on a
clean finish it is deleted, so a re-run of the same ticker and date starts
fresh — the same lifecycle as an opt-in checkpoint.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from .state import RunState


class Journal:
    """Load, save and clear the journal for one run key.

    A ``Journal`` with ``directory=None`` is a no-op (journaling disabled):
    ``load`` returns ``None`` and ``save`` / ``clear`` do nothing, so the
    pipeline never needs to branch on whether journaling is on.
    """

    def __init__(self, directory: Optional[Path], run_key: str):
        self._path = (Path(directory) / f"{run_key}.json") if directory else None

    @property
    def path(self) -> Optional[Path]:
        return self._path

    def load(self) -> Optional[RunState]:
        if self._path is None or not self._path.exists():
            return None
        with self._path.open("r", encoding="utf-8") as fh:
            return RunState.from_dict(json.load(fh))

    def save(self, state: RunState) -> None:
        if self._path is None:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".json.tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump(state.to_dict(), fh, indent=1, sort_keys=True)
        tmp.replace(self._path)

    def clear(self) -> None:
        if self._path is not None and self._path.exists():
            self._path.unlink()
