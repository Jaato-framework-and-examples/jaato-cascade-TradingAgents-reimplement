"""The one place a jaato session is opened.

Carries the recipe ``jaato-scaffold new cascade --recoverable`` emits, so
every stage connects the same way: ``IPCRecoveryClient`` (auto-reconnect,
survives a daemon restart), ``ClientType.API`` (keeps ``signal_completion``
on the wire — the daemon strips it for terminal/web/chat clients), a real
``env_file`` (``None`` crashes the handshake), and a connect timeout long
enough for a cold daemon autostart.

Host tools are passed as ``client_tools`` so the facade registers them after
connect and before ``create_session`` — a tool registered mid-session is not
seen by the runner-tier model.  Registration is also where the daemon states
the deadline it will hold each tool to, so :func:`check_tool_budgets` runs
once per session, between that answer and the model's first turn.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Any, AsyncIterator, Callable, Dict, List, Optional

from jaato_sdk import ClientType, IPCClient, IPCRecoveryClient
from jaato_sdk.events import SessionProfilesEvent

from . import eventlog, sessionlog, tools
from .config import RunConfig
from .observer import OBSERVED_EVENT_TYPES, StageObserver

log = logging.getLogger(__name__)


class ToolBudgetMismatch(RuntimeError):
    """The daemon holds a host tool to a budget its handler was not sized for.

    Raised rather than worked around: the handler deadlines were derived from
    :mod:`jaato_sdk.client_tool_timeout`, which the daemon's own registration
    path calls, so a disagreement means the two sides are not the build they
    report themselves to be — and a backtest arm must not run on that.
    """


def check_tool_budgets(expected: Dict[str, float], reported: Dict[str, float]) -> None:
    """Fail unless the daemon reports the budgets the handlers were sized for.

    ``expected`` is :func:`ta_cascade.tools.declared_budgets`; ``reported`` is
    ``session.client.client_tool_timeouts``, what the daemon answered to this
    session's registration (protocol 1.39+, jaato#1625).  A daemon too old to
    report them answers nothing, which is a mismatch like any other: the
    handler deadlines would be sized against a budget nobody confirmed.
    """
    if not expected:
        return
    if not reported:
        raise ToolBudgetMismatch(
            f"the daemon reported no host-tool budgets for {sorted(expected)} — "
            "it is older than protocol 1.39 (jaato#1625), so the handler "
            "deadlines cannot be checked against what it will enforce")
    off = {name: (want, reported.get(name)) for name, want in expected.items()
           if reported.get(name) != want}
    if off:
        raise ToolBudgetMismatch(
            "the daemon's host-tool budgets differ from what the handlers were "
            f"sized for (name: ours, theirs): {off}")


def _on_status(status: Any) -> None:
    # DEBUG, not INFO: a stage's connect/disconnect used to be the only sign
    # of life in a run's output, so it was worth a line each.  The board now
    # shows the stage itself starting and finishing, which is the fact those
    # three lines per stage were standing in for.  `-v` still shows them.
    log.debug("connection: %s", getattr(status, "state", status))


def open_stage(
    cfg: RunConfig,
    *,
    profile: str,
    agent: str,
    params: Dict[str, str],
    cascade_id: str,
    client_tools: Optional[List[Dict[str, Any]]] = None,
):
    """Return the facade's async context manager for one pipeline node.

    ``profile`` is a name resolved daemon-side against
    ``<workspace>/.jaato/profiles/<JAATO_PROFILE_SET>/`` (the set comes from
    the workspace ``.env``); ``agent`` names the persona under
    ``.jaato/agents/``; ``params`` are substituted into it and must all be
    strings (they cross the wire as ``key=value`` tokens).  ``cascade_id``
    tenants every node of one run so they share a warm runner slot and an
    observer can attach to the whole run.
    """
    bad = {k: type(v).__name__ for k, v in params.items() if not isinstance(v, str)}
    if bad:
        raise TypeError(f"agent_params must be strings; got {bad}")
    inner = IPCRecoveryClient.session(
        socket_path=cfg.socket,
        client_type=ClientType.API,
        auto_start=cfg.auto_start,
        env_file=str(cfg.env_file),
        workspace_path=str(cfg.workspace),
        config_root=str(cfg.config_root),
        on_status_change=_on_status,
        connect_timeout=cfg.connect_timeout,
        profile=profile,
        agent=agent,
        agent_params=params,
        cascade_driver_id=cascade_id,
        client_tools=client_tools,
    )
    return _accounted(inner, cfg, profile=profile, agent=agent, cascade_id=cascade_id,
                      client_tools=client_tools)


async def _consumption(session) -> Dict[str, Any]:
    """What the daemon measured for this session, or why it could not say.

    Must be asked while the session is still ATTACHED: once the context
    exits there is nobody holding it to answer.  The failure path records
    the reason rather than a zero, so a reader can distinguish a session
    that cost nothing from one nobody measured.
    """
    try:
        return {"consumption": (await session.client.get_diagnostics()).consumption}
    except (TimeoutError, ConnectionError, ValueError, AttributeError, OSError) as exc:
        return {"consumption_error": f"{type(exc).__name__}: {exc}"[:300]}


@contextlib.asynccontextmanager
async def _accounted(inner, cfg: RunConfig, *, profile: str, agent: str, cascade_id: str,
                     client_tools: Optional[List[Dict[str, Any]]] = None):
    """Wrap a stage's session so the run keeps an account of it.

    The ``ended`` line is written from the ``finally``, which runs INSIDE the
    session context — the one window in which the daemon can still be asked
    what the session spent.  It is written for a stage that raised too: a
    failed stage costs money, and a cost record that omits failures
    understates every bill it appears in.
    """
    async with inner as session:
        sid = getattr(session, "session_id", "") or ""
        sessionlog.write(cfg, "started", sid, stage=profile, agent=agent, cascade_id=cascade_id)
        # Asked here because registration happened inside `inner.__aenter__`,
        # between connect and create_session: this is the first moment the
        # daemon's answer exists, and the last before the model can call a tool.
        check_tool_budgets(tools.declared_budgets(client_tools or []),
                           session.client.client_tool_timeouts)
        failed = None
        try:
            yield session
        except BaseException as exc:          # noqa: BLE001 — recorded, never swallowed
            failed = f"{type(exc).__name__}: {exc}"[:300]
            raise
        finally:
            terminus = getattr(session, "terminus", None)
            sessionlog.write(cfg, "ended", sid, stage=profile, agent=agent, cascade_id=cascade_id,
                             reason=getattr(terminus, "reason", None) if terminus else None,
                             failed=failed, **await _consumption(session))


@contextlib.asynccontextmanager
async def observing(cfg: RunConfig, cascade_id: str,
                    log_line: Callable[[str], None]) -> AsyncIterator[None]:
    """Render stage-interior progress for as long as the body runs.

    Opens a SECOND connection in the ``observer`` role and pumps this run's
    cascade event stream through :class:`~ta_cascade.observer.StageObserver`.
    A second connection rather than one of the stages': stage clients are
    opened and closed per stage by :func:`open_stage`, and the whole point is
    to see what happens between them.

    ``auto_start=False``: the observer must never be the thing that starts a
    daemon.  The stages do that, and a display racing them into ``--daemon``
    would make "no daemon" unreportable.

    The pump NEVER fails the run.  It is a display: if the observer's
    connection drops, the pipeline is still doing the work, and stopping an
    analysis because its narrator went quiet would be absurd.  The failure IS
    reported, so a silent panel is never mistaken for a stalled daemon.
    """
    client = IPCClient(
        socket_path=cfg.socket,
        client_type=ClientType.API,
        auto_start=False,
        env_file=str(cfg.env_file),
        workspace_path=str(cfg.workspace),
        config_root=str(cfg.config_root),
    )
    events = eventlog.path_for(cfg.results_dir, cfg.ticker, cfg.trade_date)
    if not await client.connect(timeout=cfg.connect_timeout):
        log_line("stage-interior progress is OFF: the observer could not reach the daemon")
        # Written down, not merely printed: a reader coming to this run
        # afterwards must be able to tell an empty events file from a stage
        # that did nothing, and the terminal line is gone by then.
        eventlog.append(events, eventlog.note("observer_detached", why="could not reach the daemon"))
        yield
        return

    watcher = StageObserver()
    eventlog.append(events, eventlog.note("observer_attached", socket=cfg.socket))

    async def _pump() -> None:
        async for event in client.cascade_events(
            cascade_id, event_types=OBSERVED_EVENT_TYPES, role="observer",
        ):
            # Recorded before rendered: the lines are for whoever is watching
            # now, the rows for whoever reads this run later, and the later
            # reader is the one who cannot ask again.
            row = eventlog.record(event)
            if row is not None:
                eventlog.append(events, row)
            for line in watcher.render(event):
                log_line(line)

    task = asyncio.create_task(_pump())
    try:
        yield
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        if task.done() and not task.cancelled():
            exc = task.exception()
            if exc is not None:
                log_line(f"the progress stream ended early: {type(exc).__name__}: {exc}")
                eventlog.append(events, eventlog.note(
                    "observer_detached", why=f"{type(exc).__name__}: {exc}"[:300]))
        with contextlib.suppress(Exception):
            await client.disconnect()


async def resolved_profiles(*, socket: str, workspace: str, config_root: str,
                            env_file: str, timeout: float = 30.0) -> Dict[str, Dict[str, Any]]:
    """Every profile of this workspace's set, AS THE DAEMON RESOLVES IT.

    ``session.profiles`` is answered by the component that OWNS the inheritance
    rules, so each entry is what a session of that profile would actually start
    with: ``inherits`` merged, the set's binding applied, and
    ``suppress_inherited_processors`` already honoured.

    That last one is why this asks the daemon rather than reading
    ``_base_<stage>.yaml``.  Parsing the base files here would be a second
    implementation of rules the framework owns -- plugins union, processors
    concatenate, limits are min-wins -- and it would be WRONG wherever a set
    changes a capability: under the ``echo`` set the trader declines the
    ``rules_read`` gate, and the base file still declares it.  Measured
    2026-10-26: the daemon returns one gate for that profile, the base file
    says two.

    Raises rather than answering partially.  A configuration view exists to be
    trusted, so "could not ask" must be distinguishable from "has none" --
    there is no disk fallback, because the fallback is the wrong answer.
    """
    client = IPCRecoveryClient(
        str(socket), client_type=ClientType.API, auto_start=False,
        env_file=str(env_file), workspace_path=str(workspace),
        config_root=str(config_root))
    if not await client.connect(timeout=timeout):
        raise ConnectionError(f"no jaato daemon at {socket}")
    try:
        async with asyncio.timeout(timeout):
            await client.list_profiles()
            async for ev in client.events():
                if isinstance(ev, SessionProfilesEvent):
                    break
            else:  # pragma: no cover - the stream ended without an answer
                raise ConnectionError("the daemon's event stream ended before it listed profiles")
    finally:
        await client.disconnect()
    if ev.parse_errors:
        log.warning("daemon reported %d profile parse error(s): %s", len(ev.parse_errors),
                    "; ".join(f"{e.name}: {e.error}" for e in ev.parse_errors))
    return {p.name: p.model_dump(mode="json") for p in ev.profiles}
