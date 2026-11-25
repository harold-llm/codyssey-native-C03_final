"""Run from project root: python -m examples.recommend"""
import json
import sys
from pathlib import Path

from ai.contracts import RecommendationRequest
from ai.rag import RecommendationEngine


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    catalog = Path(__file__).resolve().parents[1] / "data" / "catalog" / "sample.json"
    request = RecommendationRequest(age=5, base_level=2, start_date="2026-11-17",
                                    goal="듣기", favorite_topics=("동물",))
    result = RecommendationEngine.from_file(catalog).recommend(request)
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
