"""Persona prefetch for the sentiment analyst: news for the week before the
analysis date, collected deterministically before the model's first turn.

Runs inside the session's process at session-prep.  It never raises: a
failure becomes a DATA_UNAVAILABLE sentence in the persona, and the
placeholder is the optional form (``{{!py?:``), so even an import failure
leaves the persona usable.
"""
import datetime as dt


PREFETCH_BUDGET_S = 15.0


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
    company = data.with_deadline(PREFETCH_BUDGET_S, data.news, ticker, start, as_of, as_of, 25)
    market = data.with_deadline(PREFETCH_BUDGET_S, data.global_news, as_of, 7, 10)
    return (f"<company_news symbol=\"{ticker}\" window=\"{start}..{as_of}\">\n{company}\n</company_news>\n\n"
            f"<market_news window=\"{start}..{as_of}\">\n{market}\n</market_news>")
