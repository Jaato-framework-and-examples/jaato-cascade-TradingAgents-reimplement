"""What the board will answer for, once it is bound to more than loopback.

The guards are MEMBERSHIP checks, not patterns: a request may name only a run
the driver itself wrote and a session that run recorded opening.  That makes
path traversal structurally impossible rather than filtered, and it cannot
fall behind the symbols the data layer accepts the way a "what a ticker looks
like" regex would.

Tested as plain functions rather than through starlette's ``TestClient``,
which needs ``httpx``: a dependency added for one test is a dependency added
for ever, which is the same argument this package makes for not reaching for
FastAPI.
"""
from __future__ import annotations

import json

import pytest

from ta_cascade import runview

api = pytest.importorskip("ta_cascade.ui.api",
                          reason="the board extra (starlette) is not installed")


@pytest.fixture
def tree(tmp_path):
    """One recorded run: NVDA 2026-01-15, two sessions started."""
    base = tmp_path / "results" / "NVDA" / "2026-01-15"
    base.mkdir(parents=True)
    lines = [
        {"event": "started", "session_id": "20260115_100000", "stage": "market_analyst"},
        {"event": "ended", "session_id": "20260115_100000", "stage": "market_analyst"},
        {"event": "started", "session_id": "20260115_100100", "stage": "trader"},
    ]
    (base / "sessions.jsonl").write_text("".join(json.dumps(x) + "\n" for x in lines))
    return tmp_path / "results"


def test_the_session_allow_list_is_what_the_run_recorded(tree):
    assert runview.session_ids(tree, "NVDA", "2026-01-15") == [
        "20260115_100000", "20260115_100100"]
    # Started once, ended once: the id is listed once.
    assert len(runview.session_ids(tree, "NVDA", "2026-01-15")) == 2
    assert runview.session_ids(tree, "NVDA", "2999-01-01") == []


def test_a_recorded_run_is_known_and_anything_else_is_not(tree):
    assert api.known_run(tree, "NVDA", "2026-01-15") is True
    assert api.known_run(tree, "AMD", "2026-01-15") is False
    assert api.known_run(tree, "NVDA", "2026-01-16") is False


@pytest.mark.parametrize("ticker,date", [
    ("..", ".."),
    ("..", "2026-01-15"),
    ("NVDA", ".."),
    (".", "."),
    ("", ""),
    ("NVDA/../..", "2026-01-15"),
    ("%2e%2e", "%2e%2e"),
    ("/etc", "passwd"),
])
def test_a_crafted_name_is_simply_not_a_member(tree, ticker, date):
    """Not sanitised — not present.

    ``GET /api/run/%2e%2e/%2e%2e`` used to match the route and raise
    ``ValueError: Invalid isoformat string: '..'`` out of the host-tool specs,
    a 500 whose traceback names filesystem paths.  Now none of these is a run
    the driver wrote, so none of them reaches the filesystem.
    """
    assert api.known_run(tree, ticker, date) is False


def test_a_session_must_belong_to_the_run_that_is_asked_for(tree):
    assert api.known_session(tree, "NVDA", "2026-01-15", "20260115_100000") is True
    assert api.known_session(tree, "NVDA", "2026-01-15", "20260115_999999") is False
    # A plausible id from some other run is still not this run's.
    assert api.known_session(tree, "NVDA", "2026-01-15", "20261017_231507") is False


@pytest.mark.parametrize("sid", ["..", "../../jaato.config", "%2e%2e", "", "."])
def test_a_crafted_session_id_is_not_a_member_either(tree, sid):
    assert api.known_session(tree, "NVDA", "2026-01-15", sid) is False


def test_the_app_builds_only_the_routes_its_paths_support(tmp_path):
    """A route that answers "no paths were given" is a route that looks broken."""
    run_only = api.create_app(results_dir=tmp_path / "results", workspace=tmp_path)
    paths = {r.path for r in run_only.routes}
    assert "/api/run/{ticker}/{date}" in paths and "/api/sweep" not in paths
    assert "/" in paths                      # the run view is the index when alone

    sweep_only = api.create_app(tasks_dir=tmp_path / "tasks",
                                results_path=tmp_path / "results.jsonl", name="pilot")
    paths = {r.path for r in sweep_only.routes}
    assert "/api/sweep" in paths and "/api/runs" not in paths

    both = api.create_app(tasks_dir=tmp_path / "tasks",
                          results_path=tmp_path / "results.jsonl", name="pilot",
                          results_dir=tmp_path / "results", workspace=tmp_path)
    paths = {r.path for r in both.routes}
    assert {"/", "/run", "/api/sweep", "/api/runs"} <= paths
