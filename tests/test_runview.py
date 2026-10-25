"""One run as drawable state, from files alone — no daemon, no network.

The fixtures here are written to a temp tree in the shapes the real files have:
a session log line per :mod:`ta_cascade.sessionlog`, a session record per what
the daemon saves, an events file per :mod:`ta_cascade.eventlog`.  The shapes
were taken from a real run (NVDA 2026-10-17) rather than imagined, which is
why the budget numbers below look the way they do.
"""
from __future__ import annotations

import json
from pathlib import Path

from ta_cascade import runview

REPO = Path(__file__).resolve().parents[1]


# --------------------------------------------------------------- the band table

def test_every_persona_sits_in_exactly_one_band():
    """A stage added to the pipeline and not to BANDS fails here.

    :data:`ta_cascade.runview.BANDS` mirrors
    :func:`ta_cascade.pipeline.plan_of`, and the two cannot be derived from one
    another: the plan speaks in step keys (``analyst:market``) and a session
    log speaks in profile names (``market_analyst``).  So the duplication is
    guarded rather than trusted.
    """
    personas = {p.stem for p in (REPO / ".jaato" / "agents").glob("*.md")}
    banded = [stage for _, stages in runview.BANDS for stage in stages]

    assert len(banded) == len(set(banded)), "a stage appears in two bands"
    assert set(banded) == personas, (
        f"missing from BANDS: {sorted(personas - set(banded))}; "
        f"not a persona: {sorted(set(banded) - personas)}")


# ---------------------------------------------------------------- capabilities

def test_capabilities_reads_a_profile_the_way_both_sources_spell_it():
    """One reader serves the session record and the workspace YAML.

    ``profile_snapshot`` in a session record uses the profile schema's own key
    names, which is why the record can answer for a finished stage and the
    ``_base_<agent>.yaml`` for one still in flight.
    """
    caps = runview.capabilities({
        "description": "trader stage: the plan becomes a proposal.",
        "plugins": ["references(preload, tools:[listReferences, selectReferences])"],
        "completion_payload_schema": "completion_schemas/trader_proposal.json",
        "completion_processors": [
            {"script": "scripts/processors/rules_read.py", "name": "rules_read"},
            {"script": "scripts/processors/price_fields.py",
             "output": "results/{ticker}/{trade_date}/live/3_trading/proposal.md"},
        ],
        "budget_control": {"limits": {"tool_calls": 30, "turns": 6}},
    })
    assert caps["schema"] == "completion_schemas/trader_proposal.json"
    assert caps["gates"] == ["rules_read.py", "price_fields.py"]
    assert caps["sections"] == ["results/{ticker}/{trade_date}/live/3_trading/proposal.md"]
    assert caps["references"] is True
    assert caps["limits"]["turns"] == 6


def test_a_stage_with_no_schema_and_no_plugins_has_no_capabilities_to_offer():
    caps = runview.capabilities({"description": "risk panellist", "plugins": []})
    assert caps["schema"] is None and caps["gates"] == [] and caps["references"] is False


def test_references_is_the_plugin_name_not_a_substring():
    """A comment or another plugin that merely contains the word must not count."""
    assert runview.capabilities({"plugins": ["subagent", "file_edit"]})["references"] is False
    assert runview.capabilities({"plugins": ["references"]})["references"] is True


def test_the_workspace_profiles_answer_for_a_stage_with_no_record():
    """Read from the real tree: the base profile is where stage determinism lives."""
    profile = runview.declared(REPO / ".jaato", "trader")
    assert profile, "no _base_trader.yaml found"
    caps = runview.capabilities(profile)
    assert caps["schema"] and caps["gates"] and caps["references"] is True

    # A stage that does not exist is reported as unknown, not as empty.
    assert runview.declared(REPO / ".jaato", "no_such_stage") == {}


# -------------------------------------------------------------------- the budget

def test_the_binding_dimension_is_the_one_that_produced_the_fraction():
    binding = runview._binding({
        "used": {"tool_calls": 9.0, "seconds": 28.5, "turns": 1.0, "usd": 0.0},
        "limits": {"tool_calls": 30, "seconds": 480, "turns": 6, "usd": 1.5},
        "fraction_used": 0.3, "next_rung": {"at_percent": 100.0, "action": "abort"},
    })
    assert binding["binds"] == "tool_calls"          # 9/30 beats 1/6 and 28.5/480
    assert binding["fraction_used"] == 0.3
    assert {d["name"] for d in binding["dimensions"]} == {"tool_calls", "seconds", "turns", "usd"}


def test_an_unpriced_dimension_has_no_ratio_rather_than_a_zero():
    """A subscription provider reports effort and no cost; 0% would be a claim."""
    binding = runview._binding({"used": {"usd": None}, "limits": {"usd": 1.5}})
    usd = next(d for d in binding["dimensions"] if d["name"] == "usd")
    assert usd["ratio"] is None
    assert binding["binds"] is None


def test_the_two_turn_counts_are_both_reported_when_they_disagree():
    """Measured 2026-10-25: the ceiling counted 1 turn where the record counted 7.

    To ``budget_control`` a turn is one provider binding, so the dimension
    cannot bound a model's tool loop.  A reader told only "turns 1/6" would
    tune a ceiling that does nothing, so both numbers travel together.
    """
    binding = runview._binding({"used": {"turns": 1.0}, "limits": {"turns": 6}}, 7)
    assert binding["turns_counted"] == 1.0
    assert binding["turns_recorded"] == 7
    assert binding["turns_disagree"] is True

    agreeing = runview._binding({"used": {"turns": 1.0}, "limits": {"turns": 4}}, 1)
    assert agreeing["turns_disagree"] is False

    # Nothing to compare against is not a disagreement.
    assert runview._binding({"used": {"turns": 1.0}, "limits": {"turns": 4}})["turns_disagree"] is False


# ----------------------------------------------------------------- tool calls

def test_calls_are_counted_by_name_and_only_host_tools_are_claimed_as_ours():
    rows = [
        {"kind": "tool_start", "session_id": "s1", "tool": "list_tools"},
        {"kind": "tool_start", "session_id": "s1", "tool": "list_tools"},
        {"kind": "tool_start", "session_id": "s1", "tool": "get_price_history"},
        {"kind": "tool_start", "session_id": "other", "tool": "get_reddit_posts"},
        {"kind": "tool_end", "session_id": "s1", "tool": "list_tools",
         "success": True, "error_result": True},
    ]
    calls = runview._calls(rows, "s1", ("get_price_history",))
    assert calls["total"] == 3                      # the other session's call is not ours
    assert calls["failed"] == 1                     # an error RESULT counts as failed
    by = {t["tool"]: t for t in calls["by_tool"]}
    assert by["list_tools"]["n"] == 2 and by["list_tools"]["host"] is False
    assert by["get_price_history"]["host"] is True


# --------------------------------------------------------------------- money

def test_money_keeps_the_three_states_and_withholds_a_part_priced_total():
    priced = [{"consumption": {"totals": {"cost_usd": 0.5}}},
              {"consumption": {"totals": {"cost_usd": 0.25}}}]
    assert runview._money(priced)["cost_usd"] == 0.75

    # One measured-but-unpriced session withholds the total: a part-priced sum
    # reads as a bill and is not one.
    mixed = priced + [{"consumption": {"totals": {}}}]
    assert runview._money(mixed)["cost_usd"] is None
    assert runview._money(mixed)["priced"] == 2 and runview._money(mixed)["measured"] == 3

    # Unmeasured is neither: nothing is known, not even effort.
    unmeasured = [{"consumption_error": "TimeoutError: no answer"}]
    state = runview._money(unmeasured)
    assert state["measured"] == 0 and state["cost_usd"] is None


# ------------------------------------------------------------------ the survey

def _write_run(root: Path, workspace: Path) -> None:
    """A two-stage run in the shapes the real files have."""
    base = root / "NVDA" / "2026-01-15"
    base.mkdir(parents=True)
    lines = [
        {"at": "2026-01-15T10:00:00+00:00", "event": "started", "session_id": "s1",
         "ticker": "NVDA", "trade_date": "2026-01-15", "stage": "market_analyst",
         "agent": "market_analyst", "cascade_id": "cid"},
        {"at": "2026-01-15T10:00:40+00:00", "event": "ended", "session_id": "s1",
         "ticker": "NVDA", "trade_date": "2026-01-15", "stage": "market_analyst",
         "agent": "market_analyst", "reason": "natural", "failed": None,
         "consumption": {"elapsed_seconds": 38.6, "tool_calls": 5,
                         "totals": {"turns": 1, "total_tokens": 39902},
                         "budget": {"used": {"tool_calls": 5.0, "turns": 1.0},
                                    "limits": {"tool_calls": 60, "turns": 8},
                                    "fraction_used": 0.125},
                         "completion": {"signal_completion_called": True,
                                        "nudges_fired_total": 0}}},
        # A stage still open: started, never ended.
        {"at": "2026-01-15T10:01:00+00:00", "event": "started", "session_id": "s2",
         "ticker": "NVDA", "trade_date": "2026-01-15", "stage": "trader",
         "agent": "trader", "cascade_id": "cid"},
    ]
    (base / "sessions.jsonl").write_text("".join(json.dumps(x) + "\n" for x in lines))
    (base / "state.json").write_text(json.dumps({
        "reports": {"market": {}}, "investment_debate": [{}, {}], "risk_debate": [{}, {}, {}],
        "research_plan": {"recommendation": "Underweight"},
        "trader_proposal": {"action": "Sell"},
        "portfolio_decision": {"rating": "Hold"}}))
    (base / "events.jsonl").write_text("".join(json.dumps(x) + "\n" for x in [
        {"at": "t", "kind": "observer_attached", "socket": "/tmp/jaato.sock"},
        {"at": "t", "kind": "tool_start", "session_id": "s1", "call_id": "c1",
         "tool": "get_price_history", "args": {"symbol": "NVDA"}},
        {"at": "t", "kind": "tool_end", "session_id": "s1", "call_id": "c1",
         "tool": "get_price_history", "success": True, "error_result": False, "seconds": 2.0},
        {"at": "t", "kind": "tool_start", "session_id": "s2", "call_id": "c9",
         "tool": "listReferences", "args": {}},
    ]))

    records = workspace / ".jaato" / "sessions"
    records.mkdir(parents=True)
    (records / "s1.json").write_text(json.dumps({
        "session_id": "s1", "turn_count": 2, "end_reason": "natural",
        "agent_params": {"ticker": "NVDA"},
        "rendered_instructions": "# Base System Instructions\nYou are the market analyst.",
        "profile_snapshot": {
            "description": "market analyst stage: data tools in, a typed report out.",
            "plugins": [],
            "completion_payload_schema": "completion_schemas/analyst_report.json",
            "completion_processors": [{"script": "scripts/processors/analyst_report.py",
                                       "output": "results/{ticker}/{trade_date}/live/market.md"}],
            "budget_control": {"limits": {"tool_calls": 60, "turns": 8}}},
        "history": [
            {"role": "user", "parts": [{"type": "text", "text": "Produce your report."}]},
            {"role": "model", "parts": [
                {"type": "thought", "thought": "I should call the price tool."},
                {"type": "function_call", "id": "c1", "name": "get_price_history",
                 "args": {"symbol": "NVDA"}},
                {"type": "function_call", "id": "c2", "name": "signal_completion",
                 "args": {"stance": "bullish"}}]},
            {"role": "tool", "parts": [
                {"type": "function_response", "call_id": "c1", "name": "get_price_history",
                 "result": "ok", "is_error": False, "untrusted": True},
                {"type": "function_response", "call_id": "c2", "name": "signal_completion",
                 "result": {"error": "report too short",
                            "processor_errors": ["write at least 400 characters"]},
                 "is_error": True}]},
        ]}))


def test_the_survey_reads_a_run_from_disk_alone(tmp_path):
    results, workspace = tmp_path / "results", tmp_path / "ws"
    _write_run(results, workspace)

    d = runview.survey(results, "NVDA", "2026-01-15",
                       workspace=workspace, config_root=REPO / ".jaato")

    assert d["verdict"] == {"rating": "Hold", "plan": "Underweight", "trade": "Sell",
                            "analysts": ["market"], "investment_turns": 2, "risk_turns": 3}
    assert d["counts"] == {"planned": 2, "done": 1, "running": 1, "failed": 0}
    assert d["observer"] == "attached"
    assert d["effort"]["tool_calls"] == 5

    stages = {s["stage"]: s for s in d["stages"]}

    # The finished stage answers from the daemon's own record.
    market = stages["market_analyst"]
    assert market["state"] == "done" and market["capability_source"] == "record"
    assert market["mode"] == "complete()"
    assert market["capabilities"]["gates"] == ["analyst_report.py"]
    assert market["budget"]["binds"] == "turns"
    assert market["turns_recorded"] == 2 and market["budget"]["turns_disagree"] is True
    assert market["calls"]["by_tool"][0]["tool"] == "get_price_history"
    assert market["calls"]["by_tool"][0]["host"] is True

    # The open stage has no record yet, so the workspace profile answers and
    # the card is complete from the moment the stage starts.
    trader = stages["trader"]
    assert trader["state"] == "running" and trader["capability_source"] == "profile"
    assert trader["capabilities"]["references"] is True
    assert trader["has_record"] is False
    assert trader["seconds"] is None                  # nothing measured it yet

    # Bands come out in pipeline order and empty ones are dropped.
    assert [b["name"] for b in d["bands"]] == ["analysts", "judges"]


def test_an_unplanned_stage_is_appended_rather_than_dropped(tmp_path):
    """The choice BoardState makes, for the same reason: it is worth seeing."""
    results, workspace = tmp_path / "results", tmp_path / "ws"
    _write_run(results, workspace)
    base = results / "NVDA" / "2026-01-15"
    with (base / "sessions.jsonl").open("a") as fh:
        fh.write(json.dumps({"at": "z", "event": "started", "session_id": "s3",
                             "stage": "a_stage_nobody_planned", "agent": "x"}) + "\n")

    d = runview.survey(results, "NVDA", "2026-01-15", workspace=workspace)
    assert "a_stage_nobody_planned" in [b["name"] for b in d["bands"]]
    assert [s["stage"] for s in d["stages"]][-1] == "a_stage_nobody_planned"


def test_the_drawer_prefers_the_record_and_says_so(tmp_path):
    results, workspace = tmp_path / "results", tmp_path / "ws"
    _write_run(results, workspace)

    s = runview.session(workspace, "s1", [])
    assert s["source"] == "record" and s["end_reason"] == "natural" and s["turns"] == 2
    assert s["agent_params"] == {"ticker": "NVDA"}
    assert s["persona"].startswith("# Base System Instructions")

    kinds = [p["kind"] for p in s["parts"]]
    assert kinds == ["prompt", "thought", "tool", "tool"]

    price, signal = s["parts"][2], s["parts"][3]
    assert price["ok"] is True and price["untrusted"] is True
    # A gate's refusal: the call completed, the RESULT was the error, and the
    # gate's own message is what the drawer shows.
    assert signal["ok"] is False and signal["error"] == "report too short"
    assert signal["detail"] == ["write at least 400 characters"]


def test_without_a_record_the_drawer_falls_back_to_the_events_skeleton(tmp_path):
    """Tool calls only — the model's words are deliberately not recorded."""
    results, workspace = tmp_path / "results", tmp_path / "ws"
    _write_run(results, workspace)
    events = runview.eventlog.read(runview.eventlog.path_for(results, "NVDA", "2026-01-15"))

    s = runview.session(workspace, "s2", events)
    assert s["source"] == "events"
    assert [p["tool"] for p in s["parts"]] == ["listReferences"]
    assert s["parts"][0]["ok"] is None               # started, no end seen yet
    assert s["persona"] == "" and s["profile"] == {}


def test_a_session_with_neither_record_nor_events_says_so(tmp_path):
    """An empty conversation and an unsaved one are different facts."""
    results, workspace = tmp_path / "results", tmp_path / "ws"
    _write_run(results, workspace)
    s = runview.session(workspace, "never_opened", [])
    assert s["source"] == "none" and s["parts"] == []


def test_runs_lists_what_wrote_a_session_log_newest_date_first(tmp_path):
    results = tmp_path / "results"
    for ticker, date in (("NVDA", "2026-01-15"), ("NVDA", "2026-02-15"), ("AMD", "2026-01-15")):
        d = results / ticker / date
        d.mkdir(parents=True)
        (d / "sessions.jsonl").write_text("")
    (results / "NVDA" / "2026-03-15").mkdir()        # no session log: not a run

    assert runview.runs(results) == [
        {"ticker": "AMD", "trade_date": "2026-01-15"},
        {"ticker": "NVDA", "trade_date": "2026-02-15"},
        {"ticker": "NVDA", "trade_date": "2026-01-15"},
    ]
    assert runview.runs(tmp_path / "nothing") == []
