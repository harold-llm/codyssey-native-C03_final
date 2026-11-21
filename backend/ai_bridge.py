"""Bloomy-AI 모듈 브리지 — RAG 커리큘럼 추천 연결.

`Bloomy-AI/`의 RAG 엔진을 백엔드 계획 생성에 연결한다. 모듈이 없거나
추천이 실패하면 `None`을 반환해 호출부가 기존 규칙 기반 생성기로 폴백한다.
(운영 안정성: AI 모듈 부재/오류가 서비스 전체를 막지 않는다.)
"""
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false
from __future__ import annotations

import datetime as dt
import importlib.util
import os
import sys
from typing import TYPE_CHECKING, cast

HERE = os.path.dirname(os.path.abspath(__file__))
AI_ROOT = os.path.normpath(os.path.join(HERE, "..", "Bloomy-AI"))
CATALOG_PATH = os.path.join(HERE, "data", "catalog.json")

if AI_ROOT not in sys.path:
    sys.path.insert(0, AI_ROOT)

if TYPE_CHECKING:
    from ai.rag import RecommendationEngine

_rag: RecommendationEngine | None = None
_available: bool | None = None


def available() -> bool:
    """Bloomy-AI RAG 모듈을 import할 수 있는지 (1회 캐시)."""
    global _available
    if _available is None:
        _available = importlib.util.find_spec("ai.rag") is not None
    return _available


def _engine() -> RecommendationEngine:
    global _rag
    if _rag is None:
        from ai.rag import RecommendationEngine
        _rag = RecommendationEngine.from_file(CATALOG_PATH)
    return _rag


def generate_plan(
    child: dict[str, object], goal: str = "듣기",
) -> dict[str, object] | None:
    """RAG로 4주 계획 생성. 실패/미가용 시 None (호출부가 규칙 기반 폴백)."""
    if not available():
        return None
    try:
        from ai.backend_adapter import recommendation_request
        # RAG는 session_minutes 10/15/20만 지원 → 큰 값은 20으로 캡
        child_for_rag = dict(child)
        raw_sl = child.get("session_length")
        try:
            sl = int(cast("int | float | str", raw_sl)) if raw_sl is not None else 10
        except (TypeError, ValueError):
            sl = 10
        child_for_rag["session_length"] = min(sl, 20)
        request = recommendation_request(
            child_for_rag, dt.date.today().isoformat(), goal=goal)
        result = _engine().recommend(request)
        payload = result.to_backend_payload()
        return {
            "cards": payload["days"],
            "explanation": payload["explanation"],
            "base_level": payload["base_level"],
        }
    except Exception:  # noqa: BLE001
        return None
