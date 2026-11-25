"""Durable memory, scoped history, calendar trends, and integrated retry tests."""
import sqlite3
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from ai.agent import CoachAgent, CoachRequest, Feedback, LearningCard
from ai.contracts import RecommendationRequest
from ai.memory import MemoryConflictError, MemoryService
from ai.rag import RecommendationEngine
from ai.rag.ingest import load_catalog

SAMPLE = Path(__file__).resolve().parents[1] / "data" / "catalog" / "sample.json"


class MemoryTests(unittest.TestCase):
    def setUp(self):
        local = SAMPLE.parents[1] / "local"
        local.mkdir(parents=True, exist_ok=True)
        self.temp = TemporaryDirectory(dir=local)
        self.path = Path(self.temp.name) / "memory.sqlite3"
        self.memory = MemoryService.from_sqlite(self.path)
        self.items = load_catalog(SAMPLE)
        alternate = deepcopy(self.items[0])
        alternate.update(id="test-audio", title="테스트 오디오", type="audio", review_status="reviewed")
        self.items.append(alternate)
        self.rag = RecommendationEngine(self.items, memory=self.memory)
        self.agent = CoachAgent(self.rag)

    def tearDown(self):
        self.memory.close()
        self.temp.cleanup()

    def feedback(self, **changes):
        return Feedback(**{"child_id": 1, "date": "2026-11-18", "completion": "full",
                           "satisfaction": 4, "interest": 4, "comprehension": 4, **changes})

    def card(self, day="2026-11-19"):
        item = self.items[0]
        return LearningCard(1, day, item["id"], item["task"], 10, item["check_point"])

    def request(self, **changes):
        return CoachRequest(**{"child_id": 1, "age": 5, "base_level": 2, "feedback": self.feedback(),
                               "today_card": self.card("2026-11-18"), "next_card": self.card(),
                               "plan_status": "approved", **changes})

    def recommendation(self, **changes):
        return RecommendationRequest(**{"age": 5, "base_level": 2, "start_date": "2026-11-18", **changes})

    def test_reopen_preserves_history_and_preferences(self):
        self.memory.set_preferences(1, "2026-11-01", favorite_topics=["동물"], owned_materials=["demo-animal-001"])
        self.memory.record_feedback(self.feedback(), content_id="demo-sound-001", minutes=10)
        self.memory.close()
        self.memory = MemoryService.from_sqlite(self.path)
        context = self.memory.get_context(1, "2026-11-18")
        self.assertEqual(context["history"][0]["content_id"], "demo-sound-001")
        self.assertEqual(context["preferences"]["favorite_topics"], ["동물"])
        self.assertEqual(context["summary"]["learning_streak"], 1)

    def test_child_isolation_including_event_ids(self):
        self.memory.record_feedback(self.feedback(), event_id="same")
        self.memory.record_feedback(self.feedback(child_id=2, interest=1), event_id="same")
        self.memory.set_preferences(2, "2026-11-01", favorite_topics=["우주"])
        one = self.memory.get_context(1, "2026-11-18")
        two = self.memory.get_context(2, "2026-11-18")
        self.assertEqual(one["summary"]["current_7_days"]["avg_interest"], 4)
        self.assertEqual(two["summary"]["current_7_days"]["avg_interest"], 1)
        self.assertEqual(one["preferences"]["favorite_topics"], [])

    def test_idempotency_and_conflicting_record(self):
        self.assertTrue(self.memory.record_feedback(self.feedback()))
        self.assertFalse(self.memory.record_feedback(self.feedback()))
        for feedback, event_id in ((self.feedback(interest=2), None), (self.feedback(), "different"),
                                   (self.feedback(date="2026-11-19"), "feedback:2026-11-18")):
            with self.subTest(feedback=feedback, event_id=event_id), self.assertRaises(MemoryConflictError):
                self.memory.record_feedback(feedback, event_id=event_id)
        self.assertEqual(len(self.memory.get_context(1, "2026-11-20")["history"]), 1)

    def test_as_of_filters_future_records_and_preference_versions(self):
        self.memory.set_preferences(1, "2026-11-01", favorite_topics=["동물"])
        self.memory.set_preferences(1, "2026-11-19", favorite_topics=["우주"])
        self.memory.record_feedback(self.feedback(date="2026-11-17"))
        self.memory.record_feedback(self.feedback(date="2026-11-19", interest=1))
        context = self.memory.get_context(1, "2026-11-18")
        self.assertEqual(len(context["history"]), 1)
        self.assertEqual(context["preferences"]["favorite_topics"], ["동물"])
        self.assertEqual(context["summary"]["learning_streak"], 0)  # No record on anchor date.
        self.assertEqual(self.memory.get_context(1, "2026-11-19")["preferences"]["favorite_topics"], ["우주"])

    def test_calendar_week_averages_and_rest_exclusion(self):
        self.memory.record_feedback(self.feedback(date="2026-11-05", interest=5))
        self.memory.record_feedback(self.feedback(date="2026-11-11", interest=4, comprehension=4))
        self.memory.record_feedback(self.feedback(date="2026-11-12", interest=2, comprehension=2))
        self.memory.record_feedback(self.feedback(date="2026-11-17", rest_day=True, interest=1))
        self.memory.record_feedback(self.feedback(interest=2, comprehension=2))
        summary = self.memory.get_context(1, "2026-11-18")["summary"]
        self.assertEqual(summary["current_7_days"]["record_days"], 2)
        self.assertEqual(summary["current_7_days"]["avg_interest"], 2)
        self.assertEqual(summary["previous_7_days"]["avg_interest"], 4.5)
        self.assertEqual(summary["interest_change"], -2.5)
        self.assertEqual(summary["rest_days"], 1)
        self.assertEqual(summary["low_interest_streak"], 1)

    def test_content_and_duration_patterns_require_repeated_observation(self):
        for day in ("2026-11-17", "2026-11-18"):
            self.memory.record_feedback(self.feedback(date=day, comprehension=2), content_id="demo-animal-001", minutes=15)
        summary = self.memory.get_context(1, "2026-11-18")["summary"]
        self.assertEqual(summary["preferred_content_ids"], ["demo-animal-001"])
        self.assertEqual(summary["weak_content_ids"], ["demo-animal-001"])
        self.assertEqual(summary["duration_responses"], [{"minutes": 15, "observations": 2, "avg_interest": 4.0}])
        self.assertEqual(summary["learning_streak"], 2)
        self.assertEqual(summary["low_comprehension_streak"], 2)

    def test_rag_uses_saved_materials_and_topics(self):
        self.memory.set_preferences(1, "2026-11-01", owned_materials=["demo-speaking-001"], favorite_topics=["동물"])
        result = self.rag.recommend(self.recommendation(), child_id=1)
        self.assertEqual(result.days[0]["content_id"], "demo-speaking-001")
        self.assertEqual(result.memory_context["preferences"]["favorite_topics"], ["동물"])
        with self.assertRaises(ValueError):
            self.rag.recommend(self.recommendation())

    def test_rag_reorders_by_observed_preference_without_changing_level(self):
        for day in ("2026-11-16", "2026-11-17"):
            self.memory.record_feedback(self.feedback(date=day, interest=5), content_id="demo-speaking-001")
        result = self.rag.recommend(self.recommendation(top_k=1), child_id=1)
        self.assertEqual(result.days[0]["content_id"], "demo-speaking-001")
        self.assertEqual(result.base_level, 2)

    def test_preference_edit_invalidates_cache_and_changes_rag_advice(self):
        request = self.request(feedback=self.feedback(memo="어떻게 도와줄까요?"))
        first = self.agent.coach(request)
        self.memory.set_preferences(1, "2026-11-18", owned_materials=["demo-speaking-001"])
        second = self.agent.coach(request)
        self.assertNotEqual(first.memory_context["preferences"], second.memory_context["preferences"])
        self.assertIn("개발용 인사 놀이 카드", second.message)

    def test_weak_content_is_deprioritized_in_rag(self):
        for day in ("2026-11-16", "2026-11-17"):
            self.memory.record_feedback(self.feedback(date=day, comprehension=1), content_id="demo-animal-001")
        result = self.rag.recommend(self.recommendation(favorite_topics=("동물",)), child_id=1)
        self.assertNotEqual(result.days[0]["content_id"], "demo-animal-001")

    def test_full_memory_flow_uses_no_network(self):
        with patch("socket.socket", side_effect=AssertionError("network forbidden")):
            self.memory.set_preferences(1, "2026-11-01", favorite_topics=["동물"])
            self.memory.record_feedback(self.feedback(date="2026-11-17"))
            self.rag.recommend(self.recommendation(), child_id=1)
            self.agent.coach(self.request())
            self.assertEqual(len(self.memory.get_context(1, "2026-11-18")["history"]), 2)

    def test_coach_uses_stored_yesterday_and_caches_retry(self):
        self.memory.record_feedback(self.feedback(date="2026-11-17", interest=1))
        request = self.request(feedback=self.feedback(interest=1))
        result = self.agent.coach(request, event_id="coach-event")
        self.assertEqual((result.case, result.adjust["type"]), ("C", "swap"))
        self.assertIn("이전 7일 학습 기록 1일", result.message)
        with patch.object(self.agent, "_coach", side_effect=AssertionError("cached retry must not run agent")):
            retry = self.agent.coach(request, event_id="coach-event")
        self.assertEqual(result.to_dict(), retry.to_dict())
        self.assertEqual(len(self.memory.get_context(1, "2026-11-18")["history"]), 2)
        with self.assertRaises(MemoryConflictError):
            self.agent.coach(replace(request, next_card=self.card("2026-11-20")), event_id="coach-event")

    def test_cache_survives_connection_restart(self):
        request = self.request(feedback=self.feedback(completion="partial"))
        first = self.agent.coach(request)
        self.memory.close()
        self.memory = MemoryService.from_sqlite(self.path)
        agent = CoachAgent(RecommendationEngine(self.items), memory=self.memory)
        with patch.object(agent, "_coach", side_effect=AssertionError("must use persisted result")):
            second = agent.coach(request)
        self.assertEqual(first.to_dict(), second.to_dict())
        self.assertEqual(second.tomorrow["minutes"], 5)

    def test_future_record_does_not_leak_into_coach(self):
        self.memory.record_feedback(self.feedback(date="2026-11-19", interest=1))
        result = self.agent.coach(self.request(feedback=self.feedback(interest=1)))
        self.assertEqual(result.case, "A")
        self.assertEqual(result.memory_context["summary"]["record_days"], 0)

    def test_conflicting_explicit_history_is_rejected(self):
        self.memory.record_feedback(self.feedback(date="2026-11-17", interest=1))
        with self.assertRaises(MemoryConflictError):
            self.agent.coach(self.request(history=(self.feedback(date="2026-11-17", interest=4),)))
        self.assertEqual(len(self.memory.get_context(1, "2026-11-18")["history"]), 1)

    def test_rest_saved_without_scores_memo_or_message(self):
        request = self.request(feedback=self.feedback(rest_day=True, memo="비공개 메모", interest=1))
        result = self.agent.coach(request)
        self.assertEqual(result.case, "SKIP")
        self.assertIsNone(result.message)
        context = self.memory.get_context(1, "2026-11-18")
        self.assertIsNone(context["history"][0]["interest"])
        self.assertNotIn("memo", context["history"][0])
        self.assertEqual(context["summary"]["record_days"], 0)
        self.assertNotIn("비공개 메모", self.path.read_bytes().decode("utf-8", errors="ignore"))

    def test_regular_memo_is_not_stored_as_plaintext(self):
        self.agent.coach(self.request(feedback=self.feedback(memo="비밀메모_123456")))
        connection = sqlite3.connect(self.path)
        try:
            stored = connection.execute("SELECT feedback_json, result_json FROM memory_events").fetchone()
        finally:
            connection.close()
        self.assertNotIn("비밀메모_123456", "".join(stored))

    def test_rest_retry_ignores_changed_scores_and_memo(self):
        first = self.agent.coach(self.request(feedback=self.feedback(rest_day=True, memo="첫 메모", interest=1)))
        second = self.agent.coach(self.request(feedback=self.feedback(rest_day=True, memo="다른 메모", interest=5)))
        self.assertEqual(first.to_dict(), second.to_dict())
        self.assertEqual(len(self.memory.get_context(1, "2026-11-18")["history"]), 1)

    def test_error_rolls_back_feedback_and_cache_atomically(self):
        with patch.object(self.memory.repository, "cache_result", side_effect=RuntimeError("disk error")):
            with self.assertRaises(RuntimeError):
                self.agent.coach(self.request())
        self.assertEqual(self.memory.get_context(1, "2026-11-18")["history"], [])

    def test_delete_feedback_invalidates_later_cached_decision(self):
        self.memory.record_feedback(self.feedback(date="2026-11-17", interest=1))
        request = self.request(feedback=self.feedback(interest=1))
        self.assertEqual(self.agent.coach(request).case, "C")
        self.assertEqual(self.memory.delete_feedback(1, "2026-11-17"), 1)
        self.assertEqual(self.agent.coach(request).case, "A")

    def test_delete_child_removes_only_target_history_preferences_and_cache(self):
        self.agent.coach(self.request())
        self.memory.set_preferences(1, "2026-11-01", favorite_topics=["동물"])
        self.memory.record_feedback(self.feedback(child_id=2))
        self.memory.delete_child(1)
        context = self.memory.get_context(1, "2026-11-18")
        self.assertEqual(context["history"], [])
        self.assertEqual(context["preferences"]["favorite_topics"], [])
        self.assertEqual(len(self.memory.get_context(2, "2026-11-18")["history"]), 1)

    def test_preferences_can_be_cleared_without_future_leak(self):
        self.memory.set_preferences(1, "2026-11-01", favorite_topics=["동물", "동물"])
        self.memory.set_preferences(1, "2026-11-19", favorite_topics=[])
        self.assertEqual(self.memory.get_context(1, "2026-11-18")["preferences"]["favorite_topics"], ["동물"])
        self.assertEqual(self.memory.get_context(1, "2026-11-19")["preferences"]["favorite_topics"], [])

    def test_invalid_identity_dates_and_preferences_rejected(self):
        for child in (0, True, "1", "1 OR 1=1"):
            with self.subTest(child=child), self.assertRaises(ValueError):
                self.memory.get_context(child, "2026-11-18")
        with self.assertRaises(ValueError):
            self.memory.get_context(1, "2026-02-30")
        for values in ("동물", [""], ["x" * 201], ["a"] * 101):
            with self.subTest(values=values), self.assertRaises(ValueError):
                self.memory.set_preferences(1, "2026-11-01", favorite_topics=values)

    def test_parallel_connections_store_event_once(self):
        other = MemoryService.from_sqlite(self.path)
        try:
            with ThreadPoolExecutor(max_workers=2) as pool:
                outcomes = list(pool.map(lambda service: service.record_feedback(self.feedback()), (self.memory, other)))
            self.assertEqual(sorted(outcomes), [False, True])
        finally:
            other.close()

    def test_draft_and_parent_request_gates_survive_memory_integration(self):
        result = self.agent.coach(self.request(plan_status="draft"))
        self.assertIsNone(result.tomorrow)
        request = self.request(feedback=self.feedback(date="2026-11-19", memo="바꿔 주세요"),
                               today_card=self.card("2026-11-19"), next_card=self.card("2026-11-20"))
        result = self.agent.coach(request)
        self.assertTrue(result.adjust["requires_parent_approval"])
        self.assertFalse(result.adjust["auto_apply"])
        self.assertEqual(result.tomorrow["content_id"], request.next_card.content_id)

    def test_in_memory_database_and_future_schema_rejection(self):
        with MemoryService.from_sqlite(":memory:") as service:
            service.record_feedback(self.feedback())
            self.assertEqual(len(service.get_context(1, "2026-11-18")["history"]), 1)
        path = Path(self.temp.name) / "future.sqlite3"
        with closing(sqlite3.connect(path)) as connection:
            connection.execute("PRAGMA user_version=99")
        with self.assertRaises(ValueError):
            MemoryService.from_sqlite(path)


if __name__ == "__main__":
    unittest.main()
