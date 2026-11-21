# RAG 추천 엔진 연동 계약 v1

이 문서는 초기 로컬 v1의 세부 계약을 보존합니다. 현행 LLM·정정·테스트 계약은 [통합 가이드](integration-guide.md)를 기준으로 합니다.

> 통합 전달 기준은 `integration-guide.md`입니다. 본 문서는 RAG 단계의 세부 참고 문서입니다.

## 호출

Python 3.12 이상에서 프로젝트 루트를 import 경로로 사용합니다.
현재 외부 패키지, API 키, 서버, DB가 필요하지 않습니다.

```python
from ai.contracts import RecommendationRequest
from ai.rag import RecommendationEngine

engine = RecommendationEngine.from_file("data/catalog/sample.json")
result = engine.recommend(RecommendationRequest(
    age=5, base_level=2, start_date="2026-11-17",
    goal="듣기", session_minutes=10,
    owned_materials=("개발용 소리 놀이 카드",),
    favorite_topics=("동물",),
))
payload = result.to_backend_payload()
```

`payload`는 기존 `POST /api/children/{id}/plans`용 `days`, `explanation`,
`base_level`을 포함합니다. 각 day는 `date`, `content_id`, `task`, `minutes`,
`check_point`입니다. 모듈은 HTTP 요청이나 DB 변경을 실행하지 않습니다.
백엔드는 인증·소유권 확인, 콘텐츠 ID 존재 확인, 초안 저장, 부모 승인,
실제 카드 활성화를 담당합니다. 로컬 카탈로그와 백엔드 카탈로그의 ID를 일치시켜야 합니다.

`result.to_dict()`에는 추가로 `evidence`, `warnings`, `status=draft`,
`engine_version`이 있습니다. evidence에는 콘텐츠 ID·제목·청크 ID·인용문·출처·링크·검색 점수·보유 여부가 있습니다.
점수는 검색 정렬값이며 교육 적합성 확률이나 효과 보장이 아닙니다.

## 입력과 실패

- age: 정수 4~7, base_level: 정수 1~5. 진단은 호출자가 제공하는 초기 가설입니다.
- start_date: YYYY-MM-DD. 시작일을 포함해 다음 평일 20개를 생성합니다. 공휴일은 제외하지 않습니다.
- session_minutes: 10/15/20. 콘텐츠 시간이 상한을 넘으면 제외합니다.
- goal: 비어 있지 않은 문자열. 한영 스킬명과 파닉스 검색 지원.
- owned_materials/favorite_topics: 문자열 배열. 보유 교재는 제목 부분 일치 또는 ID 일치.
- top_k: 1~100. 검색 후보 수이며 계획 일수는 항상 20개입니다.
- 잘못된 요청·카탈로그: `ValueError` (잘못된 구조로 인한 TypeError 등은 호출부에서도 방어).
- 적합 후보 없음: `InsufficientCatalogError` (`ValueError` 하위). 임의 자료를 만들거나 연령·단계 제한을 풀지 않습니다.
- 자료 부족·보유 교재 미일치·미검수: `warnings`. 화면에서 사용자에게 전달해야 합니다.

## 카탈로그

UTF-8 JSON 배열. 필수 필드는 sample.json을 참고합니다. 기존 canonical 필드에
`task`, `check_point`를 추가해 활동 설명도 카탈로그에 근거하도록 했습니다.
현재 레거시 stage/minutes 등은 지원하지 않습니다. 연동 전에 canonical 형식으로 변환해야 합니다.
`review_status=reviewed`는 검수자가 실제 검수한 자료에만 지정해야 합니다.
코드는 이 표기의 진위를 검증하지 않으므로 실사용 검수 게이트는 담당자가 관리합니다.

sample.json의 3개 항목은 L2 개발용 가상 자료이며 example.org 링크는 실제 교육 자료가 아닙니다.
60개 콘텐츠 확보·연령별 15개 이상·공식 링크 확인·전문가 검수 기준을 충족하지 않습니다.

## 구현 범위와 확장

현재 파이프라인: 자료 검증 → 콘텐츠별 3청크 → 연령/레벨/시간 필터 →
로컬 희소 벡터(TF-IDF cosine) 검색 → 보유 교재·스킬 관련도 재정렬 →
결정적 템플릿 계획 생성 → 근거·일정 검증.
검색 후보를 순환하는 반복 학습 초안이며 단계 상승을 자동으로 추정하지 않습니다.
전문가 가이드의 별도 수집, 신경망 임베딩, LLM 문장 생성은 아직 구현하지 않았습니다.
상용 LLM 기반 RAG 완성본으로 간주하지 않습니다.

`Retriever.search(request)` 인터페이스를 구현해 벡터 DB 검색으로 교체할 수 있습니다.
새 검색기는 동일한 hit 구조를 반환해야 하며 최종 카탈로그 검증은 유지해야 합니다.
Agent 연동은 `coach-integration.md`, 선택적 SQLite 영속 저장은 `memory-integration.md`를 참고하세요.
`RecommendationEngine.from_file(path, memory=memory)`를 사용하면
`recommend(request, child_id=...)`에서 아이별 저장 선호·반응을 조회합니다.
기본 memory=None 호출은 기존처럼 DB 없이 동작합니다.

## 검증

```powershell
python -m unittest discover -s tests -v
python -m examples.recommend
```

테스트는 네트워크와 환경변수에 의존하지 않습니다. 백엔드 통합 후에는 팀 저장소의
API 회귀 테스트를 백엔드 담당자가 별도로 실행해야 합니다.
