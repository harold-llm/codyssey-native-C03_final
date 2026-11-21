"""아이용 미니러닝 서버 추천 (learning/ 프론트 계약).

`learning/js/app.js`의 `POST /api/learning/recommendation` 계약을 만족하는
결정적(룰베이스) 추천기다. LLM 없이도 동작하며, 프론트가 보낸 `words`/`phrases`의
**부분집합만** 골라 반환한다(카탈로그 밖 추천 금지 원칙과 동일).

응답 스키마:
  {provider, words:[{word}], phrases:[{english}], difficulty,
   estimatedMinutes, historyCount, reason, summary, strengths[],
   supportNeeds[], nextLearning}

난이도는 영어 경험 + 최근 정답률로 정하고, 단어는 약점 단어를 우선한다.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import cast

DIFFICULTIES = ("기초", "차근차근", "도전")
EXPERIENCE_LEVEL = {
    "처음 시작해요": 0,
    "가끔 해봤어요": 1,
    "기초를 알고 있어요": 2,
    "영어를 자주 접해요": 3,
}
_WORDS_BY_DIFFICULTY = {"기초": 3, "차근차근": 4, "도전": 5}
_MINUTES_BY_DIFFICULTY = {"기초": 5, "차근차근": 10, "도전": 15}


def _as_int(value: object, default: int) -> int:
    try:
        return int(cast("int | float | str", value))
    except (TypeError, ValueError):
        return default


def _as_float(value: object) -> float | None:
    try:
        return float(cast("int | float | str", value))
    except (TypeError, ValueError):
        return None


def _str_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for v in cast("list[object]", value):
        if isinstance(v, str) and v.strip():
            out.append(v.strip())
    return out


def _field_ids(items: object, key: str) -> list[str]:
    if not isinstance(items, list):
        return []
    out: list[str] = []
    for it in cast("list[object]", items):
        if isinstance(it, dict):
            v = cast("dict[str, object]", it).get(key)
            if isinstance(v, str) and v.strip():
                out.append(v.strip())
    return out


def _difficulty(experience: str, accuracy: float | None) -> str:
    score = EXPERIENCE_LEVEL.get(experience, 1)
    if accuracy is not None:
        if accuracy >= 0.8:
            score += 1
        elif accuracy < 0.5:
            score -= 1
    if score <= 0:
        return "기초"
    if score >= 3:
        return "도전"
    return "차근차근"


def recommend(payload: Mapping[str, object]) -> dict[str, object]:
    """learning 프론트 payload → 추천 응답. 잘못된 입력은 ValueError."""
    raw_profile = payload.get("profile")
    raw_stats = payload.get("stats")
    profile = cast("dict[str, object]", raw_profile) if isinstance(raw_profile, dict) else {}
    stats = cast("dict[str, object]", raw_stats) if isinstance(raw_stats, dict) else {}

    words = _field_ids(payload.get("words"), "word")
    phrases = _field_ids(payload.get("phrases"), "english")
    if not words or not phrases:
        raise ValueError("words와 phrases가 필요합니다")

    raw_experience = profile.get("experience")
    experience = raw_experience if isinstance(raw_experience, str) else "가끔 해봤어요"
    accuracy = _as_float(stats.get("recentAccuracy"))
    difficulty = _difficulty(experience, accuracy)

    study_time = _as_int(profile.get("studyTime"), 10)
    if study_time < 5:
        study_time = 10
    minutes = max(5, min(study_time, _MINUTES_BY_DIFFICULTY[difficulty]))

    weak = [w for w in _str_list(stats.get("weakWords")) if w in words]
    ordered = weak + [w for w in words if w not in weak]
    chosen_words = ordered[: _WORDS_BY_DIFFICULTY[difficulty]]
    chosen_phrases = phrases[:2]

    interests = _str_list(profile.get("interests"))
    interest = interests[0] if interests else "아이의 관심사"
    history_count = _as_int(stats.get("recentAttemptCount"), 0)

    if accuracy is not None and accuracy >= 0.8:
        strengths = ["최근 정답률이 높아요", "배운 단어를 잘 기억하고 있어요"]
    elif accuracy is not None:
        strengths = ["꾸준히 시도하고 있어요"]
    else:
        strengths = ["학습을 시작했어요"]
    support_needs = (
        [f"{', '.join(weak[:2])} 단어를 한 번 더 연습해요"] if weak else []
    )

    return {
        "provider": "server_ai",
        "words": [{"word": w} for w in chosen_words],
        "phrases": [{"english": e} for e in chosen_phrases],
        "difficulty": difficulty,
        "estimatedMinutes": minutes,
        "historyCount": history_count,
        "reason": f"{interest} 관심사와 지금 난이도({difficulty})에 맞춰 골랐어요.",
        "summary": (
            f"오늘은 {difficulty} 단계로 단어 {len(chosen_words)}개와 "
            f"표현 {len(chosen_phrases)}개를 연습해요."
        ),
        "strengths": strengths,
        "supportNeeds": support_needs,
        "nextLearning": (
            f"다음에는 '{chosen_phrases[0]}' 표현을 소리 내어 말해봐요."
            if chosen_phrases
            else "오늘 배운 단어를 소리 내어 말해봐요."
        ),
    }
