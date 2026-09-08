"""Market-data layer: prices, indicators, statements, news, macro series.

Own implementation over ``yfinance`` (prices, statements, news, insiders)
and the FRED REST API (macro series).  Two rules every function keeps:

1. **Nothing after the as-of date.**  Every call takes the date the analysis
   is "as of" and refuses bars, filings or articles after it, so a backtest
   never reads the future.  Where a source cannot be pinned (a ticker's
   current ``info`` block) the text says so.
2. **Unavailable is a sentence, not a guess.**  Any failure returns a string
   starting with :data:`UNAVAILABLE` that tells the model the data is missing
   and not to invent it.  The model reads tool output as prose, so the
   instruction travels with the data.

Everything returns ``str`` — that is what a host tool hands back.
"""
from __future__ import annotations

import datetime as dt
import json
import os
from typing import Dict, Iterable, List, Optional, Tuple

UNAVAILABLE = "DATA_UNAVAILABLE"


def with_deadline(seconds: float, fn, *args, **kwargs) -> str:
    """Run ``fn`` in a worker thread; on timeout return an UNAVAILABLE sentence.

    yfinance and requests can stall on a broken network for far longer than
    a session bootstrap or a tool call may take.  The worker is left to
    finish on its own (threads cannot be killed); the caller gets its answer
    on time either way.
    """
    import concurrent.futures as cf
    ex = cf.ThreadPoolExecutor(max_workers=1)
    fut = ex.submit(fn, *args, **kwargs)
    try:
        return fut.result(timeout=seconds)
    except cf.TimeoutError:
        return (f"{UNAVAILABLE}: {getattr(fn, '__name__', 'fetch')} did not answer within "
                f"{seconds:.0f}s. Do not estimate or invent these values.")
    except Exception as exc:  # noqa: BLE001
        return _unavailable(getattr(fn, "__name__", "fetch"), exc)
    finally:
        ex.shutdown(wait=False)

INDICATOR_CATALOG: Dict[str, str] = {
    "sma_20": "20-day simple moving average — short-term trend.",
    "sma_50": "50-day simple moving average — medium-term trend.",
    "sma_200": "200-day simple moving average — long-term trend and support/resistance.",
    "ema_10": "10-day exponential moving average — reacts quickly to recent price.",
    "rsi_14": "14-day relative strength index — above 70 overbought, below 30 oversold.",
    "macd": "MACD line (EMA12 - EMA26) — momentum.",
    "macd_signal": "9-day EMA of the MACD line — crossovers signal momentum shifts.",
    "macd_hist": "MACD minus its signal — momentum acceleration.",
    "bb_mid": "20-day Bollinger midline (SMA 20).",
    "bb_upper": "Upper Bollinger band (midline + 2 standard deviations).",
    "bb_lower": "Lower Bollinger band (midline - 2 standard deviations).",
    "atr_14": "14-day average true range — volatility in price units.",
    "vwma_20": "20-day volume-weighted moving average — trend confirmed by volume.",
}

MACRO_SERIES: Dict[str, str] = {
    "cpi": "CPIAUCSL", "core_cpi": "CPILFESL", "pce": "PCEPI",
    "fed_funds": "FEDFUNDS", "unemployment": "UNRATE", "initial_claims": "ICSA",
    "gdp": "GDPC1", "industrial_production": "INDPRO", "retail_sales": "RSAFS",
    "consumer_sentiment": "UMCSENT", "ten_year": "DGS10", "two_year": "DGS2",
    "yield_curve": "T10Y2Y", "vix": "VIXCLS", "m2": "M2SL",
    "dollar_index": "DTWEXBGS", "oil": "DCOILWTICO",
}


# ---------------------------------------------------------------- helpers

def _date(s: str) -> dt.date:
    return dt.date.fromisoformat(str(s)[:10])


def _unavailable(what: str, exc: BaseException) -> str:
    return (
        f"{UNAVAILABLE}: {what} could not be retrieved "
        f"({type(exc).__name__}: {exc}). Do not estimate or invent these "
        f"values; state that the data was unavailable."
    )


def _ticker(symbol: str):
    import yfinance as yf  # imported lazily: the driver's tests never need it
    return yf.Ticker(symbol)


def _history(symbol: str, start: dt.date, end: dt.date):
    """Daily OHLCV bars in ``[start, end]`` inclusive, index tz-naive dates."""
    import pandas as pd

    df = _ticker(symbol).history(
        start=start.isoformat(), end=(end + dt.timedelta(days=1)).isoformat(),
        auto_adjust=False,
    )
    if df is None or df.empty:
        raise LookupError(f"no bars for {symbol} between {start} and {end}")
    idx = pd.to_datetime(df.index)
    if getattr(idx, "tz", None) is not None:
        idx = idx.tz_localize(None)
    df.index = idx.normalize()
    df = df[df.index.date <= end]
    if df.empty:
        raise LookupError(f"no bars for {symbol} on or before {end}")
    return df[["Open", "High", "Low", "Close", "Volume"]]


# ---------------------------------------------------------------- prices

def ohlcv(symbol: str, start_date: str, end_date: str, as_of: str) -> str:
    """Daily bars as CSV, ``end_date`` clamped to ``as_of``."""
    try:
        start, end = _date(start_date), min(_date(end_date), _date(as_of))
        df = _history(symbol, start, end)
        head = f"# {symbol} daily OHLCV, {df.index[0].date()} to {df.index[-1].date()}, {len(df)} bars\n"
        return head + df.round(4).to_csv(index_label="Date")
    except Exception as exc:  # noqa: BLE001 — every failure becomes a sentence
        return _unavailable(f"price history for {symbol}", exc)


def compute_indicators(df):
    """Add the :data:`INDICATOR_CATALOG` columns to an OHLCV frame (pure pandas)."""
    out = df.copy()
    close, high, low, vol = out["Close"], out["High"], out["Low"], out["Volume"]
    for n in (20, 50, 200):
        out[f"sma_{n}"] = close.rolling(n).mean()
    out["ema_10"] = close.ewm(span=10, adjust=False).mean()
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    rs = gain / loss.replace(0, float("nan"))
    out["rsi_14"] = 100 - 100 / (1 + rs)
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    out["macd"] = ema12 - ema26
    out["macd_signal"] = out["macd"].ewm(span=9, adjust=False).mean()
    out["macd_hist"] = out["macd"] - out["macd_signal"]
    mid = close.rolling(20).mean()
    sd = close.rolling(20).std()
    out["bb_mid"], out["bb_upper"], out["bb_lower"] = mid, mid + 2 * sd, mid - 2 * sd
    prev_close = close.shift(1)
    tr = (high - low).to_frame("hl").join((high - prev_close).abs().rename("hc")) \
        .join((low - prev_close).abs().rename("lc")).max(axis=1)
    out["atr_14"] = tr.ewm(alpha=1 / 14, adjust=False).mean()
    out["vwma_20"] = (close * vol).rolling(20).sum() / vol.rolling(20).sum()
    return out


def indicators(symbol: str, names: Iterable[str], as_of: str, lookback_days: int = 30) -> str:
    """Selected indicator columns for the last ``lookback_days`` bars up to ``as_of``."""
    names = [n.strip().lower() for n in names if n.strip()]
    unknown = [n for n in names if n not in INDICATOR_CATALOG]
    if unknown:
        return (f"{UNAVAILABLE}: unknown indicator(s) {unknown}. "
                f"Available: {', '.join(INDICATOR_CATALOG)}.")
    try:
        end = _date(as_of)
        df = compute_indicators(_history(symbol, end - dt.timedelta(days=420), end))
        tail = df[names].tail(int(lookback_days)).round(4)
        legend = "\n".join(f"# {n}: {INDICATOR_CATALOG[n]}" for n in names)
        return f"{legend}\n" + tail.to_csv(index_label="Date")
    except Exception as exc:  # noqa: BLE001
        return _unavailable(f"indicators for {symbol}", exc)


def snapshot(symbol: str, as_of: str, lookback_days: int = 30) -> str:
    """The verified numbers a report may quote: last close, range, change, key levels."""
    try:
        end = _date(as_of)
        df = compute_indicators(_history(symbol, end - dt.timedelta(days=420), end))
        recent = df.tail(int(lookback_days))
        last = df.iloc[-1]
        first_close = float(recent["Close"].iloc[0])
        facts = {
            "symbol": symbol,
            "as_of": end.isoformat(),
            "last_bar_date": df.index[-1].date().isoformat(),
            "last_close": round(float(last["Close"]), 4),
            f"high_{lookback_days}d": round(float(recent["High"].max()), 4),
            f"low_{lookback_days}d": round(float(recent["Low"].min()), 4),
            f"change_{lookback_days}d_pct": round((float(last["Close"]) / first_close - 1) * 100, 2),
            "sma_20": _r(last["sma_20"]), "sma_50": _r(last["sma_50"]), "sma_200": _r(last["sma_200"]),
            "rsi_14": _r(last["rsi_14"]), "atr_14": _r(last["atr_14"]),
            "avg_volume_20d": int(recent["Volume"].tail(20).mean()),
        }
        return ("VERIFIED MARKET SNAPSHOT — quote these numbers exactly; do not "
                "state other price levels as facts.\n" + json.dumps(facts, indent=1))
    except Exception as exc:  # noqa: BLE001
        return _unavailable(f"verified snapshot for {symbol}", exc)


def _r(v) -> Optional[float]:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if f != f else round(f, 4)  # NaN check


# ---------------------------------------------------------------- fundamentals

_INFO_KEYS = (
    "shortName", "sector", "industry", "marketCap", "enterpriseValue", "trailingPE",
    "forwardPE", "priceToBook", "enterpriseToEbitda", "profitMargins", "operatingMargins",
    "returnOnEquity", "revenueGrowth", "earningsGrowth", "debtToEquity", "currentRatio",
    "freeCashflow", "dividendYield", "beta", "sharesOutstanding",
)


def fundamentals(symbol: str, as_of: str) -> str:
    """Headline valuation and quality ratios from the ticker's info block.

    The info block is *current*, not point-in-time; the text says so, so a
    backtest reader can discount it.
    """
    try:
        info = _ticker(symbol).info or {}
        picked = {k: info.get(k) for k in _INFO_KEYS if info.get(k) is not None}
        if not picked:
            raise LookupError("empty info block")
        note = ("NOTE: these ratios are as reported today, not as of "
                f"{as_of}; treat them as approximate for historical analysis.\n")
        return note + json.dumps(picked, indent=1, default=str)
    except Exception as exc:  # noqa: BLE001
        return _unavailable(f"fundamentals for {symbol}", exc)


def statement(symbol: str, kind: str, freq: str, as_of: str) -> str:
    """A financial statement (``balance_sheet`` / ``cashflow`` / ``income``), periods ending on or before ``as_of``."""
    attr = {"balance_sheet": "balance_sheet", "cashflow": "cashflow", "income": "financials"}.get(kind)
    if attr is None:
        return f"{UNAVAILABLE}: unknown statement kind {kind!r}; use balance_sheet, cashflow or income."
    if freq == "quarterly":
        attr = "quarterly_" + attr
    try:
        import pandas as pd
        df = getattr(_ticker(symbol), attr)
        if df is None or df.empty:
            raise LookupError("empty statement")
        end = _date(as_of)
        keep = [c for c in df.columns if pd.Timestamp(c).date() <= end]
        if not keep:
            raise LookupError(f"no periods ending on or before {end}")
        df = df[keep]
        note = ("NOTE: periods are selected by period-end date; a statement is "
                "normally filed weeks after its period ends.\n")
        return note + df.to_csv()
    except Exception as exc:  # noqa: BLE001
        return _unavailable(f"{freq} {kind} statement for {symbol}", exc)


def insider_transactions(symbol: str, as_of: str, limit: int = 20) -> str:
    try:
        import pandas as pd
        df = _ticker(symbol).insider_transactions
        if df is None or df.empty:
            raise LookupError("no insider transactions reported")
        col = next((c for c in df.columns if "date" in str(c).lower()), None)
        if col is not None:
            df = df[pd.to_datetime(df[col]).dt.date <= _date(as_of)]
        return df.head(limit).to_csv(index=False)
    except Exception as exc:  # noqa: BLE001
        return _unavailable(f"insider transactions for {symbol}", exc)


# ---------------------------------------------------------------- news

def _news_items(raw: List[dict]) -> List[Tuple[dt.datetime, str, str, str]]:
    """Normalise yfinance's two news shapes into (published, title, source, summary)."""
    items = []
    for it in raw or []:
        c = it.get("content") if isinstance(it.get("content"), dict) else it
        title = c.get("title") or ""
        when = c.get("pubDate") or c.get("providerPublishTime")
        if isinstance(when, (int, float)):
            published = dt.datetime.fromtimestamp(when, dt.timezone.utc)
        elif isinstance(when, str):
            published = dt.datetime.fromisoformat(when.replace("Z", "+00:00"))
        else:
            continue
        prov = c.get("provider")
        source = prov.get("displayName") if isinstance(prov, dict) else (c.get("publisher") or "")
        items.append((published, title, source or "", c.get("summary") or ""))
    return sorted(items, reverse=True)


def _format_news(items, start: dt.date, end: dt.date, limit: int) -> str:
    kept = [i for i in items if start <= i[0].date() <= end][:limit]
    if not kept:
        return (f"{UNAVAILABLE}: no articles dated between {start} and {end} were "
                f"returned. Do not invent headlines.")
    lines = [f"- [{p.date()}] {t} ({s})" + (f"\n  {summ[:400]}" if summ else "")
             for p, t, s, summ in kept]
    return f"# {len(kept)} articles, {start} to {end}\n" + "\n".join(lines)


def news(symbol: str, start_date: str, end_date: str, as_of: str, limit: int = 20) -> str:
    try:
        start, end = _date(start_date), min(_date(end_date), _date(as_of))
        return _format_news(_news_items(_ticker(symbol).news), start, end, limit)
    except Exception as exc:  # noqa: BLE001
        return _unavailable(f"news for {symbol}", exc)


def global_news(as_of: str, lookback_days: int = 7, limit: int = 10) -> str:
    """Market-wide headlines: the news feeds of broad index and rates proxies."""
    try:
        end = _date(as_of)
        start = end - dt.timedelta(days=int(lookback_days))
        items = []
        for proxy in ("SPY", "QQQ", "TLT", "GLD", "USO"):
            try:
                items.extend(_news_items(_ticker(proxy).news))
            except Exception:  # noqa: BLE001 — one proxy failing is not the answer
                continue
        seen, uniq = set(), []
        for it in sorted(items, reverse=True):
            if it[1] not in seen:
                seen.add(it[1]); uniq.append(it)
        return _format_news(uniq, start, end, limit)
    except Exception as exc:  # noqa: BLE001
        return _unavailable("global news", exc)


# ---------------------------------------------------------------- macro (FRED)

def macro(series: str, as_of: str, lookback_days: int = 180) -> str:
    """A FRED series as observed on ``as_of`` (vintage-pinned), needs ``FRED_API_KEY``."""
    key = os.environ.get("FRED_API_KEY")
    sid = MACRO_SERIES.get(series.strip().lower(), series.strip().upper())
    if not key:
        return (f"{UNAVAILABLE}: FRED_API_KEY is not set, so {sid} cannot be fetched. "
                f"Say macro data was unavailable.")
    try:
        import requests
        end = _date(as_of)
        start = end - dt.timedelta(days=int(lookback_days))
        resp = requests.get(
            "https://api.stlouisfed.org/fred/series/observations",
            params={
                "series_id": sid, "api_key": key, "file_type": "json",
                "observation_start": start.isoformat(), "observation_end": end.isoformat(),
                "realtime_start": end.isoformat(), "realtime_end": end.isoformat(),
            },
            timeout=20,
        )
        resp.raise_for_status()
        obs = [(o["date"], o["value"]) for o in resp.json().get("observations", []) if o.get("value") != "."]
        if not obs:
            raise LookupError("no observations in window")
        lines = "\n".join(f"{d},{v}" for d, v in obs)
        return (f"# FRED {sid} ({series}), as known on {end} (vintage-pinned), "
                f"{start} to {end}\ndate,value\n{lines}")
    except Exception as exc:  # noqa: BLE001
        return _unavailable(f"FRED series {sid}", exc)


# ---------------------------------------------------------------- instrument / outcomes

def instrument_context(symbol: str, asset_type: str) -> str:
    """A one-line deterministic identity for the persona: name, sector, exchange."""
    try:
        info = _ticker(symbol).info or {}
        name = info.get("longName") or info.get("shortName")
        bits = [b for b in (info.get("sector"), info.get("industry"), info.get("exchange")) if b]
        if name:
            return f"{symbol} — {name}" + (f" ({', '.join(bits)})" if bits else "") + f"; asset type: {asset_type}"
    except Exception:  # noqa: BLE001 — identity falls back to the symbol
        pass
    return f"{symbol}; asset type: {asset_type}"


def return_after(symbol: str, trade_date: str, holding_days: int) -> Optional[Tuple[float, str]]:
    """``(return, resolution_date)`` over ``holding_days`` bars after ``trade_date``, or ``None`` if not enough bars yet."""
    try:
        start = _date(trade_date)
        df = _history(symbol, start, start + dt.timedelta(days=holding_days * 3 + 10))
    except Exception:  # noqa: BLE001
        return None
    df = df[df.index.date >= start]
    if len(df) <= holding_days:
        return None
    first, last = float(df["Close"].iloc[0]), float(df["Close"].iloc[holding_days])
    return last / first - 1, df.index[holding_days].date().isoformat()


# ---------------------------------------------------------------- social (StockTwits, Reddit)

_UA = "ta-cascade/0.1 (+https://github.com/Jaato-framework-and-examples/jaato-cascade-TradingAgents-reimplement)"
_FEED_CAP_BYTES = 5 * 1024 * 1024
_QUOTE_SUFFIXES = ("USD", "USDT", "USDC", "EUR", "GBP", "BTC", "ETH")
DEFAULT_SUBREDDITS = ("wallstreetbets", "stocks", "investing")


def crypto_base(symbol: str) -> Optional[str]:
    """``BTC`` for a crypto pair written as ``BTC-USD``; ``None`` for anything else."""
    s = symbol.strip().upper()
    if "-" in s:
        base, _, quote = s.rpartition("-")
        if base and quote in _QUOTE_SUFFIXES:
            return base
    return None


def _in_window(when: Optional[dt.datetime], start: dt.date, end: dt.date) -> bool:
    """Look-ahead safe: an undated item is never inside a historical window."""
    return when is not None and start <= when.date() <= end


def _iso(raw) -> Optional[dt.datetime]:
    try:
        return dt.datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _get(url: str, *, timeout: float, accept: str = "*/*", params=None):
    """One bounded GET: identified User-Agent, size cap, raised on HTTP errors."""
    import requests
    resp = requests.get(url, params=params, timeout=timeout, stream=True,
                        headers={"User-Agent": _UA, "Accept": accept})
    resp.raise_for_status()
    body = resp.raw.read(_FEED_CAP_BYTES + 1, decode_content=True)
    if len(body) > _FEED_CAP_BYTES:
        raise ValueError(f"response exceeded {_FEED_CAP_BYTES} bytes")
    return body


def stocktwits_messages(symbol: str, start_date: str, end_date: str, as_of: str,
                        limit: int = 30, timeout: float = 10.0) -> str:
    """Recent StockTwits messages for ``symbol`` inside the window, with a bull/bear tally.

    The public symbol stream needs no key but serves only recent messages, so
    a historical window is usually empty; that case is reported as such and
    kept distinct from a failed fetch, which is reported as unavailable.
    """
    base = crypto_base(symbol)
    st_symbol = f"{base}.X" if base else symbol.strip().upper()
    try:
        raw = _get(f"https://api.stocktwits.com/api/2/streams/symbol/{st_symbol}.json",
                   timeout=timeout, accept="application/json", params={"limit": limit})
        payload = json.loads(raw)
    except Exception as exc:  # noqa: BLE001
        return _unavailable(f"StockTwits stream for {st_symbol}", exc)
    start, end = _date(start_date), min(_date(end_date), _date(as_of))
    msgs = [m for m in (payload.get("messages") or []) if _in_window(_iso(m.get("created_at")), start, end)]
    if not msgs:
        return (f"NO_DATA: no StockTwits messages for {st_symbol} dated {start}..{end} "
                f"(the public stream serves recent messages only). This is an absence "
                f"of in-window messages, not a failed fetch.")
    tally = {"Bullish": 0, "Bearish": 0, "unlabelled": 0}
    lines = []
    for m in msgs[:limit]:
        label = ((m.get("entities") or {}).get("sentiment") or {}).get("basic")
        key = label if label in ("Bullish", "Bearish") else "unlabelled"
        tally[key] += 1
        body = " ".join(str(m.get("body") or "").split())[:280]
        user = (m.get("user") or {}).get("username", "?")
        lines.append(f"[{str(m.get('created_at', ''))[:10]} @{user} {key}] {body}")
    total = sum(tally.values())
    head = (f"# StockTwits {st_symbol}: {total} messages {start}..{end} — "
            f"Bullish {tally['Bullish']} ({tally['Bullish'] * 100 // total}%), "
            f"Bearish {tally['Bearish']} ({tally['Bearish'] * 100 // total}%), "
            f"unlabelled {tally['unlabelled']}")
    return head + "\n" + "\n".join(lines)


def _strip_html(content: str) -> str:
    import html
    import re
    if "<!-- SC_OFF -->" in content and "<!-- SC_ON -->" in content:
        content = content.split("<!-- SC_OFF -->", 1)[1].split("<!-- SC_ON -->", 1)[0]
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", content)).split())


def _reddit_feed(symbol_query: str, sub: str, limit: int, timeout: float,
                 retry_wait_cap: float) -> Optional[List[Dict[str, Any]]]:
    """Parse one subreddit's Atom search feed. ``None`` means the fetch failed;
    ``[]`` means it ran and matched nothing — the two must stay distinct."""
    import time
    import xml.etree.ElementTree as ET
    import requests
    url = f"https://www.reddit.com/r/{sub}/search.rss"
    params = {"q": symbol_query, "restrict_sr": "on", "sort": "new", "t": "week", "limit": limit}
    for attempt in (1, 2):
        try:
            raw = _get(url, timeout=timeout, accept="application/atom+xml", params=params)
            break
        except requests.HTTPError as exc:
            resp = getattr(exc, "response", None)
            if attempt == 1 and resp is not None and resp.status_code == 429:
                try:
                    wait = min(float(resp.headers.get("Retry-After", "0") or 0), retry_wait_cap)
                except ValueError:
                    wait = 0.0
                if wait > retry_wait_cap:
                    return None
                time.sleep(wait)
                continue
            return None
        except Exception:  # noqa: BLE001
            return None
    else:
        return None
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return None
    ns = {"a": "http://www.w3.org/2005/Atom"}
    posts = []
    for entry in root.findall("a:entry", ns)[:limit]:
        title = entry.findtext("a:title", default="", namespaces=ns) or ""
        published = _iso(entry.findtext("a:published", default=None, namespaces=ns))
        content = entry.findtext("a:content", default="", namespaces=ns) or ""
        posts.append({"title": " ".join(title.split()), "published": published,
                      "excerpt": _strip_html(content)[:240]})
    return posts


def reddit_posts(symbol: str, start_date: str, end_date: str, as_of: str,
                 subreddits: Iterable[str] = DEFAULT_SUBREDDITS, limit_per_sub: int = 5,
                 timeout: float = 10.0, retry_wait_cap: float = 5.0) -> str:
    """Posts mentioning ``symbol`` across finance subreddits, inside the window.

    Keyless, via each subreddit's public Atom search feed (the JSON search
    endpoint is blocked for anonymous clients).  A subreddit whose fetch
    failed is reported as unavailable — never as "no posts", which would
    assert a silence nobody observed.  A 429 is retried once after a short
    wait; anything longer is treated as a failed fetch, because this runs
    under a session-prep deadline where a minute's sleep is a failed session.
    """
    query = crypto_base(symbol) or symbol.strip().upper()
    start, end = _date(start_date), min(_date(end_date), _date(as_of))
    blocks, failed, found = [], [], 0
    for sub in subreddits:
        posts = _reddit_feed(query, sub, limit_per_sub, timeout, retry_wait_cap)
        if posts is None:
            failed.append(sub)
            blocks.append(f"r/{sub}: {UNAVAILABLE} (fetch failed — not an absence of posts)")
            continue
        posts = [p for p in posts if _in_window(p["published"], start, end)]
        if not posts:
            blocks.append(f"r/{sub}: no posts mentioning {query} dated {start}..{end}")
            continue
        found += len(posts)
        lines = [f"r/{sub}: {len(posts)} posts mentioning {query} (RSS: no scores or comment counts)"]
        for p in posts:
            lines.append(f"  [{p['published'].date()}] {p['title']}"
                         + (f"\n    {p['excerpt']}" if p["excerpt"] else ""))
        blocks.append("\n".join(lines))
    if failed and len(failed) == len(list(subreddits)):
        return (f"{UNAVAILABLE}: every Reddit source failed ({', '.join('r/' + s for s in failed)}); "
                f"this is not an absence of discussion. Do not infer sentiment from it.")
    head = f"# Reddit {query}: {found} in-window posts across {', '.join('r/' + s for s in subreddits)}"
    return head + "\n" + "\n\n".join(blocks)


def gather_with_deadline(seconds: float, jobs: Dict[str, Tuple]) -> Dict[str, str]:
    """Run ``{name: (fn, *args)}`` concurrently; each result is a string, and
    a job still running at the deadline yields an UNAVAILABLE sentence."""
    import concurrent.futures as cf
    ex = cf.ThreadPoolExecutor(max_workers=max(1, len(jobs)))
    futures = {name: ex.submit(job[0], *job[1:]) for name, job in jobs.items()}
    out: Dict[str, str] = {}
    try:
        for name, fut in futures.items():
            try:
                out[name] = fut.result(timeout=seconds)
            except cf.TimeoutError:
                out[name] = (f"{UNAVAILABLE}: {name} did not answer within {seconds:.0f}s. "
                             f"Do not estimate or invent these values.")
            except Exception as exc:  # noqa: BLE001
                out[name] = _unavailable(name, exc)
    finally:
        ex.shutdown(wait=False)
    return out
