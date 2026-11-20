"""Opt-in provider smoke tests; only synthetic scenarios leave the process."""
import unittest

from ai.llm import OpenAIClient
from examples.ai_demo import run_demo


class LiveProviderTests(unittest.TestCase):
    def test_curricula_intent_and_coach(self):
        llm = OpenAIClient.from_env()
        if llm is None:
            self.skipTest("OPENAI_API_KEY is unavailable")
        result = run_demo(llm)
        for plan in result["plans"]:
            self.assertEqual(plan["engine_version"], "bloomy-rag-llm-v1", plan["warnings"])
        self.assertEqual(result["coach"]["intent_version"], "bloomy-intent-llm-v1")
        self.assertEqual(result["coach"]["case"], "C")
        self.assertEqual(result["coach"]["prompt_version"], "bloomy-coach-llm-v1", result["coach"]["warnings"])
