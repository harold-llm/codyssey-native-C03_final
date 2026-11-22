"""Bloomy-AI 모듈 브리지 — RAG 커리큘럼 추천 연결.

`Bloomy-AI/`의 RAG 엔진을 백엔드 계획 생성에 연결한다. 모듈이 없거나
추천이 실패하면 `None`을 반환해 호출부가 기존 규칙 기반 생성기로 폴백한다.
(운영 안정성: AI 모듈 부재/오류가 서비스 전체를 막지 않는다.)
"""
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false
from __future__ import annotations

import importlib.util
import os
import sys
from typing import TYPE_CHECKING, cast

import clock

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
        from ai.llm import client_from_env
        from ai.rag import RecommendationEngine
        # LLM(Claude/OpenAI)을 넘겨 RAG가 계획·학습방법을 생성하게 한다.
        # 키가 없으면 None → 템플릿 기반 초안으로 폴백.
        _rag = RecommendationEngine.from_file(CATALOG_PATH, llm=client_from_env())
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
            child_for_rag, clock.today().isoformat(), goal=goal)
        result = _engine().recommend(request)
        payload = result.to_backend_payload()
        global _last_plan_error
        _last_plan_error = None
        return {
            "cards": payload["days"],
            "explanation": payload["explanation"],
            "base_level": payload["base_level"],
        }
    except Exception as exc:  # noqa: BLE001
        # 조용히 폴백하면 운영에서 원인을 알 수 없다 → 로그와 health에 남긴다.
        _last_plan_error = f"{type(exc).__name__}: {exc}"[:300]
        print(f"[bloomy-ai] RAG plan failed, rule fallback: {_last_plan_error}")
        return None


_last_plan_error: str | None = None


def rag_status() -> dict[str, object]:
    """/api/health용: RAG 엔진을 실제로 만들 수 있는지 + 최근 계획 생성 실패 사유."""
    status: dict[str, object] = {"importable": available(), "last_plan_error": _last_plan_error}
    if not available():
        status["engine"] = "unavailable"
        return status
    try:
        engine = _engine()
        status["engine"] = "ok"
        status["catalog_items"] = len(engine.catalog)
        status["llm"] = type(engine.llm).__name__ if engine.llm is not None else None
    except Exception as exc:  # noqa: BLE001
        status["engine"] = f"error: {type(exc).__name__}: {exc}"[:300]
    return status


# ---------------------------------------------------------------------------
# 핵심 AI ② — 코치 Agent 보강형 연결
#
# 피드백 판정·카드 조정·DB 반영·코칭 메시지는 backend/coach.py가 그대로 담당한다.
# Agent는 같은 피드백을 읽기 전용으로 검토해 RAG 근거(evidence), 질문에 대한 자료
# 안내, 부모 변경 요청의 승인 대기 후보, 가드레일 경고를 덧붙인다.
# Agent가 실패해도 피드백 응답은 영향을 받지 않는다 (None 반환).
# ---------------------------------------------------------------------------

_agent_rag: RecommendationEngine | None = None
ADVICE_PREFIX = "자료 안내:"


class _FixedIntent:
    """백엔드가 이미 분류한 의도를 그대로 넘긴다 (LLM 중복 호출·판정 불일치 방지)."""

    def __init__(self, intent: str, reason: str) -> None:
        self.intent = intent
        self.reason = reason or "백엔드 의도 분류"

    def classify(self, _memo: str) -> dict[str, str]:
        return {"intent": self.intent, "reason": self.reason, "version": "backend-intent"}


def _agent_engine() -> RecommendationEngine:
    """Agent 전용 RAG 엔진 — LLM 없이 로컬 TF-IDF만 사용 (추가 API 비용 없음)."""
    global _agent_rag
    if _agent_rag is None:
        from ai.rag import RecommendationEngine
        _agent_rag = RecommendationEngine.from_file(CATALOG_PATH)
    return _agent_rag


def coach_review(
    child: dict[str, object],
    feedback: dict[str, object],
    *,
    intent: str,
    intent_reason: str,
    today_card: dict[str, object] | None,
    next_card: dict[str, object] | None,
    history: list[dict[str, object]],
) -> dict[str, object] | None:
    """코치 Agent 검토 결과. 미가용·입력 불일치·오류 시 None."""
    if not available() or feedback.get("rest_day"):
        return None
    try:
        from ai.agent import CoachAgent
        from ai.backend_adapter import coaching_request

        engine = _agent_engine()
        child_for_ai = dict(child)
        raw_sl = child.get("session_length")
        try:
            sl = int(cast("int | float | str", raw_sl)) if raw_sl is not None else 10
        except (TypeError, ValueError):
            sl = 10
        child_for_ai["session_length"] = 20 if sl >= 20 else (15 if sl >= 15 else 10)
        # 백엔드 카드는 승인된 계획에서만 조회된다 → 카드가 있으면 approved
        plan_status = "approved" if (today_card or next_card) else "draft"
        request = coaching_request(
            child_for_ai, feedback, catalog=engine.catalog, plan_status=plan_status,
            today=today_card, next_card=next_card, history=history,
        )
        agent = CoachAgent(engine, intent_classifier=_FixedIntent(intent, intent_reason))
        result = agent.coach(request).to_dict()
        message = cast("str", result.get("message") or "")
        advice = next((line[len(ADVICE_PREFIX):].strip() for line in message.splitlines()
                       if line.startswith(ADVICE_PREFIX)), None)
        adjust = cast("dict[str, object]", result["adjust"])
        proposal = adjust.get("proposal") if adjust.get("requires_parent_approval") else None
        return {
            "case": result["case"],
            "advice": advice,
            "evidence": result["evidence"],
            "proposal": proposal,
            "warnings": result["warnings"],
            "agent_version": result["prompt_version"],
        }
    except Exception as exc:  # noqa: BLE001
        print(f"[bloomy-ai] coach_review skipped: {exc}")
        return None
