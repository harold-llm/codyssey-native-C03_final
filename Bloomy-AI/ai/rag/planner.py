# pyright: reportMissingImports=false, reportMissingTypeStubs=false, reportUnknownParameterType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportUnknownMemberType=false, reportMissingParameterType=false, reportAny=false, reportAttributeAccessIssue=false, reportUnannotatedClassAttribute=false, reportUnusedParameter=false, reportUnknownLambdaType=false, reportImplicitStringConcatenation=false
"""Retrieve evidence and compose a grounded plan."""
from dataclasses import replace
from datetime import date, timedelta

from ai.contracts import RecommendationResult
from ai.llm import LLMError, complete, object_schema

from .ingest import load_catalog, make_chunks, validate_catalog
from .retriever import LocalRetriever
from .validator import validate_result


class InsufficientCatalogError(ValueError):
    """No safe candidate exists; caller must obtain more catalog material."""


class RecommendationEngine:
    def __init__(self, catalog, retriever=None, memory=None, llm=None, *, reviewed_only=False,
                 deprioritized=None):
        entries = validate_catalog(catalog)
        # '앱 전체·시리즈 전체' 같은 묶음 항목: 구체적인 후보가 충분하면 빼서 막연한 카드를 줄인다
        self.deprioritized = set(deprioritized or ())
        self.catalog = [item for item in entries if item.get("review_status") == "reviewed"] if reviewed_only else entries
        chunks = make_chunks(self.catalog)
        self._items = {item["id"]: item for item in self.catalog}
        self._chunks = {chunk["chunk_id"]: chunk for chunk in chunks}
        self.retriever = retriever or LocalRetriever(self.catalog, chunks)
        self.memory = memory
        self.llm = llm

    @classmethod
    def from_file(cls, path, *, memory=None, llm=None, reviewed_only=False, deprioritized=None):
        return cls(load_catalog(path), memory=memory, llm=llm, reviewed_only=reviewed_only,
                   deprioritized=deprioritized)

    def search(self, request):
        hits = []
        for hit in self.retriever.search(request):
            item = self._items.get(hit["item"]["id"])
            chunk = self._chunks.get(hit["chunk_id"])
            if item is None or chunk is None or chunk["content_id"] != item["id"]:
                continue
            # 보유 교재는 설정 시간보다 길어도 허용 (카드 분량은 설정 시간으로 맞춘다)
            if (item["age_min"] <= request.age <= item["age_max"] and item["level"] == request.base_level
                    and (hit["owned"] or item["session_minutes"] <= request.session_minutes)):
                hits.append({**hit, "item": item, "excerpt": chunk["text"], "source": chunk["source"]})
        if self.deprioritized:
            specific = [h for h in hits if h["owned"] or h["item"]["id"] not in self.deprioritized]
            if len({h["item"]["id"] for h in specific}) >= 3:
                hits = specific
        return hits

    def recommend(self, request, *, child_id=None):
        context = None
        if self.memory is not None:
            if child_id is None:
                raise ValueError("child_id is required when memory is enabled")
            request, context = self.memory.enrich_recommendation(request, child_id)
        hits = self.search(replace(request, top_k=100) if context else request)
        if context:
            preferred = set(context["summary"]["preferred_content_ids"])
            weak = set(context["summary"]["weak_content_ids"])
            hits = sorted(hits, key=lambda h: (not h["owned"], h["item"]["id"] in weak,
                                               h["item"]["id"] not in preferred, -h["score"], h["item"]["id"]))[:request.top_k]
        if request.exposure == "none" or (request.exposure_months is not None and request.exposure_months <= 2):
            hits.sort(key=lambda hit: (not hit["owned"], hit["item"]["session_minutes"]))
        if not hits:
            raise InsufficientCatalogError("나이·단계·학습 시간에 맞는 자료가 없습니다. 카탈로그를 보완해 주세요.")
        warnings = []
        if len(hits) < 5:
            warnings.append("적합한 후보가 5개 미만이므로 반복 학습 비중이 높습니다.")
        if request.owned_materials and not any(h["owned"] for h in hits):
            warnings.append("조건에 맞는 보유 교재를 찾지 못했습니다. 구매를 자동으로 권하지 않습니다.")
        if any(h["item"].get("review_status") != "reviewed" for h in hits):
            warnings.append("미검수 자료가 포함된 개발용 초안입니다. 실사용 전 전문가 검수가 필요합니다.")
        selected = [hits[i % len(hits)] for i in range(20)]
        strategy = "조건에 맞는 보유 교재를 먼저 배치하고, 검색 관련도 순으로 순환합니다."
        version = "bloomy-rag-local-v1"
        if self.llm is not None:
            try:
                selected, strategy = self._generate_schedule(request, hits, context)
                version = "bloomy-rag-llm-v1"
            except LLMError:
                warnings.append("LLM 계획 검증 또는 호출에 실패해 로컬 검색 기반 초안을 사용했습니다.")
        days = []
        day_details = []
        current = date.fromisoformat(request.start_date)
        while len(days) < 20:
            if current.weekday() < 5:
                hit = selected[len(days)]
                item = hit["item"]
                days.append({"date": current.isoformat(), "content_id": item["id"],
                             "task": item["task"], "minutes": min(item["session_minutes"], request.session_minutes),
                             "check_point": item["check_point"]})
                day_details.append({"date": current.isoformat(), "content_id": item["id"], "title": item["title"],
                             "learning_goal": item.get("learning_goal", {
                                 "listening": "영어 소리를 듣고 반응하기", "speaking": "짧게 영어로 표현하기",
                                 "reading": "글자와 소리 또는 뜻을 연결하기", "writing": "글자나 단어를 써 보기",
                             }[item["skill"]]),
                             "recommendation_reason": (
                                 ("보유 교재. " if hit["owned"] else "") + item["expert_note"]
                             )})
            current += timedelta(days=1)
        titles = " · ".join(h["item"]["title"] for h in {hit["item"]["id"]: hit for hit in selected}.values())
        explanation = (f"초기 L{request.base_level}은 확정 진단이 아닌 가설입니다. {titles}을(를) 근거로 "
                       f"하루 최대 {request.session_minutes}분, 평일 20회 반복 학습을 제안합니다. "
                       f"{strategy} "
                       "부모는 각 카드의 활동과 확인 포인트를 따라 반응을 기록해 주세요. "
                       "2주간의 실제 반응으로 다음 계획을 조정하며, 부모 승인 후 활성화합니다.")
        evidence = [{"content_id": h["item"]["id"], "title": h["item"]["title"],
                     "chunk_id": h["chunk_id"], "excerpt": h["excerpt"], "source": h["source"],
                     "link": h["item"]["link"], "score": h["score"], "owned": h["owned"]} for h in hits]
        result = RecommendationResult(days, explanation, request.base_level, evidence, warnings, engine_version=version, day_details=day_details)
        if context:
            result.memory_context = {"child_id": child_id, "as_of": context["as_of"],
                                     "preferences": context["preferences"], "summary": context["summary"]}
            if context["summary"]["record_days"]:
                result.explanation += " 아이별 누적 반응을 참고해 선호 자료를 우선하고 반복 어려움 자료의 순위를 낮췄습니다. 단계는 자동 변경하지 않습니다."
        return validate_result(result, request, self.catalog)

    def _generate_schedule(self, request, hits, context):
        lookup = {hit["item"]["id"]: hit for hit in hits}
        strategies = [
            "익숙한 활동을 반복하며 부모가 아이의 반응을 관찰할 기회를 마련합니다.",
            "같은 목표를 여러 활동으로 연습하고 부모가 선호하는 방식을 관찰합니다.",
        ]
        schema = object_schema(
            content_ids={"type": "array", "items": {"type": "string", "enum": list(lookup)}},
            strategy={"type": "string", "enum": strategies},
        )
        data = {
            "profile": {"age": request.age, "base_level": request.base_level, "goal": request.goal,
                        "favorite_topics": request.favorite_topics, "session_minutes": request.session_minutes,
                        "exposure_months": request.exposure_months, "exposure": request.exposure},
            "retrieved_catalog": hits,
            "memory": {key: context["summary"][key] for key in ("preferred_content_ids", "weak_content_ids")}
            if context else {},
        }
        output = complete(
            self.llm, "curriculum", "Compose exactly 20 weekday activities for four learning weeks. "
            "Return their ordered catalog IDs and choose a strategy matching the sequence. Use only retrieved IDs. "
            "Start with an owned item when available. Consider exposure, interests and previous responses.", data, schema,
        )
        selected = [lookup[item_id] for item_id in output["content_ids"]]
        if len(selected) != 20 or (any(hit["owned"] for hit in hits) and not selected[0]["owned"]):
            raise LLMError("invalid schedule length or ownership priority")
        return selected, output["strategy"]
