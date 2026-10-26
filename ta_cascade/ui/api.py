"""The web board: a read-only web view over what a run or a sweep left on disk.

Renderer #2.  :mod:`ta_cascade.richboard` draws one run in a terminal; this
draws a sweep of hundreds of arms, and one run stage by stage, in a browser.
All three sit on pure state — :mod:`ta_cascade.board`, :mod:`ta_cascade.sweep`
and :mod:`ta_cascade.runview` — which is what lets any renderer be replaced
without touching what decides the truth.

Deliberately **read-only and stateless**.  It starts no runs, stops none, and
holds nothing in memory: every request re-reads the files.  A sweep is launched
with ``jaato-eval run`` from a shell and outlives this process, so restarting
the board never disturbs a run and the board is never on a run's critical path.
That is kb-rip's philosophy and the part of it worth copying hardest.

It also asks the DAEMON nothing.  A run's stages, the persona each one was
actually given and the profile each one actually resolved are all read from the
session records the daemon already saved, so this board renders a run whose
daemon has since been restarted, and a sweep arm whose workspace was kept after
the run finished.  The alternative — attaching an observer of its own — would
make the board stateful, would lose everything on a restart, and could say
nothing about a run that ended before it started, which here is most of them.

Starlette rather than FastAPI: the venv already has starlette and uvicorn, the
surface is a handful of routes, and a dependency added for a handful of routes
is a dependency added for ever.
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from starlette.applications import Starlette
from starlette.responses import FileResponse, JSONResponse
from starlette.routing import Route

from .. import plan, runview, sweep

STATIC = Path(__file__).parent / "static"


def known_run(results_dir: Path, ticker: str, trade_date: str) -> bool:
    """Whether this results tree actually holds that run.

    **A request may name only a run that exists**, and that is the whole input
    validation — by MEMBERSHIP, not by pattern.  Two reasons it is the right
    check.  It makes path traversal structurally impossible rather than
    filtered: the names a reader may ask for are the ones the driver itself
    wrote, so no crafted segment reaches the filesystem at all.  And it cannot
    go stale, where a regex for "what a ticker looks like" would have to be
    kept in step with every symbol the data layer accepts (``BTC-USD``,
    ``^GSPC``) and would silently refuse a legitimate run the day it fell
    behind.

    Measured before this existed: ``GET /api/run/%2e%2e/%2e%2e`` matched the
    route, reached :func:`ta_cascade.runview.survey` with ``ticker=".."``, and
    raised ``ValueError: Invalid isoformat string: '..'`` out of the host-tool
    specs — a 500 whose traceback names filesystem paths, which is exactly
    what must not happen on a board bound to anything but loopback.
    """
    return {"ticker": ticker, "trade_date": trade_date} in runview.runs(results_dir)


def known_session(results_dir: Path, ticker: str, trade_date: str, sid: str) -> bool:
    """Whether that run's own session log names this session.

    The same membership rule one level down, so a reader can open a transcript
    only for a session the run recorded opening.
    """
    return sid in runview.session_ids(results_dir, ticker, trade_date)


def create_app(*, tasks_dir: Optional[Path] = None, results_path: Optional[Path] = None,
               workspaces_dir: Optional[Path] = None, name: str = "",
               results_dir: Optional[Path] = None,
               workspace: Optional[Path] = None,
               config_root: Optional[Path] = None,
               socket: Optional[str] = None,
               env_file: Optional[Path] = None) -> Starlette:
    """An app over whichever of the two views its paths support.

    The sweep view needs ``tasks_dir`` (the denominator) and ``results_path``
    (what jaato-eval finished), plus ``workspaces_dir`` for arms still in
    flight.  The run view needs ``results_dir`` (the tree a run wrote) and
    ``workspace`` (where the daemon saved its session records).  Either set may
    be absent, and the routes that set would serve are then not built — a
    route that answers "no paths were given" is a route that looks broken.

    The run view is bound to ONE results tree.  A sweep arm has its own tree
    inside its own kept workspace, so reading an arm means pointing a board at
    that workspace (``run-board --results <ws>/results --workspace <ws>``)
    rather than this app guessing which arm a cell meant.
    """
    routes: List[Route] = []

    if tasks_dir is not None and results_path is not None:
        async def api_sweep(request):
            data = sweep.survey(tasks_dir, results_path, workspaces_dir)
            data["name"] = name
            data["paths"] = {"tasks": str(tasks_dir), "results": str(results_path),
                             "workspaces": str(workspaces_dir) if workspaces_dir else None}
            return JSONResponse(data)

        async def index(request):
            return FileResponse(STATIC / "index.html")

        routes += [Route("/", index), Route("/api/sweep", api_sweep)]

    if results_dir is not None and workspace is not None:
        async def api_runs(request):
            return JSONResponse({"runs": runview.runs(results_dir),
                                 "paths": {"results": str(results_dir),
                                           "workspace": str(workspace)}})

        async def api_run(request):
            ticker, date = request.path_params["ticker"], request.path_params["date"]
            if not known_run(results_dir, ticker, date):
                return JSONResponse({"error": "no such run in this results tree"}, 404)
            data = runview.survey(results_dir, ticker, date,
                                  workspace=workspace, config_root=config_root)
            return JSONResponse(data)

        async def api_session(request):
            ticker, date = request.path_params["ticker"], request.path_params["date"]
            sid = request.path_params["sid"]
            if not known_run(results_dir, ticker, date):
                return JSONResponse({"error": "no such run in this results tree"}, 404)
            if not known_session(results_dir, ticker, date, sid):
                return JSONResponse({"error": "that run's log names no such session"}, 404)
            events = runview.eventlog.read(
                runview.eventlog.path_for(results_dir, ticker, date))
            return JSONResponse(runview.session(workspace, sid, events))

        async def run_index(request):
            return FileResponse(STATIC / "run.html")

        _config_root = Path(config_root) if config_root else Path(workspace) / ".jaato"
        _env_file = Path(env_file) if env_file else Path(workspace) / ".env"

        async def api_plan(request):
            # The ONE route that asks the daemon.  Everything else here reads
            # disk, so a run still renders when the daemon is down and only
            # the configuration view degrades -- and it degrades by SAYING SO.
            # The SDK import is local because the boards do not otherwise need
            # it: a board-only deployment installs starlette, uvicorn and
            # PyYAML and nothing else, and must keep serving runs without it.
            try:
                from .. import sessions
            except ImportError as exc:
                return JSONResponse(
                    {"error": f"no jaato SDK in this environment, so the configured "
                              f"pipeline cannot be resolved: {exc}"}, 503)
            try:
                profiles = await sessions.resolved_profiles(
                    socket=socket or "/tmp/jaato.sock", workspace=str(workspace),
                    config_root=str(_config_root), env_file=str(_env_file))
            except Exception as exc:                      # the daemon's answer, or its absence
                return JSONResponse({"error": f"{type(exc).__name__}: {exc}"}, 503)
            data = plan.assemble(profiles, profile_set=plan.profile_set_of(_env_file))
            data["paths"] = {"workspace": str(workspace), "config_root": str(_config_root),
                             "env_file": str(_env_file)}
            return JSONResponse(data)

        routes += [
            Route("/api/plan", api_plan),
            Route("/run", run_index),
            Route("/api/runs", api_runs),
            Route("/api/run/{ticker}/{date}", api_run),
            Route("/api/run/{ticker}/{date}/session/{sid}", api_session),
        ]
        if tasks_dir is None:
            routes.append(Route("/", run_index))

    return Starlette(routes=routes)
