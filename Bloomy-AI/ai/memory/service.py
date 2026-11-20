"""Identity-scoped memory, idempotent feedback, and transactional coach retries."""
from dataclasses import asdict, replace
from datetime import timedelta
import hashlib
import json

from ai.agent.contracts import Feedback, CoachResult, child_identity, iso_date
from .repository import MemoryConflictError
from .sqlite_store import SQLiteMemoryRepository
from .summary import summarize


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value):
    return hashlib.sha256(encode(value).encode("utf-8")).hexdigest()


class MemoryService:
    def __init__(self, repository):
        self.repository = repository

    @classmethod
    def from_sqlite(cls, path):
        return cls(SQLiteMemoryRepository(path))

    def close(self):
        self.repository.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def set_preferences(self, child_id, effective_date, *, favorite_topics=None, owned_materials=None):
        child_identity(child_id)
        iso_date(effective_date)
        values = {}
        for kind, entries in (("favorite_topics", favorite_topics), ("owned_materials", owned_materials)):
            if entries is not None:
                if not isinstance(entries, (tuple, list)) or len(entries) > 100 or any(
                    not isinstance(v, str) or not v.strip() or len(v) > 200 for v in entries
                ):
                    raise ValueError("preferences must contain at most 100 nonempty strings (max 200 characters)")
                values[kind] = encode(list(dict.fromkeys(v.strip() for v in entries)))
        with self.repository.transaction():
            if values:
                self.repository.set_preferences(child_id, effective_date, values)

    def get_context(self, child_id, as_of):
        child_identity(child_id)
        iso_date(as_of)
        # One transaction gives a consistent view of preferences and records.
        with self.repository.transaction():
            return self._context(child_id, as_of)

    def _context(self, child_id, as_of):
        records = []
        for row in self.repository.events(child_id, as_of):
            record = json.loads(row["feedback_json"])
            record.update(content_id=row["content_id"], minutes=row["minutes"])
            records.append(record)
        preferences = {"favorite_topics": [], "owned_materials": []}
        for row in self.repository.preferences(child_id, as_of):
            preferences[row["kind"]] = json.loads(row["value_json"])
        cutoff = (iso_date(as_of) - timedelta(days=6)).isoformat()
        return {"child_id": child_id, "as_of": as_of, "preferences": preferences,
                "history": records, "recent_history": [row for row in records if row["date"] >= cutoff],
                "summary": summarize(records, as_of)}

    def _row(self, feedback, event_id, content_id, minutes):
        if not isinstance(feedback, Feedback):
            raise ValueError("feedback must be Feedback")
        event_id = event_id if event_id is not None else f"feedback:{feedback.date}"
        if not isinstance(event_id, str) or not event_id.strip() or len(event_id) > 200:
            raise ValueError("event_id must be a nonempty string (max 200 characters)")
        if content_id is not None and (not isinstance(content_id, str) or not content_id.strip()):
            raise ValueError("invalid content_id")
        if minutes is not None and (type(minutes) is not int or not 5 <= minutes <= 20):
            raise ValueError("invalid session minutes")
        clean = {key: value for key, value in asdict(feedback).items() if key != "memo"}
        if feedback.rest_day:
            clean.update(completion=None, satisfaction=None, interest=None, comprehension=None)
            content_id, minutes = None, None
        fingerprint = {**clean, "memo": "" if feedback.rest_day else feedback.memo,
                       "content_id": content_id, "minutes": minutes}
        return {"child_id": feedback.child_id, "day": feedback.date, "event_id": event_id,
                "record_hash": digest(fingerprint), "feedback_json": encode(clean),
                "content_id": content_id, "minutes": minutes}

    def _existing(self, row):
        existing = self.repository.event(row["child_id"], row["day"])
        by_id = self.repository.event_by_id(row["child_id"], row["event_id"])
        if by_id and by_id["day"] != row["day"]:
            raise MemoryConflictError("event_id already belongs to another date")
        if existing and (existing["event_id"] != row["event_id"] or existing["record_hash"] != row["record_hash"]):
            raise MemoryConflictError("feedback date or event ID conflicts with stored input")
        return existing

    def record_feedback(self, feedback, *, event_id=None, content_id=None, minutes=None):
        row = self._row(feedback, event_id, content_id, minutes)
        with self.repository.transaction():
            if self._existing(row):
                return False
            self.repository.insert_event(row)
            # Backfilled records invalidate later derived messages (not backend cards).
            self.repository.invalidate_from(feedback.child_id, feedback.date)
        return True

    def coach(self, agent, request, event_id=None):
        card = request.today_card
        row = self._row(request.feedback, event_id, card.content_id if card else None, card.minutes if card else None)
        signature_data = asdict(request)
        if request.feedback.rest_day:
            # Rest-day scores/memo are ignored, including during retry comparison.
            signature_data["feedback"] = json.loads(row["feedback_json"])
        signature = digest(signature_data)
        with self.repository.transaction():
            existing = self._existing(row)
            if existing and existing["request_hash"] and existing["request_hash"] != signature:
                raise MemoryConflictError("coach retry has different request data")
            if existing and existing["result_json"]:
                return CoachResult(**json.loads(existing["result_json"]))
            before = (iso_date(request.feedback.date) - timedelta(days=1)).isoformat()
            context = self._context(request.child_id, before)
            merged = {r["date"]: Feedback(**{k: v for k, v in r.items() if k not in ("content_id", "minutes")})
                      for r in context["history"]}
            for explicit in request.history:
                if explicit.date in merged:
                    stored = asdict(merged[explicit.date])
                    provided = asdict(explicit)
                    stored.pop("memo")
                    provided.pop("memo")
                    if stored != provided:
                        raise MemoryConflictError("explicit history conflicts with stored feedback")
                merged[explicit.date] = explicit
            preferences = self._context(request.child_id, request.feedback.date)["preferences"]
            enriched = replace(request, history=tuple(merged[k] for k in sorted(merged)),
                               favorite_topics=tuple(dict.fromkeys((*request.favorite_topics, *preferences["favorite_topics"]))),
                               owned_materials=tuple(dict.fromkeys((*request.owned_materials, *preferences["owned_materials"]))))
            result = agent._coach(enriched, memory_summary={
                key: context["summary"][key] for key in (
                    "current_7_days", "previous_7_days", "preferred_content_ids",
                    "weak_content_ids", "duration_responses",
                )
            })
            if not request.feedback.rest_day and context["summary"]["record_days"]:
                # Add observed history, never a success guarantee; preserve final AI label.
                from ai.agent.guardrails import AI_LABEL
                trend = context["summary"]["current_7_days"]
                count = trend["record_days"]
                if count:
                    line = f"이전 7일 학습 기록 {count}일: 평균 흥미 {trend['avg_interest']}, 평균 이해도 {trend['avg_comprehension']}."
                    result.message = result.message.removesuffix(AI_LABEL) + line + "\n" + AI_LABEL
            result.memory_context = {"as_of": before, "summary": context["summary"], "preferences": preferences}
            from ai.agent.guardrails import validate_result
            validate_result(result, enriched, agent.tools)
            if not existing:
                self.repository.insert_event(row)
                self.repository.invalidate_from(request.child_id, request.feedback.date)
            self.repository.cache_result(request.child_id, request.feedback.date, signature, encode(result.to_dict()))
            return result

    def enrich_recommendation(self, request, child_id):
        context = self.get_context(child_id, request.start_date)
        preferences = context["preferences"]
        return replace(request,
                       favorite_topics=tuple(dict.fromkeys((*request.favorite_topics, *preferences["favorite_topics"]))),
                       owned_materials=tuple(dict.fromkeys((*request.owned_materials, *preferences["owned_materials"])))), context

    def replace_feedback(self, feedback, *, content_id=None, minutes=None):
        """Replace an existing child/date atomically, keeping its event ID."""
        if not isinstance(feedback, Feedback):
            raise ValueError("feedback must be Feedback")
        with self.repository.transaction():
            existing = self.repository.event(feedback.child_id, feedback.date)
            if not existing:
                return False
            row = self._row(feedback, existing["event_id"], content_id, minutes)
            if existing["record_hash"] == row["record_hash"]:
                return False
            self.repository.delete_feedback(feedback.child_id, feedback.date)
            self.repository.insert_event(row)
        return True

    def delete_feedback(self, child_id, day):
        child_identity(child_id)
        iso_date(day)
        with self.repository.transaction():
            return self.repository.delete_feedback(child_id, day)

    def delete_child(self, child_id):
        child_identity(child_id)
        with self.repository.transaction():
            self.repository.delete_child(child_id)
