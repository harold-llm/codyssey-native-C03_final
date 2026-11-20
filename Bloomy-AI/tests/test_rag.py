"""Behavior tests; network and external API keys are never required."""
from copy import deepcopy
from datetime import date
from pathlib import Path
import unittest

from ai.contracts import RecommendationRequest
from ai.rag import RecommendationEngine
from ai.rag.ingest import load_catalog, make_chunks, validate_catalog
from ai.rag.planner import InsufficientCatalogError
from ai.rag.validator import validate_result

SAMPLE = Path(__file__).resolve().parents[1] / "data" / "catalog" / "sample.json"


class RagTests(unittest.TestCase):
    def setUp(self):
        self.items = load_catalog(SAMPLE)
        self.engine = RecommendationEngine(self.items)

    def request(self, **changes):
        return RecommendationRequest(**{"age": 5, "base_level": 2, "start_date": "2026-11-21", **changes})

    def test_plan_calendar_and_backend_contract(self):
        result = self.engine.recommend(self.request())
        self.assertEqual(len(result.days), 20)
        self.assertEqual(result.days[0]["date"], "2026-11-23")
        self.assertEqual(result.days[-1]["date"], "2026-12-18")
        self.assertTrue(all(date.fromisoformat(d["date"]).weekday() < 5 for d in result.days))
        self.assertEqual(set(result.to_backend_payload()), {"days", "explanation", "base_level"})
        self.assertEqual(result.status, "draft")

    def test_owned_material_is_first(self):
        result = self.engine.recommend(self.request(owned_materials=("개발용 인사 놀이 카드",)))
        self.assertEqual(result.days[0]["content_id"], "demo-speaking-001")

    def test_goal_and_topic_retrieval(self):
        result = self.engine.recommend(self.request(goal="듣기", favorite_topics=("동물",)))
        self.assertEqual(result.days[0]["content_id"], "demo-animal-001")
        result = self.engine.recommend(self.request(goal="말하기"))
        self.assertEqual(result.days[0]["content_id"], "demo-speaking-001")

    def test_age_level_and_duration_are_hard_filters(self):
        for changes in ({"age_min": 6}, {"level": 3}, {"session_minutes": 20}):
            with self.subTest(changes=changes):
                items = deepcopy(self.items)
                for item in items:
                    item.update(changes)
                with self.assertRaises(InsufficientCatalogError):
                    RecommendationEngine(items).recommend(self.request())

    def test_empty_catalog_fails_explicitly(self):
        with self.assertRaises(InsufficientCatalogError):
            RecommendationEngine([]).recommend(self.request())

    def test_warnings_for_sparse_unreviewed_and_missing_owned(self):
        result = self.engine.recommend(self.request(owned_materials=("없는 교재",)))
        self.assertEqual(len(result.warnings), 3)

    def test_evidence_and_instructions_are_catalog_grounded(self):
        result = self.engine.recommend(self.request())
        lookup = {item["id"]: item for item in self.items}
        for evidence in result.evidence:
            self.assertEqual(evidence["source"], lookup[evidence["content_id"]]["trust_source"])
            self.assertIn(evidence["title"], result.explanation)
        for day in result.days:
            self.assertEqual(day["task"], lookup[day["content_id"]]["task"])

    def test_tampered_plan_is_rejected(self):
        for key, value in (("content_id", "invented"), ("task", "invented activity"),
                           ("minutes", 30), ("date", "2026-11-22")):
            with self.subTest(key=key):
                result = self.engine.recommend(self.request())
                result.days[0][key] = value
                with self.assertRaises(ValueError):
                    validate_result(result, self.request(), self.items)

    def test_invalid_requests_are_rejected(self):
        for changes in ({"age": 3}, {"age": True}, {"base_level": 6}, {"top_k": 0},
                        {"session_minutes": 5}, {"start_date": "2026-02-30"},
                        {"start_date": "20261117"}, {"goal": ""}, {"owned_materials": "book"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.request(**changes)

    def test_catalog_validation(self):
        for changes in ({"skill": "unknown"}, {"age_max": 3}, {"link": "http://example.org"},
                        {"expert_note": ""}, {"task": ""}, {"level": True}):
            with self.subTest(changes=changes):
                items = deepcopy(self.items)
                items[0].update(changes)
                with self.assertRaises(ValueError):
                    validate_catalog(items)
        with self.assertRaises(ValueError):
            validate_catalog(self.items + [deepcopy(self.items[0])])

    def test_reproducible_and_no_input_mutation(self):
        original = deepcopy(self.items)
        self.assertEqual(self.engine.recommend(self.request()).to_dict(), self.engine.recommend(self.request()).to_dict())
        self.assertEqual(original, self.items)

    def test_chunks_have_unique_attributable_ids(self):
        chunks = make_chunks(self.items)
        self.assertEqual(len(chunks), len(self.items) * 3)
        self.assertEqual(len({c["chunk_id"] for c in chunks}), len(chunks))


if __name__ == "__main__":
    unittest.main()
