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
| 4 | **Structured-output reliability on small models.** A model that never calls `signal_completion` burns the stage's turn ceiling and returns nothing. | medium | `on_exhausted: allow` on every processor; a stage whose payload never arrives raises `StageFailed` (the run stops and resumes from the journal) rather than inventing a `Hold`; `budget_control.limits.turns` per stage (jaato#1068 removed `max_turns`, which bounded nothing); `strict_tools` still to be enabled per set after a live dry run. | in progress |
| 5 | **Per-stage session cost.** In-process a session is a `JaatoSession` construction; in daemon mode each stage claims a warm pool slot (~7 s). | low | the daemon transport is the decision (#13); a cold start is paid once per driver process and stages share one warm slot per cascade. | accepted |
| 6 | **Prompt-cache locality.** Each stage is a fresh session with its own system prompt; cross-stage reuse is nil, same as upstream. | none | — | accepted |
| 7 | **Vendor config scope.** A process-global vendor config would forbid two concurrent runs with different vendors in one process. | low | the tool factory closes over the run's `RunConfig`; no module-level singleton. | done |
| 8 | **Licence — only for what is copied.** This repository is a *reimplementation*: nothing from TradingAgents is copied verbatim, so Apache-2.0 attaches to nothing here. The architecture is an idea; the paper is cited as a courtesy. jaato's BUSL-1.1 governs redistribution of the port itself. Not legal advice. | note | keep it a reimplementation: write personas, schemas, data layer and decision log fresh. | policy |
| 9 | **`mcp` version mismatch in the dev venv** produces a harmless traceback on every `jaato-scaffold` call. | none | pin `mcp` when the daemon path is used. | open |
| 10 | **Host tools are attach-bound.** They live in the driver process; a cold session cannot use them until a client attaches (`session.wake` → `DEFERRED`). | low in-process; medium for daemon deployments | a `ToolPlugin` packaging of the data layer for daemon deployments (Phase 3). | open |
| 11 | **`echo` cannot script a multi-turn tool loop** (one call, then text). Driver-level tests cover control flow, journal and processors; the analyst loop is tested against a real model or a recorded provider trace. | low | per-stage echo profiles drive the whole pipeline end to end (`tests/test_pipeline_echo.py`); the analyst tool loop itself still needs a live model or a replay fixture. | done (control flow); the live analyst loop ran on 2026-09-08 and the sentiment analyst's four host tools on 2026-10-17, both below |
| 12 | **No embedding memory in the free jaato package.** Irrelevant to parity; a future "similar past situations" feature needs a `jaato.embedding` provider or an external store surfaced through a prefetch or host tool. | none for parity | out of scope. | deferred |
| 13 | **The in-process facade honours a subset of the profile contract.** `InProcessClient` resolves a named profile to `model`, `provider`, `plugins`, `plugin_configs`, `system_instructions`, `completion_payload_schema` and `suppress_base_instructions` only (`jaato_embedded/client.py:110-142`); `completion_processors`, `max_turns`, `spawn_payload_schema` and `budget_control` are not applied, so the gates this pipeline relies on would silently not run. Found while starting the implementation; a jaato-side finding worth an issue. | medium if in-process were used | the reimplementation uses the daemon (IPC) transport, where the whole contract applies. Decision recorded in assessment §4.1. | accepted (daemon transport) |
| 14 | **Social sources.** StockTwits (public symbol stream, no key; the Jentic OpenAPI document describes it) and Reddit (subreddit Atom search feeds; the JSON endpoint is blocked for anonymous clients) are reached by the sentiment analyst's own host tools (`get_stocktwits_messages`, `get_reddit_posts`), alongside company and market news. A failed fetch reads as unavailable, an empty window as quiet — never confused. The StockTwits public stream serves recent messages only, so historical runs get the quiet sentence. | low | `data.stocktwits_messages`, `data.reddit_posts`, `tools.sentiment_tools`; fixture tests in `tests/test_social.py`. Fetched by a persona prefetch until 2026-10-17 — see that date below. | done |
| 15 | **No budget ceiling on any stage.** jaato-server 0.12.0's validator flags every profile `budget_control_absent`: no stage is bounded on usd, tokens, seconds, tool_calls or turns, so a tool-call loop stops only at the provider bill. `max_turns` was declared per stage and bounded nothing; jaato#1068 removed the key. | medium | `budget_control` in each `_base_<agent>` profile, sized per stage group from measured usage with roughly 4–5× headroom: analysts `tool_calls 60 / usd 1.50 / seconds 600 / turns 8`, debaters `10 / 2.00 / 600 / turns 12`, judges `30 / 1.50 / 480 / turns 6`, the reflector the same with `turns 4`; `abort` at 100%. The `turns` limits are the numbers `max_turns` carried before jaato#1068 removed that key. Limits are per session and MIN-WINS, so a set profile can tighten a ceiling but never raise it. `usd` is OpenRouter's own reported cost per call, not an estimate, and does not advance on the echo set, which reports none. The evidence is thin — dollar figures for two stages from one run — so revisit the numbers once several runs give per-stage cost. An abort fails the run as `StageFailed` naming the stage or debate turn and the daemon's reason, journal kept; before jaato#1007 a capped debater hung the run instead (see the budget-abort findings below). | done |

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
  returns `None`. Filed as **jaato#898**; nothing the driver could fix.
  **FIXED upstream the same day** (`b92fb7d0`, "a reservation is not
  capacity"): `target_size` is now a floor on *unreserved* idle slots, with a
  new `max_size` ceiling (default `2 * target_size`) bounding the growth that
  implies. Verified here after restarting the daemon on the fix — two
  cascades run concurrently on one daemon, both completed, `pool at capacity`
  now reads `4/4` instead of `2/2`, and zero `session.new` timeouts or
  acquire misses. A private socket (`--socket`) is still the way to isolate a
  run that must not contend at all, as `tests/test_pipeline_echo.py` does,
  but it is no longer a workaround for a defect.
- **The driver cannot even choose to wait longer.** `create_session` takes a
  `timeout` (default 60 s) but `open_session` — the facade the `cascade`
  archetype mandates — has an explicit keyword signature that does not accept
  it (verified: `TypeError: open_session() got an unexpected keyword argument
  'timeout'`). The only escape is hand-rolling the connect/create dance the
  facade exists to own. Filed as **jaato#899**; still open as of
  2026-09-09, and much less pressing now that #898 removed the stall it was
  a defence against.
- **`.jaato/` ownership**, filed the previous day as **jaato#896**: the
  `explain paths` output listed what the framework writes under `config_root`
  but never stated that a tenant must not write there. Fixed upstream in
  `50ac3ab6`, so the rule this repository adopted on 2026-09-08 (the journal
  moved to `.ta_cascade/`) is now the framework's documented one rather than
  our inference from its behaviour.
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

## Findings from OpenRouter's own logs (2026-09-09)

Every stage now sends `Trading - <agent> (powered by Jaato)` as
`X-OpenRouter-Title`, with this repository's URL as `HTTP-Referer`
(`.jaato/profiles/openrouter_sonnet/_openrouter_app.yaml`). Confirmed
end to end against OpenRouter's activity export, not just against the
resolved profile.

- **The attribution arrives.** Sessions before the change show App `jaato`
  (the framework default); after it, each generation is named for its stage.
  Because every stage is its own jaato session, OpenRouter's session filter
  resolves to exactly one agent — so per-stage cost and token counts come out
  of their UI with no correlation work on our side. That was not the reason
  for doing it and is the better half of the result.
- **One generation in twelve arrived with no title**, and OpenRouter then
  displays the referer instead — the bare GitHub URL, which is what makes it
  look like a different app. The row is not distinguished by provider,
  streaming, cancellation or finish reason, and length does not separate it
  (a 76 s / 4042-token generation kept its title; the 52 s / 2205-token one
  did not). **No diagnosis: n=1.** If it recurs at a similar rate, capture the
  outbound headers with a profile `trace:` block rather than inferring from
  their logs.
- **The serving upstream is OpenRouter's choice and is invisible from here.**
  `model: anthropic/claude-sonnet-4.5` names the model, not who runs it: in
  the export, **every** claude-4.5-sonnet generation (34/34) was served by
  Amazon Bedrock rather than Anthropic direct. Note what this is and is not
  — the routing has been *stable*, and nothing observed shows it moving. The
  exposure is that nothing *guarantees* it: an availability blip or a price
  change could move the substrate under a pipeline built on `temperature:
  0.0` and exact quotation, with nothing in our output to show it.
  `plugin_configs.openrouter.routing` (`only` / `order`) would pin it for all
  thirteen stages at once; it is written into `_openrouter_app.yaml`
  **commented**, with the trade spelled out — pinning buys determinism and
  pays for it with a hard failure when that upstream is down.
  This does NOT explain the same-date `Overweight`/`Sell` divergence: both
  runs were in the Bedrock-only window, so routing was constant across them.
  That variance remains unexplained and needs its own experiment.

## Findings from the regression check on jaato-server 0.12.0 (2026-09-12)

After pulling jaato to `798878c8` (jaato-sdk 0.19.1, jaato-server 0.12.0,
jaato-tui 0.5.1) and restarting the shared daemon. **No regressions.**

| check | result |
|---|---|
| unit tests | 70 passed |
| `validate` both sets | 0 errors; 40 new warnings (below) |
| echo run on the shared daemon | exit 0, 41 s |
| `tests/test_pipeline_echo.py` | 2 passed, 126 s |
| live `--analysts market` NVDA 2026-09-04 | exit 0, 420 s, `Overweight`, every stage `errors: []` |
| host-tool events reach a third-party observer | start and end events for all three tools |
| market analyst figures vs `snapshot()` | all six quoted exactly; tool-call ids identical to 2026-09-08 |
| daemon errors in the run window | none new |

- **The stricter validator surfaced two things, neither a regression.**
  `budget_control_absent` on every profile is a real gap — #15 above.
  `missing_description` on the set profiles is also real, and measured
  rather than taken on trust: the base declares a `description`, the set
  profile omits it, and the resolved profile's `description` is `''`. So
  `description` does NOT inherit, unlike other scalars. Harmless here — the
  description is only advertised to a model choosing a subagent to delegate
  to, and this pipeline never delegates.
- **A stage finished field by field for the first time.** The market analyst
  called `prepare_completion` nine times — one parallel batch of six (exactly
  `analyst_report`'s six fields), a correction pass on three — then an
  argument-less `signal_completion`. The 2026-09-08 run of the same stage, and
  the other three gated stages today, each sent one `signal_completion`. So
  it is a model choosing an available path (`prepare_completion` has existed
  since jaato-server 0.6.193), not a loop. Why it chose it this time is not
  established. No `explain` topic mentions `prepare_completion` or
  `query_completion`; added to jaato#905.
- **The judgement layer varied, as it has before.** Same `Overweight`
  rating, but the trader bought at 222.5 with a stop at 210.57 (the 50-day
  SMA) where the first live run bought at 230.36 with a stop at 220.08. The
  price gate accepted both.
- **A daemon ERROR pair was not new, and first looked new.** Counting the
  current `/tmp/jaato.log` alone suggested it first appeared today; the
  daemon rotates its log, and the rotated files show it about 70 times
  since 2026-09-05. Recorded as known noise in `CLAUDE.md` §6.6.
- **`explain`'s list of valid topics omits `integrations`** — a hand-typed
  string that jaato#906 did not update. Filed as jaato#994.
- 420 s against roughly 300 s for the earlier market-only runs. Two extra
  model round trips from the field-by-field completion account for some of
  it; one sample is not enough to call the framework slower.

## Findings from forcing budget aborts (2026-09-12 … 09-14)

Each `_base_<agent>` now carries a `budget_control` ceiling (#15). To see
what an abort does to a run, one base profile at a time got `tokens: 10` on
the echo set, where every turn reports 1200 tokens.

- **A capped judge stopped cleanly.** The trader's session ended at its
  ceiling, `complete()` returned no payload, and the run failed at the
  trader with the journal kept (exit 1, 22 s); with the cap removed the same
  command resumed and finished. But the message said only "ended without
  signal_completion": the daemon's reason did not reach the driver.
- **A capped debater hung the run.** The turn that crossed the ceiling came
  back from `ask()` as empty text, as if it were an answer. The daemon then
  ended the session and, as it does for every session of a cascade,
  unloaded it and detached the driver. The driver's next `ask()` on that
  side was answered at once with `ErrorEvent("Session not found")`, which
  `ask()` did not listen for, so it waited forever: 12+ minutes, and not one
  daemon log line. Reproduced with a credential-free echo script and filed
  as jaato#1007.
- **Fixed centrally in jaato** (`f4883e09`; jaato-sdk 0.22.0, jaato-server
  0.15.0). `ask()` and `stream()` raise `SessionEnded`, with the reason and
  the terminal's details, for a turn a session's end cut short and for a
  session that is gone; `complete()` records the same on `Session.terminus`.
- **Driver side**, `pipeline._ask` and `pipeline._complete` turn both into
  `StageFailed` naming the stage or debate turn, with the daemon's reason
  and details (`investment debate turn 1 (Bull): the session ended mid-turn
  (budget_exhausted): …`). A cut turn is raised before it is appended, so it
  never reaches the journal and a resume replays it.
  `tests/test_pipeline_echo.py` caps a debater, then a judge, then resumes
  to the end.
- **`explain clients` mentions neither `SessionEnded` nor
  `Session.terminus`**; both were read from the SDK source
  (`jaato_sdk/client/convenience.py`). Filed as jaato#1063.

## Findings from the health checks (2026-09-13 and 09-14)

Two live market-only runs on NVDA 2026-09-04 both rated `Hold`, where the
2026-09-12 run had rated `Overweight`. In both, the market analyst wrote that
NVDA "closed at 230.36 … a fresh breakout above the prior 90-day high of
236.54 set on May 14", and the research manager's and the trader's warnings
name that passage.

- **The label was ours.** `snapshot()` took the last N *bars* and labelled
  them `high_Nd`, `low_Nd` and `change_Nd_pct`. With 90 it reached back to
  2026-04-29, about 128 calendar days, and returned `high_90d: 236.54`
  (May 14) and `change_90d_pct: 10.09` — the report's figures exactly. Over
  90 calendar days the high is 234.76, on 09-04 itself, and the change
  +10.41%. `get_indicators` had the same bars-as-days window, while the news
  and macro tools already meant calendar days.
- **The model added two errors of its own**: a "breakout" above a level the
  close was below, and the 189.80 low dated "July 29" (it was 06-29). The
  snapshot carried no dates at all.
- **Fixed.** `lookback_days` is calendar days in every tool. The snapshot
  states its window (`from`, `to`, `bars`), gives the high and low each with
  its date and the last ten closes with theirs, and says that indicator
  periods count sessions. For the same date it now reads `high_90d: 234.76`
  (2026-09-04), `low_90d: 189.80` (2026-06-29), `change_90d_pct: 10.41`.
- **Stale prices are refused** (P4): `ohlcv`, `indicators` and `snapshot`
  answer with a `DATA_UNAVAILABLE` sentence when the newest bar is more than
  `RunConfig.max_stale_days` (7) calendar days before the date asked.
- **No rate limiting seen.** The five "429"s in the session logs are
  millisecond timestamps, so no retry wrapper was added.

## Findings from the 2026-09-16 pull and health check

- **`max_turns` is gone from jaato** (#1068): it was declared, validated,
  inherited and advertised to the model, and compared against a turn counter
  in no path of the framework — so every per-stage turn ceiling this
  repository has ever declared bounded nothing. The validator now warns
  `removed_profile_key` on each profile that keeps it. The numbers moved into
  `budget_control.limits.turns` (analysts 8, debaters 12, judges 6, the
  reflector 4), where the `abort` rung enforces them; a turn ceiling is real
  here for the first time.
- **The live run stopped at the portfolio manager on an OpenRouter 402**:
  `in_flight_budget_exhausted`, the account down to $0.85 of $750. Nothing to
  do with this repository. After a top-up the same command resumed from the
  journal, ran only the missing stage and finished `Overweight` in 73 s — the
  resume path's first live exercise.
- **The dated snapshot held against a live model.** The market report wrote
  "a high of **236.54 on 2026-05-14** and a low of **189.80 on 2026-06-29**",
  both correct, and named 236.54 as the 120-day high and a target above the
  close rather than a breakout already achieved. The two runs before the fix
  misdated that low as "July 29" and claimed the breakout.
- Otherwise clean: 74 unit tests, the echo run in 42 s, the end-to-end suite
  3 passed in 171 s, `validate` 0 errors, and no daemon errors beyond the
  known observer-disconnect noise.
- **The integration check needs both words.** `jaato-doctor` reported the
  claude-code payload `outdated` at 0.15.0 while my own check looked only for
  `stale`, so the refresh did not run until doctor named it.

## The driver as a jaato-eval arm (2026-09-18)

A backtest is a matrix — tickers × dates × repeats — and jaato-eval owns
every matrix mechanic; what it could not express was an arm that is this
driver rather than one session. jaato#1110 designed that, #1112 shipped it
(`harness.kind: driver`, a versioned environment contract, the arm's cascade
id as the join between driver, observer, pool and per-stage records), and
this repository is its first consumer.

- **What changed here.** `contract.py` reads `JAATO_EVAL_*` once and refuses
  a version it does not know; `RunConfig` gains `config_root` and
  `cascade_id`, which the CLI takes from the contract, and `open_stage` now
  passes `config_root` (only the observer did). Under the contract an
  unreachable daemon exits 75, the code the engine records as BLOCKED.
  `python -m ta_cascade.score` grades a cell against realised returns —
  rating direction versus alpha over `holding_days` against the benchmark,
  a Hold right within a ±1 % band — with exit 0/1/75 and one JSON line of
  the facts. `backtest-tasks` writes the manifests.
- **Two facts shaped the manifests.** Every stage profile carries its own
  `budget_control`, and a session with its own ceiling never draws on a task
  pool (the framework's rule), so no `budget:` block and one cid per arm.
  And every arm is a fresh workspace, so the decision log's walk-forward
  loop cannot cross arms: `--no-memory`, and a backtest with memory is not
  offered yet.
- **Measured, zero model cost.** `backtests/echo-smoke` runs the whole
  pipeline on the echo set as an arm: driver exit 0, all 9 sessions
  attributed to the arm, `state.json` in the arm's workspace, the engine's
  `.env` carrying `JAATO_PROFILE_SET=echo`. `ECHO` is a real Yahoo symbol,
  so the scorer even grades it (`alpha +2.8 %`, PASS) — run by hand in the
  kept workspace, because in the sweep the grader was BLOCKED with exit
  127: jaato-eval exports `JAATO_EVAL_PYTHON` to the driver and not to the
  script grader (`graders/script.py:115`). Filed as jaato#1127; the
  generated grader keeps `"$JAATO_EVAL_PYTHON"`, which is right once that
  lands, rather than a PATH bet or a per-host absolute path.
- **The driver must be importable by the engine's interpreter.** An arm's
  working directory is its scratch workspace, so `-m ta_cascade` needs the
  package installed there: `pip install -e .` into the daemon's venv.
- **A regression of my own, fixed here.** PR #13 changed the shared
  identity's `api_key` to `pass://` after `validate` alone; the unit tier,
  which asserts on that key, had been failing on main since. Both tiers ran
  before this change went up.

## The determinism study (2026-09-19): NVDA 2026-08-28 × 5

The first sweep through jaato-eval on a real model (`backtests/determinism`,
`openrouter_sonnet`, market analyst only, sequential; `results.jsonl` and
`report.html` beside the tasks). Five arms, each a full run: 9 sessions,
314–394 s, $0.77–0.92 by the daemon's own accounting; no errors, no ceiling
hit. The question was whether the pipeline agrees with itself on identical
inputs.

| arm | market stance | research manager | trader | rating |
|---|---|---|---|---|
| 0 | bullish (medium) | Hold | Hold | **Hold** |
| 1 | neutral | Hold | Hold | **Hold** |
| 2 | neutral | Underweight | Sell | **Underweight** |
| 3 | neutral | Underweight | Sell | **Underweight** |
| 4 | neutral | Hold | Hold | **Hold** |

- **The data layer is deterministic; the judgement is not.** All five market
  reports quote the verified close (217.55) and RSI (52.34) exactly and list
  the same three tool calls. Above that layer the rating agreed 3 of 5
  (Hold), with two arms one notch lower — on the same report, same
  personas, `temperature: 0.0`. Sixty per cent agreement is the number a
  backtest's hit rate has to be read against: a single run of a cell is one
  draw.
- **All five were wrong against the next week.** NVDA returned +5.89 % over
  the 5 bars to 2026-09-04 against SPY's +0.11 % (alpha +5.78 %): a Hold
  fails the ±1 % band and an Underweight fails the sign. One cell says
  nothing about the strategy; it says the scorer works and the pipeline is
  not a coin that always lands the same way up.
- **No trader numbers to compare.** Every trader answered Hold or Sell with
  no entry price and (four of five) no stop, so the entry/stop spread the
  earlier runs showed (222.5 vs 230.36 on the 09-04 data) could not be
  measured here. A pilot over many dates will.
- **The facts are in the results file.** The scorer's JSON line is kept
  verbatim as each verdict's `evidence` (not `notes`, which is where a
  first read looked for it), so a pilot's rows carry rating, returns and
  alpha per cell; the table above was cross-checked by re-running the
  scorer in the kept workspaces.

## The pilot (2026-09-19): 12 cells × 5, and what the scoring was measuring

`backtests/pilot`: NVDA, AMD and SPY on 2026-07-24, 08-07, 08-21 and 09-04,
five arms per cell, `openrouter_sonnet`, market analyst only. Sixty arms,
none blocked, no errors, no ceiling hit; $47.18 ($0.79 mean, $0.34–1.21),
5.8 h sequential. Every kept workspace carries its chart.

**As first scored** (5 sessions, a fixed ±1 % Hold band): the panel's
majority was right in 4 of 12 cells, individual arms 23 of 60 — no better
than buy-and-hold (4/12) or a close-above-SMA-20 rule (5/12) on the same
cells. Two defects in the experiment, both mine, decided that number:

- **SPY against SPY is degenerate.** Alpha ≡ 0, so an index cell was right
  iff the panel said Hold; four of twelve cells measured nothing else.
- **A ±1 % band sits far inside the instruments' weekly noise** (one ATR
  over five sessions is 6–18 % of price for NVDA and AMD), so the 34 Hold
  ratings were almost mechanically wrong whenever the stock moved.

**The scorer now** (`ta_cascade/score.py`): the Hold band is one ATR over
the holding period as a fraction of price (`data.hold_band`; `--hold-band
0.01` keeps the fixed rule); a cell whose ticker is the benchmark scores its
raw return; a directional call with a stop is scored along the path
(`data.path_after`), out at the stop when a session crosses it. Re-scored
on the same sixty runs (`backtests/pilot/rescored.jsonl`):

| | majority right | arms right |
|---|---|---|
| fixed ±1 % band | 4/12 | 23/60 |
| volatility band, index raw, stops honoured | 8/12 | 46/60 |

**Read that honestly.** The rise is almost entirely Holds becoming right:
Hold majorities 6 of 6, **directional majorities 2 of 6**. A Hold on a
stock that moves 8 % a day is close to unfalsifiable in a week, so at this
horizon the panel's directional calls are the information, and those are
2 of 6 — AMD 07-24 (bearish, −9.9 %) and SPY 08-07 (bullish, +0.4 %)
right; SPY 07-24, AMD 08-07, NVDA 08-21 (bearish into rises) and NVDA
09-04 (bullish into −7.2 %) wrong. Twelve cells cannot separate that from
chance; they can say the ruler now measures the instrument and not itself.

- **Stops fire constantly.** 12 of the 19 directional calls that carried a
  stop were stopped out inside the five sessions — the trader sets stops a
  few per cent from the price on instruments that move that much in a day.
  A stop that tight is a coin flip on the path, not risk control; a
  volatility-scaled stop is a persona question for the trader.
- **Agreement is modest and the margin predicted nothing.** Direction
  unanimous in 3 cells, 4–1 in 2, 3–2 in 7; unanimous majorities were right
  1 of 3 (fixed band). 34 of 60 ratings were Hold; the rest leaned bearish
  16 to 10.
- **Both large directional misses are reversal reads**: bearish after AMD's
  26 % drop (then +6 %), bullish after NVDA's capitulation-and-rally on
  09-04 (then −8.4 % raw). The persona reads a sharp move as the start of
  the next one; twice out of twice it was the end of it.
- **A 20-session re-score** is possible for the six cells old enough
  (3 of 6 right under the fixed band) and will cover all twelve by
  2026-10-02.

Next, in order: a paired experiment on the same twelve cells with the
reversal logic changed in the analyst's and manager's personas (and an
abstain rating, so "no edge at this horizon" is not scored as a position);
then breadth.

## Jev over the pilot (2026-09-19): a System One model as the judge

TypeSafe's Jev (`jev-1.13.0`) takes structured state and typed questions
and returns typed answers with probabilities, in ~150 ms, at $0.042 per
million input tokens, no output tokens. The pilot's sixty arms were sent
through it — each arm's evidence only (the cell's 120-day snapshot and that
arm's market report; no judge output, no outcome) with eight questions
(`backtests/pilot/jev/questions.json`; `batch.py`; answers in
`backtests/pilot/jev.jsonl`), and its `rating` scored with the pilot's
ruler beside the panel's vote. Whole run: 172,751 input tokens, ≈ $0.007,
against the pilot's $47.

- **Majorities right 11 of 12 against the panel's 8 of 12 — and the
  difference is Hold.** Every cell Jev won is one where it said Hold and
  the panel went bearish; a Hold on these stocks is right unless the week
  clears the band. On the calls that carry information, **directional
  arms: Jev 14 of 26, panel 12 of 26** — a coin, both. On NVDA 09-04 Jev
  went Buy 3 / Overweight 2 into the −7.2 % week, the pipeline's own
  reversal-read failure with more conviction.
- **The arithmetic questions are reliable**: `trend_aligned` (close above
  all three averages) agreed with the computed truth 60 of 60, peaked near
  0 or 1. As a checker of a report's claims against the snapshot it works,
  and costs nothing.
- **Calibration, faintly**: confidence ≥ 0.7 right 42 of 51, below 0.7
  right 6 of 9 — the right direction, far too small a sample.
- **Where it fits**: not as a better judge of next week's direction —
  nobody in this experiment is — but as typed checks against structured
  state, and as the cheapest way to run calibration studies over hundreds
  of cells, the only route to knowing whether any of these ratings carry
  signal. Access was an API key in the pass store
  (`jaato/typesafe/api-key`); no jaato integration exists yet, and a
  provider adapter would be the framework's to add.

## Findings from the 2026-09-23 pull and health check

Pulled 79 commits of jaato (sdk 0.23.0 → **0.26.0**, server 0.16.0 →
**0.20.0**), reinstalled the editable packages, restarted the daemon and
ran the full pipeline on NVDA as of 2026-09-22 (the last session).
Finished in ~10 minutes, exit 0, thirteen stages, no stage failure and no
degrade rung fired. Rating **Underweight** (entry 228.87, stop 234.76,
target 215.00) against a split panel: market and fundamentals bullish,
sentiment bearish, news neutral — the judges overrode the majority.

- **`budget_control.limits.turns` is live after the upgrade.** The daemon
  logged `limits={'tool_calls': 10, 'usd': 2.0, 'seconds': 600, 'turns': 12}`
  on the debaters and `turns: 6` on the judges. This is the first
  confirmation that the post-jaato#1068 replacement for `max_turns`
  survives sdk 0.26 / server 0.20.
- **The memory path closed a full cycle.** The portfolio manager cited the
  lesson from the 2026-09-04 decision, which means that decision resolved,
  the reflector wrote a lesson and it reached the persona. Today's call is
  appended `pending` to `~/.ta_cascade/decisions.jsonl`, scoreable from
  2026-09-29.
- **StockTwits now fails hard: 403 Forbidden**, not an empty window. This
  changes a documented expectation — §7 of CLAUDE.md and trap 10 said a
  historical window comes back *quiet*, and quiet and unavailable are
  deliberately different sentences in the data contract. The fetcher
  reports it correctly as unavailable; nothing invented. Reddit was 60 %
  down in the same run (`r/stocks` and `r/investing` failed, only
  `r/wallstreetbets` returned).
- **`FRED_API_KEY` is absent from `.env`**, so the fed funds rate, the
  10-year and VIX were unavailable and the news analyst said so rather
  than characterising the rate environment from memory. Configuration, not
  code: `.env` is gitignored and lost the key.
- **The run's cost could not be measured.** The framework tracks spend over
  the `session.get_budget_usage` RPC and emits no spend line to the daemon
  log, so there is no number to read. The pilot's measured $47 over 60 arms
  puts this run near $0.80, but that is an inference from a different
  configuration, not a measurement.
- **`jaato-scaffold validate` no longer gates this repository** — filed as
  **jaato#1217**. It exits 1 on errors in profiles the workspace does not
  own: 13 errors, every one `tier: "user"`, from `~/.jaato/profiles/` and
  from profiles shipped as package data inside `jaato-premium`. The
  workspace's own findings were 16 warnings and zero errors. `--json`
  already stamps each finding with `tier`; only the exit code ignores it.
  Until it is fixed, `validate . --set <set> && commit` cannot pass, and
  the honest check is the workspace-scoped count in the JSON.
- **A child profile's absent `description` clobbers its base's.**
  `description` is a required field whose value a child *replaces*, and an
  omitted key resolves to the empty string rather than inheriting — measured
  with `explain profile market_analyst`, which resolved none at all. All 13
  `_base_<agent>` profiles declared one; none of the 26 set profiles did, so
  every profile the driver actually uses advertised nothing. Fixed by
  declaring the stage's description in both sets. Workspace warnings fell
  from 16 to 3 (openrouter_sonnet) and 2 (echo).
- **Three workspace warnings remain, all new framework surface:**
  `regulatory_undeclared` (the EU AI Act block — `intended_purpose`,
  `risk_class`, `interacts_with_persons`, `provider`; absent is UNDECLARED,
  not minimal, and the determination is the provider's), `budget_control_absent`
  on `_openrouter_app` (the provider-binding fragment, not a stage profile —
  all 13 stage bases still carry ceilings), and `gitignore_hides_jaato_assets`
  (`.gitignore` hides `.jaato/plans/`). None is a defect in the pipeline;
  the regulatory block is a real decision to make before any production use.

## The package rename (2026-09-27): `server` → `jaato_server`

Pulled 239 commits of jaato: sdk 0.26.0 → **0.29.0**, eval 0.3.1 → 0.3.3,
server 0.20.0 → **1.2.0**. The major bump is one change —
`caeba843 Rename squatted top-level packages to jaato_server / jaato_tui`
(jaato#1079). The top-level `server` package no longer exists: `import
server` raises `ModuleNotFoundError` and `python -m server --daemon` is
gone, replaced by `python -m jaato_server --daemon` and a `jaato-server`
console script. The daemon then running had been started from the old
module and was executing files that no longer existed on disk, so a
restart was mandatory rather than hygienic.

- **The driver needed no change.** `ta_cascade` imports only `jaato_sdk`,
  which kept its name; the pipeline, sessions and profiles are untouched
  by the rename. `jaato-doctor` reports 0 fail over 23 checks on the new
  build and the 105 unit tests pass.
- **The end-to-end tier broke by going green.** `tests/test_pipeline_echo.py`
  opened with `pytest.importorskip("server")`, so after the rename the only
  test that exercises the real daemon contract **skipped**, with a reason
  that had become false:

  ```
  SKIPPED [1] tests/test_pipeline_echo.py:33: jaato-server (the daemon) is not installed
  1 skipped in 0.38s
  ```

  jaato-server was installed; only its name had changed. A suite that
  reports success while testing nothing is worse than one that fails, and
  `importorskip` on a framework package converts every future rename into
  exactly this. Fixed by naming `jaato_server` in the guard, in the two
  `subprocess.run` daemon invocations and in the module docstring; the tier
  then passes 3/3 in 5:18, which also confirms that sessions, completion
  gates, budget aborts, resume and the reflector cycle all survive the
  major bump.
- **The end-to-end tier takes ~5:15, not ~3 minutes.** Measured 5:17 on
  server 0.20.0 (2026-09-23) and 5:18 on server 1.2.0 — two builds, one
  figure, so the number in CLAUDE.md was simply stale rather than a
  regression introduced by either upgrade. Corrected there.

## The first references (2026-10-03): a rule the trader is held to

The personas carry no investment knowledge. All thirteen total **1,781
words**, and what is in them is role, protocol and guardrails — which tool to
call in what order, what belongs in `errors` rather than `warnings`, "the
snapshot's numbers are the only price levels you may state as facts". Nothing
in them says anything about markets. So the knowledge the pipeline runs on is
not hardcoded in prose; it is latent in the model's pretraining, which is
uninspectable, unversioned, untestable and free to move on a provider
upgrade. That is the argument for a knowledge base: not refactoring knowledge
out of prose, but writing down knowledge that exists nowhere.

The shape is taken from the sibling `kb-for-coding-patterns-wiki` ("kb-rip"),
whose chain is page → atoms → references → capability → check module, and
whose transferable idea is that **a claim cannot enter the catalogue until an
executable check reproduces an answer key the check's author never saw**.
(ADR → ERI → Capability → Feature belongs to a different project,
`enablement-2.0-kb`, whose checks are declarative constraint YAML.)

- **Conformance is not validity, and only the first is a deterministic
  check.** "Did this report apply the rule correctly to the snapshot it was
  given?" is decidable and blind-testable. "Does the rule predict anything?"
  can only be answered by history, which answers many questions at once and
  promotes whichever got lucky; that needs pre-registration and an
  out-of-sample holdout, and it is not a check. The first reference is a
  conformance rule, and its check says so.
- **The blind protocol does not yet apply here.** The same hand wrote the
  rule and its check, so the check attests conformance and nothing more. The
  caveat is recorded in the catalogue entry's `origin`, so it travels with
  the reference instead of living in a conversation.
- **`state.json` kept the model's retelling of the numbers, not the
  numbers.** ATR appeared only inside prose, so no check could read what the
  analyst was actually given. `data.snapshot` now takes a `record` callback
  and the driver passes `RunState.record_snapshot`, so every verified
  snapshot survives in `state.evidence.snapshots` as data. The check reads
  only from there and reports `cannot_verify` when it is absent, rather than
  recomputing from the network: a check that reaches for live data answers
  differently on different days and stops being a check.
- **The pilot cannot be re-audited, and that is the lesson that prompted
  this.** `/tmp/pilot-ws` was cleared; `backtests/pilot/jev.jsonl` kept only
  derived fields. Sixty arms' reports and proposals are gone, so no rule
  invented afterwards can ever be measured against them.
- **The rule binds on real output.** Audited over the four surviving live
  cells, two conform and two do not: `NVDA 2026-09-22` placed its stop 5.89
  from entry against an ATR(14) of 6.25 — inside the instrument's own daily
  range, and that is the call that scored FAIL — and `NVDA 2026-09-29`
  carried a stop of 217.00 with no entry and a Hold rating.
- **Wiring.** `references(preload, tools:[listReferences, selectReferences])`
  on `_base_trader` with `preselected: [stop-placement]`. Preselected rather
  than selectable because these are obligations: a rule the model must
  remember to look up is a guardrail that silently lapses. A catalogue large
  enough to search belongs in `selectable`; this one is not.
- **Cost.** The end-to-end tier went 5:18 → 7:43 with the plugin on the
  trader; the unit tier gained 11 tests for the check.

### A reference is made available, not delivered (2026-10-03, measured)

Selecting a reference — by `selectReferences` or by `preselected` — only
**authorises readonly access to its path**. Nothing is injected, under any
mode. Measured with a probe token placed in the rule body and grepped out of
the proposal:

| mode | tools on the stage | persona told it to look | token echoed |
|---|---|---|---|
| `selectable` + `preselected` | listReferences, selectReferences | no | **no** |
| `auto` + `preselected` | listReferences | no | **no** |
| `selectable` + `preselected` | + `file_edit(readFile)` | **yes** | **yes** |

So a stage needs three things, and two of them are easy to miss:

1. the entry in the catalogue, `mode: selectable`;
2. a **read tool**, or the authorised path cannot be opened — both sibling
   projects carry `file_edit(preload, tools:[readFile])` beside `references`,
   which looked incidental and is load-bearing;
3. a **persona line telling the stage to consult the catalogue**, because a
   reference cannot announce itself: it is unread until something reaches for
   it.

The third changes the design. "Move the knowledge out of the personas" was
the wrong goal; the right one is to move the *content* out while leaving an
explicit duty behind. The persona becomes the index and the catalogue holds
what is indexed. The trader's now reads: "Before you state an entry, a stop
or a size, call `listReferences` for the rules tagged `trader` ... a rule you
did not read still applies to your proposal."

What made this expensive to find: `jaato-scaffold validate` passed, the
catalogue loaded (`Discovered 1 reference(s): stop-placement`), both test
tiers were green, and the daemon logged nothing either way. Session logs hold
RPC diagnostics, not prompt content, so their silence was no evidence at all —
an inference this repository drew and had to retract. A probe token was the instrument that found it; `context.tool_calls` is the
standing one — see the next entry, which corrects this.

Also seen while measuring, both the pipeline working rather than failing:

- The **research manager refused a debate** because the bear researcher
  asserted "three rejections" at a level the market report never counted and
  recharacterised the report's "indecision" as "distribution". A judge
  checking a debater against the source is the same conformance property this
  KB work is meant to systematise, already happening between stages. It is
  the second rule worth writing.
- The **sentiment stage now fails every full run**: StockTwits 403 since
  2026-09-23, both Reddit subs failing, news feeds empty for the window. The
  persona tells the analyst to put a total failure in `errors[]` and the
  driver turns that into `StageFailed`, so the run dies. Open decision:
  report "no observable sentiment" as a finding (and lose the distinction
  between an outage and a quiet market, which is the one thing the data
  contract exists to preserve), or drop sentiment from the default set until
  the sources are replaced.
- **The trader is the volatile stage.** Four runs of the identical cell
  (NVDA 2026-09-29) produced Hold-with-a-stop-and-no-entry, Sell with no
  levels, Buy at 227.21 stop 215.17, and Hold with no levels — while the
  portfolio manager answered Hold every time. The analyst sets differed
  across those runs, so this is not a clean determinism measurement, but runs
  1 and 2 differed by one analyst and still swung Hold to Sell.

### The duty is checkable, and sentiment leaves the default set (2026-10-03)

Two corrections to the entry above, both from the user.

**"There is no introspection for did this reference reach the model" was
wrong.** `context.tool_calls` is the paired ledger of every call and its
response, and kb-rip already audits it this way
(`ledger_paths(tool_calls, "readFile")`). So the persona's duty to consult the
catalogue is enforceable, not merely stated: `scripts/processors/rules_read.py`
resolves every catalogue entry tagged `trader` to its path and refuses the
completion when the session never opened it. It reads the requirement from the
catalogue, so a new rule tagged `trader` becomes required with no change to
the gate. This is better than the probe token that found the problem, because
it runs in production on every proposal rather than once under a test.

**Sentiment leaves the default analyst set.** All four of its sources are
down. The alternative — reporting "no observable sentiment" as an ordinary
finding — would make an outage and a genuinely quiet market produce the same
payload, and that distinction is the one thing the data contract exists to
keep. `DEFAULT_ANALYSTS` is now market, news, fundamentals; sentiment is still
available by name for when a source returns.

**The attribution rule goes on the debaters**, where the fabrication
originates: `claims-must-match-the-source`, quoting the refusal that prompted
it. It binds by instruction only. Debaters run as plain turns with no
completion payload, so no gate can inspect them and `rules_read` does not
apply; the research manager catches violations downstream, as it did. Making
it enforceable would mean either a gate on the judge that reads the transcript
or giving debaters a completion payload — both larger changes than the rule.

### Measuring whether a rule changes behaviour (2026-10-03): spoiled, and why

Five runs were planned to test whether `stop-placement` changes what the
trader proposes: NVDA 2026-09-22 ×3 (a cell that previously violated rule 3)
and 2026-09-04 ×2 (a cell that previously produced conforming levels). The
ruler was fixed in advance — among proposals carrying a stop, the fraction
conforming on all three clauses, with proposals carrying no levels excluded
and the excluded count reported, because a rule that "works" by suppressing
levels altogether is a degenerate result, not a success.

**Two of the five runs are real.** Three died in the sentiment stage, and the
harness copied `results/.../state.json` regardless of exit code, so the failed
runs produced duplicates of the previous successful run and three identical
rows looked like three observations. Key the snapshot on the exit code that is
already being recorded.

**They died in sentiment because the decision to drop it had not taken
effect.** `DEFAULT_ANALYSTS` was changed in `config.py`, but `cli.py` defaulted
`--analysts` to `",".join(ANALYST_KEYS)`, so the dataclass default is dead
code for anything started from the command line — which is everything. The
config said one thing and every actual run did another. `tests/test_cli_defaults.py`
now pins the parser default to the config default so the two cannot drift.

What the two surviving observations say, which is little:

| cell | before (no rule) | after | check |
|---|---|---|---|
| 2026-09-22 | Sell 228.87 / **234.76**, rule 3 violation | Buy 228.87 / 220.50, 8.37 vs ATR 6.25 | compliant |
| 2026-09-04 | Buy 230.36 / 210.57 | **Hold, no levels** | not_applicable — excluded |

The first flipped direction, so it is not the same proposal placed better; the
second is exactly the degenerate outcome the protocol predicted and excluded.
Nothing here supports a claim that the rule changes behaviour, and the
experiment needs redoing with the CLI fixed, a harness that discards failed
runs, and a real control arm — the same cells re-run with the rule removed,
which the original design lacked.

One thing that did hold: the gate resolves its requirement correctly
(`_required()` returns `stop-placement` with its path). Whether it ever
refused cannot be read from the daemon log, and absence of a log line is not
evidence of absence — the same mistake this file records two entries above.

### A second provider set: MiniMax-M3 (2026-10-03)

`.jaato/profiles/minimax_m3/` binds the same thirteen stages to `MiniMax-M3`
on jaato's native `minimax` provider. Nothing else moved: every stage profile
is `inherits: [_base_<agent>, _minimax_app]` plus `model` and `provider`, so
the stage determinism — gates, schemas, ceilings, the references wiring —
stays in the tier-1 bases and a set swaps only the binding. The credential is
`pass://jaato/minimax/api-key`, resolved daemon-side and proven with
`jaato-doctor --secret`.

`JAATO_PROFILE_SET` still selects `openrouter_sonnet`. Keeping both sets is
the point: the same cell can be run on either, which is the control arm the
stop-placement experiment lacked.

Differences worth knowing before trusting a run on it:

- **No prompt caching.** OpenRouter has it, minimax does not. This cascade
  re-sends a growing context to every stage — the judges read both debate
  transcripts plus every report — so it benefits from caching more than a
  single-turn application would. M3 is far cheaper per token, so this is
  likely still a large net win, but not by the headline per-token ratio.
- **The `prose_tool_calls` quirk.** `explain provider minimax` names it and
  does not describe it, and there is no `explain quirks` topic. This pipeline
  rests on `signal_completion` being called as a tool against a strict schema,
  plus the market analyst's real tool loop, so the quirk is directly relevant
  and currently unmeasured here. kb-rip runs M3 across seven session kinds
  with completion processors and strict gates, which is good evidence that
  gated stages work on this provider.
- **No `temperature` is set.** `explain provider minimax` warns that reasoning
  models commonly reject an explicit `0.0`, and that omitting a parameter is
  never the cause of a 400. The OpenRouter set pins `temperature: 0.0`; this
  one does not, so runs on the two sets are not sampling-equivalent and a
  difference between them is not evidence about the model alone.
- **Thinking** is `enable_thinking: true` on `research_manager` and
  `portfolio_manager`, matching the OpenRouter set's intent. M3 maps it to
  `thinking: {type: adaptive}`; there is no `thinking_level` knob here.

**A framework bug found building it (jaato, server 1.3.0, reproduced on
`3204f77d`):** a profile that names a plugin under `plugin_configs` with no
body parses as `{plugin: None}`, and `_merge_profiles` does `.update(None)`:

    File ".../plugins/subagent/config.py", line 4361, in _merge_profiles
        merged_configs[plugin_name].update(config)
    TypeError: 'NoneType' object is not iterable

`jaato-scaffold validate` exists to diagnose malformed profiles and instead
dies with a traceback and exit 120, emitting no JSON; the daemon reaches the
same code at session creation. Reproduced with a two-file workspace.

### First live runs on MiniMax-M3 (2026-10-03): three contract gaps, no provider fault

Four runs of NVDA 2026-09-29 on the new `minimax_m3` set. The pipeline now
completes end to end on it. **Nothing that failed was a MiniMax defect**: each
failure was a place where the contract specified the payload's *structure* and
never its *meaning*, which Sonnet had been filling in from habit.

- **The `prose_tool_calls` quirk is not a problem here.** PR #23 flagged it as
  the main risk. The market analyst drove a three-call tool loop
  (`get_price_history`, `get_indicators`, `get_verified_snapshot`) and
  signalled a gated completion against the strict `analyst_report` schema,
  with no provider error. The trader later did the heavier pattern —
  `listReferences`, `selectReferences`, `readFile` — and passed the
  `rules_read` gate, which refuses the completion if the rule was not opened.
- **`errors: ["none"]`.** M3 filled the required array with a placeholder and
  the driver, which treats a non-empty `errors[]` as `StageFailed`, killed a
  stage that had no error. Only `analyst_report.json` had ever documented the
  convention; the other four schemas described `errors` not at all. All five
  now state that an empty array is the signal, that a placeholder is wrong,
  and that **a non-empty errors array stops the run**, so a caveat belongs in
  `warnings`. Fixed in the contract, not by teaching the driver to ignore the
  string "none" — that would have passed this run and left the ambiguity for
  the next model and the next field.
- **A demanded `CLAUDE.md`.** The portfolio manager reported as an error that
  it could not read the repository's convention file — "no filesystem tool
  enabled for this profile" — and stopped the run at the last stage. Nothing
  in our instructions, our personas or the framework's base layer mentions
  that file; it is the model's own prior about workspaces. `00-team.md` now
  states that the session's inputs are the prompt, its tools and any reference
  it is told to read, that no project documentation exists to consult and none
  is missing, and that an error is what stopped you producing a result while
  anything worked around is a warning.

Both fixes are provider-agnostic and apply to every set.

**What the completed run produced**, and why it matters beyond the migration:

    rating Buy | trader Buy, entry 227.21, stop 216.98
    ATR(14) 6.0162, distance 10.23 | check: compliant, no violations

This is the first proposal in the project that carries levels, demonstrably
read `stop-placement`, and conforms on all three clauses. Every earlier
attempt either never reached the rule or proposed no levels, which a rule
about stops cannot bind. It is one observation on one cell with two analysts,
so it is evidence the mechanism works end to end, not evidence about the rule's
effect on behaviour — that still needs the control arm.

Also: the analyst set was `market,fundamentals`, because **`get_company_news`
returned zero articles for NVDA over 2026-08-30 to 2026-09-29**. A month with
no NVDA coverage is not a plausible state of the world, so the fetcher or its
endpoint is the likely fault rather than the news supply. With sentiment
already out, two of four analysts are now unavailable and the pipeline is
deciding on price and fundamentals alone — which the personas do not say.

### News moves to Finnhub (2026-10-03), and the pilot had none

`yfinance`'s news endpoint began answering **404** — the library negotiates its
cookie and crumb, then the news POST 404s, and it returns `[]` rather than
raising. We are already on the latest release (1.7.0), so there was no upgrade
to take. `history()` is unaffected, which is why prices kept working while news
went silent. (A `429` seen while debugging came from a direct probe of a
different Yahoo endpoint, which rate-limits this IP; it was not the cause.)

**The pilot ran with no company news, and the reports read as though it had
some.** `yfinance.news` only ever served RECENT articles; `_format_news` then
filtered to the cell's window. For a cell dated April–August, every recent
article falls outside the window and is dropped, so all sixty pilot cells were
told there were no articles. Finnhub, asked for those same windows, serves
~250 each. The pilot's workspaces are gone so this cannot be re-verified
directly, but the mechanism is not in doubt.

`company-news` takes `from`/`to`, so a historical window is **served, not
filtered** — the point-in-time property backtests need and never had. The token
is `pass://jaato/finnhub/api-key`, read by the driver from the pass store:
one source, not a resolution chain, because a credential that can come from
several places fails in several ways and the one that matters is silent.
(`FRED_API_KEY` is the cautionary case: it reads from the environment, has
never been set, and macro data has quietly been unavailable throughout.)

**Three kinds of nothing, not two.** `_format_news` had ONE message for a
source that answered with nothing and a window that was genuinely quiet,
despite CLAUDE.md §7 stating they must differ. Now `DATA_UNAVAILABLE` when we
were not served and `NO_DATA` when the source served items and none fell in the
window.

That split then exposed a third case while wiring `global_news`. Finnhub's
general feed takes **no date range** and carries only the last few days, so for
a backtest window "served 100, none in your window" would read as *that window
was quiet* — a claim about a period nobody observed. `global_news` now compares
the span the feed actually carries against the window asked for and reports a
window outside it as unavailable:

    DATA_UNAVAILABLE: the market news feed carries 2026-09-30..2026-10-03 only
    and takes no date range, so it cannot speak to 2026-03-27..2026-04-03. This
    is an absence of evidence about that window, NOT evidence the market was quiet.

Two things to know before leaning on Finnhub: counts come back at 246–250 per
request, so there is likely a **250-item cap**; and `company-news` returns
pieces merely TAGGED to the symbol — the top April NVDA article was about
cruise lines — so this is more raw material than yfinance gave, wanting
relevance filtering rather than less. The per-category vendor chain of
`docs/gaps.md` P1 is still not built; this is one vendor replacing another, and
the next 404 will go just as quiet.

### The fundamentals analyst had lookahead, and the pilot ran with it (2026-10-03)

`fundamentals()` served yfinance's `info` block — trailing and forward P/E,
market cap, margins, growth, targets — to every cell, with a note saying the
figures were current rather than as-of. **A note is not a clamp.** The numbers
were in the model's context either way, and the info block is undated: every
ratio in it describes today. For a cell dated six months back, today's multiple
already reflects everything that happened after the as-of date, so the analyst
was reading the future and calling it analysis.

This is the one failure mode a prediction test cannot survive, because it
manufactures skill rather than hiding it. And the pilot ran this way: all four
analysts, sixty cells dated April–August, each shown October's valuation.

It was also a contract violation, not merely a caveat. CLAUDE.md §7 says
`as_of` bounds everything and nothing after it exists; the sibling
`statement()` honours that by filtering to periods ending on or before `as_of`.
The info block was the one source that warned instead of clamping.

Now the block is split by what moves:

- `_INFO_IDENTITY` (`shortName`, `sector`, `industry`) — what the company IS.
  Does not move with the price, served at any date.
- `_INFO_CURRENT` (the seventeen valuation, margin, growth and balance ratios)
  — what it is WORTH today. Served only when `as_of` is the present, judged by
  the same `max_stale_days` the price layer already uses to refuse stale bars.

A historical cell now gets an explicit refusal naming the gap in days and
pointing at `get_statement`, which remains the point-in-time source:

    DATA_UNAVAILABLE: the info block's valuation and performance ratios are
    undated — they describe today, 183 days after 2026-04-03 — so quoting them
    here would be reading the future. They are withheld. Use `get_statement`
    for figures dated on or before 2026-04-03; what follows is only the
    company's identity.

**Consequence for any backtest, including the pilot's numbers.** Every
historical result produced before this change had six months or more of
valuation hindsight available to one of its four analysts. The pilot's
headline figures were already uninterpretable for want of statistical power
(26 directional calls, ±19 pp); this is a second, independent reason not to
read anything into them.
### Every session is now accounted for (2026-10-03)

The question "what did that run cost?" had no answer: it is not in the daemon
log, and four MiniMax runs went unmeasured for that reason. The answer, taken
from kb-rip, is one call in one place:

    spend = (await session.client.get_diagnostics()).consumption

asked **while the session is still attached** — once the context exits there is
nobody holding it to answer — and written to an append-only log.
`sessions.open_stage` now wraps every stage: a `started` line when it opens, an
`ended` line from a `finally` INSIDE the session context, carrying the
terminus reason, the failure if it raised, and the consumption.

Measured on an echo run: 18 lines over 9 sessions, every one measured, with
`input_tokens_total`, `output_tokens`, `tool_calls` and `elapsed_seconds`.
A failed stage is logged too — a cost record that omits failures understates
every bill it appears in.

**`sessionlog.py` is not `journal.py`, deliberately.** The journal exists so a
failed run can resume and is DELETED when a run succeeds, so a successful run
leaves no trace of how it went. The session log is never cleared. It lives at
`results/<ticker>/<date>/sessions.jsonl`, beside the report tree rather than
under the driver's runtime state, because that is the directory that survives:
a jaato-eval arm materialises its own workspace and only what the run wrote
into its results travels with `--keep-workspaces`. The pilot's sixty arms were
lost for exactly this reason — and `--keep-workspaces` was there all along.

**Three money states, not two.** This is the third time today the same shape
has caught us, after quiet-vs-unavailable in the news layer:

| state | consumption | cost_usd | means |
|---|---|---|---|
| measured, priced | present | a number | OpenRouter — real money |
| measured, **unpriced** | present | `null` | a subscription plan or no pricing table: effort known, money not applicable |
| unmeasured | absent | — | the daemon could not be asked; nothing known, not even effort |

MiniMax is a subscription here, so it will always be the middle row.
Rendering that as `$0.00` would understate every total it joins, and
`consumption_error` must never read as a tidy zero. Aggregates should report
"measured 7 of 12" and **withhold a partial cost entirely** rather than sum
what they have — kb-rip's rule, worth copying verbatim.

Still unproven: `cost_usd` has never been seen populated here. Echo does not
price and MiniMax does not either; it needs one run on `openrouter_sonnet` to
confirm the money column fills. The plumbing carries whatever the provider
reports.

### What a historical cell can actually see (2026-10-03)

Before committing hours to a 600-cell eval, each analyst's inputs were probed
at four as-of dates. Three of the four input paths had changed that day, and a
backtest that discovers its own blind spots mid-run wastes the whole run.

| input | recent | 6 mo | 1 yr | 2 yr |
|---|---|---|---|---|
| price / indicators / snapshot | ok | ok | ok | ok |
| company news (Finnhub) | ok | ok | **gone** | gone |
| global news (Finnhub general) | **unavailable** | unavailable | unavailable | unavailable |
| fundamentals ratios | ok | withheld | withheld | withheld |
| statements | ok | ok | ok | **gone** |
| macro (FRED, vintage-pinned) | ok | ok | ok | ok |
| sentiment | disabled | disabled | disabled | disabled |

**Finnhub's free tier stops at about twelve months** — 250 articles a week at
8 months, 247 at 11, 99 at 12, and **zero** at 13 and beyond, returned as HTTP
200 with an empty array rather than an error. **Global news is unusable for any
backtest at all**: Finnhub's general feed takes no date range and carries only
the last few days, so the coverage clamp refuses every historical window,
correctly.

**Google News RSS does serve deep history** — `after:`/`before:` in the query
return correctly dated items at 18 and 30 months. It is not the answer for the
eval, for two reasons that matter more than depth: volume decays with age (100
capped recent, 22 at 18 months, 12 at 30), so input quality would be
non-stationary across the test window and any early-vs-late difference would be
unattributable; and RSS carries title and date with no summary, so mixing it
with Finnhub puts a step change in input richness exactly at the 12-month
boundary. It belongs in the vendor chain for LIVE runs (gaps P1 — today proved
the case, when one dead vendor silenced the whole category), not in a
measurement that needs homogeneous inputs.

**FRED is now wired and is the one unlimited point-in-time source.** The token
moved from `FRED_API_KEY` — which nothing ever set, so macro was silently
unavailable for the project's whole life — to `pass://jaato/fred/api-key`,
alongside Finnhub's, read by `_pass_secret`. `realtime_start`/`realtime_end`
pin the vintage to the as-of date, so a revised figure cannot leak backwards:
verified returning VIXCLS as known on 2024-04-03.

**Consequence for the eval design: widen tickers, not history.** A two-year
window would run its older half as a technical-only pipeline — one analyst with
real inputs — which tests something other than what was built. So the window is
capped at roughly 2025-11-01 → 2026-09-22 (news coverage, less five sessions to
resolve each cell): about 46 weekly dates.

| design | cells | directional | 95% CI |
|---|---|---|---|
| 6 tickers x 46 dates | 276 | ~193 | ±7.1 pp |
| **12 tickers x 46 dates** | **552** | **~386** | **±5.0 pp** |

Twelve tickers rather than six, which independently answers the pilot's
correlation problem: NVDA and AMD are both AI semis, so its twelve cells over
two names carried far fewer independent observations than twelve suggests.

And the pre-registration must name what is being tested: with sentiment
disabled, no global news and no current ratios, this is a REDUCED pipeline —
market, news, statements-only fundamentals, and macro. Worth measuring, but not
the four-analyst design.

### The client venv moves to its own SDK (2026-10-09)

The architecture settled on 2026-10-06 — a client holds its own venv with the
SDK, the daemon is a shared service in its own environment — left one question
open: when does the client's SDK move? Answer, now recorded in `CLAUDE.md` §2:
when someone decides to, never as a side effect of pulling jaato. The daemon's
venv is reinstalled from the checkout on every pull; the client tracks a
PUBLISHED build, and `jaato-doctor`'s `package releases` check is the thing
that says a newer one exists.

Moved today: `jaato-sdk` 0.29.0 (PyPI) → **0.30.0rc6** (TestPyPI), against a
daemon running jaato-server 1.3.0 from source at `0ccb7069`.

* A `pip freeze` diff before and after changed **exactly one line**. Worth
  doing: `--index-url test.pypi.org --extra-index-url pypi.org` makes TestPyPI
  the PRIMARY index, so pip is free to substitute any dependency that happens
  to have a newer build published there. It substituted none, but the diff is
  what proves it rather than the absence of complaint.
* **137 unit tests and all 3 end-to-end tests pass** (4 m 55 s). Only the
  end-to-end tier means anything here: the unit tier never opens a session, so
  it cannot see a wire-protocol change. Both tiers were run because the thing
  that moved is the library that talks to the daemon.
* `jaato-doctor` then reported the Claude Code skill copy stale by version
  (`installed from 0.29.0, framework is 0.30.0rc6`) — the skill ships as SDK
  package data, so moving the SDK stales it by construction. Re-run
  `jaato-scaffold integration claude-code --force`. Doctor gained a `kernel
  confinement` check in this build (N/A without jaato-server here), and the
  SDK now carries a `references/apparmor.md`.
### `jaato-eval` belongs to the client, and that fixes which interpreter an arm runs (2026-10-09)

Moving the SDK surfaced that **`jaato-eval` was never in this venv**. It is a
THIRD package — not the SDK, not jaato-server — and it was only ever reachable
because the shared daemon venv happened to hold it. So the client venv as
`CLAUDE.md` §2 builds it could not launch the 564-cell sweep at all.

It is now declared as a `sweep` extra in `pyproject.toml` and installed
(`jaato-eval` 0.3.5rc1 from TestPyPI; one line in a `pip freeze` diff, nothing
substituted). It fits a client venv because it depends on PyYAML and
`jaato-sdk>=0.30.0.dev0` and **not** on jaato-server — and note that floor: on
0.29.0 it would not have installed, so moving the SDK was its prerequisite
rather than a coincidence.

The part that matters is not tidiness. `contract.py` sets

```python
contract["JAATO_EVAL_PYTHON"] = sys.executable
```

— **the interpreter jaato-eval itself runs under**, which every task's
`harness.run` and every `script` grader is written against. So the environment
that launches the sweep decides the interpreter each of the 564 arms executes
the driver with. Launching from the daemon venv hands every arm the DAEMON's
python, which is why that venv still carries `ta-cascade` (editable, pointing
at this repo) plus pandas, yfinance and matplotlib: the pilot ran on the
coupling the client/daemon split was meant to remove. Launching from the
client venv fixes it at the root — no flag, no wrapper, just the right process
starting the sweep.

Two residues worth knowing:

* The two venvs are slightly skewed — pandas 3.0.5 / numpy 2.5.0 in the
  daemon's, 3.0.6 / 2.5.3 in the client's. Patch-level and not a concern for
  the indicator maths, but it means the pilot's arms and this repo's unit
  tests did not run on the same build.
* `ta_cascade` in the daemon venv is **not** purely accidental:
  `.jaato/scripts/prefetch_sentiment.py` runs inside the runner and imports
  it (see §4, Prefetch). That path is only used by the sentiment analyst,
  which is out of `DEFAULT_ANALYSTS` and out of this sweep — so the sweep does
  not need it, but removing it from the daemon venv would break a sentiment
  run.

Verified from the client venv, with the daemon at jaato-server 1.3.0:

* `discover_tasks()` parses **all 564** manifests — 564 distinct task ids, 12
  tickers x 47 dates, every one `harness.kind: driver`, `profile_set:
  minimax_m3`, one `script` grader, `repeats: 1` -> 564 arms. The matrix the
  installed jaato-eval sees is the registered design.
* `budget` resolves to an empty `BudgetSpec(limits={}, degrade=[])`, not a
  pool, so the generator's "no budget block on purpose" comment still holds
  and each stage's own `budget_control` governs.
* One throwaway `echo` arm run through the CLI end to end: PASS, results
  written, cost rendered `—` rather than `$0.00` (the same three-state money
  rule `sweep.py` keeps).

`jaato-eval run` prints `JAATO_RUNNER_POOL_SIZE should be >= N` on every run.
It is static advice — `pool_size_advice(concurrency)` reads no environment
(`cli.py:96`) — not a reading of the daemon's actual pool, so it is not
evidence that the pool is short.

### The one check that could catch a client/daemon skew cannot fail (2026-10-09, jaato#1610)

The 2026-10-09 pull left `jaato-doctor` reporting

```
✔ PASS  jaato_sdk checkout   client and daemon both resolve jaato_sdk from
                             …/.venv/lib/python3.12/site-packages/jaato_sdk (0.30.0rc6).
```

They do not. The daemon imports the editable source checkout
(`…/jaato/jaato-sdk/jaato_sdk/__init__.py`, 0.30.0); this venv imports the
installed rc (0.30.0rc6). A source tree against an installed copy is the case
`_skew_verdict` grades **FAIL** by design. Doctor printed OUR path as the
daemon's and called it agreement.

Re-checked by hand on 2026-10-11 before launching the third AAPL batch, with
the recipe this file prescribes: still 0.30.0 (daemon, source checkout)
against 0.30.0rc6 (this venv), and doctor still PASSes. Re-checked again after the
2026-10-11 pull to `b120c2ce` and reported on the ticket: **both sides
declare the same version strings** (jaato-sdk 0.30.0 vs 0.30.0rc6,
jaato-server 1.3.0 either way), so a pull that changes behaviour without a
version bump leaves nothing in pip, doctor or a session record to tell the
two builds apart — only the commit. The pairing is not a
blocker — it is what the two completed arms of batch one and the whole
end-to-end tier ran against — but no check in doctor would tell us if it
became one.

Root cause, every predicate measured rather than argued:

```
info.executable   : /usr/bin/python3.12        <- readlink /proc/<pid>/exe
sys.executable    : …/.venv/bin/python
realpaths equal?  : True
other_interpreter : False          <- the guard needs True to fire
daemon PYTHONPATH : (empty)
_resolve_package_on(entries, "jaato_sdk") : None
_daemon_package_dir("jaato_sdk", …)       : (…/.venv/…/jaato_sdk,
                                   'the installed package — the same one you resolve')
```

`check_checkout_skew` guards the installed-package fallback with
`realpath(info.executable) != realpath(sys.executable)`. A venv's `bin/python`
is a symlink to the system binary, so **two venvs over one system Python
collapse to the same realpath**. Every condition for the WARN holds except
that one, so the guard is skipped and the fallback answers with the caller's
own site-packages — its own source string admits the assumption, "the same one
you resolve". The fix has to compare ENVIRONMENTS (`/proc/<pid>/cmdline`
argv[0] names the daemon's venv interpreter; `VIRTUAL_ENV` is absent when a
daemon is started by absolute path, as ours is), not binaries.

Why it matters here rather than in general: the client-venv split
*guarantees* the two sides run different builds, and `dependency coherence`
and `jaato_server checkout` are already unavailable to us under #1576 — they
say so honestly. So `jaato_sdk checkout` is the only remaining check that
could detect a framework mismatch, and it asserts health instead. A false PASS
is the dangerous direction, because the failure it predicts is silent by
construction: pydantic drops the unknown event field on ingest and the
`AttributeError` surfaces frames from the cause.

Until it is fixed, compare by hand when it matters:

```bash
/home/apanoia/.local/share/jaato/venv/bin/python -c 'import jaato_sdk; print(jaato_sdk.__file__)'
.venv/bin/python -c 'import jaato_sdk; print(jaato_sdk.__file__)'
```

Worth noting for our own habit: this was found only because the ritual asks
doctor to prove no skew between client and daemon. The check it relies on for
that has been vacuous for as long as the client has had its own venv, and the
PASS is what hid it — three health checks in a row reported it green.

### `validate` exits 1 on other projects' profiles (2026-10-09)

`jaato-scaffold validate . --set <set>` now exits **1** on this workspace, and
nothing in this workspace causes it.

Evidence:

* `--json` tags every finding with a `tier`. This workspace's findings are
  `tier: workspace` and number 3 / 3 / 2+13 across the three sets — the
  baseline unchanged since 2026-10-06, with **zero errors**.
* The run also walks the USER tier and reports **105 further findings,
  including all 13 errors**. Corrected 2026-10-09 (an earlier version of this
  entry called them "other projects of this user", which is wrong for 11 of
  the 13): **11 are jaato-premium's OWN bundled profiles**, which the daemon
  discovers because `jaato-premium` 0.1.209 is installed in ITS venv —
  `skill-mod-code-*`, `skill-code-001-add-circuit-breaker-java-resilience4j`.
  The remaining two are the user's, from `~/.jaato/profiles/`:
  `editor-assistant` and `gen-references`. So most of what buries our findings
  ships with the framework rather than belonging to a neighbour, which makes
  the exit-code coupling worse, not better — a client cannot remove them.
* `validate . --set minimax_m3` → exit **1**;
  `validate . --set minimax_m3 --profile trader` → exit **0**.

Two of those 13 are a stale profile of the user's, and the other **11 share
one root cause** — worth separating from the exit-code defect, because it is a
real disarming of real profiles rather than noise:

```
[error] skill-mod-code-002-retry: plugin_missing_tier: plugin 'auto_steering'
  declares no PLUGIN_TIER, so the runner will not load it — this session would
  come up without its tools. Add PLUGIN_TIER = "runner" to the plugin
  package's __init__.py
```

All 11 name `auto_steering`, and the source confirms the validator:
`jaato_premium/auto_steering/__init__.py` declares no `PLUGIN_TIER`. The
convention is established on both sides — jaato's own plugins declare it in
the package `__init__.py` (`artifact_tracker`, `ast_search`, `anthropic_auth`
…), and premium's own `session_ops` declares
`PLUGIN_TIER = "daemon_callable"`; it is the only one of premium's 14 packages
that does. So one missing constant silently disarms 11 premium profiles: they
come up without the tools they declare, and nothing at session time says so.

Filed 2026-10-09 as **jaato-premium#81**, split out of jaato#1217 where it was
recorded as a separate defect awaiting its own ticket. Not ours to fix
(jaato-premium, in the daemon's venv), but validate surfaces it on every run
of this ritual, which is how it resurfaced. Note the fix is probably
package-wide, not only `auto_steering`: 13 of premium's 14 packages declare no
`PLUGIN_TIER`, and they stay quiet only because no shipped profile names them
yet.

Walking the user tier is defensible by itself: `~/.jaato/profiles/` is a real
fallback in the resolution path, and a profile name this workspace does not
define can resolve there, so a reader should know it is broken. The defect is
narrower — **the exit code ignores the tier the target names**. `validate
<workspace>` is a verdict on that workspace; a user-tier error is a fact about
the environment, not a fault in the target. Two consequences here: the §10
pre-commit gate (`validate --set openrouter_sonnet && validate --set echo`)
fails on every commit touching `.jaato/` for a cause no one can fix from this
repo, and 105 of 108 printed lines bury the 3 that are ours.

Already filed as **jaato#1217** (open), with a fresh reproduction added
2026-10-09: the three foreign counts are byte-identical to the original report
on sdk 0.26.0 / server 0.20.0 / premium 0.1.207 — `user error 13 / info 21 /
warn 71` — while this workspace's own went 16 warn -> 3 warn. The exit code
never moved, because it was never reporting on the workspace. 105 of 108
printed lines are foreign: 3% of the output is about the target.

And in a correct client/daemon split the author cannot even SEE the packages
that decide their exit code — `jaato-premium` lives in the daemon's venv, not
the client's.

Until it is fixed, judge this workspace by `tier` (`--json`) or
`grep '[workspace]'`, not by the exit code. Not a workaround in code — no
driver behaviour depends on it — just how to read the output.

### A sweep's memory scales with concurrency × 5, not concurrency (2026-10-09, jaato#1622)

The first batch of the 564-cell `predict-2026-10` sweep was launched at
`--concurrency 4` and had to be abandoned: the box reached **23–25
`jaato_server.server.runner` processes**, available memory fell 2257 → 617 MB
and swap was fully consumed (2047/2047 MB). Seven arms had been recorded, all
seven are voided, and the registration says so
(`docs/preregistration-2026-10.md` §10, 2026-10-09).

**Why, with the evidence.** A runner slot serves ONE session. A cascade's
sessions share slot *affinity* through `cascade_driver_id`, which is not the
same as sharing a slot — and this pipeline deliberately keeps several sessions
of one cascade open at the same time: the bull and bear debate on two
long-lived sessions, the risk panel on three. Each of those concurrent
sessions therefore takes a PURE IDLE slot and stamps it with the same cascade
(`PoolManager.acquire_slot` path 2). Counted from `/tmp/jaato.log.1` over the
batch's seven cascades: **29 `cascade reuse MISS` to 19 `HIT`**, and each of
the two arms that completed shows **5 MISS / 6 HIT** across its 11 sessions.
So one arm holds about five runner processes at peak, ~170 MB each. Four
concurrent arms is ~20, plus the virgin floor (`JAATO_RUNNER_POOL_SIZE`) and
the per-cascade reservations that linger for the pool's 300 s
`cascade_idle_timeout_seconds` — which is the 23–25 observed. Re-running at
`--concurrency 2` with the pool at its default 2 gives 9–11 runners, the same
ratio.

**A MISS is not a cold spawn,** and the first version of this finding said it
was. `acquire_slot` logs "cascade reuse MISS — fresh slot" when it takes a
warm pure-idle slot and stamps it; "fresh" means freshly stamped. Cold-spawn
is only the path where no idle slot qualifies at all. So the latency half of
`jaato-eval`'s pool advice is sound and `JAATO_RUNNER_POOL_SIZE` is not what
the memory went on.

**Filed as jaato#1622**, because what is wrong is in the framework and not
here: `jaato-eval`'s `pool_size_advice` prints
`JAATO_RUNNER_POOL_SIZE should be >= {concurrency}` on the stated assumption
that "each simultaneous arm needs its own warm slot", which holds for a
single-session arm and for a strictly sequential cascade but not for a
`harness.kind: driver` arm with concurrent sessions. It is the only guidance a
sweep planner is given, it is read as a resource estimate, and it understates
this harness by 5×. The issue suggests the sweep report observed
slots-per-arm from the daemon's own `cascade_slot_reuse_*` counters after the
first arm, rather than guessing.

**What this repository changes: nothing in code.** The number to pick is
`--concurrency`, and it is picked from measurement — `concurrency × 5 × 170 MB`
is the floor on what a sweep will occupy, against `free -m`'s *available*
column, not its *free* one. No driver behaviour depends on the pool, and
adding a knob here to compensate for a framework estimate would be the
workaround this project does not write. `CLAUDE.md` §4 carried the wrong claim
("they share one warm runner slot") and has been corrected.

**One thing this does not explain.** `AAPL/2025-11-03` FAILed at
`fundamentals_analyst` with `DriverStoppedShort: driver exited 1`,
`nudges=0`, `finish=stop`, no budget ceiling reached and no gate refusal — so
it is neither nudge exhaustion nor a budget abort, and there is no evidence
either way on whether contention caused it. Carried as open: if that cell
fails the same way on a quiet host, the cause is in the pipeline.

### `get_fundamentals` raised a NameError for six days and nobody could tell (2026-10-09, fixed 2026-10-11)

`ta_cascade/tools.py` built the fundamentals analyst's `get_fundamentals`
spec with a lambda closing over `stale`, a name bound in `market_tools` and
never in `fundamentals_tools`. Every call, every ticker, every date answered:

```
DATA_UNAVAILABLE: <lambda> could not be retrieved (NameError: name 'stale' is
not defined). Do not estimate or invent these values; state that the data was
unavailable.
```

Reproducible in one line, no network and no daemon — which is the measure of
how cheap this was to catch and was not:

```python
tools.fundamentals_tools(RunConfig(ticker="AAPL", trade_date="2025-11-17"))
```

`git blame` puts it on `9a9aa2d`, 2026-10-03 — the commit that stopped the
`info` block being lookahead. `fundamentals()` gained a `max_stale_days`
keyword, `market_tools` gained the local binding it needed, and
`fundamentals_tools` did not.

**Three separate failures let it stand, and the fix addresses each.**

**1. The exception was rendered as a data failure.** `data.with_deadline`
caught everything and returned `_unavailable(...)`, so a typo in our own code
produced a sentence indistinguishable from a dead endpoint. The data layer's
contract — never raise, every failure is a sentence (§7 of `CLAUDE.md`) — is
about DATA failures; it was never meant to cover our bugs. `with_deadline`
now re-raises `NameError` and `AttributeError` (`data.BUGS_NOT_DATA`). The
scope is deliberate and narrow: its only caller is `tools._spec`, whose `fn`
is one of our own lambdas, and a lambda does nothing but call a function in
`data` that already catches its own library errors — so one of those two
exceptions arriving there is ours. The same narrowing is NOT applied inside
`data`'s own handlers, where an `AttributeError` is usually yfinance choking
on a bad response, and guessing which it was would be the inference the data
contract exists to avoid. `gather_with_deadline` is also left alone: it runs
the sentiment prefetch inside the runner at session-prep, where an exception
kills the session (trap #1), and its job is isolation.

**2. The test asserted the handler EXISTS.** `test_specs_are_well_formed`
checks `callable(spec["handler"])`, and a lambda body is only resolved when it
runs, so the unbound name was invisible to it.
`test_every_handler_can_actually_be_called` now calls every handler once with
the data layer stubbed and schema-derived arguments, so a new tool is covered
the day it is added. **The first version of that test was worthless** — the
stub loop replaced `with_deadline` too, so `guarded` returned the stub without
ever running the lambda, and the test passed with the bug reintroduced.
Verified the corrected version by reintroducing the bug: it fails with the
NameError, which also proves the re-raise above works.

**3. A non-empty `errors[]` stops the run, and a blank string is non-empty.**
This is what turned one broken tool into lost cells. The analysts reported the
unavailable tool honestly, and WHERE they reported it decided the arm:

| cell | `errors[]` | arm |
|---|---|---|
| AAPL/2025-11-03 | `["get_fundamentals returned NameError ('stale'); no headline ratios available for valuation"]` | FAIL |
| AAPL/2025-11-17 | `[""]` | FAIL |
| AAPL/2025-11-10, AAPL/2025-11-03 | `[]`, same tool failure filed under `warnings` | PASS |

Two FAILs in six settled arms, from one deterministic bug and a
model-dependent choice of field. The schemas already SAID so — the `errors`
description reads "never a placeholder such as "none", "n/a" or """ and "put
anything that is merely a caveat in warnings" — and the model ignored it. A
description is a request; `"minLength": 1` on the items is a constraint, so
`[""]` is now refused by the daemon when `signal_completion` is validated and
the model is told why, instead of being interpreted by the driver afterwards.
Applied to all five schemas, not just `analyst_report`: the shape and the
driver's rule are identical in every gated stage, and fixing one would have
left the same trap in four.

**What was NOT changed, and why.** A genuine `errors[]` entry still fails the
stage — that is the contract, and it is right. Whether a tool reporting
`DATA_UNAVAILABLE` *belongs* in `errors` or `warnings` is still decided by the
model rather than by the pipeline, and making that a persona edit is a change
to what is under test, so it is left open rather than slipped in
mid-experiment.

**Cost.** The second AAPL batch is voided
(`results-VOIDED-2026-10-09-broken-get-fundamentals.jsonl`; registration §10),
because all three of its arms ran against the broken tool. The scientific
impact is smaller than the operational one: §2 of the registration already
withholds the `info` ratios from a historical cell, so a working
`get_fundamentals` returns the withheld-notice plus the company identity —
which the model also receives in `instrument_context`. What the analyst could
SEE barely changes. What changes is that a third of the arms stop dying.

**And possibly which FIELD the analyst files it under** (first arm of the
third batch, 2026-10-11 — one observation, stated as a hypothesis the batch
will settle). Both sentences open with `DATA_UNAVAILABLE`, but they are not
equivalent:

| | what the analyst read |
|---|---|
| until 2026-10-11 | `DATA_UNAVAILABLE: <lambda> could not be retrieved (NameError: name 'stale' is not defined)` |
| after | `DATA_UNAVAILABLE: the info block's valuation and performance ratios are undated — they describe today, N days after <as_of> — so quoting them here would be reading the future. They are withheld. Use `get_statement` for figures dated on or before <as_of>…` |

The second states a reason, says the withholding is deliberate, and names the
substitute. The first states nothing. On `AAPL/2025-11-10` the analyst
paraphrased the second accurately — "the headline ratios it normally returns
were undated and described a date roughly 335 days after the analysis date —
i.e. they would be reading the future. I am not using them. All numbers below
come from the three statements." — and filed it under **`warnings`**, then
wrote a full report from the statements. Under the broken sentence, the same
tool's silence went into `errors[]` and stopped the run.

If that holds across the batch, the persona edit considered as option D (tell
the analysts explicitly that an unavailable tool is a warning) is unnecessary:
the sentence that explains itself does the work, and the fix for the field
choice was the fix for the bug. If some arms still file it under `errors`, the
batch measures the rate, which is the number that would justify a
model-facing change. Either way it was right NOT to edit the personas at the
same time as fixing the bug — doing both would have made this unmeasurable.

**Narrowed the same day, by a failure with the same symptom and a different
cause.** The hypothesis above holds for the fundamentals analyst — 17 arms in,
every one of its reports carries `errors: []`. But `AAPL/2026-02-23` died of
`DriverStoppedShort` with `errors: ['no-error-placeholder']`, from the
PORTFOLIO MANAGER, which had nothing to report and no broken tool. See the
next finding: the disease there is the protocol, not the sentence.

### A required array that is normally empty is a trap in field-by-field completion (2026-10-11, jaato#1626)

`AAPL/2026-02-23` completed every stage — three analyst reports, both
debates, the research plan, the trader proposal — and then was discarded with
a valid `Hold` sitting in the payload, because `errors` arrived as
`['no-error-placeholder']` and `pipeline._require` treats a non-empty
`errors[]` as `StageFailed`.

**What actually happened**, from the session's own history (`.jaato/sessions/`,
the `function_call` parts; note they are flat with a `type` discriminator —
`{"type": "function_call", "name": …, "args": …}` — not nested under a
`function_call` key, which cost one wrong reading first):

| turn | call |
|---|---|
| 1 | `prepare_completion("errors", "[]")` — the STRING `"[]"`, not an empty array |
| 5 | `prepare_completion("errors", "")` |
| 7 | `prepare_completion("errors", "[]")` |
| 11 | `prepare_completion("errors[0]", "no-error-placeholder")` |
| 13 | `prepare_completion("errors", "")` |
| 15 | `prepare_completion("errors[0]", "no-error-placeholder")` |
| 17 | `signal_completion()` — arg-less, the framework synthesizing from accumulated state |

Eight turns spent trying to say "there are no errors". `explain plugin
lifecycle` is explicit that `prepare_completion`'s `value` takes whatever the
schema expects for that path, arrays included, so an empty array IS
expressible and the framework was right to reject each attempt. The model
could not produce one. What it eventually found was that indexing `errors[0]`
is accepted — and an array with an element is not empty.

**It is the protocol shape, not the agent.** Across the first 17 arms
(~110 sessions) M3 completes ONE-SHOT almost always — 16 to 19 sessions per
agent — and one-shot gets `errors: []` right every single time. Field-by-field
occurred 7 times, and all 7 flailed the same way:

| cell / agent | sequence | outcome |
|---|---|---|
| 2026-01-05 news | `"[]"` → `errors[0]=""` → one-shot `[]` | recovered |
| 2026-01-12 news | `"[]"` → `errors[0]=""` → one-shot `[]` | recovered |
| 2026-02-02 fundamentals | `"[]"` → `errors[0]="__PLACEHOLDER__"` → `""` → one-shot `[]` | recovered |
| 2026-02-23 fundamentals | `"[]"` → `""` → `errors[0]=""` → one-shot `[]` | recovered |
| 2026-03-02 fundamentals | `"[]"` → `""` → one-shot `[]` | recovered |
| 2025-12-15 research manager | `"[]"` → `["none"]` → `""` → `errors[0]=""` → … | recovered |
| **2026-02-23 portfolio manager** | `"[]"` → `""` → `"[]"` → `errors[0]="no-error-placeholder"` | **arm lost** |

Six recovered by abandoning field-by-field for one-shot. The seventh satisfied
`is_complete` with a token instead, and `signal_completion()` fired on a
payload whose `errors` field said, in words, that it was a placeholder.

This is the `prose_tool_calls` quirk that `explain provider minimax` names and
does not describe, and that `.jaato/profiles/minimax_m3/` records as
unmeasured here. It is now measured: it does not garble prose, it sends a
JSON-ish STRING where a typed value is expected, and the only field in these
five schemas where that is fatal is an array whose correct value is empty.

**`minLength: 1` neither caused nor fixed it.** Without the constraint the
same path lands on `errors[0] = ""`, i.e. `[""]`, which is non-empty and kills
the stage identically — that is precisely the second batch's signature. The
constraint changed the token, not the outcome.

**Cost, and what it is not.** One arm of 17 (~6%). A `DriverStoppedShort` arm
is recorded `FAIL`, not `BLOCKED`, so it spends none of §7's 57 permitted
exclusions, yet it yields no rating and so contributes nothing to §4 — the
sample shrinks silently. At this rate ~33 of 564 cells would vanish without
moving the kill switch. Whether a pipeline failure should count against §7 is
a registration question, recorded in the preregistration rather than decided
here.

**Not fixed while the batch runs**, so that all 47 arms run one pipeline. Two
changes are proposed for the batch boundary:

- **Drop `errors` and `warnings` from `required` in the five schemas.**
  `pending_required_fields` then never asks for them, `is_complete` goes true
  without the model touching them, and absence means no error. `_require`
  already reads `payload.get("errors") or []`, so **the driver needs no
  change** — it handles absence today. The cost is the strict-shape
  convention (`additionalProperties: false` plus exhaustive `required`) that
  every schema here follows.
- **Filed as jaato#1626.** Eight turns of rejection never taught the model
  the accepted shape, and the quirk doing the damage is one the provider
  profile already declares. The trap is generic to any schema with a
  normally-empty required array, which makes it the framework's to carry
  rather than this driver's. The issue asks first for a rejection message
  that shows the accepted form, which on the evidence would close it on its
  own, and notes that the author-side mitigations do not work: `minLength: 1`
  is satisfied by `"none"`, and a description forbidding `"none"` by name was
  ignored twice in those words.

**Second instance, 24 arms in, and it narrows the cause.** `AAPL/2026-04-27`
died the same way at the RESEARCH MANAGER, six sessions in:

```
prep errors   = "[]"                               (string)
prep warnings = "[\"Headline valuation ratios …"   (string holding JSON)
prep errors   = ""
prep warnings = ["Headline valuation ratios we…]   <- correct ARRAY, second try
prep errors   = ["none"]                           <- correct array, placeholder content
signal(args)
```

The model mangles an array value once and then **gets it right** — `warnings`
arrives as a proper array on the retry. What it never produces is an EMPTY
array: for `errors`, whose correct value is `[]`, it substituted `["none"]`.

So the trap is not array typing, which works. It is specifically **a required
array whose correct value is empty**, and that is the whole of it. Two
consequences:

- The proposed fix is the right shape: dropping `errors`/`warnings` from
  `required` removes exactly the field the model cannot express and leaves
  array handling, which is fine, untouched.
- `"none"` is the placeholder the schema's own description forbids **by
  name**, and `minLength: 1` accepts it at four characters. A description does
  not constrain a model; structure does. That is the second time in two days
  this repository has learned it — the first was the `[""]` these descriptions
  also already forbade.

Rate after 24 arms: 2 lost (~8%).

**FIXED upstream (2026-10-14, jaato `513f937b`, issue closed 2026-10-13).**
Present from jaato `976c3773`, the build this workspace's daemon now runs.
Four changes, all four of what would have closed it:

- `"[]"` on an array path is converted to `[]` (the #1358 coercion rule
  applied to the leaf schema), so the shape the model kept sending is now the
  shape that works. `""` is still refused, correctly.
- a rejection on an array or object path **names the accepted shape**
  (`value=[] for none`) — the one ask that, on this repository's evidence,
  would have closed it alone.
- every pending array field that may be empty (no positive `minItems`) carries
  `set_empty_with` — the literal call,
  `prepare_completion(field_path='errors', value=[])` — in every
  `prepare_completion` and `query_completion` answer, so the accepted form is
  in front of the model on every turn rather than discoverable by luck.
- the tool and value-parameter descriptions name the empty array.

**So the queued schema change is retired.** Our five schemas declare no
`minItems` — the `minLength: 1` added on 10-11 sits on the ITEMS, not the
array — so `set_empty_with` reaches `errors`, `warnings` and `tools_used` with
the schemas exactly as committed. Dropping `errors`/`warnings` from `required`
is no longer needed to make an empty array reachable, and the strict-shape
convention is kept. What remains is to confirm it on the first live arms: the
observable is a completion that sets `errors=[]` directly instead of the
`errors[0]=<placeholder>` this entry was written about.

### `TOOL_BUDGET_S` is 45s and the daemon gives a client tool 30s (2026-10-11, jaato#1625)

`AAPL/2026-05-18` died at the news analyst with every one of its tools
reporting, verbatim to the model:

```
{"error": "Client tool get_company_news timed out after 30.0s"}
```

Six calls, `get_company_news`, `get_global_news`, `get_insider_transactions`
and `get_macro_series` ×3. `turn_accounting` shows all six **started within 27
milliseconds** of each other (13:38:17.4887 → .5150) and all six cut at
30.05s, so dispatch is parallel and the clock is one the DAEMON keeps.

**`tools.py` sets `TOOL_BUDGET_S = 45.0`.** It is larger than the daemon's
budget, so for any handler taking between 30 and 45 seconds our deadline is
dead code: the daemon answers first and the model receives a raw transport
error instead of

```
DATA_UNAVAILABLE: <tool> did not answer within 45s. Do not estimate or invent these values.
```

That sentence is the data layer's whole contract (§7 of CLAUDE.md) — the
instruction not to invent travels WITH the failure, and the three kinds of
nothing stay distinguishable. A `{"error": …}` object carries none of it.
The fix is to put `TOOL_BUDGET_S` below the daemon's budget so ours fires
first; it is **not** applied mid-batch, so that all 47 arms run one pipeline.

**The clock is undocumented.** `jaato-scaffold explain clients` prints a
table introduced as "every clock between connect and a turn's terminus", and
this one is not in it — not in the shipped snapshot and not when a running
daemon is asked with `--connect`. Nor does `explain env` expose a knob for
it: the only timeouts there are `JAATO_EPHEMERAL_TIMEOUT_S`,
`JAATO_RUNNER_ACK_TIMEOUT`, `JAATO_CREDENTIAL_LOCK_TIMEOUT`,
`JAATO_CLARIFICATION_TIMEOUT` and `JAATO_PERMISSION_TIMEOUT`. Filed as **jaato#1625**: a driver cannot size its own handler budget
against a limit the framework does not state, and introspection is supposed
to be the source of truth. The issue asks for three things in order — put the
clock in the `explain clients` table, expose it like the other per-concern
clocks, and ideally return it from the handshake that accepts `client_tools=`
so a client derives its deadline instead of guessing.

**FIXED upstream (2026-10-14, jaato `991be687`, issue closed 2026-10-14).**
Present from jaato `976c3773`. `explain clients` now carries the row:

```
30s   client_tools=[{'timeout': <ms>}] per tool        both
      ONE host-tool call, daemon-side (the spec value is in ms)
      on expiry: the MODEL gets {"error": "Client tool <name> timed out after <N>s"}
```

and states the rule this entry had to derive from a dead arm — *"A host tool's
handler that applies its own deadline (to return an answer the model can read)
must fire BEFORE the daemon's"* — and the handshake now reports the budget:
`register_client_tools()` returns `{name: seconds}` per tool and keeps it on
`client.client_tool_timeouts` (protocol 1.39+). All three asks, in the order
they were asked.

**The two halves cost differently here, measured in the installed SDK rather
than assumed.** SETTING the budget needs no SDK move: 0.30.0rc6's
`register_client_tools` already documents an optional `timeout` in ms and
forwards every spec key except `handler`, so a `timeout` on each spec in
`tools.py` reaches the daemon today. READING it does need one: rc6 returns
`None` and carries no `client_tool_timeouts`; `jaato-doctor`'s
`package releases` check names 0.30.0rc16 on TestPyPI. So the fix for
`TOOL_BUDGET_S` is now a choice between making our number the daemon's number
(one spec key, no SDK move) and deriving ours from the daemon's (no hardcoded
number anywhere, but the client SDK moves first) — not the blind lowering this
entry originally proposed.

**CLOSED HERE (2026-10-14): the deriving one, by operator decision.** The
client venv moved to `jaato-sdk` 0.30.0rc16 (one line in `pip freeze`, nothing
substituted) and `TOOL_BUDGET_S` is gone:

- `tools.handler_deadline_s(spec)` asks `jaato_sdk.client_tool_timeout`, the
  module the DAEMON's registration path also calls, for the budget that spec
  will be held to, and subtracts `tools.HANDOFF_MARGIN_S`. No budget is
  written down in this repository, so if the framework's default moves, every
  handler follows it. The margin — 5 s, covering the result event's trip back
  — is the only number left, and it is a margin, not a budget.
- `sessions.check_tool_budgets` compares the derived numbers against what the
  daemon REPORTS for that session (`session.client.client_tool_timeouts`,
  protocol 1.39+) and raises `ToolBudgetMismatch` on any disagreement,
  including a daemon too old to answer. It runs inside `_accounted` after
  registration and before the stage's first turn — the first moment the
  answer exists and the last before the model can call a tool — so a
  disagreement fails the stage instead of being discovered in a dead arm.
- a tool that needs longer does not get a bigger constant: it declares
  `timeout` (ms) on its spec, and its deadline follows. `handler_deadline_s`
  refuses a budget smaller than the margin rather than clamping it.

**What this does and does not buy.** Every handler now fires at 25 s against
the daemon's 30 s, so a stalled dependency reaches the model as the data
layer's sentence rather than as a transport error — which is what killed five
arms. It does NOT make slow data arrive: `data.FINNHUB_TIMEOUT_S` is 20 s with
one retry, a ~40 s worst case that still exceeds the budget, so a Finnhub
stall now produces our sentence instead of their error. Making the data arrive
is a separate sizing decision — either declare `timeout: 50000` on the three
news specs, or cut the data layer's own retry so the chain fits inside 25 s —
and it is not taken here.

**What stalled THIS arm is not established.** Lowering the budget would have
produced six of our own sentences at 25s rather than six transport errors at
30s; it would not have made the tools answer. Candidates and their standing:

- *Host starvation of one driver process.* Fits that exactly one arm of 26
  was hit while its concurrent neighbour was fine, and the box carries 2 GB
  of swap in use. But there is **no load measurement from 13:38**, so this
  is a hypothesis, not a finding.
- *`pass`/`gpg-agent` contention.* Every one of the six tools needs a
  pass-store credential, and the `market_analyst` session that succeeded 60
  seconds earlier uses only yfinance tools, which need none — a striking
  correlation, and `functools.lru_cache` does not deduplicate IN-FLIGHT
  calls, so six cold concurrent lookups do spawn six `pass` subprocesses.
  **But it does not survive the retries:** `_pass_secret` has
  `timeout=10` and caches its `None`, so a stuck `pass` would make later
  calls return instantly rather than time out again at 30s, and every retry
  across 3.5 minutes timed out. Recorded as refuted on present evidence.

What would settle it: sampling load and per-process state during a sweep, or
logging the handler's own elapsed time inside `with_deadline` so the driver's
view and the daemon's can be compared directly. Neither exists yet.

**Three pipeline failures in 26 arms (~11.5%), three causes** — two of them
the empty-array trap above (portfolio manager, research manager) and this
one. The arms are recorded `FAIL`, so none spends a §7 exclusion; see the
preregistration's open question of 2026-10-11.


**A better way to stop a sweep, learned here.** `SIGINT` to the `jaato-eval`
parent recorded three arms and **zero BLOCKED** — the two in flight were
simply not written, so `--resume` re-runs them. `pkill` on the driver
processes, which is what was done two batches earlier, recorded four arms as
`BLOCKED` and would have spent four of the 57 permitted exclusions on the
operator.

**But SIGINT stops the RECORD, not the work** (found 2026-10-11, while
preparing the third batch). Two arm workspaces for cells the stop had left
unrecorded — `AAPL/2025-11-24` and `AAPL/2025-12-01` — were sitting in the
live `--workspaces` root with directory mtimes of 23:05 and 23:07, *later*
than the copies already moved aside at 22:55 and 22:58, and carrying a
`report.md` those copies did not have. The arm drivers had outlived the
parent: the move pulled their directories out from under them, they
recreated them and ran on to write a report (2–3 and ~7 sessions, against
the 11 of a settled arm).

Two consequences, both operational:

- **Wait for the drivers to exit before touching workspaces.** Moving a
  workspace while its driver runs does not orphan the driver, it orphans the
  directory: a fresh one appears in its place and the voided run finishes
  into it.
- **An unrecorded arm is not an arm that did not run.** These two spent real
  provider budget that appears in no `results.jsonl`, so a sweep's cost read
  from the results file alone understates what was actually bought. It is
  the same shape of error as keying `sweep.py` by cell instead of by arm,
  which read the pilot's $47 as $9.

They were moved to `/tmp/predict-2026-10-ws-VOIDED-orphans-after-sigint/`
rather than deleted, for the same reason the other two batches were: the
re-run reuses arm workspace paths deterministically, and
`python -m ta_cascade.score` grades whatever report tree it finds under
`./results`. A voided run's `portfolio_decision` left in place would have
been graded as the new one's if a re-run failed before overwriting it.

### `--no-memory` does not gate the READ of past decisions (2026-10-11)

Every backtest arm runs the driver with `--no-memory`, and `cli.py:194`
turns that into `record_decision=False, resolve_pending=False`. Both are
honoured. But `pipeline.run` builds `past_context=memory.past_context(...)`
unconditionally a few lines further down, so the flag suppresses *writing* a
decision and *scoring* the pending ones while still **reading** the log and
handing it to the portfolio manager.

The log it reads is `~/.ta_cascade/decisions.jsonl` by default
(`config.py:119`) — one file shared by every arm of every sweep and every
manual run on the box, unless `TA_CASCADE_DECISION_LOG` says otherwise, and
no `task.yaml` sets it.

**Nothing leaked into the AAPL batch, and the reason is the point-in-time
filter, not the flag.** The shared log holds four entries, two of them
`resolved` (NVDA 2026-09-04 and 2026-09-22). `past_context` keeps a resolved
entry only when `resolved_on <= as_of`, and `as_of` is the cell's trade date
— every AAPL cell is in 2025, every resolution is in 2026, so the filter
drops both and `past_context` is `""` for all 47 cells. Verified by reading
the log and the filter, not inferred from the flag.

So this is a latent gap rather than a live defect: a cell at or near the
present date would be served another ticker's lessons from whatever else
had run on the machine. It is deliberately **not** fixed while a batch is in
flight — changing `pipeline.run` mid-sweep would mean the 47 arms did not
all run the same pipeline, which is the one thing a batch has to guarantee.


### A swap-exhausted host cannot measure the end-to-end tier (2026-10-14)

The first end-to-end run of the derived-deadline tree failed — `1 failed,
2 passed in 407.18s`, with `StageFailed: session could not be created:
session.new was sent but not answered within 60.0s`. **It was not the
change.** Two facts rule it out: the 60 s clock fires inside
`create_session`, before `sessions.check_tool_budgets` is reachable at all,
and no `ToolBudgetMismatch` appears anywhere in the output.

What the evidence did say, gathered rather than assumed:

- the daemon's runner pool was at capacity **4/4** with two cascade ids live,
  tearing slots down `reason=over-capacity` repeatedly;
- the 5-minute load average was **7.31**;
- a unit tier run concurrently took **71.41 s** instead of its usual ~6 s;
- the tier itself took **407 s** against a ~272–294 s baseline;
- the host: **10714 of 11902 MB used, swap 2047/2047 EXHAUSTED**, 973 MB free,
  load 11.03. The consumers were another project's benchmark (a 743 MB
  template-mode runner plus a 608 MB `bench_references_daemon.py --size
  1000`), our own daemon at 527 MB, **16 runners totalling 3.34 GB**, six
  `claude` sessions and Keycloak at 372 MB.

Re-run alone on a quiet box: **3 passed in 300.52 s**. So the cause was
contention, and the arithmetic explains it — this pipeline claims ~5 runner
slots per concurrent cascade at ~170–200 MB each (#1622 and §4 of CLAUDE.md),
and a `session.new` confirmation has to wait for a slot that memory cannot
supply.

**Rule.** The end-to-end tier is not a measurement on a host with no free
memory. Read a `session.new` timeout there as a host finding, re-run alone,
and only then suspect the tree. The lesson that cost the time is narrower and
is mine: do not run a second test tier against a shared daemon whose pool is
sized for one cascade.

### The sentiment prefetch put a driver package in the daemon's venv (2026-10-17)

**What was wrong.** `ta_cascade` was editable-installed into the SHARED daemon
venv (`~/.local/share/jaato/venv`, `INSTALLER: pip`, dated 2026-09-18 — before
the client/daemon split of 2026-10-09). It was the **only non-jaato package
there**, among seven editable installs, and it pointed at this working tree, so
the shared daemon's environment depended on this repository's path.

**Why it was there.** `.jaato/scripts/prefetch_sentiment.py` did `from
ta_cascade import data`, and `explain prefetch` is explicit: *"The script is
imported into the runner's own interpreter, so a third-party import resolves in
the DAEMON's environment."*

**Why there is no configuration that fixes it.** `script_imports:
workspace_venv` (jaato#1644) looks like the escape and is not one. It is a
`plugin_configs.cli` key — a venv scoped to the `cli` plugin, for the commands
the model runs, unrelated to a cascade's own venv — and every analyst stage
here declares `plugins: []`. Its venv is also model-writable by design.

**What the other cascades do**, surveyed across 32 sibling workspaces on this
host: no workspace sets `script_imports` except `kb-for-coding-patterns-wiki`,
which uses `workspace_venv: pipeline/venv` for its model's `cli` commands.
Every other `.jaato/scripts/` file imports **stdlib plus its own neighbours in
that directory** (`_gate_helpers`, `pricing_rules`, `audit_validator`,
`_audit`), reached with `sys.path.insert(0, str(Path(__file__).parent))`.
`prefetch_sentiment.py:29` was the only line in any of them importing a driver
package. The convention is: local `.venv`, local `.jaato`, no venv inside
`.jaato`, no workspace-venv setting, and self-contained scripts.

**The fix: the sentiment analyst gets host tools, like the other three.**
Considered and rejected: a stdlib-only `subprocess` bridge to this venv's
python (an exec boundary in the runner, and a C extension under the workspace
needs an exec-mapping grant the base profile does not carry); re-implementing
the four fetches in the script (duplicates the three-kinds-of-nothing contract
in a second place); `ToolPlugin` packaging (#10 — still installs our code
daemon-side). Host tools need nothing of ours in the runner by any route.

What changed: `tools.sentiment_tools` gives the stage `get_company_news`,
`get_global_news`, `get_stocktwits_messages`, `get_reddit_posts` — the two news
specs factored into shared builders so the news analyst and this one cannot
drift; the persona rewritten to call them instead of reading pre-fetched text;
`prefetch_sentiment.py` deleted; `TA_CASCADE_PREFETCH` removed from all
thirteen echo profiles (it was each one's only `env:` key, so the block went
too); and `data.gather_with_deadline` removed, the prefetch having been its
only caller. The stage's `budget_control` needed no change: all four analysts
share one ceiling (`turns: 8`, `tool_calls: 60`) and news and fundamentals
already run four host tools inside it.

**Verified, in this order.** 147 unit tests pass; `validate` holds the
baseline on all three sets (openrouter_sonnet 3 warn, minimax_m3 3 warn, echo
2 warn + 13 info, zero errors); the end-to-end tier passed at **292.08 s**
with the daemon-venv install still present; then `pip uninstall ta-cascade`
from the daemon venv, a daemon restart so no runner could inherit the old
`sys.path`, and the tier passed again at **283.11 s**. So the pipeline is
measured to work with no package of this repository in the daemon's
environment, which is the claim that matters.

This also retires trap #1 for the sentiment stage: a host tool runs in the
driver process, where a stalled fetch cannot reach `session.bootstrap`. The
rule for the future is in CLAUDE.md §4 — a `.jaato/scripts/` file may import
stdlib and its neighbours, nothing else.

**Not verified:** no live-model run yet. The stage now has to CHOOSE to call
four tools where it was previously handed the text, and only a real model
shows whether the persona's instruction is followed. The echo set cannot test
it — echo emits one canned tool call, which is spent on `signal_completion`.

### The framework declares Python 3.14, and the daemon moved to it the same day (2026-10-17, jaato#1076)

Found on the 2026-10-17 pull (42 commits, `75e366d1` → `612dfc22`). Commit
`85424765` moved every `pyproject.toml` to `requires-python = ">=3.14,<3.15"`
— an exact pin, so 3.15 is excluded by declaration too. This host has
`/usr/bin/python3.12` (3.12.3) and no other interpreter; the daemon venv and
this client venv are both 3.12.

**Nothing is broken today, and the distinction matters.** The pulled tree
imports, byte-compiles (`compileall`, rc=0) and answers `-m jaato_server
--help` under 3.12, so the declaration gates INSTALLATION, not execution. The
restart that day was therefore safe and needed no reinstall: the packaging
diff across those 42 commits is `requires-python` and classifiers only — nine
insertions, nine deletions, five files, no dependency, package or entry-point
change.

**What it blocks is the next editable reinstall of the daemon venv** — the
step a packaging change forces after a pull, as jaato#1643 did on 2026-10-14.
That step will be refused by pip until a 3.14 interpreter exists.

The dependency ecosystem is **not** the obstacle, measured rather than assumed:
a wheels-only `uv` resolution for 3.14 succeeds both for the daemon's declared
core (15 deps → 175 packages) and for the heavy tenant extras that were the
real risk — `numpy 2.5.4`, `scipy 1.18.1`, `onnxruntime 1.31.0`,
`tokenizers 0.23.3`, `presidio-analyzer 2.2.362`, `spacy 3.8.16`,
`grpcio 1.84.0`, `pynacl 1.6.2`. Nothing needs a compiler.

What the move actually costs is the venv and its launchers: 225 packages, eight
editable installs (`jaato-sdk`, `jaato-server`, `jaato-eval`, `jaato-tui`,
`jaato-premium`, `jaato-client-telegram`, `jaato-m365` from
`jaato-m365-plugin/src`, and — until today — `ta_cascade`), and one systemd
user unit, `jaato-tg.service`. `uv` 0.9.26 is on the box and `uv python
install 3.14` needs no root and no compiler; `apt` offers no 3.13 or 3.14 and
no deadsnakes source is configured, and a source build would first need
`libsqlite3-dev`, `libreadline-dev`, `libbz2-dev` and `liblzma-dev`, none of
which are installed.

**This repository already faces the same wall — measured, not predicted.**
`jaato-sdk` carries the identical pin, and two newer rcs are already published
with it. A dry-run install into this 3.12 venv is refused:

```
ERROR: Ignored the following versions that require a different python version:
  0.30.0rc21 Requires-Python >=3.14,<3.15; 0.30.0rc22 Requires-Python >=3.14,<3.15
```

`0.30.0rc20` still installs (dry run: *"Would install
jaato-sdk-0.30.0rc20"*), so **rc20 is the ceiling for a 3.12 client venv**.
One consequence to know before acting on it: `jaato-doctor`'s `package
releases` WARN now reports `0.30.0rc16 → 0.30.0rc21` and prints an install
command that cannot succeed. The doctor tally moved to **1 fail, 9 warn, 24
checks** for exactly this reason — that check went quiet on 10-14 when the venv
came current and is back now. Read the WARN as "a 3.14 interpreter is needed".
`--ignore-requires-python` only defers the moment the code genuinely needs
3.14, so it is a stopgap and not the fix.

**RESOLVED for the daemon, the same day.** The operator moved the daemon venv
to **Python 3.14.2**, taken from `uv`'s own standalone build
(`~/.local/share/uv/python/cpython-3.14.2-linux-x86_64-gnu`, symlinked at
`~/.local/bin/python3.14`) — the no-root, no-compiler route. There is still no
system `python3.14`.

Two things were then worth measuring rather than assuming:

- **`ta_cascade` did not come back.** The rebuilt venv holds six editable
  installs and ours is not among them (`python -I -c 'import ta_cascade'` →
  `ModuleNotFoundError`). Had the prefetch still existed, this rebuild would
  have had to put this repository AND pandas, yfinance and matplotlib into a
  3.14 venv to keep the sentiment stage working. The retirement above landed
  hours before it would have cost something.
- **A 3.12 client drives a 3.14 daemon.** `validate` delegates correctly
  (`[validated by the daemon at /tmp/jaato.sock (jaato-server 1.3.0) — not
  this venv]`) and the end-to-end tier passes: **3 passed in 296.14 s**. The
  two sides share a wire protocol, not an interpreter, which is what the
  client/daemon split of 2026-10-09 is for — but it is now measured across a
  two-minor-version gap, which it had never been.

**CLOSED the same day: this venv moved too.** Rebuilt on **Python 3.14.2**
from the same `uv` build, and the SDK taken to **0.30.0rc22**, the newest on
TestPyPI. Verified: 147 unit tests; `validate` at baseline on all three sets;
doctor back to **1 fail, 8 warn, 24 checks** with `package releases` PASSing
("nothing newer is published") and the claude-code skill refreshed to rc22; the
end-to-end tier **3 passed in 274.87 s**. The dependency diff against the 3.12
venv is **exactly one line** — `jaato-sdk==0.30.0rc16` -> `0.30.0rc22` — which
is the point of the next finding.

What forced the move was the published SDK, not the daemon: a 3.12 venv is
refused rc21 and later, so rc20 was its ceiling. The daemon's own interpreter
never required it, as the 296.14 s measurement above shows.

### `--pre` is global, and on a fresh venv it substitutes pre-releases wholesale (2026-10-17)

Found while moving this venv to 3.14. CLAUDE.md §2's documented install —
`pip install -e ".[dev,board,sweep]" --pre --index-url
https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/` — is
correct for the two packages it exists for, and quietly wrong for everything
else when the venv is EMPTY. `--pre` is not per-package: it licenses a
pre-release for every requirement, and with TestPyPI as the PRIMARY index pip
prefers whatever is newest there. Run bare into the new 3.14 venv it installed:

```
pandas==3.1.0rc0        (3.0.6 on the old venv)
lxml==7.0.0b1           (6.1.3)
urllib3==2.8.1.dev23    (2.8.0)
protobuf==7.37.0rc1     (7.36.2)
curl_cffi==0.16.4b1     (0.16.3)
```

plus a dozen stable-but-moved lines. A backtest arm must not quietly run on a
pandas release candidate, and nothing in the install output says it is doing
so — the drift is only visible in a freeze diff.

**Why it had not bitten before.** On 2026-10-09 the same command moved exactly
one line, because it ran against an already-populated venv whose installed
versions already satisfied every requirement, so pip had nothing to choose.
The hazard is specific to a fresh venv, which is precisely what an interpreter
move creates. The existing warning in §2 ("take a `pip freeze` before and
after and diff it") is what caught it; it was right and it was not enough.

**The fix, and it is deterministic rather than defensive.** pip has no
per-package `--pre`, so constrain the rest explicitly from the last known-good
freeze:

```
grep -E '^[A-Za-z0-9_.-]+==' freeze-before.txt | grep -v '^ta.cascade==' > pins.txt
PIP_CONSTRAINT=pins.txt .venv/bin/pip install -e ".[dev,board,sweep]" --pre ...
```

Every one of the 51 pins from the 3.12 venv resolved **wheels-only** on 3.14
(checked with `uv pip compile --python-version 3.14 --only-binary :all:`
BEFORE the venv was touched), so the move needed no dependency drift at all —
and then moving the SDK alone, with the same pins minus its line, left the
one-line diff above. Recipe now in CLAUDE.md §2.

**One tenant left the daemon, by decision rather than accident:**
`jaato-tg.service` (the telegram bot) went `inactive (dead)` at 18:20:23 with
`status=0/SUCCESS` after 2w 3d of uptime, and `jaato_client_telegram` was not
reinstalled into the 3.14 venv. The operator stopped it deliberately, so this
is not pending work, and the unit was then `disable`d at the operator's
instruction (only the `default.target.wants` symlink was removed; the unit file
is still at `~/.config/systemd/user/jaato-tg.service`, so `systemctl --user
enable --now jaato-tg.service` brings it back once
`jaato_client_telegram` is reinstalled into the 3.14 venv). Worth knowing
because the daemon now serves one fewer long-lived client, which changes what
competes for runner slots and memory on this box — see 2026-10-14 above, where
contention alone failed the end-to-end tier.

### The sentiment analyst calls its four tools, measured (2026-10-17)

`analyze NVDA 2026-10-17 --analysts sentiment -v` on the `minimax_m3` set
against the shared daemon at `ec64c5b7`; exit 0, ten sessions, 40 tool calls,
179.5 session-seconds. This is the evidence the host-tool switch earlier the
same day left owing: the stage now has to CHOOSE to call what the prefetch
used to hand it, and echo cannot test that — it scripts one canned tool call
and that one is spent on `signal_completion`.

- **All four, in the persona's order, in one turn.** The daemon's ledger for
  the session reports `used.tool_calls: 5.0` — the four sources plus
  `signal_completion` — with `turns: 1`, `nudges_fired_total: 0` and
  `reason: natural`; the payload's `tools_used` names
  `get_stocktwits_messages`, `get_reddit_posts`, `get_company_news`,
  `get_global_news`. Both halves matter: `tools_used` is the model's prose
  about itself, and `used.tool_calls` is the daemon's own count. They agree.
- **The derived handler deadline was verified live for the first time.**
  `sessions.check_tool_budgets` raised nothing, so the daemon reported, for
  each of the four specs, exactly the budget `tools.handler_deadline_s`
  derived from `jaato_sdk.client_tool_timeout` (protocol 1.39, SDK
  0.30.0rc22, both sides on 3.14.2). Until this run that path had only ever
  been exercised against the echo set.
- **Three kinds of nothing survived the trip into the model.** StockTwits
  answered 403 (trap #10, unchanged since 2026-09-23) and two of three Reddit
  feeds failed. The report declares StockTwits `DATA_UNAVAILABLE` and writes
  that the tally "cannot be computed; do not infer crowd labels from
  silence", files all four observations in `warnings[]`, keeps `errors[]`
  empty, and then builds the mood from the 5 r/wallstreetbets posts and the
  50 + 50 articles it did get — naming the thinness as the reason its
  confidence is medium. A stage that cannot see is not a stage that invents.
- **The default window is the one the persona promises.** The report's header
  reads "Window 2026-10-10 to 2026-10-17", the seven days `_week_before`
  computes, and the model raised `limit` to the specs' maximum of 50 on both
  news tools rather than taking the default of 20. The closures' as-of
  clamping is doing the dating, not the model.
- **Cost is the unpriced state, not zero.** `budget.used.usd` is 0.0 for all
  ten sessions because the native minimax provider reports no cost, so what
  bounds a stage there is the `seconds` / `tool_calls` ceiling: this one
  spent 38.6 s of 600 and 5 tool calls of 60, `fraction_used` 0.125. Never
  render that as $0.00.
- **A downstream refusal worth keeping.** With only the sentiment analyst
  selected, the trader declined to place any price level — "no market report
  was provided in this prompt, so the verified market snapshot is not
  available … entry_price, stop_loss and position_sizing are therefore
  null" — and said in `warnings[]` that the sentiment report's quoted $214
  reference price is context, not the verified snapshot. The stop-placement
  rule held against a missing input instead of borrowing a number that was
  lying there.

What this does NOT measure: the openrouter_sonnet set, where the same persona
has never driven these four tools, and any date whose news window Finnhub
cannot serve. The run used today's date, so company news was served natively
and the general feed's few days covered the window.

### A neighbour's daemon deletes the shared pid file, and `--stop` does not need it (2026-10-20, jaato#1764)

`/tmp/jaato.pid` was missing on two consecutive days while the daemon it names
was alive and serving — pid 2382642 on 10-19, pid 3912123 on 10-20, each
verified by `ps` and by a delegated `validate` answering as
`jaato-server 1.3.0`. On 10-19 this was reported as "no evidence yet for the
cause", which was the honest answer then. It recurred, so it could be measured
instead of guessed.

The daemon writes the file correctly. On a controlled restart it appears at
once: `-rw-rw-r-- 7 2026-10-20 10:26:00.014595492 /tmp/jaato.pid`. No
`Could not write PID file` or `Could not remove PID file` warning exists in any
of the six `/tmp/jaato.log*` rotations. So the write works and something else
removes it afterwards.

The sibling default file is where it becomes visible. While our daemon held
`/tmp/jaato.sock`, `/tmp/jaato.config.json` — written 09:20 that morning —
named `/tmp/jaato-conformance-nzov3ws_/d.sock`, `.../d.pid` and
`.../daemon.log`: a conformance-fixture daemon on a private socket had written
the SHARED default path. `--restart` reads that file (`load_config()` with no
argument), so it would have restarted our daemon onto a dead fixture's
identity.

The mechanism is that the daemon's auxiliary paths are independent defaults,
not derived from `--ipc-socket` (`DEFAULT_PID_FILE`, `DEFAULT_CONFIG_FILE`),
written at start and **deleted at stop** (`_remove_pid`). Any daemon started on
a private socket without the matching flags therefore writes, and then
deletes, the files belonging to whoever is using the defaults. The SDK's own
autostart is exactly such a caller: it passes `--ipc-socket` and `--daemon`
and nothing else. Filed as **jaato#1764** (bug, P2), with the fix argued
daemon-side — a private socket should imply a private identity — rather than
SDK-side, which would leave the trap armed for the next caller.

**What is still not evidenced: which process deleted it.** The autostart
banner prints to the client's stdout, not the daemon log, and nothing logs a
pid-file path. The culprit is identified by code path plus the config-file
evidence, not by a captured event. This repository is a victim and never a
cause: it runs `auto_start=False`.

What it costs us, from `check_running` being pid-file-first: a default pid file
naming a live but unrelated daemon is believed, so `jaato-server --stop` can
SIGTERM that one and reap its runners while the daemon we meant survives. On a
shared host, read the pid back from `ps` before trusting it.

And the correction that matters for our own procedure: **`--stop` does not
need the pid file.** `check_running` falls back to `_pid_on_socket`, which
resolves the daemon from the socket and verifies the owner's cmdline, so
`--stop --pid-file /tmp/jaato.pid --ipc-socket /tmp/jaato.sock` stopped both
pid-file-less daemons cleanly (5 orphan runners reaped on 10-19, 5 again on
10-20). Rewriting the pid file by hand from the ps-verified pid, as was done on
10-19, was unnecessary. Trap #5 in `CLAUDE.md` is corrected accordingly.

One more thing the day taught about restarts. The shared `jaato/` checkout is
not ours: on 10-20 it sat on another agent's branch, one cherry-picked commit
ahead of `origin/main` and three behind, so `git pull --ff-only` refused. The
daemon's editable install follows the WORKING TREE, so a restart after someone
else's pull is what closes the skew — on 10-20 the daemon had loaded
`a8dc4dd8` while the tree had moved 34 commits to `97828dc0`, and every newly
spawned runner was already importing code the daemon core did not have. Moving
that tree to `main` is the operator's call, not ours, and it is lossless only
while the other branch's ref survives: that commit existed on no remote.

### jaato#1764 is fixed: the pid file follows the socket (2026-10-21, jaato#1785)

An amendment to yesterday's finding, which should not be read as current.
jaato#1764 was closed by PR #1785 in the pull of 2026-10-21, with the fix
daemon-side as argued rather than a patch to the SDK's autostart alone. A new
module, `jaato_sdk.daemon_paths`, is the single rule for where a daemon keeps
its pid file, restart config and log, and the server's `__main__`, the SDK's
autostart and `jaato-doctor` all read it, so the three cannot disagree about
which file belongs to which daemon. The conformance fixture's workaround — the
`--pid-file` it had to pass to avoid corrupting a neighbour — was dropped in
the same PR.

Checked against the two sockets this repository actually observed:

| socket | derived pid / config / log |
|---|---|
| `/tmp/jaato.sock` (ours) | `/tmp/jaato.pid`, `.config.json`, `.log` — the legacy trio, so nothing migrates |
| `/tmp/jaato-1.3.0rc28.sock` (the clobberer of 10-20) | its own private trio |

Explicit `--pid-file` / `--config-file` / `--log-file` still win. Our restart
command passes them, so our procedure did not change — what changed is that it
no longer needs to.

Worth recording about the evidence, because it decided the fix: the config
file was the half that could be shown rather than inferred. The pid file's
disappearance left no trace of its cause, and the issue said so; the clobbered
`/tmp/jaato.config.json` named the offending daemon's own socket, which is what
turned "something deletes our pid file" into a mechanism. It then reproduced a
second time the same day from a different caller — a version-named daemon on
`/tmp/jaato-1.3.0rc28.sock` that had passed `--pid-file` but not
`--config-file`, so only the config half fired.

The client venv moved the same day: `jaato-sdk` 0.30.0rc22 -> rc26,
`jaato-eval` 0.3.5rc1 -> rc2, and the freeze diff was exactly those two lines
of 52. A detail the §2 recipe did not say and now does: `pip install -e .`
does not move a dependency pip already considers satisfied, so the first
constrained install reinstalled only `ta-cascade` and moved nothing. The two
packages had to be named explicitly, still under the same `PIP_CONSTRAINT`.
`jaato-doctor` came back to 1 fail, 8 warn, 24 checks, and a `validate` from
the rc26 client still delegates to the 1.3.0 daemon — the two sides share a
wire protocol, not a build.

### Every session is confined now, and the client caught up to the gates (2026-10-23, jaato#1808/#1809/#1777/#1811)

Three things landed together, and the end-to-end tier measured all of them at
once: **3 passed in 162.63 s**, the first run of that tier since 2026-10-14.

**Confinement stopped being opt-in.** Protocol 1.46 confines any
client-driven IPC session a daemon with a kernel backend was not told to leave
unconfined. The surprise is that our client never says anything either way and
still gets it: a pre-1.46 SDK sends `apparmor: false` by DEFAULT, and
`jaato_sdk.confinement_option.client_signal` returns
`True if legacy is True else None` — so `false` is "not said", not an opt-out,
and the daemon's default applies. That was worth settling BEFORE restarting,
because this daemon warns at every startup that the runner's own interpreter
(`~/.local/share/uv/python/cpython-3.14.2-.../bin/python3.14`, which is what
`venv/bin/python` resolves to) sits "inside the workspace root /home/apanoia"
and is "not granting it (model-writable)" — an ungranted interpreter under a
new mandatory profile is a plausible way for every session on the host to stop
bootstrapping.

It does not. One probed session through `open_stage` came back
`[confinement] confined by default (apparmor)`, `confined=True`,
`profile applied`, `enforced=True`; then the whole tier ran the pipeline twice
plus the resume and budget tests with `confined=True` on every session. The
measured cost is **~505 ms per session** of provisioning, 501.6 ms of it the
AppArmor parser — a per-SESSION cost, so a sweep pays it ~11 times per run,
not once. Still unmeasured: a confined session making a real HTTPS call to a
provider. Echo needs no network, and the CA-bundle grants that make TLS work
under confinement (jaato#1814) arrived in this same payload, which is itself a
sign that confinement broke TLS for someone. `JAATO_IPC_CONFINE_DEFAULT=off`
is the host-scoped escape, announced at WARNING; it was not needed.

**The client caught up to the completion gates.** `jaato-sdk` 0.30.0rc26 ->
rc28 (`jaato-eval` rc2 -> rc3), freeze diff exactly those two lines of 52.
rc26 RAISED `ValueError: Unknown event type` on `completion.processor_verdict`
and `completion.nudge_fired` (jaato#1777) — bounded, because
`IPCClient._drain_loop` logs one line and continues, but one line per gated
stage per run, in OUR client's log, where trap #6 only ever inventoried noise
in the DAEMON's. rc28 deserializes both into typed events, and a probe that
drove one gated echo stage saw
`COMPLETION_PROCESSOR_VERDICT analyst_report accepted errors=0 refusals=0`
arrive. That is new observability, not just quieter logs: a `NudgeExhausted`
dead-end (§4, what echo cannot test) was until now diagnosable only by
inference.

**Seven stages stopped paying for a Files panel nobody reads.** The daemon's
own `validate` began reporting `workspace_monitor_unwatched` (jaato#1811) for
every concrete, completion-gated profile with no tool plugins: the four
analysts, `research_manager`, `portfolio_manager` and `reflector` each kept the
workspace monitor, costing a baseline walk and one watch per kept directory per
session. They now declare `workspace_monitor: false` on their `_base_<agent>`,
which cleared all seven advisories (workspace info 7 -> 0 on both real sets;
3 warn / 3 warn / 2 warn + 13 info and zero errors is unchanged). The tier got
faster in the same step — 274.87 s on 2026-10-17 to 162.63 s — but the cause is
NOT isolated: the same payload also took the monitor off the session-create
path framework-side, so this profile change is belt-and-braces on top of a
framework fix, and nothing here measures the two apart.

A note on introspection, which §2 calls the source of truth: it was BEHIND the
daemon here. `explain profile` on rc28 has no mention of `workspace_monitor` at
all — the scaffold surfacing for it is in the checkout the daemon runs but not
in the published rc. What named the key, its value and its placement was the
daemon's own `validate` output, and the field itself
(`Optional[bool]`, default `None`, top-level on the profile). When the client's
snapshot and the daemon disagree, the daemon is the one that reads the profile.

**Carried, not closed:** the daemon venv holds `anthropic` 1.15.0 while the
tree now pins `anthropic>=0.40.0,<1` (jaato#1800: the 1.x SDK moved to httpx2
and client construction fails with the httpx client the tree passes). It is
pre-existing — installed 2026-10-17 18:21, three daemons have run on it — and
it does not touch this repository, which uses OpenRouter and minimax. Fixing
it means reinstalling inside a venv twelve other workspaces share, so it is
the venv owner's call, not a client's.

## Feature parity with the reference implementation

The table above tracks gaps of the *port* (framework limits, decisions).
This one tracks features the reference implementation (TradingAgents
main at `be952b8`, after the v0.4.0 release; still upstream main on
2026-09-14) has and this repository does not yet, so the size comparison in
the assessment is read honestly: the reimplementation is smaller partly
because the framework absorbed work and partly because these are not
built. Priority is for a first production-shaped run, not for parity's
sake. Reimplement, never copy.

| # | Feature upstream | Here today | Priority | Notes |
|---|---|---|---|---|
| P1 | **Second price/fundamentals/news vendor (Alpha Vantage)** with a per-category vendor chain (`data_vendors`) and per-tool override (`tool_vendors`); typed vendor errors (rate-limited, not configured, no data) decide fall-through | yfinance only; one code path per function | medium | needs an API key; the chain semantics ("the configured list IS the chain, no silent fallback") are worth keeping when built |
| P2 | **Polymarket prediction-markets tool** (keyless public search, forward-looking filter, ranked by volume) | none | low | one function in `data.py` plus a host tool on the news analyst |
| P3 | **OHLCV file cache** with a TTL, a stale-data guard (refuse bars older than N days when the market should have traded), and a retry wrapper around yfinance | direct yfinance call under a deadline; no cache (deferred until a backtest needs one); the staleness guard landed with P4 | medium | the staleness guard matters for correctness (a stale last bar silently mis-dates a snapshot); the cache matters for backtests over many dates |
| P4 | **Verified market snapshot** from checked rows: the latest bar on or before the date, a 10-day staleness refusal, recent closes with dates (upstream fills price gaps rather than refusing them) | a calendar-day window stating its dates, the high and low with their dates, the last ten closes with dates; bars more than `max_stale_days` (7) old are refused; no gap filling | done | an earlier version of this row said upstream validates contiguous bars; it fills gaps instead (read 2026-09-14) |
| P5 | **Point-in-time filtering of fundamentals and news** by publication/filing date, so a backtest sees only what was published by the analysis date | statements filtered by period end with a filing-lag note; `info` ratios flagged as current; news filtered by article date | medium | yfinance exposes no filing dates; a true fix needs a vendor that does (P1) |
| P6 | **Global news from configured macro search queries** (a list of query strings, a lookback and a limit) | headlines from the feeds of index/rates/commodity proxy tickers | low | ours is a proxy; upstream's is a search |
| P7 | **Interactive CLI**: questionary flow (ticker, date, analysts, depth, provider, models, thinking level, language), saved config, typed `TRADINGAGENTS_*` env overrides that fail fast on bad values | argparse only; model/provider chosen by `JAATO_PROFILE_SET` | low | jaato's TUI can attach to a running cascade for the live view; the selection flow is a small typer command when wanted |
| P8 | **Output language** setting injected into every prompt | English only | low | one `{{language}}` param on every persona plus a base-instruction line |
| P9 | **Azure OpenAI and Bedrock providers** (17 OpenAI-compatible specs, a capabilities table with per-model structured-output method, DeepSeek/MiniMax reasoning quirks) | jaato's 18 providers; OpenAI-family via OpenRouter | medium | gap #1 above |
| P10 | **Benchmark by ticker suffix** (`.T` → Nikkei, `.L` → FTSE, … else SPY) and a **decision-log rotation cap** | one benchmark symbol (`RunConfig.benchmark`); unbounded log | low | both are small additions to `memory.py` / `config.py` |
| P11 | **Test coverage** of look-ahead guards per source, symbol normalisation, vendor routing and config precedence (≈45 upstream test files are framework-free) | 105 unit tests (config, journal, memory point-in-time, indicators, snapshot windows and staleness, tools, gates, report, social parsing, board, observer, the jaato-eval contract, the scorer, the task generator) and 3 end-to-end | medium | write against our own functions as each feature lands |
| P12 | **Structured-output fallback to free text** when a model cannot bind a schema, with regex rating extraction and a `REVIEW` sentinel | the daemon re-prompts an agent that ends in prose; a stage with no payload raises `StageFailed` | n/a | deliberately different: a missing decision stops the run rather than being parsed out of prose |
| P13 | **Checkpoint resume at every graph node**, opt-in | journal per stage and per debate turn | done | equivalent; see gap #2 |
| P14 | **Reddit + StockTwits ingestion** | done | done | gap #14 |
