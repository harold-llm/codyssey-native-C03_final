# 04. API 스펙 — 꽃피다 (Bloomy)

> **목적**: F(프론트엔드)·A(AI)·Q(QA)가 백엔드 코드 없이도 의존할 수 있는 **계약 문서**.
> 구현(`backend/`)의 실제 동작을 기준으로 작성했다. 구현이 이 문서와 다르면 **이 문서를 고치거나 버그를 잡는 것 중 하나** — PR에서 명시한다.
>
> - 백엔드: 표준 라이브러리(HTTP) + SQLite(로컬) / PostgreSQL·Neon(프로덕션, `DATABASE_URL` 설정 시 자동 전환)
> - Vercel: `api/index.py`(FastAPI ASGI 래퍼) + 크론. 정적 파일은 루트에서 서빙, SPA 폴백은 `index.html`

---

## 1. 공통 규약

### 1.1 인증

- 모든 인증 API는 `Authorization: Bearer <token>` 헤더.
- 토큰: `POST /api/register`, `POST /api/login` 응답의 `token`(30일 유효, HMAC 서명).
- 비밀번호: PBKDF2-SHA256(200,000회) + 소금.

### 1.2 응답 형태

- 성공: `Content-Type: application/json; charset=utf-8`, 아래 정의된 JSON.
- 실패: `{"error": "<한국어 메시지>"}` — 상태코드만 의미 있고 본문은 표시용.

| 상태 | 의미 |
|------|------|
| 200/201 | 성공 (201은 리소스 생성) |
| 400 | 요청 본문/쿼리 검증 실패 |
| 401 | 로그인 필요 / 토큰·크론 시크릿 잘못 |
| 404 | 존재하지 않거나 **타인 계정 자원** (정보 노출 방지 위해 404로 통합) |
| 405 | 허용되지 않은 메서드 (현재는 GET/POST만 존재) |
| 409 | 상태 충돌 (중복 가입·중복 기록·재승인) |
| 500 | 서버 오류 |

### 1.3 공통 객체

**child** (공개 필드)

```json
{
  "id": 1, "user_id": 1, "name": "수지", "age": 5, "birth_year": 2021,
  "ek_kindergarten": 0, "exposure": "some", "materials": "", "favorite_topics": "",
  "session_length": 10, "diagnosis": {"score": 3, "level": 2, "answers": {...}, "note": "..."},
  "level": 2, "created_at": "2026-11-17T00:00:00"
}
```
> `diagnosis`는 저장 시 JSON 문자열 → 노출 시 객체로 파싱된다.

**plan**

```json
{"id": 1, "child_id": 1, "week_start": "2026-11-17", "status": "draft",
 "source": "onboarding_rule", "base_level": 2, "explanation": "왜 이 순서인지...",
 "created_at": "..."}
```
- `status`: `draft` → `approved` / `superseded` / `done`
- `source`: `onboarding_rule`(규칙 기반) | `rag_onboarding`(A의 RAG 업로드)

**card**

```json
{"id": 1, "plan_id": 1, "child_id": 1, "date": "2026-11-17",
 "content_id": "supersimple-001", "task": "'...'을(를) 아이와 함께 읽기",
 "minutes": 10, "check_point": "그림을 가리키며 뜻에 맞게 반응하나요?", "status": "pending"}
```
- `content_id`는 `catalog` 항목의 `id`. 규칙 생성기의 대체 불가일 때 `null`(타스만 안내 카드).

**coach message** (i.e. `/messages` 항목)

```json
{"id": 1, "child_id": 1, "feedback_id": 5, "date": "2026-11-18", "branch": "B",
 "memo_intent": "none", "body": "…\nAI가 작성한 코칭 메시지입니다.",
 "model": "gpt-4o-mini", "prompt_version": "bloomy-coach-v2-llm", "is_ai_generated": 1}
```
- `branch`: `A|B|C` (휴식일 SKIP은 메시지로 저장되지 않는다)
- `prompt_version`: `bloomy-coach-v2-rules`(룰베이스) | `bloomy-coach-v2-llm`(LLM)
- 메시지 말미에는 **`AI가 작성한 코칭 메시지입니다.`** 라벨이 항상 붙는다 (6.6).

---

## 2. 엔드포인트

### 2.1 헬스·진단 정의

| | |
|---|---|
| `GET /api/health` | `200 {"ok": true, "service": "bloomy", "time": "..."}` — 무인증 |
| `GET /api/diagnosis/questions` | 온보딩 5문항 정의 (F UI용) — 무인증 |

`GET /api/diagnosis/questions` 응답:

```json
{"questions": [
  {"key": "alphabet", "label": "알파벳(a, b, c) 인지",
   "options": {"none": "인지 못 함", "some": "일부 인지", "many": "대부분 인지"}},
  {"key": "phonics",  "label": "파닉스(글자-소리) 노출", "options": {...}},
  {"key": "readers",  "label": "레벨드 리더스 경험", "options": {...}},
  {"key": "response", "label": "영어 질문에 아이 반응", "options": {...}},
  {"key": "focus",    "label": "책·영상 집중 길이", "options": {...}}
]}
```
> key 순서 고정: `alphabet → phonics → readers → response → focus`. 옵션 값은 항상 `none|some|many`.

### 2.2 계정

#### `POST /api/register` — 무인증

```json
{"email": "p@test.com", "password": "secret123"}
```
- 검증: 이메일 형식, 비밀번호 ≥6자 → 아니면 `400`. 중복 이메일 → `409`.
- `201` `{"token": "...", "account": {"id": 1, "email": "..."}, "children": []}`

#### `POST /api/login` — 무인증

```json
{"email": "p@test.com", "password": "secret123"}
```
- 실패 시 `401`(이메일/비밀번호 구분 없이 동일한 메시지).
- `200` `{"token": "...", "account": {...}, "children": [child, ...]}`

#### `GET /api/me`

- `200` `{"account": {"id", "email"}, "children": [child, ...]}` / `401`

### 2.3 온보딩 (프로필 + 5문항 → 계획 초안)

#### `POST /api/children`

```json
{
  "name": "수지", "age": 5, "birth_year": 2021,
  "ek_kindergarten": false,
  "exposure": "some",
  "materials": "핑크퐁, 슈퍼심플",
  "favorite_topics": "공주, 동물",
  "session_length": 10,
  "diagnosis": {"alphabet": "some", "phonics": "none", "readers": "none",
                "response": "some", "focus": "some"}
}
```

| 필드 | 제약 |
|------|------|
| `name` | 20자 이내 (공백 허용) |
| `age` | **만 4~7** (int) — 3세/8세면 `400` |
| `birth_year` | optional int |
| `ek_kindergarten` | bool |
| `exposure` | `none` \| `some` \| `much` |
| `session_length` | `10` \| `15` \| `20` (default 10) |
| `diagnosis` | 5문항 전부 `none/some/many` — 하나라도 빠지면 `400` |
| `materials`, `favorite_topics` | optional, 200자 이내 |

- `201` 응답 — **4개 필드**:
```json
{"child": child,
 "diagnosis": {"score": 2, "level": 2, "answers": {...},
               "note": "5문항 기반 초기 가설입니다. 2주간의 실제 반응 데이터로 보정돼요."},
 "plan": plan,
 "cards": [card × 20]}
```
- 진단 가설 규칙: 각 문항 none/some/many = 0/1/2점, 합 0~10 → `level = 1 + score//2` (0-1→L1, 2-3→L2, 4-5→L3, 6-7→L4, 8-10→L5), `exposure=much`면 +1 (L5 상한). **가설**이다 — "확정" 문구 금지.
- 계획은 **`draft`** 상태로 생성된다 (20평일 카드). **부모 승인 전에는 카드가 도착하지 않는다** (승인 게이트, 6.1).
- welcome 알림 1건 생성.

#### `POST /api/children/{id}/plans` — **A의 RAG 추천 계획 업로드용** (6.2)

```json
{
  "days": [
    {"date": "2026-11-18", "content_id": "phonics-song-001",
     "task": "(선택) 커스텀 작업 문장", "minutes": 10, "check_point": "(선택)"}
  ],
  "explanation": "4주 계획의 학습 방법 설명 (콘텐츠명 인용)",
  "base_level": 2
}
```
- `days[].content_id`는 **카탈로그에 있는 항목만** 허용 → 아니면 `400` ("6.6 근거 없는 추천 금지").
- `task`/`check_point` 누락 시 카탈로그 템플릿 자동 생성. `minutes` 최소 5분.
- 기존 `draft` 계획은 `superseded` 처리 (동시 draft 1개).
- `201` `{"plan": plan, "cards": [card, ...]}` — 이후 기존 `approve` 플로우로 활성화.

#### `POST /api/children/{id}/plans/{plan_id}/approve`

- `draft`만 승인 가능. `200` `{"plan": plan(status=approved), "cards": [card, ...]}`
- 재승인/비-draft 승인 → `409`. 승인 시 계획 알림 1건.
- 승인된 계획이 있으면 `get_card_for_child`/`next_card_for_child`는 **approved plan 카드만** 참조.

#### `POST /api/children/{id}/replan`

- 기존 `approved`는 `done` → 새 규칙 기반 `draft` 생성.
- `200` `{"plan": plan, "cards": [card × 20]}`

#### `GET /api/children/{id}/plan`

- `200` `{"plan": plan(approved 또는 최신), "cards": [...]}` / 없음 `404`

### 2.4 데일리 루프

#### `GET /api/children/{id}/today`

- `200`:
```json
{"date": "2026-11-17",
 "plan": plan(approved) | null,
 "draft_plan": plan(draft) | null,
 "card": card(오늘) | null,
 "record": feedback(오늘) | null,
 "message": coach_message(최근 1건) | null}
```
- 승인 전: `plan=null`, `draft_plan`=초안 (F는 승인 게이트 화면으로 유도).

#### `POST /api/children/{id}/feedback` — **핵심** (1분 피드백 → 3단계 코치)

```json
{
  "date": "2026-11-17",          // default 오늘. 미래 날짜 → 400
  "completion": "full",           // full | partial | none  (잘 따라옴/일부/못 함)
  "satisfaction": 4,              // 1~5
  "interest": 3,                  // 1~5
  "comprehension": 5,             // 1~5
  "memo": "이건 너무 어려운 것 같아요",  // optional, 500자
  "rest_day": false               // true면 나머지 필드 무시
}
```
- 검증: `completion` 열거, 만족도·흥미·이해도 1~5 → 위반 `400`.
- 같은 날짜에 이미 기록이 있으면 `409`.
- `rest_day=true` → 분기 **SKIP**: 메시지 미생성, 성취 분모 제외. 응답 `message: null`.
- `201` 응답:
```json
{"record": {"id": 1, "date": "...", "content_id": "..." | null,
            "completion": "full", "satisfaction": 4, "interest": 3,
            "comprehension": 5, "memo": "...", "rest_day": false,
            "memo_intent": "change_request"},
 "case": "C",
 "memo_intent": "change_request",
 "message": "…\nAI가 작성한 코칭 메시지입니다.",
 "adjust": {"type": "propose_swap", "reason": "큰 변경 — 부모 확인 후에만 반영 (6.1 승인 게이트)",
            "dates": [], "proposal": "슈퍼심플 레벨1: My Day"},
 "tomorrow": {"date": "2026-11-18", "content_id": "...", "title": "...",
              "task": "...", "minutes": 10, "check_point": "..."} | null}
```
- `adjust` 구조: `{type, reason, dates[], proposal?}` — type은 아래 4절.
- `tomorrow`는 **조정이 적용된 후**의 카드 (shrink/swap 반영).

#### `GET /api/children/{id}/messages`

- `200` `coach_message[]` — 날짜 **내림차순**(최근 1건이 첫 요소).

### 2.5 리포트·대시보드

#### `GET /api/children/{id}/report?week_start=YYYY-MM-DD`

- `week_start` 미지정 시 **지난 주(월~일)**. 형식 잘못 `400`.
- `200`:
```json
{"week_start": "2026-11-09", "week_end": "2026-11-15", "record_days": 4,
 "avg_interest": 3.5, "avg_comprehension": 4.0,
 "prev_avg_interest": 3.8, "prev_avg_comprehension": 3.5,
 "trend": ["흥미 3.8→3.5", "이해도 3.5→4.0"],
 "learned": ["Super Simple Songs: My Day"],
 "branch_counts": {"A": 2, "B": 1, "C": 1, "SKIP": 0},
 "choices": ["현재 흐름 유지 (추이가 안정적이라면 추천)", "..."],
 "next_cards": [{"date": "...", "task": "...", "minutes": 10}],
 "confidence_sentence": "데이터로 보면, 이번 주도 옳은 길로 가고 있어요." | "",
 "honest_note": "..." | null,
 "one_step": "이번 주의 한 걸음: ...",
 "summary": "이번 주 학습 4일. 추이: ..."}
```
- `confidence_sentence`는 **데이터 조건부**(confidence_ok, 아래 5절) — 어떤 주에도 무조건 삽입되지 않는다. 하락·미해결 주에는 `honest_note`로 솔직히 안내 (6.6).
- `learned` 기준: `completion=full`이고 `comprehension≥4`인 기록의 콘텐츠 (최대 3개).

#### `GET /api/children/{id}/achievement?month=YYYY-MM`

- `month` 미지정 시 **지난 달**. 형식 잘못 `400`.
- `200` (요금·청구 필드는 **없다**):
```json
{"month": "2026-10", "record_days": 15, "max_streak": 5,
 "avg_interest": 3.7, "avg_comprehension": 4.1,
 "learned": ["..."],
 "note": "학습 성취 리포트입니다 — 요금·청구와 무관합니다."}
```

#### `GET /api/children/{id}/stats`

- 현재 달 기준 대시보드:
```json
{"month": "2026-11", "record_days": 10, "planned_days": 15, "record_rate": 0.67,
 "streak": 3, "avg_interest": 3.8, "avg_comprehension": 4.2,
 "recent": [{"date": "...", "completion": "full", "interest": 4, "comprehension": 5}]}
```
- `recent`는 최근 14개 기록을 **오래된 순**.

### 2.6 설정·카탈로그·알림

#### `POST /api/children/{id}/settings`

```json
{"name": "수지", "session_length": 15}   // 둘 다 optional
```
- `name` 20자, `session_length` 10/15/20. `200` → 갱신된 `child`.

#### `GET /api/catalog?age=&level=&skill=&type=&keyword=` — 무인증

- 파라미터 전부 optional. 응답: `item[]` (카탈로그 항목, 7절 스키마).

#### `GET /api/notifications`

- `200` `{"items": [notification, ...](최신순), "unread": 2}`
- notification: `{id, user_id, title, body, kind, read_at, created_at}` — `kind`: `welcome|plan|card|remind|report|info`

#### `POST /api/notifications/read`

- 전체 읽음 처리. `200` `{"ok": true}`

#### `POST /api/learning/recommendation` — 인증 필요

아이용 미니러닝(`learning/`)의 서버 추천. 프론트가 보낸 `words`/`phrases`의 **부분집합만** 골라 반환한다(카탈로그 밖 추천 금지). 룰베이스(결정적)로 동작하며 LLM 불요.

```json
{
  "profile": {"age": 5, "experience": "가끔 해봤어요", "interests": ["동물"], "studyTime": 10},
  "diagnosis": {"q1": "..."},
  "stats": {"recentAttemptCount": 3, "recentAccuracy": 0.5, "weakWords": ["Cat"], "words": [], "completionRate": 0.5},
  "words": [{"word": "Star"}, {"word": "Cat"}],
  "phrases": [{"english": "Hello, Star!"}]
}
```
- `words`/`phrases`가 비면 `400`. 미인증 `401`.
- `200`:
```json
{
  "provider": "server_ai",
  "words": [{"word": "Cat"}, {"word": "Star"}],
  "phrases": [{"english": "Hello, Star!"}],
  "difficulty": "차근차근",
  "estimatedMinutes": 10,
  "historyCount": 3,
  "reason": "동물 관심사와 지금 난이도(차근차근)에 맞춰 골랐어요.",
  "summary": "오늘은 차근차근 단계로 단어 2개와 표현 1개를 연습해요.",
  "strengths": ["꾸준히 시도하고 있어요"],
  "supportNeeds": ["Cat 단어를 한 번 더 연습해요"],
  "nextLearning": "다음에는 'Hello, Star!' 표현을 소리 내어 말해봐요."
}
```
- `difficulty ∈ {기초, 차근차근, 도전}` — 영어 경험 + 최근 정답률로 결정. 약점 단어(`weakWords`)를 우선 배치.
- `estimatedMinutes`는 `5 ≤ x ≤ studyTime` 범위.

### 2.7 크론 (Vercel)

#### `POST /api/cron`

- 헤더: `Authorization: Bearer <BLOOMY_CRON_SECRET>` — 미설정/불일치 `401`.
- 본문:
```json
{"job": "daily", "date": "2026-11-17"}   // date optional (daily/remind)
```
- `job`: `daily` | `remind` | `weekly` | `monthly`. 미지정 `400`.
- `200` `{"ok": true, "job": "daily"}`
- **무료 티어는 크론 1회/일이므로** `daily` 잡이 단일 진입점(`scheduler.run_daily`)에서 순서 처리:
  1. 모든 승인 아이에 오늘 카드 알림(card)
  2. 어젯날 기록이 없으면 21:00 리마인더(1회만, meta dedup)
  3. 일요일이면 주간 리포트 알림
  4. 매월 1일이면 월간 성취 알림
- 중복 실행 안전: meta 테이블에 `daily:{child}:{date}` 같은 키로 dedup.

### 2.8 그 외 경로

- `/api/` 접두 GET이 아니라면 정적 파일 서빙. 존재하지 않는 경로 → **SPA 폴백** `index.html` (200).

---

## 3. 분기 판정 규칙 엔진 (5.4) — `branch.decide`

**순 규칙(코드가 소비)** — LLM 불참. 입력: 완료도·흥미·이해도 숫자 + 메모 의도 **라벨**(6.3 분류기 출력).

### 3.1 판정 조건 (우선순위 **C → B → A**, A는 디폴트)

| 케이스 | 조건 | 의미 |
|--------|------|------|
| **SKIP** | `rest_day=true` | 분기 건너뜀 — 메시지 미생성, 성취 분모 제외 |
| **C** | `memo_intent ∈ {question, change_request}` **또는** 흥미≤2 **캘린더 전일 인접** 2일 연속 | 소재·형식 교체 또는 부모 질문/요청 |
| **B** | (C 미해당 전제) `completion ∈ {partial, none}` 또는 `comprehension < 3` | 부분 미달 — 분량 축소 |
| **A** | 그 외 (디폴트) | 순조 |

- "2일 연속"은 `(오늘 - 전일 기록 날짜).days == 1` **캘린더 인접**만 성립한다.
- **공백 해소**: "잘 따라옴 + 이해도 4 + 흥미 2(단 하루)" → C의 2연속 불만족 → **A**로 수렴. 단발 흥미 저하는 `interest_dip` 플래그로 memory에 기록하고 다음 날 재평가 (단발 과반응 방지).
- **중복 해소**: B+C 동시 성립 → **C 우선** + `difficulty_adjust` 플래그로 조정 안에 난이도 조정(B)을 포함.

### 3.2 결정 객체

```json
{"case": "C", "intent": "change_request",
 "flags": {"difficulty_adjust": false, "expert_referral": false, "interest_dip": false},
 "low_interest_streak": 0,
 "reasons": ["메모 의도 change_request → 수정·질문·형식 변경"]}
```

| 플래그 | 의미 |
|--------|------|
| `difficulty_adjust` | C+B 중복 → 조정 안에 난이도 조정 포함 |
| `expert_referral` | `out_of_scope` → 전문가 상담 전환 (6.6 가드레일) |
| `interest_dip` | 단발 흥미 저하 → memory 기록 |

### 3.3 메모 의도 라벨 (6.3 — 별도 스키마-제약 LLM 호출)

| 라벨 | 의미 | 분기 영향 |
|------|------|----------|
| `none` | 질문·변경 의도 없음 | 없음 |
| `question` | 학습 관련 질문 | C |
| `change_request` | 콘텐츠/형식 변경 요청 | C (제안만, 자동 적용 X) |
| `out_of_scope` | 학습 범위 밖(발달·질병·장애 등) | C + `expert_referral` (전문가 상담 전환) |

- 분류는 LLM 스키마 호출(`{intent, reason}`, 버전 `bloomy-intent-v2`) → 실패 시 키워드 폴백(`out_of_scope` → `change_request` → `question` 순 검사).
- **분기를 바꾸는 판단은 이 라벨까지** — 메시지 생성 LLM은 분기(케이스)를 받지 않는다 (5.4/6.3 설계 정직함).

---

## 4. 자동 조정 (다음 카드 반영)

| 조정 type | 발생 | 동작 |
|-----------|------|------|
| `none` | A / SKIP / C(out_of_scope) / C(question, B 미중복) | 카드 불변 |
| `shrink` | B, 또는 C+difficulty_adjust | 내일 카드 분량 **5분 축소(최소 5분)** — 같은 콘텐츠로 부담 낮춤 |
| `swap` | C(흥미≤2 2연속) | **같은 레벨 다른 유형** 소재로 자동 교체 |
| `swap_easy` | C(흥미 2연속) + difficulty_adjust | **한 레벨 아래** 다른 소재로 자동 교체 |
| `propose_swap` | C(change_request) | **자동 적용 없음** — `proposal`에 후보 제목만 제시, 부모 확인 후에만 반영 (6.1 승인 게이트) |

응답 `adjust`: `{"type", "reason", "dates": [...], "proposal"?: str|null}`

---

## 5. 코치 3단계 (6.3) · 확신 문구 (6.6)

1. **메모 의도 분류** (위 3.3 — 스키마 제약 호출)
2. **분기 판정** (위 3절 — 순 규칙, LLM 불참)
3. **메시지 생성**
   - LLM 사용 시 스키마 `{case, body, tomorrow_card, confidence_sentence?}` — **`case`는 규칙 판정 결과가 무조건 우선** (LLM이 case를 바꿀 수 없음).
   - LLM 없거나 스키마 실패 → **룰베이스** 결정적 메시지 (동등 동작, `prompt_version=bloomy-coach-v2-rules`).
   - `confidence_sentence`는 아래 confidence_ok가 True일 때만 수용, 아니면 **폐기**.
   - 모든 메시지 말미에 AI 라벨: `AI가 작성한 코칭 메시지입니다.`

**confidence_ok** (확신 문구 데이터 조건 — 전부 충족):

1. 최근 7일 흥미·이해도 평균이 이전 7일 대비 현저히 하락하지 않음 (또는 ≥3)
2. 미해결 C 없음 (C 이후 `full`+이해도≥3 기록 존재)
3. 연속 B(캘린더 인접) 없음

> "이번 주도 옳은 길로 가고 있다" 같은 확신 문구는 **고정 삽입 금지** — 조건 불만족 주에는 `honest_note`로 조정 사실을 솔직히 안내 (6.6 가드레일·보장 금지).

---

## 6. Long-term Memory (6.4)

- 피드백 저장 시 `write_memory`가 최근 14 기록에서 연속 지표(연속 학습일, 이해도 저하 연속일, 흥미 저하 연속일, 순항 연속일)를 `memory_facts`에 갱신.
- 의도: 다음날 3단계에서 "어제의 흐름" 근거로 사용. 숫자·라벨만 저장 (부모 메모 원문 저장 없음).

---

## 7. 카탈로그 (7.1) — 스키마·분담

### 7.1 canonical 항목 스키마 (필드 10종)

`catalog/*.json` (seed 파일 — 로드 시 DB `contents` 테이블로 멱등 업서트):

```json
[{
  "id": "supersimple-001",          // 고유 id (카드 content_id로 참조됨)
  "title": "Super Simple Songs: My Day",
  "age_min": 4, "age_max": 7,
  "level": 3,                        // 1~5 (L1~L5, "L3" 문자열도 허용)
  "skill": "listening",              // listening | speaking | reading | writing
  "type": "video",                   // readers_series | phonics | worksheet | video | audio | activity
  "provider": "link",                // purchase(교재·부모 구입) | link(영상·오디오 공식 링크)
  "link": "https://...",
  "session_minutes": 10,             // 10 | 15 | 20
  "expert_note": "이유 한 줄 (전문가 검수)",
  "trust_source": "출처 신뢰 근거"
}]
```
- **레거시 포맷** (`stage`/`minutes`/`why`/`tip`/`paid` + 한국어 type: 교재·노래·앱·웹·유튜브·활동·읽기·그림책·워크시트)은 자동 매핑된다.
- 레벨: L1 노출·듣기 → L2 소리 인지 → L3 파닉스 → L4 사이트워드·초기 해독 → L5 리더스 독해.
- **게이트 G3 기준**: 총 60개, **나이별(4/5/6/7) 15개 이상**.
- `stats` 게이트(`gate_ok`): 총 45개+ AND 나이별 15+ 미만이면 카탈로그 품질 미달로 플래그 (D4 점검용).

### 7.2 4인 분담 규칙 (03-작업-계획서 §1·D1~D4)

- **A(코디)**: 구조 설계(D1 오후 확정 게이트) + 20개 + 전문가 검수 조율·기록
- **F**: 20개 항목 작성 (프론트엔드 작업 병행)
- **Q**: 20개 항목 작성 (테스터 모집 병행) + 필드 8종 완비 품질 점검
- **B**: seed 스크립트/검증 툴, D3 seed 실행·검증
- 항목 작성 순서는 **4세 → 5세 → 6세 → 7세**로 균등 분배 (나이별 15+ 보장).
- 항목 `id`는 파일 간·인간 사이 중복 금지 — `kebab-case`로 `{시리즈/유형}-{번호}` 추천.

### 7.3 규칙 기반 계획 생성기 (B 기본 구현 — A RAG가 대체)

- 평일 20일(4주) 계획, 시작일 요일에 무관하게 **캘린더 요일 기반** 패턴:
  - 월/화/목: 주(base) 레벨, **수: L1 워밍업**, **금: 주 레벨+1**(한 단계 위 살짝 도전)
  - 학습일 11일째(3주차 블록)부터 주 레벨 +1 (L5 상한)
- `explanation`: "왜 이 순서인지" 학습 방법 설명 (소리→글자-소리→읽기→말하기, 가정(hypothesis) 명시).

---

## 8. 환경변수

| 변수 | 필수 | 기본 | 설명 |
|------|------|------|------|
| `DATABASE_URL` | 프로덕션 | —(없으면 SQLite) | Neon Postgres. 설정 시 `store_pg` 자동 전환 |
| `BLOOMY_PEPPER` | 권장 | `bloomy-default-pepper` | 비밀번호 해시 페퍼 — **프로덕션에서 반드시 설정** |
| `OPENAI_API_KEY` | 선택 | — | 없으면 룰베이스 코치로 동작(결정적) |
| `BLOOMY_LLM_BASE_URL` | 선택 | `https://api.openai.com/v1` | LLM 엔드포인트 (호환 API 가능) |
| `BLOOMY_LLM_MODEL` | 선택 | `gpt-4o-mini` | LLM 모델 |
| `BLOOMY_CRON_SECRET` | 프로덕션 | —(없으면 크론 401) | `POST /api/cron` Bearer 시크릿 |
| `BLOOMY_DAILY_TIME` | 선택 | `09:00` | 로컬 프로세스 스케줄러 카드 발송 시각 |
| `BLOOMY_DB` | 선택 | `backend/bloomy.db` | SQLite 경로 (로컬/테스트) |
| `BLOOMY_PORT` / `BLOOMY_HOST` | 선택 | `8787` / `127.0.0.1` | 로컬 서버 |

---

## 9. 실행·검증

### 9.1 로컬 실행

```bash
python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt
./.venv/bin/python backend/main.py --port 8787
# → http://127.0.0.1:8787
```

### 9.2 smoke test (F·Q 회귀 기준 — 78케이스)

```bash
./.venv/bin/python scripts/smoke_test.py
# → "78 passed, 0 failed"
```
- 새 SQLite(`.smoke_test.db`)로 격리, LLM 키 제거(룰베이스 확정)로 **결정적**.
- 커버리지: auth·온보딩(draft→승인 게이트)·RAG 계획 업로드(400 검증)·분기 E2E(A 단발/C 2연속 swap/C+B 중복 propose_swap 자동적용X/B shrink/휴식일 SKIP)·메시지 이력·조정 반영·카탈로그·알림·타계정 404·스케줄러 dedup·크론 인증.
- **변경 전후 반드시 실행** — 게이트 G3/G4 회귀 확인에 사용.

### 9.3 Vercel

- `api/index.py`가 FastAPI(ASGI)로 `dispatch()`를 위임 (Postgres datetime 정규화 포함).
- `vercel.json`의 crons: daily 잡 `0 0 * * *`(UTC) → `POST /api/cron {"job":"daily"}`.
- DB 마이그레이션: 첫 요청 시 `store.init()`이 `CREATE TABLE IF NOT EXISTS`로 자동 스키마 (수기 마이그레이션 없음 — 컬럼 추가 시 스키마 정의를 갱신해야 **기존 DB에도** 반영되는 점 주의).

---

## 10. F·A·Q 체크리스트

**F (프론트엔드)**
- [ ] 토큰 저장 후 모든 요청에 `Authorization: Bearer`
- [ ] 401 → 로그인 화면, 404 → "존재하지 않음" (타계정 자원 포함)
- [ ] 온보딩: 5문항은 `/api/diagnosis/questions`에서 동적 렌더 (hardcode 금지)
- [ ] 승인 게이트: `plan.status=draft`면 승인 버튼, 승인 전 카드 미노출
- [ ] 피드백 화면: `completion` 3단계 + 3개 1~5점 + 메모 + 휴식일 토글
- [ ] 메시지: `AI가 작성한 코칭 메시지입니다.` 라벨 포함 표시 (6.6)
- [ ] `confidence_sentence`는 빈 문자열일 수 있음 — 빈 값이면 렌더하지 말 것

**A (AI)**
- [ ] RAG 계획 업로드는 `POST /api/children/{id}/plans` — `content_id`는 카탈로그에만 있는 id
- [ ] 카탈로그 항목은 7.1 스키마 + `catalog/*.json` seed (id 중복 금지)
- [ ] 코치 프롬프트: 규칙 case를 바꾸지 못하도록 스키마/검증 (5.4)
- [ ] 확신 문구는 confidence_ok 조건부 — 고정 삽입 금지 (6.6)

**Q (QA)**
- [ ] `scripts/smoke_test.py` 78케이스 = 최소 회귀 기준
- [ ] E2E 시나리오: 가입 → 온보딩(5문항) → draft 확인 → 승인 → 오늘 카드 → 피드백(4가지 case 각 1회) → 내일 카드 확인 → 주간 리포트
- [ ] 409 케이스: 중복 가입, 같은 날짜 중복 기록, 재승인
- [ ] 404 케이스: 타계정 child_id로 today/feedback (정보 누수 확인)
- [ ] 휴식일: 메시지 없음 + `rest_day` 기록 확인
