#!/usr/bin/env python3
"""Cascade driver entry point.

Originally emitted by ``jaato-scaffold new cascade --recoverable``; the
generated recipe (``IPCRecoveryClient``, ``ClientType.API``, a real
``env_file``, a 120 s connect timeout, ``complete()`` for gated stages and
``ask()`` for plain turns) now lives in ``ta_cascade/sessions.py`` and the
worklist became the pipeline in ``ta_cascade/pipeline.py``.

Preflight first:
  jaato-doctor --workspace . --env-file .env
Then, for example:
  python run_cascade.py analyze NVDA 2026-01-15 --analysts market,news
"""
from ta_cascade.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
