# Bloomy AI

만 4~7세 영어 학습을 위한 독립 Python 모듈입니다. 카탈로그 기반 4주 추천 초안, 부모 피드백 코칭, SQLite 아이별 장기 기억을 제공합니다. 팀 백엔드 연동은 [통합 가이드](docs/integration-guide.md)를 기준으로 합니다.

## 로컬 실행

Python 3.12 이상이 필요합니다. 프로젝트 최상위에서 다음 명령을 실행합니다.

```text
python -m venv .venv
```

Windows PowerShell에서는 `.\.venv\Scripts\Activate.ps1`, macOS/Linux에서는 `source .venv/bin/activate`로 활성화합니다.

```text
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python -m examples.ai_demo
python -m examples.integration_demo
```

오프라인 예제는 API 키와 네트워크 없이 TF-IDF 검색, 규칙, 템플릿으로 실행합니다. 신규 단위 테스트에는 `jsonschema`가 필요합니다. [시연 시나리오](docs/demo-scenario.md)와 [검증 결과](docs/test-results.md)를 참고하세요.

## 실제 LLM API 모드

`.env.example`은 환경변수 이름을 보여 줍니다. Python은 프로세스 환경변수를 읽으므로 실행 셸, IDE 또는 백엔드 환경에 설정을 적용하세요.

| 환경변수 | 용도 |
|---|---|
| `OPENAI_API_KEY` | API 키. 실제 호출 시 필요 |
| `BLOOMY_LLM_MODEL` | 기본값 Anthropic `claude-haiku-5-5` / OpenAI `gpt-4o-mini` (Structured Outputs 지원 모델) |
| `BLOOMY_LLM_BASE_URL` | OpenAI 호환 API의 베이스 URL. 기본값 `https://api.openai.com/v1` |

```text
python -m examples.ai_demo --live
python -m unittest discover -s tests_live -v
```

`--live`는 가상 프로필 두 건의 추천과 가상 메모·코칭을 실제 API로 호출합니다. 하나라도 로컬로 폴백하면 결과와 경고를 출력한 뒤 종료 코드 1을 반환합니다. 서비스 코드의 추천·코치는 API 오류나 응답 검증 실패 시 로컬 결과를 반환합니다. 테스트는 키가 없는 환경에서 실호출 1개를 건너뜁니다.

## 기능

- **추천**은 나이·단계·시간으로 후보를 제한하고 관심사와 목표의 TF-IDF 유사도, 보유 교재, 누적 이력으로 순위를 매깁니다. LLM에 검색 근거를 주고 사용 가능한 ID로 평일 20개 카드의 순서를 구성하도록 합니다. 날짜·학습 방법·시간·부모 확인 포인트는 카탈로그와 Python이 결정합니다. 콘텐츠명·목표·추천 이유는 `day_details`에 기록합니다. 부모 승인 전 상태는 `draft`입니다.
- **코치**는 별도 LLM 호출로 메모 의도를 분류합니다. Python이 휴식일과 C → B → A 규칙을 적용하며, 카탈로그 도구가 다음 카드나 승인 대기 제안을 결정합니다. 메시지 호출은 고정된 분기에서 제공된 안전한 문장 중 문맥에 맞는 표현을 선택합니다. 카드 안내와 근거 인용은 코치가 조합하며 AI 생성 문구를 붙입니다.
- **장기 기억**은 SQLite에 아이·날짜별 학습 반응을 저장합니다. 최근 7일 조회, 선호와 누적 어려움, 학습 시간별 반응, 중복 재시도, 원자적 수정·삭제를 지원합니다. 이력은 후속 추천과 코칭에 반영됩니다. PostgreSQL 연동 지점은 `MemoryRepository`입니다.
- `data/catalog/sample.json`과 `sample-extra.json`은 **미검수 가상 자료**입니다. 시연에서 두 파일을 합쳐 L1~L5 후보를 제공합니다. 실사용은 동일 콘텐츠 ID의 공유 카탈로그와 전문가 검수가 필요합니다.

## 작업 범위

기획서 v0.5와 기존 코드의 차이는 [초기 분석](docs/project-analysis.md)에 정리했습니다. 실제 팀 HTTP 연동, PostgreSQL·pgvector, 별도 전문가 해설·발달 가이드 코퍼스, 전문가 검수, 외부 배포는 이번 로컬 시연 범위 밖입니다.

팀 백엔드 체크아웃이 있으면 `python -m examples.backend_smoke /path/to/team-backend-checkout`으로 기존 계획 등록·승인 API와 AI 코치 입력 변환을 임시 DB에서 확인할 수 있습니다.
