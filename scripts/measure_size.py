#!/usr/bin/env python3
"""Size and complexity of this repository versus the reference implementation.

Usage:
    python scripts/measure_size.py /path/to/TradingAgents /path/to/this/repo

Counts physical lines, logical lines (non-blank, excluding comments and
docstrings) and doc/comment lines per layer, runs radon cyclomatic
complexity per function (``pip install radon``), and counts runtime
dependencies from each ``pyproject.toml``.  The figures in
``docs/size-and-complexity.md`` were produced by this script; re-run it
when either side changes.
"""
import io
import json
import re
import subprocess
import sys
import tokenize
from pathlib import Path


def sloc(path: Path):
    src = path.read_text(errors="replace")
    lines = src.splitlines()
    doc = set()
    try:
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type == tokenize.COMMENT:
                doc.add(tok.start[0])
            elif tok.type == tokenize.STRING and tok.line.strip().startswith(('"""', "'''", 'r"""')):
                doc.update(range(tok.start[0], tok.end[0] + 1))
    except Exception:  # noqa: BLE001 — a tokenize failure just under-counts docs
        pass
    logical = sum(1 for i, l in enumerate(lines, 1) if l.strip() and i not in doc)
    return len(lines), logical, len(doc)


def group(files):
    p = l = c = 0
    for f in files:
        a, b, d = sloc(f)
        p, l, c = p + a, l + b, c + d
    return dict(files=len(files), physical=p, logical=l, doc=c)


def radon(files):
    if not files:
        return dict(functions=0, mean=0, max=0, over10=0, over15=0)
    out = subprocess.run([sys.executable, "-m", "radon", "cc", "-s", "-j", *map(str, files)],
                         capture_output=True, text=True).stdout
    scores = sorted(b["complexity"] for blocks in json.loads(out or "{}").values()
                    for b in blocks if b["type"] in ("function", "method"))
    return dict(functions=len(scores), mean=round(sum(scores) / len(scores), 2) if scores else 0,
                max=scores[-1] if scores else 0, over10=sum(s > 10 for s in scores),
                over15=sum(s > 15 for s in scores))


def report(name, groups):
    print(f"\n== {name}")
    tot = dict(files=0, physical=0, logical=0, doc=0)
    allf = []
    for g, files in groups.items():
        s, r = group(files), radon(files)
        for k in tot:
            tot[k] += s[k]
        allf += files
        print(f"  {g:44s} files={s['files']:3d} physical={s['physical']:5d} logical={s['logical']:5d} "
              f"doc={s['doc']:4d}  cc: n={r['functions']} mean={r['mean']} max={r['max']} >10={r['over10']} >15={r['over15']}")
    r = radon(allf)
    print(f"  {'TOTAL':44s} files={tot['files']:3d} physical={tot['physical']:5d} logical={tot['logical']:5d} "
          f"doc={tot['doc']:4d}  cc: n={r['functions']} mean={r['mean']} max={r['max']} >10={r['over10']} >15={r['over15']}")


def nonpy_lines(root: Path, pattern: str):
    files = [p for p in root.rglob(pattern) if p.is_file()]
    return len(files), sum(len(p.read_text(errors="replace").splitlines()) for p in files)


def deps(pyproject: Path):
    m = re.search(r"dependencies\s*=\s*\[(.*?)\]", pyproject.read_text(), re.S)
    return [d.strip().strip('",') for d in m.group(1).split("\n") if d.strip().strip('",')] if m else []


def main(ta: Path, ours: Path) -> None:
    t = ta / "tradingagents"
    report("TradingAgents (Python)", {
        "graph/": sorted((t / "graph").glob("*.py")),
        "agents/": sorted((t / "agents").rglob("*.py")),
        "dataflows/": sorted((t / "dataflows").glob("*.py")),
        "llm_clients/": sorted((t / "llm_clients").glob("*.py")),
        "reporting.py + default_config.py": [t / "reporting.py", t / "default_config.py"],
        "cli/": sorted((ta / "cli").glob("*.py")),
        "tests/": sorted((ta / "tests").glob("*.py")),
    })
    o = ours / "ta_cascade"
    report("ta_cascade (Python)", {
        "driver (pipeline, sessions, state, journal, config, cli)": [
            o / f for f in ("pipeline.py", "sessions.py", "state.py", "journal.py", "config.py", "cli.py", "__main__.py", "__init__.py")],
        "memory.py + report.py": [o / "memory.py", o / "report.py"],
        "data.py": [o / "data.py"],
        "tools.py": [o / "tools.py"],
        ".jaato/scripts (gates + prefetch)": sorted((ours / ".jaato/scripts").rglob("*.py")),
        "run_cascade.py": [ours / "run_cascade.py"],
        "tests/": sorted((ours / "tests").glob("*.py")),
    })
    print("\n== ta_cascade model-facing and config material outside Python")
    for label, sub, pat in (("personas", ".jaato/agents", "*.md"), ("base instructions", ".jaato/instructions", "*.md"),
                            ("completion schemas", ".jaato/completion_schemas", "*.json"), ("profiles", ".jaato/profiles", "*.yaml")):
        n, l = nonpy_lines(ours / sub, pat)
        print(f"  {label:24s} files={n:3d} lines={l}")
    print("\n== runtime dependencies")
    for label, p in (("TradingAgents", ta), ("ta_cascade", ours)):
        d = deps(p / "pyproject.toml")
        print(f"  {label:14s} {len(d):2d}: {', '.join(d)}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    main(Path(sys.argv[1]), Path(sys.argv[2]))
