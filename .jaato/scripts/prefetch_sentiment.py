"""Persona prefetch for the sentiment analyst: the crowd's material for the
week before the analysis date, collected deterministically before the
model's first turn.

Four sources — company news, market news, StockTwits, Reddit — fetched
concurrently under ONE deadline, because this runs at session-prep and a
slow prefetch is a failed session, not a slow one.  It never raises: a
failure becomes a DATA_UNAVAILABLE sentence inside its block, and the
placeholder is the optional form (``{{!py?:``), so even an import failure
leaves the persona usable.  ``TA_CASCADE_PREFETCH=off`` in the session env
skips the fetch entirely (the echo set uses it).
"""
import datetime as dt

PREFETCH_BUDGET_S = 20.0


def render(context, args):
    env = getattr(context, "env", None) or {}
    if str(env.get("TA_CASCADE_PREFETCH", "on")).lower() in ("off", "0", "false", "no"):
        return ("DATA_UNAVAILABLE: pre-fetch is switched off for this session "
                "(TA_CASCADE_PREFETCH=off). Say the material was not collected.")
    params = getattr(context, "agent_params", None) or {}
    ticker = params.get("ticker")
    as_of = params.get("trade_date")
    if not ticker or not as_of:
        return "DATA_UNAVAILABLE: ticker or trade_date was not supplied to the prefetch."
    try:
        from ta_cascade import data
    except Exception as exc:  # noqa: BLE001
        return f"DATA_UNAVAILABLE: the data layer could not be imported ({exc})."
    start = (dt.date.fromisoformat(as_of) - dt.timedelta(days=7)).isoformat()
    got = data.gather_with_deadline(PREFETCH_BUDGET_S, {
        "company_news": (data.news, ticker, start, as_of, as_of, 25),
        "market_news": (data.global_news, as_of, 7, 10),
        "stocktwits": (data.stocktwits_messages, ticker, start, as_of, as_of, 30),
        "reddit": (data.reddit_posts, ticker, start, as_of, as_of),
    })
    window = f'window="{start}..{as_of}"'
    return "\n\n".join(
        f'<{name} symbol="{ticker}" {window}>\n{got[name]}\n</{name}>'
        for name in ("company_news", "market_news", "stocktwits", "reddit")
    )
