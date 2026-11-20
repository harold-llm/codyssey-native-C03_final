# Bloomy-AI 백엔드 통합 가이드

문서 버전 local-v2 · 2026-11-18

이 문서는 RAG·AI 코치 Agent·Long-term Memory의 **현재 로컬 구현**을 연동하기 위한 단일 기준 문서입니다.
이전 단계별 문서의 핵심 계약을 합쳤습니다. 아래 Python 계약이 현재 구현 기준이며,
팀 저장소의 HTTP API를 실제로 수정하거나 검증했다는 의미는 아닙니다.

## 1. 전달 범위와 실행

- Python 3.12 이상입니다. LLM과 응답 검증 테스트에 `requirements.txt`의 `jsonschema`를 설치합니다.
- RAG는 TF-IDF 검색과 구조화 LLM 일정 생성 경로를 제공합니다. 키를 설정하지 않거나 호출에 실패하면 검색과 템플릿을 사용합니다.
- Agent는 별도 LLM 의도 분류와 문장 선택 호출, 결정적 Python 분기, 카탈로그 도구를 조합합니다. 로컬 폴백을 제공합니다.
- Memory는 SQLite 영속 저장과 아이별 최근 7일, 선호, 누적 반응, 수정·삭제를 지원합니다.
- 신경망 임베딩, 실제 인증·카드 승인 처리·알림·스케줄러는 팀 통합 범위입니다.
- GitHub 원격 저장소를 수정하거나 커밋하지 않습니다.

Bloomy-AI 프로젝트 폴더에서 실행합니다. 가상환경은 선택입니다.

```powershell
python --version
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python -m examples.integration_demo
```

명령이 성공하면 다음 형태의 JSON 요약을 출력합니다. 검증 실패는 종료 코드가 0이 아닙니다.

```json
{
  "status": "passed",
  "checks_passed": 57,
  "run_directory": ".../data/local/integration-runs/run-...",
  "primary_child_records": 10
}
```

데모는 매번 새 디렉터리와 전용 SQLite 파일을 생성해 기존 데이터를 보존합니다.
경로를 직접 정할 경우 **아직 존재하지 않는 디렉터리**를 사용합니다.

```powershell
python -m examples.integration_demo --run-dir data/local/handoff-run-01
```

같은 경로로 재실행하면 덮어쓰지 않고 실패합니다. 새 경로를 쓰거나 기본 명령을 다시 실행하세요.
일반 메모리 예제 `python -m examples.memory`는 별도 고정 데모 DB를 사용하므로 명령을 반복해도 기록은 2개입니다.
두 예제의 실행 방식은 의도적으로 다릅니다.

## 2. 통합 데모에서 확인하는 흐름

```text
아이별 선호 저장
  → RAG 20일 계획 초안
  → 미승인 차단 확인
  → 데모 부모 승인
  → 10일 피드백 / Agent / SQLite 저장
  → 허용된 소규모 조정을 다음 카드에 반영
  → 부모 변경 요청은 제안으로 보관
  → 두 번째 데모 승인 후에만 제안 반영
  → 누적 이력을 읽어 새 RAG 초안 생성
  → SQLite 연결 재개 후 기록·재시도 캐시 확인
```

승인과 실제 카드 반영은 `examples.integration_demo.DemoBackend`가 JSON 상태로 시뮬레이션합니다.
스크립트에 등장하는 승인은 가상 시나리오이며 실제 보호자의 동의가 아닙니다.
초안 차단 미리보기는 메모리 없는 Agent로 실행해 승인 전 피드백을 저장하지 않습니다.
실제 제품에서도 승인 전 피드백 제출을 막을지는 백엔드의 API 정책으로 적용해야 합니다.
Memory가 연결된 Agent 자체는 draft 상태로 전달된 피드백도 이력에 저장할 수 있습니다.

| 가상 학습일 | 상황 | 기대 분기 | 조정 |
|---|---|---|---|
| 2026-11-16 | 순조 | A | 유지 |
| 2026-11-17 | 일부 완료·이해도 낮음 | B | 5분 축소 |
| 2026-11-18 | 단발 흥미 저하 | A | 유지 + interest_dip |
| 2026-11-19 | 인접 2일 흥미 저하 | C | 같은 레벨 다른 형식 |
| 2026-11-20 | C와 B 중복 | C | 한 레벨 아래 다른 형식 |
| 2026-11-23 | 휴식일 | SKIP | 메시지·조정 없음 |
| 2026-11-24 | 부모 변경 요청 | C | 승인 대기 제안 |
| 2026-11-25 | 공부 방법 질문 | C | RAG 근거 안내 |
| 2026-11-26 | 범위 밖 발달 문의 | C | 전문가 상담 안내 |
| 2026-11-27 | 조정 이후 순조 | A | 유지 |

이외에 동일 요청 재시도, 백엔드 중복 반영 방지, 충돌 입력 거부, 아이별 격리,
날짜별 조회, 휴식일 집계 제외, 관찰 선호의 RAG 반영, 아이별 삭제를 검증합니다.
가상 아이 1번은 10개 기록(학습 9일+휴식 1일), 2번은 선호 관찰용 2개 기록을 유지합니다.
삭제 검증용 3번만 삭제합니다. 실행에 사용자 정보는 사용하지 않습니다.

실행 디렉터리에는 다음 파일이 남습니다.

| 파일 | 용도 |
|---|---|
| catalog.json | 6개 가상 콘텐츠의 실행 스냅샷 |
| initial-plan.json | 최초 RAG 초안·검색 근거·메모리 컨텍스트 |
| backend-state.json | 모의 승인·다음 카드 변경·승인 대기 처리 결과 |
| memory.sqlite3 | 아이별 학습 이력·선호·코칭 캐시 |
| next-plan.json | 누적 이력 사용 후 새 RAG 초안 |
| report.json | 57개 검증과 시나리오별 요청·응답·최종 메모리 |

모든 콘텐츠와 example.org 링크는 가상 테스트 자료입니다. 전문가 검수 완료 표시를 하지 않습니다.
기존 3개 샘플에서 형식·레벨별 가상 자료를 추가해 swap/swap_easy까지 검증합니다.
실사용 카탈로그 60개 내외·연령별 15개 이상 확보와 공식 링크·전문가 검수는 별도 필요합니다.

## 3. 책임 경계

| AI 모듈 | 백엔드 |
|---|---|
| 요청 형식·아이 ID 일치·카탈로그 근거 검증 | 인증·계정 소유권·법정대리인 동의 |
| RAG 초안과 근거 생성 | 초안 업로드·저장·부모 승인 기록·활성화 |
| C/B/A 판정·코칭·다음 카드 조정안 반환 | 현재 카드 버전 확인·실제 계획/카드 변경 |
| 같은 이벤트의 로컬 SQLite 재시도 처리 | API 중복 제출·백엔드 DB와의 재시도 조율 |
| SQLite 이력·선호·수치 요약 | 개인정보 정책·미래 피드백 거부·HTTP 응답 매핑 |
| 아이별 삭제 메서드 | 모든 관련 저장소·백업·외부 저장의 삭제 조율 |

AI 모듈은 LLM 설정 시 모델 API만 호출합니다. 팀 HTTP API와 DB는 백엔드가 호출·관리합니다.
SQLite를 쓰지 않으려면 MemoryRepository 계약에 맞는 별도 구현이 필요합니다.
현재 PostgreSQL 어댑터는 없습니다.

## 4. 객체 생성과 수명

```python
from pathlib import Path
from ai.memory import MemoryService
from ai.llm import OpenAIClient
from ai.rag import RecommendationEngine
from ai.agent import CoachAgent

memory = MemoryService.from_sqlite(Path("data/local/learning.sqlite3"))
llm = OpenAIClient.from_env()  # 키 미설정 시 None
rag = RecommendationEngine.from_file("data/catalog/sample.json", memory=memory, llm=llm)
coach = CoachAgent(rag)  # rag.memory를 함께 사용

# 실제 서비스 종료 시 실행
# memory.close()
```

짧은 작업은 `with MemoryService.from_sqlite(...) as memory:`를 사용합니다.
단일 SQLite 연결의 트랜잭션은 잠금으로 보호하고 여러 연결의 쓰기는 SQLite가 직렬화합니다.
busy timeout은 10초입니다. 현재 코칭의 중복 방지와 저장은 한 트랜잭션에서 동작하므로 LLM을 함께 구성하면 호출 동안 SQLite 쓰기 잠금이 유지됩니다. 각 네트워크 호출의 소켓 타임아웃은 15초입니다. 팀의 다중 요청 환경에서는 백엔드 이벤트 처리와 저장소 트랜잭션을 통합하며 모델 호출을 쓰기 잠금 밖에서 처리하는 경계 설계가 필요합니다.
로컬 DB 경로는 data/local 아래에 두며 .gitignore에 data/local과 SQLite 파일 제외 규칙이 있습니다.

Memory 없이 사용하는 기존 `RecommendationEngine.from_file(path)`와 `CoachAgent(rag)`도 유지됩니다.
RAG에 Memory를 연결했다면 recommend에 child_id를 반드시 전달해야 합니다.
코치에만 연결할 때는 `CoachAgent(rag, memory=memory)`를 사용합니다.

## 5. RAG 입출력

```python
from ai.contracts import RecommendationRequest

request = RecommendationRequest(
    age=5, base_level=2, start_date="2026-11-16", goal="듣기",
    session_minutes=10, owned_materials=("demo-sound-001",),
    favorite_topics=("동물",), top_k=8,
)
result = rag.recommend(request, child_id=1)
backend_payload = result.to_backend_payload()
audit_payload = result.to_dict()
```

| 입력 | 제약 |
|---|---|
| age | 정수 4~7 |
| base_level | 정수 1~5. 진단 확정이 아닌 초기 가설 |
| start_date | YYYY-MM-DD, 시작일 포함 다음 평일 20개, 공휴일 별도 처리 없음 |
| goal | 비어 있지 않은 문자열. 한영 스킬·파닉스 검색 지원 |
| session_minutes | 10 / 15 / 20 |
| owned_materials, favorite_topics | 비어 있지 않은 문자열의 list 또는 tuple |
| top_k | 정수 1~100, 계획 일수가 아닌 검색 후보 수 |
| exposure_months | 선택, 0 이상 정수. 초기 노출은 짧은 후보를 우선 |
| exposure | 선택, 백엔드 범주 `none / some / much` |

`to_backend_payload()`는 다음 3개 필드만 반환합니다.

```json
{
  "days": [{
    "date": "2026-11-16", "content_id": "demo-sound-001",
    "task": "소리를 듣고 같은 그림을 함께 골라 보세요.",
    "minutes": 10, "check_point": "아이가 소리에 반응해 그림을 고르나요?"
  }],
  "explanation": "카탈로그 제목과 학습 방법 설명...",
  "base_level": 2
}
```

JSON의 days는 구조를 설명하기 위해 1개만 표시했으며 실제 생성 결과는 20개입니다.
기존 `POST /api/children/{id}/plans` 업로드용으로 매핑할 수 있습니다.
AI 결과의 content_id를 백엔드 카탈로그에도 먼저 등록해야 합니다.
모듈이 해당 엔드포인트를 호출하거나 계획을 승인하지는 않습니다.

`to_dict()`에는 추가로 status(draft), evidence, warnings, engine_version, memory_context, day_details가 있습니다. `day_details`는 동일 날짜·콘텐츠의 title, learning_goal, recommendation_reason을 포함합니다.
evidence는 content_id·title·chunk_id·excerpt·source·link·score·owned를 포함합니다.
검색 점수는 교육 적합성 확률이 아닙니다. memory_context는 조회 날짜·아이 ID·선호·요약입니다.

RAG는 연령·레벨·시간 필터 후 보유 교재를 우선합니다.
Memory가 있으면 반복 어려움 자료를 뒤로, 반복 고흥미 자료를 앞으로 배치합니다.
단계 승급·시간 증가·계획 활성화를 자동으로 수행하지 않습니다.
저장된 선호와 요청 목록은 합쳐 사용하므로 요청의 빈 배열만으로 저장 선호가 지워지지는 않습니다.

## 6. 카탈로그 계약

UTF-8 JSON 배열. 각 항목의 필수 필드는 다음과 같습니다.

| 필드 | 제약 |
|---|---|
| id, title, expert_note, trust_source | 비어 있지 않은 문자열, id 중복 금지 |
| age_min, age_max | 4~7, age_min ≤ age_max |
| level | 정수 1~5 |
| skill | listening / speaking / reading / writing |
| type | readers_series / phonics / worksheet / video / audio / activity |
| provider | purchase / link |
| link | https://로 시작하는 문자열 |
| session_minutes | 10 / 15 / 20 |
| task, check_point | 비어 있지 않은 문자열. 계획과 대체 카드의 활동 근거 |

`learning_goal`과 `review_status`는 선택 필드입니다. 검수된 자료만 대상으로 실행할 경우 `reviewed_only=True`를 지정합니다. 실제 검수된 자료에만 reviewed를 지정해야 합니다.
코드는 링크의 실제 유효성·공식 출처·검수 표기의 진위를 보장하지 않습니다.
이전 stage/minutes/why 같은 레거시 필드는 백엔드 어댑터에서 변환해야 합니다.
카탈로그 내용은 신뢰된 내부 자료로 관리하고 비밀값이나 부모 메모를 넣지 마세요.

## 7. 코치 입출력과 백엔드 필드 변환

```python
from ai.agent import CoachRequest, Feedback, LearningCard

def card_from_backend(row, authorized_child_id):
    if row is None:
        return None
    keys = ("date", "content_id", "task", "minutes", "check_point")
    return LearningCard(child_id=authorized_child_id, **{key: row[key] for key in keys})

# authorized_child_id와 plan_status는 인증·저장소 조회로 검증된 값이어야 합니다.
# today_row와 next_row도 같은 아이의 승인 계획에서 읽어 옵니다.
# request = CoachRequest(
#     child_id=authorized_child_id, age=profile.age, base_level=profile.level,
#     plan_status=stored_plan.status,
#     feedback=Feedback(child_id=authorized_child_id, date=feedback_date,
#         completion="partial", satisfaction=3, interest=3, comprehension=2),
#     today_card=card_from_backend(today_row, authorized_child_id),
#     next_card=card_from_backend(next_row, authorized_child_id),
#     session_minutes=profile.session_length,
# )
# result = coach.coach(request, event_id=stable_feedback_event_id)
```

Feedback는 child_id(양의 정수), date, completion(full/partial/none),
satisfaction·interest·comprehension(정수 1~5), memo(선택 문자열, 최대 500자), rest_day(bool)를 받습니다.
휴식일은 날짜·아이 ID·rest_day 외 피드백 값을 무시합니다.
LearningCard의 minutes는 5~20 정수이며 세션 상한 이하여야 합니다.
카드는 같은 아이 소유, 오늘 카드는 피드백과 같은 날짜, 다음 카드는 이후 날짜여야 합니다.
알 수 없는 content_id는 거부합니다. null content_id 카드에 대한 규칙형 코칭은 지원하지 않습니다.

CoachRequest의 plan_status 기본값은 draft이며 draft/approved/done/superseded를 허용합니다.
history는 선택적인 과거 Feedback 배열입니다. 중복 날짜·현재/미래 날짜·다른 아이 기록은 거부합니다.
Memory 사용 시 과거 기록은 자동으로 읽으므로 보통 history를 직접 제공할 필요가 없습니다.
명시적 history는 자동 저장하지 않으며 같은 날짜의 저장 수치와 다르면 충돌입니다.
시스템 날짜를 읽지 않으므로 미래 피드백 금지는 백엔드에서 별도로 검증해야 합니다.

CoachResult.to_dict() 필드:

| 그룹 | 필드 |
|---|---|
| 판정 | case, memo_intent, intent_reason, flags, reasons, low_interest_streak |
| 사용자 응답 | message, adjust, tomorrow, evidence, warnings, confidence_sentence |
| 추적 | is_ai_generated, model, prompt_version, intent_version, memory_context |

flags에는 difficulty_adjust, expert_referral, interest_dip이 들어갑니다.
low_interest_streak는 분기용 0/1/2 값이며 누적 연속일 수는 Memory summary를 사용합니다.
model은 local-rules이고 메시지는 AI 생성 표시로 끝납니다.
confidence_sentence는 현재 항상 빈 문자열입니다. 추이 저장만으로 성공 보장 문구를 활성화하지 않습니다.
tomorrow는 내일이라는 달력 날짜가 아니라 **다음 예정 카드**를 뜻하며, 주말 다음 평일일 수도 있습니다.

## 8. 분기와 승인 계약

판정 순서: 휴식일 → 범위 밖 문의 → C → B → A.

| 조건 | 판정·조정 |
|---|---|
| rest_day=true | SKIP, message=null, tomorrow=null, 조정 없음. 실제 다음 카드 삭제 아님 |
| out_of_scope | C + expert_referral, 전문가 안내, 카드 변경 없음 |
| question/change_request 또는 인접 2일 interest≤2 | C |
| 위 조건 미해당 + partial/none 또는 comprehension<3 | B |
| 나머지 | A |

휴식일이나 날짜 공백은 인접 2일 흥미 저하를 끊습니다. 단발 흥미 저하는 A+interest_dip입니다.
C와 B가 동시에 성립하면 C가 우선이고 difficulty_adjust를 남깁니다.

| adjust.type | 발생·반영 |
|---|---|
| none | 유지, 미승인 계획, 다음 카드 없음, 범위 밖 문의 등 |
| shrink | B 또는 질문 C+B: 같은 콘텐츠를 5분 축소, 최소 5분 |
| swap | 연속 흥미 저하: 같은 레벨·스킬, 다른 형식, 기존 시간 이하 |
| swap_easy | 위 조건+B: 한 레벨 아래·같은 스킬·다른 형식 |
| propose_swap | 부모 변경 요청: 후보만 반환, 부모 확인 전 기존 카드 유지 |

교체 후보가 없으면 자료를 만들거나 제약을 풀지 않고 warnings와 함께 교체를 보류합니다.
C+B의 대체 자료가 없거나 L1에서 하향할 수 없으면 shrink로 폴백합니다.
부모 변경 요청은 B와 겹쳐도 자동 축소하지 않고 승인 대기 상태를 유지합니다.
큰 목표 변경이나 전체 재계획은 RAG의 새 초안과 별도 승인으로 처리해야 합니다.
키워드 분류는 자유 문장의 새 목표·시간·레벨을 정밀하게 해석하지 못합니다.

```json
{
  "type": "propose_swap", "reason": "부모 변경 요청 — 확인 후에만 반영",
  "dates": ["2026-11-25"],
  "proposal": null,
  "requires_parent_approval": true,
  "auto_apply": false
}
```

proposal은 후보가 있으면 LearningCard 객체, 없으면 null입니다.
auto_apply=true는 백엔드가 반영해도 되는 **조정안**이라는 뜻이며 이미 DB를 수정했다는 뜻이 아닙니다.
tomorrow에는 허용된 소규모 변경의 예상 결과가 들어가고, 승인 대기일 때는 기존 카드가 들어갑니다.
모든 minutes는 차감 명령이 아닌 최종 절대값입니다. 재시도마다 5분을 다시 빼면 안 됩니다.

백엔드는 조정 반영 시 현재 승인 상태·대상 날짜·카드 버전·이벤트 처리 여부를 다시 확인합니다.
제안의 승인/거절 엔드포인트와 승인 이벤트 저장은 백엔드가 별도 구현해야 합니다.
외부 사용자가 보낸 plan_status=approved 문자열을 그대로 신뢰하지 마세요.

## 9. 기존 HTTP API와의 차이

- RAG 업로드는 days/explanation/base_level로 매핑할 수 있지만 엔드포인트 호출은 백엔드 담당입니다.
- CoachResult는 HTTP feedback 응답과 동일한 객체가 아닙니다. record 저장과 응답 조합은 백엔드가 합니다.
- adjust.proposal은 기존 제목 문자열 형식과 달리 카드 객체입니다. 상세 후보를 보존한 뒤
  기존 UI에 필요하면 카탈로그 title로 변환합니다. 제목만으로 승인·반영하지 마세요.
- LearningCard에는 child_id가 있습니다. 기존 HTTP 카드에 추가 내부 필드가 있다면 필요한 필드만 변환하세요.
- SKIP의 tomorrow=null은 다음 카드 제거 명령이 아닙니다. adjust.type=none을 함께 확인하세요.
- Memory summary와 audit evidence는 내부 추적용으로 보관하고 UI에 필요한 정보만 응답하세요.

## 10. SQLite Memory 계약

| 메서드 | 의미 |
|---|---|
| set_preferences(child_id, effective_date, favorite_topics=..., owned_materials=...) | 날짜별 선호 버전. None=유지, []=비우기 |
| record_feedback(feedback, event_id=None, content_id=None, minutes=None) | 새 기록 True, 동일 재시도 False |
| get_context(child_id, as_of) | 해당 날짜까지의 history/preferences/summary |
| delete_feedback(child_id, day) | 해당 날짜 삭제와 이후 결과 캐시 무효화, 삭제 수 반환 |
| delete_child(child_id) | 해당 아이의 이력·선호·코칭 캐시 삭제 |

아이 ID는 모든 조회·삭제에 필수입니다. 임의 ID를 안다는 것만으로 권한이 생기지 않도록 인증 계층에서 제한합니다.
선호 목록은 종류별 100개, 항목별 200자이며 중복은 제거합니다.
직접 record_feedback을 사용할 때 콘텐츠 ID의 실제 존재 여부는 호출자가 검증합니다.
카드가 포함된 코치 경로는 콘텐츠를 검증합니다.

summary는 저장 이력에서 조회 시 계산합니다.

- 현재 7일·이전 7일 평균 흥미/이해도/만족도와 기록 수, 평균 변화량
- 기준일에서 역으로 계산한 연속 학습일·낮은 흥미/이해도 연속일
- 콘텐츠별 관찰 수·평균 반응과 시간별 관찰 수·평균 흥미
- 콘텐츠 2회 이상 관찰, 평균 흥미≥4: 선호 콘텐츠
- 콘텐츠 2회 이상 관찰, 평균 이해도≤2: 반복 어려움 콘텐츠

휴식일은 평균·학습일 수에서 제외합니다. 결측 평균은 0 대신 null입니다.
선호와 어려움은 동시에 관찰될 수 있습니다. 시간별 평균은 인과관계나 진단이 아닙니다.
Memory는 선호를 메모에서 추측하지 않으며 자동 난이도 승급을 하지 않습니다.
RAG는 시작일까지, 코치는 피드백 전날까지의 학습 이력과 당일 유효 선호를 사용합니다.
미래 선호·기록이 과거 조회에 섞이지 않습니다.

## 11. 중복 요청·트랜잭션·오류 복구

아이·날짜당 피드백은 1개이고 아이별 event_id는 유일합니다.
기본 event_id는 feedback:YYYY-MM-DD이며 실제 API에서는 안정적인 피드백 이벤트 ID를 전달하는 것이 좋습니다.
같은 날짜/ID의 다른 피드백, 또는 기존 카드·계획 상태 등이 달라진 재시도는 MemoryConflictError입니다.
같은 요청은 저장한 결과를 반환하므로 원래 요청 스냅샷을 보존해야 합니다.
이미 조정된 다음 카드를 읽어 새 요청으로 조합하면 동일 이벤트 재시도로 인정되지 않을 수 있습니다.

Feedback 저장과 코칭 결과 캐시는 하나의 SQLite 트랜잭션입니다.
오류 시 롤백하지만 백엔드의 계획 DB까지 같은 트랜잭션으로 묶지는 않습니다.

권장 백엔드 처리 흐름:

1. 인증·동의·소유권·날짜·현재 승인 상태를 검증하고 이벤트 ID를 고정합니다.
2. 오늘/다음 카드의 원래 스냅샷과 요청을 백엔드 이벤트에 저장합니다.
3. Agent를 호출하고 결과를 이벤트에 연결합니다.
4. 백엔드 트랜잭션에서 카드 버전을 확인하고 절대값 변경 또는 승인 대기 제안을 저장합니다.
5. 이벤트를 처리 완료로 표시한 뒤 HTTP 응답을 만듭니다.
6. 3~4 사이 실패하면 원래 요청으로 캐시를 재조회하고 백엔드 이벤트의 처리 여부로 중복 반영을 막습니다.

과거 기록 추가·삭제와 선호 변경은 해당 날짜 이후의 결과 캐시를 무효화합니다.
이 경우 같은 요청의 재계산 결과가 달라질 수 있지만 백엔드 기존 카드는 자동으로 바뀌지 않습니다.
정정 이후 재계산을 새 반영 이벤트로 처리할지 백엔드 정책을 정하고 기존 승인 기록을 보존하세요.
정정은 `replace_feedback(feedback, content_id=..., minutes=...)`로 수행합니다. 이벤트 ID를 유지하며 같은 날짜를 원자적으로 수정합니다. `get_context(child_id, as_of)`는 전체 `history`, `recent_history`, 누적 `summary`를 반환합니다.

| 예외/상황 | 백엔드 대응 제안 |
|---|---|
| ValueError, 요청 구조의 TypeError | 입력 검증 오류로 매핑; 원문 내부 예외를 사용자에게 그대로 노출하지 않음 |
| InsufficientCatalogError(ValueError 하위) | 적합 자료 부족 안내, 임의 추천 금지 |
| MemoryConflictError(ValueError 하위) | HTTP 409 등 상태 충돌로 매핑 |
| SQLite 잠금/디스크 오류 | 5xx/일시 오류 처리, 동일 원래 요청 재시도 |
| warnings | 미검수·후보 부족·폴백 사실을 UI/운영 로그에 전달 |

## 12. 개인정보와 운영 전 확인

학습 이력에는 메모 원문을 저장하지 않고 입력 비교용 SHA-256 지문을 남깁니다.
기본 코치의 결과·카탈로그 인용·선호 문자열은 SQLite에 저장됩니다.
LLM 모드에서는 분류를 위해 부모 메모를 제공자에게 전송하므로 시연은 가상 메모를 사용합니다. 메시지 호출은 아이 ID·날짜·메모를 제외한 수치 요약과 카탈로그 근거를 사용합니다. 기본 모델의 메모 분류 이유와 코칭 문장은 정의된 선택지로 제한됩니다. 커스텀 분류기 결과는 메모 원문이 포함되지 않도록 연동부에서 검토합니다. SHA-256 지문과 SQLite 파일에는 암호화가 적용되어 있지 않습니다.
SQLite 파일도 암호화되어 있지 않습니다. 운영용 암호화·접근 통제·보존 기간·동의 철회는 백엔드 책임입니다.

현재 SQLite 스키마는 user_version=1이며 알 수 없는 버전은 거부합니다.
팀 DB 경로를 재사용하지 말고 전용 파일을 지정하세요.
delete_child는 해당 파일 안의 논리 데이터와 캐시를 지우며 secure_delete를 사용합니다.
백업·외부 저장·로그의 삭제는 별도 조율해야 합니다.

운영 전 확인 항목:

- 검수된 실제 카탈로그·공식 링크·백엔드 content_id 일치
- 인증·부모 동의·승인·제안 거절·카드 버전 검사·중복 반영 방지
- API 스키마 변환과 팀 백엔드 HTTP 회귀 테스트
- 실제 환경의 지연·동시성·SQLite 파일 권한·백업/삭제 정책
- 키워드 분류의 부정문·복합 의도·건강/심리 표현 한계 검증
- 전문가 검토와 실제 사용자 테스트; 로컬 데모 통과가 교육 효과를 입증하지 않음

## 13. 파일과 검증 기준

| 위치 | 책임 |
|---|---|
| ai/contracts.py | RAG 입출력 |
| ai/rag/ | 검증·검색·계획 생성 |
| ai/agent/ | 코치 입력·분류·규칙·도구·승인 가드레일 |
| ai/memory/ | 서비스·저장소 계약·SQLite·추이 계산 |
| examples/integration_demo.py | 10일 통합 데모와 모의 백엔드 |
| tests/test_integration_demo.py | 전체 오프라인 흐름·산출물·덮어쓰기 방지·CLI |
| docs/integration-guide.md | 본 통합 문서 |

검증은 아래 두 명령으로 재현합니다. 첫 명령은 기존 모듈 회귀 테스트도 포함합니다.

```powershell
python -m unittest discover -s tests -v
python -m examples.integration_demo
```

검증 실행 결과와 실 API 테스트 상태는 [검증 결과](test-results.md)를 참고하세요.
실제 팀 백엔드의 인증·HTTP·DB 통합 테스트는 이 결과에 포함되지 않습니다.

## 14. 다운로드한 백엔드와 API 키 없이 연결 확인

`ai/backend_adapter.py`는 세 가지 연결 함수를 제공합니다.

- `shared_catalog(backend_rows, ai_metadata)`는 백엔드 목록에 등록된 ID와 AI 메타데이터의 교집합을 사용합니다. 공통 필드가 다르면 오류를 반환합니다. 카탈로그 원본에 AI용 활동과 검수 상태를 함께 관리할 수 있습니다.
- `recommendation_request(child, start_date, goal=...)`는 백엔드의 `level`, `session_length`, `exposure`를 옮기고 쉼표·세미콜론·줄바꿈으로 구분된 관심사와 교재를 파싱합니다. 현재 팀 프로필은 목표와 노출 개월을 저장하지 않으므로 필요한 경우 호출자가 별도로 전달합니다.
- `coaching_request(child, feedback, catalog=..., plan_status=..., today=..., next_card=..., history=...)`는 인증·소유권 확인 후 읽은 행을 AI 입력으로 변환합니다. 승인 상태 기본값은 `draft`입니다. 카탈로그에서 사라졌거나 나이·시간 조건에 맞지 않는 카드는 조정에 사용하지 않습니다.

아래 명령은 내려받은 팀 백엔드의 `dispatch()`를 호출합니다.

```text
python -m examples.backend_smoke /path/to/team-backend-checkout
```

임시 SQLite에 가상 샘플을 등록하고 가상 계정으로 인증합니다. 5세 L1과 7세 L3의 20개 카드 계획 등록, 승인 전 비활성, 승인 후 조회, 변경안 승인 대기, 새 초안 등록 시 기존 승인 유지 순서로 확인합니다. 코치 테스트는 어댑터와 AI 모듈을 직접 호출합니다. 팀의 피드백 라우트 교체, 실제 콘텐츠 등록, PostgreSQL 저장, 외부 API는 백엔드 연동 작업입니다. 기존 승인 계획을 먼저 종료하는 팀 `/replan` 경로에는 백엔드 담당자의 변경이 필요합니다.
