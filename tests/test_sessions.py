"""The budget check `open_stage` runs before a stage's model can call a tool.

`check_tool_budgets` is a pure function of two dicts precisely so it can be
tested without a daemon: what the handlers were sized for, and what the daemon
answered to this session's registration.
"""
import pytest

from ta_cascade.sessions import ToolBudgetMismatch, check_tool_budgets


def test_agreement_passes():
    check_tool_budgets({"get_company_news": 25.0}, {"get_company_news": 25.0})


def test_a_stage_with_no_host_tools_is_not_a_mismatch():
    """Every stage but the four analysts passes no tools at all."""
    check_tool_budgets({}, {})
    check_tool_budgets({}, {"something_else": 30.0})


def test_a_daemon_that_reports_nothing_is_a_mismatch():
    """Protocol < 1.39 answers no budgets, so nothing confirms the deadlines."""
    with pytest.raises(ToolBudgetMismatch, match="protocol 1.39"):
        check_tool_budgets({"get_company_news": 25.0}, {})


def test_a_different_budget_names_both_numbers():
    """The message must carry ours AND theirs: the gap is the whole finding."""
    with pytest.raises(ToolBudgetMismatch) as exc:
        check_tool_budgets({"get_company_news": 45.0}, {"get_company_news": 30.0})
    assert "45.0" in str(exc.value) and "30.0" in str(exc.value)


def test_a_tool_the_daemon_never_heard_of_is_a_mismatch():
    with pytest.raises(ToolBudgetMismatch, match="get_company_news"):
        check_tool_budgets({"get_company_news": 25.0}, {"get_macro_series": 25.0})
