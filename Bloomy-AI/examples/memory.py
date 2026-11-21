"""Persist local memory and reuse it in RAG and Agent. Safe to repeat."""
import argparse
import json
from pathlib import Path
import sys

from ai.agent import CoachAgent, CoachRequest, Feedback, LearningCard
from ai.contracts import RecommendationRequest
from ai.memory import MemoryService
from ai.rag import RecommendationEngine


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=root / "data" / "local" / "memory-demo.sqlite3")
    args = parser.parse_args()
    with MemoryService.from_sqlite(args.db) as memory:
        # Dedicated demonstration DB and synthetic child; do not use a live child ID.
        existing = memory.get_context(1, "2026-11-18")
        if existing["preferences"]["favorite_topics"] != ["동물"]:
            memory.set_preferences(1, "2026-11-01", favorite_topics=["동물"])
        memory.record_feedback(Feedback(1, "2026-11-17", "full", 4, 2, 4),
                               content_id="demo-animal-001", minutes=10)
        rag = RecommendationEngine.from_file(root / "data" / "catalog" / "sample.json", memory=memory)
        plan = rag.recommend(RecommendationRequest(age=5, base_level=2, start_date="2026-11-18"), child_id=1)
        item = rag.catalog[0]
        today = LearningCard(1, "2026-11-18", item["id"], item["task"], 10, item["check_point"])
        next_card = LearningCard(1, "2026-11-19", item["id"], item["task"], 10, item["check_point"])
        result = CoachAgent(rag).coach(CoachRequest(
            child_id=1, age=5, base_level=2, plan_status="approved",
            feedback=Feedback(1, "2026-11-18", "full", 4, 2, 4),
            today_card=today, next_card=next_card,
        ))
        context = memory.get_context(1, "2026-11-18")
        print(json.dumps({"database": str(args.db), "records": len(context["history"]),
                          "rag_first_content": plan.days[0]["content_id"],
                          "coach_case": result.case, "adjustment": result.adjust,
                          "summary": context["summary"], "preferences": context["preferences"]},
                         ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
