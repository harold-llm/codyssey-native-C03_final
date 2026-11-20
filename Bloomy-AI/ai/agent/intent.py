"""Auditable keyword fallback; no generative model is called."""
from typing import Protocol

INTENTS = {"none", "question", "change_request", "out_of_scope"}


class IntentClassifier(Protocol):
    def classify(self, memo: str) -> dict: ...


class KeywordIntentClassifier:
    def classify(self, memo):
        text = memo.casefold()
        groups = (
            ("out_of_scope", ("발달", "질병", "장애", "자폐", "adhd", "진단", "치료", "우울", "건강", "심리", "아파", "아픈")),
            ("change_request", ("바꿔", "바꾸", "변경", "교체", "다른 자료", "다른 교재", "줄여", "늘려", "쉬운 걸", "쉬운걸")),
            ("question", ("?", "？", "어떻게", "왜", "궁금", "알려", "조언", "맞나요", "되나요", "할까요")),
        )
        for intent, keywords in groups:
            if any(word in text for word in keywords):
                return {"intent": intent, "reason": f"로컬 키워드 규칙: {intent}", "version": "bloomy-intent-keywords-v1"}
        return {"intent": "none", "reason": "질문·변경·범위 밖 키워드 없음", "version": "bloomy-intent-keywords-v1"}


def classify_safely(classifier, memo):
    try:
        output = classifier.classify(memo)
        if (not isinstance(output, dict) or output.get("intent") not in INTENTS or
                not isinstance(output.get("reason"), str) or not output["reason"].strip()):
            raise ValueError("invalid intent schema")
        return output, []
    except (ValueError, TypeError, KeyError, RuntimeError, OSError):
        return KeywordIntentClassifier().classify(memo), ["의도 분류기 실패로 로컬 키워드 분류를 사용했습니다."]


class LLMIntentClassifier:
    def __init__(self, llm):
        self.llm = llm

    def classify(self, memo):
        from ai.llm import LLMError, complete, object_schema

        reasons = {
            "none": "학습 기록이며 질문이나 변경 요청이 없습니다.",
            "question": "부모가 학습 방법에 관한 질문을 했습니다.",
            "change_request": "부모가 콘텐츠 또는 학습 방식의 변경을 요청했습니다.",
            "out_of_scope": "건강·심리·발달 등 학습 코칭 범위 밖 판단을 요청했습니다.",
        }
        schema = object_schema(intent={"type": "string", "enum": sorted(INTENTS)},
                               reason={"type": "string", "enum": list(reasons.values())})
        result = complete(
            self.llm, "memo_intent", "Classify only the parent's memo. Prefer out_of_scope for clinical requests "
            "and change_request for explicit requests to modify learning, including those phrased as questions. "
            "Choose the matching Korean reason. An empty memo means none.", {"memo": memo}, schema,
        )
        if result["reason"] != reasons[result["intent"]]:
            raise LLMError("memo intent and reason do not match")
        return {**result, "version": "bloomy-intent-llm-v1"}
