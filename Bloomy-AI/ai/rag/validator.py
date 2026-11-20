"""Enforce catalog grounding and backend-compatible plan invariants."""
from datetime import date


def validate_result(result, request, catalog):
    lookup = {item["id"]: item for item in catalog}
    if result.status != "draft" or len(result.days) != 20:
        raise ValueError("a recommendation must be a 20-day draft")
    previous = None
    evidence_ids = {e["content_id"] for e in result.evidence}
    for day in result.days:
        item = lookup.get(day["content_id"])
        current = date.fromisoformat(day["date"])
        if current.weekday() >= 5 or (previous and current <= previous) or current < date.fromisoformat(request.start_date):
            raise ValueError("invalid plan calendar")
        previous = current
        if item is None or item["id"] not in evidence_ids:
            raise ValueError("ungrounded content_id")
        if not (item["age_min"] <= request.age <= item["age_max"] and item["level"] == request.base_level):
            raise ValueError("content violates age or level constraint")
        if not 5 <= day["minutes"] <= request.session_minutes or day["minutes"] != item["session_minutes"]:
            raise ValueError("invalid duration")
        if day["task"] != item["task"] or day["check_point"] != item["check_point"]:
            raise ValueError("ungrounded instructions")
    return result
