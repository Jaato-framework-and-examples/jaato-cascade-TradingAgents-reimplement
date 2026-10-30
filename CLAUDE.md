# CLAUDE.md — handover for agents working on this repository

This file is the working knowledge of the agent that built the repository,
written so another agent can continue without the original conversation.
Read it fully before changing anything. `README.md` is for humans;
`docs/assessment.md` is the design rationale; `docs/gaps.md` is the live
list of what is open; `docs/size-and-complexity.md` compares this tree with
the reference (regenerate with `scripts/measure_size.py`); `docs/manual.md`
is the vocabulary — market, pipeline, jaato — the mechanisms, and the
argument for why they should work. This file is the operational layer on
top of them.

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
   each: completion-gated session, host tools
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

**This repository is a jaato CLIENT. It holds its own venv with the SDK and
its own dependencies, and it does NOT hold `jaato-server`.**

The daemon is a shared service living in its own environment; a client reaches
it over IPC. Installing the server into a client venv couples the client's
build to the daemon's and makes them move together, which is the opposite of
what a shared daemon is for.

```bash
# Python 3.14 — the framework declares ">=3.14,<3.15" and the SDK carries the
# same pin, so a 3.12 venv cannot install the current rc. There is no system
# python3.14 on this host; `uv python install 3.14` provides one.
~/.local/bin/python3.14 -m venv .venv
# The SDK and jaato-eval are published packages, but NO LONGER always to an
# index: the jaato repository is private, so since 2026-10-23 (jaato#1816) a
# build may be attached to a GitHub RELEASE of that private repository instead
# of uploaded anywhere public. This recipe still BUILDS the venv — it is what
# resolves pandas/yfinance/starlette — but it cannot reach such a build; see
# "A build that lives only on a GitHub Release" below for that.
# On a release both come from PyPI; this venv tracks release candidates, which
# are staged on TestPyPI, so the two index flags are needed and `--pre` is what
# allows an rc.
# Pass BOTH indexes: TestPyPI alone cannot resolve pandas/yfinance/starlette.
#
# ON A FRESH VENV, CONSTRAIN IT. `--pre` is global: it licenses a pre-release
# for EVERY package, and with TestPyPI as the primary index pip then prefers
# whatever is newest there. Run bare into an empty venv on 2026-10-17 it
# installed pandas 3.1.0rc0, lxml 7.0.0b1, urllib3 2.8.1.dev23, protobuf
# 7.37.0rc1 and curl_cffi 0.16.4b1 — a backtest must not quietly run on a
# pandas release candidate. pip has no per-package `--pre`, so pass a
# constraints file built from the last known-good `pip freeze` (minus the two
# lines you intend to move) and the drift is nil:
#   grep -E '^[A-Za-z0-9_.-]+==' freeze.txt | grep -v '^ta.cascade==' > pins.txt
#   PIP_CONSTRAINT=pins.txt .venv/bin/pip install -e ".[dev,board,sweep]" --pre ...
# Then diff the freeze anyway. The absence of a complaint from pip is not the
# same evidence.
.venv/bin/pip install -e ".[dev,board,sweep]" --pre \
    --index-url https://test.pypi.org/simple/ \
    --extra-index-url https://pypi.org/simple/
```

Making TestPyPI the PRIMARY index lets pip substitute any dependency that has
a newer build published there, so take a `pip freeze` before and after and
diff it: on 2026-10-09 each of the two installs moved exactly one line. The
absence of a complaint from pip is not the same evidence.

**A build that lives only on a GitHub Release.** The jaato repository is
private, and jaato#1816 gave its four publish workflows a `target: release`
that runs the same gate and build steps and attaches the wheel, the sdist and
a `SHA256SUMS` to a Release tagged `<dist>-<version>` — the same tag name the
PyPI path uses. So a build can exist with no index entry at all, and for such
a build this is the install path:

```bash
cd ../jaato && gh release list | head        # what exists; `gh release view <tag>`
D=$(mktemp -d)                               # its OWN empty directory
gh release download jaato-sdk-0.30.0rc31 --repo Jaato-framework-and-examples/jaato --dir "$D"
(cd "$D" && sha256sum -c SHA256SUMS)         # the Release ships the sums; CHECK them
# --no-index: there is nothing to resolve from an index, and the SDK's own
# dependencies (python-dotenv, pydantic>=2,<3) are already satisfied here, so
# nothing is downloaded. The constraint keeps the other 50 lines nailed down.
PIP_CONSTRAINT=pins.txt .venv/bin/pip install --no-index --find-links "$D" "jaato-sdk==0.30.0rc31"
```

**`jaato-doctor`'s `package releases` check reads GitHub Releases, and its
PASS is still weak — now for a different reason.** It no longer only queries
the indexes: `jaato_sdk.release_channels` calls the Releases API
(`/repos/<repo>/releases`) with a token from `GH_TOKEN`, `GITHUB_TOKEN` or
`gh auth token`, so a private repository's Release IS visible to it and the
PASS can say "newest released on GitHub Releases". What it cannot do is answer
promptly: the listing is CACHED in `~/.jaato/release_check.json`
(`DEFAULT_MAX_AGE` = **6 hours**), and inside that window a freshly released
build is described as the opposite of what it is. Measured 2026-10-30: minutes
after installing rc39 from its Release, the check PASSed with "jaato-sdk is
AHEAD of every release (an unreleased build, which is normal in a checkout)",
because the cache had been fetched at 18:54 and rc39 was released at 21:02.
`jaato-doctor --refresh-release-check` re-fetched and the same check read
"newest released on GitHub Releases". **So pass `--refresh-release-check` once
after installing a build released in the last six hours.** The older caveats
still hold for anything the token cannot see or that is staged on TestPyPI
only, so treat the PASS as "nothing newer that this check could see just now".
The source of truth for what exists is `gh release list` in the jaato
checkout. See `docs/gaps.md`, 2026-10-30.

- `jaato-scaffold` and `jaato-doctor` come with **jaato-sdk**, so a client venv
  has both. `validate` needs no local server: it DELEGATES, and says so —
  `[validated by the daemon at /tmp/jaato.sock (jaato-server 1.3.0) — not this venv]`.
- **`jaato-eval` is a third package** (the `sweep` extra), neither the SDK nor
  jaato-server, and the sweep must be launched from THIS venv. Its contract
  sets `JAATO_EVAL_PYTHON = sys.executable` — the interpreter jaato-eval itself
  runs under — and every `task.yaml` writes `harness.run` and its graders
  against that variable. So the process that starts a sweep decides the
  interpreter all 564 arms execute the driver with: launch it from the daemon's
  venv and every arm runs the DAEMON's python, which is the client/daemon
  coupling this layout exists to remove. See `docs/gaps.md`, 2026-10-09.
- `pandas`, `yfinance`, `requests`, `matplotlib` for the data layer and chart;
  `pytest` and `PyYAML` for tests; `starlette`/`uvicorn` for `sweep-board`
  (`[board]`). PyYAML used to arrive transitively from jaato-server and was
  never declared — two tests skipped silently the first time the venv was
  built correctly.
- **`jaato-doctor` reports one FAIL in a correct client venv**:
  `import jaato_server … required for autostart`. It does not apply here —
  `RunConfig.auto_start=False` against a shared daemon never starts one — and
  the `jaato_server checkout` skew check degrades to a WARN for the same
  reason. The tally to expect is **1 fail, 8 warn, 24 checks**, first on
  2026-10-17 (3.14, SDK 0.30.0rc22) and re-measured 2026-10-23 on SDK
  0.30.0rc30 + jaato-eval 0.3.5rc5. On **2026-10-26** the SDK moved to rc31
  and the COUNT grew to **1 fail, 8 warn, 25 checks**, re-measured unchanged on
  2026-10-30 on SDK 0.30.0rc37 and again on **0.30.0rc39**, both with
  jaato-eval 0.3.5rc6 — rc31 carries a check
  rc30 did not, which is why the instruction below is to compare the LINES and
  not the number. Expect a transient NINTH warn immediately after any SDK
  move: `integration (claude-code)  installed from <old>, framework is <new>`,
  because the skill ships as package data of the SDK; `jaato-scaffold
  integration claude-code --force` clears it. On 2026-10-17 it went to 9 warn when
  `package releases` reported an rc this venv could not install, and back to
  8 — PASS, "nothing newer is published" — once the venv moved to 3.14 and
  took rc22. Read that check with the caveat in §2 above: on a private
  repository it cannot see a Release, so its PASS now means "nothing newer on
  an index", which is a weaker statement than it used to be. Compare the LINES, not the number: `jaato_sdk checkout` and
  `jaato_server checkout` are WARNs here by construction (see #1610 below). Verified 2026-10-06 on `jaato-sdk` 0.29.0 (PyPI) and again
  2026-10-09 on 0.30.0rc6 (TestPyPI), 2026-10-14 on 0.30.0rc16 — the
  first published build whose `register_client_tools` reports the daemon's
  per-tool budgets (jaato#1625) — and 2026-10-17 on **0.30.0rc22 under Python
  3.14.2**, which is what this venv now holds: **147 unit tests and the
  end-to-end tier both pass** (3 passed in 274.87 s) from a venv holding only
  the SDK, against a daemon running from an entirely different environment —
  and, since 2026-10-17, one holding no package of this repository at all. A tier that fails on a loaded host is
  not a regression: see `docs/gaps.md`, 2026-10-14, on what swap exhaustion
  does to `session.new`. Moving the client's SDK is a deliberate
  step, not a consequence of pulling jaato: the daemon's venv is reinstalled
  from the checkout after a pull, the client tracks a PUBLISHED SDK and moves
  when someone decides to. `jaato-doctor`'s `package releases` check is what
  says a newer one exists, and after moving, re-run
  `jaato-scaffold integration claude-code --force` — the skill ships with the
  SDK and doctor reports the copy stale by version.
- **Both sides run Python 3.14 as of 2026-10-17** (jaato#1076, commit
  `85424765`): every framework `pyproject.toml`, and the published SDK, declare
  `requires-python = ">=3.14,<3.15"` — an exact pin, so 3.15 is excluded by
  declaration too. The daemon venv moved to **3.14.2** and this venv followed
  the same day, both from `uv`'s standalone build
  (`~/.local/share/uv/python/cpython-3.14.2-linux-x86_64-gnu`, symlinked at
  `~/.local/bin/python3.14`). There is still no system `python3.14`;
  `/usr/bin/python3.12` (3.12.3) is what a bare `python3` gives you, so a venv
  made without naming the interpreter is the wrong one.
  **They do not have to match.** Before this venv moved, a 3.12 client was
  measured driving the 3.14 daemon — `validate` delegating correctly and the
  end-to-end tier passing (3 passed in 296.14 s) — because the two sides share
  a wire protocol, not an interpreter, which is the point of the split in §2.
  What forced this venv to 3.14 was not the daemon but the PUBLISHED SDK: a
  3.12 venv is refused 0.30.0rc21 and later (*"Ignored the following versions
  that require a different python version"*), so rc20 was its ceiling. On 3.14
  the SDK moved rc16 -> **rc22**, the newest on TestPyPI, and the dependency
  diff against the 3.12 venv is exactly that one line. On **2026-10-21** it
  moved rc22 -> **rc26** (and `jaato-eval` 0.3.5rc1 -> rc2) by the constrained
  recipe above: `pip install -e .` alone does NOT move an already-satisfied
  dependency, so the two were named explicitly under the same
  `PIP_CONSTRAINT`, and the freeze diff was exactly those two lines out of 52.
  `jaato-doctor` returned to **1 fail, 8 warn, 24 checks** afterwards — the
  two extra warns beforehand were `package releases` and a skill copy stale by
  version, both cleared by the move plus
  `jaato-scaffold integration claude-code --force`. On **2026-10-23** the same
  recipe moved rc26 -> **rc28** (and `jaato-eval` rc2 -> rc3), again a freeze
  diff of exactly those two lines out of 52, and doctor returned to **1 fail,
  8 warn, 24 checks** from the 9 it reads whenever `package releases` sees a
  newer build. THAT move had a reason beyond currency: rc28 is the first
  published SDK that knows `completion.processor_verdict` and
  `completion.nudge_fired` (jaato#1777), so the gate verdicts this repository
  depends on are finally visible to it — see trap #12. Later the SAME DAY it
  moved rc28 -> **rc30** (and `jaato-eval` rc3 -> **rc5**), this time from a
  GitHub Release rather than an index, by the recipe above: one wheel each,
  checksums verified, a freeze diff of exactly one line out of 52 per package,
  `pip check` clean, and doctor back to **1 fail, 8 warn, 24 checks** (it read
  9 beforehand, naming rc29/rc4 on TestPyPI). THAT move is the one that closes
  the protocol gap: **rc28 is a 1.45 client and rc30 is 1.46**, so rc28 had no
  field in which to state a confinement decision at all — which is the root of
  trap #12, not a daemon default chosen against us. rc30 also carries the
  scaffold snapshot that KNOWS `workspace_monitor` (`explain profile` on rc28:
  zero mentions), so introspection is no longer behind the daemon here, and
  `DiagnosticsResultEvent` gains `confinement_decision` and `provider_files`
  (jaato#1809, #1814) — the two facts a session's confinement was previously
  only readable for in the daemon's own log.
  Both rc30 and jaato-eval rc5 were built from `92d7a419`, the commit this
  host's daemon checkout was on, so client and daemon were the same revision —
  by timing, not by any mechanism that keeps them so. **That caveat came true
  in three days.** On 2026-10-26 the daemon's checkout was fast-forwarded to
  `fe68bf21` (jaato-server 1.3.0rc33), which moved the DAEMON to protocol
  **1.49** while this venv sat on rc30 at **1.46** — and both test tiers passed
  against that skew, because the mismatch is silent by construction and
  `jaato_sdk checkout` is a declared blind spot that cannot see it (below).
  The same day the client moved rc30 -> **rc31** to restore parity: rc31 is
  built from `67fb7d82`, declares **1.49**, and is 16 commits from the server's
  build commit where rc30 was 92. Measured after the move: a freeze diff of
  exactly one line out of 53, `pip check` clean, client and daemon both 1.49,
  unit 188 passed and end-to-end 3 passed in 96.28 s, 132 `confined=True` with
  no `confined=False`. **Pin a deployment by PROTOCOL, not by revision
  proximity**, and re-check the pair after ANY pull of the daemon's checkout:
  moving the daemon moves the protocol, and nothing warns you.
  On **2026-10-30** that check earned its keep twice in a day: the morning pull
  moved the protocol **1.49 -> 1.50** (client rc31 -> **rc36**, jaato-eval rc5
  -> **rc6**) and the evening pull moved it **1.50 -> 1.51** (client ->
  **rc37**), each caught by reading `origin/main`'s `PROTOCOL_VERSION` BEFORE
  merging. rc37 is built from `dc5b5dab`, which IS `origin/main` — zero commits
  apart — so that pull and the SDK move were two halves of one step; align by
  protocol anyway, because the alignment is timing and not a mechanism.
  Measured after: both sides 1.51, freeze diff one line of 52, `pip check`
  clean, unit 214 passed, end-to-end 3 passed in 118.87 s, 40/40
  `confined=True`.
  **A pull whose `pyproject.toml` is in the diff needs one more step.** The
  daemon's venv installs `jaato-server` EDITABLE from the checkout, so a pull
  moves its code with no reinstall — but entry points live in the installed
  `.dist-info`, so jaato#1966's new `render-request` scaffold verb was absent
  after the pull and present after
  `uv pip install -e jaato-server --no-deps --python <daemon venv>/bin/python`
  (that venv is uv-managed and carries no `pip`). Re-register BEFORE the
  restart, so the restart lands on a consistent install; a half-registered
  state is silent, the verb simply does not exist.
  **A pull can move the protocol more than one step.** The same evening's third
  pull moved it **1.51 -> 1.53** at once (client rc37 -> **rc39**): 1.52 adds
  the gate verbs (jaato#1978) and 1.53 `render-request` through the daemon
  (jaato#1981), both purely additive new verbs under the 1.7 rule, with the
  only changes to what this driver calls being new OPTIONAL keywords
  (`traceparent` / `tracestate`, jaato#1977). rc39 and jaato-server 1.3.0rc40
  are both built from `58d7b333` = `origin/main`. Measured: both sides 1.53,
  freeze diff one line of 52, unit 214 passed, end-to-end 3 passed in
  119.70 s, 40/40 `confined=True`. `pyproject.toml` was untouched this time,
  so no entry-point re-registration was needed — verified by listing the
  verbs after the pull rather than assumed.
  `--ignore-requires-python`
  would only have deferred the moment the code genuinely needs 3.14, so it was
  never the fix. See `docs/gaps.md`, 2026-10-17, 2026-10-23 and 2026-10-30.
- **`jaato_sdk checkout` now says it cannot tell, instead of PASSing**
  (jaato#1610, fixed in SDK 0.30.0rc16; from 0.29.0 to 0.30.0rc6 it reported
  "client and daemon both resolve jaato_sdk from <path>" while printing OUR
  path as the daemon's, because its guard compared two venvs over one system
  Python and so compared our site-packages with itself). It is now a WARN:
  "the daemon's PYTHONPATH names no jaato_sdk, so it uses the copy installed
  in ITS environment …, which is not yours … so client/daemon checkout skew
  is unchecked." **The hand-check is still the only thing that resolves it** —
  what changed is that doctor no longer claims otherwise, which is the part
  that mattered: a false PASS is worse than a declared blind spot. Check it by
  hand when it matters:
  `/home/apanoia/.local/share/jaato/venv/bin/python -c 'import jaato_sdk; print(jaato_sdk.__file__)'`
  against `.venv/bin/python -c` the same. The mismatch it is meant to predict
  is silent by construction — pydantic drops an unknown event field on ingest
  and the `AttributeError` surfaces frames away from the cause. With
  `dependency coherence` and `jaato_server checkout` also unavailable (#1576),
  nothing in doctor DETECTS such a mismatch for us; all three now admit it.
- **`jaato-scaffold validate <workspace>` exits 1 on findings that are not
  this workspace's.** It walks the USER tier too (`~/.jaato/profiles/`, a real
  fallback in the resolution path) and, as of jaato `0ccb7069`, 13 errors in
  other projects' profiles there decide the exit code: 105 of the 108 lines
  printed are theirs. So the §10 pre-commit gate
  (`validate --set openrouter_sonnet && validate --set echo`) now fails for a
  cause nobody can fix from this repo. Read the `tier` field
  (`--json`) or `grep '\[workspace\]'` and judge OUR findings by those;
  `--profile <name>` scopes to one profile and exits 0. Baseline for this
  workspace, unchanged since 2026-10-06: openrouter_sonnet 3 warn,
  minimax_m3 3 warn, echo 2 warn + 13 info, **zero errors**.

### Commands

```bash
# preflight (socket, env file, profiles, secret scrub; 0 fail expected)
jaato-doctor --workspace . --env-file .env

# validate a profile set against the installed framework — run after ANY
# change under .jaato/profiles/, completion_schemas/ or scripts/processors/
jaato-scaffold validate . --set openrouter_sonnet
jaato-scaffold validate . --set echo         # info-level "echo is a test double" lines are expected

# run (needs JAATO_PROFILE_SET in .env; the OpenRouter key resolves daemon-side
#      from pass://jaato/openrouter/api-key — `jaato-doctor --secret pass://jaato/openrouter/api-key` proves it)
python -m ta_cascade analyze NVDA 2026-01-15 --analysts market,news,fundamentals
python -m ta_cascade analyze NVDA 2026-01-15 --debate-rounds 2 --risk-rounds 1 -v
python -m ta_cascade analyze BTC-USD 2026-01-15 --asset-type crypto --analysts market,sentiment
#   --no-journal / --clear-journal / --no-memory / --socket PATH / --workspace DIR
#   --display auto|board|lines   auto draws the live board on a terminal, plain lines when piped

# NOTE: jaato#898 (a second cascade starving until the first finished) is CLOSED.
# One daemon serves several tenants: workspace, config_root and .env travel with
# each SESSION, which is how it serves this workspace and another project's
# profile set at once. The end-to-end tier shares it rather than starting one.
# Its runner pool scales with concurrent demand, so a loaded box is loaded by
# the tenants, not by any one of them.

# tests
.venv/bin/pytest -q tests --ignore=tests/test_pipeline_echo.py   # unit, <1 s, no daemon
.venv/bin/pytest -q tests/test_pipeline_echo.py                  # end to end, ~5 min, needs a REACHABLE daemon

# the boards (read-only, daemon-free, `pip install -e .[board]`)
python -m ta_cascade run-board --port 8098              # one run: a card per stage, a drawer per session
python -m ta_cascade run-board --results /tmp/pilot-ws/NVDA-2026-04-03/results \
                              --workspace /tmp/pilot-ws/NVDA-2026-04-03   # ... or one sweep ARM
python -m ta_cascade sweep-board pilot --port 8099 [--workspaces DIR]     # the whole matrix

# backtests: the driver as a jaato-eval ARM (harness.kind: driver, jaato#1110)
python -m ta_cascade backtest-tasks pilot --tickers NVDA,AMD --from 2026-04-03 --to 2026-08-28 --every 7
jaato-eval run backtests/pilot/tasks --profile-set openrouter_sonnet --socket /tmp/jaato.sock \
    --out backtests/pilot/results.jsonl --workspaces /tmp/pilot-ws --arm-timeout 1200 --resume
python -m ta_cascade.score NVDA 2026-08-28      # grade one cell by hand (reads ./results)
```

Exit codes of the CLI: 0 finished; 1 a node failed (journal kept, re-run
to resume); 2 daemon unreachable.

**Stopping a sweep, and re-running what it was doing.** Send `SIGINT` to the
`jaato-eval` parent: it records nothing for the arms in flight, so `--resume`
re-runs them. Never `pkill` the driver processes — that records them
`BLOCKED`, which `--resume` then skips permanently and which spends a
pre-registered exclusion. Then **wait for the arm drivers to exit** before
touching anything: they outlive the parent, and a workspace moved out from
under a live driver is simply recreated and finished into. Before re-running
a batch, the live `--workspaces` root must hold no resume journal
(`.ta_cascade/journal/`) and no `results/` tree from the voided run — arm
workspace names are deterministic, so a reused directory resumes the old run,
and `ta_cascade.score` grades whatever report tree it finds. Move the old
root aside under a name that says why; do not delete it. (`docs/gaps.md`,
2026-10-11.)

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

The skill `jaato-sdk` is the condensed version of this. It ships WITH the
framework (package data of `jaato-server`), so it cannot describe a different
build than the one installed; apply it with `jaato-scaffold integration
claude-code` and `jaato-doctor` reports when a copy goes stale. Its three
"ways a harness hangs" are all real and all encountered or guarded against
here. (It supersedes `jaato-sdk-client`, which was a file in the jaato repo
and had to be copied by hand.)

---

## 3. Layout and where things live

```
ta_cascade/                the driver (Python; the only code that talks to jaato)
  config.py                RunConfig: ticker, date, analysts, rounds, workspace, socket, journal, log, auto_start
  sessions.py              open_stage(): THE one place a session is opened (IPCRecoveryClient recipe);
                           observing(): the read-only observer subscription. The only SDK importer.
  pipeline.py              run(): the graph as control flow; prompts; phases; StageFailed
  state.py                 RunState / DebateTurn; prompt-composition helpers; to_dict/from_dict
  journal.py               Journal: per-run JSON, load/save/clear (resume) — CLEARED on success
  sessionlog.py            the run's sessions, append-only, NEVER cleared:
                           results/<ticker>/<date>/sessions.jsonl, one started/ended line each,
                           with the daemon's `consumption` (tokens, tool calls, seconds, cost_usd
                           when the provider prices). Asked via get_diagnostics() while the session
                           is still ATTACHED — after the context exits nobody can answer. Three
                           money states: priced / measured-but-unpriced (subscription) / unmeasured;
                           never collapse them, never render unpriced as $0.00.
  memory.py                DecisionLog: JSONL decisions, pending → resolved, past_context(as_of=)
  data.py                  market data: yfinance, FRED, StockTwits, Reddit; deadlines; UNAVAILABLE sentences
  tools.py                 host-tool specs per analyst (closures over the run's as-of date)
  report.py                report tree under results/<ticker>/<date>/
  chart.py                 chart.png beside report.md: candles, SMAs, Bollinger, volume, the span's
                           dated high/low, entry/stop/target, the rating; the holding period after
                           the as-of date when bars exist (a backtest cell). Drawn by code from the
                           same bars as the snapshot; the model never sees it. matplotlib, driver-side.
  board.py                 BoardState: ONE run's progress as drawable state (pure, no renderer),
                           held in memory by the driver while it runs
  runview.py               ONE run's stages as drawable state read from DISK ALONE, afterwards or
                           mid-flight: sessions.jsonl (which stages ran, what each cost),
                           events.jsonl (what happened inside one), state.json (the verdict) and
                           the daemon's own .jaato/sessions/<id>.json (the full history, the
                           persona AS RENDERED, the profile AS RESOLVED). Asks the daemon nothing,
                           so it renders a run whose daemon has since restarted. A stage's
                           capability set — schema, gate, section, references, host tools — decides
                           what its card offers and is READ, never assumed: the record's
                           `profile_snapshot` and `_base_<agent>.yaml` spell it with the same keys,
                           so one reader serves both, the record preferred because it is what the
                           session actually resolved. BANDS mirrors pipeline.plan_of and a test
                           asserts every persona sits in exactly one band.
  eventlog.py              the run's cascade events as structured rows (pure, no SDK import),
                           written by sessions.observing() beside the session log. Records the
                           FOUR low-volume events — one per session, one per tool call, with each
                           call's OUTCOME, which the driver never learns because a tool call that
                           failed inside a stage is not a stage that failed. Deliberately NOT
                           AgentOutputEvent: the per-client queue is bounded (2048) and drops the
                           oldest lossy chunks, no event carries a sequence number, so a client
                           cannot tell a dropped chunk from a model that said nothing. The words
                           come from the record the daemon saves whole, so the drawer degrades to
                           complete-but-delayed, never to silently-missing.
  sweep.py                 a SWEEP's progress as drawable state (pure, no renderer): reads the
                           task dirs (the denominator), results.jsonl (finished arms, with
                           usage.cost_usd) and each arm workspace's sessions.jsonl (what is open
                           now). Money and effort aggregate over ARMS, states over CELLS — keying
                           results by cell drops every repeat but the last, and read the pilot's
                           spend as $9 against a real $47.
  ui/api.py, ui/static/    renderer #2: a READ-ONLY starlette board over those files, two views.
                           `python -m ta_cascade sweep-board <name> --port 8099 [--workspaces DIR]`
                           draws the matrix; `python -m ta_cascade run-board [--results DIR]
                           [--workspace DIR] --port 8098` draws ONE run as a card per stage, each
                           card's icon row being its capability row, with a drawer over the
                           session: the prompt collapsed, the model's words, every tool call with
                           its outcome and a gate's refusal message. Starts no run, stops none,
                           holds nothing, and asks the daemon nothing: every request re-reads the
                           files. A sweep arm keeps its own results tree inside its own workspace,
                           so reading one means pointing run-board at THAT pair rather than having
                           the board guess which arm a cell meant. `pip install -e .[board]`.
  richboard.py             the live two-panel view; the ONLY module that imports rich
  observer.py              cascade events -> trace lines; imports no SDK (testable daemon-free)
  contract.py              the jaato-eval driver contract (JAATO_EVAL_*): workspace, config root,
                           socket, cascade id, params — read once; refuses a version it does not know
  score.py                 `python -m ta_cascade.score`: grades one backtest cell against realised
                           returns (rating direction vs alpha over holding_days); exit 0/1/75
  backtest.py              `backtest-tasks`: writes jaato-eval task.yaml files for tickers × dates
  cli.py, __main__.py      `python -m ta_cascade analyze ...` / `backtest-tasks ...`
run_cascade.py             thin entry point (scaffolded originally; delegates to cli)
backtests/<name>/          generated matrices: fixture/ (empty) + tasks/<TICKER>-<DATE>/task.yaml;
                           results.jsonl and the report land beside them when a sweep runs

.jaato/                    the workspace the daemon reads; DATA, not code
  profiles/_base_<agent>.yaml         13 provider-agnostic stage profiles (ceilings, schemas, gates)
  profiles/anthropic_sonnet/*.yaml    provider+model binding (claude-sonnet-5-5 on the NATIVE
                                      anthropic provider, credential pass://jaato/anthropic/api-key).
                                      The set to run while the MiniMax key is invalid. Its knobs
                                      differ from OpenRouter's: thinking is `enable_thinking` +
                                      `thinking_budget` (tokens) and there is NO `thinking_level`
                                      or `app_title`, so the two judges carry enable_thinking only.
                                      Measured 2026-10-26: all 13 stages resolve and the model
                                      answers (`READY.`) on a real call.
  profiles/openrouter_sonnet/*.yaml   provider+model binding (anthropic/claude-sonnet-4.5 via OpenRouter)
  profiles/minimax_m3/*.yaml          provider+model binding (MiniMax-M3 on the native minimax
                                      provider). Same 13 stages, same _base_<agent> parents:
                                      a set swaps the BINDING, never the stage determinism.
                                      No prompt caching on this provider, and it carries the
                                      `prose_tool_calls` quirk, which `explain` names and does
                                      not describe — unmeasured here; kb-rip runs M3 under
                                      completion gates, so gated stages do work on it.
  profiles/echo/*.yaml                deterministic test double set (canned payloads, no network)
  agents/<agent>.md                   13 personas (YAML frontmatter params + body with {{param}})
  instructions/00-team.md             base layer every persona sits on
  completion_schemas/*.json           5 typed payloads (analyst_report, research_plan, trader_proposal,
                                      portfolio_decision, reflection)
  scripts/processors/*.py             3 completion gates: analyst_report.py (the 4 analysts),
                                      price_fields.py (trader, portfolio_manager) and
                                      rules_read.py (trader). The trader carries TWO, concatenated
                                      as the inheritance rule says. research_manager and reflector
                                      declare a schema and NO processor, so they render no section.
                                      NB: `.jaato/scripts/` is code the DAEMON runs inside the
                                      runner, and it must be SELF-CONTAINED: stdlib plus its
                                      own neighbours in that directory, never an import of
                                      `ta_cascade`. Nothing of this repository is installed in
                                      the daemon's environment (see §4, Host tools).
                                      It is not the repo's own `scripts/` at the root, below.
  references/<bundle>/*.json           the references CATALOG: one entry per rule, pointing at
                                      its body under knowledge/. Wired on _base_trader as
                                      `references(preload)` + `preselected:` — obligations, not
                                      a library to search.
  logs/  sessions/  .artifact_tracker.json
                                      the FRAMEWORK's runtime state, gitignored.
                                      `.jaato/` is the daemon's config_root and holds
                                      framework assets only — never a driver product.

knowledge/                 the KB's authored half, committed
  rules/<id>.md            a binding rule's text: Rule / Rationale / Scope / Examples / Sources
  checks/check-<id>/       its conformance check: check.py, stdlib only, read-only, one JSON
                           object on stdout. Reads ONLY the run's captured evidence, never the
                           network — `cannot_verify` when a cell predates the capture.
                           A check attests conformance to a rule, never the rule's validity.

.ta_cascade/               the DRIVER's runtime state, gitignored
  journal/                 per-run resume journals (see RunConfig.journal_dir)

tests/                     unit tests + test_pipeline_echo.py (daemon-marked)
scripts/measure_size.py    repo tooling YOU run (never the daemon); regenerates
                           docs/size-and-complexity.md against a reference checkout
docs/assessment.md         the port assessment (moved from the jaato repo; framework paths refer to jaato)
docs/gaps.md               living gap tracker with statuses and run findings
docs/size-and-complexity.md  lines, complexity and dependencies vs the reference
.env                       gitignored; JAATO_PROFILE_SET (+ FRED_API_KEY). No provider key: the
                           OpenRouter set names pass://jaato/openrouter/api-key, resolved daemon-side
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
`cascade_driver_id` shared by every node of one run (an observer can attach
by that id). **That is slot AFFINITY, not one slot per run**: a slot serves
one session, and this pipeline holds several sessions of the same cascade open
at once — two debaters, then three risk panellists — so each of those claims
and stamps a slot of its own. Measured over a sweep batch: 5
`cascade reuse MISS` to 6 `HIT` per 11-session run, i.e. **~5 runner
processes per concurrent run**, each ~170 MB. It is what makes a sweep's
memory scale with `concurrency × 5`, not `concurrency` (jaato#1622). Decision rationale: the
in-process facade applies only `model/provider/plugins/plugin_configs/
completion_payload_schema/suppress_base_instructions` of a named profile and
silently ignores `completion_processors`, `spawn_payload_schema`,
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
concatenate (remove only via `suppress_inherited_processors`), scalars are
child-replaces. A stage's turn ceiling is `budget_control.limits.turns`:
`max_turns` used to sit here and jaato#1068 removed the key, having measured
that it was compared against a turn counter in no path of the framework.
Every `_base_<agent>`
carries a `budget_control` ceiling — per session, on `usd` (OpenRouter's
reported cost), `tool_calls` and `seconds` (summed across the session's turns),
with `abort` at 100%; sizing is in `docs/gaps.md` #15. Its `limits` are
MIN-WINS too: a set profile may tighten a ceiling, never raise it. An aborted
stage fails like any other: `StageFailed` naming the stage or debate turn and
the daemon's reason, journal kept, re-run to resume. That holds because
`ask()` raises `SessionEnded` for a turn a session's end cut short (jaato#1007;
before it, the next `ask()` on that session hung forever) and `complete()`
leaves the reason on `Session.terminus`; `pipeline._ask` / `_complete` are the
only callers of either, and turn both into `StageFailed`.

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
run in the driver process and return strings. They exist only while the
driver is attached (a cold session woken with no client is `DEFERRED`).

**A handler's deadline is DERIVED, never written down here** (jaato#1625).
The daemon holds each host-tool call to a budget — 30 s unless the spec's
`timeout` (MILLISECONDS) names another — and on expiry hands the model
`{"error": "Client tool <name> timed out after <N>s"}`, a transport error
where this repository's data contract is a sentence the model can read. So
`tools.handler_deadline_s` asks `jaato_sdk.client_tool_timeout`, the module
the daemon's own registration path calls, and subtracts
`tools.HANDOFF_MARGIN_S` (5 s, covering the result event's trip back). Then
`sessions.check_tool_budgets` compares the derived numbers against what the
daemon REPORTS for that session (`session.client.client_tool_timeouts`,
protocol 1.39+) and raises `ToolBudgetMismatch` on any disagreement,
including a daemon too old to answer — so the derivation is verified once per
session rather than trusted. A handler that needs longer than the default
does not get a bigger constant: it declares `timeout` on its spec, and the
deadline follows. `TOOL_BUDGET_S = 45.0` used to sit above the daemon's
budget, which made our deadline dead code and cost five arms of the third
batch; see `docs/gaps.md`, 2026-10-11.

**Prefetch is NOT used here, and must not come back** (retired 2026-10-17).
The framework's `{{!py:...}}` placeholder runs a script **inside the runner at
session-prep**, so its imports resolve in the DAEMON's environment — and
`script_imports: workspace_venv` is no escape, since it is a `plugin_configs.cli`
key and the analyst stages declare `plugins: []`. The sentiment analyst used it
for its four sources, which is why `ta_cascade` was editable-installed into the
shared daemon venv: the one workspace of thirteen on this host that put a driver
package there. It now uses host tools like the other three analysts, so the data
layer runs in the driver process out of this repository's own venv. A
`.jaato/scripts/` file may import stdlib and its neighbours in that directory
(`sys.path.insert(0, str(Path(__file__).parent))`, the convention every sibling
cascade follows) and nothing else. See `docs/gaps.md`, 2026-10-17.

**The `echo` provider** is the framework's deterministic test double:
`plugin_configs.echo.tool_call` emits one canned tool call on the first
turn (used for `signal_completion` with a canned payload), `response` gives
canned text, and `usage` is **mandatory** (a turn reporting no tokens emits
no terminal event and `complete()` waits forever; `validate` flags it as
`echo_reports_no_usage`). It cannot script a multi-turn tool loop; one call
then text is all it does.  **So a completion gate that requires the session
to have CALLED something cannot be exercised by echo**: refusing the
completion sends it back to do what it cannot do, the nudges exhaust and the
stage dies with `NudgeExhausted` — `on_exhausted: allow` does not save it,
because the failure is not exhausted refusals.  The echo set declines such a
gate by name (`suppress_inherited_processors`), as `echo/trader.yaml` does
for `rules_read`.

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
   session-prep must be bounded. Hence `data.with_deadline`. The prefetch
   itself is gone (§4), which retires this trap for the sentiment stage —
   a host tool runs in the driver process, where a stall cannot reach
   `session.bootstrap` — but the lesson stands for anything added at
   session-prep later.
2. **`python -m jaato_server --daemon` returns before the socket is bound.** A
   client with `auto_start=False` must wait for the socket file (the test
   fixture polls for it up to 180 s). **After an UNCLEAN death, polling for the
   FILE is worthless** — a daemon that is killed leaves the socket, the pid file
   and the restart config behind, so the file is already there and the poll
   returns at once, before the new daemon has bound anything. Measured
   2026-10-23: a start after a SIGKILLed daemon reported "socket present after
   1s" while nothing was listening. Poll for a CONNECT (`socket.connect` on
   `AF_UNIX`, retry until it stops raising), which is also what proves the
   thing is ready rather than merely present.
3. **Client autostart can race a busy daemon.** With `auto_start=True` a
   client that times out its first connect attempt tries to start another
   daemon on the same socket. When something else owns the daemon (tests,
   an operator), pass `auto_start=False` (`RunConfig.auto_start`).
4. **Unix socket paths are limited to ~104 characters.** The test fixture
   picks a short temp dir for the private socket.
5. **`--stop` finds a daemon by its SOCKET; the pid file is the fast path,
   not the requirement.** `check_running` reads the pid file first and falls
   back to `_pid_on_socket`, which resolves the owner of the socket and
   verifies its cmdline — so
   `--stop --pid-file /tmp/jaato.pid --ipc-socket /tmp/jaato.sock` stops a
   daemon whose pid file has been deleted (measured twice, 2026-10-19 and
   2026-10-20). Pass BOTH flags for a daemon on custom paths.
   **The hazard that made this matter is FIXED** (jaato#1764, PR #1785, pulled
   2026-10-21): the pid file, restart config and log are now DERIVED from the
   socket by one module, `jaato_sdk.daemon_paths`, which the server, the SDK's
   autostart and `jaato-doctor` all read — so a daemon on a private socket can
   no longer write or delete ours. `/tmp/jaato.sock` still maps to
   `/tmp/jaato.pid`, so nothing here changed. Explicit flags still win. Before
   that fix, a default pid file could name a LIVE but unrelated daemon and
   `--stop` would kill it; against a daemon built before #1785 — the version
   string does not move, so check the build, not `1.3.0` — read the pid back
   from `ps` before trusting it (`docs/gaps.md`, 2026-10-20 and 2026-10-21).
6. **ERROR lines in the daemon log that are noise here:** an `mcp` package
   version traceback (`'types.UnionType' object has no attribute
   'model_validate_json'`) and `file_edit` refusing to initialise without a
   `config_root` — neither plugin is in any profile's `plugins:` — and a pair
   whenever an observer disconnects with an event still in flight:
   `Send error to ipc_N: Connection lost` then `Error reading from ipc_N:
   [Errno 32] Broken pipe`. The daemon writes one more event to the observer
   a millisecond after `cascade.unregister` removed it; the run is unaffected.
   Seen for this driver's own observer at the end of a run (2026-09-12), and
   about 70 times across 2026-09-05 … 09-12 from all the daemon's clients.
   **Search every `/tmp/jaato.log*` before calling a daemon line new:** the
   daemon rotates its log, and a count taken from the fresh file alone
   reported this pair as "first seen today".
7. **`jaato-scaffold new profile-set` refuses `--provider echo`** (echo is
   hidden on purpose); the echo set was written by hand (a small Python
   generator did it — see the commit that added `.jaato/profiles/echo/`).
8. **`new cascade --transport in_process` needs `--provider/--model`**;
   irrelevant now (daemon transport) but explains the scaffolded header.
9. **Reddit's JSON search endpoint is WAF-blocked for anonymous clients;
   the Atom RSS search feed works** with an identified User-Agent. A 429 is
   retried once after at most `retry_wait_cap` (5 s) — a longer backoff
   risks the handler's derived deadline (§4, Host tools).
10. **StockTwits' public symbol stream serves recent messages only**, so a
    historical window is normally empty and reported as quiet. Crypto pairs
    are addressed as `<BASE>.X`. **Since 2026-09-23 the endpoint answers
    403 Forbidden to this client**, so the source is *unavailable* rather
    than quiet — a different sentence in the data contract (§7), and the
    right one: nothing is inferred from an absence that was never observed.
    Reddit degraded in the same run (`r/stocks` and `r/investing` failed,
    `r/wallstreetbets` returned). See `docs/gaps.md`, 2026-09-23.
11. **The `subagent` plugin README in jaato is stale** (documents
    `background=True` / `get_subagent_result`, which do not exist). Trust
    `jaato-scaffold explain plugin subagent`.
12. **Every session this driver opens is now AppArmor-CONFINED, and we never
    asked for it.** Since protocol 1.46 (jaato#1808, #1809) a daemon with a
    kernel backend confines any client-driven IPC session it was not told to
    leave unconfined. A pre-1.46 SDK sent `apparmor: false` by DEFAULT, and
    that is deliberately NOT read as an opt-out: `client_signal` returns
    `True if legacy is True else None`, so our `false` means "not said" and we
    get the daemon's default. Do not try to opt out to keep the old behaviour —
    it is measured working here: on 2026-10-23 the whole end-to-end tier ran
    with `confined=True` on every session (`[confinement] confined by default
    (apparmor)`, `enforced=True`), including the stage that reads the
    workspace, and the startup warning that the runner's interpreter is
    "inside the workspace root /home/apanoia; not granting it (model-writable)"
    did NOT prevent a single bootstrap. It costs **~505 ms per session** of
    profile provisioning (501.6 ms of it the AppArmor parser), which a sweep
    pays per session, not per run. What is still UNMEASURED is a confined
    session making a real HTTPS call to a provider: echo needs no network, and
    the CA-bundle grants that make TLS work under confinement landed in the
    same payload (jaato#1814) — though since SDK rc30 the ANSWER is readable
    from the client: `DiagnosticsResultEvent` carries `confinement_decision`
    (why the session is or is not confined) and `provider_files` (each file a
    provider declared, with `copy` / `grant` / `none` / `refused` and the
    reason), and `sessionlog._consumption` already asks `get_diagnostics()`
    once per session while it is still attached, which is where those two
    belong when someone wants them per stage.
    **This client could not say anything about confinement until rc30.** rc28
    speaks protocol 1.45, which has no field for it; 1.46 adds
    `workspace_confinement` (`None` = the daemon's default, `True` = confine,
    `False` = an announced opt-out) to `IPCClient`, `IPCRecoveryClient` and
    `convenience.session(...)`, with `apparmor` kept as a deprecated alias
    whose default moved from `False` to `None`. `sessions.open_stage` passes
    NEITHER, deliberately: unset means the daemon's default, which is
    confinement, and that is measured working above. Leave it unset — an
    explicit `False` is an announced opt-out and would be a per-run workaround
    for a thing that is not broken.
    The host-scoped escape is
    `JAATO_IPC_CONFINE_DEFAULT=off`, announced at WARNING at startup — an
    operator's decision about this host, never a per-run workaround.
13. **`budget_control.limits.turns` does not count the stage's turns, and so
    cannot bound a tool loop.** Measured 2026-10-25 over the ten sessions of
    the NVDA 2026-10-17 run: `budget_usage.turns` is **1.0 for every one of
    them**, while the session record's own `turn_count` runs 1 … 7, and
    `turn_accounting` holds a single `{"turn": 0}` entry listing all of a
    session's calls. To `budget_control` a "turn" is one provider BINDING, not
    a step of the model's tool loop. Consequences, both real: the **trader
    reached `turn_count` 7 against its declared `turns: 6`** and
    `budget_exhausted_reason` stayed `None` — the `degrade: [{at: 100, action:
    abort}]` rung never fired; and the dimension looks like the binding one on
    any stage whose tool use is light (1/8 beats 5/60), so a reader told
    "turns binds" would tune a ceiling that does nothing. **What actually
    bounds a stage here is `tool_calls` and `seconds`.** This is the same shape
    as `max_turns`, which jaato#1068 removed "having measured that it was
    compared against a turn counter in no path of the framework" — one key
    later. `runview` reports BOTH numbers and flags the disagreement rather
    than picking one; the `turns` entries in every `_base_<agent>` ceiling have
    not been changed, because re-sizing a ceiling is a decision about this
    pipeline and not a consequence of reading its telemetry. NOT yet filed
    upstream.

---

## 7. The data layer's contract (keep it)

- Every public function returns `str` and never raises; the failure path
  returns `_unavailable(...)` text. Unknown indicator names, a missing
  credential, network errors, empty frames all become sentences.
- **That promise covers DATA failures, not our own bugs.** `with_deadline`,
  which wraps every tool handler, re-raises `NameError` and `AttributeError`
  (`data.BUGS_NOT_DATA`) rather than rendering them as missing data. It used
  to render them, and `get_fundamentals` answered `DATA_UNAVAILABLE ...
  NameError: name 'stale' is not defined` for six days while the analysts
  dutifully reported a source that was unavailable — a third of a backtest's
  arms died of it. The narrowing applies at THAT boundary only, because
  `with_deadline`'s one caller passes our own lambda; inside `data`'s own
  handlers the same exception is usually the library choking on a bad
  response. (`gather_with_deadline`, the session-prep sibling, went with the
  prefetch on 2026-10-17: nothing of this repository's code runs inside the
  runner any more.) See `docs/gaps.md`, 2026-10-09.
- **Credentials come from the pass store, one entry each, never a chain**
  (`_pass_secret`): `pass://jaato/finnhub/api-key`, `pass://jaato/fred/api-key`.
  A key that can arrive from several places fails in several ways and the one
  that matters is silent — `macro()` read `FRED_API_KEY` from the environment,
  nothing ever set it, and macro data was quietly unavailable for the life of
  the project.
- **`macro()` is vintage-pinned** (`realtime_start`/`realtime_end` at `as_of`),
  so a revised figure cannot leak backwards into a historical cell: a backtest
  sees the number the market saw. It is the only input with unlimited
  point-in-time history — company news stops at ~12 months (Finnhub free tier),
  statements at ~2 years, and the `info` block is withheld for any past date.
- `as_of` bounds everything; `end_date` arguments are clamped to it.
- Indicators are computed in pandas (`compute_indicators`): SMA 20/50/200,
  EMA 10, RSI 14 (Wilder), MACD 12/26/9, Bollinger 20/2, ATR 14, VWMA 20.
  Their periods count trading sessions; every `lookback_days` window counts
  calendar days up to the as-of date. `snapshot()` is the "verified numbers"
  block the market analyst must quote from: it states its window and gives
  the high and low with their dates and the last closes with theirs.
- Stale prices are refused, not quoted: `ohlcv`, `indicators` and
  `snapshot` return an UNAVAILABLE sentence when the newest bar is more
  than `RunConfig.max_stale_days` (7) calendar days before the date asked.
- **yfinance `info` is undated — every ratio in it describes TODAY — so
  `fundamentals()` CLAMPS it rather than warning about it.** Identity
  (`shortName`, `sector`, `industry`) is served at any date; the seventeen
  valuation, margin and growth ratios only when `as_of` is the present, by the
  same `max_stale_days` the price layer uses. A historical cell is refused them
  and pointed at `get_statement`. Serving them with a note was lookahead: the
  numbers reached the model anyway, and a backtest reading today's multiple for
  a cell six months back can manufacture skill out of hindsight. The pilot ran
  that way. Statements are filtered by period-end date, with a filing-lag note,
  and are the point-in-time source.
- **News comes from Finnhub** (`pass://jaato/finnhub/api-key`, read by the
  DRIVER from the pass store, not an env var). `company-news` takes `from`/`to`
  natively, so a historical window is SERVED rather than filtered out of a
  recent feed — which is what yfinance did until its news endpoint began
  answering 404 on 2026-10-03, and why the pilot's sixty April–August cells ran
  with no company news at all. `global_news` uses Finnhub's general feed, which
  takes NO date range and carries only the last few days: it compares the span
  it actually carries with the window asked for and reports a window outside it
  as unavailable, never as quiet.
- **Three kinds of nothing, three sentences.** `DATA_UNAVAILABLE` = we were not
  served (a 404, a missing credential, a feed that cannot cover the window);
  `NO_DATA` = the source served items and none fell in the window, so the
  window really was quiet; articles = what we saw. Collapsing the first two
  lets a model reason about a silence nobody observed, which is how a dead
  endpoint read as "a quiet month for NVDA".
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
  `JAATO_PROFILE_SET=echo`, and runs against the daemon ALREADY RUNNING
  (`/tmp/jaato.sock`, or `TA_E2E_SOCKET`) rather than starting a private
  file, runs the whole pipeline twice (the second run
  resolves the first run's decision through the reflector and injects the
  lesson), then a resume test with a pre-seeded journal and a spy on
  `open_stage`, then a budget test: in a copy of the workspace it caps one
  `_base_<agent>` at a time (`tokens: 10`), and a capped debater and a capped
  judge must each fail by name with the journal kept before the run resumes
  and finishes. `data.instrument_context` and `data.return_after` are
  monkeypatched so the driver never touches the network either. **It does NOT
  stop the daemon** — teardown removes only the temp workspace. It used to
  start and stop a private one; since the tier shares the daemon you already
  have (jaato#898 is closed), stopping it would kill the service the other
  twelve workspaces on this host are using. Last measured **2026-10-23: 3
  passed in 120.89 s** on SDK 0.30.0rc30 (protocol 1.46), every session
  AppArmor-confined — 40 profiles applied across the tier's two temp
  workspaces, no `confined=False`, no `enforced=False` (see trap #12).
  The same tier read 3 passed in 162.63 s earlier that day on rc28,
  and 274.87 s on 2026-10-17 — the framework took the workspace monitor off
  the session-create path in the same payload (jaato#1811), so the speed-up is
  not attributable to this repository's `workspace_monitor: false` alone, and
  a single timing on a host with seven other tenants resident is not evidence
  of anything finer than the order of magnitude.
- What echo cannot test: an analyst's real tool loop. It scripts ONE canned
  tool call and that one is spent on `signal_completion`, so a stage that
  must call several tools before it writes can only be measured against a
  live model (or a recorded provider trace via the profile `trace:` block).
  Both analysts that have been measured that way passed: the market analyst
  on 2026-09-08, and the sentiment analyst's four host tools on 2026-10-17 —
  five tool calls in one turn, no nudges, the payload's `tools_used` matching
  the daemon's own `used.tool_calls`. The news and fundamentals analysts have
  not been run that way, and neither set has been measured on
  `openrouter_sonnet` since the sources moved to host tools.

---

## 9. State of the work and what is next

Merged on `main` (PR #1): the driver, the workspace, both profile sets,
StockTwits/Reddit ingestion, 22 unit tests and the end-to-end run.

Not done (see `docs/gaps.md` for the full table):

1. **A run against a real model.** Store the OpenRouter key at
   `pass://jaato/openrouter/api-key` — the set resolves it daemon-side, and
   `jaato-doctor --secret pass://jaato/openrouter/api-key` proves it
   (`JAATO_PROFILE_SET=openrouter_sonnet` is already in `.env`), run
   `python -m ta_cascade analyze NVDA <recent date> --analysts market -v`,
   read `.jaato/logs/` and `results/`. Expect to tune each stage's
   `budget_control` ceiling,
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
