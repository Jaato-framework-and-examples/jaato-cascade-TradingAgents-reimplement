"""Completion gate for the trader and the portfolio manager.

Price fields are absolute levels or null.  A percentage smuggled in as a
number (a stop of 15 on an instrument trading at 600) is the classic error,
so every price must be positive and, for a Buy, the stop must sit below the
entry.  ``render`` writes the section.
"""


def _num(v):
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


def validate(payload, context):
    errors, warnings = [], []
    if payload.get("errors"):
        return {"errors": [], "faults": [], "warnings": [], "incomplete": []}
    for key in ("entry_price", "stop_loss", "price_target"):
        if key in payload and payload[key] is not None:
            v = _num(payload[key])
            if v is None or v <= 0:
                errors.append(f"{key} must be a positive absolute price or null; got {payload[key]!r}.")
    entry, stop = _num(payload.get("entry_price")), _num(payload.get("stop_loss"))
    if entry and stop:
        if payload.get("action") == "Buy" and stop >= entry:
            errors.append("For a Buy the stop_loss must be below the entry_price.")
        if payload.get("action") == "Sell" and stop <= entry:
            errors.append("For a Sell the stop_loss must be above the entry_price.")
        if stop < entry * 0.2 or stop > entry * 5:
            warnings.append("stop_loss is very far from entry_price; check it is a price, not a percentage.")
    if payload.get("action") == "Hold" and (entry or stop):
        warnings.append("A Hold normally carries no entry or stop; confirm they are intended.")
    return {"errors": errors, "faults": [], "warnings": warnings, "incomplete": []}


def render(payload, context):
    lines = []
    for k, v in payload.items():
        if k in ("errors", "warnings") or v in (None, "", []):
            continue
        lines.append(f"**{k.replace('_', ' ').title()}**: {v}\n")
    return "\n".join(lines) + "\n"
