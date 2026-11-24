"""Bloomy 스모크 테스트 — 01-기획서 v0.5 / 04-API-스펙 기준.

HTTP 소켓 대신 main.dispatch()를 직접 호출해 전 엔드포인트 +
분기 규칙 엔진(5.4: C>B>A, 공백/중복 해소) + 3단계 코치(6.3) +
자동화(6.5)를 검증한다.

실행: ./.venv/bin/python scripts/smoke_test.py
전부 통과하면 exit 0, 하나라도 실패하면 exit 1.

결정성: OPENAI_API_KEY 제거 → 내장 룰베이스 코치 + 키워드 의도 분류기.
"""

import datetime as dt
import json
import os
import sys
import urllib.parse
from typing import cast

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND = os.path.join(ROOT, "backend")
sys.path.insert(0, BACKEND)

TEST_DB = os.path.join(BACKEND, ".smoke_test.db")
os.environ["BLOOMY_DB"] = TEST_DB
_ = os.environ.pop("OPENAI_API_KEY", None)  # 룰베이스 코치로 확정
_ = os.environ.pop("BLOOMY_CRON_SECRET", None)
if os.path.exists(TEST_DB):
    os.remove(TEST_DB)

import auth
import catalog
import clock
import curriculum
import scheduler
import songs

import main as bloomy_main
import store

pass_count = 0
fail_count = 0
AI_LABEL = "AI가 작성한 코칭 메시지입니다."
DIAG_KEYS = ("alphabet", "phonics", "readers", "response", "focus")


CONSENT = {"agree_privacy": True, "agree_guardian": True}


def check(name: str, cond: bool, extra: str = "") -> None:
    global pass_count, fail_count
    if cond:
        pass_count += 1
        print(f"PASS  {name}")
    else:
        fail_count += 1
        print(f"FAIL  {name}  {extra}")


def req(
    method: str, path: str, token: str | None = None, body: object = None
) -> tuple[int, object]:
    """(status, parsed_json_or_text) 반환 — dispatch 직접 호출."""
    headers: dict[str, str] = {}
    if token:
        headers["Authorization"] = "Bearer " + token
    code, payload, ctype = bloomy_main.dispatch(method, path, headers, body)
    if ctype == bloomy_main.JSON:
        if isinstance(payload, (dict, list)):
            return code, cast("dict[str, object] | list[object]", payload)
        if isinstance(payload, (str, bytes)):
            return code, cast(
                "dict[str, object] | list[object] | str", json.loads(payload)
            )
        return code, str(payload)
    return (
        code,
        payload.decode("utf-8", "replace")
        if isinstance(payload, bytes)
        else str(payload),
    )


def iso(d: dt.date) -> str:
    return d.isoformat()


def _item_level(item_id: object) -> int | None:
    item = catalog.find_item(item_id)
    return item["level"] if item is not None else None


def _alt(it: catalog.Item, age: int) -> catalog.Item | None:
    pool: list[catalog.Item] = [
        x
        for x in (
            catalog.items_by_level(it["level"], age)
            or catalog.items_by_level(it["level"])
        )
        if x["id"] != it["id"]
    ]
    return pool[0] if pool else None


def fb(
    token1: str | None, child2: int, date: dt.date, **kw: object
) -> tuple[int, dict[str, object]]:
    body: dict[str, object] = {"date": iso(date)}
    body.update(kw)
    st, payload = req(
        "POST", f"/api/children/{child2}/feedback", token=token1, body=body
    )
    return st, cast("dict[str, object]", payload)


def section_auth(suffix: str) -> str | None:
    # 1. health / 정적 페이지
    st, d = req("GET", "/api/health")
    d = cast("dict[str, object]", d)
    check("health", st == 200 and d.get("ok") is True, str(d))
    llm = cast("dict[str, object]", d.get("llm") or {})
    check(
        "health llm 진단 (키 미노출)",
        llm.get("mode") == "rule_based" and llm.get("key_configured") is False
        and "sk-" not in json.dumps(d),
        str(llm),
    )
    st, d = req("GET", "/")
    d = cast("str", d)
    check("frontend /", st == 200 and "꽃피다" in d, f"status={st}")
    st, d = req("GET", "/learning/")
    d = cast("str", d)
    check("frontend /learning/", st == 200 and "themeToggle" in d, f"status={st}")
    st, d = req("GET", "/learning/css/style.css")
    d = cast("str", d)
    check("frontend /learning/css", st == 200 and "--accent" in d, f"status={st}")
    st, d = req("GET", "/learning/js/app.js")
    d = cast("str", d)
    check("frontend /learning/js", st == 200 and "Bloomy" in d, f"status={st}")

    # 2. 회원가입 / 로그인 (개인정보 동의 필수)
    email1 = f"parent{suffix}@test.bloomy"
    st, d = req("GET", "/api/privacy")
    d = cast("dict[str, object]", d)
    check("privacy notice", st == 200 and "agree_guardian" in cast("dict[str, object]", d["required"]), str(d)[:160])
    st, d = req("POST", "/api/register", body={"email": email1, "password": "secret123"})
    check("register without consent -> 400", st == 400, str(d)[:160])
    st, d = req("POST", "/api/register",
                body={"email": email1, "password": "secret123", "agree_privacy": True})
    check("register without guardian consent -> 400",
          st == 400 and cast("dict[str, object]", d)["missing"] == ["agree_guardian"], str(d)[:160])
    st, d = req(
        "POST", "/api/register", body={"email": email1, "password": "secret123", **CONSENT}
    )
    d = cast("dict[str, object]", d)
    check("register", st == 201 and "token" in d, str(d)[:200])
    consent_rec = cast("dict[str, object]", cast("dict[str, object]", d.get("account") or {}).get("consent") or {})
    check("register records consent version+time",
          bool(consent_rec.get("version")) and bool(consent_rec.get("consented_at")), str(consent_rec))
    token1 = cast("str | None", d.get("token"))
    st, d = req(
        "POST", "/api/register", body={"email": email1, "password": "secret123", **CONSENT}
    )
    check("register duplicate -> 409", st == 409, str(d))
    st, d = req("POST", "/api/login", body={"email": email1, "password": "wrongpw!"})
    check("login wrong pw -> 401", st == 401, str(d))
    st, d = req("POST", "/api/login", body={"email": email1, "password": "secret123", **CONSENT})
    d = cast("dict[str, object]", d)
    check("login", st == 200 and "token" in d, str(d)[:200])
    token1 = cast("str | None", d.get("token", token1))
    st, d = req("GET", "/api/me", token=token1)
    d = cast("dict[str, object]", d)
    account = cast("dict[str, object]", d["account"])
    check("me", st == 200 and account["email"] == email1, str(d)[:200])
    st, d = req("GET", "/api/me")
    check("me without token -> 401", st == 401)

    # 3. 진단 5문항 정의 (F 온보딩 UI용)
    st, d = req("GET", "/api/diagnosis/questions")
    d = cast("dict[str, object]", d)
    questions = cast("list[dict[str, object]]", d.get("questions", []))
    keys = [q["key"] for q in questions]
    check("diagnosis questions 5", st == 200 and keys == list(DIAG_KEYS), str(keys))
    return token1


def section_child1(token1: str | None, today: dt.date) -> int:
    # 4. 온보딩 (5.1) — child1: 4세, 5문항 모두 none → L1 가설, draft 계획
    diag_none: dict[str, str] = {k: "none" for k in DIAG_KEYS}
    st, d = req(
        "POST",
        "/api/children",
        token=token1,
        body={
            "name": "우리별",
            "age": 4,
            "ek_kindergarten": 1,
            "exposure": "none",
            "session_length": 10,
            "diagnosis": diag_none,
        },
    )
    d = cast("dict[str, object]", d)
    child = cast("dict[str, object]", d["child"])
    check("onboarding create child", st == 201 and child["age"] == 4, str(d)[:200])
    child1 = cast("int", child["id"])
    diagnosis = cast("dict[str, object]", d["diagnosis"])
    check(
        "diagnosis L1 (가설)",
        diagnosis["score"] == 0 and diagnosis["level"] == 1,
        str(diagnosis),
    )
    plan = cast("dict[str, object]", d["plan"])
    plan1_id = cast("int", plan["id"])
    cards = cast("list[dict[str, object]]", d["cards"])
    check(
        "plan draft 20 cards",
        plan["status"] == "draft" and len(cards) == 20,
        f"{plan['status']} n={len(cards)}",
    )
    c0 = cards[0]
    check(
        "plan starts today+ (weekdays only)",
        str(c0["date"]) >= iso(today)
        and dt.date.fromisoformat(str(c0["date"])).weekday() < 5,
        str(c0["date"]),
    )
    wed: list[dict[str, object]] = [
        c
        for c in cards
        if dt.date.fromisoformat(str(c["date"])).weekday() == 2 and c["content_id"]
    ]
    check(
        "wednesday L1 warm-up",
        len(wed) >= 1 and all(_item_level(c["content_id"]) == 1 for c in wed),
        f"wed={len(wed)}",
    )

    # 온보딩 입력 검증
    st, d = req(
        "POST",
        "/api/children",
        token=token1,
        body={"name": "x", "age": 3, "diagnosis": diag_none},
    )
    check("child age 3 -> 400", st == 400, str(d))
    st, d = req("POST", "/api/children", token=token1, body={"name": "x", "age": 5})
    check("child missing diagnosis -> 400", st == 400, str(d))
    st, d = req(
        "POST",
        "/api/children",
        token=token1,
        body={"name": "x", "age": 5, "session_length": 7, "diagnosis": diag_none},
    )
    check("child bad session_length -> 400", st == 400, str(d))

    # 승인 전 today: draft만 노출
    st, d = req("GET", f"/api/children/{child1}/today", token=token1)
    d = cast("dict[str, object]", d)
    draft_plan = cast("dict[str, object]", d["draft_plan"])
    song = cast("dict[str, object]", d.get("song") or {})
    check("today에 오늘의 동요(YouTube 링크)", str(song.get("url", "")).startswith("https://www.youtube.com/watch?v="),
          str(song.get("id")))
    check(
        "today before approve: draft only",
        st == 200
        and d["plan"] is None
        and d["draft_plan"] is not None
        and draft_plan["id"] == plan1_id,
        str(d)[:160],
    )

    # 승인 게이트 (6.1)
    st, d = req(
        "POST",
        f"/api/children/{child1}/plans/{plan1_id}/approve",
        token=token1,
        body={},
    )
    d = cast("dict[str, object]", d)
    plan = cast("dict[str, object]", d["plan"])
    cards = cast("list[dict[str, object]]", d["cards"])
    check(
        "approve plan",
        st == 200 and plan["status"] == "approved" and len(cards) == 20,
        str(d)[:160],
    )
    st, d = req(
        "POST",
        f"/api/children/{child1}/plans/{plan1_id}/approve",
        token=token1,
        body={},
    )
    check("approve twice -> 409", st == 409, str(d))

    # 설정 변경 / 재계획
    st, d = req(
        "POST",
        f"/api/children/{child1}/settings",
        token=token1,
        body={"name": "별별", "session_length": 15},
    )
    d = cast("dict[str, object]", d)
    check(
        "settings",
        st == 200 and d["name"] == "별별" and d["session_length"] == 15,
        str(d)[:160],
    )
    st, d = req("POST", f"/api/children/{child1}/replan", token=token1, body={})
    d = cast("dict[str, object]", d)
    plan = cast("dict[str, object]", d["plan"])
    cards = cast("list[dict[str, object]]", d["cards"])
    check(
        "replan draft 20",
        st == 200 and plan["status"] == "draft" and len(cards) == 20,
        str(d)[:160],
    )
    return child1


def section_child2(
    token1: str | None,
    m: dt.date,
    d0: dt.date,
    d1: dt.date,
    d2: dt.date,
    d3: dt.date,
    d4: dt.date,
) -> tuple[int, catalog.Item, dict[str, dict[str, object]]]:
    # 5. child2 — A의 RAG 계획 업로드(6.2) + 피드백 E2E (5.3, 5.4, 6.3)
    diag_some: dict[str, str] = {k: "some" for k in DIAG_KEYS}
    st, d = req(
        "POST",
        "/api/children",
        token=token1,
        body={
            "name": "별이",
            "age": 5,
            "ek_kindergarten": 0,
            "exposure": "some",
            "session_length": 10,
            "diagnosis": diag_some,
        },
    )
    d = cast("dict[str, object]", d)
    child = cast("dict[str, object]", d["child"])
    child2 = cast("int", child["id"])
    diagnosis = cast("dict[str, object]", d["diagnosis"])
    check("child2 level L3 (score 5)", diagnosis["level"] == 3, str(diagnosis))

    cand: list[catalog.Item] = catalog.search(age=5) or catalog.search()
    item0 = next((i for i in cand if _alt(i, 5)), cand[0])

    # RAG 계획: 과거 20평일 (content_id는 카탈로그 내 항목만 허용, 6.6)
    days: list[dict[str, str]] = [
        {"date": x.isoformat(), "content_id": item0["id"]}
        for x in catalog.next_weekdays(m, 20)
    ]
    st, d = req(
        "POST",
        f"/api/children/{child2}/plans",
        token=token1,
        body={"days": days, "explanation": "smoke", "base_level": 1},
    )
    d = cast("dict[str, object]", d)
    plan = cast("dict[str, object]", d["plan"])
    cards = cast("list[dict[str, object]]", d["cards"])
    check(
        "rag plan create",
        st == 201 and plan["status"] == "draft" and len(cards) == 20,
        str(d)[:160],
    )
    plan2_id = cast("int", plan["id"])
    st, d = req(
        "POST",
        f"/api/children/{child2}/plans",
        token=token1,
        body={"days": [{"date": iso(m), "content_id": "nope"}]},
    )
    check("rag plan unknown content -> 400 (6.6)", st == 400, str(d))
    st, d = req(
        "POST", f"/api/children/{child2}/plans", token=token1, body={"days": "x"}
    )
    check("rag plan bad days -> 400", st == 400, str(d))
    st, d = req(
        "POST",
        f"/api/children/{child2}/plans/{plan2_id}/approve",
        token=token1,
        body={},
    )
    d = cast("dict[str, object]", d)
    plan = cast("dict[str, object]", d["plan"])
    check(
        "approve child2 plan", st == 200 and plan["status"] == "approved", str(d)[:160]
    )
    st, pd = req("GET", f"/api/children/{child2}/plan", token=token1)
    pd = cast("dict[str, object]", pd)
    cards = cast("list[dict[str, object]]", pd["cards"])
    orig: dict[str, dict[str, object]] = {str(c["date"]): c for c in cards}

    # d0(월): 잘 따라옴+흥미2(단발) → A + interest_dip (공백 해소, 5.4)
    st, d = fb(
        token1,
        child2,
        d0,
        completion="full",
        satisfaction=4,
        interest=2,
        comprehension=4,
    )
    check(
        "d0 case A (단발 흥미 저하 — C 아님)",
        st == 201 and d["case"] == "A",
        str(d)[:200],
    )
    adjust = cast("dict[str, object]", d.get("adjust", {}))
    check("d0 no adjust", adjust.get("type") == "none", str(d.get("adjust")))
    check(
        "d0 AI label",
        AI_LABEL in str(d.get("message") or ""),
        str(d.get("message", ""))[:120],
    )
    check(
        "d0 확신 문구 없음 (데이터 조건부, 6.6)",
        "옳은 길" not in str(d.get("message") or ""),
        "",
    )
    check(
        "d0 tomorrow = d1",
        d.get("tomorrow") is not None
        and cast("dict[str, object]", d["tomorrow"])["date"] == iso(d1),
        str(d.get("tomorrow")),
    )
    record = cast("dict[str, object]", d["record"])
    check(
        "d0 intent none",
        d["memo_intent"] == "none" and record["memo_intent"] == "none",
        str(d)[:160],
    )
    review = cast("dict[str, object] | None", d.get("ai_review"))
    check(
        "d0 ai_review (코치 Agent 연결: RAG 근거 포함)",
        review is not None and review["case"] == d["case"]
        and len(cast("list[object]", review["evidence"])) >= 1,
        str(review)[:200],
    )

    # d1(화): 흥미2 2일 연속 → C → 내일 카드 swap
    st, d = fb(
        token1,
        child2,
        d1,
        completion="full",
        satisfaction=3,
        interest=2,
        comprehension=4,
    )
    check("d1 case C (흥미≤2 2일 연속)", st == 201 and d["case"] == "C", str(d)[:200])
    adjust = cast("dict[str, object]", d["adjust"])
    check(
        "d1 swap adjust",
        adjust["type"] in ("swap", "swap_easy") and adjust["dates"] == [iso(d2)],
        str(adjust),
    )
    check(
        "d1 tomorrow swapped",
        d["tomorrow"] is not None
        and cast("dict[str, object]", d["tomorrow"])["content_id"] != item0["id"],
        str(d.get("tomorrow")),
    )

    # d2(수): 일부완료 + 변경요청 메모 → C + B 중복, 제안만 (자동 적용 X, 6.1)
    st, d = fb(
        token1,
        child2,
        d2,
        completion="partial",
        satisfaction=3,
        interest=3,
        comprehension=4,
        memo="너무 어려워서요. 쉬운 걸로 바꿔주세요",
    )
    check(
        "d2 memo intent change_request",
        d["memo_intent"] == "change_request",
        str(d)[:200],
    )
    check("d2 case C (C 우선, B 중복)", st == 201 and d["case"] == "C", str(d)[:200])
    adjust = cast("dict[str, object]", d["adjust"])
    check(
        "d2 propose only (자동 적용 X)",
        adjust["type"] == "propose_swap" and adjust["dates"] == [],
        str(adjust),
    )
    today_item = catalog.find_item(cast("dict[str, object]", d["record"])["content_id"])
    check(
        "d2 proposal != 오늘 자료 (같은 자료 재제안 금지)",
        adjust.get("proposal") is None or today_item is None
        or adjust["proposal"] != today_item["title"],
        f"proposal={adjust.get('proposal')} today={today_item and today_item['title']}",
    )
    review = cast("dict[str, object] | None", d.get("ai_review"))
    check(
        "d2 ai_review 변경 요청 → 자료 안내·근거 (Agent)",
        review is not None and review["case"] == "C"
        and bool(review["advice"]) and len(cast("list[object]", review["evidence"])) >= 1,
        str(review)[:300],
    )

    # d3(목): 이해도 2 → B → 내일 분량 축소
    st, d = fb(
        token1,
        child2,
        d3,
        completion="full",
        satisfaction=3,
        interest=4,
        comprehension=2,
    )
    check("d3 case B (이해도<3)", st == 201 and d["case"] == "B", str(d)[:200])
    adjust = cast("dict[str, object]", d["adjust"])
    check(
        "d3 shrink adjust",
        adjust["type"] == "shrink" and adjust["dates"] == [iso(d4)],
        str(adjust),
    )
    check(
        "d3 tomorrow shrunk",
        cast("int", cast("dict[str, object]", d["tomorrow"])["minutes"])
        == max(5, cast("int", orig[iso(d4)]["minutes"]) - 5),
        str(d.get("tomorrow")),
    )

    # d4(금): 휴식일 → SKIP (메시지 없음, 성취 분모 제외, 5.4)
    st, d = fb(token1, child2, d4, rest_day=True)
    check(
        "d4 rest day SKIP",
        st == 201 and d["case"] == "SKIP" and d["message"] is None,
        str(d)[:200],
    )
    record = cast("dict[str, object]", d["record"])
    check("d4 record rest_day", record["rest_day"] is True, str(record))

    # 피드백 검증
    st, d = fb(
        token1,
        child2,
        d0,
        completion="full",
        satisfaction=4,
        interest=4,
        comprehension=4,
    )
    check("duplicate record -> 409", st == 409, str(d))
    st, d = req(
        "POST",
        f"/api/children/{child2}/feedback",
        token=token1,
        body={
            "date": "2999-01-01",
            "completion": "full",
            "satisfaction": 4,
            "interest": 4,
            "comprehension": 4,
        },
    )
    check("future date -> 400", st == 400, str(d))
    st, d = fb(
        token1,
        child2,
        d0 - dt.timedelta(days=1),
        completion="weird",
        satisfaction=4,
        interest=4,
        comprehension=4,
    )
    check("bad completion -> 400", st == 400, str(d))
    return child2, item0, orig


def section_reports(
    token1: str | None,
    child2: int,
    d0: dt.date,
    d2: dt.date,
    d3: dt.date,
    d4: dt.date,
    item0: catalog.Item,
    orig: dict[str, dict[str, object]],
) -> None:
    # 메시지 이력 (SKIP는 메시지 없음)
    st, d = req("GET", f"/api/children/{child2}/messages", token=token1)
    msgs = cast("list[dict[str, object]]", d)
    check("messages 4 (SKIP excluded)", st == 200 and len(msgs) == 4, f"n={len(msgs)}")
    check(
        "message branch order B,C,C,A",
        [x["branch"] for x in msgs] == ["B", "C", "C", "A"],
        str([x["branch"] for x in msgs]),
    )
    check(
        "message AI label + rules version",
        AI_LABEL in str(msgs[0]["body"])
        and msgs[0]["prompt_version"] == "bloomy-coach-v2-rules",
        str(msgs[0])[:160],
    )

    # 조정 반영 확인 (카드 변경)
    st, pd = req("GET", f"/api/children/{child2}/plan", token=token1)
    pd = cast("dict[str, object]", pd)
    cards = cast("list[dict[str, object]]", pd["cards"])
    cards2: dict[str, dict[str, object]] = {str(c["date"]): c for c in cards}
    check(
        "d2 card swapped (적용됨)",
        cards2[iso(d2)]["content_id"] != item0["id"],
        str(cards2[iso(d2)])[:160],
    )
    check(
        "d3 card unchanged (제안만)",
        cards2[iso(d3)]["content_id"] == item0["id"],
        str(cards2[iso(d3)])[:160],
    )
    check(
        "d4 card shrunk",
        cast("int", cards2[iso(d4)]["minutes"])
        == max(5, cast("int", orig[iso(d4)]["minutes"]) - 5),
        str(cards2[iso(d4)])[:160],
    )

    # 주간 리포트 (5.5) — 확신 문구는 데이터 조건부
    st, d = req(
        "GET", f"/api/children/{child2}/report?week_start={iso(d0)}", token=token1
    )
    d = cast("dict[str, object]", d)
    check(
        "weekly report",
        st == 200
        and d["record_days"] == 4
        and d["branch_counts"] == {"A": 1, "B": 1, "C": 2, "SKIP": 0},
        str({k: d.get(k) for k in ("record_days", "branch_counts")}),
    )
    check(
        "weekly 확신 문구 없음 + honest_note",
        d.get("confidence_sentence") == "" and bool(d.get("honest_note")),
        str(d.get("honest_note")),
    )
    check("weekly one_step", bool(d.get("one_step")), str(d)[:160])

    # 월간 성취 (요금 무관) / 대시보드
    st, d = req(
        "GET",
        f"/api/children/{child2}/achievement?month={d0.strftime('%Y-%m')}",
        token=token1,
    )
    d = cast("dict[str, object]", d)
    check(
        "monthly achievement (요금 없음)",
        st == 200 and "next_fee" not in d and "요금" in str(d["note"]),
        str(d)[:160],
    )
    st, d = req("GET", f"/api/children/{child2}/stats", token=token1)
    d = cast("dict[str, object]", d)
    check(
        "stats dashboard",
        st == 200 and "record_rate" in d and "streak" in d,
        str(d)[:160],
    )

    # 6. 카탈로그 검색
    st, d = req("GET", "/api/catalog?level=1")
    items = cast("list[dict[str, object]]", d)
    check(
        "catalog level=1",
        st == 200
        and isinstance(d, list)
        and len(items) > 0
        and all(i["level"] == 1 for i in items),
        f"n={len(items)}",
    )
    st, d = req("GET", "/api/catalog?age=4&level=1")
    items = cast("list[dict[str, object]]", d)
    check(
        "catalog age+level",
        st == 200
        and isinstance(d, list)
        and all(
            cast("int", i["age_min"]) <= 4 <= cast("int", i["age_max"]) for i in items
        ),
        f"n={len(items)}",
    )
    st, d = req("GET", "/api/catalog?keyword=" + urllib.parse.quote(item0["title"][:4]))
    check("catalog keyword", st == 200 and isinstance(d, list), "")

    # 7. 알림 (환영·계획) + 읽음 처리
    st, d = req("GET", "/api/notifications", token=token1)
    d = cast("dict[str, object]", d)
    items = cast("list[dict[str, object]]", d["items"])
    kinds = {n["kind"] for n in items}
    check(
        "notifications welcome+plan",
        st == 200 and "welcome" in kinds and "plan" in kinds,
        str(kinds),
    )
    st, _ = req("POST", "/api/notifications/read", token=token1, body={})
    st, d = req("GET", "/api/notifications", token=token1)
    d = cast("dict[str, object]", d)
    check("notifications read", d["unread"] == 0, str(d["unread"]))


def section_other_accounts(
    token1: str | None,
    child1: int,
    child2: int,
    d5: dt.date,
    suffix: str,
) -> None:
    # 8. 타 계정 접근 차단
    email2 = f"parent2{suffix}@test.bloomy"
    st, d = req(
        "POST", "/api/register", body={"email": email2, "password": "secret123", **CONSENT}
    )
    d = cast("dict[str, object]", d)
    token2 = cast("str | None", d.get("token"))
    st, d = req("GET", f"/api/children/{child1}/today", token=token2)
    check("other account today -> 404", st == 404, str(d))
    st, d = req("GET", "/api/children/99999/today", token=token1)
    check("unknown child -> 404", st == 404, str(d))
    st, d = req(
        "POST",
        f"/api/children/{child2}/feedback",
        token=token2,
        body={
            "date": iso(d5),
            "completion": "full",
            "satisfaction": 4,
            "interest": 4,
            "comprehension": 4,
        },
    )
    check("other account feedback -> 404", st == 404, str(d))


def section_scheduler_cron(token1: str | None, m: dt.date, d5: dt.date) -> None:
    # 9. 자동화 (6.5) — 스케줄러 직접 호출
    scheduler.daily(date=iso(d5))
    scheduler.remind(date=iso(d5))
    st, d = req("GET", "/api/notifications", token=token1)
    d = cast("dict[str, object]", d)
    items = cast("list[dict[str, object]]", d["items"])
    n_daily = sum(1 for n in items if n["kind"] == "daily")
    n_remind = sum(1 for n in items if n["kind"] == "remind")
    check("scheduler daily card sent", n_daily >= 1, f"n={n_daily}")
    check("scheduler remind sent", n_remind >= 1, f"n={n_remind}")
    scheduler.remind(date=iso(d5))  # 1회만 (meta 중복 방지)
    st, d2 = req("GET", "/api/notifications", token=token1)
    d2 = cast("dict[str, object]", d2)
    items2 = cast("list[dict[str, object]]", d2["items"])
    check(
        "remind once only (dedup)",
        sum(1 for n in items2 if n["kind"] == "remind") == n_remind,
        "",
    )
    scheduler.weekly(date=iso(m + dt.timedelta(days=6)))  # 일요일
    st, d3 = req("GET", "/api/notifications", token=token1)
    d3 = cast("dict[str, object]", d3)
    items3 = cast("list[dict[str, object]]", d3["items"])
    check(
        "weekly report notification",
        any(n["kind"] == "report" for n in items3),
        str([n["kind"] for n in items3]),
    )

    # 10. Vercel Cron 엔드포인트
    st, d = req("POST", "/api/cron", body={"job": "daily"})
    check("cron without secret -> 401", st == 401, str(d))
    os.environ["BLOOMY_CRON_SECRET"] = "smoke-sec"
    st, d = req("POST", "/api/cron", token="smoke-sec", body={"job": "daily"})
    d = cast("dict[str, object]", d)
    check("cron daily -> 200", st == 200 and bool(d.get("ok")), str(d))
    st, d = req("POST", "/api/cron", token="wrong", body={"job": "daily"})
    check("cron wrong secret -> 401", st == 401, str(d))
    st, d = req("POST", "/api/cron", token="smoke-sec", body={"job": "bogus"})
    check("cron unknown job -> 400", st == 400, str(d))
    st, d = req(
        "POST",
        "/api/cron",
        token="smoke-sec",
        body={"job": "weekly", "date": iso(m + dt.timedelta(days=6))},
    )
    check("cron weekly -> 200", st == 200, str(d))
    st, d = req(
        "POST",
        "/api/cron",
        token="smoke-sec",
        body={"job": "monthly", "date": "2026-11-01"},
    )
    check("cron monthly -> 200", st == 200, str(d))
    _ = os.environ.pop("BLOOMY_CRON_SECRET", None)


def section_learning(token: str | None) -> None:
    payload = {
        "profile": {
            "age": 5, "experience": "가끔 해봤어요",
            "interests": ["동물"], "studyTime": 10,
        },
        "diagnosis": {},
        "stats": {
            "recentAttemptCount": 3, "recentAccuracy": 0.5,
            "weakWords": ["Cat"], "words": [], "completionRate": 0.5,
        },
        "words": [
            {"word": "Star"}, {"word": "Cat"},
            {"word": "Dog"}, {"word": "Rabbit"},
        ],
        "phrases": [
            {"english": "Hello, Star!"}, {"english": "I love cats!"},
        ],
    }
    st, d = req("POST", "/api/learning/recommendation", token=token, body=payload)
    d = cast("dict[str, object]", d)
    check("learning recommendation -> 200", st == 200, str(d))
    check("learning provider server_ai", d.get("provider") == "server_ai", str(d))
    words = cast("list[dict[str, object]]", d.get("words") or [])
    phrases = cast("list[dict[str, object]]", d.get("phrases") or [])
    allowed_words = {"Star", "Cat", "Dog", "Rabbit"}
    allowed_phrases = {"Hello, Star!", "I love cats!"}
    check(
        "learning words subset",
        bool(words) and all(w.get("word") in allowed_words for w in words),
        str(words),
    )
    check(
        "learning weak word first",
        bool(words) and words[0].get("word") == "Cat",
        str(words),
    )
    check(
        "learning phrases subset",
        bool(phrases) and all(p.get("english") in allowed_phrases for p in phrases),
        str(phrases),
    )
    check(
        "learning difficulty valid",
        d.get("difficulty") in ("기초", "차근차근", "도전"),
        str(d.get("difficulty")),
    )
    mins = d.get("estimatedMinutes")
    check(
        "learning minutes in range",
        isinstance(mins, int) and 5 <= mins <= 10,
        str(mins),
    )
    check(
        "learning historyCount int",
        isinstance(d.get("historyCount"), int),
        str(d.get("historyCount")),
    )

    st, d = req("POST", "/api/learning/recommendation", body=payload)
    check("learning without auth -> 401", st == 401, str(d))

    bad = dict(payload)
    bad["words"] = []
    st, d = req("POST", "/api/learning/recommendation", token=token, body=bad)
    check("learning empty words -> 400", st == 400, str(d))


def section_delete_account(token1: str | None, child_ids: tuple[int, int]) -> None:
    """동의 철회(탈퇴) → 계정·아이 데이터 전부 삭제."""
    st, d = req("POST", "/api/me/delete", token=token1, body={"password": "wrongpw!"})
    check("delete account wrong pw -> 403", st == 403, str(d))
    st, d = req("POST", "/api/me/delete", body={"password": "secret123"})
    check("delete account no auth -> 401", st == 401, str(d))
    st, d = req("POST", "/api/me/delete", token=token1, body={"password": "secret123"})
    check("delete account -> 200", st == 200 and cast("dict[str, object]", d)["deleted"] is True, str(d))
    st, d = req("GET", "/api/me", token=token1)
    check("deleted account token -> 401", st == 401, str(d))
    left = 0
    for cid in child_ids:
        for table in ("children", "feedbacks", "coach_messages", "memory_facts", "cards", "plans"):
            col = "id" if table == "children" else "child_id"
            left += len(store.query(f"SELECT 1 FROM {table} WHERE {col}=?", (cid,)))
    check("deleted account leaves no child data", left == 0, f"rows left={left}")

    # 기존 가입자(동의 기록 없음) → 로그인 후 동의
    salt = auth.new_salt()
    _ = store.create_user("legacy@test.bloomy", auth.hash_password("secret123", salt), salt)
    st, d = req("POST", "/api/login", body={"email": "legacy@test.bloomy", "password": "secret123"})
    d = cast("dict[str, object]", d)
    legacy_token = cast("str | None", d.get("token"))
    legacy_consent = cast("dict[str, object]", cast("dict[str, object]", d["account"])["consent"])
    check("legacy account has no consent", legacy_consent["version"] is None, str(legacy_consent))
    st, d = req("POST", "/api/me/consent", token=legacy_token, body={"agree_privacy": True})
    check("legacy consent partial -> 400", st == 400, str(d)[:160])
    st, d = req("POST", "/api/me/consent", token=legacy_token, body=CONSENT)
    acc = cast("dict[str, object]", cast("dict[str, object]", d)["account"])
    check("legacy consent recorded",
          st == 200 and bool(cast("dict[str, object]", acc["consent"])["version"]), str(d)[:200])


def section_curriculum() -> None:
    """학습 단위 커리큘럼 + 카탈로그 안내 문서 (docs/catalog.md)."""
    print("\n[curriculum] 학습 단위·카탈로그 문서")
    guide_items = cast("dict[str, object]", curriculum.guide()["items"])
    missing = [it["id"] for it in catalog.search() if it["id"] not in guide_items]
    check("모든 카탈로그 항목에 안내(content_guide) 있음", not missing, str(missing))
    t0 = curriculum.unit_text("ort-stage2", 0)
    t1 = curriculum.unit_text("ort-stage2", 1)
    t2 = curriculum.unit_text("ort-stage2", 2)
    check("ORT Stage 2: 1권 첫 읽기", bool(t0 and "『The Big Egg』" in t0[0] and "첫 읽기" in t0[0]), str(t0))
    check("ORT Stage 2: 1권 다시 읽기", bool(t1 and "『The Big Egg』" in t1[0] and "다시 읽기" in t1[0]), str(t1))
    check("ORT Stage 2: 2권으로 진도", bool(t2 and "『Poor Floppy』" in t2[0]), str(t2))
    check("단위 없는 자료는 그대로(None)", curriculum.unit_text("epic-full", 0) is None)
    cards = [{"content_id": "ort-full", "task": "x", "check_point": "y"} for _ in range(3)]
    curriculum.apply(cast("list[dict[str, object]]", cards), {"ort-full": 4})
    check("이전 진도(4회)에 이어 3권부터", "『Put It Back』" in str(cards[0]["task"]), str(cards[0]["task"]))
    shared = [{"content_id": c, "task": "", "check_point": ""} for c in ("songbirds-1", "songbirds-full")]
    curriculum.apply(cast("list[dict[str, object]]", shared))
    check("같은 책을 공유하는 항목끼리 중복 배정 안 함", shared[0]["task"] != shared[1]["task"],
          str([c["task"][:25] for c in shared]))
    draft = catalog.generate_plan({"age": 4, "level": 3, "materials": "ort", "session_length": 30},
                                  clock.today())
    curriculum.apply(cast("list[dict[str, object]]", draft["cards"]))
    ort = [c for c in draft["cards"] if str(c["content_id"]).startswith("ort-")]
    check("ORT 보유 아이 계획에 권 제목 카드", bool(ort) and all("『" in c["task"] for c in ort),
          str([c["task"][:30] for c in ort[:2]]))
    # 피드백 반영: 목표 통일·카드 안내·묶음 축소·날짜 선택
    bad = [it["id"] for it in catalog.search()
           if catalog.card_text(it)[1] != curriculum.goal_text(it["title"], it["skill"], it["type"])[1]]
    check("활동·확인 포인트가 주 목표(skill) 하나로 통일", not bad, str(bad[:5]))
    info = curriculum.card_info(cast("dict[str, object]", catalog.find_item("ort-stage2")), owned=True)
    check("카드 안내: 비용·찾는 법·부모 역할·보유 이유",
          bool(info and info["cost"] and info["find"] and info["help"] and "집에 있다고" in str(info["why"])), str(info))
    check("Peppa Pig 에피소드 단위", "『Muddy Puddles』" in str(curriculum.unit_text("peppa", 0)))
    loose = curriculum.collection_ids()
    draft2 = catalog.generate_plan({"age": 4, "level": 3, "materials": "", "session_length": 15}, clock.today())
    used_loose = [c["content_id"] for c in draft2["cards"] if c["content_id"] in loose]
    check("규칙 계획: 구체적 후보가 있으면 묶음 항목 제외", not used_loose, str(used_loose[:5]))
    fut = (clock.today() + dt.timedelta(days=1)).isoformat()
    check("today?date=미래 → 400", bloomy_main.ep_today({"id": 0}, {"date": [fut]})[0] == 400)
    check("today?date=형식오류 → 400", bloomy_main.ep_today({"id": 0}, {"date": ["2026/1/1"]})[0] == 400)
    # 보호자 피드백: 알파벳을 모르는 아이는 알파벳 자료부터, 그날 글자 표시
    import json as _json
    nochild = {"id": 0, "age": 4, "level": 1, "materials": "", "session_length": 10,
               "diagnosis": _json.dumps({"answers": {"alphabet": "none"}})}
    d3 = catalog.generate_plan(nochild, clock.today())
    changed = curriculum.alphabet_first(nochild, cast("list[dict[str, object]]", d3["cards"]),
                                        catalog.find_item, catalog.card_text)
    curriculum.apply(cast("list[dict[str, object]]", d3["cards"]))
    first5 = [c["content_id"] for c in d3["cards"][:5]]
    check("알파벳 '인지 못 함' → 첫 주 알파벳 자료",
          changed and all(c in curriculum.ALPHABET_ROTATION for c in first5), str(first5))
    jolly = next((c for c in d3["cards"] if str(c["content_id"]).startswith("jolly-")), None)
    lets = curriculum.letters_for(nochild, jolly)
    check("Jolly 카드에 오늘의 소리 글자(s·a·t)", [x["letter"] for x in lets] == ["s", "a", "t"], str(lets))
    check("알파벳 아는 아이는 계획 그대로",
          not curriculum.alphabet_first({**nochild, "diagnosis": "{}"}, [{"content_id": "x"}],
                                        catalog.find_item, catalog.card_text))
    import subprocess
    r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "gen_catalog_doc.py"), "--check"],
                       capture_output=True, text=True)
    check("docs/catalog.md 최신 (gen_catalog_doc.py --check)", r.returncode == 0, r.stdout.strip())


def section_songs() -> None:
    """오늘의 동요 — 단계별 공식 채널 YouTube 링크 1곡."""
    print("\n[songs] 오늘의 동요")
    import re
    allsongs = songs.all_songs()
    official = {"Super Simple Songs", "Super Simple ABCs", "Jack Hartmann", "Have Fun Teaching",
                "Alphablocks", "Pinkfong"}
    bad = [s["id"] for s in allsongs
           if not re.fullmatch(r"https://www\.youtube\.com/watch\?v=[\w-]{11}", str(s["url"]))
           or s["channel"] not in official or not s.get("do")]
    check("동요 링크 형식·공식 채널·부모 안내 완비", not bad, str(bad))
    check("동요 L1~L5 단계마다 5곡 이상",
          all(sum(1 for s in allsongs if s["level"] == lv) >= 5 for lv in range(1, 6)))
    check("동요 id 중복 없음", len({s["id"] for s in allsongs}) == len(allsongs))
    kid = {"id": 5, "level": 3}
    days = [(dt.date(2026, 12, 1) + dt.timedelta(days=i)).isoformat() for i in range(6)]
    picks = [songs.song_for(kid, d) for d in days]
    check("같은 날 같은 곡(결정적)", songs.song_for(kid, days[0]) == picks[0])
    check("연속한 날은 다른 곡", all(picks[i]["id"] != picks[i + 1]["id"] for i in range(5)),
          str([p["id"] for p in picks]))
    lv = [p["level"] for p in picks]
    check("단계 맞춤(L3) + 사흘에 한 번 L2 복습", set(lv) <= {2, 3} and lv.count(3) >= 3, str(lv))
    abc = {"id": 5, "level": 4, "diagnosis": json.dumps({"answers": {"alphabet": "none"}})}
    check("알파벳 '인지 못 함' 아이는 알파벳·글자 소리 노래(L1~L2)",
          all(songs.song_for(abc, d)["level"] in (1, 2) for d in days))
    plan_level = songs.song_for({"id": 5, "level": 1}, days[1], {"base_level": 5})
    check("계획 단계(base_level)를 아이 기본값보다 우선", plan_level["level"] in (4, 5), str(plan_level["level"]))


def main() -> int:
    store.init()
    _ = catalog.load()
    today = clock.today()  # 서버와 같은 한국 시간 기준
    suffix = dt.datetime.now().strftime("%H%M%S")

    # 과거 계획 앵커: 최근 월요일(<= 오늘-3). d0..d4 = 월~금 모두 과거,
    # d5 = 그 다음 주 월요일(계획 내, 피드백 없음) — 요일에 무관하게 결정적.
    base = today - dt.timedelta(days=3)
    m = base - dt.timedelta(days=base.weekday())
    d0, d1, d2, d3, d4 = (m + dt.timedelta(days=i) for i in range(5))
    d5 = d4 + dt.timedelta(days=3)  # 금 → 다음 월

    token1 = section_auth(suffix)
    child1 = section_child1(token1, today)
    child2, item0, orig = section_child2(token1, m, d0, d1, d2, d3, d4)
    section_reports(token1, child2, d0, d2, d3, d4, item0, orig)
    section_other_accounts(token1, child1, child2, d5, suffix)
    section_scheduler_cron(token1, m, d5)
    section_learning(token1)
    section_delete_account(token1, (child1, child2))
    section_curriculum()
    section_songs()

    try:
        os.remove(TEST_DB)
    except OSError:
        pass
    print(f"\n{pass_count} passed, {fail_count} failed")
    return 1 if fail_count else 0


if __name__ == "__main__":
    sys.exit(main())
