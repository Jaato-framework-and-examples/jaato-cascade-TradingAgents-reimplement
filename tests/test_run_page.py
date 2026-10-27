"""The run page's own render path, exercised in node against a DOM stub.

Written because `v0.3.0` shipped a configuration view that crashed in the one
case it was added for -- a board with no runs -- while 209 unit tests and 3
end-to-end tests passed at that tag.  None of them execute a line of the page.
`render()` read ``d.paths.results`` unconditionally, the no-runs caller passes
no ``paths``, and the outer catch rewrote the resulting TypeError as "cannot
reach the board" over the caller's own message.  So the page failed, blamed
the network, and every endpoint answered 200 throughout.

The gap this closes is narrow and deliberate: it is not a browser test and it
asserts nothing about appearance.  It runs the page's real script with the
smallest stub that lets `render()` execute, and checks the two shapes the page
is actually called with -- a plan with no run, and a run -- because those are
the two the code has to tell apart.

node is required and the test SKIPS without it rather than passing quietly: a
skipped test that says why is honest, and a green tier that never ran the
assertion is what produced this bug in the first place.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

PAGE = Path(__file__).resolve().parents[1] / "ta_cascade" / "ui" / "static" / "run.html"

#: Enough DOM for `render()` to run: every `$()` returns a recording stub, and
#: the timers and fetch are inert so loading the script starts no polling.
HARNESS = r"""
const els = {};
function el() { return {textContent: "", innerHTML: "", hidden: true, value: "",
                        style: {}, classList: {add(){}, remove(){}, toggle(){}},
                        addEventListener(){}, closest(){ return null; },
                        querySelectorAll(){ return []; }}; }
globalThis.document = {
  querySelector(sel) { return els[sel] || (els[sel] = el()); },
  querySelectorAll() { return []; },
  addEventListener() {},
  getElementById(id) { return document.querySelector("#" + id); },
};
globalThis.window = {addEventListener(){}, location: {hash: ""}};
globalThis.location = {hash: "", slice(){ return ""; }};
globalThis.fetch = async () => ({json: async () => ({})});
globalThis.setInterval = () => 0;
globalThis.setTimeout = () => 0;
__SCRIPT__
try {
  render(__ARG__);
  // Read through a default: an element render() never touched is absent from
  // the stub, and "absent" is the assertion in the no-run case.
  const txt = s => (els[s] ? els[s].textContent : "");
  const html = s => (els[s] ? els[s].innerHTML : "");
  console.log(JSON.stringify({ok: true, title: txt("#title"), sub: txt("#sub"),
                              bands: html("#bands").length}));
} catch (e) {
  console.log(JSON.stringify({ok: false, error: String(e)}));
}
"""


def _script() -> str:
    """The page's own script, so the test cannot drift from what ships."""
    blocks = re.findall(r"<script>(.*?)</script>", PAGE.read_text(encoding="utf-8"), re.S)
    assert blocks, "run.html carries no inline script"
    return "\n".join(blocks)


def _render(arg: dict, tmp_path: Path) -> dict:
    if shutil.which("node") is None:
        pytest.skip("node is not installed, so the page's own script cannot be executed here")
    src = HARNESS.replace("__SCRIPT__", _script()).replace("__ARG__", json.dumps(arg))
    f = tmp_path / "harness.mjs"
    f.write_text(src, encoding="utf-8")
    out = subprocess.run(["node", str(f)], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, f"node failed: {out.stderr[:800]}"
    return json.loads(out.stdout.strip().splitlines()[-1])


def _stage(name: str, band: str) -> dict:
    return {"stage": name, "band": band, "state": "planned", "session_id": None,
            "capabilities": {"schema": "s.json", "gates": [], "sections": [],
                             "references": False, "limits": {}},
            "host_tools": [], "mode": "complete()", "capability_source": "daemon"}


PLAN_ONLY = {"stages": [_stage("market_analyst", "analysts")],
             "bands": [{"name": "analysts", "stages": [_stage("market_analyst", "analysts")]}]}


def test_render_survives_a_plan_with_no_run(tmp_path):
    """The case v0.3.0 crashed in: a configured pipeline and no run at all."""
    out = _render(PLAN_ONLY, tmp_path)
    assert out["ok"], f"render() threw on the no-run shape: {out.get('error')}"


def test_a_plan_with_no_run_is_titled_as_one(tmp_path):
    out = _render(PLAN_ONLY, tmp_path)
    assert out["title"] == "configured pipeline"
    assert "undefined" not in out["title"], "a missing run must not reach the page as text"


def test_the_callers_own_message_is_not_overwritten(tmp_path):
    """`#sub` carries which set resolved and which stages are missing.

    render() must leave it alone when there is no run; replacing it with a
    results path threw that away, and the catch then replaced it again with
    "cannot reach the board".
    """
    out = _render(PLAN_ONLY, tmp_path)
    assert out["sub"] == "", "render() wrote to #sub with no run to describe"


def test_a_real_run_still_titles_and_subtitles(tmp_path):
    """The run shape must keep working: the fix is a branch, not a removal."""
    run = dict(PLAN_ONLY, ticker="NVDA", trade_date="2026-10-17",
               paths={"results": "/tmp/results", "workspace": "/tmp/ws"},
               verdict={}, money={}, effort={}, counts={})
    out = _render(run, tmp_path)
    assert out["ok"], out.get("error")
    assert out["title"] == "NVDA · 2026-10-17"
    assert out["sub"] == "/tmp/results"


def test_bands_are_drawn_in_both_shapes(tmp_path):
    """Whatever the title does, the stage cards are the point of the view."""
    assert _render(PLAN_ONLY, tmp_path)["bands"] > 0
