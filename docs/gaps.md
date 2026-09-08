# Gaps and risks — living tracker

Extracted from [assessment.md §6](assessment.md#6-gaps-and-risks) so it can be
updated as the reimplementation lands. Severity is for the first cut (parity
on the `propagate()` path, daemon transport). `Status` is the only column
expected to change.

| # | Gap | Severity | Mitigation | Status |
|---|---|---|---|---|
| 1 | **No native `openai`, `azure`, `bedrock` providers in jaato.** OpenAI, xAI, DeepSeek, Qwen, GLM, MiniMax, Mistral, Kimi, Groq are reached through `openrouter`; a self-hosted or third-party OpenAI-compatible endpoint through `nim` / `vllm` with a `base_url`. Azure OpenAI and Bedrock have no route. | medium | profile sets bind `openrouter` first; Azure is a base-URL + header variant of the OpenAI-compatible base class, Bedrock a new adapter. Not needed for the first cut. | open |
| 2 | **Pipeline resume is driver code, not a framework feature.** jaato persists sessions, not pipeline position. Granularity is the driver's choice: stage-level, or finer than upstream by having one session `signal_completion` per sub-stage and be driven again on the same history (assessment §4.8). | low | `ta_cascade/journal.py`: journal per stage and per debate turn; clear on success. Sub-stage journaling (one session signalling per sub-stage) is not yet used — every analyst is one stage today. | done (stage + turn) |
| 3 | **Provider quirks the upstream client layer carried** (DeepSeek `reasoning_content` round-trip, MiniMax `reasoning_split`, content-block flattening) are per-model checks against jaato's own quirk tables. | low–medium | smoke each model a profile set names; `quirks:` is the escape hatch. | open |
| 4 | **Structured-output reliability on small models.** A model that never calls `signal_completion` burns `max_turns` and returns nothing. | medium | `on_exhausted: allow` on every processor; a stage whose payload never arrives raises `StageFailed` (the run stops and resumes from the journal) rather than inventing a `Hold`; `max_turns` set per stage; `strict_tools` still to be enabled per set after a live dry run. | in progress |
| 5 | **Per-stage session cost.** In-process a session is a `JaatoSession` construction; in daemon mode each stage claims a warm pool slot (~7 s). | low | the daemon transport is the decision (#13); a cold start is paid once per driver process and stages share one warm slot per cascade. | accepted |
| 6 | **Prompt-cache locality.** Each stage is a fresh session with its own system prompt; cross-stage reuse is nil, same as upstream. | none | — | accepted |
| 7 | **Vendor config scope.** A process-global vendor config would forbid two concurrent runs with different vendors in one process. | low | the tool factory closes over the run's `RunConfig`; no module-level singleton. | done |
| 8 | **Licence — only for what is copied.** This repository is a *reimplementation*: nothing from TradingAgents is copied verbatim, so Apache-2.0 attaches to nothing here. The architecture is an idea; the paper is cited as a courtesy. jaato's BUSL-1.1 governs redistribution of the port itself. Not legal advice. | note | keep it a reimplementation: write personas, schemas, data layer and decision log fresh. | policy |
| 9 | **`mcp` version mismatch in the dev venv** produces a harmless traceback on every `jaato-scaffold` call. | none | pin `mcp` when the daemon path is used. | open |
| 10 | **Host tools are attach-bound.** They live in the driver process; a cold session cannot use them until a client attaches (`session.wake` → `DEFERRED`). | low in-process; medium for daemon deployments | a `ToolPlugin` packaging of the data layer for daemon deployments (Phase 3). | open |
| 11 | **`echo` cannot script a multi-turn tool loop** (one call, then text). Driver-level tests cover control flow, journal and processors; the analyst loop is tested against a real model or a recorded provider trace. | low | per-stage echo profiles drive the whole pipeline end to end (`tests/test_pipeline_echo.py`); the analyst tool loop itself still needs a live model or a replay fixture. | done (control flow); the live analyst loop ran on 2026-09-08, see the live-run findings below |
| 12 | **No embedding memory in the free jaato package.** Irrelevant to parity; a future "similar past situations" feature needs a `jaato.embedding` provider or an external store surfaced through a prefetch or host tool. | none for parity | out of scope. | deferred |
| 13 | **The in-process facade honours a subset of the profile contract.** `InProcessClient` resolves a named profile to `model`, `provider`, `plugins`, `plugin_configs`, `system_instructions`, `completion_payload_schema` and `suppress_base_instructions` only (`jaato_embedded/client.py:110-142`); `completion_processors`, `max_turns`, `spawn_payload_schema` and `budget_control` are not applied, so the gates this pipeline relies on would silently not run. Found while starting the implementation; a jaato-side finding worth an issue. | medium if in-process were used | the reimplementation uses the daemon (IPC) transport, where the whole contract applies. Decision recorded in assessment §4.1. | accepted (daemon transport) |
| 14 | **Social sources.** StockTwits (public symbol stream, no key; the Jentic OpenAPI document describes it) and Reddit (subreddit Atom search feeds; the JSON endpoint is blocked for anonymous clients) are fetched by the sentiment prefetch alongside company and market news, all four concurrently under one 20 s deadline. A failed fetch reads as unavailable, an empty window as quiet — never confused. The StockTwits public stream serves recent messages only, so historical runs get the quiet sentence. | low | `data.stocktwits_messages`, `data.reddit_posts`, `data.gather_with_deadline`; fixture tests in `tests/test_social.py`. | done |

Status vocabulary: `open` (nothing done), `planned` (design settled, code pending),
`in progress`, `done` (with the commit that closed it), `accepted` (a cost we
take), `deferred` (out of scope for parity), `policy` (a rule, not work).

## Findings from the first end-to-end run (echo set, private daemon)

- **A persona prefetch that touches the network can sink the session.** The
  sentiment analyst's `{{!py?:…}}` prefetch called yfinance from inside the
  runner; the sandbox's TLS interception stalled it, `session.bootstrap`
  exceeded its 30 s RPC budget, and the driver saw a 60 s "no answer" from
  `session.new` — the same symptom as a refused spawn. Fix: the prefetch runs
  its fetches under a 15 s deadline (`data.with_deadline`), host tools get
  45 s, and the echo set sets `env: {TA_CASCADE_PREFETCH: off}` so the test
  double never reaches for the network. Rule for the future: anything that
  runs at session-prep must be bounded, because a slow prefetch is a failed
  session, not a slow one.
- **`--daemon` returns before the socket is bound.** A client that does not
  autostart must wait for the socket itself; the test fixture polls for it.
- **Two harmless daemon-side ERROR lines per session** in this environment:
  the `mcp` version traceback (#9) and `file_edit` refusing to initialise
  without a `config_root` for its backups. Neither plugin is in any profile's
  `plugins:` list, so neither affects a stage.

## Findings from the first live-model run (2026-09-08, openrouter_sonnet)

`analyze NVDA 2026-09-04 --analysts market -v` against the shared daemon on
`/tmp/jaato.sock`; Sonnet 4.5 on every stage; exit 0 in ~5 min over 9 sessions
(market analyst → bull/bear → research manager → trader → 3 risk debaters →
portfolio manager). This closes the "not run yet" half of #11.

- **The real tool loop works, and the verified-numbers contract holds across
  the whole graph.** The market analyst called three host tools and quoted
  `snapshot()`'s figures back exactly (230.36 close, SMA 220.08 / 210.57 /
  196.68, RSI 60.39, ATR 7.38). Those numbers then travelled through the
  debate, the research plan and into the trader's stop-loss (`220.08`) without
  a decimal drifting. Every completion payload arrived with `errors: []`; no
  stage exhausted `max_turns`, so no `max_turns` tuning was needed after all.
- **`warnings[]` is load-bearing, not decoration.** With only the market
  analyst selected, the research manager warned "no fundamental catalyst
  identified — purely technical, vulnerable to macro headwinds", and the
  portfolio manager carried the compressed risk/reward into its sizing advice.
  A single-analyst run reports its own thinness.
- **The driver was writing a product into the framework's config_root.**
  `RunConfig.journal_dir` defaulted to `<workspace>/.jaato/journal/`, but
  `.jaato/` is the daemon's `config_root`: `jaato-scaffold explain paths`
  assigns it profiles, agents, instructions and the framework's own `logs/`
  and `sessions/`, and nothing else. The live run made the mixing visible —
  the daemon dropped `.jaato/sessions/` and `.jaato/.artifact_tracker.json`
  next to our journal. It also matters beyond tidiness: `server/apparmor.py`
  grants a confined session write access to `.jaato/sessions/` and
  `.jaato/logs/` specifically, and jaato is tightening writes under
  `config_root` (`b034904a` denies writes to `.jaato/templates/`), so a driver
  product parked there sits in the blast radius with no grant covering it.
  Fixed: the journal defaults to `<workspace>/.ta_cascade/journal/`, and
  `tests/test_config.py` now asserts no driver path resolves under
  `config_root`. Filed jaato-side so `explain paths` states the rule.
- **`-v` was unusable as a watch mode.** It raised the *root* logger to DEBUG,
  so yfinance and its peewee cache emitted hundreds of lines per fetch and
  buried the pipeline's own output. Fixed by keeping the root at INFO and
  deepening only `ta_cascade` — an allowlist of our own namespace rather than
  a denylist of third-party logger names that would need a new entry per
  dependency.
- **Still open: transcripts double the speaker label.** `4_risk/debate.md`
  reads `Aggressive: Aggressive:` — the report writer prefixes the speaker and
  the persona also opens with its own name. Cosmetic, in the shipped report,
  not yet fixed.

## Findings from the second live run (2026-09-09, openrouter_sonnet)

A repeat of `analyze NVDA 2026-09-04 --analysts market` **failed** after the
trader with a 60 s `SessionNotConfirmed`, while an identical run an hour
earlier had succeeded. Chased to ground in `/tmp/jaato.log`; the cause is
daemon-side and filed upstream.

- **Two cascades on one daemon starve each other.** A second cascade
  (`/tmp/forge-run7`) was running. When our trader's session ended, our warm
  slot was returned into a pool already at `2/2` idle and **torn down as
  over-capacity** — 300 ms before our next stage asked for one. That stage's
  `session.new` then received *no daemon attention for 60 s*: 166 log lines
  in that window, every one of them RPC for the other cascade's client. It
  released 31 s after our client gave up.
  Two accounting defects in `server/runner_pool.py`, either sufficient alone:
  eviction's "an affine slot displaces a PURE-IDLE resident" rule only fires
  against *unaffiliated* residents, so a live cascade's slot loses to another
  cascade's idle ones; and the replenish loop's `idle_count()` counts slots
  the requesting tenant is forbidden to use (cross-cascade reuse is forbidden
  by design), so the pool reads "full" and never forks while `acquire_slot`
  returns `None`. Filed as **jaato#898**. Nothing the driver can fix.
  Mitigation available today: run on a private socket (`--socket`), as
  `tests/test_pipeline_echo.py` already does.
- **The driver cannot even choose to wait longer.** `create_session` takes a
  `timeout` (default 60 s) but `open_session` — the facade the `cascade`
  archetype mandates — has an explicit keyword signature that does not accept
  it (verified: `TypeError: open_session() got an unexpected keyword argument
  'timeout'`). The only escape is hand-rolling the connect/create dance the
  facade exists to own. Filed as **jaato#899**.
- **`.jaato/` ownership**, filed earlier the same day as **jaato#896**: the
  `explain paths` output lists what the framework writes under `config_root`
  but never states that a tenant must not write there.
- **Diagnosing the above took a daemon-log dig, which is why the board
  exists.** `-v` could not have answered "what was it doing for those 60
  seconds", because the driver was blocked inside `complete()` and had
  nothing to say. `ta_cascade/board.py` + `richboard.py` + `observer.py` draw
  the pipeline live: structure from the driver (which knows the graph),
  stage interior from the daemon's own cascade event stream (which knows
  what the model is doing). A stalled stage now shows as a row stuck at `●`
  with an empty trace beneath it.
- **Host tools DO reach a cascade observer.** Probed on the live run, because
  the reference implementation this was modelled on has runner-side tools and
  could not answer it: `get_price_history`, `get_indicators` and
  `get_verified_snapshot` — all executing in the *driver* process — arrive as
  `ToolCallStartEvent` with `tool_name` set, and `AgentCreatedEvent` carries
  `profile_name`. So the trace needs no driver-side tool instrumentation.
  Attribution is by `session_id`: this pipeline runs two investment debaters
  and three risk debaters concurrently under one cascade id.
- **Still open: transcripts double the speaker label** (`Aggressive:
  Aggressive:`), carried over from the first live run.

## Feature parity with the reference implementation

The table above tracks gaps of the *port* (framework limits, decisions).
This one tracks features the reference implementation (TradingAgents
v0.4.2) has and this repository does not yet, so the size comparison in
the assessment is read honestly: the reimplementation is smaller partly
because the framework absorbed work and partly because these are not
built. Priority is for a first production-shaped run, not for parity's
sake. Reimplement, never copy.

| # | Feature upstream | Here today | Priority | Notes |
|---|---|---|---|---|
| P1 | **Second price/fundamentals/news vendor (Alpha Vantage)** with a per-category vendor chain (`data_vendors`) and per-tool override (`tool_vendors`); typed vendor errors (rate-limited, not configured, no data) decide fall-through | yfinance only; one code path per function | medium | needs an API key; the chain semantics ("the configured list IS the chain, no silent fallback") are worth keeping when built |
| P2 | **Polymarket prediction-markets tool** (keyless public search, forward-looking filter, ranked by volume) | none | low | one function in `data.py` plus a host tool on the news analyst |
| P3 | **OHLCV file cache** with a TTL, a stale-data guard (refuse bars older than N days when the market should have traded), and a retry wrapper around yfinance | direct yfinance call under a deadline; no cache, no staleness check | medium | the staleness guard matters for correctness (a stale last bar silently mis-dates a snapshot); the cache matters for backtests over many dates |
| P4 | **Market-data validator** producing the verified snapshot from a checked window (contiguous bars, last-bar recency) | `snapshot()` computes the numbers but does not validate the window | medium | pair with P3 |
| P5 | **Point-in-time filtering of fundamentals and news** by publication/filing date, so a backtest sees only what was published by the analysis date | statements filtered by period end with a filing-lag note; `info` ratios flagged as current; news filtered by article date | medium | yfinance exposes no filing dates; a true fix needs a vendor that does (P1) |
| P6 | **Global news from configured macro search queries** (a list of query strings, a lookback and a limit) | headlines from the feeds of index/rates/commodity proxy tickers | low | ours is a proxy; upstream's is a search |
| P7 | **Interactive CLI**: questionary flow (ticker, date, analysts, depth, provider, models, thinking level, language), saved config, typed `TRADINGAGENTS_*` env overrides that fail fast on bad values | argparse only; model/provider chosen by `JAATO_PROFILE_SET` | low | jaato's TUI can attach to a running cascade for the live view; the selection flow is a small typer command when wanted |
| P8 | **Output language** setting injected into every prompt | English only | low | one `{{language}}` param on every persona plus a base-instruction line |
| P9 | **Azure OpenAI and Bedrock providers** (17 OpenAI-compatible specs, a capabilities table with per-model structured-output method, DeepSeek/MiniMax reasoning quirks) | jaato's 18 providers; OpenAI-family via OpenRouter | medium | gap #1 above |
| P10 | **Benchmark by ticker suffix** (`.T` → Nikkei, `.L` → FTSE, … else SPY) and a **decision-log rotation cap** | one benchmark symbol (`RunConfig.benchmark`); unbounded log | low | both are small additions to `memory.py` / `config.py` |
| P11 | **Test coverage** of look-ahead guards per source, symbol normalisation, vendor routing and config precedence (≈45 upstream test files are framework-free) | 22 unit tests: config, journal, memory (point-in-time), indicators, tools, gates, report, social parsing | medium | write against our own functions as each feature lands |
| P12 | **Structured-output fallback to free text** when a model cannot bind a schema, with regex rating extraction and a `REVIEW` sentinel | the daemon re-prompts an agent that ends in prose; a stage with no payload raises `StageFailed` | n/a | deliberately different: a missing decision stops the run rather than being parsed out of prose |
| P13 | **Checkpoint resume at every graph node**, opt-in | journal per stage and per debate turn | done | equivalent; see gap #2 |
| P14 | **Reddit + StockTwits ingestion** | done | done | gap #14 |
