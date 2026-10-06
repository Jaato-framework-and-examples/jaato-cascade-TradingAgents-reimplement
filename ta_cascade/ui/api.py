"""The sweep board: a read-only web view over what a sweep left on disk.

Renderer #2.  :mod:`ta_cascade.richboard` draws one run in a terminal; this
draws a sweep of hundreds of arms in a browser.  Both sit on pure state —
:mod:`ta_cascade.board` and :mod:`ta_cascade.sweep` — which is what lets either
be replaced without touching what decides the truth.

Deliberately **read-only and stateless**.  It starts no runs, stops none, and
holds nothing in memory: every request re-reads the files.  A sweep is launched
with ``jaato-eval run`` from a shell and outlives this process, so restarting
the board never disturbs a run and the board is never on a run's critical path.
That is kb-rip's philosophy and the part of it worth copying hardest.

Starlette rather than FastAPI: the venv already has starlette and uvicorn, the
surface is two routes, and a dependency added for two routes is a dependency
added for ever.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from starlette.applications import Starlette
from starlette.responses import FileResponse, JSONResponse
from starlette.routing import Route

from .. import sweep

STATIC = Path(__file__).parent / "static"


def create_app(tasks_dir: Path, results_path: Path, workspaces_dir: Optional[Path],
               name: str) -> Starlette:
    """An app bound to one sweep's three paths."""

    async def api_sweep(request):
        data = sweep.survey(tasks_dir, results_path, workspaces_dir)
        data["name"] = name
        data["paths"] = {"tasks": str(tasks_dir), "results": str(results_path),
                         "workspaces": str(workspaces_dir) if workspaces_dir else None}
        return JSONResponse(data)

    async def index(request):
        return FileResponse(STATIC / "index.html")

    return Starlette(routes=[Route("/", index), Route("/api/sweep", api_sweep)])
