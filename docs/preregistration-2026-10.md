# Pre-registration: does the pipeline predict?

**Written 2026-10-03, before any cell of this experiment was generated or run.**
Nothing below may be changed once the first arm starts. If something here turns
out to be wrong, the run is abandoned and re-registered — it is not amended
mid-flight, and the amendment is not applied to data already seen.

This document exists because of a specific failure earlier in this project. On
2026-09-19 the hold band was widened *after* seeing that it raised the pass
rate, and the result was presented as a finding. The author's own judgement is
not a sufficient guard against that; declaring the ruler in advance is.

---

## 1. The question

**Does the pipeline's directional call carry information about the
instrument's return over the following five sessions, relative to SPY?**

Null hypothesis: it does not — the mean of (direction × alpha) is zero.

This asks nothing about whether the pipeline is *useful*, profitable after
costs, or better than a simpler rule. It asks only whether the signal is
distinguishable from chance.

## 2. What is under test

Not the four-analyst design described in `CLAUDE.md` §1. A **reduced
pipeline**, because that is what the data layer can actually serve at a
historical date (`docs/gaps.md`, 2026-10-03):

| stage | state in this experiment |
|---|---|
| market analyst | full — price, indicators, verified snapshot |
| news analyst | company news (Finnhub) + macro (FRED, vintage-pinned). **No global news**: Finnhub's general feed takes no date range. |
| fundamentals analyst | **statements only**. The `info` block's valuation ratios are withheld for any historical date — they are undated and would be lookahead. |
| sentiment analyst | **disabled**. All four of its sources are dead. |
| bull / bear debate, research manager, trader, risk panel, portfolio manager | full |

Any result applies to *this* pipeline on *these* inputs. It is not evidence
about the four-analyst design, and the distinction must survive into any
summary of the outcome.

## 3. Sample

- **Tickers (12), fixed now:** NVDA, AMD, MSFT, AAPL, GOOGL, JPM, BAC, XOM,
  CVX, UNH, JNJ, KO.
  Chosen for sector spread and a volatility range, deliberately not for past
  performance; none was selected after seeing any result of this experiment.
  Six sectors, so no single theme dominates as AI semis did in the pilot.
- **Dates:** weekly, Mondays, **2025-11-03 → 2026-09-21** inclusive (**47
  dates** — see the amendment in §10). The start is Finnhub's free-tier news
  horizon (~12 months); the end leaves five sessions for resolution.
- **Cells:** 12 × 47 = **564**, one run each. No repeats: the pilot already
  established that the pipeline disagrees with itself, and re-measuring that
  spends cells on a known answer.
- **Profile set:** `minimax_m3`.

## 4. Primary measure — one, declared

For every cell whose portfolio-manager rating is directional
(Buy/Overweight → +1, Underweight/Sell → −1; Hold is excluded):

```
score = direction × alpha
alpha = instrument return over the holding period − SPY return over the same period
```

**Primary statistic: the mean of `score` across all directional cells.**

**Interval: a bootstrap 95 % CI resampling DATES, not cells** — 10 000
resamples, dates drawn with replacement, all cells of a drawn date taken
together.

That clustering is not a detail. Twelve tickers on one date share a market, so
552 cells are not 552 independent observations. Alpha removes the index move
and therefore much of that, but sector and theme correlation survive it.
Resampling cells would understate the interval and manufacture significance.
A naive per-cell CI will also be reported, labelled as the optimistic bound,
and the **clustered interval is the one that decides the question**.

**The result is positive only if the clustered 95 % CI excludes zero.**

Power: ~395 directional calls expected (the pilot ran ~70 % directional). On a
binary reading that is ±4.9 pp, enough to separate a 60 % hit rate from chance;
a 55 % edge would need ~783 and is out of reach here. A continuous measure is
used precisely because it carries more information per observation than a
hit rate.

## 5. Secondary measures — reported, never promoted

Declared now so that none can be elevated to primary after the fact:

- directional hit rate (sign agreement), with the same clustered interval;
- mean `score` split by rating strength (Buy/Sell vs Overweight/Underweight);
- Hold calls scored against the ATR band, reported separately and **excluded
  from the primary**;
- conformance: the fraction of proposals satisfying `stop-placement`;
- cost and effort per cell from `sessions.jsonl`, reported as
  measured N/M (MiniMax is a subscription, so `cost_usd` will be null and must
  not render as $0.00).

Any analysis not listed here is **exploratory**, is labelled as such, and
cannot be cited as a result of this experiment.

## 6. The ruler, frozen

- holding period: **5 trading sessions** after the as-of date
- benchmark: **SPY**; a cell whose ticker is SPY scores its raw return (none here)
- hold band: **one ATR(14) over the holding period**, `data.hold_band`
- stops: honoured **along the path** — a long stopped when a session's low
  reaches the stop, a short when a high does; scored at the stop
- rating → direction: `score.DIRECTION`, the shared vocabulary

`ta_cascade/score.py` is frozen at the commit recorded in §9 below. If it
changes before the run completes, the run is void.

## 7. Exclusions, declared in advance

- A cell that produces **no decision** (a stage failed, the arm errored) is
  excluded and **counted in the report**. If more than 10 % of cells are
  excluded, the experiment is reported as inconclusive regardless of the
  statistic, because a pipeline that only finishes on easy cells is a
  selection effect.
- A cell that cannot be graded (not enough bars) is excluded and counted.
- **Degraded inputs are NOT grounds for exclusion.** A cell where news was
  unavailable stays in. That is the pipeline's real operating condition, and
  removing those cells after seeing them would be the 2026-09-19 mistake in a
  new costume.

## 8. Known limits that no sample size fixes

- **One regime.** 46 consecutive weeks of one market. A result describes this
  period, not markets.
- **Survivorship in the ticker list.** All twelve exist and are liquid today;
  none was delisted or distressed during the window.
- **Reduced pipeline** (§2).
- **News volume is capped** at ~250 articles per request and is thinner for
  low-coverage names (KO returned 41 for a week where NVDA returned 250), so
  input richness varies by ticker.
- **Coverage per ticker varies by a factor of six**, verified across all
  twelve at both ends of the window before registering: the start week
  (2025-11-03) returned 247 articles for NVDA and 47 for UNH; the end week
  returned 248 and 41. So the mega-cap tech names sit at Finnhub's ~250 cap
  while the rest run 41–123, and the news analyst is working with materially
  more evidence on some tickers than others. This is a property of the
  instrument set, constant across the window, not a drift.
- **The window start was placed inside full coverage, not at the cliff.**
  Finnhub's horizon falls off between 11 and 12 months (247 articles at 11,
  99 at 12, zero at 13). Starting 2025-11-03 keeps every cell on the flat part,
  so there is no early-vs-late news gradient to confound an early-vs-late
  comparison.

## 9. Provenance

| | |
|---|---|
| registered | 2026-10-03 |
| scorer frozen at | `ta_cascade/score.py` as of the commit that adds this file |
| tasks generated | *(after this file is committed)* |
| run started | **2026-10-09** (AAPL batch first; see §10) |
| run completed | *(to be filled)* |

The order matters and is checkable in `git log`: this document is committed
**before** the task files exist. A reader who doubts the ruler was fixed in
advance can verify it there rather than taking anyone's word.


---

## 10. Amendments

### 2026-10-06 — the date count was wrong, and the registration was not pushed

Two corrections, both made before any cell ran, both recorded rather than
quietly applied.

**The count was a fencepost error.** 2025-11-03 to 2026-09-21 is 322 days,
which is 46 *intervals* and therefore **47 dates** inclusive; the cells are
**564**, not 552. The original figure counted the gaps between dates instead
of the dates. Expected directional calls move 386 → 395 and the naive interval
±5.0 → ±4.9 pp.

**The window itself is unchanged.** Both endpoints were fixed in §3 and both
stand; only the count derived from them was wrong. Moving the end date back a
week so the total matched the number already written was considered and
rejected: adjusting an experiment to fit a figure in its own registration is
the exact failure this document exists to prevent, and it would have discarded
twelve real observations to protect a typo.

**The registration was committed on 2026-10-03 and not pushed until today.**
It sat as a local commit while the branch it was on was merged without it, and
was reported in the interim as having landed. It has not been edited in that
window — the author date on the commit is 2026-10-03 and the content is as
written then, apart from this section — but the ordering guarantee is weaker
than §9 claims: a reader can see the task files and this document arrive in the
same push, with this document as the earlier commit, rather than seeing it
pushed days before the tasks existed. That is worth less than the original
claim, and the difference is recorded here instead of being left for someone
to discover.

Nothing else changes: the primary measure, the date-clustered interval, the
secondary list, the exclusions and the kill switch are as registered.

### 2026-10-09 — the run is executed in batches, and why that is not a peek

The 564 cells are run in batches rather than in one sweep, starting with the
47 AAPL cells. This is an **operational** decision with one scientific
constraint attached, and the constraint is the reason it is written down.

**Why batches.** §7 excludes a cell that produces no decision and declares the
experiment inconclusive if more than 10 % of cells (57) are excluded. So the
binding risk is not wall-clock but the exclusion budget: an arm that dies of
resource contention or provider throttling spends it just as surely as a
pipeline fault. Three things were unmeasured before the first batch — the
failure rate on `minimax_m3` with three analysts, whether MiniMax throttles
concurrent requests on a subscription plan (neither
`explain provider minimax` nor the profile set documents a limit), and peak
memory at concurrency 4 on a shared box where the end-to-end suite has been
OOM-killed twice. Measuring those on 47 cells rather than 564 is cheaper in
exclusions, and `--resume` makes the remainder a continuation rather than a
re-run.

**The ticker was chosen without reference to any outcome.** AAPL is first
alphabetically among the twelve. No price, return, or prior result entered the
choice, and the batch is the whole 47-date column for that ticker, not a
subset of its dates.

**What the batch may be read for, and what it may not.** Between batches the
only quantities consulted are operational: arm state counts, error strings,
wall-clock, memory. **Pass rate, hit rate, and any directional result are not
consulted, and no batch boundary is a decision point about whether to
continue.** All 564 cells are run regardless of what the first 47 score,
because the primary measure in §4 is declared over the full sample and a
sample truncated after seeing its outcome is not that measure. This document
declares no interim-analysis rule and none is being added; if the sweep is
abandoned it will be for an operational reason, named here, with the cells
that ran reported as the exclusions they are.

The distinction matters because this project has already made the opposite
mistake once: the 2026-09-19 pilot was re-read after the fact with cells
removed on grounds discovered by looking at them. Batching for resources is
not that. Batching and then stopping because the early numbers looked good —
or bad — would be.

**Order does not affect grading.** Each cell is graded against its own
realised returns over its own holding period (§6), so the sequence in which
cells run cannot change any cell's score.

**The scorer is unchanged.** `ta_cascade/score.py` is byte-identical to its
state at the registration commit `a9f9ed0`, verified before the first batch
launched, as §6 requires.

### 2026-10-09 — the first AAPL batch is voided in full, before it is re-run

The AAPL batch described above was launched at concurrency 4 and stopped
after seven arms. **All seven are voided — including the two that passed.**
They are preserved verbatim as
`backtests/predict-2026-10/results-VOIDED-2026-10-09-thrash.jsonl`; nothing is
edited and nothing is deleted. The file is renamed rather than kept as
`results.jsonl` precisely so that `--resume`, which skips every `task_id`
already present, re-runs all seven cells instead of freezing them.

**What the seven were.**

| cell | state | s | turns | why |
|---|---|---|---|---|
| AAPL/2025-11-03 | FAIL | 296 | 3 | `DriverStoppedShort: driver exited 1`, stopped at `fundamentals_analyst` |
| AAPL/2025-11-10 | PASS | 531 | 11 | — |
| AAPL/2025-11-17 | PASS | 528 | 11 | — |
| AAPL/2025-11-24 | BLOCKED | 653 | 9 | killed by SIGTERM — the operator's `pkill` |
| AAPL/2025-12-01 | BLOCKED | 357 | 7 | killed by SIGTERM — the operator's `pkill` |
| AAPL/2025-12-08 | BLOCKED | 123 | 2 | killed by SIGTERM — the operator's `pkill` |
| AAPL/2025-12-15 | BLOCKED | 120 | 1 | killed by SIGTERM — the operator's `pkill` |

**The operational condition, which is what voids them.** Every one of the
seven ran while the host was thrashing. The box reached **23–25 runner
processes**, available memory fell 2257 → 617 MB and swap was fully consumed
(2047/2047 MB). The sweep was stopped to avoid an OOM kill, and the four
BLOCKED arms are that stop.

**Why 23–25 runners for 4 arms.** One arm does not hold one runner slot. The
pipeline keeps several sessions of the same cascade open at once — two
long-lived debaters, then three risk panellists — and a slot serves one
session, so each additional concurrent session claims and stamps another slot
for that cascade. Counted over the whole batch from `/tmp/jaato.log.1`,
`PoolManager.acquire_slot` logged **29 `cascade reuse MISS` to 19 `HIT`**
across the seven cascades, and each of the two arms that finished shows **5
MISS / 6 HIT** over its 11 sessions. So the live demand is roughly
`concurrency × 5`, not `concurrency`; at 4 that is ~20 slots, plus the idle
floor and the per-cascade reservations that linger for the pool's 300 s
cascade-idle timeout — which is the 23–25 observed.

*A correction to the first version of this paragraph, same day:* it said each
arm "cold-forked a fresh runner" on a MISS and quoted 5 MISS to 1 HIT. Both
were wrong. The 5:1 was a six-acquire sample taken during the arms' startup,
where every first acquire is necessarily a MISS; the batch ratio is the 29:19
above. And a MISS does not cold-fork: `acquire_slot` path (2) takes a PURE
IDLE slot and stamps it, which is warm — "fresh slot" in the log line means
freshly stamped, not freshly spawned. Cold-spawn is only the path where no
idle slot qualifies at all. `jaato-eval`'s advice to keep
`JAATO_RUNNER_POOL_SIZE >= concurrency` is therefore right about latency, and
the idle slots it adds are capped by `JAATO_RUNNER_POOL_MAX_SIZE`
(default 2 × size); neither is what the memory went on.

**Why the whole batch and not the four.** The condition declared above is a
property of the batch, not of an arm: it was visible on the host, it applies
uniformly to all seven, and it was identified from memory and pool telemetry
rather than from any score. Keeping the two PASSes and the FAIL and re-running
only the four killed arms was considered and rejected — it would retain
exactly the arms that happened to finish under the pathological condition,
which is a survivorship filter, and the author has by now seen all seven
states. Once an outcome has been seen, the only honest exclusion rule is one
that cannot select on it, and "every arm in the batch" is that rule.

**These seven do not spend the §7 exclusion budget.** §7 excludes cells that
produce no decision *in the recorded run*; a voided batch is not a recorded
run, and the cells are re-run from scratch. Were the four BLOCKED arms instead
left in `results.jsonl`, they would have consumed 4 of the 57 permitted
exclusions for a cause that is purely the operator's, which is the second
reason for the rename.

**The one open question is carried, not resolved.** AAPL/2025-11-03 failed at
`fundamentals_analyst` with `nudges=0`, `finish=stop`, no budget ceiling
reached and no gate refusal — so it is not nudge exhaustion and not a budget
abort, and there is no evidence either way on whether contention caused it.
If that cell fails the same way on the re-run, with the host quiet, the cause
is in the pipeline and belongs in `docs/gaps.md`.

**The re-run changes concurrency only.** The batch is relaunched at
`--concurrency 2` against a daemon at its default pool target of 2. No task
file, persona, profile, schema, gate or scorer is touched: `score.py` is still
byte-identical to `a9f9ed0`. Concurrency is not a registered quantity — §4's
measure is over cells, and §6 grades each cell against its own realised
returns — so this is a resource decision, recorded because it is the reason
the batch is being run twice. Measured arm duration is **~530 s**, not the
pilot's 343 s (which was Sonnet with four analysts), so the full matrix is
~83 arm-hours and the AAPL batch ~3.5 h at concurrency 2.

The re-run was launched verbatim as, from the CLIENT venv (so that
`JAATO_EVAL_PYTHON` is the client's interpreter — see `docs/gaps.md`,
2026-10-09):

```
.venv/bin/jaato-eval run backtests/predict-2026-10/tasks-probe-aapl \
    --profile-set minimax_m3 --socket /tmp/jaato.sock \
    --out backtests/predict-2026-10/results.jsonl \
    --workspaces /tmp/predict-2026-10-ws \
    --concurrency 2 --arm-timeout 2400 --resume --keep-workspaces
```

`tasks-probe-aapl/` holds the 47 AAPL `task.yaml` files copied byte-identical
from `tasks/` and placed as its sibling, so `../../fixture` and
`../../../../.jaato` resolve to the same paths; it is a batch selector, not a
second definition of the cells. `--arm-timeout 2400` is ~4.5× the measured
530 s: an arm that exceeds it is recorded `BLOCKED` and would spend an
exclusion, so the ceiling is set to catch a hang rather than a slow arm. The
voided batch's arm workspaces were moved to
`/tmp/predict-2026-10-ws-VOIDED-thrash/` before the relaunch — the FAILed
arm had left a driver resume journal in its workspace, and an arm that reused
that directory would have resumed the voided run instead of starting the cell
fresh.

### 2026-10-11 — the second batch is voided too: the pipeline was broken, and the fix is declared here

The AAPL batch re-run at concurrency 2 was stopped after three arms and **all
three are voided**, preserved as
`backtests/predict-2026-10/results-VOIDED-2026-10-09-broken-get-fundamentals.jsonl`.
This voiding is not a judgement call: the cells have to be re-run whatever is
decided, because all three ran against a tool that could not work.

**What was wrong.** `ta_cascade/tools.py` built `get_fundamentals` with a
lambda closing over a name that was never bound in its factory, so the tool
answered `DATA_UNAVAILABLE: ... NameError: name 'stale' is not defined` on
every call since 2026-10-03 — before the first cell of this experiment ran.
Full diagnosis in `docs/gaps.md`, 2026-10-09.

**Why it cost cells.** The analysts reported the unavailable tool honestly,
and which field they put it in decided the arm: a non-empty `errors[]` stops
the run, so the two arms that filed it under `errors` FAILed and the two that
filed the same thing under `warnings` PASSed. Two FAILs in six settled arms
across both batches, against §7's budget of 57 in 564. That rate, from a cause
that is not the pipeline's behaviour under test, is what the batching in the
amendment above exists to catch, and it caught it.

**What the fix changes about what is under test, stated plainly.**

- `get_fundamentals` now works. **This barely changes what the fundamentals
  analyst can see**, and that is worth being precise about rather than
  reassuring about: §2 already withholds the `info` block's ratios from a
  historical cell as lookahead, so a working call returns the
  withheld-notice plus the company's identity (`shortName`, `sector`,
  `industry`) — which the model also receives in `instrument_context`. §2's
  "fundamentals analyst: statements only" was true as registered and remains
  true. What changes is that the stage stops dying.
- `"minLength": 1` on the `errors[]` and `warnings[]` items of all five
  completion schemas. A blank string is no longer representable, so the
  `[""]` that failed AAPL/2025-11-17 is refused by the daemon at
  `signal_completion` and the model is told why. The schemas' own
  descriptions already said never to send a placeholder; this makes it a
  constraint rather than a request.
- `data.with_deadline` re-raises `NameError` / `AttributeError` instead of
  rendering them as missing data, and a new unit test calls every tool
  handler once. Neither is model-facing.

**What was deliberately NOT changed.** Whether a tool reporting
`DATA_UNAVAILABLE` belongs in `errors[]` or `warnings[]` is still the model's
judgement, and the two batches show models split on it. Fixing that means
editing the analyst personas, which is model-facing wording and therefore a
change to what is under test. It is left open rather than slipped in while the
experiment is running; if it is done, it will be a further amendment here,
before the batch that uses it.

**No scorer change.** `ta_cascade/score.py` is still byte-identical to
`a9f9ed0`, as §6 requires. The sample, the measure, the exclusions and the
kill switch are unchanged.

**The stop was clean this time.** `SIGINT` to the `jaato-eval` parent recorded
three arms and no `BLOCKED` — the two in flight were not written at all, so
`--resume` re-runs them. The earlier `pkill` on the driver processes recorded
four `BLOCKED` arms and would have spent four exclusions on the operator. The
difference is recorded because it is the operational procedure for every
remaining batch.

**A correction to that paragraph, 2026-10-11.** `SIGINT` stops the *record*,
not the work. Two arm workspaces for the unrecorded cells were found in the
live `--workspaces` root with mtimes *later* than the copies moved aside, and
carrying a `report.md` those copies lacked: the arm drivers outlived the
parent, the move pulled their directories out from under them, and they
recreated them and finished writing. So the procedure has a second step —
wait for the driver processes to exit before moving any workspace aside — and
a caveat: an unrecorded arm still spent provider budget, so a batch's cost
read from `results.jsonl` alone is a floor, not the total. See
`docs/gaps.md`, 2026-10-11.

### 2026-10-11 — the third AAPL batch, launched after the fix

Launched at 11:21 local from the client venv, verbatim, with the command
§9 already records:

```
.venv/bin/jaato-eval run backtests/predict-2026-10/tasks-probe-aapl \
    --profile-set minimax_m3 --socket /tmp/jaato.sock \
    --out backtests/predict-2026-10/results.jsonl \
    --workspaces /tmp/predict-2026-10-ws \
    --concurrency 2 --arm-timeout 2400 --resume --keep-workspaces
```

**What was checked first**, so that a reader can tell a clean start from a
contaminated one:

| precondition | state at launch |
|---|---|
| `backtests/predict-2026-10/results.jsonl` | absent — the two voided batches are renamed, so `--resume` has nothing to skip and all 47 cells run |
| `/tmp/predict-2026-10-ws/` | **empty** — three voided sets moved aside: `-VOIDED-thrash`, `-VOIDED-broken-get-fundamentals`, `-VOIDED-orphans-after-sigint` |
| resume journals | none anywhere under the live root (`.ta_cascade/journal/`), so no arm resumes a voided run |
| voided report trees | none under the live root, so no grader can grade a voided `portfolio_decision` |
| the fix | committed before launch — `b53e0f7` (the NameError and its test), `32eb4ab` (`minLength: 1` on all five schemas) |
| tests | unit tier 138 passed; end-to-end tier 3 passed |
| profile sets | `jaato-scaffold validate` unchanged on all three: 3 warn / 3 warn / 2 warn + 13 info, zero workspace-tier errors |
| client ↔ daemon | checked by hand, since no doctor check can (jaato#1610): client SDK 0.30.0rc6 against the daemon's 0.30.0 source checkout — the same pairing batch one's completed arms and the end-to-end tier ran against |
| `tasks-probe-aapl/` | the 47 `task.yaml` files verified byte-identical to `tasks/` at commit `69a234e` |

`past_context` is `""` for all 47 cells. Each arm runs with `--no-memory`,
which gates recording and pending-resolution but not the read; the read is
empty anyway because the shared decision log's only two resolved entries
resolve in 2026 and every cell's as-of date is in 2025, so the point-in-time
filter drops them. Recorded because it is a property of the data the model
saw, not of the flag (`docs/gaps.md`, 2026-10-11).

Nothing about §4's measure, §6's scorer, §7's exclusions or the 564-cell
matrix changes here. The 47 AAPL cells remain a batch of the pre-registered
sample, and what is consulted between batches stays operational: wall-clock,
memory, spend, and the states that §7 already defines.

#### An open question §7 does not answer, raised 2026-10-11, not decided

`AAPL/2026-02-23` ran all eleven sessions, produced a valid `Hold`, and was
then discarded by the driver because the portfolio manager's `errors[]`
arrived holding the string `no-error-placeholder` — a provider quirk in the
field-by-field completion protocol, diagnosed in `docs/gaps.md`, 2026-10-11.

That arm is recorded **`FAIL`**, not `BLOCKED`. So under §7 as written it
spends **none** of the 57 permitted exclusions, while yielding no rating and
therefore contributing nothing to §4. The sample shrinks and the kill switch
does not move. At the observed rate — 1 of the first 17 arms — roughly 33 of
564 cells would disappear that way.

§7 distinguishes outcomes from infrastructure, and this is neither: the
pipeline worked and the harness worked, and a provider's serialisation of one
field threw the cell away. Three readings are available and the choice is not
the analyst's to make after seeing the data:

1. leave it a `FAIL` — the cell is lost, counted nowhere, §7 untouched;
2. count a pipeline failure against the §7 budget, which would put these in
   the same bucket as an operator's `pkill` and let ~6% trip a 10% switch;
3. define a fourth state for "the run completed and the result was
   discarded by a transport or protocol fault", excluded from §4 and
   reported separately with its own rate.

**No option is adopted here.** The question is recorded before the batch
finishes so that whichever is chosen, it was chosen against a stated rate
and not fitted to the final numbers. Any change takes effect as a dated
amendment in this section, before the batch it applies to.

### 2026-10-11, 13:55 — the third batch is STOPPED at 33 of 47: Finnhub went down

`finnhub.io`'s news endpoints began refusing connections at about 13:38 and
were still refusing at 13:55. Measured directly from the client venv, three
times:

```
news (company, Finnhub)          40.60s   ConnectTimeout: HTTPSConnectionPool(host='finnhub.io'…)
global_news (Finnhub)            40.10s   ConnectTimeout
insider_transactions (Finnhub)    1.11s   served
macro ×3 (FRED)                  ~1.0s    served
```

**The failure chain, every link measured.** `FINNHUB_TIMEOUT_S` is 20 s but a
connect timeout is retried once, so the wall time is ~40 s. That is longer
than the DAEMON's 30 s client-tool budget, so the daemon answers the model
first with a raw `{"error": "Client tool get_company_news timed out after
30.0s"}`; and it is shorter than our own `TOOL_BUDGET_S` of 45 s, so the
`DATA_UNAVAILABLE … Do not estimate or invent these values` sentence — the
whole of the data layer's contract — is never delivered. The news analyst,
given no data and no instruction, reported the failure in `errors[]`, and a
non-empty `errors[]` stops the run. Four arms died this way consecutively,
five in all.

The sweep was stopped with `SIGINT` to the `jaato-eval` parent (the real
process, not the `nohup` wrapper — signalling the wrapper does nothing).
**33 arms settled, 0 `BLOCKED`, so no §7 exclusion was spent.**

**The outage separates cleanly from the data, and that is checked, not
assumed.** Seven arm workspaces contain the 30 s timeout string — 2026-05-18,
-05-25, -06-01, -06-08, -06-15, -06-22, -06-29 — and **none of the 26 arms
carrying a rating is among them**. The rated cells all ran before 13:38.

| population | arms | pipeline failures | rate |
|---|---|---|---|
| before the outage | 28 | 2 | **7%** — the empty-array trap, `docs/gaps.md` 2026-10-11 |
| during the outage | 5 | 5 | **100%** |

The 21% over all 33 arms mixes two populations and should not be quoted as
one rate.

**Where the 26 rated cells stand** (operational, not an analysis):
ratings Hold 18, Underweight 5, Overweight 3; directional 8/26 (31%);
directional hits 3/8; mean `direction × alpha` −0.0070 with sd 0.024 on
n = 8, which is noise at that size and is recorded only so the §4 statistic
is visible as it accumulates.

**The directional rate is the finding that bears on the remaining 517.** §4
sized the experiment on the pilot's ~70% directional rate — ~395 directional
calls, ±4.9 pp, "enough to separate a 60% hit rate from chance". Across 26
rated cells M3 is directional 31% of the time. Held over 564 cells that is
~175 directional calls and an interval near ±7.4 pp, below the power §4
declared it needed. This is a sample-size property, not an outcome, so
consulting it between batches is within §4's terms; what to do about it —
accept a wider interval, enlarge the matrix, or change the instrument — is a
decision for the operator and must be amended here before the batch it
applies to.

**Nothing is voided yet.** The five outage arms are recorded `FAIL`, which
`--resume` skips, so they cannot simply be re-run; the question of whether
an external vendor outage is a §7 exclusion is the open question above, now
with a concrete instance. The two arms lost to the empty-array trap are a
separate case with a separate cause.

### 2026-10-11, 14:20 — the framework moved: the sample now spans two builds

The jaato checkout was pulled and the shared daemon restarted, by operator
decision, while nothing was running.

| | |
|---|---|
| build the 33 settled arms ran on | `9315a75d` (jaato-sdk 0.30.0, jaato-server 1.3.0) |
| build everything after this runs on | `b120c2ce` (same two version strings) |

**The version strings did not change**, so nothing in `pip`, `jaato-doctor`
or a session record distinguishes these two builds. Only the commit does,
which is why it is written down here: a reader comparing arms across this
line has no other way to know the framework moved under them. The changed
paths were the MCP plugin and remote transport, the template plugin,
`jaato_server/server/runner/rpc.py`, and the `explain` snapshot.

**Checked after the restart, before anything was run:**

- socket bound 2 s after launch (`--daemon` returns before it binds —
  CLAUDE.md trap #2, so this is polled, not assumed);
- `jaato-doctor`: 1 fail, 8 warn, 24 checks — identical to the pre-restart
  baseline, the fail being the `import jaato_server` autostart check that
  does not apply at `auto_start=False`;
- `jaato-scaffold validate` on all three sets, read by `tier` rather than by
  exit code: openrouter_sonnet 3 warn, minimax_m3 3 warn, echo 2 warn +
  13 info, **zero workspace-tier errors** — the documented baseline exactly;
- the client/daemon pairing checked **by hand**, because no doctor check can
  (jaato#1610, still unfixed in this build — it reports PASS while printing
  our path as the daemon's): client SDK 0.30.0rc6 against the daemon's
  editable `b120c2ce` checkout;
- the end-to-end tier re-run against the restarted daemon.

**Two findings survive the pull unchanged**, which matters because both were
reasons to want a newer build: the client-tool execution timeout that
discarded five arms is still absent from `jaato-scaffold explain clients` —
whose table is introduced as "every clock between connect and a turn's
terminus" — and `explain env` still exposes no knob for it.

**A consequence worth stating plainly.** Pulling rather than freezing a
snapshot means the daemon's build tracks a moving branch, so the next pull
moves it again. If the 33 settled arms are kept, the 564-cell sample spans
`9315a75d` and `b120c2ce`, and AAPL is the only ticker with cells on the
older one — a framework change sitting on top of a factor. If those arms are
voided and re-run, the whole sample is on one build. That is an argument
about which voiding decision to take, not a reason to undo this one.
### 2026-10-11, 17:51 — the framework moved again: `b120c2ce` -> `aeee87f2`

Pulled and restarted by operator decision, with nothing running: no
`jaato-eval`, no cascade, **zero peers** on `/tmp/jaato.sock`, and only idle
`--template-mode` runners on the old daemon.

| | |
|---|---|
| build the 33 settled arms ran on | `9315a75d` |
| build the 14:20 restart moved to | `b120c2ce` (nothing ran under it) |
| build everything after this runs on | `aeee87f2` |

All three declare **the same two version strings** (jaato-sdk 0.30.0,
jaato-server 1.3.0), so again only the commit distinguishes them
(jaato#1610).

Six commits. The changed paths were the `template` plugin's required-input
inference (jaato#1623, #1627, #1628), the `mcp` plugin plus a new
`schema_compat` module (#1629, #1631), and one hunk in
`jaato_server/server/runner/rpc.py` that resolves wire tool ids back to tool
names inside an error string (#1631). **No packaging metadata changed**, so
the daemon venv's editable installs were not reinstalled; both packages were
re-checked to resolve from the checkout afterwards.

Neither of those plugins is in any profile's `plugins:` here — this workspace
declares `references` and `file_edit` and nothing else — so the expectation
was no behavioural change for this pipeline. The checks below are what tested
that rather than assumed it.

**Checked after the restart, before anything was run:**

- the pull was `--ff-only` from a clean checkout, so the tree is exactly
  `origin/main` and no local work was carried into it;
- the socket bound 1 s after launch, polled rather than assumed (CLAUDE.md
  trap #2), and exactly one daemon runs: the pid in `/tmp/jaato.pid` is the
  only `jaato_server --daemon` process;
- `jaato-doctor`: 1 fail, 8 warn, 24 checks — the same shape as the
  pre-restart baseline, the fail being the `import jaato_server` autostart
  check that does not apply at `auto_start=False`;
- `jaato-scaffold validate` on all three sets, read by `tier` rather than by
  exit code: openrouter_sonnet 3 warn, minimax_m3 3 warn, echo 2 warn +
  13 info, **zero workspace-tier errors** — the documented baseline, so the
  template plugin's changed required-input inference moved none of it.
  `validate` prints `[validated by the daemon at /tmp/jaato.sock
  (jaato-server 1.3.0)]`, which is what makes these the NEW build's findings
  and not this venv's;
- the client/daemon pairing **by hand**, since no doctor check can
  (jaato#1610, unfixed in this build too): client SDK 0.30.0rc6 (published)
  against the daemon's editable `aeee87f2` checkout;
- the end-to-end tier: **3 passed in 293.88 s** against the restarted daemon, plus the unit tier at 138 passed.

**Both gaps filed this afternoon survive this pull**, re-measured against the
running daemon rather than the shipped snapshot:

- **jaato#1625** — `explain clients --connect` still lists six clocks under
  "TIMEOUTS — every clock between connect and a turn's terminus", and the
  client-tool execution timeout is not among them; `explain env` still exposes
  the same five `JAATO_*TIMEOUT*` knobs, none of them it.
- **jaato#1626** — the diff between the two builds touches no completion path
  at all (a `git diff --stat` restricted to `*completion*` and `*client_tool*`
  comes back empty), so `prepare_completion`'s rejection text is unchanged and
  the empty-array trap stands as filed.

So `TOOL_BUDGET_S` is still the queued one-line fix, and the two arms lost to
the empty-array trap would be lost the same way on this build.

**The sample still spans two builds**, not three, if the 33 settled arms are
kept: AAPL's settled cells on `9315a75d` and everything from here on
`aeee87f2`, with nothing at all on `b120c2ce` — it was the daemon's build for
three and a half hours in which no arm ran. That the middle build carries no
arms is luck rather than design; it keeps the open question exactly as narrow
as it was — whether those 33 arms are voided — without answering it.
### 2026-10-14, 22:50 — the framework moved to `976c3773`, and both filed gaps are fixed in it

Pulled and restarted by operator decision, with nothing running: no
`jaato-eval`, no cascade, zero peers on `/tmp/jaato.sock`.

**What the restart actually ended was a live skew.** The daemon PROCESS had
run since 2026-10-11 17:48 on `aeee87f2`, but the checkout moved under it
three times in between — `ac8483d9` (10-12 21:53), `1d32e877` (10-13 00:24),
`bac5e3d8` (10-14 13:44), all by someone else — and the daemon venv holds
`jaato-sdk` and `jaato-server` as **editable** installs. So every runner
spawned after the first of those pulls imported code the daemon process
itself had never loaded, while `pip`, the version strings and every session
record said nothing about it. A restart after someone else pulls is therefore
not housekeeping; it is what makes the daemon and its runners one build again.
Eighty commits separate `aeee87f2` from the new `976c3773`.

**Packaging metadata changed this time**, unlike the two 10-11 moves, so the
pull alone would have left the venv incoherent: jaato-sdk's `pyproject.toml`
moved both console scripts onto a new top-level `jaato_tool_launch` module
(jaato#1643) and declared it under `[tool.setuptools] py-modules`. The
staleness was measured, not assumed — `bin/jaato-doctor` still read
`from jaato_sdk.doctor import main`, and `import jaato_tool_launch` raised
`ModuleNotFoundError`, because the editable finder was generated before the
module existed. The editable jaato-sdk was reinstalled with
`--no-deps --no-build-isolation --no-index`, so nothing could be substituted
off an index: `pip freeze` is identical at 224 lines before and after, the
launcher now resolves, and both scripts repoint. jaato-server's metadata did
not change in this range and it was left alone.

Two operational notes from the stop, both new: `--stop` reported *"Reaped 3
orphan runner processes left behind by killed mid-cascade sessions"* — those
were the three idle `--template-mode` runners, so the wording overstates what
had happened — and it left a **stale pid file** behind (pid 1193837, verified
dead) where the 10-11 stop had removed it. It was removed by hand before
starting, after checking the pid was not alive.

**Checked after the restart, before anything was run:**

- the socket bound 5 s after launch, polled rather than assumed, and exactly
  one daemon runs: the pid in `/tmp/jaato.pid` is the only `--daemon` process;
- `jaato-doctor`: 1 fail, 8 warn, 24 checks — the documented shape;
- `jaato-scaffold validate` on all three sets, read by `tier`:
  openrouter_sonnet 3 warn, minimax_m3 3 warn, echo 2 warn + 13 info,
  **zero workspace-tier errors** — the baseline, which also means jaato#1686
  ("profiles pin an ABI", landed in this range) raises nothing against our 13
  stage profiles;
- the client/daemon pairing by hand (jaato#1610): client SDK 0.30.0rc6
  published, daemon editable at `976c3773`;
- unit tier 138 passed; end-to-end tier: **3 passed in 272.42 s** against the restarted daemon;
- the daemon log since the restart carries only the known observer-disconnect
  pair (CLAUDE.md trap #6), from the `validate` and `explain` delegations.

#### Both gaps filed on 10-11 are fixed, closed, and in this build

**jaato#1625** (closed 2026-10-14 06:08, `991be687`). `explain clients` now
carries the row this repository could not find:

    30s   client_tools=[{'timeout': <ms>}] per tool        both
          ONE host-tool call, daemon-side (the spec value is in ms)

and states the rule plainly — *"A host tool's handler that applies its own
deadline (to return an answer the model can read) must fire BEFORE the
daemon's"* — plus the reporting ask: `register_client_tools()` returns
`{name: seconds}` per tool and keeps it on `client.client_tool_timeouts`
(protocol 1.39+). Two halves with different costs for us, measured in the
installed SDK rather than inferred: **setting** the budget needs no SDK move,
because rc6's `register_client_tools` already documents an optional `timeout`
in ms and forwards every spec key except `handler`; **reading** it does,
because rc6 returns `None` and carries no `client_tool_timeouts`.
`jaato-doctor`'s `package releases` check names 0.30.0rc16 on TestPyPI.

**jaato#1626** (closed 2026-10-13 19:22, `513f937b`). All four things that
would close it: `"[]"` on an array path is now coerced to `[]` by the #1358
rule (`""` is still refused), a rejection on an array or object path names the
accepted shape, the tool and value-parameter descriptions name the empty
array, and every pending array field with no positive `minItems` carries
`set_empty_with` — the literal call,
`prepare_completion(field_path='errors', value=[])` — in every
`prepare_completion` and `query_completion` answer. Our five schemas declare
no `minItems` (the `minLength: 1` added on 10-11 sits on the ITEMS, not the
array), so the hint reaches `errors`, `warnings` and `tools_used` with the
schemas exactly as committed. **The queued schema change — dropping
`errors`/`warnings` from `required` — is therefore no longer needed to make
an empty array reachable**, and the two arms lost to that trap would not be
lost on this build.

**What this does to the open voiding question.** It does not answer it, but it
sharpens the stakes: the 33 settled AAPL arms ran on `9315a75d`, a build
carrying both defects, and a re-run would run on one carrying neither. Seven
of those 33 arms died of exactly these two causes — 2 of the empty-array trap,
5 of the 30 s clock during the Finnhub outage.
### 2026-10-14, 23:15 — `TOOL_BUDGET_S` is gone: the handler deadline is derived

Of the two shapes the 22:50 record left open for jaato#1625, the operator chose
the deriving one. The client venv moved `jaato-sdk` 0.30.0rc6 -> 0.30.0rc16 —
one line in `pip freeze`, nothing substituted, which is worth checking because
TestPyPI is the PRIMARY index and may shadow any dependency — and the constant
is gone:

- `tools.handler_deadline_s(spec)` asks `jaato_sdk.client_tool_timeout` (the
  module the daemon's own registration path calls) for the budget that spec
  will be held to, and subtracts `tools.HANDOFF_MARGIN_S`. **No budget is
  written down in this repository any more**; if the framework's default moves,
  every handler follows it.
- `sessions.check_tool_budgets` compares the derived numbers against what the
  daemon REPORTS for that session (`client.client_tool_timeouts`, protocol
  1.39+) and raises `ToolBudgetMismatch` on disagreement — including a daemon
  too old to answer. It runs after registration and before the stage's first
  turn: the first moment the answer exists, the last before the model can call
  a tool.
- 8 new unit tests (146 total, from 138); end-to-end tier: 3 passed in 300.52 s, re-run alone after a first attempt died of host contention (`docs/gaps.md`, 2026-10-14).

**What it changes for the arms.** Every handler now fires at 25.0 s against
the daemon's 30.0 s, so the third batch's five-arm failure mode — the model
reading `{"error": "Client tool get_company_news timed out after 30.0s"}`
where this repository's contract is a sentence — cannot recur in that form.
It does **not** make slow data arrive: `data.FINNHUB_TIMEOUT_S` is 20 s with
one retry, so a stalled Finnhub still exceeds the budget and now yields our
`DATA_UNAVAILABLE` sentence instead of their error. Whether to raise the three
news specs' budget (`timeout: 50000`) or cut the data layer's retry so the
chain fits inside 25 s is a sizing decision, still open, deliberately not
taken here.

**A third gap closed by the same move: jaato#1610** (closed upstream
2026-10-14 06:07). `jaato-doctor`'s `jaato_sdk checkout` check no longer
PASSes while comparing our site-packages with itself; it WARNs that the
daemon resolves the SDK from its own environment and *"client/daemon checkout
skew is unchecked"*. So every pairing note in this document that says no
doctor check can tell should now be read as: doctor says so itself, and the
hand-check is still what resolves it. The tally is unchanged at 1 fail / 8
warn / 24 checks, but its composition moved — `package releases` went quiet as
the venv came current, and this WARN arrived in its place.

**Consequence for the sample.** The driver that runs from here is not the one
the 33 settled AAPL arms ran: a derived deadline on top of `976c3773`'s two
fixes. Three of the four things that cost those arms — the empty-array trap,
the raw transport error, and the inability to tell client/daemon skew — are
addressed above the arm level. The voiding question is unchanged in kind, but
every new piece of evidence points the same way.
### 2026-10-17, 17:33 — the framework moved to 612dfc22, and the driver left the daemon's venv

Two changes, one of them not a framework move at all.

**The move.** `75e366d1` -> `612dfc22`, 42 commits. The tree was already at
`75e366d1`, not the `976c3773` the running daemon was loaded from on 10-14, so
a third party had pulled twice in between: with editable installs, every runner
spawned in that window imported code the daemon process had never loaded. The
restart is what makes daemon and runners one build again.

Pre/post: no editable reinstall was needed (the packaging diff across the 42
commits is `requires-python` and classifiers only — nine lines in five files,
no dependency, package or entry-point change). `--stop` reaped all three pool
runners and removed both the pid file and the socket, which the 10-14 stop had
not done. Restart: socket bound in 2 s, template ready, 2 pool slots. The
`jaato_client_telegram` tenant (17 days up, its own systemd unit) survived and
reconnected itself. Health checks were skipped at the operator's instruction.

**A wall arrived with this move, and it is not ours to work around.**
jaato#1076 (`85424765`) declared `requires-python = ">=3.14,<3.15"` across
every package, and this host has only Python 3.12.3. The pulled tree still
imports, byte-compiles and runs under 3.12, so the declaration gates
installation, not execution — but the next packaging change that forces an
editable reinstall of the daemon venv will be refused by pip, and the SDK
carries the same pin, so this venv cannot take the next published rc either.
Full measurement, including a wheels-only 3.14 resolution that succeeds for
every dependency, in `docs/gaps.md`, 2026-10-17. **Open, and an operator
decision**: it changes a daemon shared by every tenant on the box.

**The driver left the daemon's environment.** `ta_cascade` had been
editable-installed into the shared daemon venv since 2026-09-18 — the only
non-jaato package there — because the sentiment analyst's persona prefetch ran
inside the runner and imported it. The sentiment analyst now uses host tools
like the other three analysts, the prefetch script and its env switch are gone,
and `pip uninstall ta-cascade` has been run against the daemon venv.

Verified in order: 147 unit tests; `validate` at baseline on all three sets,
zero errors; end-to-end **3 passed in 292.08 s** with the install still
present; then the uninstall, a daemon restart so no runner could inherit the
old `sys.path`, and end-to-end again, **3 passed in 283.11 s**. The 283 s run
is the one that matters: the pipeline is measured to work with no package of
this repository in the daemon's environment.

**What it changes for the arms.** Nothing about an arm's determinism — the four
sources, their windows and their three-kinds-of-nothing sentences are
unchanged; only who calls them moved, from session-prep to the model's own tool
loop in the driver process. It does change what an arm DEPENDS on: a sweep no
longer requires the daemon's venv to carry this repository, which is the
condition that made the client/daemon split of 2026-10-09 incomplete.

**Not yet measured, and it bears on the sample.** No live-model run has
exercised the new sentiment stage. The stage must now choose to call four tools
where it was previously handed the text, and echo cannot test that (one canned
tool call, spent on `signal_completion`). Any future batch including the
sentiment analyst should be read as running a stage whose tool-calling
behaviour is unverified; the 33 settled AAPL arms did not include it, so the
existing sample is unaffected.

### 2026-10-17, 18:23 — the daemon moved to Python 3.14.2; the driver did not

The interpreter wall recorded three hours earlier is resolved on the daemon
side. The operator rebuilt the daemon venv on **Python 3.14.2** from `uv`'s
standalone build; there is still no system `python3.14`, and this client venv
remains **3.12.3**.

For the arms, two measurements and one dependency that is now gone:

- **A 3.12 client drives a 3.14 daemon.** End-to-end tier: **3 passed in
  296.14 s**, and `validate` delegates correctly to `jaato-server 1.3.0` over
  the socket. An arm's driver therefore runs on a different interpreter from
  the runners that serve it, by two minor versions, and the wire protocol is
  the only thing they share. That was the design of the 2026-10-09 split; it is
  now measured rather than argued.
- **The rebuild did not pull this repository back in.** `ta_cascade` is absent
  from the new venv. Had the sentiment prefetch still existed, this rebuild
  would have had to install this repository plus pandas, yfinance and
  matplotlib into a 3.14 venv for the stage to work at all — so the retirement
  recorded above stopped being hygiene and started being load-bearing within
  hours of landing.

**What it does not change.** No profile, persona, schema, gate, ceiling or data
function moved, so an arm's determinism is untouched; the 33 settled AAPL arms
remain comparable. What changed is which interpreter executes the runner tier,
and the pairing note for any future batch should record the daemon at
**Python 3.14.2 / jaato-server 1.3.0** against a driver at **3.12.3 with SDK
0.30.0rc16**.

**Open.** This venv cannot take SDK 0.30.0rc21 or later while it is 3.12 —
rc20 is its ceiling — so the client's SDK is now pinned by the interpreter
rather than by choice. The interpreter to move it exists on the box; whether to
move it before the next batch is an operator decision, and moving it mid-study
would change the client half of every pairing note.
