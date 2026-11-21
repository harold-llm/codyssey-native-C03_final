"""Offline tests with mocked model responses and HTTP transport."""
import io
import json
import unittest
from dataclasses import replace
from unittest.mock import Mock, patch

from ai.agent import CoachAgent, CoachRequest, Feedback, LearningCard
from ai.contracts import RecommendationRequest
from ai.llm import OpenAIClient
from ai.memory import MemoryService
from ai.rag import RecommendationEngine
from ai.rag.planner import InsufficientCatalogError
from examples.ai_demo import demo_engine

PLAN_DATE = "2026-11-16"


def schema_response(name, instructions, data, schema):
    properties = schema["properties"]
    if name == "curriculum":
        ids = properties["content_ids"]["items"]["enum"]
        return {"content_ids": [ids[i % len(ids)] for i in range(20)],
                "strategy": properties["strategy"]["enum"][0]}
    if name == "memo_intent":
        return {"intent": "question", "reason": properties["reason"]["enum"][1]}
    return {"case": data["case"], "body": properties["body"]["enum"][0]}


class StructuredTests(unittest.TestCase):
    def setUp(self):
        self.llm = Mock(spec=OpenAIClient, model="mock")
        self.llm.generate.side_effect = schema_response
        self.rag = demo_engine(self.llm)
        self.profile = RecommendationRequest(5, 1, PLAN_DATE, favorite_topics=("동물",), exposure_months=0)

    def test_two_profiles_and_evidence(self):
        for request, first in (
            (self.profile, "demo-l1-animals"),
            (RecommendationRequest(7, 3, PLAN_DATE, goal="파닉스", session_minutes=15,
                                   exposure_months=18), "demo-l3-first-sound"),
        ):
            with self.subTest(age=request.age):
                result = self.rag.recommend(request)
                self.assertEqual(result.engine_version, "bloomy-rag-llm-v1")
                self.assertEqual(result.status, "draft")
                self.assertEqual(len(result.days), 20)
                self.assertEqual(result.days[0]["content_id"], first)
                for day, details in zip(result.days, result.day_details, strict=True):
                    self.assertEqual(day["content_id"], details["content_id"])
                    self.assertEqual(day["date"], details["date"])
                    self.assertTrue(details["title"] and details["learning_goal"] and details["recommendation_reason"])
                self.assertNotIn("title", result.to_backend_payload()["days"][0])
                call = self.llm.generate.call_args.args
                self.assertEqual(call[2]["profile"]["exposure_months"], request.exposure_months)
                self.assertTrue(all(hit["excerpt"] for hit in call[2]["retrieved_catalog"]))

    def test_model_schedule_is_used(self):
        self.llm.generate.side_effect = None
        self.llm.generate.return_value = {
            "content_ids": ["demo-l1-colors"] * 20,
            "strategy": "익숙한 활동을 반복하며 부모가 아이의 반응을 관찰할 기회를 마련합니다.",
        }
        result = self.rag.recommend(self.profile)
        self.assertEqual(result.engine_version, "bloomy-rag-llm-v1")
        self.assertEqual({day["content_id"] for day in result.days}, {"demo-l1-colors"})

    def test_bad_catalog_id_plan_length_and_provider_failure_fall_back(self):
        strategy = "익숙한 활동을 반복하며 부모가 아이의 반응을 관찰할 기회를 마련합니다."
        for output in (
            {"content_ids": ["demo-l3-first-sound"] * 20, "strategy": strategy},
            {"content_ids": ["demo-l1-colors"], "strategy": strategy},
            {"content_ids": ["invented"] * 20, "strategy": strategy},
            OSError("provider unavailable"),
        ):
            with self.subTest(output=output):
                self.llm.generate.side_effect = output if isinstance(output, Exception) else None
                self.llm.generate.return_value = output
                result = self.rag.recommend(self.profile)
                self.assertEqual(result.engine_version, "bloomy-rag-local-v1")
                self.assertTrue(any("LLM" in warning for warning in result.warnings))
                self.assertEqual(result.days[0]["content_id"], "demo-l1-animals")

    def test_reviewed_only_excludes_samples(self):
        with self.assertRaises(InsufficientCatalogError):
            RecommendationEngine(self.rag.catalog, reviewed_only=True).recommend(self.profile)

    def coach_request(self):
        plan = demo_engine().recommend(self.profile)
        today, next_card = [LearningCard(child_id=1, **day) for day in plan.days[:2]]
        return CoachRequest(1, 5, 1, Feedback(1, PLAN_DATE, "partial", 3, 3, 2, "어떻게 할까요?"),
                            today, next_card, plan_status="approved")

    def test_separate_intent_and_message_calls_case_c_has_priority(self):
        request = self.coach_request()
        result = CoachAgent(self.rag).coach(request)
        self.assertEqual((result.case, result.adjust["type"]), ("C", "shrink"))
        self.assertTrue(result.flags["difficulty_adjust"])
        self.assertEqual(result.tomorrow["minutes"], 5)
        self.assertEqual(result.prompt_version, "bloomy-coach-llm-v1")
        self.assertEqual([call.args[0] for call in self.llm.generate.call_args_list], ["memo_intent", "coach_message"])
        message_data = self.llm.generate.call_args.args[2]
        self.assertNotIn("memo", message_data["feedback"])
        self.assertNotIn("child_id", message_data["feedback"])

    def test_rest_never_calls_model(self):
        request = self.coach_request()
        result = CoachAgent(self.rag).coach(replace(request, feedback=Feedback(1, PLAN_DATE, rest_day=True)))
        self.assertEqual(result.case, "SKIP")
        self.assertIsNone(result.message)
        self.llm.generate.assert_not_called()

    def test_provider_errors_keep_python_decision(self):
        self.llm.generate.side_effect = TimeoutError()
        result = CoachAgent(self.rag).coach(self.coach_request())
        self.assertEqual((result.case, result.adjust["type"]), ("C", "shrink"))
        self.assertEqual(result.model, "local-rules")
        self.assertEqual(len([warning for warning in result.warnings if "실패" in warning]), 2)

    def test_model_cannot_change_case_or_recommend_arbitrary_content(self):
        def tampered(name, instructions, data, schema):
            if name == "coach_message":
                return {"case": "A", "body": "미등록 자료를 쓰면 성과를 보장합니다."}
            return schema_response(name, instructions, data, schema)

        self.llm.generate.side_effect = tampered
        result = CoachAgent(self.rag).coach(self.coach_request())
        self.assertEqual(result.case, "C")
        self.assertEqual(result.model, "local-rules")
        self.assertNotIn("보장", result.message)

    def test_openai_wire_format(self):
        client = OpenAIClient("fake-key")
        response = {"choices": [{"message": {"content": '{"intent":"none"}'}}]}
        schema = {"type": "object"}
        with patch("ai.llm.urlopen", return_value=io.StringIO(json.dumps(response))) as http:
            self.assertEqual(client.generate("test", "Test", {"label": "학습"}, schema), {"intent": "none"})
        request = http.call_args.args[0]
        wire = json.loads(request.data)
        self.assertEqual(request.full_url, "https://api.openai.com/v1/chat/completions")
        self.assertEqual(wire["response_format"], {"type": "json_schema", "json_schema": {
            "name": "test", "strict": True, "schema": schema,
        }})

    def test_memory_correction_and_recent_view_are_child_scoped(self):
        with MemoryService.from_sqlite(":memory:") as memory:
            for child in (1, 2):
                memory.record_feedback(Feedback(child, "2026-11-01", "full", 4, 4, 5),
                                       content_id="demo-l1-colors", minutes=10)
                memory.record_feedback(Feedback(child, PLAN_DATE, "full", 4, 4, 5), event_id="start")
            corrected = Feedback(1, PLAN_DATE, "partial", 4, 3, 2)
            self.assertTrue(memory.replace_feedback(corrected, content_id="demo-l1-animals", minutes=10))
            self.assertFalse(memory.replace_feedback(corrected, content_id="demo-l1-animals", minutes=10))
            self.assertFalse(memory.replace_feedback(Feedback(1, "2026-11-15", "full", 4, 4, 4)))
            child_one = memory.get_context(1, PLAN_DATE)
            self.assertEqual(len(child_one["history"]), 2)
            self.assertEqual([row["comprehension"] for row in child_one["recent_history"]], [2])
            self.assertEqual(memory.get_context(2, PLAN_DATE)["recent_history"][0]["comprehension"], 5)
            self.assertEqual(memory.delete_feedback(1, PLAN_DATE), 1)
            self.assertEqual(memory.get_context(1, PLAN_DATE)["recent_history"], [])
