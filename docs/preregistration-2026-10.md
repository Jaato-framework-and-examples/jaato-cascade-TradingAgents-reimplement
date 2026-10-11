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
