"""분기 판정 규칙 엔진 (01 §5.4, §6.3-2).

**LLM을 거치지 않는 순 규칙**이다: 메모 의도 *라벨*(6.3 분류기 출력)과
피드백 숫자(완료도·이해도·흥미)를 코드로 소비해 A/B/C를 선판정한다.
메시지 생성 LLM은 이 라벨만 받는다 — "분기를 규칙으로 고정한다"는 설계의
정직함을 위해 유일한 LLM 판단(메모 의도 분류)은 6.3의 별도 스키마-제약
호출로 분리되어 있다.

우선순위: **C → B → A**. A는 디폴트(C·B 모두 미해당 → A).
이 구조면 "어느 케이스에도 안 맞는 공백"과 "두 케이스가 동시에 걸리는
중복"이 모두 자동 해소된다 (5.4).

판정 조건 (5.4 표):
  C  memo_intent ∈ {question, change_request} 또는 흥미≤2 **2일 연속**
  B  완료도 ∈ {일부, 못 함}(partial/none) 또는 이해도<3   (C 미해당 전제)
  A  그 외(디폴트)

공백 해소: "잘 따라옴 + 이해도 4 + 흥미 2(단 하루)"는 C의 2일 연속을
만족하지 못해 A로 수렴한다. 대신 흥미 저하를 memory에 기록해
(interest_dip 플래그), 다음 날에도 흥미≤2면 2일째에 C로 전환한다 —
단발 과반응 방지.

중복 해소: B와 C가 동시에 걸리면 C가 우선이며, difficulty_adjust 플래그를
달아 조정 안에 B의 난이도 조정을 포함하도록 한다.

휴식일: rest_day면 분기 자체를 건너뜀(SKIP) — 메시지 미생성, 성취 분모
제외 (5.4).
"""
import datetime as dt
from typing import TypedDict

INTENTS = ("none", "question", "change_request", "out_of_scope")

COMPLETIONS = ("full", "partial", "none")  # 잘 따라옴 / 일부 / 못 함


class Decision(TypedDict):
    case: str
    intent: str
    flags: dict[str, bool]
    low_interest_streak: int
    reasons: list[str]


def decide(
    *, date: str, completion: str, interest: int, comprehension: int,
    intent: str = "none", prev: dict[str, object] | None = None,
    rest_day: bool = False,
) -> Decision:
    """분기 판정. 순수 함수 — DB·LLM 접근 없음.

    date: 피드백 날짜 "YYYY-MM-DD" (2일 연속 판정에 사용)
    completion: "full" | "partial" | "none"
    interest, comprehension: 1~5 int
    intent: 6.3 분류기 라벨 (none|question|change_request|out_of_scope)
    prev: **캘린더 전일** 기록 dict (최소 {"date", "interest"}).
          호출부는 전일과 인접한 마지막 기록만 넘긴다. 없으면 None.
    rest_day: 휴식일 표시

    returns:
      {
        "case": "A"|"B"|"C"|"SKIP",
        "intent": <라벨>,
        "flags": {
          "difficulty_adjust": bool,  # C+B 중복 → 조정 안에 난이도 조정 포함
          "expert_referral": bool,    # out_of_scope → 전문가 상담 전환 (6.6)
          "interest_dip": bool,       # 단발 흥미 저하 → memory 기록
        },
        "low_interest_streak": 0|1|2,
        "reasons": [str, ...],        # 감사용 판정 근거
      }
    """
    if rest_day:
        return _result("SKIP", intent, 0,
                       reasons=["휴식일 — 분기 건너뜀 (메시지 미생성, 성취 분모 제외)"])
    if intent not in INTENTS:
        intent = "none"

    # --- 흥미 2일 연속: 전일(캘린더 인접) 기록도 흥미≤2여야 성립 ---
    streak = 1 if interest <= 2 else 0
    if streak and prev is not None:
        prev_date = None
        today = None
        try:
            prev_date = dt.date.fromisoformat(str(prev.get("date")))
            today = dt.date.fromisoformat(str(date))
        except (TypeError, ValueError):
            prev_date = None
            today = None
        if (
            prev_date is not None
            and today is not None
            and (today - prev_date).days == 1
        ):
            raw_interest = prev.get("interest", 0)
            if isinstance(raw_interest, int | float | str):
                try:
                    if int(raw_interest) <= 2:
                        streak = 2
                except (TypeError, ValueError):
                    pass

    intent_c = intent in ("question", "change_request", "out_of_scope")
    is_c = intent_c or streak >= 2
    is_b = completion in ("partial", "none") or comprehension < 3

    flags = {
        "difficulty_adjust": False,
        "expert_referral": intent == "out_of_scope",
        "interest_dip": streak == 1,
    }
    reasons: list[str] = []

    if is_c:
        if intent_c:
            reasons.append(f"메모 의도 {intent} → 수정·질문·형식 변경")
        if streak >= 2:
            reasons.append("흥미≤2 2일 연속 → 소재 교체·휴식일 제안")
        # 중복 해소: B 조건도 동시에 걸리면 난이도 조정을 조정 안에 포함 (5.4)
        if is_b:
            flags["difficulty_adjust"] = True
            reasons.append("B 조건 동시 성립(완료도·이해도) → 조정 안에 난이도 조정 포함")
        return _result("C", intent, streak, flags, reasons)

    if is_b:
        if completion in ("partial", "none"):
            reasons.append(f"완료도 {completion} → 부분 미달")
        if comprehension < 3:
            reasons.append(f"이해도 {comprehension} < 3 → 부분 미달")
        return _result("B", intent, streak, flags, reasons)

    reasons.append("C·B 모두 미해당 → 디폴트 A(순조)")
    if streak == 1:
        reasons.append("단발 흥미 저하 — memory 기록 후 내일 재평가")
    return _result("A", intent, streak, flags, reasons)


def _result(
    case: str, intent: str, streak: int,
    flags: dict[str, bool] | None = None,
    reasons: list[str] | None = None,
) -> Decision:
    return {
        "case": case,
        "intent": intent,
        "flags": flags or {
            "difficulty_adjust": False,
            "expert_referral": False,
            "interest_dip": False,
        },
        "low_interest_streak": streak,
        "reasons": reasons or [],
    }
