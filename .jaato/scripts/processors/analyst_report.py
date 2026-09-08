"""Completion gate for the four analysts.

``validate`` blocks a completion whose report is too thin to argue from or
whose author claims a stance without having touched the data it was given
tools for.  ``render`` writes the report section so the report tree fills in
as the run progresses.  Both are pure functions of the payload so the driver's
tests can call them without a session.
"""
MIN_REPORT_CHARS = 400


def validate(payload, context):
    errors, warnings = [], []
    report = str(payload.get("report", "")).strip()
    if payload.get("errors"):
        # The agent says it could not answer; let that stand rather than
        # forcing a report out of nothing.
        return {"errors": [], "faults": [], "warnings": [], "incomplete": []}
    if len(report) < MIN_REPORT_CHARS:
        errors.append(
            f"The report is {len(report)} characters; a researcher cannot argue from "
            f"that. Write at least {MIN_REPORT_CHARS} characters covering the points "
            f"your persona lists, then call signal_completion again."
        )
    tools_used = payload.get("tools_used") or []
    ledger = getattr(context, "tool_calls", None) or []
    called = {getattr(c, "name", None) or (c.get("name") if isinstance(c, dict) else None)
              for c in ledger}
    called.discard(None)
    if not tools_used and called - {"signal_completion"}:
        warnings.append("tools_used is empty although data tools were called; list them.")
    if "DATA_UNAVAILABLE" in report and not payload.get("warnings"):
        warnings.append("The report mentions unavailable data; record it in warnings.")
    return {"errors": errors, "faults": [], "warnings": warnings, "incomplete": []}


def render(payload, context):
    if payload.get("errors"):
        return "# No report\n\n" + "\n".join(f"- {e}" for e in payload["errors"]) + "\n"
    head = (f"**Stance**: {payload.get('stance')}  \n"
            f"**Confidence**: {payload.get('confidence')}  \n"
            f"**Tools used**: {', '.join(payload.get('tools_used') or []) or 'none'}\n\n")
    return head + str(payload.get("report", "")) + "\n"
