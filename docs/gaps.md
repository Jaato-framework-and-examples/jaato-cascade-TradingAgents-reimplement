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
| 11 | **`echo` cannot script a multi-turn tool loop** (one call, then text). Driver-level tests cover control flow, journal and processors; the analyst loop is tested against a real model or a recorded provider trace. | low | per-stage echo profiles drive the whole pipeline end to end (`tests/test_pipeline_echo.py`); the analyst tool loop itself still needs a live model or a replay fixture. | done (control flow); the live analyst loop ran on 2026-09-08, see the live-run findings below |
| 12 | **No embedding memory in the free jaato package.** Irrelevant to parity; a future "similar past situations" feature needs a `jaato.embedding` provider or an external store surfaced through a prefetch or host tool. | none for parity | out of scope. | deferred |
| 13 | **The in-process facade honours a subset of the profile contract.** `InProcessClient` resolves a named profile to `model`, `provider`, `plugins`, `plugin_configs`, `system_instructions`, `completion_payload_schema` and `suppress_base_instructions` only (`jaato_embedded/client.py:110-142`); `completion_processors`, `max_turns`, `spawn_payload_schema` and `budget_control` are not applied, so the gates this pipeline relies on would silently not run. Found while starting the implementation; a jaato-side finding worth an issue. | medium if in-process were used | the reimplementation uses the daemon (IPC) transport, where the whole contract applies. Decision recorded in assessment §4.1. | accepted (daemon transport) |
| 14 | **Social sources.** StockTwits (public symbol stream, no key; the Jentic OpenAPI document describes it) and Reddit (subreddit Atom search feeds; the JSON endpoint is blocked for anonymous clients) are fetched by the sentiment prefetch alongside company and market news, all four concurrently under one 20 s deadline. A failed fetch reads as unavailable, an empty window as quiet — never confused. The StockTwits public stream serves recent messages only, so historical runs get the quiet sentence. | low | `data.stocktwits_messages`, `data.reddit_posts`, `data.gather_with_deadline`; fixture tests in `tests/test_social.py`. | done |
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
| P11 | **Test coverage** of look-ahead guards per source, symbol normalisation, vendor routing and config precedence (≈45 upstream test files are framework-free) | 98 unit tests (config, journal, memory point-in-time, indicators, snapshot windows and staleness, tools, gates, report, social parsing, board, observer, the jaato-eval contract, the scorer, the task generator) and 3 end-to-end | medium | write against our own functions as each feature lands |
| P12 | **Structured-output fallback to free text** when a model cannot bind a schema, with regex rating extraction and a `REVIEW` sentinel | the daemon re-prompts an agent that ends in prose; a stage with no payload raises `StageFailed` | n/a | deliberately different: a missing decision stops the run rather than being parsed out of prose |
| P13 | **Checkpoint resume at every graph node**, opt-in | journal per stage and per debate turn | done | equivalent; see gap #2 |
| P14 | **Reddit + StockTwits ingestion** | done | done | gap #14 |
