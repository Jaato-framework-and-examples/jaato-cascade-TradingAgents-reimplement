"""StockTwits and Reddit fetchers against canned responses — no network."""
import json

import pytest
import requests

from ta_cascade import data

ST_PAYLOAD = {"messages": [
    {"created_at": "2026-01-14T15:00:00Z", "body": "Loading up before earnings", "user": {"username": "a"},
     "entities": {"sentiment": {"basic": "Bullish"}}},
    {"created_at": "2026-01-13T09:00:00Z", "body": "Overextended here", "user": {"username": "b"},
     "entities": {"sentiment": {"basic": "Bearish"}}},
    {"created_at": "2026-01-12T09:00:00Z", "body": "watching", "user": {"username": "c"}, "entities": {}},
    {"created_at": "2026-01-20T09:00:00Z", "body": "FUTURE — must be dropped", "user": {"username": "d"},
     "entities": {"sentiment": {"basic": "Bullish"}}},
    {"created_at": None, "body": "undated — must be dropped", "user": {"username": "e"}, "entities": {}},
]}

ATOM = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry><title>NVDA earnings thread</title><published>2026-01-14T10:00:00+00:00</published>
    <content type="html">&lt;!-- SC_OFF --&gt;&lt;div&gt;&lt;p&gt;Guidance looks &amp;amp; strong&lt;/p&gt;&lt;/div&gt;&lt;!-- SC_ON --&gt;</content></entry>
  <entry><title>Old thread</title><published>2025-12-01T10:00:00+00:00</published><content type="html"></content></entry>
  <entry><title>Future thread</title><published>2026-01-19T10:00:00+00:00</published><content type="html"></content></entry>
</feed>"""


def test_stocktwits_window_and_tally(monkeypatch):
    seen = {}

    def fake_get(url, **kw):
        seen["url"] = url
        return json.dumps(ST_PAYLOAD).encode()

    monkeypatch.setattr(data, "_get", fake_get)
    text = data.stocktwits_messages("BTC-USD", "2026-01-08", "2026-01-15", "2026-01-15")
    assert seen["url"].endswith("/streams/symbol/BTC.X.json")
    assert "3 messages" in text and "Bullish 1 (33%)" in text and "Bearish 1 (33%)" in text
    assert "FUTURE" not in text and "undated" not in text
    assert "[2026-01-14 @a Bullish] Loading up" in text


def test_stocktwits_empty_window_is_not_a_failure(monkeypatch):
    monkeypatch.setattr(data, "_get", lambda url, **kw: json.dumps(ST_PAYLOAD).encode())
    text = data.stocktwits_messages("NVDA", "2025-06-01", "2025-06-08", "2025-06-08")
    assert text.startswith("NO_DATA") and "not a failed fetch" in text


def test_stocktwits_failure_is_unavailable(monkeypatch):
    def boom(url, **kw):
        raise requests.ConnectionError("reset")

    monkeypatch.setattr(data, "_get", boom)
    text = data.stocktwits_messages("NVDA", "2026-01-08", "2026-01-15", "2026-01-15")
    assert text.startswith(data.UNAVAILABLE) and "ConnectionError" in text


def test_reddit_parse_window_and_html(monkeypatch):
    calls = []

    def fake_get(url, **kw):
        calls.append((url, kw.get("params", {}).get("q")))
        return ATOM.encode()

    monkeypatch.setattr(data, "_get", fake_get)
    text = data.reddit_posts("NVDA", "2026-01-08", "2026-01-15", "2026-01-15", subreddits=("stocks", "investing"))
    assert [c[1] for c in calls] == ["NVDA", "NVDA"] and "/r/stocks/search.rss" in calls[0][0]
    assert "2 in-window posts" in text
    assert "[2026-01-14] NVDA earnings thread" in text and "Guidance looks & strong" in text
    assert "Old thread" not in text and "Future thread" not in text


def test_reddit_failed_source_is_unavailable_not_silence(monkeypatch):
    def fake_get(url, **kw):
        if "/r/stocks/" in url:
            raise requests.ConnectionError("blocked")
        return ATOM.encode()

    monkeypatch.setattr(data, "_get", fake_get)
    text = data.reddit_posts("NVDA", "2026-01-08", "2026-01-15", "2026-01-15", subreddits=("stocks", "investing"))
    assert "r/stocks: DATA_UNAVAILABLE (fetch failed" in text and "r/investing: 1 posts" in text

    monkeypatch.setattr(data, "_get", lambda url, **kw: (_ for _ in ()).throw(requests.ConnectionError("x")))
    text = data.reddit_posts("NVDA", "2026-01-08", "2026-01-15", "2026-01-15", subreddits=("stocks",))
    assert text.startswith(data.UNAVAILABLE) and "not an absence of discussion" in text


def test_reddit_429_retries_once_within_cap(monkeypatch):
    attempts = []

    def fake_get(url, **kw):
        attempts.append(url)
        if len(attempts) == 1:
            resp = requests.Response(); resp.status_code = 429; resp.headers["Retry-After"] = "0"
            raise requests.HTTPError(response=resp)
        return ATOM.encode()

    monkeypatch.setattr(data, "_get", fake_get)
    text = data.reddit_posts("NVDA", "2026-01-08", "2026-01-15", "2026-01-15", subreddits=("stocks",))
    assert len(attempts) == 2 and "1 in-window posts" in text


def test_gather_with_deadline_isolates_slow_and_broken_jobs():
    import time

    def slow():
        time.sleep(2); return "late"

    def broken():
        raise RuntimeError("nope")

    out = data.gather_with_deadline(0.3, {"fast": (lambda: "ok",), "slow": (slow,), "broken": (broken,)})
    assert out["fast"] == "ok"
    assert out["slow"].startswith(data.UNAVAILABLE) and out["broken"].startswith(data.UNAVAILABLE)


def test_crypto_base():
    assert data.crypto_base("BTC-USD") == "BTC" and data.crypto_base("eth-usdt") == "ETH"
    assert data.crypto_base("NVDA") is None and data.crypto_base("BRK-B") is None
