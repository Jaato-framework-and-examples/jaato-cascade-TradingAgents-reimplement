"""Every pilot arm's evidence through Jev, scored with the pilot's ruler, beside the panel's vote."""
import json, glob, subprocess, time, collections, sys
import requests
from ta_cascade import data, score
KEY = subprocess.run(["pass", "show", "jaato/typesafe/api-key"], capture_output=True, text=True).stdout.splitlines()[0].strip()
QUESTIONS = json.load(open(sys.argv[1])); OUT = sys.argv[2]
DIR = score.DIRECTION
def ask(state):
    for attempt in range(6):
        r = requests.post("https://api.typesafe.ai/v1/systemone", headers={"Authorization": f"Bearer {KEY}"},
                          json={"state": state, "model": "jev-latest", "questions": QUESTIONS}, timeout=60)
        if r.status_code in (429, 529): time.sleep(2 ** attempt); continue
        r.raise_for_status(); return r.json()
    raise RuntimeError(f"gave up after retries: {r.status_code} {r.text[:200]}")
snapshots, bands, alphas = {}, {}, {}
rows = []
for ws in sorted(glob.glob("/tmp/pilot-ws/*")):
    st = glob.glob(f"{ws}/results/*/*/state.json")
    if not st: continue
    ticker, date = st[0].split("/")[-3:-1]; cell = f"{ticker}/{date}"
    if cell not in snapshots:
        snapshots[cell] = json.loads(data.snapshot(ticker, date, 120, max_stale_days=7).split("\n", 1)[1])
        bands[cell] = data.hold_band(ticker, date, 5)
        r = data.return_after(ticker, date, 5)[0]
        alphas[cell] = r if ticker == "SPY" else r - data.return_after("SPY", date, 5)[0]
    s = json.load(open(st[0])); m = s["reports"]["market"]
    state = {"ticker": ticker, "as_of": date, "snapshot": snapshots[cell],
             "market_report": {"stance": m["stance"], "confidence": m["confidence"], "text": m["report"]}}
    t0 = time.monotonic(); resp = ask(state); ms = (time.monotonic() - t0) * 1000
    a = resp["answers"]; rating = a["rating"]["choice"]
    rows.append({"cell": cell, "arm": ws.split("_")[-1], "model": resp.get("model"), "ms": round(ms),
                 "usage": resp.get("usage"), "pipeline_rating": s["portfolio_decision"]["rating"],
                 "jev_rating": rating, "jev_rating_p": a["rating"]["probabilities"], "jev_conf": a["rating"].get("confidence"),
                 "next_week": a["next_week_vs_index"]["choice"], "next_week_p": a["next_week_vs_index"]["probabilities"],
                 "trend_aligned": a["trend_aligned"]["noul"], "breakout_claimed": a["breakout_claimed"]["noul"],
                 "breakout_supported": a["breakout_supported"]["noul"], "momentum": a["momentum"]["score"],
                 "sharp_move": a["sharp_move_just_happened"]["noul"], "stance_warranted": a["stance_warranted"]["noul"],
                 "alpha": alphas[cell], "band": bands[cell],
                 "jev_right": score.grade(rating, alphas[cell], bands[cell]),
                 "pipeline_right": score.grade(s["portfolio_decision"]["rating"], alphas[cell], bands[cell])})
with open(OUT, "w") as f:
    for r in rows: f.write(json.dumps(r) + "\n")
tok = sum(r["usage"]["input_tokens"] for r in rows)
print(f"{len(rows)} arms; model {rows[0]['model']}; mean {sum(r['ms'] for r in rows)/len(rows):.0f} ms; {tok} input tokens ≈ ${tok*0.042/1e6:.4f}\n")
print(f"  {'cell':16} {'alpha':>7} {'band':>5}  {'Jev ratings (5 arms)':30} {'Jev maj':11} {'right':5}  {'panel maj':11} {'right':5}  next-week")
cells = collections.defaultdict(list)
for r in rows: cells[r["cell"]].append(r)
jm = pm = ja = pa = 0
for cell, rs in sorted(cells.items(), key=lambda kv: (kv[0].split('/')[1], kv[0])):
    a, band = rs[0]["alpha"], rs[0]["band"]
    def maj(ratings):
        d = collections.Counter(DIR[x] for x in ratings).most_common(1)[0][0]
        return {1: "bullish", 0: "Hold", -1: "bearish"}[d], (abs(a) <= band) if d == 0 else d * a > 0
    jl, jr = maj([r["jev_rating"] for r in rs]); pl, pr = maj([r["pipeline_rating"] for r in rs])
    jm += jr; pm += pr; ja += sum(r["jev_right"] for r in rs); pa += sum(r["pipeline_right"] for r in rs)
    nw = collections.Counter(r["next_week"] for r in rs).most_common(1)[0][0]
    print(f"  {cell:16} {a*100:+6.2f}% {band*100:4.1f}%  {str(dict(collections.Counter(r['jev_rating'] for r in rs))):30} {jl:11} {'yes' if jr else 'no':5}  {pl:11} {'yes' if pr else 'no':5}  {nw}")
print(f"\n  majorities right — Jev {jm}/12, panel {pm}/12;  arms right — Jev {ja}/60, panel {pa}/60")
dj = [r for r in rows if DIR[r["jev_rating"]] != 0]; dp = [r for r in rows if DIR[r["pipeline_rating"]] != 0]
print(f"  directional arms — Jev {sum(r['jev_right'] for r in dj)}/{len(dj)} right, panel {sum(r['pipeline_right'] for r in dp)}/{len(dp)} right")
print(f"  Jev rating distribution: {dict(collections.Counter(r['jev_rating'] for r in rows))}")
conf = [(r["jev_conf"], r["jev_right"]) for r in rows if r["jev_conf"] is not None]
hi = [ok for c, ok in conf if c >= 0.7]; lo = [ok for c, ok in conf if c < 0.7]
print(f"  calibration: confidence ≥0.7 right {sum(hi)}/{len(hi)}; <0.7 right {sum(lo)}/{len(lo)}")
