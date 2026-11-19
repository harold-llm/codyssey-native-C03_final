# 🌷 꽃피다 (Bloomy)

> 영어 유치원 대신, 집에서 피는 영어 — **만 3~6세 영어 자율 학습 AI 코칭 웹 서비스**

아이의 하루 학습량과 만족도·흥미·이해도를 부모가 1분 만에 기록하면, AI 코치가 매일
독려·보완·커리큘럼 조정까지 답해줍니다. 영어는 '증서'가 아니라 **영어로 사고하는 사람**을
키우는 여정이라는 철학이 모든 메시지에 스며 있습니다.

## 빠르게 실행

**로컬 개발 (의존성 0, 표준 라이브러리만):**

```bash
python3 backend/main.py
# → http://127.0.0.1:8787  (SQLite 저장)
```

**로컬에서 Vercel과 동일한 구성으로 (FastAPI + Postgres):**

```bash
python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt uvicorn
DATABASE_URL='postgresql://...' ./.venv/bin/python -m uvicorn api.index:app --port 8000
```

스모크 테스트 (엔드포인트 44개 검증):

```bash
python3 scripts/smoke_test.py
```

또는:

```bash
./run.sh          # 서버 시작
./run.sh test     # 스모크 테스트
```

## 구조

```
bloomy/
├── 01-기획서.md               # 서비스 기획서 (미션 산출물)
├── 02-요구-명세서.md          # 요구 명세서 + AI 활용 명세 (미션 산출물)
├── api/index.py               # Vercel Function 진입점 (FastAPI 껍질 → backend.dispatch 위임)
├── index.html / style.css / app.js   # 바닐라 JS SPA (모바일 퍼스트, 루트에서 정적 서빙)
├── backend/
│   ├── main.py                # HTTP 서버 + 라우팅 (dispatch = 소켓 없이 테스트 가능) + /api/cron
│   ├── auth.py                # 이메일 ID + PBKDF2(200k) + HMAC 토큰(30일)
│   ├── store.py               # SQLite 저장소 (DATABASE_URL 있으면 store_pg로 자동 재바인딩)
│   ├── store_pg.py            # Postgres 저장소 (Vercel/Neon 운영용, store와 동일 API)
│   ├── catalog.py             # 큐레이션 콘텐츠(50종) + 4주 계획 생성
│   ├── coach.py               # AI 코치 (LLM 선택 / 룰베이스 폴백, A·B·C 케이스)
│   ├── scheduler.py           # 자동화 (매일 알림·리마인드·주간·월간)
│   └── data/catalog.json      # 나이·발달 단계별 큐레이션 콘텐츠
├── vercel.json                # Vercel Function + 크론(매일 00:00 UTC = 09:00 KST)
├── pyproject.toml             # Python 3.12 + entrypoint(api.index:app)
├── requirements.txt           # fastapi, psycopg[binary]
└── scripts/
    └── smoke_test.py
```

## 핵심 플로우

1. **가입** — 이메일(=ID) + 비밀번호. 실명 인증 없음(시터·가족 공유 목적).
2. **온보딩** — 나이(3~6세)·영어유치원 여부·노출 정도·하루 분량 → 4주(20 학습일) 계획 자동 생성.
3. **매일 루프** — 오늘의 콘텐츠(링크/구입 안내) 제공 → 부모가 아이와 함께 학습 → 4개 칩 + 메모로 기록 → AI 코치 메시지.
   - **A** 계획대로 잘 진행 → 기분 좋은 독려 + 내일 리마인드
   - **B** fully 못 따라옴 → 쉬운 설명 + 내일 소규모 연습 + "하루 하루하면 말문이 트인다" 격려
   - **C** 구체적 피드백/수정 요청 → 분석 + 계획 자동 조정(repeat/swap/advance)
4. **주간 리포트** (일요일) · **월간 구독 갱신** (1일) — 80% 달성 시 다음 달 10만 원(기본 30만 원). '할인'이 아니라 꾸준함의 상.

## 환경 변수

| 변수 | 기본값 | 설명 |
|---|---|---|
| `DATABASE_URL` | — | **설정 시 Postgres 모드(Vercel/Neon), 미설정 시 SQLite 로컬 모드** |
| `BLOOMY_CRON_SECRET` | — | `/api/cron` 인증 secret. Vercel 크론은 `CRON_SECRET` 헤더를 자동 첨부하므로 **Vercel 대시보드의 CRON_SECRET과 같은 값**을 설정 |
| `BLOOMY_PORT` / `--port` | `8787` | 포트 (로컬 표준라이브러리 서버) |
| `BLOOMY_HOST` / `--host` | `127.0.0.1` | 바인딩 주소 |
| `BLOOMY_DB` | `backend/bloomy.db` | SQLite 경로 (로컬 모드) |
| `BLOOMY_PEPPER` | 개발용 기본값 | 비밀번호 해시 pepper (운영 시 반드시 교체) |
| `OPENAI_API_KEY` | — | 설정 시 LLM 코칭 활성화 (없으면 내장 룰베이스 코치) |
| `BLOOMY_LLM_BASE_URL` | `https://api.openai.com/v1` | OpenAI 호환 API |
| `BLOOMY_LLM_MODEL` | `gpt-4o-mini` | LLM 모델 |
| `BLOOMY_DAILY_TIME` | `09:00` | 매일 아침 알림 시각 (로컬 스케줄러) |

LLM 모드/룰베이스 모드 모두 동일한 A·B·C 케이스 규칙과 조정 동작을 따르며,
모든 코칭 메시지에 "AI가 작성한 코칭 메시지입니다." 라벨이 붙습니다.

## 기술 스택

- **두 가지 런타임, 하나의 코어**: 모든 로직은 `backend.dispatch()`에 모여 있어,
  - **로컬/개발**: Python 표준 라이브러리 `http.server` + SQLite (설치 0개)
  - **Vercel 운영**: FastAPI(ASGI) 껍질(`api/index.py`) + **Neon Postgres**(`store_pg.py`)

  이 둘은 동일한 dispatch를 호출해서 동작이 1:1 일치합니다. `DATABASE_URL` 유무로 저장소가 자동 전환됩니다.
- **프론트엔드**: 바닐라 JS SPA(5개 뷰) — 프레임워크 없이 동작, 모바일 퍼스트. 루트의 `index.html` 등 정적 파일도 dispatch가 서빙(로컬·Vercel 동일).

## 배포 — Vercel

1. **Neon Postgres** 생성 (Vercel 대시보드 → Storage → Neon, 무료 티어) → `DATABASE_URL` 복사
2. 이 디렉토리를 git 리포지토리로 만들어 Vercel에 연결 (`vercel` CLI 또는 대시보드 import)
3. **환경 변수** 설정: `DATABASE_URL`, `BLOOMY_PEPPER`(무작위), `BLOOMY_CRON_SECRET`(무작위), 선택 `OPENAI_API_KEY`
4. 배포 완료. Python 3.12(`.python-version`), FastAPI 프리셋이 `api/index.py`(`[tool.vercel] entrypoint`)를 자동 감지

자동화 (Vercel Cron):

- `vercel.json`의 크론이 **매일 00:00 UTC(=09:00 KST)**에 `/api/cron`을 호출
- 무료 플랜은 하루 1회 크론만 지원 → `daily` 잡이 **아침 알림 + 어젯셈 미기록 리마인드 캐치업**을 함께 수행
  (21:00 리마인드·일요일 주간·1일 월간 잡은 로컬 스케줄러 모드에서 그대로 동작. 상위 플랜에서 추가 크론으로 확장 가능)
- 크론 인증: Vercel이 `Authorization: Bearer $CRON_SECRET`을 자동 첨부 → `BLOOMY_CRON_SECRET` 값과 일치하면 처리

로컬에서 Vercel 경로 검증 (이미 수행됨):

```bash
./.venv/bin/python -m uvicorn api.index:app --port 8000   # SQLite + FastAPI 조합
```

## 보안 · 윤리 메모

- 비밀번호: PBKDF2-HMAC-SHA256 200,000회 + 계정별 salt + pepper. 원문 미저장.
- 토큰: HMAC-SHA256 서명, 30일 만료.
- 개인정보 최소화: 아이의 **이름·생일 미수집**(닉네임만).
- AI 가드레일: 발달 진단·의료 표현·효과 보증 금지, 콘텐츠 정보에만 근거, AI 생성 라벨 필수.

## 알려진 한계 (v1)

- Vercel 무료 플랜: 크론 하루 1회(21:00 리마인드는 아침 캐치업으로 대체), 서버리스 콜드 스타트 시 첫 요청이 느릴 수 있음
- 로컬 표준라이브러리 서버의 스케줄러는 프로세스 내 스레드(재시작 시 당일 잡 누락 가능)
- 온보딩 후 추가 아이 등록 UI 없음(API `/api/children` POST는 지원)
- 결제 연동 없음(구독 티어 계산만 제공)
