"""Translate team backend records into the independent AI contracts."""
import re

from ai.agent import CoachRequest, Feedback, LearningCard
from ai.contracts import RecommendationRequest
from ai.rag.ingest import validate_catalog

_SHARED_FIELDS = ("id", "title", "age_min", "age_max", "level", "skill", "type", "provider",
                  "link", "session_minutes", "expert_note", "trust_source")
_AI_FIELDS = ("task", "check_point", "learning_goal", "review_status")


def shared_catalog(rows, metadata):
    """Index only entries with an ID in both the backend snapshot and AI metadata."""
    entries = validate_catalog(list(metadata))
    rows_by_id = {}
    for raw in rows:
        row = dict(raw)
        content_id = row["id"]
        if content_id in rows_by_id:
            raise ValueError(f"duplicate backend content_id: {content_id}")
        rows_by_id[content_id] = row

    shared = []
    for entry in entries:
        row = rows_by_id.get(entry["id"])
        if row is None:
            continue
        differing = [key for key in _SHARED_FIELDS if row.get(key) != entry[key]]
        if differing:
            raise ValueError(f"catalog drift for {entry['id']}: {', '.join(differing)}")
        item = {key: row[key] for key in _SHARED_FIELDS}
        item.update({key: entry[key] for key in _AI_FIELDS if key in entry})
        shared.append(item)
    return validate_catalog(shared)


def _terms(value):
    if isinstance(value, str):
        value = re.split(r"[,;\n]", value)
    return tuple(part.strip() for part in (value or ()) if part.strip())


def recommendation_request(child, start_date, *, goal="듣기", exposure_months=None):
    return RecommendationRequest(
        age=child["age"], base_level=child["level"], start_date=start_date, goal=goal,
        session_minutes=child["session_length"], owned_materials=_terms(child.get("materials")),
        favorite_topics=_terms(child.get("favorite_topics")), exposure=child.get("exposure"),
        exposure_months=exposure_months,
    )


def _feedback(row, child_id):
    if row.get("child_id", child_id) != child_id:
        raise ValueError("feedback belongs to another child")
    rest_day = row.get("rest_day", False)
    if type(rest_day) not in (bool, int) or rest_day not in (0, 1):
        raise ValueError("rest_day must be boolean or integer 0/1")
    if rest_day:
        return Feedback(child_id, row["date"], rest_day=True)
    return Feedback(child_id, row["date"], row["completion"], row["satisfaction"],
                    row["interest"], row["comprehension"], row.get("memo") or "")


def coaching_request(child, feedback, *, catalog, plan_status="draft",
                     today=None, next_card=None, history=(), goal="듣기"):
    """Build a request from records already authorized by the backend."""
    child_id = child["id"]
    profile = recommendation_request(child, feedback["date"], goal=goal)
    known = {entry["id"]: entry for entry in catalog}

    def card(row):
        if row is None:
            return None
        if row.get("child_id", child_id) != child_id:
            raise ValueError("card belongs to another child")
        item = known.get(row.get("content_id"))
        if item is None or not item["age_min"] <= profile.age <= item["age_max"]:
            return None
        if row["minutes"] > profile.session_minutes:
            return None
        return LearningCard(child_id, row["date"], row["content_id"], row["task"],
                            row["minutes"], row["check_point"])

    current = _feedback(feedback, child_id)
    return CoachRequest(
        child_id, profile.age, profile.base_level, current, card(today), card(next_card),
        tuple(_feedback(row, child_id) for row in history), plan_status, profile.session_minutes,
        profile.goal, profile.owned_materials, profile.favorite_topics,
    )
