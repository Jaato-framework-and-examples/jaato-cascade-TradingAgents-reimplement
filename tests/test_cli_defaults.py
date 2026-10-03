"""What a run gets when the operator says nothing.

`RunConfig`'s dataclass default is dead code for anything started from the
CLI, because the parser always supplies a value. On 2026-10-03 sentiment was
removed from `DEFAULT_ANALYSTS` and three live runs still died in the
sentiment stage, because `cli.py` defaulted `--analysts` to every key. These
tests pin the two together so the config default cannot be bypassed again.
"""
from ta_cascade.cli import build_parser
from ta_cascade.config import ANALYST_KEYS, DEFAULT_ANALYSTS


def _analysts(argv):
    args = build_parser().parse_args(argv)
    return [s.strip() for s in args.analysts.split(",") if s.strip()]


def test_the_cli_default_is_the_config_default():
    assert _analysts(["analyze", "NVDA", "2026-09-29"]) == DEFAULT_ANALYSTS


def test_sentiment_is_off_by_default_but_still_reachable_by_name():
    """Its four sources are down; it is excluded, not deleted."""
    assert "sentiment" not in _analysts(["analyze", "NVDA", "2026-09-29"])
    assert "sentiment" in ANALYST_KEYS
    assert _analysts(["analyze", "NVDA", "2026-09-29", "--analysts", "market,sentiment"]) == ["market", "sentiment"]


def test_the_default_is_a_subset_of_the_known_keys():
    assert set(DEFAULT_ANALYSTS) <= set(ANALYST_KEYS)
