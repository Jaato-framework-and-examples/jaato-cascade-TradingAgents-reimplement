"""The one place a jaato session is opened.

Carries the recipe ``jaato-scaffold new cascade --recoverable`` emits, so
every stage connects the same way: ``IPCRecoveryClient`` (auto-reconnect,
survives a daemon restart), ``ClientType.API`` (keeps ``signal_completion``
on the wire — the daemon strips it for terminal/web/chat clients), a real
``env_file`` (``None`` crashes the handshake), and a connect timeout long
enough for a cold daemon autostart.

Host tools are passed as ``client_tools`` so the facade registers them after
connect and before ``create_session`` — a tool registered mid-session is not
seen by the runner-tier model.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Any, AsyncIterator, Callable, Dict, List, Optional

from jaato_sdk import ClientType, IPCClient, IPCRecoveryClient

from .config import RunConfig
from .observer import OBSERVED_EVENT_TYPES, StageObserver

log = logging.getLogger(__name__)


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
    return IPCRecoveryClient.session(
        socket_path=cfg.socket,
        client_type=ClientType.API,
        auto_start=cfg.auto_start,
        env_file=str(cfg.env_file),
        workspace_path=str(cfg.workspace),
        on_status_change=_on_status,
        connect_timeout=cfg.connect_timeout,
        profile=profile,
        agent=agent,
        agent_params=params,
        cascade_driver_id=cascade_id,
        client_tools=client_tools,
    )


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
    if not await client.connect(timeout=cfg.connect_timeout):
        log_line("stage-interior progress is OFF: the observer could not reach the daemon")
        yield
        return

    watcher = StageObserver()

    async def _pump() -> None:
        async for event in client.cascade_events(
            cascade_id, event_types=OBSERVED_EVENT_TYPES, role="observer",
        ):
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
        with contextlib.suppress(Exception):
            await client.disconnect()
