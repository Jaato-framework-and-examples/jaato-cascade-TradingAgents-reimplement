# CLAUDE.md — handover for agents working on this repository

This file is the working knowledge of the agent that built the repository,
written so another agent can continue without the original conversation.
Read it fully before changing anything. `README.md` is for humans;
`docs/assessment.md` is the design rationale; `docs/gaps.md` is the live
list of what is open; `docs/size-and-complexity.md` compares this tree with
the reference (regenerate with `scripts/measure_size.py`). This file is the operational layer on top of them.

---

## 1. What this repository is

A **clean reimplementation** of the TradingAgents pipeline
(TauricResearch/TradingAgents, a LangGraph multi-agent trading-analysis
framework) on the **jaato SDK**, where every pipeline node is a jaato
session driven by a Python cascade driver and market data reaches the
model as host tools.

The pipeline, per run (one ticker, one analysis date):

```
analysts in sequence  (market → sentiment → news → fundamentals; any subset)
   each: completion-gated session, host tools (except sentiment: persona prefetch)
bull ⇄ bear debate    2·max_debate_rounds turns on two long-lived sessions, ask()
research manager      completion-gated → research_plan
trader                completion-gated → trader_proposal
risk debate           aggressive → conservative → neutral, 3·max_risk_rounds turns, ask()
portfolio manager     completion-gated → portfolio_decision (rating Buy … Sell)
```

Before the analysts run, pending decisions on the same ticker from earlier
runs are scored against realised returns and a `reflector` session writes a
lesson; the portfolio manager persona receives those lessons.

**Premise that must hold: nothing is copied from TradingAgents.** Personas,
schemas, the data layer, the decision log and the report writer are written
fresh. The architecture is the paper's idea and is not protected; verbatim
code and prompts would be (Apache-2.0, attribution obligations). See
`docs/gaps.md` #8. If you need to look at the reference implementation,
clone it shallow into a scratch directory, read it, and write your own.

Rough map of what was learned about the reference (v0.4.2) is in
`docs/assessment.md` §2 and §4.7; the social-source semantics it gets right
(and that this repo mirrors) are described in §7 below.

---

## 2. Environment and commands

### Dependencies

- `jaato-sdk` (the client library) and, wherever the daemon runs,
  `jaato-server`. During development both were **editable installs from a
  sibling checkout of the jaato repository** (`pip install -e jaato-sdk/.
  -e jaato-server/.`); there is no published wheel yet. `pyproject.toml`
  declares only `jaato-sdk`.
- `pandas`, `yfinance`, `requests` for the data layer; `pytest` for tests.
- The `jaato-scaffold` and `jaato-doctor` console scripts come with those
  packages. **Run them from the same Python environment as the daemon.**

```bash
python -m venv .venv
.venv/bin/pip install -e /path/to/jaato/jaato-sdk -e /path/to/jaato/jaato-server
.venv/bin/pip install -e ".[dev]"
```

### Commands

```bash
# preflight (socket, env file, profiles, secret scrub; 0 fail expected)
jaato-doctor --workspace . --env-file .env

# validate a profile set against the installed framework — run after ANY
# change under .jaato/profiles/, completion_schemas/ or scripts/processors/
jaato-scaffold validate . --set openrouter_sonnet
jaato-scaffold validate . --set echo         # info-level "echo is a test double" lines are expected

# run (needs JAATO_PROFILE_SET and a provider credential in .env)
python -m ta_cascade analyze NVDA 2026-01-15 --analysts market,news,fundamentals
python -m ta_cascade analyze NVDA 2026-01-15 --debate-rounds 2 --risk-rounds 1 -v
python -m ta_cascade analyze BTC-USD 2026-01-15 --asset-type crypto --analysts market,sentiment
#   --no-journal / --clear-journal / --no-memory / --socket PATH / --workspace DIR
#   --display auto|board|lines   auto draws the live board on a terminal, plain lines when piped

# NOTE: two cascades on one daemon starve each other (jaato#898, docs/gaps.md).
# For a run that must not be interrupted, give it its own daemon and --socket.

# tests
.venv/bin/pytest -q tests --ignore=tests/test_pipeline_echo.py   # unit, <1 s, no daemon
.venv/bin/pytest -q tests/test_pipeline_echo.py                  # end to end, ~50-70 s, starts a private daemon
```

Exit codes of the CLI: 0 finished; 1 a node failed (journal kept, re-run
to resume); 2 daemon unreachable.

### Introspection is the source of truth for jaato

Do not read jaato source to learn what the framework offers; ask it:

```bash
jaato-scaffold explain                     # overview
jaato-scaffold explain profile             # every profile key and its inheritance rule
jaato-scaffold explain completion          # the completion-gate contract
jaato-scaffold explain prefetch            # the {{!py:...}} contract
jaato-scaffold explain plugin subagent     # tools a plugin exposes
jaato-scaffold explain provider openrouter # knobs by layer
jaato-scaffold explain archetype cascade   # what `new cascade` writes and why
jaato-scaffold new <archetype> ... --dry-run
```

The skill `jaato-sdk-client` (in the jaato repo under `.claude/skills/`)
is the condensed version of this; its three "ways a harness hangs" are all
real and all encountered or guarded against here.

---

## 3. Layout and where things live

```
ta_cascade/                the driver (Python; the only code that talks to jaato)
  config.py                RunConfig: ticker, date, analysts, rounds, workspace, socket, journal, log, auto_start
  sessions.py              open_stage(): THE one place a session is opened (IPCRecoveryClient recipe);
                           observing(): the read-only observer subscription. The only SDK importer.
  pipeline.py              run(): the graph as control flow; prompts; phases; StageFailed
  state.py                 RunState / DebateTurn; prompt-composition helpers; to_dict/from_dict
  journal.py               Journal: per-run JSON, load/save/clear (resume)
  memory.py                DecisionLog: JSONL decisions, pending → resolved, past_context(as_of=)
  data.py                  market data: yfinance, FRED, StockTwits, Reddit; deadlines; UNAVAILABLE sentences
  tools.py                 host-tool specs per analyst (closures over the run's as-of date)
  report.py                report tree under results/<ticker>/<date>/
  board.py                 BoardState: the run's progress as drawable state (pure, no renderer)
  richboard.py             the live two-panel view; the ONLY module that imports rich
  observer.py              cascade events -> trace lines; imports no SDK (testable daemon-free)
  cli.py, __main__.py      `python -m ta_cascade analyze ...`
run_cascade.py             thin entry point (scaffolded originally; delegates to cli)

.jaato/                    the workspace the daemon reads; DATA, not code
  profiles/_base_<agent>.yaml         13 provider-agnostic stage profiles (ceilings, schemas, gates)
  profiles/openrouter_sonnet/*.yaml   provider+model binding (anthropic/claude-sonnet-4.5 via OpenRouter)
  profiles/echo/*.yaml                deterministic test double set (canned payloads, no network)
  agents/<agent>.md                   13 personas (YAML frontmatter params + body with {{param}})
  instructions/00-team.md             base layer every persona sits on
  completion_schemas/*.json           5 typed payloads (analyst_report, research_plan, trader_proposal,
                                      portfolio_decision, reflection)
  scripts/processors/*.py             2 completion gates: analyst_report.py, price_fields.py
  scripts/prefetch_sentiment.py       the sentiment analyst's four-source prefetch
                                      NB: `.jaato/scripts/` is code the DAEMON runs inside the
                                      runner (bounded, `ta_cascade` must be importable there).
                                      It is not the repo's own `scripts/` at the root, below.
  logs/  sessions/  .artifact_tracker.json
                                      the FRAMEWORK's runtime state, gitignored.
                                      `.jaato/` is the daemon's config_root and holds
                                      framework assets only — never a driver product.

.ta_cascade/               the DRIVER's runtime state, gitignored
  journal/                 per-run resume journals (see RunConfig.journal_dir)

tests/                     unit tests + test_pipeline_echo.py (daemon-marked)
scripts/measure_size.py    repo tooling YOU run (never the daemon); regenerates
                           docs/size-and-complexity.md against a reference checkout
docs/assessment.md         the port assessment (moved from the jaato repo; framework paths refer to jaato)
docs/gaps.md               living gap tracker with statuses and run findings
docs/size-and-complexity.md  lines, complexity and dependencies vs the reference
.env                       gitignored; JAATO_PROFILE_SET + provider credential (+ FRED_API_KEY)
```

The 13 agents: `market_analyst`, `sentiment_analyst`, `news_analyst`,
`fundamentals_analyst`, `bull_researcher`, `bear_researcher`,
`research_manager`, `trader`, `risk_aggressive`, `risk_conservative`,
`risk_neutral`, `portfolio_manager`, `reflector`. Profile name == agent
name == the string the driver passes as both `profile=` and `agent=`.

---

## 4. How jaato is used here (the concepts you must hold)

**Transport: the daemon over IPC, never in-process.** `sessions.open_stage`
uses `IPCRecoveryClient.session(...)` with `client_type=ClientType.API`
(keeps `signal_completion` on the wire; the daemon strips it for
terminal/web/chat clients), a real `env_file` (`None` crashes the
handshake), `connect_timeout=120` (cold autostart takes 30-60 s), and
`cascade_driver_id` shared by every node of one run (they share one warm
runner slot; an observer can attach by that id). Decision rationale: the
in-process facade applies only `model/provider/plugins/plugin_configs/
completion_payload_schema/suppress_base_instructions` of a named profile and
silently ignores `completion_processors`, `max_turns`, `spawn_payload_schema`,
`budget_control` — the gates this pipeline depends on. (`docs/gaps.md` #13.)

**`complete()` vs `ask()`.** A completion-gated stage (one whose profile
declares `completion_payload_schema`) ends at `signal_completion`; a plain
turn's end is not its terminus, because the daemon re-prompts an agent that
stops in prose. So gated stages use `await s.complete(prompt)` (returns the
typed payload, `None` if the agent never signalled) and debaters use
`await s.ask(prompt)` (returns collected text). Mixing them up hangs or
returns half-finished work.

**Profiles and sets.** `_base_<agent>.yaml` holds stage determinism;
`<set>/<agent>.yaml` binds provider and model and `inherits: [_base_<agent>]`.
`JAATO_PROFILE_SET` in the workspace `.env` selects the set daemon-side (the
workspace `.env` IS the session env; the driver's process env is irrelevant
to profile resolution and secret expansion). Inheritance rules that bit or
nearly bit: `plugins` is a union (a child cannot remove), `completion_processors`
concatenate (remove only via `suppress_inherited_processors`), `max_turns`
is most-restrictive-wins, scalars are child-replaces.

**Personas and params.** `.jaato/agents/<name>.md` = YAML frontmatter
(`description`, `params: {name: {required, default, description}}`) + body
with `{{param}}` / `{{param:default}}`. `agent_params` **must all be
strings** (they cross the wire as `key=value` tokens); a
`spawn_payload_schema` property typed anything else is refused on every
spawn and the caller only sees a 60 s `SessionNotConfirmed`. Long content
(reports, transcripts) goes in the trigger prompt, not in params. Never put
a credential in a param (the rendered persona is persisted).

**Completion payloads.** The schema **is** the `signal_completion` tool's
`parameters`, so payload fields are flat at the top level. Every schema here
is strict-shaped (`additionalProperties: false`, exhaustive `required`,
nullable via `["number","null"]`) and carries `errors[]` and `warnings[]`
so an agent can say "could not answer" instead of inventing one. The driver
treats a non-empty `errors[]` as `StageFailed`.

**Completion gates** (`scripts/processors/*.py`) expose `validate(payload,
context)` returning `{errors, faults, warnings, incomplete}` and/or
`render(payload, context)` returning text written to the profile entry's
`output:` template (placeholders resolve from payload, then `agent_params`,
relative to the workspace). `errors` block the completion and are handed to
the model as instructions for the retry; `max_refusals: 2` +
`on_exhausted: allow` on every entry so the loop terminates. `context.tool_calls`
is the ledger of what the session actually called. Gates are pure functions
of the payload so `tests/test_processors.py` calls them directly. Rendered
sections go under `results/<ticker>/<date>/live/`; the driver writes the
final tree separately via `report.py`.

**Host tools** (`tools.py`) are `{name, description, parameters, handler,
auto_approve: True}` passed as `client_tools=` to `session(...)`; the facade
registers them after connect and before `create_session` (mid-session
registration is invisible to the model). `auto_approve` whitelists them with
the permission plugin so a headless run never blocks on a prompt. Handlers
run in the driver process, are wrapped in a 45 s deadline, and return
strings. They exist only while the driver is attached (a cold session woken
with no client is `DEFERRED`).

**Prefetch** (`scripts/prefetch_sentiment.py`) is the persona placeholder
`{{!py?:scripts/prefetch_sentiment.py}}` (the `?` makes failure drop the
placeholder instead of aborting session-prep). It runs **inside the runner
at session-prep**, so `ta_cascade` must be importable there, and it must be
fast: four sources are fetched concurrently under one 20 s deadline. The
session env key `TA_CASCADE_PREFETCH=off` skips it (the echo set sets it).

**The `echo` provider** is the framework's deterministic test double:
`plugin_configs.echo.tool_call` emits one canned tool call on the first
turn (used for `signal_completion` with a canned payload), `response` gives
canned text, and `usage` is **mandatory** (a turn reporting no tokens emits
no terminal event and `complete()` waits forever; `validate` flags it as
`echo_reports_no_usage`). It cannot script a multi-turn tool loop; one call
then text is all it does.

---

## 5. Decisions and why (do not relitigate without new evidence)

| Decision | Why |
|---|---|
| Driver-as-graph, not a supervisor agent with `spawn_subagent` | a model-driven parent receives a child's result as injected prose, not a typed payload; and the pipeline is a fixed deterministic DAG, which a driver expresses exactly |
| Daemon (IPC) transport, not in-process | in-process applies only part of the profile contract (§4); the daemon honours gates, ceilings, spawn validation, budgets |
| Per-profile models, not `model_tiers` | the judges are different nodes with different personas, not the same session switching tiers; tier switching also costs a cold prompt cache |
| Own decision log (`memory.py`), not the jaato `memory` plugin | the plugin is tag-based, needs a curator reactor before its hints surface, and has no "resolved on or before this date" filter; backtests need point-in-time |
| Debaters as two/three long-lived sessions driven by the driver | each side keeps its own history natively; the driver relays only the opponent's last turn; `send_to_sibling` is fire-and-forget and not for control flow |
| Stage-level journaling now; sub-stage possible later | granularity is the driver's choice; a session can `signal_completion` per sub-stage and be driven again on the same history (the completion flag resets per turn) |
| Every data failure is a sentence beginning `DATA_UNAVAILABLE` | the model reads tool output as prose; the instruction not to invent travels with the data. An **empty window** is a different sentence (`NO_DATA` / "quiet"), never confused with a failed fetch |
| Nothing after the as-of date | every data function takes `as_of` and clamps; FRED is vintage-pinned; statements filtered by period end |
| Reimplementation, no copying | licence scope and the repository's premise (§1) |

---

## 6. Traps encountered in this repository's history (all real)

1. **A prefetch that touches the network can kill the session.** The first
   end-to-end run failed at the sentiment stage: yfinance stalled inside the
   runner, `session.bootstrap` exceeded its 30 s RPC budget, and the driver
   saw `create_session: no answer within 60.0s`. Anything that runs at
   session-prep must be bounded. Hence `data.with_deadline`,
   `data.gather_with_deadline`, and the prefetch switch.
2. **`python -m server --daemon` returns before the socket is bound.** A
   client with `auto_start=False` must wait for the socket file (the test
   fixture polls for it up to 180 s).
3. **Client autostart can race a busy daemon.** With `auto_start=True` a
   client that times out its first connect attempt tries to start another
   daemon on the same socket. When something else owns the daemon (tests,
   an operator), pass `auto_start=False` (`RunConfig.auto_start`).
4. **Unix socket paths are limited to ~104 characters.** The test fixture
   picks a short temp dir for the private socket.
5. **`--stop` needs `--pid-file` and `--ipc-socket`** to find a daemon
   started with a custom pid file.
6. **Two ERROR lines per session in the daemon log are noise here:** an
   `mcp` package version traceback (`'types.UnionType' object has no
   attribute 'model_validate_json'`) and `file_edit` refusing to initialise
   without a `config_root`. Neither plugin is in any profile's `plugins:`.
7. **`jaato-scaffold new profile-set` refuses `--provider echo`** (echo is
   hidden on purpose); the echo set was written by hand (a small Python
   generator did it — see the commit that added `.jaato/profiles/echo/`).
8. **`new cascade --transport in_process` needs `--provider/--model`**;
   irrelevant now (daemon transport) but explains the scaffolded header.
9. **Reddit's JSON search endpoint is WAF-blocked for anonymous clients;
   the Atom RSS search feed works** with an identified User-Agent. A 429 is
   retried once after at most `retry_wait_cap` (5 s) — a longer backoff is
   a failed session under the prefetch deadline.
10. **StockTwits' public symbol stream serves recent messages only**, so a
    historical window is normally empty and reported as quiet. Crypto pairs
    are addressed as `<BASE>.X`.
11. **The `subagent` plugin README in jaato is stale** (documents
    `background=True` / `get_subagent_result`, which do not exist). Trust
    `jaato-scaffold explain plugin subagent`.

---

## 7. The data layer's contract (keep it)

- Every public function returns `str` and never raises; the failure path
  returns `_unavailable(...)` text. Unknown indicator names, missing
  `FRED_API_KEY`, network errors, empty frames all become sentences.
- `as_of` bounds everything; `end_date` arguments are clamped to it.
- Indicators are computed in pandas (`compute_indicators`): SMA 20/50/200,
  EMA 10, RSI 14 (Wilder), MACD 12/26/9, Bollinger 20/2, ATR 14, VWMA 20.
  `snapshot()` is the "verified numbers" block the market analyst must
  quote from.
- yfinance `info` is not point-in-time; `fundamentals()` says so in its
  text. Statements are filtered by period-end date, with a filing-lag note.
- Social: `stocktwits_messages` tallies user-applied Bullish/Bearish labels;
  `reddit_posts` reads the `wallstreetbets`, `stocks`, `investing` search
  feeds, strips Reddit's HTML body markers, and reports per-subreddit
  unavailable vs quiet. A window filter drops undated items.
- `return_after(symbol, date, holding_days)` gives `(return, resolution_date)`
  or `None` when not enough bars exist yet (a pending decision stays pending).

---

## 8. Test strategy

- **Unit** (`tests/test_*.py` except the pipeline test): config, journal,
  memory (including point-in-time), indicator maths on synthetic frames,
  tool-spec shape and as-of clamping, the two gates, the report tree, and the
  social fetchers against canned JSON/Atom via a monkeypatched `data._get`.
  No network, no daemon, under a second.
- **End to end** (`tests/test_pipeline_echo.py`, marked `daemon`): copies
  `.jaato/` to a short temp workspace, writes `.env` with
  `JAATO_PROFILE_SET=echo`, starts a daemon on a private socket and pid
  file, waits for the socket, runs the whole pipeline twice (the second run
  resolves the first run's decision through the reflector and injects the
  lesson), then a resume test with a pre-seeded journal and a spy on
  `open_stage`. `data.instrument_context` and `data.return_after` are
  monkeypatched so the driver never touches the network either. Stops the
  daemon in teardown.
- What echo cannot test: an analyst's real tool loop. That needs a live
  model (or a recorded provider trace via the profile `trace:` block) and
  has **not been run yet**.

---

## 9. State of the work and what is next

Merged on `main` (PR #1): the driver, the workspace, both profile sets,
StockTwits/Reddit ingestion, 22 unit tests and the end-to-end run.

Not done (see `docs/gaps.md` for the full table):

1. **A run against a real model.** Put `JAATO_OPENROUTER_API_KEY` in `.env`
   (`JAATO_PROFILE_SET=openrouter_sonnet` is already there), run
   `python -m ta_cascade analyze NVDA <recent date> --analysts market -v`,
   read `.jaato/logs/` and `results/`. Expect to tune `max_turns` per stage,
   possibly enable `api_params.strict_tools: true` on the OpenRouter set,
   and adjust persona wording where a model ignores the tool order.
2. **Deep model for the judges.** The OpenRouter set binds Sonnet 4.5
   everywhere with thinking enabled on `research_manager` and
   `portfolio_manager`; the assessment's intent was a stronger model for
   those two. One-line change per set profile.
3. **Sub-stage journaling** for analysts (choose → fetch → write) if a live
   run shows analyst stages failing late; the mechanism is documented in
   `docs/assessment.md` §4.8.
4. **`ToolPlugin` packaging** of `ta_cascade.data` for daemon deployments
   where tools must outlive the driver (`docs/gaps.md` #10).
5. **Backtest matrix** via `jaato-scaffold new sweep` / `jaato-eval` once
   single runs are trustworthy.
6. **jaato-side findings worth filing as issues** in the jaato repository:
   the in-process facade's partial profile contract (#13), the stale
   subagent README, the `mcp` version traceback.

---

## 10. Conventions

- **Branching:** work on a branch from `main`, push, open a draft PR; do
  not push to `main` directly. After a PR merges, restart the branch from
  the new `main` for follow-ups.
- **Validate before committing** anything under `.jaato/`:
  `jaato-scaffold validate . --set openrouter_sonnet && jaato-scaffold validate . --set echo`.
- **Run both test tiers** before a PR; the end-to-end test is slow but it is
  the only thing that exercises the real daemon contract.
- **Docstrings** on every module and public function say what the thing is
  for and which invariant it keeps (see `data.py`, `journal.py`); keep them
  accurate when you change behaviour.
- **Prompts and personas** are data under `.jaato/`; changing model-facing
  wording is a persona edit, not a driver edit. Keep `errors[]`/`warnings[]`
  semantics in every schema.
- **No module-level singletons** for run configuration; everything closes
  over `RunConfig`.
- **Update `docs/gaps.md`** when you close, open or change the status of a
  gap, and add a dated finding when a run teaches something.
- Keep the repository a reimplementation: reference the upstream design,
  never its text.
