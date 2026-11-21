# AI 코치 Agent 연동 계약 v1

이 문서는 초기 로컬 v1의 세부 계약을 보존합니다. 현행 LLM·정정·테스트 계약은 [통합 가이드](integration-guide.md)를 기준으로 합니다.

> 통합 전달 기준은 `integration-guide.md`입니다. 본 문서는 Agent 단계의 세부 참고 문서입니다.

## 실행과 입력

Python 3.12 이상, 표준 라이브러리만 사용합니다. API 키·설치·DB·네트워크가 필요하지 않습니다.

```powershell
python -m examples.coach
python -m unittest discover -s tests -v
```

```python
from ai.agent import CoachAgent, CoachRequest, Feedback, LearningCard
from ai.rag import RecommendationEngine

rag = RecommendationEngine.from_file("data/catalog/sample.json")
agent = CoachAgent(rag)
item = rag.catalog[0]
next_card = LearningCard(
    child_id=1, date="2026-11-19", content_id=item["id"],
    task=item["task"], minutes=10, check_point=item["check_point"],
)
result = agent.coach(CoachRequest(
    child_id=1, age=5, base_level=2, plan_status="approved",
    feedback=Feedback(child_id=1, date="2026-11-18", completion="partial",
                      satisfaction=3, interest=3, comprehension=2),
    next_card=next_card,
))
payload = result.to_dict()
```

`plan_status`의 기본값은 `draft`입니다. `approved`는 실제 부모 승인을 확인한
백엔드가 저장소에서 읽어 전달해야 합니다. 클라이언트가 보내는 문자열을 그대로 신뢰하면 안 됩니다.
이 모듈은 인증·승인 기록·DB 갱신·HTTP 요청을 수행하지 않습니다.

- Feedback: child_id(양의 정수), date(YYYY-MM-DD), completion(full/partial/none),
  satisfaction/interest/comprehension(정수 1~5), memo(최대 500자), rest_day(bool).
- 휴식일에는 날짜·아이 ID·rest_day만 검증하고 나머지 입력은 무시합니다.
- history: 같은 아이의 과거 Feedback 배열. 날짜 중복과 현재·미래 이력은 거부합니다.
- today_card: 선택, 피드백과 같은 날짜. next_card: 선택, 피드백 이후의 다음 예정 카드.
  주말이 끼어도 다음 학습일을 전달할 수 있습니다. 응답 이름 `tomorrow`는 다음 예정 카드를 뜻합니다.
- 모든 카드는 동일 아이·알려진 콘텐츠·연령 조건·세션 시간 상한을 충족해야 합니다.
- age/base_level/session_minutes/goal/owned_materials/favorite_topics는 RAG와 같은 계약입니다.
- 미래 피드백 금지, 계정 소유권, 중복 제출, 휴식일의 성취 분모 제외는 백엔드가 처리합니다.
  모듈은 테스트 재현성을 위해 시스템 시계를 읽지 않습니다.
- 입력 오류·알 수 없는 콘텐츠는 ValueError. 후보 부족은 예외 대신 warnings와 기존 카드 유지로 처리합니다.

## 세 단계 처리

1. `intent.py`: 별도 분류기. 기본 키워드 우선순위는 out_of_scope → change_request → question → none.
   교체 가능한 분류기는 `classify(memo)`에서 `{intent, reason, version?}`를 반환합니다.
   잘못된 스키마·지원하는 실행 오류는 키워드 분류로 폴백합니다.
2. `rules.py`: 순수 규칙. 휴식일은 SKIP. 범위 밖 문의는 C+expert_referral.
   질문·변경 요청 또는 캘린더 인접 2일 흥미≤2는 C. 이후 미완료 또는 이해도<3은 B.
   그 외는 A. C+B 중복은 difficulty_adjust 플래그를 남깁니다.
3. `coach.py`: 카탈로그 조회·RAG 검색 도구를 호출해 조정안과 템플릿 메시지를 만듭니다.
   출력 가드레일이 규칙 결과·근거·승인 경계를 다시 검증합니다.

단발 흥미 저하는 A+interest_dip. 날짜 공백·휴식일은 2일 연속 조건을 끊습니다.
이력 정렬 순서에 의존하지 않으며 `low_interest_streak`는 분기용 0/1/2 값입니다.
장기 연속일 수치·기억 저장과 연결하는 방법은 `memory-integration.md`를 참고하세요.

## 조정과 승인 경계

| 상황 | adjust.type | 반환 결과 |
|---|---|---|
| A | none | 다음 카드 유지 |
| B, 또는 질문 C+B | shrink | 같은 콘텐츠를 5분 축소, 최소 5분 |
| 인접 2일 흥미 저하 | swap | 같은 레벨·스킬, 다른 형식, 기존 시간 이하 |
| 위 조건+B | swap_easy | 한 레벨 아래·같은 스킬·다른 형식 |
| 부모 변경 요청 | propose_swap | 기존 카드 유지, 후보만 별도 반환, 승인 필요 |
| 범위 밖 문의 | none | 전문가 안내, 카드 변경 없음 |
| 휴식일 | none | 메시지·다음 카드 응답 없음, 실제 계획은 변경하지 않음 |
| draft/done/superseded | none | 카드 활성화·조정 없음 |
| 다음 카드 없음 | none | 새 카드를 임의로 만들지 않음 |

적절한 교체 후보가 없으면 교체하지 않고 경고합니다. C+B는 부담 완화를 위해 shrink로
폴백합니다. L1에서 L0를 만들지 않습니다. 변경 요청은 이 경우에도 부모 승인 전 조정을 하지 않습니다.
부모 변경 요청 후보는 목표 스킬을 유지하며 다른 형식 조건은 강제하지 않습니다.
자유 메모의 새 목표·시간·레벨을 정확히 해석하는 기능은 아직 없습니다.
큰 목표 변경·전체 재계획은 RAG 추천 후 별도 부모 승인 절차를 사용하세요.

`adjust` 필드:

```json
{
  "type": "propose_swap",
  "reason": "부모 변경 요청 — 확인 후에만 반영",
  "dates": ["2026-11-19"],
  "proposal": null,
  "requires_parent_approval": true,
  "auto_apply": false
}
```

proposal은 후보가 있으면 LearningCard 형태의 객체이며, 없으면 null입니다.
`auto_apply=true`는 **백엔드가 자동 반영해도 되는 조정안**이라는 뜻입니다.
모듈 자체가 DB를 변경했다는 뜻이 아닙니다. `tomorrow`는 허용된 소규모 조정안을 반영한 예상 카드입니다.
승인 대기 상태에서는 반드시 기존 카드가 들어갑니다.
백엔드는 현재 계획 상태·대상 카드 버전을 다시 확인한 뒤 원자적으로 변경하고,
중복 피드백 처리로 조정이 두 번 적용되지 않도록 해야 합니다.
제안 승인 엔드포인트는 이 모듈에 포함되지 않습니다. 백엔드가 별도 계약을 구현해야 합니다.

## 출력과 제한

CoachResult.to_dict(): case, memo_intent, intent_reason, flags, reasons, message,
adjust, tomorrow, evidence, warnings, confidence_sentence, is_ai_generated,
model, prompt_version, intent_version, low_interest_streak.

메시지는 카탈로그 제목·활동·해설만 인용하고 AI 라벨을 붙입니다.
개발용 미검수 자료 사용은 경고합니다. 확신 문구는 추이 검증이 마련되기 전까지 항상 비웁니다.
health/발달 문의는 진단하지 않고 전문가에게 안내합니다.
키워드 분류는 부정문·암시·복합 의도를 정밀하게 이해하지 못하며 전문가 상담 분류의 완전성을 보장하지 않습니다.
이 구현은 결정적 도구 호출·규칙·템플릿을 사용하는 로컬 Agent이며, LLM의 자율 추론·문장 생성은 포함하지 않습니다.
RAG 검색도 로컬 TF-IDF를 사용합니다. Memory를 연결하면 이전 이력과 선호를 읽고 결과를 SQLite에 저장합니다.

기존 백엔드 feedback 응답과 완전히 같은 객체가 아닙니다. `record` 저장과
응답 필드 매핑은 백엔드 책임이며, adjust.proposal은 기존 제목 문자열 대신 카드 객체입니다.
통합 어댑터에서 기존 형식이 필요하면 제목으로 변환하고 상세 후보는 별도 보관하세요.
최종 HTTP 회귀 테스트는 백엔드에 통합한 뒤 실행해야 합니다.
