# Size and complexity: the reference implementation versus this one

**Measured**: 2026-09-08, TradingAgents v0.4.2 (`be952b8`) against this
repository at the merge of PR #3 (social ingestion included).
**Method**: `scripts/measure_size.py <TradingAgents checkout> .` — physical
lines, logical lines (non-blank, excluding comments and docstrings) and
doc/comment lines per layer; cyclomatic complexity per function via
`radon` (`pip install radon`); runtime dependencies from each
`pyproject.toml`. Re-run the script when either side changes; the tables
below are its output as of the date above.

The headline ratio is about **one fifth** of the reference's application
code. §3 explains why that number must not be read as a plain win: part is
work the framework absorbed, part is scope not yet built here, and part is
genuine simplification. Only the third part is a design result.

---

## 1. Application Python, excluding tests

| | TradingAgents v0.4.2 | ta_cascade |
|---|---|---|
| Files | 78 | 16 |
| Physical lines | 10,658 | 1,864 |
| Logical lines | 6,705 | 1,291 |
| Doc / comment lines | 2,476 | 344 |
| Functions and methods | 296 | 80 |
| Mean cyclomatic complexity | 3.9 | 4.6 |
| Maximum complexity | 41 | 18 |
| Functions over 10 | 24 | 8 |
| Functions over 15 | 12 | 2 |

### By layer

| Layer | Reference (logical lines) | Here (logical lines) | Where it went |
|---|---|---|---|
| Orchestration: graph / driver, state, checkpoint or journal, CLI | 825 (`graph/`) + 1,526 (`cli/`) | 501 (`pipeline`, `sessions`, `state`, `journal`, `config`, `cli`) | reducers, message-clearing nodes, path maps, the checkpointer library and the chunk-merging dashboard have no counterpart; the framework's event stream and TUI cover the live view |
| Agents: node factories, prompts, output schemas, structured-output glue | 1,605 (`agents/`) | 88 Python (two gates, one prefetch) + 268 lines of persona markdown + 64 lines of JSON schema | prompts moved from f-strings inside twelve factories into thirteen persona files; `with_structured_output`, its capability table and the free-text fallback became a completion schema plus a gate |
| Data layer | 1,951 (`dataflows/`) | 421 (`data.py`) + 135 (`tools.py`) | one vendor (yfinance) plus FRED, StockTwits and Reddit; see §3.2 for what the reference has that this does not |
| Provider layer | 641 (`llm_clients/`) | 0 | jaato's providers and profile sets |
| Memory, reporting, config | 157 + the decision log inside `agents/utils/` | 143 (`memory.py`, `report.py`) | comparable |
| Tests | 5,127 in 63 files | 336 in 10 files | see §3.2 |
| Runtime dependencies | 22 | 4 | see §4 |

### Material outside Python, this repository

| | Files | Lines |
|---|---|---|
| Personas (`.jaato/agents/*.md`) | 13 | 268 |
| Base instructions (`.jaato/instructions/`) | 1 | 11 |
| Completion schemas (`.jaato/completion_schemas/*.json`) | 5 | 64 |
| Profiles (13 base + 2 sets of 13) | 39 | 863 |

The reference keeps prompts and provider configuration inside Python, so
they are counted in its Python totals above; here they are data. The
profile YAML is mostly the scaffold's output (the provider-agnostic base
tier, the OpenRouter binding, and the canned echo payloads).

---

## 2. Complexity distribution

Mean complexity is slightly higher here (4.6 against 3.9) because there is
less trivial glue to average it down, and the distribution is tighter:

| | Reference | Here |
|---|---|---|
| Highest function | 41, the rich dashboard renderer (`cli/main.py`) | 18, `DecisionLog.past_context` and the analyst gate's `validate` |
| Functions over 15 | 12 (five of them in `dataflows/`) | 2 |
| Functions over 10 | 24 | 8 |

Both functions over 15 here are branchy formatting and would split easily
if the project adopts jaato's own ceiling of 15 (its cyclomatic-complexity
guard treats anything above that as a defect for new code).

---

## 3. How to read the ratio

### 3.1 Work that moved into the framework

This is the honest part of the reduction. The following exist in the
reference as application code and here as jaato:

- the provider layer (641 logical lines: seventeen OpenAI-compatible
  specs, native Anthropic/Google/Azure/Bedrock clients, a capabilities
  table, DeepSeek and MiniMax reasoning quirks, content normalisation);
- graph state and reducers, `RemoveMessage` clearing nodes, the SQLite
  checkpointer and the `invoke(None)` resume protocol;
- tool-loop mechanics (`ToolNode`) and structured-output binding;
- most of what the 1,526-line CLI does at run time: live progress from
  streamed state, permission handling, attaching to a running session.

Prompts moved medium rather than shrinking: twelve f-string factories
became thirteen markdown personas of comparable wording.

### 3.2 Scope not yet implemented

This is where the ratio flatters this repository. The reference's data
layer is 4.6 times ours largely because it has, and we do not: a second
vendor (Alpha Vantage) with a per-category vendor chain and per-tool
override; Polymarket prediction markets; an OHLCV file cache with
staleness guards and a retry wrapper; a market-data validator; point-in-
time filtering of fundamentals and news by publication date; global news
from configured search queries. Its CLI has an interactive selection flow,
saved config, typed env overrides and an output-language setting. Its 63
test files cover per-source look-ahead guards, symbol normalisation, vendor
routing and config precedence that we have not written tests for yet.

Each item is tracked, with a priority, in the "Feature parity with the
reference implementation" table of [gaps.md](gaps.md). A fair estimate for
this repository at parity is 2,500 to 3,000 logical lines of application
Python: still well under half of the reference, because §3.1 does not
change.

### 3.3 Genuine simplification

Two layers are smaller by design rather than by omission:

- **Orchestration.** 501 lines replace 825 lines of graph code plus the
  parts of the CLI that reconstruct state from streamed chunks. A driver
  that owns the state needs no reducers, no message-clearing nodes, no
  over-complete path maps and no checkpointer library; resume is a JSON
  file the driver writes after each unit of work.
- **Agents.** A completion schema plus a gate replaces the structured-
  output binding, the per-model capability table, the free-text fallback
  and the regex rating extractor. The gate can also check what the
  session actually did (the tool-call ledger), which the reference could
  only request in a prompt.

---

## 4. Dependencies

22 against 4. Of the reference's 22, two are declared but imported
nowhere (`backtrader`, `redis`); five are LangChain/LangGraph packages that
jaato replaces; the rest are the CLI stack (`rich`, `typer`,
`questionary`, `tqdm`) and the data stack (`pandas`, `yfinance`,
`stockstats`, `parsel`, `requests`, `pytz`). Ours hides one large dependency
behind `jaato-sdk`, so the count understates total surface, but that
surface is shared with every other jaato client rather than owned here.

---

## 5. Reproducing

```bash
git clone --depth 1 https://github.com/TauricResearch/TradingAgents /tmp/ta   # reference, read-only
pip install radon
python scripts/measure_size.py /tmp/ta .
```

The reference checkout is for measurement only. Nothing from it is copied
into this repository (see [gaps.md](gaps.md) #8).
