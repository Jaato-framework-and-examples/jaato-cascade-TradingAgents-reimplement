"""The pipeline: the graph, written as the driver.

Order, mirroring the paper's team structure::

    analysts (selected, in order)   completion-gated, host tools
    bull ⇄ bear  × 2·debate_rounds  two long-lived sessions, ask()
    research manager                completion-gated
    trader                          completion-gated
    aggressive → conservative → neutral × 3·risk_rounds   three sessions, ask()
    portfolio manager               completion-gated

Before the analysts run, pending decisions on the same ticker are scored
and reflected on (a ``reflector`` stage per entry) so the portfolio manager
reads fresh lessons.  After the portfolio manager, the decision is
recorded pending, the report tree is written and the journal is cleared.

Every unit of work — a stage payload, a debate turn — is journaled as soon
as it exists, and the loop that produces it skips what the journal already
holds, so a crashed run resumes where it stopped.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, Optional, Set

from jaato_sdk import AgentError, SessionCreateFailed

from . import data
from .board import NullBoard
from .config import RunConfig
from .journal import Journal
from .memory import DecisionLog
from .report import write_report
from .sessions import observing, open_stage
from .state import DebateTurn, RunState
from .tools import host_tools

log = logging.getLogger(__name__)


class StageFailed(RuntimeError):
    """A pipeline node ended without a usable result.

    Raised when a completion-gated stage returns no payload (the session
    ended without ``signal_completion``), when a payload carries
    ``errors[]`` (the agent says it could not answer), or when a session
    could not be created or ended in error.  The journal keeps everything
    produced before the failure, so re-running resumes at this node.
    """


# ------------------------------------------------------------------ prompts

ANALYST_PROMPT = (
    "Produce your report for {ticker} as of {trade_date}. Use your data tools "
    "first, quote only numbers the tools returned, and finish by calling "
    "signal_completion with the full report and your stance."
)

DEBATE_OPENING = (
    "Open the debate. The analyst reports are below. Make your side's case in "
    "a few tight paragraphs; the {opponent} has not spoken yet, so argue from "
    "the evidence rather than against an imagined position.\n\n{reports}"
)

DEBATE_REBUTTAL = (
    "The {opponent} just said:\n\n{argument}\n\nRespond to it directly — "
    "concede what is right, rebut what is not, and add anything from the "
    "reports that strengthens your side."
)

DEBATE_RESUME = (
    "You are rejoining a debate in progress. Analyst reports:\n\n{reports}\n\n"
    "Transcript so far:\n\n{transcript}\n\nContinue as {side}: respond to the "
    "{opponent}'s latest argument."
)

RESEARCH_MANAGER_PROMPT = (
    "Judge the investment debate for {ticker} as of {trade_date}.\n\n"
    "Analyst reports:\n\n{reports}\n\nDebate transcript:\n\n{transcript}\n\n"
    "Decide which side made the better evidence-based case, set a rating, and "
    "call signal_completion with your recommendation, rationale and the "
    "concrete actions that follow from it."
)

TRADER_PROMPT = (
    "Turn the research plan into a trade proposal for {ticker} as of {trade_date}.\n\n"
    "Research plan:\n{plan}\n\nAnalyst reports:\n\n{reports}\n\n"
    "Call signal_completion with an action, reasoning, and (where justified by "
    "the verified numbers in the reports) an entry price, stop loss and sizing "
    "note. Prices are absolute levels in the instrument's currency, never "
    "percentages."
)

RISK_OPENING = (
    "Open the risk discussion of the trader's proposal for {ticker}.\n\n"
    "Trader's proposal:\n{proposal}\n\nAnalyst reports:\n\n{reports}\n\n"
    "Argue your assigned risk posture in a few paragraphs."
)

RISK_REBUTTAL = (
    "Latest arguments from the other risk analysts:\n\n{others}\n\n"
    "Respond from your posture: what they get right, what they miss, and what "
    "the proposal should change."
)

RISK_RESUME = (
    "You are rejoining a risk discussion in progress.\n\nTrader's proposal:\n"
    "{proposal}\n\nAnalyst reports:\n\n{reports}\n\nTranscript so far:\n\n"
    "{transcript}\n\nContinue as the {side} analyst."
)

PORTFOLIO_MANAGER_PROMPT = (
    "Make the final decision on {ticker} as of {trade_date}.\n\n"
    "Trader's proposal:\n{proposal}\n\nRisk discussion:\n\n{transcript}\n\n"
    "Research plan:\n{plan}\n\nWeigh the risk arguments, then call "
    "signal_completion with a rating, an executive summary, the investment "
    "thesis, and a price target and horizon only if the evidence supports them."
)

REFLECTOR_PROMPT = (
    "A past decision has been scored.\n\nTicker: {ticker}\nDecision date: "
    "{trade_date}\nRating given: {rating}\nSummary at the time:\n{summary}\n\n"
    "Realised {holding_days}-day return: {raw:+.2%}\nAlpha versus {benchmark}: "
    "{alpha:+.2%}\n\nCall signal_completion with whether the directional call "
    "was right and one concrete lesson in two to four sentences."
)

# ------------------------------------------------------------------ stage table

ANALYST_STAGES = {
    "market": ("market_analyst", "market_analyst"),
    "sentiment": ("sentiment_analyst", "sentiment_analyst"),
    "news": ("news_analyst", "news_analyst"),
    "fundamentals": ("fundamentals_analyst", "fundamentals_analyst"),
}
"""analyst key -> (profile name, agent name)."""

RISK_ROTATION = (
    ("Aggressive", "risk_aggressive"),
    ("Conservative", "risk_conservative"),
    ("Neutral", "risk_neutral"),
)


def plan_of(cfg: RunConfig):
    """The whole diagram, derived from the config before any session opens.

    This pipeline's shape is a pure function of ``RunConfig`` — which
    analysts, ``2 * max_debate_rounds`` investment turns, ``3 *
    max_risk_rounds`` risk turns, four fixed judges — so the board can show
    what is LEFT, not merely what has happened.  Keys are the driver's
    vocabulary for a step and must match what the phases report.

    Returns a list of ``(key, label, depth)`` for :meth:`BoardState.plan`.
    """
    rows = [(f"analyst:{k}", f"{k} analyst", 0) for k in cfg.analysts]

    rows.append(("debate:investment", "investment debate", 0))
    for turn in range(2 * cfg.max_debate_rounds):
        side = "Bull" if turn % 2 == 0 else "Bear"
        rows.append((f"debate:investment:{turn}", f"{side} {turn // 2 + 1}", 1))

    rows.append(("stage:research_manager", "research manager", 0))
    rows.append(("stage:trader", "trader", 0))

    rows.append(("debate:risk", "risk debate", 0))
    for turn in range(3 * cfg.max_risk_rounds):
        side = RISK_ROTATION[turn % 3][0]
        rows.append((f"debate:risk:{turn}", f"{side} {turn // 3 + 1}", 1))

    rows.append(("stage:portfolio_manager", "portfolio manager", 0))
    return rows


def _replay(board, state: RunState) -> None:
    """Mark what the journal already holds, so a resumed run draws the truth.

    Without this a resume shows every completed stage as pending and the
    board contradicts the journal it is resuming from.
    """
    for key, report in state.reports.items():
        board.finish(f"analyst:{key}", _analyst_detail(report))
    for i, turn in enumerate(state.investment_debate):
        board.finish(f"debate:investment:{i}", "")
    if state.investment_debate:
        board.finish("debate:investment", f"{len(state.investment_debate)} turns")
    if state.research_plan:
        board.finish("stage:research_manager", str(state.research_plan.get("recommendation", "")))
    if state.trader_proposal:
        board.finish("stage:trader", str(state.trader_proposal.get("action", "")))
    for i, turn in enumerate(state.risk_debate):
        board.finish(f"debate:risk:{i}", "")
    if state.risk_debate:
        board.finish("debate:risk", f"{len(state.risk_debate)} turns")
    if state.portfolio_decision:
        board.finish("stage:portfolio_manager", str(state.portfolio_decision.get("rating", "")))


def _judge_detail(which: str, payload: Dict[str, Any]) -> str:
    """The one-glance verdict of a judge, plus how loudly it hedged."""
    field = {"research_manager": "recommendation", "trader": "action",
             "portfolio_manager": "rating"}[which]
    bits = [str(payload.get(field, ""))]
    warnings = payload.get("warnings") or []
    if warnings:
        bits.append(f"{len(warnings)} warn")
    return " · ".join(b for b in bits if b)


def _analyst_detail(report: Dict[str, Any]) -> str:
    """The one-glance verdict of an analyst report: stance, confidence, warnings."""
    bits = [str(report.get("stance", "")), str(report.get("confidence", ""))]
    warnings = report.get("warnings") or []
    if warnings:
        bits.append(f"{len(warnings)} warn")
    return " · ".join(b for b in bits if b)


def _payload_text(payload: Optional[Dict[str, Any]], *keys: str) -> str:
    if not payload:
        return "(none)"
    return "\n".join(f"{k}: {payload[k]}" for k in keys if payload.get(k) not in (None, ""))


def _require(payload: Optional[Dict[str, Any]], stage: str) -> Dict[str, Any]:
    if payload is None:
        raise StageFailed(f"{stage}: the session ended without signal_completion")
    errors = payload.get("errors") or []
    if errors:
        raise StageFailed(f"{stage}: the agent reported it could not answer: {errors}")
    for w in payload.get("warnings") or []:
        log.warning("%s: %s", stage, w)
    return payload


def _base_params(cfg: RunConfig, state: RunState) -> Dict[str, str]:
    return {
        "ticker": cfg.ticker,
        "trade_date": cfg.trade_date,
        "asset_type": cfg.asset_type,
        "instrument_context": state.instrument_context,
    }


# ------------------------------------------------------------------ the run

async def run(cfg: RunConfig, *, record_decision: bool = True,
              resolve_pending: bool = True, board=None) -> RunState:
    """Run the pipeline for ``cfg``; return the finished state.

    Raises :class:`StageFailed` when a node produces nothing usable; the
    journal then holds everything before it.

    ``board`` is any object with the :class:`~ta_cascade.board.NullBoard`
    interface.  The default records nothing, so the pipeline behaves
    identically whether or not anyone is watching — a display must never be
    load-bearing.  The driver reports STRUCTURE to it (which stage, which
    debate turn); what happens inside a stage comes from the daemon's own
    event stream, pumped by :func:`~ta_cascade.sessions.observing`.
    """
    board = board or NullBoard()
    cascade_id = uuid.uuid4().hex
    journal = Journal(cfg.journal_dir, cfg.run_key)
    memory = DecisionLog(cfg.decision_log)
    board.plan(plan_of(cfg))

    async with observing(cfg, cascade_id, board.trace):
        state = journal.load()
        if state is None:
            if resolve_pending:
                await _resolve_pending(cfg, memory, cascade_id, board)
            as_of = cfg.trade_date if cfg.trade_date < data.dt.date.today().isoformat() else None
            state = RunState(
                ticker=cfg.ticker, trade_date=cfg.trade_date, asset_type=cfg.asset_type,
                instrument_context=data.instrument_context(cfg.ticker, cfg.asset_type),
                past_context=memory.past_context(cfg.ticker, as_of=as_of),
            )
            journal.save(state)
            log.info("run %s started (cascade %s)", cfg.run_key, cascade_id)
        else:
            log.info("run %s resumed from journal %s", cfg.run_key, journal.path)
            _replay(board, state)

        params = _base_params(cfg, state)
        tools = host_tools(cfg)

        try:
            await _analysts(cfg, state, params, tools, journal, cascade_id, board)
            await _investment_debate(cfg, state, params, journal, cascade_id, board)
            await _judge(cfg, state, params, journal, cascade_id, "research_manager", board)
            await _judge(cfg, state, params, journal, cascade_id, "trader", board)
            await _risk_debate(cfg, state, params, journal, cascade_id, board)
            await _judge(cfg, state, params, journal, cascade_id, "portfolio_manager", board)
        except SessionCreateFailed as exc:
            board.close(f"stopped: {exc}")
            raise StageFailed(f"session could not be created: {exc}") from exc
        except AgentError as exc:
            board.close(f"stopped: {exc.error_type}")
            raise StageFailed(f"agent error {exc.error_type}: {exc.error_summary}") from exc
        except StageFailed as exc:
            board.close(f"stopped: {exc}")
            raise

    root = write_report(state, cfg.results_dir)
    log.info("report written to %s", root)
    if record_decision and state.portfolio_decision:
        memory.record(cfg.ticker, cfg.trade_date, state.portfolio_decision.get("rating", "REVIEW"),
                      state.portfolio_decision.get("executive_summary", ""), cfg.holding_days)
    journal.clear()
    board.close(str((state.portfolio_decision or {}).get("rating", "done")))
    return state


# ------------------------------------------------------------------ phases

async def _analysts(cfg, state, params, tools, journal, cid, board) -> None:
    for key in cfg.analysts:
        if key in state.reports:
            continue
        profile, agent = ANALYST_STAGES[key]
        board.start(f"analyst:{key}")
        async with open_stage(cfg, profile=profile, agent=agent, params=params,
                              cascade_id=cid, client_tools=tools.get(key)) as s:
            payload = await s.complete(ANALYST_PROMPT.format(**params))
        state.reports[key] = _require(payload, key)
        board.finish(f"analyst:{key}", _analyst_detail(state.reports[key]))
        journal.save(state)


async def _investment_debate(cfg, state, params, journal, cid, board) -> None:
    total = 2 * cfg.max_debate_rounds
    if len(state.investment_debate) >= total:
        return
    board.start("debate:investment")
    reports = state.reports_block()
    async with open_stage(cfg, profile="bull_researcher", agent="bull_researcher",
                          params=params, cascade_id=cid) as bull, \
               open_stage(cfg, profile="bear_researcher", agent="bear_researcher",
                          params=params, cascade_id=cid) as bear:
        briefed: Set[str] = set()
        while len(state.investment_debate) < total:
            turn = len(state.investment_debate)
            side, session, opponent = ("Bull", bull, "Bear") if turn % 2 == 0 else ("Bear", bear, "Bull")
            if turn == 0:
                prompt = DEBATE_OPENING.format(opponent=opponent, reports=reports)
            elif side not in briefed:
                prompt = DEBATE_RESUME.format(reports=reports, side=side, opponent=opponent,
                                              transcript=RunState.transcript(state.investment_debate))
            else:
                prompt = DEBATE_REBUTTAL.format(opponent=opponent,
                                                argument=state.investment_debate[-1].text)
            briefed.add(side)
            board.start(f"debate:investment:{turn}")
            text = await session.ask(prompt)
            state.investment_debate.append(DebateTurn(side, text.strip()))
            board.finish(f"debate:investment:{turn}")
            journal.save(state)
    board.finish("debate:investment", f"{total} turns")


async def _judge(cfg, state, params, journal, cid, which: str, board) -> None:
    """One completion-gated judge: research manager, trader or portfolio manager."""
    reports = state.reports_block()
    if which == "research_manager":
        if state.research_plan:
            return
        prompt = RESEARCH_MANAGER_PROMPT.format(
            ticker=cfg.ticker, trade_date=cfg.trade_date, reports=reports,
            transcript=RunState.transcript(state.investment_debate))
        extra: Dict[str, str] = {}
    elif which == "trader":
        if state.trader_proposal:
            return
        prompt = TRADER_PROMPT.format(
            ticker=cfg.ticker, trade_date=cfg.trade_date, reports=reports,
            plan=_payload_text(state.research_plan, "recommendation", "rationale", "strategic_actions"))
        extra = {}
    else:
        if state.portfolio_decision:
            return
        prompt = PORTFOLIO_MANAGER_PROMPT.format(
            ticker=cfg.ticker, trade_date=cfg.trade_date,
            proposal=_payload_text(state.trader_proposal, "action", "reasoning", "entry_price",
                                   "stop_loss", "position_sizing"),
            transcript=RunState.transcript(state.risk_debate),
            plan=_payload_text(state.research_plan, "recommendation", "rationale"))
        extra = {"past_context": state.past_context or "(no prior decisions recorded)"}
    board.start(f"stage:{which}")
    async with open_stage(cfg, profile=which, agent=which, params={**params, **extra},
                          cascade_id=cid) as s:
        payload = _require(await s.complete(prompt), which)
    setattr(state, {"research_manager": "research_plan", "trader": "trader_proposal",
                    "portfolio_manager": "portfolio_decision"}[which], payload)
    board.finish(f"stage:{which}", _judge_detail(which, payload))
    journal.save(state)


async def _risk_debate(cfg, state, params, journal, cid, board) -> None:
    total = 3 * cfg.max_risk_rounds
    if len(state.risk_debate) >= total:
        return
    board.start("debate:risk")
    reports = state.reports_block()
    proposal = _payload_text(state.trader_proposal, "action", "reasoning", "entry_price",
                             "stop_loss", "position_sizing")
    async with open_stage(cfg, profile="risk_aggressive", agent="risk_aggressive", params=params, cascade_id=cid) as a, \
               open_stage(cfg, profile="risk_conservative", agent="risk_conservative", params=params, cascade_id=cid) as c, \
               open_stage(cfg, profile="risk_neutral", agent="risk_neutral", params=params, cascade_id=cid) as n:
        sessions = {"Aggressive": a, "Conservative": c, "Neutral": n}
        briefed: Set[str] = set()
        while len(state.risk_debate) < total:
            turn = len(state.risk_debate)
            side = RISK_ROTATION[turn % 3][0]
            if turn == 0:
                prompt = RISK_OPENING.format(ticker=cfg.ticker, proposal=proposal, reports=reports)
            elif side not in briefed:
                prompt = RISK_RESUME.format(proposal=proposal, reports=reports, side=side,
                                            transcript=RunState.transcript(state.risk_debate))
            else:
                since = state.risk_debate[-2:] if turn >= 2 else state.risk_debate[-1:]
                prompt = RISK_REBUTTAL.format(others=RunState.transcript(since))
            briefed.add(side)
            board.start(f"debate:risk:{turn}")
            text = await sessions[side].ask(prompt)
            state.risk_debate.append(DebateTurn(side, text.strip()))
            board.finish(f"debate:risk:{turn}")
            journal.save(state)
    board.finish("debate:risk", f"{total} turns")


async def _resolve_pending(cfg: RunConfig, memory: DecisionLog, cid: str, board) -> None:
    """Score and reflect on every pending same-ticker decision that has enough bars."""
    for entry in memory.pending(cfg.ticker):
        got = data.return_after(entry.ticker, entry.trade_date, entry.holding_days or cfg.holding_days)
        bench = data.return_after(cfg.benchmark, entry.trade_date, entry.holding_days or cfg.holding_days)
        if got is None or bench is None:
            log.info("decision %s %s still pending: not enough bars", entry.ticker, entry.trade_date)
            continue
        raw, resolved_on = got
        alpha = raw - bench[0]
        prompt = REFLECTOR_PROMPT.format(
            ticker=entry.ticker, trade_date=entry.trade_date, rating=entry.rating,
            summary=entry.summary, holding_days=entry.holding_days or cfg.holding_days,
            raw=raw, alpha=alpha, benchmark=cfg.benchmark)
        params = {"ticker": entry.ticker, "trade_date": entry.trade_date}
        key = f"reflector:{entry.trade_date}"
        board.start(key, f"reflect on {entry.trade_date}", 0)
        try:
            async with open_stage(cfg, profile="reflector", agent="reflector", params=params,
                                  cascade_id=cid) as s:
                payload = _require(await s.complete(prompt), "reflector")
        except (StageFailed, AgentError, SessionCreateFailed) as exc:
            log.warning("reflection for %s %s failed: %s", entry.ticker, entry.trade_date, exc)
            board.finish(key, "failed", failed=True)
            continue
        board.finish(key, f"alpha {alpha:+.2%}")
        memory.resolve(entry.ticker, entry.trade_date, raw_return=raw, alpha=alpha,
                       benchmark=cfg.benchmark, resolved_on=resolved_on,
                       lesson=str(payload.get("lesson", "")),
                       call_was_correct=payload.get("call_was_correct"))
