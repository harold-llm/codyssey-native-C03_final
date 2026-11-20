"""Test repository boundaries using synthetic rows without network or team code."""
import unittest

from ai.agent import CoachAgent
from ai.backend_adapter import coaching_request, recommendation_request, shared_catalog
from ai.rag import RecommendationEngine
from ai.rag.planner import InsufficientCatalogError
from examples.ai_demo import demo_engine


class BackendAdapterTests(unittest.TestCase):
    def setUp(self):
        self.item = demo_engine().catalog[0]
        self.child = {"id": 7, "age": 5, "level": 2, "session_length": 10,
                      "materials": "demo-sound-001; 교재 A", "favorite_topics": "동물, 우주\n",
                      "exposure": "some"}
        self.feedback = {"child_id": 7, "date": "2026-11-16", "completion": "partial",
                         "satisfaction": 3, "interest": 3, "comprehension": 2}
        self.card = {"child_id": 7, "date": "2026-11-17", "content_id": self.item["id"],
                     "minutes": 5, "task": self.item["task"], "check_point": self.item["check_point"]}

    def test_profile_maps_terms_and_exposure(self):
        req = recommendation_request(self.child, "2026-11-16", exposure_months=14)
        self.assertEqual(req.owned_materials, ("demo-sound-001", "교재 A"))
        self.assertEqual(req.favorite_topics, ("동물", "우주"))
        self.assertEqual((req.exposure, req.exposure_months), ("some", 14))

    def test_catalog_excludes_unregistered_ids_and_rejects_drift(self):
        shared = shared_catalog([self.item, {"id": "old-id"}], demo_engine().catalog)
        self.assertEqual(shared, [self.item])
        with self.assertRaisesRegex(ValueError, "catalog drift"):
            shared_catalog([{**self.item, "age_max": 6}], [self.item])
        with self.assertRaisesRegex(ValueError, "duplicate backend content_id"):
            shared_catalog([self.item, self.item], [self.item])
        rag = RecommendationEngine(shared_catalog([], [self.item]))
        with self.assertRaises(InsufficientCatalogError):
            rag.recommend(recommendation_request(self.child, "2026-11-16"))

    def test_draft_is_inactive_and_five_minute_card_needs_no_write(self):
        rag = RecommendationEngine([self.item])
        coach = CoachAgent(rag)
        request = coaching_request(self.child, self.feedback, catalog=rag.catalog, next_card=self.card)
        self.assertIsNone(coach.coach(request).tomorrow)
        request = coaching_request(self.child, self.feedback, catalog=rag.catalog, next_card=self.card,
                                   plan_status="approved")
        result = coach.coach(request)
        self.assertEqual((result.case, result.tomorrow["minutes"]), ("B", 5))
        self.assertEqual(result.adjust["type"], "none")
        self.assertFalse(result.adjust["auto_apply"])

    def test_legacy_card_without_id_cannot_be_adjusted(self):
        rag = RecommendationEngine([self.item])
        request = coaching_request(self.child, self.feedback, catalog=rag.catalog,
                                   next_card={**self.card, "content_id": None}, plan_status="approved")
        self.assertIsNone(request.next_card)
        self.assertFalse(CoachAgent(rag).coach(request).adjust["auto_apply"])

    def test_rest_row_and_cross_child_isolation(self):
        rag = RecommendationEngine([self.item])
        rest = {"child_id": 7, "date": self.feedback["date"], "completion": "", "interest": 0, "rest_day": 1}
        request = coaching_request(self.child, rest, catalog=rag.catalog, next_card=self.card,
                                   plan_status="approved")
        self.assertEqual(CoachAgent(rag).coach(request).case, "SKIP")
        with self.assertRaisesRegex(ValueError, "card belongs to another child"):
            coaching_request(self.child, self.feedback, catalog=rag.catalog, next_card={**self.card, "child_id": 8})
        with self.assertRaisesRegex(ValueError, "feedback belongs to another child"):
            coaching_request(self.child, self.feedback, catalog=rag.catalog,
                             history=[{**self.feedback, "date": "2026-11-15", "child_id": 8}])

    def test_rest_day_requires_boolean_or_database_integer(self):
        catalog = demo_engine().catalog
        for value in (False, True, 0, 1):
            with self.subTest(value=value):
                request = coaching_request(
                    self.child, {**self.feedback, "rest_day": value}, catalog=catalog)
                self.assertEqual(request.feedback.rest_day, bool(value))
        for value in ("false", "true", "0", "1", "", None, 0.0, 1.0, 2, -1, [], {}):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "rest_day"):
                coaching_request(
                    self.child, {**self.feedback, "rest_day": value}, catalog=catalog)
        request = coaching_request(self.child, self.feedback, catalog=catalog)
        self.assertFalse(request.feedback.rest_day)
