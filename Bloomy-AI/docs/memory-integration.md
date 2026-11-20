# Long-term Memory 연동 계약 v1

이 문서는 초기 로컬 v1의 세부 계약을 보존합니다. 현행 LLM·정정·테스트 계약은 [통합 가이드](integration-guide.md)를 기준으로 합니다.

> 통합 전달 기준은 `integration-guide.md`입니다. 본 문서는 Memory 단계의 세부 참고 문서입니다.

## 빠른 시작

Python 3.12 표준 라이브러리의 sqlite3를 사용합니다. API 키·서버·외부 패키지가 필요하지 않습니다.
프로젝트 루트에서 실행합니다.

```powershell
python -m unittest discover -s tests -v
python -m examples.memory
```

예제는 `data/local/memory-demo.sqlite3`에 가상의 아이 1명과 고정 날짜 기록을 저장합니다.
같은 명령을 반복하거나 프로세스를 재시작해도 학습 기록은 2개로 유지됩니다.
기본 개발용 카탈로그는 모든 콘텐츠 형식이 activity이므로 연속 흥미 저하(C)를 판정해도
다른 형식으로 자동 교체하지 않습니다. 경고와 함께 기존 카드를 유지합니다.
이 동작은 대체 자료를 만들어내지 않기 위한 것입니다.
`--db`로 별도 경로를 지정할 수 있으나 실제 서비스 DB와 데모 DB를 분리하세요.

```python
from pathlib import Path
from ai.memory import MemoryService
from ai.rag import RecommendationEngine
from ai.contracts import RecommendationRequest
from ai.agent import CoachAgent

with MemoryService.from_sqlite(Path("data/local/learning.sqlite3")) as memory:
    memory.set_preferences(
        child_id=1, effective_date="2026-11-01",
        favorite_topics=["동물"], owned_materials=["demo-animal-001"],
    )
    rag = RecommendationEngine.from_file("data/catalog/sample.json", memory=memory)
    plan = rag.recommend(RecommendationRequest(
        age=5, base_level=2, start_date="2026-11-18",
    ), child_id=1)
    agent = CoachAgent(rag)  # RAG에 연결된 memory를 함께 사용합니다.
    # agent.coach(coach_request, event_id="feedback-123")
    context = memory.get_context(1, as_of="2026-11-18")
```

Memory가 없는 기존 호출은 그대로 동작합니다. RAG에 memory를 연결했다면 recommend에
child_id가 필수입니다. 코치에만 연결하려면 `CoachAgent(rag, memory=memory)`를 사용합니다.
연결의 close 또는 with 사용으로 파일 핸들을 해제해야 합니다.

## 저장 대상

| SQLite 테이블 | 내용 |
|---|---|
| memory_events | 아이·날짜·이벤트 ID, 수치형 피드백, 콘텐츠 ID, 세션 시간, 입력 지문, 코칭 결과 캐시 |
| memory_preferences | 아이·적용 날짜·선호 종류별 문자열 목록 |

아이 ID는 양의 정수이며 모든 조회·수정·삭제에 반드시 사용합니다.
학습 이력의 메모 원문은 저장하지 않습니다. 중복 입력 비교용 SHA-256 지문만 남깁니다.
기본 키워드 분류·템플릿의 코칭 결과와 카탈로그 인용은 저장됩니다.
커스텀 분류기·향후 LLM이 메모나 개인정보를 intent_reason/message에 복사하면 결과 캐시에
남을 수 있으므로 해당 확장 시에는 출력의 개인정보 제거를 별도로 구현해야 합니다.
SHA-256 지문과 SQLite 파일은 암호화가 아닙니다. 운영용 암호화·접근 통제는 백엔드 책임입니다.

최초 파일 생성 시 스키마 v1을 초기화합니다. 알려지지 않은 user_version은 거부하며
팀 백엔드 DB를 마이그레이션하거나 변경하지 않습니다. 전용 로컬 DB 경로를 사용하세요.

## 서비스 메서드

- `record_feedback(feedback, event_id=None, content_id=None, minutes=None)`:
  새 기록이면 True, 완전히 같은 이벤트 재시도면 False. 코치 없이 과거 이력을 가져올 때 사용합니다.
  콘텐츠 ID의 실제 존재 여부는 호출자가 검증합니다. 카드를 함께 제공한 코치 경로는 카탈로그를 검증합니다.
- `get_context(child_id, as_of)`: 해당 날짜까지의 history, preferences, summary 반환.
  미래 날짜 자료는 포함하지 않습니다. 날짜는 YYYY-MM-DD이며 타임존 없는 학습 날짜입니다.
  history에는 아이 ID·날짜·완료도·만족도·흥미·이해도·휴식일·콘텐츠 ID·시간이 들어갑니다.
- `set_preferences(child_id, effective_date, favorite_topics=None, owned_materials=None)`:
  종류별 전체 목록 교체. None은 변경 없음, []는 해당 날짜부터 비우기입니다.
  날짜별 버전을 남겨 과거 조회에 미래 선호가 섞이지 않습니다.
  항목당 200자, 종류별 100개까지 허용하며 중복은 제거합니다.
- `delete_feedback(child_id, day)`: 해당 기록과 결과 캐시 삭제, 삭제 건수 반환.
  과거 기록 수정은 이 메서드로 삭제한 뒤 올바른 Feedback을 다시 입력합니다.
- `delete_child(child_id)`: 해당 아이의 모든 이력·선호·결과 캐시 삭제.
  다른 아이의 데이터는 유지합니다. SQLite secure_delete를 사용하지만 백업 파일은 별도 관리 대상입니다.

선호 문자열은 보호자가 제공한 명시적 정보로 취급합니다. 메모에서 자동으로 선호 소재나
실패 원인을 추측해 저장하지 않습니다. 성과에서 도출하는 선호·어려움은 콘텐츠 ID 단위의 관찰입니다.

## 반응 추이

summary는 저장 이력에서 조회할 때 계산하므로 별도 집계 테이블의 갱신 지연이 없습니다.

- 현재 7일과 이전 7일의 학습 기록 수, 평균 흥미·이해도·만족도, 평균 변화량
- 조회 기준일에서 역으로 계산한 연속 학습일·낮은 흥미 연속일·낮은 이해도 연속일
- 콘텐츠별 관찰 수·평균 반응과 시간별 관찰 수·평균 흥미
- 같은 콘텐츠의 2회 이상 관찰에서 평균 흥미≥4: preferred_content_ids
- 같은 콘텐츠의 2회 이상 관찰에서 평균 이해도≤2: weak_content_ids

휴식일은 평균과 학습일 수에서 제외하며 날짜 공백·휴식일은 연속일을 끊습니다.
관찰이 없는 평균·변화량은 0 대신 null입니다. 선호·어려움은 동시에 성립할 수 있습니다.
이 지표는 진단·인과관계·교육 효과 보장이 아닙니다. 시간별 평균만으로 시간 상한을 자동 변경하지 않습니다.

## RAG 연결

recommend의 시작 날짜까지 저장된 선호와 반응을 조회합니다.
입력의 소재·교재 목록과 저장 목록을 합쳐 검색하고, 보유 교재 우선 → 반복 어려움 자료 후순위 →
관찰된 선호 콘텐츠 우선 → 기존 검색 관련도 순으로 정렬합니다.
연령·레벨·시간 필터와 부모 승인 전 draft 상태는 유지합니다. 레벨을 자동 승급하지 않습니다.
반응이 적합성을 입증하는 것은 아니며 검수된 카탈로그 조건을 대체하지 않습니다.
RecommendationResult.memory_context에 사용한 기준일·선호·요약을 반환합니다.
입력 배열로 저장 선호를 지울 수는 없고 set_preferences(..., [] )로 명시적으로 비워야 합니다.

## 코치 연결과 트랜잭션

1. 현재 피드백 날짜보다 이전의 저장 이력을 읽고 명시적 history와 합칩니다.
   같은 날짜의 수치가 다르면 MemoryConflictError입니다. 전달한 history는 참조만 하며 자동 저장하지 않습니다.
2. 당일까지 유효한 소재·보유 교재 선호를 합쳐 기존 C → B → A 판정과 RAG 도구에 전달합니다.
3. 코칭 결과를 검증하고 오늘의 피드백·결과를 같은 SQLite 트랜잭션에서 저장합니다.
   이전 7일 관찰 요약을 메시지에 덧붙이되 확신 문구는 계속 비웁니다.
4. 동일 요청 재시도에는 캐시를 반환합니다. 재분류·재조정하지 않습니다.

아이·날짜당 피드백은 1개, 아이별 event_id는 유일합니다.
event_id를 생략하면 `feedback:YYYY-MM-DD`를 사용합니다. 같은 날짜/ID에 다른 입력은
MemoryConflictError(ValueError 하위)입니다. 원래 카드·계획 상태 등 요청도 변경된 재시도는 거부합니다.
원문 메모가 달라도 입력 지문이 달라지므로 충돌입니다. 휴식일의 무시되는 항목은 학습 기록에 남기지 않습니다.
같은 DB에 여러 연결이 있어도 BEGIN IMMEDIATE와 고유 제약으로 중복 입력을 직렬화합니다.
계산·저장 오류는 롤백하며 기본 10초 SQLite busy timeout 후 잠금 오류가 발생할 수 있습니다.

과거 기록 추가·삭제와 선호 변경은 그 날짜 이후의 결과 캐시를 무효화합니다.
이에 따라 같은 요청을 다시 계산하면 결과가 바뀔 수 있습니다. 백엔드의 기존 카드는 자동으로
변경되지 않으며, 이미 적용한 피드백 조정은 백엔드 이벤트 ID로 중복 방지해야 합니다.
minutes는 차감 명령이 아니라 목표 시간의 절대값입니다.

휴식일도 이력에는 저장하지만 메시지·조정은 생성하지 않습니다.
미승인 계획과 부모 변경 요청의 승인 경계도 유지합니다.
CoachResult.memory_context에는 이전 날짜까지의 요약과 사용한 선호를 반환합니다.

## 백엔드의 책임과 범위

계정 소유권·법정대리인 동의·미래 피드백 금지·승인 기록 확인은 백엔드에서 처리합니다.
Memory의 SQLite 트랜잭션은 백엔드의 계획/카드 DB와 분리되어 있습니다.
실제 카드 반영·승인·재시도 조율에 원자성이 필요하면 통합 어댑터/이벤트 처리 전략을 마련해야 합니다.
임의의 child_id를 아는 것만으로 조회 권한이 생기지 않도록 인증 계층에서 제한하세요.

실행 예제의 가상 데이터 외 사용자 데이터는 data/local/ 아래에 저장하고 Git에서 제외합니다.
원격 DB·GitHub 업로드·API 키·백그라운드 작업은 이 구현에 포함하지 않습니다.
