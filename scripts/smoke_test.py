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

import catalog
import scheduler

import main as bloomy_main
import store

pass_count = 0
fail_count = 0
AI_LABEL = "AI가 작성한 코칭 메시지입니다."
DIAG_KEYS = ("alphabet", "phonics", "readers", "response", "focus")


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
    st, d = req("GET", "/")
    d = cast("str", d)
    check("frontend /", st == 200 and "꽃피다" in d, f"status={st}")
    st, d = req("GET", "/style.css")
    d = cast("str", d)
    check("frontend /style.css", st == 200 and "--teal" in d, f"status={st}")
    st, d = req("GET", "/app.js")
    d = cast("str", d)
    check("frontend /app.js", st == 200 and "Bloomy" in d, f"status={st}")

    # 2. 회원가입 / 로그인
    email1 = f"parent{suffix}@test.bloomy"
    st, d = req(
        "POST", "/api/register", body={"email": email1, "password": "secret123"}
    )
    d = cast("dict[str, object]", d)
    check("register", st == 201 and "token" in d, str(d)[:200])
    token1 = cast("str | None", d.get("token"))
    st, d = req(
        "POST", "/api/register", body={"email": email1, "password": "secret123"}
    )
    check("register duplicate -> 409", st == 409, str(d))
    st, d = req("POST", "/api/login", body={"email": email1, "password": "wrongpw!"})
    check("login wrong pw -> 401", st == 401, str(d))
    st, d = req("POST", "/api/login", body={"email": email1, "password": "secret123"})
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
        "POST", "/api/register", body={"email": email2, "password": "secret123"}
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


def main() -> int:
    store.init()
    _ = catalog.load()
    today = dt.date.today()
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

    try:
        os.remove(TEST_DB)
    except OSError:
        pass
    print(f"\n{pass_count} passed, {fail_count} failed")
    return 1 if fail_count else 0


if __name__ == "__main__":
    sys.exit(main())
