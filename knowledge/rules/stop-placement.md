# Where a stop goes, and when there is none

## Rule

1. **A proposal that opens no position states no stop.** `stop_loss` is
   `null` whenever `entry_price` is `null` or the action is Hold. A stop is
   the level at which a position is abandoned; with no position there is
   nothing to abandon.
2. **A stop sits on the side of entry that invalidates the thesis** — below
   entry for a long, above entry for a short. A stop on the other side is
   not a stop, it is a target.
3. **The distance from entry to stop is at least one ATR(14)** as of the
   trade date, taken from the verified snapshot. Closer than that and the
   stop sits inside the instrument's ordinary daily range.
4. **If the snapshot carries no ATR, the proposal states no stop** and says
   so in `warnings`. A stop placed on a level the snapshot did not supply is
   a level that was invented.

## Rationale

A stop closer than one ATR is hit by ordinary movement rather than by the
thesis being wrong, which converts a directional call into a coin flip on
intraday noise and realises the loss without the information that would
justify it.

This is not a theoretical concern here. In the 12 × 5 pilot of 2026-09-19,
**12 of 19 proposals that carried a stop were stopped out inside the
five-session holding period**, and the scorer books a stopped position at
the stop rather than at the period's close, so those arms were graded on the
noise rather than on the call.

## Scope and limits

The rule governs *placement*, not whether a stop should exist at all, and it
is silent on sizing. One ATR is a floor, not a recommendation: a thesis whose
invalidation level sits three ATR away should use that level.

It says nothing about whether the direction was right. A proposal can satisfy
this rule completely and still lose money, and a violation does not mean the
call was wrong — only that the stop could not survive the instrument's own
volatility long enough to find out.

## Examples

Compliant — a short with the stop above entry, 5.2 % away on an instrument
whose ATR(14) is about 4 %:

    action: Sell   entry_price: 607.57   stop_loss: 639.00

Violation of rule 1 — a Hold carrying a stop, observed in
`results/NVDA/2026-09-29`:

    action: Hold   entry_price: null     stop_loss: 217.00

Violation of rule 3 — a stop 2.57 % from entry on an instrument whose
ATR(14) over the period was wider, observed in `results/NVDA/2026-09-22`:

    action: Sell   entry_price: 228.87   stop_loss: 234.76

## Sources

- Pilot of 2026-09-19, `backtests/pilot/` — 19 arms carried a stop, 12 were
  stopped out inside five sessions; see `docs/gaps.md`, "The pilot".
- Live runs `results/NVDA/2026-09-04`, `results/NVDA/2026-09-22`,
  `results/AMD/2026-09-29`, `results/NVDA/2026-09-29` — observed stop
  distances 8.59 %, 2.57 %, 5.17 % and one Hold carrying a stop.
- `ta_cascade.data.hold_band` — the ATR-over-holding-period band the scorer
  already uses to judge a Hold.
