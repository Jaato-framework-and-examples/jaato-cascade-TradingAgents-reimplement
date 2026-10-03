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
- **Dates:** weekly, Mondays, **2025-11-03 → 2026-09-21** inclusive (46 dates).
  The start is Finnhub's free-tier news horizon (~12 months); the end leaves
  five sessions for resolution.
- **Cells:** 12 × 46 = **552**, one run each. No repeats: the pilot already
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

Power: ~386 directional calls expected (the pilot ran ~70 % directional). On a
binary reading that is ±5.0 pp, enough to separate a 60 % hit rate from chance;
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
| run started | *(to be filled)* |
| run completed | *(to be filled)* |

The order matters and is checkable in `git log`: this document is committed
**before** the task files exist. A reader who doubts the ruler was fixed in
advance can verify it there rather than taking anyone's word.
