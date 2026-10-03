# What a debater may attribute to a report

## Rule

1. **State as fact only what a report states.** Counts, dates, price levels
   and tallies are the report's words, not yours. If the market report does
   not say how many times a level was tested, there is no number to cite.
2. **Do not recharacterise.** Where a report names something, that name
   stands. "Indecision" is not "distribution"; "mixed" is not "weakening".
   Changing the word changes the claim while appearing to quote it.
3. **Inference is welcome, and must be marked as yours.** Arguing past the
   evidence is the point of a debate. Say "this reads to me as…" rather than
   attributing the conclusion to a report that did not draw it.
4. **Name the report you are drawing on** when you attribute. A claim
   sourced to "the analysis" cannot be checked against anything.

## Rationale

The debate exists to stress a thesis, and a fabricated premise destroys that:
the opposing side must then argue against something no evidence supports, and
the judge has to spend its turn refereeing the record instead of weighing the
argument. Worse, a fabricated detail is more persuasive than a real one,
because it is shaped to fit the case being made.

The failure is observed, not hypothetical. On 2026-10-03 the research manager
refused a NVDA debate outright with two findings:

    "Bear fabricated claim of 'three rejections' at $234.76 resistance —
     market report does not specify the number of rejection attempts"
    "Bear characterized consolidation as 'distribution' when market report
     explicitly states 'indecision — neither aggressive accumulation nor
     distribution'"

Both are this rule: a count that was never given, and a word swapped for its
opposite.

## Scope and limits

The rule governs attribution, not position. A debater may be as bearish or
bullish as the evidence allows, may weight evidence differently from the
other side, and may call a report wrong — saying "the market report calls
this indecision; I think it is distribution, and here is why" satisfies the
rule completely while disagreeing entirely.

It is also unenforced at this stage. The debaters run as plain turns with no
completion payload, so no gate inspects their output; the research manager
catches violations downstream, as it did above. The rule is written here
because that is where the fabrication originates.

## Examples

Violation of rule 1 — a count the source never gave:

    "price has been rejected three times at $234.76"

Compliant — the same argument without the invented number:

    "the market report puts the 120-day high at $234.76 and price below it;
     I read repeated failure to close above it as supply"

Violation of rule 2 — the report's word replaced by its opposite:

    report: "indecision — neither aggressive accumulation nor distribution"
    debater: "the consolidation is distribution"

## Sources

- Research-manager refusal, NVDA 2026-09-29 run of 2026-10-03; see
  `docs/gaps.md`, "A reference is made available, not delivered".
- `.jaato/completion_schemas/research_plan.json` — the judge's `errors[]`,
  the mechanism that caught it.
