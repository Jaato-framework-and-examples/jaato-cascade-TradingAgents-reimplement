# jaato-cascade-TradingAgents-reimplement

A clean reimplementation of the [TradingAgents](https://github.com/TauricResearch/TradingAgents)
multi-agent trading-analysis pipeline on the [jaato](https://github.com/Jaato-framework-and-examples/jaato)
SDK: four analysts in sequence, a bull/bear debate, a research manager, a
trader, a three-way risk debate, and a portfolio manager, each a jaato session
driven by a cascade driver, with market data supplied as host tools.

Nothing here is copied from TradingAgents. The pipeline shape follows the
paper (Xiao et al., 2024); personas, schemas, the data layer and the decision
log are written fresh. See [docs/gaps.md](docs/gaps.md) #8.

## Documents

- [docs/assessment.md](docs/assessment.md) — the port assessment: what
  TradingAgents is, which `jaato-scaffold` verb settled which decision, the
  primitive-by-primitive mapping, a worked slice, gaps, phasing.
- [docs/gaps.md](docs/gaps.md) — the living gap tracker.
- [docs/size-and-complexity.md](docs/size-and-complexity.md) — lines, complexity and
  dependencies against the reference implementation, and how to read the ratio.

## Running

```bash
python -m venv .venv && .venv/bin/pip install -e ".[dev]"     # plus jaato-server, for the daemon
jaato-doctor --workspace . --env-file .env                      # preflight
# set JAATO_PROFILE_SET and the provider credential in .env, then:
python -m ta_cascade analyze NVDA 2026-01-15 --analysts market,news,fundamentals
```

The driver talks to a jaato daemon over IPC (autostarted on first use; a
cold start takes 30–60 s). Each pipeline node is a session named by a
profile in `.jaato/profiles/<set>/`; the set is selected by
`JAATO_PROFILE_SET` in the workspace `.env`. Two sets ship: `openrouter_sonnet`
(real models) and `echo` (the framework's deterministic test double — zero
cost, no credentials; what the tests run on).

On a terminal the run draws itself: a diagram of the pipeline filling in as
it goes, with the debates showing who holds the floor, over a trace of what
each stage is doing inside (`--display lines` for plain output; piping picks
that automatically).

A crashed run resumes where it stopped: every stage and debate turn is
journaled under `.ta_cascade/journal/` and cleared on success (`.jaato/`
is the framework's config_root and stays framework-only). Decisions are
recorded in `~/.ta_cascade/decisions.jsonl`; the next run on the same ticker
scores them against realised returns, has a reflector agent write a lesson,
and hands the lessons to the portfolio manager.

## Tests

```bash
.venv/bin/pytest -q                       # unit tests, no daemon
.venv/bin/pytest -q -m daemon             # end to end over a private daemon on the echo set
```

## Layout

```
.jaato/
  profiles/_base_<agent>.yaml       provider-agnostic stage determinism (13 agents)
  profiles/<set>/<agent>.yaml       provider + model binding, selected by JAATO_PROFILE_SET
  agents/<agent>.md                 personas ({{param}} substitution, one prefetch)
  instructions/00-team.md           the base layer every persona sits on
  completion_schemas/*.json         typed payloads (the signal_completion tool's parameters)
  scripts/processors/*.py           completion gates (validate / render)
  scripts/prefetch_sentiment.py     the sentiment analyst's pre-fetch (news, StockTwits, Reddit)
ta_cascade/                         the driver: pipeline, sessions, host tools, data, journal, memory, report
run_cascade.py                      entry point (scaffolded by `jaato-scaffold new cascade --recoverable`)
tests/                              unit tests + one end-to-end run on the echo set
```
