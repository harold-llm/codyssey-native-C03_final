"""RAG draft -> explicit approval boundary -> local feedback coach demo."""
import json
import sys
from pathlib import Path

from ai.agent import CoachAgent, CoachRequest, Feedback, LearningCard
from ai.contracts import RecommendationRequest
from ai.rag import RecommendationEngine


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    catalog = Path(__file__).resolve().parents[1] / "data" / "catalog" / "sample.json"
    rag = RecommendationEngine.from_file(catalog)
    plan = rag.recommend(RecommendationRequest(age=5, base_level=2, start_date="2026-11-18"))
    today, next_card = [LearningCard(child_id=1, **day) for day in plan.days[:2]]
    # Demonstration only: the real backend supplies approval verified from storage.
    request = CoachRequest(
        child_id=1, age=5, base_level=2,
        feedback=Feedback(child_id=1, date=today.date, completion="partial",
                          satisfaction=3, interest=3, comprehension=2,
                          memo="어떻게 도와줄까요?"),
        today_card=today, next_card=next_card, plan_status="approved",
    )
    result = CoachAgent(rag).coach(request)
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
