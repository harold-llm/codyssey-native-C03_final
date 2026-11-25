"""Catalog and RAG tools; never write a backend plan or approve it."""
from dataclasses import asdict

from ai.contracts import RecommendationRequest


class CoachTools:
    def __init__(self, rag_engine):
        self.rag = rag_engine
        self.catalog = {item["id"]: item for item in rag_engine.catalog}

    def get_detail(self, content_id):
        try:
            return self.catalog[content_id]
        except KeyError as exc:
            raise ValueError(f"unknown content_id: {content_id}") from exc

    def search(self, request, level=None):
        query = RecommendationRequest(
            age=request.age, base_level=level if level is not None else request.base_level,
            start_date=request.feedback.date, goal=request.goal + " " + request.feedback.memo,
            session_minutes=request.session_minutes, owned_materials=request.owned_materials,
            favorite_topics=request.favorite_topics, top_k=100,
        )
        return self.rag.search(query)

    def card_for(self, original, item, minutes=None):
        return {**asdict(original), "content_id": item["id"], "task": item["task"],
                "check_point": item["check_point"],
                "minutes": item["session_minutes"] if minutes is None else minutes}

    def evidence(self, item):
        return {"content_id": item["id"], "title": item["title"],
                "source": item["trust_source"], "link": item["link"], "excerpt": item["expert_note"]}
