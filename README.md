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

## Layout

```
.jaato/
  profiles/_base_<agent>.yaml       provider-agnostic stage determinism (12 agents)
  profiles/<set>/<agent>.yaml       provider + model binding, selected by JAATO_PROFILE_SET
  agents/<agent>.md                 personas ({{param}} substitution)
  completion_schemas/*.json         typed payloads (the signal_completion tool's parameters)
  scripts/processors/*.py           completion gates (validate / render)
ta_cascade/                         the driver package (pipeline, host tools, journal, memory)
run_cascade.py                      entry point (scaffolded by `jaato-scaffold new cascade`)
tests/                              echo-provider tests: zero cost, no credentials
```

## Status

Phase 0 (scaffold) and the Phase 1 skeleton are in progress; see the PR
history and `docs/gaps.md`.
