"""Every OpenRouter stage identifies itself, and none of them re-declares the key.

`http_referer` and `app_title` become the HTTP-Referer / X-OpenRouter-Title
headers OpenRouter attributes traffic by, so a stage that ships without a
title is invisible in exactly the place attribution was added for.  The
failure is silent — the run works perfectly — which is why it is asserted
here rather than left to review.

Reads the YAML directly: this guards OUR data, not the framework's merge.
"""
import pathlib

import pytest

yaml = pytest.importorskip("yaml")

SET = pathlib.Path(__file__).resolve().parent.parent / ".jaato" / "profiles" / "openrouter_sonnet"
SHARED = "_openrouter_app"


def _stage_profiles():
    return sorted(p for p in SET.glob("*.yaml") if not p.name.startswith("_"))


def test_the_set_has_the_stages_the_pipeline_names():
    from ta_cascade.pipeline import ANALYST_STAGES, RISK_ROTATION
    expected = ({p for p, _ in ANALYST_STAGES.values()}
                | {p for _, p in RISK_ROTATION}
                | {"bull_researcher", "bear_researcher", "research_manager",
                   "trader", "portfolio_manager", "reflector"})
    assert {p.stem for p in _stage_profiles()} == expected


@pytest.mark.parametrize("path", _stage_profiles(), ids=lambda p: p.stem)
def test_stage_is_attributed_and_takes_the_shared_identity(path):
    spec = yaml.safe_load(path.read_text())
    agent = path.stem

    assert SHARED in spec["inherits"], f"{agent} does not inherit the shared identity"
    openrouter = spec["plugin_configs"]["openrouter"]

    assert openrouter["app_title"] == f"Trading - {agent} (powered by Jaato)"

    # The credential comes from the shared parent.  A stage that re-declares
    # it is a second place to rotate a key, and the reason it would be missed
    # is that nothing fails when it drifts.
    assert "api_key" not in openrouter, f"{agent} re-declares api_key"
    assert "http_referer" not in openrouter, f"{agent} re-declares http_referer"


@pytest.mark.parametrize("path", _stage_profiles(), ids=lambda p: p.stem)
def test_stage_keeps_its_own_api_params(path):
    """`plugin_configs` merges ONE level: a nested dict is replaced, not merged.

    Measured against the framework's own `discover_profiles` — a parent
    `api_params` would be dropped wholesale by the two stages that set their
    own, silently taking `temperature: 0.0` with it.  So every stage carries
    its own, and this asserts none of them lost it.
    """
    spec = yaml.safe_load(path.read_text())
    api_params = spec["plugin_configs"]["openrouter"]["api_params"]
    assert api_params["temperature"] == 0.0


def test_the_shared_identity_carries_no_api_params():
    """The corollary of the one-level merge: putting api_params in the parent
    would look like it worked for eleven stages and silently fail for two."""
    spec = yaml.safe_load((SET / f"{SHARED}.yaml").read_text())
    openrouter = spec["plugin_configs"]["openrouter"]
    assert "api_params" not in openrouter
    assert openrouter["api_key"].startswith("${")        # expanded daemon-side
    assert openrouter["http_referer"].startswith("https://")
