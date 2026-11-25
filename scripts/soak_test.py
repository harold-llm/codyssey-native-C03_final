"""반복 실행 안정성 테스트 — 같은 프로세스에서 데일리 루프를 수천 번 돌려 오류·응답 시간·메모리를 기록한다.

실행:
  python3 scripts/soak_test.py              # 기본: 가정 200개 × 하루 루프 10회
  python3 scripts/soak_test.py --users 50 --rounds 5 --llm-fail
    --llm-fail : LLM 키는 있지만 호출이 실패하는 상황(연결 거부)을 만들어 폴백 경로를 검증

HTTP 소켓 없이 main.dispatch()를 직접 호출하므로(로컬·Vercel 공통 코드) 네트워크 지연은 포함되지 않는다.
임시 SQLite DB를 쓰고 끝나면 지운다.
"""
from __future__ import annotations

import argparse
import os
import statistics
import sys
import tempfile
import time
import tracemalloc
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND = os.path.join(ROOT, "backend")
sys.path.insert(0, BACKEND)

parser = argparse.ArgumentParser()
parser.add_argument("--users", type=int, default=200)
parser.add_argument("--rounds", type=int, default=10)
parser.add_argument("--llm-fail", action="store_true")
args = parser.parse_args()

tmpdir = tempfile.mkdtemp(prefix="bloomy-soak-")
os.environ["BLOOMY_DB"] = os.path.join(tmpdir, "soak.db")
for k in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "BLOOMY_LLM_PROVIDER", "BLOOMY_LLM_BASE_URL"):
    os.environ.pop(k, None)
if args.llm_fail:
    os.environ["ANTHROPIC_API_KEY"] = "soak-test-invalid-key"
    os.environ["BLOOMY_LLM_BASE_URL"] = "http://127.0.0.1:9"  # 연결 거부 → 즉시 실패

import catalog

import main
import store

DIAG = {k: "some" for k in ("alphabet", "phonics", "readers", "response", "focus")}
CONSENT = {"agree_privacy": True, "agree_guardian": True}

lat: dict[str, list[float]] = defaultdict(list)
status_count: dict[int, int] = defaultdict(int)
errors: list[str] = []


def call(name: str, method: str, path: str, token: str | None = None, body: object = None) -> tuple[int, object]:
    headers = {"Authorization": "Bearer " + token} if token else {}
    t0 = time.perf_counter()
    try:
        code, payload, _ = main.dispatch(method, path, headers, body)
    except Exception as exc:  # dispatch가 예외를 밖으로 던지면 안정성 실패
        errors.append(f"{name}: 예외 {type(exc).__name__}: {exc}")
        code, payload = 599, None
    lat[name].append((time.perf_counter() - t0) * 1000)
    status_count[code] += 1
    if code >= 500:
        errors.append(f"{name}: {code} {str(payload)[:120]}")
    return code, payload


def mb(n: int) -> float:
    return n / 1024 / 1024


store.init()
catalog.load()
tracemalloc.start()
mem_points: list[tuple[int, float]] = []
started = time.perf_counter()
today = main.clock.today().isoformat()

for u in range(args.users):
    _, d = call("register", "POST", "/api/register",
                body={"email": f"soak{u}@test.local", "password": "secret123", **CONSENT})
    token = d.get("token") if isinstance(d, dict) else None
    _, d = call("create_child", "POST", "/api/children", token,
                {"name": f"아이{u}", "age": 4 + u % 4, "exposure": "some", "session_length": 10,
                 "interests": ["동물", "노래"][: 1 + u % 2], "diagnosis": DIAG})
    if not isinstance(d, dict) or "child" not in d:
        errors.append(f"create_child 실패 user={u}: {str(d)[:120]}")
        continue
    cid, pid = d["child"]["id"], d["plan"]["id"]
    call("approve", "POST", f"/api/children/{cid}/plans/{pid}/approve", token, {})
    for r in range(args.rounds):
        call("today", "GET", f"/api/children/{cid}/today", token)
        call("plan", "GET", f"/api/children/{cid}/plan", token)
        if r == 0:
            call("feedback", "POST", f"/api/children/{cid}/feedback", token,
                 {"date": today, "completion": ["full", "partial", "none"][u % 3],
                  "satisfaction": 1 + u % 5, "interest": 1 + (u + 1) % 5, "comprehension": 1 + (u + 2) % 5,
                  "memo": ["", "너무 어려워했어요", "다른 책으로 바꿔 주세요", "노래를 좋아해요"][u % 4]})
        call("report", "GET", f"/api/children/{cid}/report", token)
        call("messages", "GET", f"/api/children/{cid}/messages", token)
        call("health", "GET", "/api/health")
    if (u + 1) % max(1, args.users // 10) == 0:
        cur, _peak = tracemalloc.get_traced_memory()
        mem_points.append((u + 1, mb(cur)))

elapsed = time.perf_counter() - started
_, peak = tracemalloc.get_traced_memory()
total = sum(status_count.values())

print(f"모드: {'LLM 실패 주입(연결 거부) → 폴백' if args.llm_fail else '규칙 기반(LLM 키 없음)'}")
print(f"가정 {args.users}개 × 하루 루프 {args.rounds}회 · 요청 {total:,}건 · {elapsed:.1f}초")
print("상태 코드: " + ", ".join(f"{k}={v:,}" for k, v in sorted(status_count.items())))
print(f"5xx·예외: {len(errors)}건")
for e in errors[:10]:
    print("  - " + e)
print("\n| 요청 | 횟수 | 평균 ms | p95 ms | 최대 ms |")
print("|---|---|---|---|---|")
for name, xs in lat.items():
    xs_sorted = sorted(xs)
    p95 = xs_sorted[int(len(xs_sorted) * 0.95) - 1]
    print(f"| {name} | {len(xs):,} | {statistics.mean(xs):.1f} | {p95:.1f} | {max(xs):.1f} |")
print("\n파이썬 힙 메모리(tracemalloc, 가정 수 → MB): " + " · ".join(f"{n}→{m:.1f}" for n, m in mem_points))
print(f"최고치 {mb(peak):.1f} MB")
if args.llm_fail:
    import ai_bridge
    print("마지막 계획 생성 오류(폴백 원인): " + str(ai_bridge.rag_status().get("last_plan_error")))

try:
    os.remove(os.environ["BLOOMY_DB"])
    os.rmdir(tmpdir)
except OSError:
    pass
sys.exit(1 if errors else 0)
