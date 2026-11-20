"""Bounded local Agent: classify, decide, retrieve, propose, and validate."""
from dataclasses import asdict
from .contracts import CoachRequest, CoachResult
from .guardrails import AI_LABEL, validate_result
from ai.llm import LLMError
from .intent import KeywordIntentClassifier, LLMIntentClassifier, classify_safely
from .message import generate_opening
from .rules import decide
from .tools import CoachTools


class CoachAgent:
    def __init__(self, rag_engine, intent_classifier=None, memory=None, *, llm=None):
        self.tools = CoachTools(rag_engine)
        self.llm = llm if llm is not None else getattr(rag_engine, "llm", None)
        self.classifier = intent_classifier or (
            LLMIntentClassifier(self.llm) if self.llm is not None else KeywordIntentClassifier()
        )
        self.memory = memory if memory is not None else getattr(rag_engine, "memory", None)

    def coach(self, request: CoachRequest, *, event_id=None) -> CoachResult:
        if not isinstance(request, CoachRequest):
            raise ValueError("request must be CoachRequest")
        if self.memory is not None:
            return self.memory.coach(self, request, event_id)
        return self._coach(request)

    def _coach(self, request: CoachRequest, *, memory_summary=None) -> CoachResult:
        empty = {"type": "none", "reason": "변경 없음", "dates": [], "proposal": None,
                 "requires_parent_approval": False, "auto_apply": False}
        if request.feedback.rest_day:
            decision = decide(request.feedback)
            result = CoachResult("SKIP", "none", "휴식일 — 의도 분류 생략", decision["flags"],
                                 decision["reasons"], None, {**empty, "reason": "휴식일"}, None,
                                 is_ai_generated=False)
            return validate_result(result, request, self.tools)

        for card in (request.today_card, request.next_card):
            if card:
                item = self.tools.get_detail(card.content_id)
                if not item["age_min"] <= request.age <= item["age_max"]:
                    raise ValueError("card is outside child's age range")
        classified, warnings = classify_safely(self.classifier, request.feedback.memo)
        decision = decide(request.feedback, request.history, classified["intent"])
        tomorrow = asdict(request.next_card) if request.next_card and request.plan_status == "approved" else None
        adjustment = {**empty, "reason": "계획 유지"}
        evidence_items = {}

        def remember(item):
            evidence_items[item["id"]] = item

        if request.today_card:
            remember(self.tools.get_detail(request.today_card.content_id))
        if tomorrow:
            remember(self.tools.get_detail(tomorrow["content_id"]))

        if request.plan_status != "approved":
            adjustment["reason"] = "부모 승인된 계획이 없어 카드 조정을 보류합니다."
            warnings.append("계획 승인 전에는 다음 카드를 활성화하지 않습니다.")
        elif decision["flags"]["expert_referral"]:
            adjustment["reason"] = "학습 범위 밖 문의 — 전문가 안내, 카드 변경 없음"
        elif not request.next_card:
            adjustment["reason"] = "다음 카드가 없어 조정하지 않습니다."
            warnings.append("계획이 끝났거나 다음 카드가 없습니다. 새 계획은 별도 승인해야 합니다.")
        else:
            original_item = self.tools.get_detail(request.next_card.content_id)
            needs_change = classified["intent"] == "change_request"
            low_streak = decision["low_interest_streak"] >= 2
            difficulty = decision["flags"]["difficulty_adjust"] or decision["case"] == "B"
            if needs_change or low_streak:
                target_level = max(1, original_item["level"] - int(difficulty))
                hits = self.tools.search(request, level=target_level)
                candidates = [h["item"] for h in hits
                              if h["item"]["id"] != original_item["id"]
                              and h["item"]["skill"] == original_item["skill"]
                              and h["item"]["session_minutes"] <= request.next_card.minutes
                              and (needs_change or h["item"]["type"] != original_item["type"])]
                if difficulty and not needs_change and original_item["level"] == 1:
                    candidates = []  # No fabricated L0 or same-level swap_easy.
                candidate = candidates[0] if candidates else None
                if candidate:
                    remember(candidate)
                if needs_change:
                    adjustment.update(type="propose_swap", reason="부모 변경 요청 — 확인 후에만 반영",
                                      proposal=self.tools.card_for(request.next_card, candidate) if candidate else None,
                                      dates=[request.next_card.date], requires_parent_approval=True)
                    if not candidate:
                        warnings.append("변경 조건에 맞는 대체 자료가 없습니다. 기존 카드를 유지하고 부모와 재협의해야 합니다.")
                elif candidate:
                    tomorrow = self.tools.card_for(request.next_card, candidate)
                    adjustment.update(type="swap_easy" if difficulty else "swap", reason="연속 흥미 저하 — 같은 목표의 다른 형식 제안",
                                      dates=[request.next_card.date], auto_apply=True)
                else:
                    warnings.append("레벨·목표·형식 조건에 맞는 대체 자료가 없어 교체하지 않았습니다.")
                    if difficulty and tomorrow["minutes"] > 5:
                        tomorrow = {**tomorrow, "minutes": max(5, tomorrow["minutes"] - 5)}
                        adjustment.update(type="shrink", reason="대체 자료 부족 — 같은 콘텐츠의 부담만 완화",
                                          dates=[request.next_card.date], auto_apply=True)
            elif difficulty and tomorrow["minutes"] > 5:
                tomorrow = {**tomorrow, "minutes": max(5, tomorrow["minutes"] - 5)}
                adjustment.update(type="shrink", reason="미완료·이해도 저하 — 5분 축소, 최소 5분",
                                  dates=[request.next_card.date], auto_apply=True)

        if (tomorrow and tomorrow["minutes"] == 5 and adjustment["type"] == "none"
                and (decision["case"] == "B" or decision["flags"]["difficulty_adjust"])):
            adjustment["reason"] = "다음 카드가 이미 최소 5분이므로 기존 분량을 유지합니다."

        # Questions use RAG evidence for advice; no arbitrary advice is generated.
        advice = None
        if classified["intent"] in ("question", "change_request") and not decision["flags"]["expert_referral"]:
            hits = self.tools.search(request)
            if hits:
                item = hits[0]["item"]
                remember(item)
                advice = f"자료 안내: '{item['title']}' — {item['expert_note']}"
            else:
                warnings.append("질문에 참고할 해당 단계 자료가 없어 구체적인 조언을 보류합니다.")
        if any(i.get("review_status") != "reviewed" for i in evidence_items.values()):
            warnings.append("미검수 자료를 사용한 개발용 코칭입니다. 실사용 전 전문가 검수가 필요합니다.")

        if decision["flags"]["expert_referral"]:
            lines = ["건강·심리·발달에 관한 판단은 학습 코칭 범위를 벗어납니다.",
                     "해당 분야 전문가와 상담해 주세요. 이 문의를 근거로 학습 계획을 바꾸지 않습니다."]
        elif decision["case"] == "A":
            title = self.tools.get_detail(request.today_card.content_id)["title"] if request.today_card else "오늘 활동"
            lines = [f"'{title}' 활동을 마치고 반응을 기록해 주셨어요. 오늘의 기록을 바탕으로 계획을 유지합니다."]
            if decision["flags"]["interest_dip"]:
                lines.append("오늘 흥미가 낮았다는 점을 확인했습니다. 하루 기록으로 교체하지 않고 다음 반응을 살펴봅니다.")
        elif decision["case"] == "B":
            lines = ["어려웠던 예를 하나 골라 부모가 먼저 천천히 보여 주세요. 다음에는 같은 활동을 짧게 함께 해 보세요."]
        else:
            lines = ["질문·변경 요청 또는 이어진 흥미 저하를 확인했습니다."]
            if decision["low_interest_streak"] >= 2:
                lines.append("다른 형식의 자료와 휴식일 선택을 함께 고려해 주세요. 휴식일은 부모가 직접 표시할 수 있습니다.")
        if advice:
            lines.append(advice)
        lines.append(adjustment["reason"] + ".")
        if adjustment["requires_parent_approval"]:
            proposal = adjustment["proposal"]
            if proposal:
                lines.append(f"변경 후보는 '{self.tools.get_detail(proposal['content_id'])['title']}'입니다. 승인 전에는 반영하지 않습니다.")
        if tomorrow:
            title = self.tools.get_detail(tomorrow["content_id"])["title"]
            lines.append(f"다음 학습일 {tomorrow['date']}: '{title}', {tomorrow['minutes']}분. {tomorrow['task']}")
        elif request.plan_status != "approved":
            lines.append("부모 승인 후 학습 카드를 시작할 수 있습니다.")
        else:
            lines.append("현재 다음 학습 카드가 없습니다.")
        lines.append(AI_LABEL)
        result = CoachResult(decision["case"], classified["intent"], classified["reason"], decision["flags"],
                             decision["reasons"], "\n".join(lines), adjustment, tomorrow,
                             [self.tools.evidence(i) for i in evidence_items.values()], warnings,
                             intent_version=classified.get("version", "custom-classifier"),
                             low_interest_streak=decision["low_interest_streak"])
        if self.llm is not None and not decision["flags"]["expert_referral"]:
            try:
                opening = generate_opening(self.llm, result, request, memory_summary or {})
                result.message = "\n".join([opening, *lines])
                result.model = getattr(self.llm, "model", "custom-llm")
                result.prompt_version = "bloomy-coach-llm-v1"
            except LLMError:
                warnings.append("LLM 코칭 호출 또는 검증에 실패해 로컬 코칭 메시지를 사용했습니다.")
        return validate_result(result, request, self.tools)
