"""Calendar-based, reproducible response summaries; no diagnostic inference."""
from collections import defaultdict
from datetime import date, timedelta


def summarize(records, as_of):
    anchor = date.fromisoformat(as_of)
    active = [row for row in records if not row["rest_day"]]

    def window(start, end):
        rows = [r for r in active if start <= date.fromisoformat(r["date"]) <= end]
        return {"record_days": len(rows), **{
            "avg_" + key: round(sum(r[key] for r in rows) / len(rows), 3) if rows else None
            for key in ("interest", "comprehension", "satisfaction")}}

    current = window(anchor - timedelta(days=6), anchor)
    previous = window(anchor - timedelta(days=13), anchor - timedelta(days=7))
    by_date = {r["date"]: r for r in records}

    def streak(predicate):
        count, day = 0, anchor
        while True:
            row = by_date.get(day.isoformat())
            if not row or row["rest_day"] or not predicate(row):
                return count
            count, day = count + 1, day - timedelta(days=1)

    groups = defaultdict(list)
    durations = defaultdict(list)
    for row in active:
        if row.get("content_id"):
            groups[row["content_id"]].append(row)
        if row.get("minutes"):
            durations[row["minutes"]].append(row)
    content = []
    for content_id, rows in sorted(groups.items()):
        content.append({"content_id": content_id, "observations": len(rows),
                        "avg_interest": round(sum(r["interest"] for r in rows) / len(rows), 3),
                        "avg_comprehension": round(sum(r["comprehension"] for r in rows) / len(rows), 3)})
    return {
        "as_of": as_of, "record_days": len(active), "rest_days": len(records) - len(active),
        "current_7_days": current, "previous_7_days": previous,
        "interest_change": round(current["avg_interest"] - previous["avg_interest"], 3)
            if current["avg_interest"] is not None and previous["avg_interest"] is not None else None,
        "comprehension_change": round(current["avg_comprehension"] - previous["avg_comprehension"], 3)
            if current["avg_comprehension"] is not None and previous["avg_comprehension"] is not None else None,
        "learning_streak": streak(lambda r: True),
        "low_interest_streak": streak(lambda r: r["interest"] <= 2),
        "low_comprehension_streak": streak(lambda r: r["comprehension"] <= 2),
        "content_responses": content,
        "preferred_content_ids": [r["content_id"] for r in content if r["observations"] >= 2 and r["avg_interest"] >= 4],
        "weak_content_ids": [r["content_id"] for r in content if r["observations"] >= 2 and r["avg_comprehension"] <= 2],
        "duration_responses": [{"minutes": minutes, "observations": len(rows),
                                "avg_interest": round(sum(r["interest"] for r in rows) / len(rows), 3)}
                               for minutes, rows in sorted(durations.items())],
    }
