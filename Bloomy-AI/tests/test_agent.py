"""Coach behavior and RAG integration tests; no API keys or network."""
from copy import deepcopy
from dataclasses import asdict, replace
from pathlib import Path
import json
import subprocess
import sys
import unittest
from unittest.mock import patch

from ai.agent import CoachAgent, CoachRequest, Feedback, LearningCard
from ai.agent.guardrails import AI_LABEL, validate_result
from ai.agent.intent import KeywordIntentClassifier
from ai.contracts import RecommendationRequest
from ai.rag import RecommendationEngine
from ai.rag.ingest import load_catalog

SAMPLE = Path(__file__).resolve().parents[1] / "data" / "catalog" / "sample.json"


class CoachTests(unittest.TestCase):
    def setUp(self):
        self.items = load_catalog(SAMPLE)
        for level in (1, 2):
            item = deepcopy(self.items[0])
            item.update(id=f"test-audio-l{level}", title=f"테스트 오디오 L{level}",
                        level=level, type="audio", review_status="reviewed")
            self.items.append(item)
        self.rag = RecommendationEngine(self.items)
        self.agent = CoachAgent(self.rag)

    def feedback(self, **changes):
        return Feedback(**{"child_id": 1, "date": "2026-11-18", "completion": "full",
                           "satisfaction": 4, "interest": 4, "comprehension": 4, **changes})

    def card(self, day="2026-11-19", **changes):
        item = self.items[0]
        return LearningCard(**{"child_id": 1, "date": day, "content_id": item["id"],
                               "task": item["task"], "minutes": 10,
                               "check_point": item["check_point"], **changes})

    def request(self, **changes):
        return CoachRequest(**{"child_id": 1, "age": 5, "base_level": 2,
                               "feedback": self.feedback(), "today_card": self.card("2026-11-18"),
                               "next_card": self.card(), "plan_status": "approved", **changes})

    def test_a_preserves_plan_and_ai_label(self):
        request = self.request()
        result = self.agent.coach(request)
        self.assertEqual(result.case, "A")
        self.assertEqual(result.tomorrow, asdict(request.next_card))
        self.assertTrue(result.message.endswith(AI_LABEL))
        self.assertEqual(result.confidence_sentence, "")

    def test_b_shrinks_with_five_minute_floor(self):
        for completion, comprehension in (("partial", 4), ("none", 4), ("full", 2)):
            with self.subTest(completion=completion, comprehension=comprehension):
                result = self.agent.coach(self.request(feedback=self.feedback(completion=completion, comprehension=comprehension)))
                self.assertEqual((result.case, result.adjust["type"], result.tomorrow["minutes"]), ("B", "shrink", 5))
                self.assertTrue(result.adjust["auto_apply"])
        result = self.agent.coach(self.request(feedback=self.feedback(completion="partial"), next_card=self.card(minutes=5)))
        self.assertEqual(result.tomorrow["minutes"], 5)

    def test_single_interest_dip_stays_a(self):
        result = self.agent.coach(self.request(feedback=self.feedback(interest=2)))
        self.assertEqual(result.case, "A")
        self.assertTrue(result.flags["interest_dip"])
        self.assertEqual(result.adjust["type"], "none")

    def test_two_adjacent_low_days_swap_format_same_level(self):
        result = self.agent.coach(self.request(feedback=self.feedback(interest=2),
                                             history=(self.feedback(date="2026-11-17", interest=2),)))
        self.assertEqual((result.case, result.adjust["type"]), ("C", "swap"))
        self.assertEqual(result.tomorrow["content_id"], "test-audio-l2")
        self.assertIn("휴식일", result.message)

    def test_gap_or_rest_breaks_low_interest_streak(self):
        for previous in (self.feedback(date="2026-11-16", interest=1),
                         self.feedback(date="2026-11-17", rest_day=True, interest=1)):
            with self.subTest(previous=previous):
                result = self.agent.coach(self.request(feedback=self.feedback(interest=2), history=(previous,)))
                self.assertEqual(result.case, "A")

    def test_c_b_overlap_uses_lower_level_format(self):
        result = self.agent.coach(self.request(feedback=self.feedback(interest=1, comprehension=2),
                                             history=(self.feedback(date="2026-11-17", interest=1),)))
        self.assertEqual((result.case, result.adjust["type"]), ("C", "swap_easy"))
        self.assertTrue(result.flags["difficulty_adjust"])
        self.assertEqual(result.tomorrow["content_id"], "test-audio-l1")

    def test_question_has_rag_advice_and_c_precedence(self):
        result = self.agent.coach(self.request(feedback=self.feedback(memo="어떻게 도와줄까요?", comprehension=2)))
        self.assertEqual((result.case, result.memo_intent, result.adjust["type"]), ("C", "question", "shrink"))
        self.assertTrue(result.flags["difficulty_adjust"])
        self.assertTrue(result.evidence)
        self.assertIn("자료 안내:", result.message)

    def test_parent_change_is_pending_even_with_b_overlap(self):
        request = self.request(feedback=self.feedback(memo="다른 자료로 바꿔 주세요", comprehension=2))
        result = self.agent.coach(request)
        self.assertEqual((result.case, result.adjust["type"]), ("C", "propose_swap"))
        self.assertTrue(result.adjust["requires_parent_approval"])
        self.assertFalse(result.adjust["auto_apply"])
        self.assertIsNotNone(result.adjust["proposal"])
        self.assertEqual(result.tomorrow, asdict(request.next_card))

    def test_out_of_scope_wins_over_change_and_b(self):
        request = self.request(feedback=self.feedback(memo="발달 진단 후 교재를 바꿔야 하나요?", comprehension=1))
        result = self.agent.coach(request)
        self.assertEqual((result.case, result.memo_intent), ("C", "out_of_scope"))
        self.assertTrue(result.flags["expert_referral"])
        self.assertEqual(result.adjust["type"], "none")
        self.assertEqual(result.tomorrow, asdict(request.next_card))
        self.assertIn("전문가", result.message)

    def test_rest_skips_classifier_retrieval_and_message(self):
        request = self.request(feedback=self.feedback(rest_day=True, memo="발달 진단 바꿔", interest=None))
        with patch.object(self.agent.classifier, "classify", side_effect=AssertionError("must not classify")), \
             patch.object(self.rag.retriever, "search", side_effect=AssertionError("must not search")):
            result = self.agent.coach(request)
        self.assertEqual(result.case, "SKIP")
        self.assertIsNone(result.message)
        self.assertIsNone(result.tomorrow)
        self.assertFalse(result.is_ai_generated)

    def test_unapproved_or_inactive_plans_cannot_activate_or_adjust(self):
        for status in ("draft", "done", "superseded"):
            for memo in ("", "바꿔 주세요"):
                with self.subTest(status=status, memo=memo):
                    result = self.agent.coach(self.request(plan_status=status,
                        feedback=self.feedback(completion="partial", memo=memo)))
                    self.assertIsNone(result.tomorrow)
                    self.assertEqual(result.adjust["type"], "none")
                    self.assertFalse(result.adjust["auto_apply"])

    def test_end_of_plan_never_invents_next_card(self):
        result = self.agent.coach(self.request(next_card=None, feedback=self.feedback(memo="바꿔 주세요")))
        self.assertIsNone(result.tomorrow)
        self.assertEqual(result.adjust["type"], "none")

    def test_sparse_catalog_does_not_invent_replacement(self):
        agent = CoachAgent(RecommendationEngine([self.items[0]]))
        request = self.request(feedback=self.feedback(interest=1), history=(self.feedback(date="2026-11-17", interest=1),))
        result = agent.coach(request)
        self.assertEqual(result.adjust["type"], "none")
        self.assertTrue(result.warnings)
        result = agent.coach(replace(request, feedback=self.feedback(memo="바꿔 주세요")))
        self.assertIsNone(result.adjust["proposal"])
        self.assertTrue(result.adjust["requires_parent_approval"])
        self.assertEqual(result.tomorrow, asdict(request.next_card))

    def test_no_lower_candidate_falls_back_to_shrink(self):
        agent = CoachAgent(RecommendationEngine(load_catalog(SAMPLE)))
        result = agent.coach(self.request(feedback=self.feedback(interest=1, comprehension=1),
                                         history=(self.feedback(date="2026-11-17", interest=1),)))
        self.assertEqual(result.adjust["type"], "shrink")
        self.assertEqual(result.tomorrow["content_id"], self.items[0]["id"])

    def test_unknown_content_and_cross_child_rejected(self):
        with self.assertRaises(ValueError):
            self.agent.coach(self.request(next_card=self.card(content_id="invented")))
        for changes in ({"next_card": self.card(child_id=2)}, {"feedback": self.feedback(child_id=2)},
                        {"history": (self.feedback(child_id=2, date="2026-11-17"),)}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.request(**changes)

    def test_invalid_feedback_and_dates_rejected(self):
        for changes in ({"interest": True}, {"comprehension": 0}, {"satisfaction": 6}, {"completion": "other"},
                        {"memo": "x" * 501}, {"date": "2026-02-30"}, {"rest_day": "true"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.feedback(**changes)
        for changes in ({"history": (self.feedback(),)},
                        {"history": (self.feedback(date="2026-11-19"),)},
                        {"today_card": self.card("2026-11-17")}, {"next_card": self.card("2026-11-18")},
                        {"plan_status": "active"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.request(**changes)

    def test_classifier_schema_failure_falls_back(self):
        class BrokenClassifier:
            def classify(self, memo):
                return {"intent": "invented", "case": "A"}
        result = CoachAgent(self.rag, BrokenClassifier()).coach(self.request(feedback=self.feedback(memo="도와줄까요?")))
        self.assertEqual(result.memo_intent, "question")
        self.assertTrue(any("분류기 실패" in warning for warning in result.warnings))

    def test_no_input_mutation_and_reproducible(self):
        request = self.request(feedback=self.feedback(completion="partial"))
        snapshot = asdict(request)
        self.assertEqual(self.agent.coach(request).to_dict(), self.agent.coach(request).to_dict())
        self.assertEqual(asdict(request), snapshot)

    def test_guardrail_rejects_applied_pending_change(self):
        request = self.request(feedback=self.feedback(memo="바꿔 주세요"))
        result = self.agent.coach(request)
        result.tomorrow = result.adjust["proposal"]
        with self.assertRaises(ValueError):
            validate_result(result, request, self.agent.tools)

    def test_guardrail_rejects_changed_rule_decision(self):
        request = self.request(feedback=self.feedback(comprehension=2))
        result = self.agent.coach(request)
        result.case = "A"
        with self.assertRaises(ValueError):
            validate_result(result, request, self.agent.tools)

    def test_lowest_level_never_invents_level_zero(self):
        item = self.items[-2]
        card = self.card(content_id=item["id"], task=item["task"], check_point=item["check_point"])
        result = self.agent.coach(self.request(base_level=1, next_card=card,
            feedback=self.feedback(interest=1, comprehension=1),
            history=(self.feedback(date="2026-11-17", interest=1),)))
        self.assertEqual(result.adjust["type"], "shrink")
        self.assertEqual(result.tomorrow["content_id"], item["id"])

    def test_rag_plan_to_coach_end_to_end_without_network(self):
        with patch("socket.socket", side_effect=AssertionError("network forbidden")):
            plan = self.rag.recommend(RecommendationRequest(age=5, base_level=2, start_date="2026-11-18"))
            today, tomorrow = (LearningCard(child_id=1, **day) for day in plan.days[:2])
            request = self.request(today_card=today, next_card=tomorrow,
                                   feedback=self.feedback(completion="partial"))
            pending = self.agent.coach(replace(request, plan_status=plan.status))
            self.assertIsNone(pending.tomorrow)
            approved = self.agent.coach(request)
            self.assertEqual(approved.tomorrow["date"], tomorrow.date)
            self.assertEqual(approved.tomorrow["minutes"], 5)

    def test_windows_cli_emits_valid_utf8_json(self):
        run = subprocess.run([sys.executable, "-m", "examples.coach"],
                             cwd=SAMPLE.parents[2], capture_output=True, encoding="utf-8", check=True)
        output = json.loads(run.stdout)
        self.assertEqual((output["case"], output["memo_intent"], output["adjust"]["type"]),
                         ("C", "question", "shrink"))
        self.assertIn(AI_LABEL, output["message"])

    def test_intent_keyword_priority(self):
        classifier = KeywordIntentClassifier()
        for memo, expected in (("발달 진단 교재 바꿔?", "out_of_scope"),
                               ("바꿔도 될까요?", "change_request"), ("왜 이 활동인가요?", "question"), ("잘 했어요", "none")):
            self.assertEqual(classifier.classify(memo)["intent"], expected)


if __name__ == "__main__":
    unittest.main()
