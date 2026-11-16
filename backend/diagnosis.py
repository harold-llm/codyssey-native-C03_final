"""초기 단계 진단 (01 §5.1) — 보호자 5문항 체크 → 단계 가설(L1~L5).

진단 결과는 "확정"이 아니라 **가설**이다: 2주간의 실제 반응 데이터
(피드백·분기 이력)로 보정한다는 점을 API 응답과 UI에 명시한다 (5.1-4).

규칙 v1 (B 기준선):
  - 5문항 각 none/some/many → 0/1/2점, 합 0~10
  - level = 1 + score//2  (0-1→L1, 2-3→L2, 4-5→L3, 6-7→L4, 8-10→L5)
  - 영어 노출 'much' → +1 (L5 상한)
"""

QUESTIONS = {
    "alphabet": {
        "label": "알파벳(a, b, c) 인지",
        "options": {"none": "인지 못 함", "some": "일부 인지", "many": "대부분 인지"},
    },
    "phonics": {
        "label": "파닉스(글자-소리) 노출",
        "options": {"none": "노출 없음", "some": "한두 번 접함", "many": "정기적으로 학습"},
    },
    "readers": {
        "label": "레벨드 리더스 경험",
        "options": {"none": "경험 없음", "some": "몇 번 읽어봄", "many": "정기적으로 읽음"},
    },
    "response": {
        "label": "영어 질문에 아이 반응",
        "options": {"none": "드뭄", "some": "가끔", "many": "자주"},
    },
    "focus": {
        "label": "책·영상 집중 길이",
        "options": {"none": "5분 미만", "some": "5~10분", "many": "10분 이상"},
    },
}

SCORE = {"none": 0, "some": 1, "many": 2}


def questions_payload():
    """UI(온보딩 5문항 화면)에 내릴 질문 정의."""
    return [
        {"key": k, "label": v["label"], "options": v["options"]}
        for k, v in QUESTIONS.items()
    ]


def diagnose(answers, exposure="none"):
    """5문항 응답 → {score, level, answers, note}.

    answers: {alphabet, phonics, readers, response, focus} 각 none|some|many
    누락 문항이 있으면 ValueError.
    """
    if not isinstance(answers, dict):
        raise ValueError("diagnosis answers must be an object")
    unknown = [k for k in QUESTIONS if answers.get(k) not in SCORE]
    if unknown:
        raise ValueError("missing or invalid answers: %s" % ",".join(unknown))
    score = sum(SCORE[answers[k]] for k in QUESTIONS)
    level = 1 + score // 2
    if exposure == "much":
        level += 1
    level = max(1, min(5, level))
    return {
        "score": score,
        "level": level,
        "answers": {k: answers[k] for k in QUESTIONS},
        "note": "5문항 기반 초기 가설입니다. 2주간의 실제 반응 데이터로 보정돼요.",
    }
