"""The configured pipeline: assembly, merge and the active set.

Daemon-free by construction — :func:`ta_cascade.plan.assemble` takes the
profiles as data, which is the reason the daemon call lives in
:mod:`ta_cascade.sessions` and not here.
"""
from pathlib import Path

import pytest

from ta_cascade import plan
from ta_cascade.runview import BANDS


def _profile(name, **over):
    p = {"name": name, "description": f"{name} stage", "plugins": [],
         "completion_payload_schema": f"completion_schemas/{name}.json",
         "completion_processors": [{"script": f"scripts/processors/{name}.py",
                                    "output": f"live/{name}.md"}],
         "budget_control": {"limits": {"usd": 1.5, "turns": 6}},
         "model": "echo", "provider": "echo"}
    p.update(over)
    return p


def _all_stages():
    return {s: _profile(s) for s in plan.stages()}


def test_stages_are_the_bands_in_order():
    assert plan.stages() == [s for _b, members in BANDS for s in members]
    assert len(plan.stages()) == 13


def test_assemble_reports_every_stage_with_its_capability_row():
    out = plan.assemble(_all_stages(), profile_set="echo")
    assert out["set"] == "echo"
    assert out["missing"] == []
    assert [s["stage"] for s in out["stages"]] == plan.stages()
    one = out["stages"][0]
    assert one["state"] == plan.PLANNED
    assert one["capability_source"] == "daemon"
    assert one["mode"] == "complete()"
    assert one["capabilities"]["gates"] == [f"{one['stage']}.py"]
    # The run-only fields are absent, not zero: nothing has run.
    assert one["session_id"] is None and one["seconds"] is None and one["tokens"] is None


def test_a_stage_the_daemon_does_not_list_is_reported_not_drawn_empty():
    profiles = _all_stages()
    del profiles["trader"]
    out = plan.assemble(profiles)
    assert out["missing"] == ["trader"]
    assert "trader" not in [s["stage"] for s in out["stages"]]


def test_mode_follows_the_schema():
    profiles = _all_stages()
    profiles["bull_researcher"] = _profile("bull_researcher", completion_payload_schema=None)
    out = plan.assemble(profiles)
    by = {s["stage"]: s for s in out["stages"]}
    assert by["bull_researcher"]["mode"] == "ask()"
    assert by["trader"]["mode"] == "complete()"


def test_analysts_carry_their_host_tools_and_others_do_not():
    out = plan.assemble(_all_stages())
    by = {s["stage"]: s for s in out["stages"]}
    assert by["market_analyst"]["host_tools"], "an analyst registers host tools"
    assert by["portfolio_manager"]["host_tools"] == []


def test_merge_paints_the_run_onto_the_plan():
    planned = plan.assemble(_all_stages())["stages"]
    observed = [{"stage": "market_analyst", "state": "done", "band": "analysts"}]
    merged = plan.merge(planned, observed)
    by = {s["stage"]: s for s in merged}
    assert by["market_analyst"]["state"] == "done"          # the run wins
    assert by["trader"]["state"] == plan.PLANNED            # unreached stays planned
    assert [s["stage"] for s in merged] == plan.stages()    # plan order preserved


def test_merge_appends_a_stage_the_plan_never_declared():
    planned = plan.assemble(_all_stages())["stages"]
    observed = [{"stage": "mystery", "state": "done", "band": "mystery"}]
    merged = plan.merge(planned, observed)
    assert merged[-1]["stage"] == "mystery", "an unplanned stage is the most worth seeing"
    assert len(merged) == len(planned) + 1


@pytest.mark.parametrize("text,want", [
    ("JAATO_PROFILE_SET=echo\n", "echo"),
    ("# a comment\nJAATO_PROFILE_SET=minimax_m3\nFRED_API_KEY=x\n", "minimax_m3"),
    ("FRED_API_KEY=x\n", None),
    ("JAATO_PROFILE_SET=\n", None),
])
def test_profile_set_is_read_from_the_session_env(tmp_path, text, want):
    env = tmp_path / ".env"
    env.write_text(text, encoding="utf-8")
    assert plan.profile_set_of(env) == want


def test_an_unreadable_env_is_not_a_set(tmp_path):
    assert plan.profile_set_of(tmp_path / "nothing-here") is None
