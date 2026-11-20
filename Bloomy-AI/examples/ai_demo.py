"""Demonstrate L1/L3 curricula and coaching with synthetic profiles."""
import argparse
import json
from pathlib import Path
import sys

from ai.agent import CoachAgent, CoachRequest, Feedback, LearningCard
from ai.contracts import RecommendationRequest
from ai.llm import OpenAIClient
from ai.rag import RecommendationEngine
from ai.rag.ingest import load_catalog

CATALOG = Path(__file__).resolve().parents[1] / "data" / "catalog"


def demo_engine(llm=None):
    items = load_catalog(CATALOG / "sample.json") + load_catalog(CATALOG / "sample-extra.json")
    return RecommendationEngine(items, llm=llm)


def run_demo(llm=None):
    rag = demo_engine(llm)
    profiles = (
        RecommendationRequest(5, 1, "2026-11-16", favorite_topics=("동물",), exposure_months=0),
        RecommendationRequest(7, 3, "2026-11-16", goal="파닉스", session_minutes=15, exposure_months=18),
    )
    plans = [rag.recommend(profile) for profile in profiles]
    plan = plans[0]
    today, next_card = [LearningCard(child_id=1, **card) for card in plan.days[:2]]
    coach = CoachAgent(rag).coach(CoachRequest(
        child_id=1, age=5, base_level=1,
        feedback=Feedback(1, today.date, "partial", 4, 3, 2, "그림을 먼저 보여 주면 어떨까요?"),
        today_card=today, next_card=next_card, plan_status="approved",
    ))
    return {
        "synthetic_demo": True,
        "simulated_plan_approval": True,
        "plans": [{"age": profile.age, **plan.to_dict()} for profile, plan in zip(profiles, plans)],
        "coach": coach.to_dict(),
    }


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Call the real provider using synthetic data")
    args = parser.parse_args()
    llm = OpenAIClient.from_env() if args.live else None
    if args.live and llm is None:
        parser.error("--live requires OPENAI_API_KEY")
    result = run_demo(llm)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.live and (
        any(plan["engine_version"] != "bloomy-rag-llm-v1" for plan in result["plans"])
        or result["coach"]["prompt_version"] != "bloomy-coach-llm-v1"
        or result["coach"]["intent_version"] != "bloomy-intent-llm-v1"
    ):
        parser.exit(1, "Live provider did not complete all structured calls. Check warnings in the report.\n")


if __name__ == "__main__":
    main()
