"""Compose coaching with a case-specific vocabulary and immutable card actions."""
from datetime import timedelta

from .contracts import iso_date
from ai.llm import complete, object_schema

OPENERS = {
    "A": (
        "오늘 활동을 마친 뒤 아이의 반응을 기록해 주셨어요.",
        "오늘 활동에서 아이가 반응한 순간을 기억해 두고 같은 흐름으로 이어가 보세요.",
    ),
    "B": (
        "오늘은 어려웠던 부분을 한 가지 골라 부모가 먼저 천천히 보여 주세요.",
        "다음에는 같은 활동에서 쉬운 예를 하나 골라 짧게 함께 연습해 보세요.",
    ),
    "C": (
        "오늘 기록을 바탕으로 활동 방식과 다음 학습의 부담을 살펴봤어요.",
        "부모님이 남겨 주신 반응과 요청을 참고해 다음 활동을 살펴봤어요.",
    ),
}


def generate_opening(llm, result, request, memory_summary):
    # The model composes from approved sentences. Card mutations, references, and
    # sensitive referrals stay in the deterministic agent.
    schema = object_schema(case={"type": "string", "enum": [result.case]},
                           body={"type": "string", "enum": list(OPENERS[result.case])})
    fields = ("completion", "satisfaction", "interest", "comprehension")
    cutoff = (iso_date(request.feedback.date) - timedelta(days=7)).isoformat()
    data = {
        "case": result.case,
        "feedback": {key: getattr(request.feedback, key) for key in fields},
        "recent_history": [{key: getattr(row, key) for key in fields}
                           for row in sorted(request.history, key=lambda row: row.date)
                           if row.date >= cutoff and not row.rest_day],
        "memory_summary": memory_summary,
        "adjustment_type": result.adjust["type"],
        "catalog_evidence": result.evidence,
    }
    response = complete(llm, "coach_message", "Select the best Korean opening for the fixed case given the "
                        "feedback, learning history and catalog context. Return the supplied case.", data, schema)
    return response["body"]
