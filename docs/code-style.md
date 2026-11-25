# 코드 컨벤션 — 꽃피다 (Bloomy)

> 린트 설정: `pyproject.toml`의 `[tool.ruff]` · 타입 검사: `pyrightconfig.json`

## 검사 명령

```bash
ruff check backend api scripts Bloomy-AI   # 린트 (현재 통과)
python3 scripts/smoke_test.py              # 스모크 테스트 154개
cd Bloomy-AI && python -m unittest discover -s tests   # AI 모듈 단위 테스트 84개 (jsonschema 필요)
```

커밋 전에 스모크 테스트가 모두 통과해야 합니다.

## Python

| 항목 | 규칙 |
|---|---|
| 버전 | Python 3.12 이상 (`requires-python = ">=3.12"`) |
| 린트 | ruff `E`·`W`·`F`·`I` (스타일, 오류, import 정렬). 줄 길이는 120 권장 — 긴 한국어 문구·SQL은 예외로 강제하지 않음 |
| 타입 | 함수 인자·반환값에 타입 힌트. pyright로 검사 |
| 의존성 | `backend/`는 표준 라이브러리만 사용(로컬 실행 시 설치 0개). 운영 전용 의존성(FastAPI·psycopg·jsonschema)은 `pyproject.toml`에만 |
| 구조 | 모듈 하나에 책임 하나 (`auth`·`catalog`·`coach`·`branch`·`curriculum`·`songs`·`scheduler`·`store`). 모든 API 요청은 `main.dispatch()` 한 곳을 거침 — 로컬 서버와 Vercel이 같은 코드를 실행 |
| 저장소 | SQL은 `store.py`(SQLite)와 `store_pg.py`(Postgres)에만. 다른 모듈은 함수로 접근 |
| LLM | 호출은 `coach.py`·`Bloomy-AI/ai/llm.py`에만. 출력은 JSON 스키마로 검증하고, 실패하면 규칙 기반으로 폴백 |
| 주석·문서 | 모듈 docstring에 역할을 한국어로. 사용자에게 보이는 문구는 한국어 |
| 이름 | 함수·변수 `snake_case`, 상수 `UPPER_CASE`, 내부용은 `_` 접두사 |

## JavaScript · CSS (`learning/`)

| 항목 | 규칙 |
|---|---|
| 프레임워크 | 없음 (바닐라 JS, 빌드 단계 없음), 파일 상단 `'use strict'` |
| 보안 | 화면에 넣는 모든 사용자·서버 문자열은 `esc()`로 이스케이프 |
| 구조 | 화면마다 `xxxHtml()`(그리기)와 `bindXxx()`(이벤트 연결) 한 쌍, 상태는 `state` 객체 하나 |
| 스타일 | 색은 CSS 변수로, 다크 모드 지원, 모바일 우선(좁은 화면에서 가로 넘침 없음) |

## 데이터 · 문서

- 추천 자료는 `backend/data/catalog.json`·`content_guide.json`이 단일 출처. 바꾸면 `05-RAG-추천-자료.md`가 pre-commit 훅으로 자동 갱신 (`git config core.hooksPath .githooks`)
- 학습 단위(책 제목 등)는 공식 목록에서 확인한 것만 넣음

## 커밋 메시지

`feat:` 기능 · `fix:` 버그 수정 · `docs:` 문서 · `chore:` 설정. 한국어로 무엇을 왜 바꿨는지 한 줄.
