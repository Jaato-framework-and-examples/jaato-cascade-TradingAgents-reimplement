from pathlib import Path

import pytest

from ta_cascade import contract

FULL = {
    "JAATO_EVAL_CONTRACT": "1",
    "JAATO_EVAL_WORKSPACE": "/tmp/ws",
    "JAATO_EVAL_CONFIG_ROOT": "/repo/.jaato",
    "JAATO_EVAL_CASCADE_ID": "jaato-eval-x-1234",
}


def test_no_contract_outside_jaato_eval():
    assert contract.from_environment({}) is None
    assert contract.from_environment({"JAATO_EVAL_PARAM_TICKER": "NVDA"}) is None


def test_contract_is_read_once_and_typed():
    c = contract.from_environment({**FULL, "JAATO_EVAL_SOCKET": "/tmp/d.sock"})
    assert c.version == "1"
    assert c.workspace == Path("/tmp/ws") and c.config_root == Path("/repo/.jaato")
    assert c.cascade_id == "jaato-eval-x-1234" and c.socket == "/tmp/d.sock"


def test_absent_socket_means_the_sdk_default():
    assert contract.from_environment(FULL).socket is None
    assert contract.from_environment({**FULL, "JAATO_EVAL_SOCKET": ""}).socket is None


def test_unknown_version_is_refused_not_guessed():
    with pytest.raises(contract.UnknownContract, match="JAATO_EVAL_CONTRACT='2'"):
        contract.from_environment({**FULL, "JAATO_EVAL_CONTRACT": "2"})


def test_missing_variable_is_refused_by_name():
    env = {k: v for k, v in FULL.items() if k != "JAATO_EVAL_CASCADE_ID"}
    with pytest.raises(contract.UnknownContract, match="JAATO_EVAL_CASCADE_ID"):
        contract.from_environment(env)


def test_params_are_the_exported_inputs():
    env = {**FULL, "JAATO_EVAL_PARAM_TICKER": "NVDA", "JAATO_EVAL_PARAM_TRADE_DATE": "2026-08-28",
           "JAATO_EVAL_PARAMS": '{"TICKER": "NVDA"}', "PATH": "/usr/bin"}
    assert contract.params(env) == {"TICKER": "NVDA", "TRADE_DATE": "2026-08-28"}
