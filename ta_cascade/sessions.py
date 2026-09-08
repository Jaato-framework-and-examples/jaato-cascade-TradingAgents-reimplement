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

import logging
from typing import Any, Dict, List, Optional

from jaato_sdk import ClientType, IPCRecoveryClient

from .config import RunConfig

log = logging.getLogger(__name__)


def _on_status(status: Any) -> None:
    log.info("connection: %s", getattr(status, "state", status))


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
