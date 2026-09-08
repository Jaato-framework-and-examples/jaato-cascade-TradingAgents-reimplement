"""ta_cascade — a TradingAgents-shaped analysis pipeline as a jaato cascade.

The package is the *driver* side of the port: it owns the run state, opens
one jaato session per pipeline node over the daemon (IPC) transport, supplies
market data as host tools, journals every stage for resume, and keeps the
decision log that feeds the next run.  Everything the model sees — personas,
completion schemas, completion gates — lives under ``.jaato/`` and is data,
not code.

Module map:

- :mod:`ta_cascade.config`   — ``RunConfig``: what to analyse, how deep, where.
- :mod:`ta_cascade.sessions` — the one place a jaato session is opened.
- :mod:`ta_cascade.data`     — the market-data layer (yfinance, FRED); no model.
- :mod:`ta_cascade.tools`    — host-tool specs over the data layer, per stage.
- :mod:`ta_cascade.state`    — ``RunState``: the fields the nodes pass along.
- :mod:`ta_cascade.journal`  — per-run resume journal.
- :mod:`ta_cascade.memory`   — the decision log and its outcome resolution.
- :mod:`ta_cascade.pipeline` — the pipeline itself.
- :mod:`ta_cascade.report`   — the report tree written at the end.
- :mod:`ta_cascade.cli`      — ``python -m ta_cascade``.
"""

__version__ = "0.1.0"
