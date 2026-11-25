"""Pure decision function: rest day, referral, C, B, then default A."""
from datetime import timedelta

from .contracts import iso_date
from .intent import INTENTS


def decide(feedback, history=(), intent="none"):
    if intent not in INTENTS:
        raise ValueError("invalid intent")
    flags = {"difficulty_adjust": False, "expert_referral": False, "interest_dip": False}
    if feedback.rest_day:
        return {"case": "SKIP", "flags": flags, "reasons": ["휴식일 — 메시지·조정 없음"], "low_interest_streak": 0}
    yesterday = (iso_date(feedback.date) - timedelta(days=1)).isoformat()
    previous = next((r for r in history if r.date == yesterday and not r.rest_day), None)
    streak = (2 if previous and previous.interest <= 2 else 1) if feedback.interest <= 2 else 0
    is_b = feedback.completion in ("partial", "none") or feedback.comprehension < 3
    flags["interest_dip"] = streak == 1
    if intent == "out_of_scope":
        case, reasons = "C", ["학습 범위 밖 문의 — 전문가 안내 우선"]
        flags["expert_referral"] = True
    elif intent in ("question", "change_request") or streak >= 2:
        case, reasons = "C", []
        if intent in ("question", "change_request"):
            reasons.append(f"메모 의도 {intent}")
        if streak >= 2:
            reasons.append("캘린더 인접 2일 흥미≤2")
        flags["difficulty_adjust"] = is_b
        if is_b:
            reasons.append("B 조건 중복 — 부담 완화 포함")
    elif is_b:
        case, reasons = "B", ["미완료 또는 이해도<3"]
    else:
        case, reasons = "A", ["C·B 미해당 — 계획 유지"]
    return {"case": case, "flags": flags, "reasons": reasons, "low_interest_streak": streak}
