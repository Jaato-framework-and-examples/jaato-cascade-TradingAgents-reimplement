"""The revision a board reports: parsing, absence, and drift.

Git is monkeypatched throughout rather than exercised, so these assert the
REPORTING rules — which are the part that can lie — and not git's behaviour.
One test does touch a real directory, to prove a non-checkout says so.
"""
from pathlib import Path

from ta_cascade import version


def test_a_directory_that_is_not_a_checkout_says_so(tmp_path):
    out = version._revision(root=tmp_path)
    assert out["pin"] is None and out["commit"] is None
    assert out["dirty"] is None, "unknown is not clean"
    assert str(tmp_path) in out["reason"]


def test_dirty_is_read_from_git_s_own_description(monkeypatch):
    monkeypatch.setattr(version, "_git", lambda *a, **k: "v0.2.1-2-g45a22e4-dirty")
    assert version._revision()["dirty"] is True


def test_a_clean_description_is_not_dirty(monkeypatch):
    monkeypatch.setattr(version, "_git", lambda *a, **k: "v0.2.1")
    out = version._revision()
    assert out["dirty"] is False and out["pin"] == "v0.2.1"


def test_drift_is_the_loaded_commit_against_the_tree_now(monkeypatch):
    monkeypatch.setattr(version, "LOADED",
                        {"pin": "v0.2.0", "commit": "49d8c25", "branch": "main",
                         "dirty": False, "reason": None})
    monkeypatch.setattr(version, "_revision",
                        lambda root=None: {"pin": "v0.2.1", "commit": "345a5d4",
                                           "branch": "main", "dirty": False, "reason": None})
    out = version.report()
    assert out["drifted"] is True, "a pull under a running server must show"
    assert out["loaded"]["commit"] == "49d8c25"
    assert out["checkout"]["commit"] == "345a5d4"


def test_no_drift_when_the_two_agree(monkeypatch):
    same = {"pin": "v0.2.1", "commit": "345a5d4", "branch": "main",
            "dirty": False, "reason": None}
    monkeypatch.setattr(version, "LOADED", same)
    monkeypatch.setattr(version, "_revision", lambda root=None: dict(same))
    assert version.report()["drifted"] is False


def test_drift_is_unknown_when_either_side_is(monkeypatch):
    """A comparison with an unknown is unknown.

    Answering ``False`` here would assert "this deployment matches its pin"
    on no evidence, which is the one claim this module exists not to make.
    """
    monkeypatch.setattr(version, "LOADED",
                        {"pin": None, "commit": None, "branch": None,
                         "dirty": None, "reason": "no git"})
    monkeypatch.setattr(version, "_revision",
                        lambda root=None: {"pin": "v0.2.1", "commit": "345a5d4",
                                           "branch": "main", "dirty": False, "reason": None})
    assert version.report()["drifted"] is None


def test_an_absent_sdk_is_reported_not_hidden(monkeypatch):
    """A board-only deployment has no SDK, which is supported, so it is a fact."""
    import importlib.metadata as md

    def _raise(_name):
        raise md.PackageNotFoundError("jaato-sdk")

    monkeypatch.setattr(md, "version", _raise)
    out = version.sdk_version()
    assert out["version"] is None and "jaato-sdk" in out["reason"]


def test_report_carries_every_field_a_tile_reads(monkeypatch):
    out = version.report()
    assert set(out) == {"loaded", "checkout", "drifted", "sdk"}
    for side in ("loaded", "checkout"):
        assert set(out[side]) == {"pin", "commit", "branch", "dirty", "reason"}
