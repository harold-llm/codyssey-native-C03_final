"""AI 코치 (01 §6.3 3단계 분리, §6.6 가드레일).

출력은 3단계로 분리되고, 각 LLM 출력은 JSON 스키마로 검증한다:

  1. 메모 의도 분류  classify_memo_intent(memo)
     — 별도 LLM 호출, 스키마 {"intent": 4종, "reason"}로 제한.
       라벨만 반환하고 케이스·메시지를 생성하지 못한다(6.3-1).
       검증 실패 1회 재시도 후에도 실패하면 키워드 규칙으로 폴백(6.6).
  2. 분기 판정  branch.decide()
     — 순수 규칙 코드. LLM을 거치지 않는다 (5.4, 6.3-2).
  3. 메시지 생성  build_message()
     — 규칙 판정된 case를 **무조건 우선**한다(LLM이 case를 바꿀 수 없음).
       스키마 {case, body, tomorrow_card, confidence_sentence?}.
       confidence_sentence는 confidence_ok(데이터 조건, 6.6)가 True일 때만
       수용하고, 아니면 폐기한다. 어떤 주에도 고정 삽입하지 않는다.

OPENAI_API_KEY가 없으면 내장 룰베이스 코치가 동일한 분기·조정 규칙으로
동작한다 (오프라인/데모 모드, 스모크 테스트 결정성 보장).
"""
import datetime as dt
import io
import json
import os
import re
import urllib.request
from collections.abc import Callable
from itertools import pairwise
from typing import TypedDict, cast

import branch
import catalog
import clock
import curriculum

import store

RULES_VERSION = "bloomy-coach-v2-rules"
INTENT_VERSION = "bloomy-intent-v2"
LLM_VERSION = "bloomy-coach-v2-llm"
AI_LABEL = "AI가 작성한 코칭 메시지입니다."
ACCUMULATION = ("100% 쉽게 느껴지지 않아도, 하루하루 쌓이면 어느 순간 "
                "말문이 트이듯 한 단계 올라가요.")

COMPLETION_KO = {"full": "잘 따라옴", "partial": "일부", "none": "못 함"}


# ---------------------------------------------------------------------------
# 1단계 — 메모 의도 분류 (6.3: 별도 스키마-제약 호출)
# ---------------------------------------------------------------------------

INTENT_SYSTEM = (
    '너는 어린이 영어 학습 피드백 메모의 의도 분류기다. '
    '메시지나 케이스를 만들지 않는다. 라벨 하나만 분류한다.\n'
    "라벨 정의:\n"
    "- none: 단순 감상·칭찬·기록. 조치 불필요\n"
    "- question: 공부 방법에 대한 질문 (예: '왜 이렇게 읽어줘요?')\n"
    "- change_request: 콘텐츠·난이도·형식 변경 요청 (예: '쉬운 걸로 바꿔주세요')\n"
    "- out_of_scope: 아이 건강·심리·발달 등 학습 범위 밖 (예: '병원에 가볼까요?')\n"
    "반드시 아래 JSON만 반환한다: "
    '{"intent": "none|question|change_request|out_of_scope", "reason": "<1문장>"}'
)

_INTENT_RULES = (
    ("out_of_scope", ("병원", "의사", "열이", "발달", "장애", "심리", "질병", "상담", "약 먹")),
    ("change_request", ("바꿔", "바꾸고", "바뀌", "다른", "쉬운", "어렵", "지루", "너무",
                        "길어", "길게", "짧", "쉬어", "중단", "그만", "교체")),
    ("question", ("왜", "어떻게", "어떡", "무엇", "뭐가", "?", "?")),
)


def _intent_keywords(memo: str) -> tuple[str, str]:
    m = (memo or "").strip()
    for label, keys in _INTENT_RULES:
        for k in keys:
            if k in m:
                return label, f"키워드 '{k}' 매칭"
    return "none", "변경·질문 키워드 없음"


def _strip_fences(raw: str) -> str:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text.removeprefix("json")
    return text.strip()


def _try_llm_intent(memo: str) -> tuple[str, str] | None:
    """LLM으로 의도 분류. 스키마 검증 실패 1회 재시도, 그래도 실패하면 None."""
    for _attempt in (1, 2):
        raw = _call_llm(INTENT_SYSTEM, f"메모: {memo}")
        if not raw:
            return None
        try:
            data = cast("dict[str, object]", json.loads(_strip_fences(raw)))
            intent = data.get("intent")
            if not isinstance(intent, str) or intent not in branch.INTENTS:
                continue
            return intent, str(data.get("reason") or "")[:200]
        except (ValueError, AttributeError):
            continue
    return None


def classify_memo_intent(memo: str) -> tuple[str, str]:
    """(intent, reason) 반환. LLM 없이도 키워드 규칙으로 결정적 동작."""
    m = (memo or "").strip()
    if not m:
        return "none", "메모 없음"
    if _llm_available():
        got = _try_llm_intent(m)
        if got:
            return got
    return _intent_keywords(m)


# ---------------------------------------------------------------------------
# 확신 문구 데이터 조건 (6.6 — 고정 삽입 금지)
# ---------------------------------------------------------------------------

def learned_name(row: dict[str, object]) -> str | None:
    """기록한 날 실제로 한 것: 카드의 권·회차 제목(『…』)이 있으면 그것, 없으면 자료 이름."""
    m = re.search(r"『([^』]+)』", str(row.get("card_task") or ""))
    if m:
        return f"『{m.group(1)}』"
    it = catalog.find_item(row.get("content_id"))
    return it["title"] if it else None


def today_title(child: dict[str, object], rec: dict[str, object], item: catalog.Item | None) -> str:
    """코칭 메시지에 쓸 '오늘 한 것' — 서비스 이름이 아니라 그날 카드의 권·회차."""
    card = store.get_card_for_child(int(cast("int", child["id"])), str(rec.get("date") or "")) if rec.get("date") else None
    name = learned_name({"card_task": card.get("task") if card else "",
                         "content_id": item["id"] if item else None})
    if not name:
        return "오늘 학습"
    return name if name.startswith("『") else f"'{name}'"


# ---------------------------------------------------------------------------
# 칭찬 가이드 — 기록 후 부모에게 "이렇게 칭찬해 주세요" (앱 안 점수·보상 대신 부모가 주는 칭찬)
# ---------------------------------------------------------------------------

PRAISE_GOOD = ("Great job!", "You did it!", "Well done!", "I'm so proud of you!", "High five!",
               "Wow, you remembered!", "Awesome listening!")
PRAISE_TRY = ("Good try!", "Nice try!", "You're doing great!", "Keep going!", "Let's try again tomorrow!")

_TIPS_GOOD = (
    ("무엇을 잘했는지 구체적으로", "\"잘했어\"보다 \"{title} 끝까지 봤네!\"처럼 해낸 일을 콕 집어 말해 주세요."),
    ("끝난 직후에 바로", "활동이 끝나자마자 눈을 맞추고 하이파이브. 시간이 지나면 칭찬과 행동이 이어지지 않아요."),
    ("결과보다 과정", "몇 개 맞혔는지보다 \"소리를 크게 따라 했네\", \"모르는 단어도 들어 봤네\"처럼 노력과 태도를 칭찬해 주세요."),
    ("작은 보상은 스티커 한 장", "칭찬 스티커판에 스티커 1장. 다섯 장이 모이면 좋아하는 책 함께 읽기처럼 '함께하는 시간'으로 바꿔 주세요. 간식·장난감은 피하는 게 좋아요."),
    ("가족에게 자랑할 기회", "\"아빠한테도 들려줄까?\" 아이가 오늘 배운 걸 다른 가족에게 보여 주게 해 주세요."),
    ("내일을 기대하게", "\"내일은 또 어떤 노래가 나올까?\"처럼 다음 시간을 예고하면 다음 날 시작이 쉬워져요."),
    ("비교하지 않기", "형제나 친구와 비교하지 말고, 어제의 아이와 비교해 \"어제보다 더 잘 들리네\"라고 해 주세요."),
)
_TIPS_TRY = (
    ("시작한 것부터 칭찬", "끝까지 못 했어도 \"오늘도 영어 시간 했네!\" 하고 앉아서 시작한 것을 먼저 칭찬해 주세요."),
    ("잘한 한 가지만", "어려웠던 부분은 짚지 말고, 잘한 장면 하나를 찾아 말해 주세요."),
    ("내일은 조금만", "\"내일은 한 곡만 더 들어 볼까?\"처럼 작고 구체적인 약속으로 마무리해 주세요."),
    ("부담 없이 끝내기", "아이가 지쳐 보이면 바로 멈추고 안아 주세요. 즐겁게 끝나야 내일 다시 앉아요."),
)


def praise_guide(child: dict[str, object], record: dict[str, object] | None,
                 card: dict[str, object] | None = None, streak: int = 0) -> dict[str, object] | None:
    """기록에 맞춘 칭찬 방법. 잘 해낸 날은 성취 칭찬, 일부만 한 날은 노력 칭찬, 못 한 날·휴식일은 없음."""
    if not record or record.get("rest_day") or record.get("completion") not in ("full", "partial"):
        return None
    good = record.get("completion") == "full"
    try:
        day = dt.date.fromisoformat(str(record.get("date"))).toordinal()
    except ValueError:
        day = 0
    title = learned_name({"card_task": (card or {}).get("task") or "",
                          "content_id": (card or {}).get("content_id") or record.get("content_id")}) or "오늘 영어"
    if not title.startswith("『") and title != "오늘 영어":
        title = f"'{title}'"
    phrases = PRAISE_GOOD if good else PRAISE_TRY
    tips = _TIPS_GOOD if good else _TIPS_TRY
    picked_phrases = [phrases[(day + i) % len(phrases)] for i in range(3)]
    rest = tips[1:]  # 첫 팁(구체적으로·시작 칭찬)은 매일, 나머지는 날마다 두 개씩 돌아가며
    picked_tips = [tips[0]] + [rest[(day * 2 + i) % len(rest)] for i in range(2)]
    out_tips = [{"title": t, "text": x.replace("{title}", title)} for t, x in picked_tips]
    streak_note = None
    if good and streak >= 3:
        streak_note = (f"{streak}일 연속 기록이에요. 스티커판이나 달력에 연속으로 한 날을 표시해 "
                       "아이가 눈으로 확인하게 해 주세요. 꾸준함 자체를 칭찬해 주면 습관이 돼요.")
    return {
        "kind": "good" if good else "try",
        "headline": "오늘 잘 해냈어요. 이렇게 칭찬해 주세요" if good
                    else "끝까지 못 해도 괜찮아요. 이렇게 격려해 주세요",
        "phrases": picked_phrases,
        "tips": out_tips,
        "streak_note": streak_note,
    }


MIN_TREND_DAYS = 3  # 추세·확신 문구를 말하려면 필요한 최소 기록 일수


def confidence_ok(
    child_id: int, as_of: dt.date | None = None,
) -> tuple[bool, list[str]]:
    """(ok, reasons) 반환.

    True 조건(모두 충족):
      ① 최근 7일 흥미·이해도 평균이 이전 7일 대비 현저히 하락하지 않음 (또는 ≥3)
      ② 미해결 C 없음 (C 이후 full+이해도≥3 기록 존재)
      ③ 연속 B(캘린더 인접) 없음
    """
    as_of = as_of or clock.today()
    reasons: list[str] = []
    cur = store.feedback_between(
        child_id, (as_of - dt.timedelta(days=6)).isoformat(), as_of.isoformat())
    if not cur:
        return False, ["최근 7일 기록 없음 — 데이터가 조건을 뒷받침하지 못함"]
    if len(cur) < MIN_TREND_DAYS:
        # 기록 1~2일로는 추세를 말할 수 없다 (피드백 보고서 3)
        return False, [f"최근 7일 기록 {len(cur)}일 — {MIN_TREND_DAYS}일 이상이어야 추세 판단"]

    def avg(rows: list[dict[str, object]], k: str) -> float | None:
        vs = [cast("int", r[k]) for r in rows]
        return sum(vs) / len(vs) if vs else None

    cur_int, cur_comp = avg(cur, "interest"), avg(cur, "comprehension")
    prev = store.feedback_between(
        child_id, (as_of - dt.timedelta(days=13)).isoformat(),
        (as_of - dt.timedelta(days=7)).isoformat())
    if prev:
        p_int, p_comp = avg(prev, "interest"), avg(prev, "comprehension")
        if p_int is not None and cur_int is not None and cur_int < p_int - 0.5:
            reasons.append(f"흥미 평균 하락({p_int:.1f}→{cur_int:.1f})")
        if p_comp is not None and cur_comp is not None and cur_comp < p_comp - 0.5:
            reasons.append(f"이해도 평균 하락({p_comp:.1f}→{cur_comp:.1f})")
    if cur_int is not None and cur_comp is not None and min(cur_int, cur_comp) < 3:
        reasons.append("현재 흥미·이해도 평균 3 미만")

    bd = store.branch_dates(
        child_id, (as_of - dt.timedelta(days=27)).isoformat(), as_of.isoformat())
    last_c: str | None = None
    for d, b in bd:
        if b == "C":
            last_c = d
    if last_c:
        resolved = store.one(
            "SELECT 1 AS ok FROM feedbacks WHERE child_id=? AND date>? AND date<=? AND completion='full' AND comprehension>=3",
            (child_id, last_c, as_of.isoformat()))
        if not resolved:
            reasons.append(f"미해결 C 잔존({last_c}~)")

    for (d1, b1), (d2, b2) in pairwise(bd):
        if b1 == "B" and b2 == "B":
            try:
                if (dt.date.fromisoformat(d2) - dt.date.fromisoformat(d1)).days == 1:
                    reasons.append(f"연속 B({d1}, {d2})")
                    break
            except ValueError:
                pass
    return (not reasons), reasons


# ---------------------------------------------------------------------------
# Long-term Memory (6.4)
# ---------------------------------------------------------------------------

class MemorySummary(TypedDict):
    recent: list[dict[str, object]]
    streak: int
    low_comprehension_streak: int
    low_interest_streak: int
    strong_streak: int


def memory_summary(child_id: int) -> MemorySummary:
    """최근 기록에서 연속 지표 추출 (수치형 피드백 기준)."""
    rows = store.query(
        "SELECT f.*, c.content_id AS content_id FROM feedbacks f LEFT JOIN cards c ON c.id=f.card_id WHERE f.child_id=? AND f.rest_day=0 ORDER BY f.date DESC LIMIT 14",
        (child_id,))
    recs: list[dict[str, object]] = []
    for r in rows:
        item = catalog.find_item(r["content_id"])
        recs.append({**dict(r), "title": item["title"] if item else "학습"})
    recs.reverse()  # 오래된 순

    def streak_of(pred: Callable[[dict[str, object]], bool]) -> int:
        n = 0
        for r in reversed(recs):
            try:
                ok = pred(r)
            except (TypeError, ValueError):
                ok = False
            if ok:
                n += 1
            else:
                break
        return n

    streak = 0
    if recs:
        recorded = {r["date"] for r in recs}
        d = dt.date.fromisoformat(cast("str", recs[-1]["date"]))
        while d.isoformat() in recorded:
            streak += 1
            d -= dt.timedelta(days=1)

    return {
        "recent": recs,
        "streak": streak,
        "low_comprehension_streak": streak_of(
            lambda r: cast("int", r["comprehension"]) <= 2),
        "low_interest_streak": streak_of(
            lambda r: cast("int", r["interest"]) <= 2),
        "strong_streak": streak_of(
            lambda r: r["completion"] == "full"
            and cast("int", r["comprehension"]) >= 4),
    }


def write_memory(
    child: dict[str, object], rec: dict[str, object],
    decision: branch.Decision, item: catalog.Item | None,
) -> None:
    """피드백 1건 → memory_facts 기록 (6.4)."""
    if decision["case"] == "SKIP":
        return
    if item and item["title"]:
        if decision["case"] == "B":
            store.upsert_fact(cast("int", child["id"]), "weak_point", item["title"])
        elif decision["case"] == "A" and \
                rec["completion"] == "full" and cast("int", rec["comprehension"]) >= 4:
            store.upsert_fact(cast("int", child["id"]), "learned", item["title"])
    if decision["flags"]["interest_dip"] or decision["low_interest_streak"] >= 2:
        store.replace_facts(cast("int", child["id"]), "interest_low_streak",
                            [f"{decision['low_interest_streak']}"])
    if decision["flags"]["expert_referral"]:
        store.upsert_fact(cast("int", child["id"]), "out_of_scope",
                          cast("str", rec["date"]))


# ---------------------------------------------------------------------------
# 조정 (5.4) — 다음 카드에 반영
# ---------------------------------------------------------------------------

def _pick_swap(
    child: dict[str, object], card: dict[str, object] | None,
    lower: bool = False, exclude: set[object] | None = None,
) -> catalog.Item | None:
    """대체 콘텐츠 후보: (lower면 한 레벨 아래, 아니면 같은 레벨) 다른 항목.
    다른 유형을 우선해 '형식·소재 교체'를 실제로 체감하게 한다."""
    if not card or not card.get("content_id"):
        return None
    cur = catalog.find_item(card["content_id"])
    if not cur:
        return None
    level = max(1, cur["level"] - (1 if lower else 0))
    age = cast("int | None", child.get("age"))
    pool = [it for it in (catalog.items_by_level(level, age)
                          or catalog.items_by_level(level))
            if it["id"] != cur["id"] and it["id"] not in (exclude or set())]
    diff = [it for it in pool if it["type"] != cur["type"]]
    if diff:
        return diff[0]
    return pool[0] if pool else None


def _shrink_card(tomorrow: dict[str, object]) -> int:
    new_min = max(5, cast("int", tomorrow["minutes"] or 10) - 5)
    store.update_card_content(
        cast("int", tomorrow["id"]),
        cast("str | None", tomorrow["content_id"]),
        cast("str", tomorrow["task"]), new_min,
        cast("str", tomorrow["check_point"]),
    )
    return new_min


def _swap_card(
    tomorrow: dict[str, object], child: dict[str, object],
    new_item: catalog.Item,
) -> catalog.Item:
    task, check = catalog.card_text(new_item)
    unit = curriculum.unit_text(
        new_item["id"], curriculum.prior_counts(cast("int", child["id"])).get(new_item["id"], 0))
    if unit is not None:
        task, check = unit
    minutes = min(new_item["session_minutes"] or 10,
                  cast("int", child.get("session_length") or 10))
    store.update_card_content(cast("int", tomorrow["id"]), new_item["id"],
                              task, minutes, check)
    return new_item


def apply_adjustment(
    child: dict[str, object], _rec: dict[str, object],
    decision: branch.Decision, tomorrow: dict[str, object] | None,
) -> dict[str, object]:
    """분기 판정을 다음 카드에 반영. (type, reason, dates, proposal?) 반환.

    A/SKIP: 없음
    B:      내일 카드 분량 5분 축소(최소 5분) — 같은 콘텐츠로 부담 낮춤
    C:      intent별 —
      question: (B 중복 시 shrink, 아니면 카드 불변)
      change_request: **자동 적용 없이 제안만** (6.1 승인 게이트)
      흥미 2일 연속: 같은 레벨 다른 유형 소재 swap (+B 중복 시 한 레벨 아래)
      out_of_scope: 카드 불변 (전문가 상담 전환)
    """
    case = decision["case"]
    flags = decision["flags"]
    if case in ("A", "SKIP"):
        return {"type": "none", "reason": "", "dates": []}

    if case == "B":
        if not tomorrow:
            return {"type": "none", "reason": "다음 카드 없음", "dates": []}
        new_min = _shrink_card(tomorrow)
        return {"type": "shrink",
                "reason": f"완료도·이해도 미달 → 내일 분량 {new_min}분으로 축소",
                "dates": [tomorrow["date"]]}

    # --- C ---
    intent = decision["intent"]
    if intent == "out_of_scope":
        return {"type": "none", "reason": "범위 밖 → 전문가 상담으로 전환", "dates": []}
    if intent == "change_request":
        # 부모가 바꾸고 싶은 건 오늘 한 자료다 → 오늘·다음 카드와 같은 자료는 제안하지 않는다
        today_card = store.get_card_for_child(cast("int", child["id"]), cast("str", _rec["date"]))
        prop = _pick_swap(child, tomorrow, lower=flags["difficulty_adjust"],
                          exclude={today_card.get("content_id")} if today_card else None)
        return {"type": "propose_swap",
                "reason": "큰 변경 — 부모 확인 후에만 반영 (6.1 승인 게이트)",
                "dates": [],
                "proposal": prop["title"] if prop else None}
    if decision["low_interest_streak"] >= 2:
        if not tomorrow:
            return {"type": "none", "reason": "다음 카드 없음", "dates": []}
        new_item = _pick_swap(child, tomorrow, lower=flags["difficulty_adjust"])
        if not new_item:
            return {"type": "none",
                    "reason": "대체 콘텐츠 없음 — 카탈로그 보강 필요", "dates": []}
        _ = _swap_card(tomorrow, child, new_item)
        t = "swap_easy" if flags["difficulty_adjust"] else "swap"
        return {"type": t,
                "reason": f"흥미≤2 2일 연속 → 같은 목표, 다른 형식·소재로 교체({new_item['title']})",
                "dates": [tomorrow["date"]]}
    if flags["difficulty_adjust"] and tomorrow:
        new_min = _shrink_card(tomorrow)
        return {"type": "shrink",
                "reason": f"C+B 중복 → 조정 안에 난이도 조정 포함(분량 {new_min}분)",
                "dates": [tomorrow["date"]]}
    return {"type": "none", "reason": "", "dates": []}


def tomorrow_payload(card: dict[str, object] | None) -> dict[str, object] | None:
    if not card:
        return None
    item = catalog.find_item(card.get("content_id"))
    return {
        "date": card["date"],
        "content_id": card.get("content_id"),
        "title": item["title"] if item else None,
        "task": card["task"],
        "minutes": card["minutes"],
        "check_point": card["check_point"],
    }


# ---------------------------------------------------------------------------
# 3단계 — 메시지 생성
# ---------------------------------------------------------------------------

def build_message_v2(
    child: dict[str, object], _rec: dict[str, object],
    decision: branch.Decision, item: catalog.Item | None,
    tomorrow: dict[str, object] | None,
    adjust: dict[str, object], conf: tuple[bool, list[str]],
) -> str:
    """룰베이스 코치 — LLM 없이도 결정적·동등하게 동작."""
    case = decision["case"]
    name = child.get("name") or "우리 아이"
    title = today_title(child, _rec, item)
    lines: list[str] = []
    if case == "A":
        # 기록 1~2일에 '좋은 흐름'이라 단정하지 않는다 (피드백 보고서 3)
        lines.append(
            f"{name}이(가) 오늘 {title}을(를) 끝까지 함께 해냈어요. "
            + ("좋은 흐름이에요." if conf[0] else "오늘 한 걸음을 쌓았어요."))
        if tomorrow:
            lines.append(f"내일은 '{tomorrow['task']}'({tomorrow['minutes']}분) — 오늘 모멘텀 그대로 이어가요.")
        else:
            lines.append("이번 계획의 마지막이었어요. 짧게 마무리하며 마무리 인사를 나눠보세요.")
        if conf[0]:
            lines.append("데이터로 보면, 이번 주도 옳은 길로 가고 있어요.")
        else:
            lines.append(ACCUMULATION)
    elif case == "B":
        lines.append(f"오늘은 {title}에서 여기까지 닿았어요. 그 자체로 하루치의 쌓임이에요.")
        lines.append("조금 쉽게: 오늘의 활동을 절반으로 나눠서, 먼저 소리만 따라 해보세요.")
        if tomorrow:
            lines.append(f"내일 연습할 것 하나: '{tomorrow['task']}' — {tomorrow['minutes']}분으로 줄여서 부담 없이 시작해요.")
        lines.append(ACCUMULATION)
    elif case == "C":
        intent = decision["intent"]
        if intent == "question":
            lines.append("남겨주신 질문에 답드릴게요.")
            lines.append("이 단계에서는 한국어로 해석하기보다 소리를 내어 따라 읽는 게 더 효과적이에요. 아이가 틀려도 멈추지 말고 소리를 유지해 주세요.")
            if decision["flags"]["difficulty_adjust"]:
                lines.append("이해도도 조금 흔들렸던 것 같아, 내일 분량을 줄여서 다잡을게요.")
        elif intent == "change_request":
            prop = adjust.get("proposal")
            lines.append(f"변경 요청 접수했어요. 제안: {prop or '대체 콘텐츠를 준비해 둘게요'}. 확인해 주시면 다음 카드부터 반영할게요 — 큰 변경은 부모님 확인 후에만 적용해요.")
        elif decision["low_interest_streak"] >= 2:
            tp = tomorrow_payload(tomorrow)
            nxt = (tp["title"] if tp and tp.get("title") else "대체 콘텐츠")
            lines.append(f"이틀 연속 흥미가 흔들리는 걸 확인했어요. 같은 목표를 유지한 채 소재만 바꿀게요: {nxt}.")
            lines.append("오늘만 쉬어가는 휴식일도 괜찮습니다 — 기록에서 휴식일로 표시해 주시면 성취 분모에서 제외할게요.")
        elif intent == "out_of_scope":
            lines.append("남겨주신 내용은 영어 학습 범위 밖의 건강·발달 관련 질문인 것 같아요. 앱으로 판단 드리는 것보다 소아과·언어치료 전문가와 상담하시는 걸 권해요. 학습은 지금 흐름을 유지할게요.")
        else:
            lines.append("오늘 기록을 바탕으로 내일 카드를 점검할게요.")
    if case != "SKIP":
        lines.append(AI_LABEL)
    return "\n".join(lines)


MESSAGE_SYSTEM = (
    '너는 "꽃피다"의 AI 학습 코치다. 영어 유치원 대신 집에서 영어를 자율 학습하는 '
    "만 4~7세 아이를 둔 부모에게 매일 짧은 코칭 메시지를 남긴다.\n\n"
    "철학: 영어를 배우는 이유는 증서가 아니라 영어로 사고하는 사람이 되기 위해서다. "
    "'매일의 작은 입력이 언젠가 말문이 트이는 순간이 된다'는 축적의 믿음을 전한다.\n\n"
    "규칙:\n"
    "- 따뜻하고 구체적이며 짧게 (3~6줄)\n"
    "- 부모를 평가하지 않는다. '아이가 못했다'가 아니라 '오늘은 여기까지 닿았다'로 서술한다\n"
    "- 발달 지연·질병·장애 등 진단적 표현, 능력 단정, 과장된 효과 보장은 절대 하지 않는다\n"
    "- 제공된 카탈로그 콘텐츠 정보에만 근거한다. 모르는 사실을 지어내지 않는다\n"
    "- 메시지에는 내일 학습 내용(작업·분량)을 포함한다\n"
    '- 확신 문구("옳은 길로 가고 있다" 등)는 confidence_ok가 true일 때만 '
    "confidence_sentence 필드에 쓰고, false면 빈 문자열로 둔다. "
    "하락·미해결 주에는 body에서 조정 사실을 솔직하게 전달한다\n"
    '- 메시지 마지막 줄에 "AI가 작성한 코칭 메시지입니다."를 포함한다\n\n'
    '반드시 아래 JSON만 반환한다:\n'
    '{"case": "A|B|C", "body": "코칭 메시지", "tomorrow_card": "내일 카드 요약", '
    '"confidence_sentence": ""}'
)


def _llm_user_context(
    child: dict[str, object], rec: dict[str, object],
    decision: branch.Decision, item: catalog.Item | None,
    tomorrow: dict[str, object] | None,
    adjust: dict[str, object], mem: MemorySummary, conf: tuple[bool, list[str]],
) -> str:
    t = tomorrow_payload(tomorrow)
    if t:
        tomorrow_desc = f"{t['date']} '{t['task']}' {t['minutes']}분"
    else:
        tomorrow_desc = "없음(계획 종료)"
    ek = "예" if child.get("ek_kindergarten") else "아니오"
    exposure = child.get("exposure") or "none"
    completion = cast("str", rec["completion"])
    raw_decision = cast("dict[str, object]", cast("object", decision))
    intent_reason = raw_decision.get("intent_reason") or ""
    return (
        f"아이: 만 {child['age']}세, 영어유치원 재원={ek}, 영어 노출={exposure}, "
        f"하루 학습 {child.get('session_length') or 10}분, "
        f"현재 단계 L{child.get('level') or 1}\n"
        f"오늘 기록: 완료={COMPLETION_KO.get(completion, completion)} "
        f"만족도={rec['satisfaction']} 흥미={rec['interest']} 이해도={rec['comprehension']}\n"
        f"메모: {rec.get('memo') or '(없음)'}\n"
        f"메모 의도(1단계 분류기 출력): {decision['intent']} — {intent_reason}\n"
        f"오늘 콘텐츠: {item['title'] if item else '학습'} — 오늘 한 것: {today_title(child, rec, item)} "
        f"(L{item['level'] if item else 1}, "
        f"{item.get('type', '') if item else ''}, "
        f"해설: {(item.get('expert_note') or '')[:200] if item else ''})\n"
        f"분기 판정(규칙, 변경 불가): {decision['case']} — "
        f"{'; '.join(decision.get('reasons') or [])}\n"
        f"적용된 조정: {adjust.get('type', 'none')} ({adjust.get('reason', '')})\n"
        f"내일 카드: {tomorrow_desc}\n"
        f"최근 추이: 연속 학습 {mem['streak']}일, 이해도 저하 연속 {mem['low_comprehension_streak']}일, "
        f"흥미 저하 연속 {mem['low_interest_streak']}일, "
        f"순항 연속 {mem['strong_streak']}일\n"
        f"확신 문구 데이터 조건(confidence_ok): {str(bool(conf[0])).lower()}"
        f"{'' if conf[0] else ' — 사유: ' + ', '.join(conf[1])}"
    )


class MessageResult(TypedDict):
    case: str
    message: str
    prompt_version: str
    model: str
    is_ai_generated: bool


def _try_llm_message(
    child: dict[str, object], rec: dict[str, object],
    decision: branch.Decision, item: catalog.Item | None,
    tomorrow: dict[str, object] | None,
    adjust: dict[str, object], mem: MemorySummary,
    conf: tuple[bool, list[str]],
) -> MessageResult | None:
    try:
        raw = _call_llm(MESSAGE_SYSTEM,
                        _llm_user_context(child, rec, decision, item, tomorrow,
                                          adjust, mem, conf))
        if not raw:
            return None
        data = cast("dict[str, object]", json.loads(_strip_fences(raw)))
        body = str(data.get("body") or "").strip()
        if not body:
            return None
        # 6.6 스키마 강제: case는 규칙 판정이 무조건 우선 — LLM이 못 바꾼다
        conf_sentence = str(data.get("confidence_sentence") or "").strip()
        if conf_sentence and not conf[0]:
            conf_sentence = ""  # 데이터 조건 실패 → 폐기 (고정 삽입 금지)
        if conf_sentence and conf_sentence not in body:
            body = body + "\n" + conf_sentence
        if AI_LABEL not in body:
            body += "\n" + AI_LABEL
        return {
            "case": decision["case"],
            "message": body,
            "prompt_version": LLM_VERSION,
            "model": _llm_model(),
            "is_ai_generated": True,
        }
    except Exception:  # noqa: BLE001 — 스키마 밖 출력/호출 실패 → 폴백 (6.6)
        return None


def build_message(
    child: dict[str, object], rec: dict[str, object],
    decision: branch.Decision, item: catalog.Item | None,
    tomorrow: dict[str, object] | None,
    adjust: dict[str, object],
    conf: tuple[bool, list[str]] | None = None,
) -> MessageResult:
    """3단계 진입점. (LLM 없거나 스키마 실패 시) 룰베이스로 폴백."""
    if conf is None:
        try:
            as_of = dt.date.fromisoformat(cast("str", rec["date"]))
        except (TypeError, ValueError):
            as_of = clock.today()
        conf = confidence_ok(cast("int", child["id"]), as_of)
    result: MessageResult | None = None
    if _llm_available():
        result = _try_llm_message(child, rec, decision, item, tomorrow, adjust,
                                  memory_summary(cast("int", child["id"])), conf)
    if result is None:
        result = {
            "case": decision["case"],
            "message": build_message_v2(child, rec, decision, item, tomorrow,
                                        adjust, conf),
            "prompt_version": RULES_VERSION,
            "model": "",
            "is_ai_generated": True,
        }
    return result


# ---------------------------------------------------------------------------
# 주간 · 월간 (5.5)
# ---------------------------------------------------------------------------

def weekly_report(child: dict[str, object], week_start: str | None = None) -> dict[str, object]:
    """주간 리포트. week_start 미지정 시 지난 주(월~일).

    확신 문구는 confidence_ok(데이터 조건)일 때만 포함하고, 하락·미해결 주에는
    honest_note로 조정 사실을 솔직히 안내한다 (6.6 고정 삽입 금지).
    """
    child_id = cast("int", child["id"])
    today = clock.today()
    if week_start:
        ws = dt.date.fromisoformat(week_start)
    else:
        ws = today - dt.timedelta(days=today.weekday() + 7)  # 지난 주 월요일
    we = ws + dt.timedelta(days=6)
    crows = store.feedback_between(child_id, ws.isoformat(), we.isoformat())
    pw = store.feedback_between(
        child_id, (ws - dt.timedelta(days=7)).isoformat(),
        (ws - dt.timedelta(days=1)).isoformat())
    record_days = len(crows)

    def avg(rows: list[dict[str, object]], k: str) -> float | None:
        vs = [cast("int", r[k]) for r in rows]
        return round(sum(vs) / len(vs), 1) if vs else None

    cur_int, cur_comp = avg(crows, "interest"), avg(crows, "comprehension")
    prev_int, prev_comp = avg(pw, "interest"), avg(pw, "comprehension")
    trend: list[str] = []
    if cur_int is not None and prev_int is not None:
        trend.append(f"흥미 {prev_int:.1f}→{cur_int:.1f}")
    if cur_comp is not None and prev_comp is not None:
        trend.append(f"이해도 {prev_comp:.1f}→{cur_comp:.1f}")

    learned: list[str] = []
    seen: set[str] = set()
    for r in crows:
        if (r["completion"] == "full"
                and cast("int", r["comprehension"]) >= 4 and r["content_id"]):
            name = learned_name(r)
            if name and name not in seen:
                seen.add(name)
                learned.append(f"{name} (끝까지, 이해도 {r['comprehension']}점)")
    learned = learned[:3]

    bd = store.branch_dates(child_id, ws.isoformat(), we.isoformat())
    counts: dict[str, int] = {"A": 0, "B": 0, "C": 0, "SKIP": 0}
    for _d, b in bd:
        counts[b] = counts.get(b, 0) + 1

    choices: list[str] = ["현재 흐름 유지 (추이가 안정적이라면 추천)"]
    if counts["B"] >= 2 or (cur_comp is not None and cur_comp < 3):
        choices.append("난이도를 살짝 낮춰서 진행")
    if ((cur_int is not None and prev_int is not None and cur_int < prev_int - 0.5)
            or counts["C"] >= 1):
        choices.append("소재·형식을 아이 흥미에 맞춰 교체")

    next_cards: list[dict[str, object]] = []
    plan = store.approved_plan(child_id)
    if plan:
        for c in store.cards_for_plan(cast("int", plan["id"])):
            if cast("str", c["date"]) > we.isoformat():
                next_cards.append({"date": c["date"], "task": c["task"],
                                   "minutes": c["minutes"]})
            if len(next_cards) >= 5:
                break

    as_of = min(today, we)
    conf = confidence_ok(child_id, as_of)
    confidence_sentence = ""
    honest_note: str | None = None
    if conf[0]:
        confidence_sentence = "데이터로 보면, 이번 주도 옳은 길로 가고 있어요."
    elif crows and len(crows) < MIN_TREND_DAYS:
        # 기록이 적으면 좋다·흔들린다 어느 쪽도 말하지 않는다 (보고서 3)
        honest_note = (f"기록 {len(crows)}일 — 아직 추세를 말하기엔 이르러요. "
                       f"{MIN_TREND_DAYS}일 이상 쌓이면 흐름을 알려 드릴게요.")
    elif crows:
        if counts["C"] >= 1:
            honest_note = ("이번 주에는 흥미가 흔들려 소재를 바꾸거나 조정했어요. 그게 방향을 세우는 일입니다.")
        elif counts["B"] >= 2:
            honest_note = ("이번 주에는 조금 막혔던 날이 있었어요. 분량을 줄여 내일은 더 가볍게 가요.")
        else:
            honest_note = ("이번 주 추이는 살짝 흔들렸어요. 억지로 밀어붙이기보다 아이가 따라 올 수 있는 속도로 진행해요.")

    if record_days and record_days < MIN_TREND_DAYS:
        one_step = (f"첫 기록을 남겼어요 ({record_days}일). 추세는 기록이 {MIN_TREND_DAYS}일 이상 "
                    "쌓이면 알려 드릴게요.")
    elif learned:
        one_step = f"이번 주의 한 걸음: {learned[0]} — 부모님이 관찰해 기록해 주신 결과예요."
    elif record_days:
        one_step = (f"이번 주의 한 걸음: {record_days}일 동안 매일 한 걸음씩 걸었어요. "
                    "그 자체가 큰 걸음입니다.")
    else:
        one_step = "이번 주에는 첫 걸음을 함께 내딛어요."

    parts: list[str] = [f"이번 주 학습 {record_days}일."]
    if trend:
        parts.append(f"추이: {', '.join(trend)}.")
    summary = "".join(parts)

    return {
        "week_start": ws.isoformat(),
        "week_end": we.isoformat(),
        "record_days": record_days,
        "avg_interest": cur_int,
        "avg_comprehension": cur_comp,
        "prev_avg_interest": prev_int,
        "prev_avg_comprehension": prev_comp,
        "trend": trend,
        "learned": learned,
        # 부모가 기록한 날별 요약 — 일하느라 함께 못 본 날도 무엇을 했고 어땠는지 확인 (시트 의견)
        "days": [{
            "date": r["date"], "what": learned_name(r),
            "completion": r["completion"], "interest": r["interest"],
            "comprehension": r["comprehension"], "memo": r.get("memo") or "",
        } for r in sorted(crows, key=lambda x: str(x["date"]))],
        "branch_counts": counts,
        "choices": choices[:3],
        "next_cards": next_cards,
        "confidence_sentence": confidence_sentence,
        "honest_note": honest_note,
        "one_step": one_step,
        "summary": summary,
    }


class MonthlyAchievement(TypedDict):
    month: str
    record_days: int
    max_streak: int
    avg_interest: float | None
    avg_comprehension: float | None
    learned: list[str]
    note: str


def monthly_achievement(
    child: dict[str, object], month: str | None = None,
) -> MonthlyAchievement:
    """월간 학습 성취 리포트 (5.5) — 요금·청구와 무관하게 성취만 보고."""
    today = clock.today()
    if month is None:
        month = (today.replace(day=1) - dt.timedelta(days=1)).strftime("%Y-%m")
    m = dt.date.fromisoformat(month + "-01")
    next_m = (m.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
    rows = store.feedback_between(
        cast("int", child["id"]), m.isoformat(),
        (next_m - dt.timedelta(days=1)).isoformat())
    dates = sorted({cast("str", r["date"]) for r in rows})

    max_streak = streak = 0
    prev: dt.date | None = None
    for dstr in dates:
        d = dt.date.fromisoformat(dstr)
        if prev is not None and (d - prev).days == 1:
            streak += 1
        else:
            streak = 1
        max_streak = max(max_streak, streak)
        prev = d

    learned: list[str] = []
    seen: set[str] = set()
    for r in rows:
        if (r["completion"] == "full"
                and cast("int", r["comprehension"]) >= 4 and r["content_id"]):
            name = learned_name(r)
            if name and name not in seen:
                seen.add(name)
                learned.append(name)

    def avg(k: str) -> float | None:
        vs = [cast("int", r[k]) for r in rows]
        return round(sum(vs) / len(vs), 1) if vs else None

    return {
        "month": month,
        "record_days": len(rows),
        "max_streak": max_streak,
        "avg_interest": avg("interest"),
        "avg_comprehension": avg("comprehension"),
        "learned": learned[:5],
        "note": "학습 성취 리포트입니다 — 요금·청구와 무관합니다.",
    }


def stats_payload(child: dict[str, object]) -> dict[str, object]:
    """학습 성취 대시보드 (5.6) — 진행·추이만 노출, 인센티브 조건으로 쓰이지 않음."""
    child_id = cast("int", child["id"])
    today = clock.today()
    month = today.strftime("%Y-%m")
    rows = store.feedback_between(child_id, month + "-01", today.isoformat())
    mem = memory_summary(child_id)
    plan = store.approved_plan(child_id)
    planned = 0
    if plan:
        planned = len([c for c in store.cards_for_plan(cast("int", plan["id"]))
                       if cast("str", c["date"]).startswith(month)])

    def avg(k: str) -> float | None:
        vs = [cast("int", r[k]) for r in rows]
        return round(sum(vs) / len(vs), 1) if vs else None

    return {
        "month": month,
        "record_days": len(rows),
        "planned_days": planned,
        "record_rate": round(len(rows) / planned, 2) if planned else None,
        "streak": mem["streak"],
        "avg_interest": avg("interest"),
        "avg_comprehension": avg("comprehension"),
        "recent": [
            {"date": r["date"], "completion": r["completion"],
             "interest": r["interest"], "comprehension": r["comprehension"]}
            for r in reversed(rows[-14:])
        ],
    }


# ---------------------------------------------------------------------------
# LLM 전송 (OpenAI 호환, urllib)
# ---------------------------------------------------------------------------

def _llm_provider() -> str:
    """LLM 제공자. BLOOMY_LLM_PROVIDER 우선, 없으면 키 존재로 추론."""
    provider = os.environ.get("BLOOMY_LLM_PROVIDER", "").strip().lower()
    if provider in ("anthropic", "claude"):
        return "anthropic"
    if provider in ("openai", "openai-compatible"):
        return "openai"
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic"
    return "openai"


def _llm_available() -> bool:
    if _llm_provider() == "anthropic":
        return bool(os.environ.get("ANTHROPIC_API_KEY"))
    return bool(os.environ.get("OPENAI_API_KEY"))


DEFAULT_ANTHROPIC_MODEL = "claude-haiku-5-5"
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"


def _llm_model() -> str:
    """현재 제공자에서 실제로 호출하는 모델 ID (응답 메타데이터에도 이 값을 기록)."""
    default = DEFAULT_ANTHROPIC_MODEL if _llm_provider() == "anthropic" else DEFAULT_OPENAI_MODEL
    return os.environ.get("BLOOMY_LLM_MODEL") or default


def llm_status() -> dict[str, object]:
    """/api/health용 LLM 설정 요약 (비밀값 없음). 실제 호출 성공 여부는 아니다."""
    provider = _llm_provider()
    key_configured = _llm_available()
    return {
        "provider": provider,
        "model": _llm_model(),
        "key_configured": key_configured,
        "mode": "llm" if key_configured else "rule_based",
        "model_from_env": bool(os.environ.get("BLOOMY_LLM_MODEL")),
    }


def _call_llm(system: str, user: str) -> str | None:
    if _llm_provider() == "anthropic":
        return _call_anthropic(system, user)
    return _call_openai(system, user)


def _call_anthropic(system: str, user: str) -> str | None:
    """Anthropic(Claude) Messages API. JSON은 프롬프트로 유도하고 호출부가 파싱."""
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return None
    base = os.environ.get("BLOOMY_LLM_BASE_URL", "https://api.anthropic.com").rstrip("/")
    # Claude Haiku 5.5: temperature 등 샘플링 값을 바꾸면 400 → 보내지 않는다.
    # 적응형 사고가 기본으로 켜져 있어 사고 토큰도 max_tokens에 포함되므로 여유를 둔다.
    payload: dict[str, object] = {
        "model": _llm_model(),
        "max_tokens": 4096,
        "output_config": {"effort": "low"},
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }
    try:
        req = urllib.request.Request(
            base + "/v1/messages",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "x-api-key": key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
        )
        resp = cast("io.BufferedIOBase", urllib.request.urlopen(req, timeout=40))
        with resp:
            out = cast("dict[str, object]", json.loads(resp.read()))
        blocks = cast("list[dict[str, object]]", out.get("content") or [])
        text = "".join(
            cast("str", b.get("text") or "")
            for b in blocks
            if b.get("type") == "text"
        )
        return text or None
    except Exception as exc:  # noqa: BLE001
        print(f"[bloomy-coach] Anthropic call failed: {exc}")
        return None


def _call_openai(system: str, user: str) -> str | None:
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        return None
    base = os.environ.get("BLOOMY_LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    model = _llm_model()
    last_err: Exception | None = None
    for use_json_mode in (True, False):
        payload: dict[str, object] = {
            "model": model,
            "temperature": 0.7,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        if use_json_mode:
            payload["response_format"] = {"type": "json_object"}
        try:
            req = urllib.request.Request(
                base + "/chat/completions",
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Authorization": "Bearer " + key,
                    "Content-Type": "application/json",
                },
            )
            resp = cast("io.BufferedIOBase", urllib.request.urlopen(req, timeout=40))
            with resp:
                out = cast("dict[str, object]", json.loads(resp.read()))
            choices = cast("list[dict[str, object]]", out["choices"])
            message = cast("dict[str, object]", choices[0]["message"])
            return cast("str | None", message["content"])
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            continue
    if last_err:
        print(f"[bloomy-coach] LLM call failed: {last_err}")
    return None
