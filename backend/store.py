"""SQLite 저장소 레이어 (Python 표준 라이브러리만 사용).

데이터 모델: 01-기획서.md §8.3
  users / children / contents / plans / cards / feedbacks /
  coach_messages / memory_facts
  (+ notifications: 인앱 발송 채널, meta: 크론 중복 발송 방지)

Vercel 운영 환경: DATABASE_URL 설정 시 store_pg(Postgres)로 재바인딩.
호출부는 `import store`만 하므로 어느 모드에서도 동일하게 동작한다.
"""
import json
import os
import sqlite3
from typing import cast

DB_PATH = os.environ.get(
    "BLOOMY_DB",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "bloomy.db"),
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY,
  email TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  salt TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS children (
  id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id),
  name TEXT NOT NULL DEFAULT '',
  age INTEGER NOT NULL,
  birth_year INTEGER,
  ek_kindergarten INTEGER NOT NULL DEFAULT 0,
  exposure TEXT NOT NULL DEFAULT 'none',
  materials TEXT NOT NULL DEFAULT '',
  favorite_topics TEXT NOT NULL DEFAULT '',
  session_length INTEGER NOT NULL DEFAULT 10,
  diagnosis TEXT NOT NULL DEFAULT '{}',
  level INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS contents (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  age_min INTEGER NOT NULL,
  age_max INTEGER NOT NULL,
  level INTEGER NOT NULL,
  skill TEXT NOT NULL DEFAULT '',
  type TEXT NOT NULL DEFAULT '',
  provider TEXT NOT NULL DEFAULT 'link',
  link TEXT NOT NULL DEFAULT '',
  session_minutes INTEGER NOT NULL DEFAULT 10,
  expert_note TEXT NOT NULL DEFAULT '',
  trust_source TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS plans (
  id INTEGER PRIMARY KEY,
  child_id INTEGER NOT NULL REFERENCES children(id),
  week_start TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'draft',
  source TEXT NOT NULL DEFAULT 'onboarding_rule',
  base_level INTEGER NOT NULL DEFAULT 1,
  explanation TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS cards (
  id INTEGER PRIMARY KEY,
  plan_id INTEGER NOT NULL REFERENCES plans(id),
  child_id INTEGER NOT NULL REFERENCES children(id),
  date TEXT NOT NULL,
  content_id TEXT,
  task TEXT NOT NULL DEFAULT '',
  minutes INTEGER NOT NULL DEFAULT 10,
  check_point TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'pending',
  UNIQUE(plan_id, date)
);

CREATE TABLE IF NOT EXISTS feedbacks (
  id INTEGER PRIMARY KEY,
  child_id INTEGER NOT NULL REFERENCES children(id),
  card_id INTEGER REFERENCES cards(id),
  date TEXT NOT NULL,
  completion TEXT NOT NULL DEFAULT '',
  satisfaction INTEGER NOT NULL DEFAULT 0,
  interest INTEGER NOT NULL DEFAULT 0,
  comprehension INTEGER NOT NULL DEFAULT 0,
  memo TEXT NOT NULL DEFAULT '',
  rest_day INTEGER NOT NULL DEFAULT 0,
  memo_intent TEXT NOT NULL DEFAULT 'none',
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE(child_id, date)
);

CREATE TABLE IF NOT EXISTS coach_messages (
  id INTEGER PRIMARY KEY,
  child_id INTEGER NOT NULL REFERENCES children(id),
  feedback_id INTEGER,
  date TEXT NOT NULL,
  branch TEXT NOT NULL,
  memo_intent TEXT NOT NULL DEFAULT 'none',
  body TEXT NOT NULL,
  model TEXT NOT NULL DEFAULT '',
  prompt_version TEXT NOT NULL DEFAULT '',
  is_ai_generated INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS memory_facts (
  id INTEGER PRIMARY KEY,
  child_id INTEGER NOT NULL REFERENCES children(id),
  kind TEXT NOT NULL,
  value TEXT NOT NULL,
  updated_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE(child_id, kind, value)
);

CREATE TABLE IF NOT EXISTS notifications (
  id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id),
  title TEXT NOT NULL,
  body TEXT NOT NULL DEFAULT '',
  kind TEXT NOT NULL DEFAULT 'info',
  read_at TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
"""


def conn() -> sqlite3.Connection:
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    _ = c.execute("PRAGMA foreign_keys = ON")
    return c


def init() -> None:
    c = conn()
    try:
        _ = c.executescript(SCHEMA)
        # 마이그레이션: 개인정보 동의 기록 컬럼 (기존 DB에도 추가)
        cols = {r[1] for r in c.execute("PRAGMA table_info(users)").fetchall()}
        for col in ("consent_version", "consented_at"):
            if col not in cols:
                _ = c.execute(f"ALTER TABLE users ADD COLUMN {col} TEXT")
        c.commit()
    finally:
        c.close()


def query(sql: str, args: tuple[object, ...] = ()) -> list[dict[str, object]]:
    c = conn()
    try:
        rows: list[sqlite3.Row] = list(c.execute(sql, args).fetchall())
        return [dict(r) for r in rows]
    finally:
        c.close()


def one(sql: str, args: tuple[object, ...] = ()) -> dict[str, object] | None:
    c = conn()
    try:
        row: sqlite3.Row | None = c.execute(sql, args).fetchone()  # pyright: ignore[reportAny]
        return dict(row) if row else None
    finally:
        c.close()


def execute(sql: str, args: tuple[object, ...] = ()) -> int | None:
    c = conn()
    try:
        cur = c.execute(sql, args)
        c.commit()
        return cur.lastrowid
    finally:
        c.close()


# --- users ------------------------------------------------------------------

def create_user(
    email: str, pw_hash: str, salt: str, consent_version: str | None = None,
) -> int:
    return cast("int", execute(
        "INSERT INTO users(email, password_hash, salt, consent_version, consented_at) "
        "VALUES (?, ?, ?, ?, CASE WHEN ? IS NULL THEN NULL ELSE datetime('now') END)",
        (email, pw_hash, salt, consent_version, consent_version),
    ))


def record_consent(user_id: int, version: str) -> None:
    _ = execute(
        "UPDATE users SET consent_version=?, consented_at=datetime('now') WHERE id=?",
        (version, user_id),
    )


# 탈퇴 시 삭제 순서 (FK 참조 역순). child_id/user_id 기준.
_CHILD_TABLES = ("feedbacks", "coach_messages", "memory_facts", "cards", "plans")


def delete_account(user_id: int) -> None:
    """동의 철회(탈퇴): 계정과 아이 관련 데이터를 한 트랜잭션으로 모두 삭제."""
    c = conn()
    try:
        child_ids = [r[0] for r in c.execute(
            "SELECT id FROM children WHERE user_id=?", (user_id,)).fetchall()]
        for cid in child_ids:
            for table in _CHILD_TABLES:
                _ = c.execute(f"DELETE FROM {table} WHERE child_id=?", (cid,))
        _ = c.execute("DELETE FROM children WHERE user_id=?", (user_id,))
        _ = c.execute("DELETE FROM notifications WHERE user_id=?", (user_id,))
        _ = c.execute("DELETE FROM users WHERE id=?", (user_id,))
        c.commit()
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()


def get_user(user_id: int) -> dict[str, object] | None:
    return one("SELECT * FROM users WHERE id=?", (user_id,))


def get_user_by_email(email: str) -> dict[str, object] | None:
    return one("SELECT * FROM users WHERE email=?", (email,))


# --- children ---------------------------------------------------------------

def create_child(
    user_id: int, name: str, age: int, birth_year: int | None,
    ek: int, exposure: str, materials: str, favorite_topics: str,
    session_length: int, diagnosis_json: str, level: int,
) -> int:
    return cast("int", execute(
        "INSERT INTO children(user_id, name, age, birth_year, ek_kindergarten, exposure, materials, favorite_topics, session_length, diagnosis, level) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (user_id, name, age, birth_year, ek, exposure, materials,
         favorite_topics, session_length, diagnosis_json, level),
    ))


def get_child(child_id: int) -> dict[str, object] | None:
    return one("SELECT * FROM children WHERE id=?", (child_id,))


def get_children(user_id: int) -> list[dict[str, object]]:
    return query("SELECT * FROM children WHERE user_id=? ORDER BY id", (user_id,))


def all_children() -> list[dict[str, object]]:
    return query("SELECT * FROM children ORDER BY id")


def get_user_by_child(child_id: int) -> dict[str, object] | None:
    return one(
        "SELECT u.* FROM users u JOIN children c ON c.user_id=u.id WHERE c.id=?",
        (child_id,),
    )


def update_child_settings(
    child_id: int, name: str | None = None,
    session_length: int | None = None,
) -> None:
    c = conn()
    try:
        if name is not None:
            _ = c.execute("UPDATE children SET name=? WHERE id=?", (name, child_id))
        if session_length is not None:
            _ = c.execute(
                "UPDATE children SET session_length=? WHERE id=?",
                (session_length, child_id),
            )
        c.commit()
    finally:
        c.close()


def child_public(child: dict[str, object]) -> dict[str, object]:
    """diagnosis JSON 문자열을 파싱해서 노출."""
    d = dict(child)
    try:
        diagnosis: object = json.loads(str(d.get("diagnosis") or "{}"))  # pyright: ignore[reportAny]
        if isinstance(diagnosis, dict):
            diagnosis = {str(k): v for k, v in diagnosis.items()}  # pyright: ignore[reportUnknownVariableType, reportUnknownArgumentType]
        d["diagnosis"] = diagnosis
    except ValueError:
        d["diagnosis"] = {}
    return d


# --- plans ----------------------------------------------------------------------

def create_plan(
    child_id: int, week_start: str, source: str, base_level: int,
    explanation: str, status: str = "draft",
) -> int:
    return cast("int", execute(
        "INSERT INTO plans(child_id, week_start, status, source, base_level, explanation) VALUES (?, ?, ?, ?, ?, ?)",
        (child_id, week_start, status, source, base_level, explanation),
    ))


def get_plan(plan_id: int) -> dict[str, object] | None:
    return one("SELECT * FROM plans WHERE id=?", (plan_id,))


def latest_plan(child_id: int) -> dict[str, object] | None:
    return one(
        "SELECT * FROM plans WHERE child_id=? ORDER BY id DESC", (child_id,)
    )


def approved_plan(child_id: int) -> dict[str, object] | None:
    return one(
        "SELECT * FROM plans WHERE child_id=? AND status='approved' ORDER BY id DESC",
        (child_id,),
    )


def approve_plan(plan_id: int) -> dict[str, object] | None:
    """draft 계획 승인. 같은 아이의 기존 draft/approved는 superseded."""
    c = conn()
    try:
        p = one("SELECT * FROM plans WHERE id=?", (plan_id,))
        if not p or p["status"] != "draft":
            return None
        _ = c.execute(
            "UPDATE plans SET status='superseded' WHERE child_id=? AND id<>? AND status IN ('draft','approved')",
            (p["child_id"], plan_id),
        )
        _ = c.execute("UPDATE plans SET status='approved' WHERE id=?", (plan_id,))
        c.commit()
        return get_plan(plan_id)
    finally:
        c.close()


def finish_plan(plan_id: int, status: str = "done") -> None:
    _ = execute("UPDATE plans SET status=? WHERE id=?", (status, plan_id))


def plans_for_child(child_id: int) -> list[dict[str, object]]:
    return query("SELECT * FROM plans WHERE child_id=? ORDER BY id", (child_id,))


# --- cards --------------------------------------------------------------------

def add_cards(
    plan_id: int, child_id: int, rows: list[tuple[object, object, object, object, object]],
) -> list[int]:
    """rows: [(date, content_id, task, minutes, check_point), ...]"""
    ids: list[int] = []
    for date, content_id, task, minutes, check_point in rows:
        ids.append(cast("int", execute(
            "INSERT INTO cards(plan_id, child_id, date, content_id, task, minutes, check_point) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (plan_id, child_id, date, content_id, task, minutes, check_point),
        )))
    return ids


def cards_for_plan(plan_id: int) -> list[dict[str, object]]:
    return query(
        "SELECT * FROM cards WHERE plan_id=? ORDER BY date", (plan_id,)
    )


def _card_where_child_status() -> str:
    return (
        "SELECT c.* FROM cards c JOIN plans p ON p.id=c.plan_id "
        "WHERE c.child_id=? AND p.status='approved'"
    )


def get_card_for_child(child_id: int, date: str) -> dict[str, object] | None:
    return one(
        _card_where_child_status() + " AND c.date=?", (child_id, date)
    )


def next_card_for_child(child_id: int, after_date: str) -> dict[str, object] | None:
    return one(
        _card_where_child_status() + " AND c.date>? ORDER BY c.date LIMIT 1",
        (child_id, after_date),
    )


def count_cards(child_id: int, status: str | None = None) -> int:
    sql = "SELECT COUNT(*) AS n FROM cards WHERE child_id=?"
    args: list[object] = [child_id]
    if status:
        sql += " AND status=?"
        args.append(status)
    r = one(sql, tuple(args))
    n = r["n"] if r else 0
    return n if isinstance(n, int) else 0


def set_card_status(card_id: int, status: str) -> None:
    _ = execute("UPDATE cards SET status=? WHERE id=?", (status, card_id))


def update_card_content(
    card_id: int, content_id: str | None, task: str, minutes: int, check_point: str,
) -> None:
    _ = execute(
        "UPDATE cards SET content_id=?, task=?, minutes=?, check_point=? WHERE id=?",
        (content_id, task, minutes, check_point, card_id),
    )


# --- feedbacks --------------------------------------------------------------------

def add_feedback(
    child_id: int, card_id: int | None,
    date: str, completion: str, satisfaction: int, interest: int,
    comprehension: int, memo: str, rest_day: bool, memo_intent: str = "none",
) -> int:
    return cast("int", execute(
        "INSERT INTO feedbacks(child_id, card_id, date, completion, satisfaction, interest, comprehension, memo, rest_day, memo_intent) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (child_id, card_id, date, completion, satisfaction, interest,
         comprehension, memo, 1 if rest_day else 0, memo_intent),
    ))


def set_feedback_intent(feedback_id: int, memo_intent: str) -> None:
    _ = execute(
        "UPDATE feedbacks SET memo_intent=? WHERE id=?", (memo_intent, feedback_id)
    )


def get_feedback(child_id: int, date: str) -> dict[str, object] | None:
    return one(
        "SELECT * FROM feedbacks WHERE child_id=? AND date=?", (child_id, date)
    )


def feedback_between(
    child_id: int, start: str, end: str, include_rest: bool = False,
) -> list[dict[str, object]]:
    sql = (
        "SELECT f.*, c.content_id AS content_id FROM feedbacks f "
        "LEFT JOIN cards c ON c.id=f.card_id "
        "WHERE f.child_id=? AND f.date>=? AND f.date<=?"
    )
    if not include_rest:
        sql += " AND f.rest_day=0"
    return query(sql + " ORDER BY f.date", (child_id, start, end))


def last_feedback_before(child_id: int, date: str) -> dict[str, object] | None:
    return one(
        "SELECT * FROM feedbacks WHERE child_id=? AND date<? AND rest_day=0 ORDER BY date DESC",
        (child_id, date),
    )


def feedback_dates(child_id: int, month: str) -> list[str]:
    return [
        str(r["date"])
        for r in query(
            "SELECT date FROM feedbacks WHERE child_id=? AND date LIKE ? AND rest_day=0",
            (child_id, month + "%"),
        )
    ]


# --- coach messages ------------------------------------------------------------------

def add_coach_message(
    child_id: int, feedback_id: int | None,
    date: str, branch: str, memo_intent: str, body: str, model: str,
    prompt_version: str, is_ai_generated: bool = True,
) -> int:
    return cast("int", execute(
        "INSERT INTO coach_messages(child_id, feedback_id, date, branch, memo_intent, body, model, prompt_version, is_ai_generated) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (child_id, feedback_id, date, branch, memo_intent, body, model,
         prompt_version, 1 if is_ai_generated else 0),
    ))


def latest_message(child_id: int) -> dict[str, object] | None:
    return one(
        "SELECT * FROM coach_messages WHERE child_id=? ORDER BY id DESC", (child_id,)
    )


def get_messages(child_id: int, limit: int = 30) -> list[dict[str, object]]:
    return query(
        "SELECT * FROM coach_messages WHERE child_id=? ORDER BY id DESC LIMIT ?",
        (child_id, limit),
    )


def branch_dates(child_id: int, start: str, end: str) -> list[tuple[str, str]]:
    """[(date, branch)] — 분기 이력 (확신 문구 데이터 조건 판단용)."""
    return [
        (str(r["date"]), str(r["branch"]))
        for r in query(
            "SELECT cm.date AS date, cm.branch AS branch FROM coach_messages cm JOIN feedbacks f ON f.id=cm.feedback_id WHERE f.child_id=? AND cm.date>=? AND cm.date<=? ORDER BY cm.date",
            (child_id, start, end),
        )
    ]


# --- memory facts ---------------------------------------------------------------------

def upsert_fact(child_id: int, kind: str, value: str) -> None:
    _ = execute(
        "INSERT INTO memory_facts(child_id, kind, value) VALUES (?, ?, ?) ON CONFLICT(child_id, kind, value) DO UPDATE SET updated_at=datetime('now')",
        (child_id, kind, value),
    )


def replace_facts(child_id: int, kind: str, values: list[str]) -> None:
    """kind 단일값 팩트 갱신 (예: interest_low_streak)."""
    c = conn()
    try:
        _ = c.execute(
            "DELETE FROM memory_facts WHERE child_id=? AND kind=?", (child_id, kind)
        )
        for v in values:
            _ = c.execute(
                "INSERT INTO memory_facts(child_id, kind, value) VALUES (?, ?, ?)",
                (child_id, kind, v),
            )
        c.commit()
    finally:
        c.close()


def get_facts(child_id: int, kind: str | None = None) -> list[dict[str, object]]:
    if kind:
        return query(
            "SELECT * FROM memory_facts WHERE child_id=? AND kind=? ORDER BY id",
            (child_id, kind),
        )
    return query(
        "SELECT * FROM memory_facts WHERE child_id=? ORDER BY kind, id", (child_id,)
    )


# --- notifications ---------------------------------------------------------------------

def add_notification(user_id: int, title: str, body: str, kind: str = "info") -> int | None:
    return execute(
        "INSERT INTO notifications(user_id, title, body, kind) VALUES (?, ?, ?, ?)",
        (user_id, title, body, kind),
    )


def get_notifications(user_id: int, limit: int = 50) -> list[dict[str, object]]:
    return query(
        "SELECT * FROM notifications WHERE user_id=? ORDER BY id DESC LIMIT ?",
        (user_id, limit),
    )


def count_unread(user_id: int) -> int:
    r = one(
        "SELECT COUNT(*) AS n FROM notifications WHERE user_id=? AND read_at IS NULL",
        (user_id,),
    )
    n = r["n"] if r else 0
    return n if isinstance(n, int) else 0


def mark_notifications_read(user_id: int) -> None:
    _ = execute(
        "UPDATE notifications SET read_at=datetime('now') WHERE user_id=? AND read_at IS NULL",
        (user_id,),
    )


# --- meta --------------------------------------------------------------------------------

def meta_get(key: str) -> str | None:
    r = one("SELECT value FROM meta WHERE key=?", (key,))
    value = r["value"] if r else None
    return value if isinstance(value, str) else None


def meta_set(key: str, value: str) -> None:
    _ = execute(
        "INSERT INTO meta(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )


# ---------------------------------------------------------------------------
# Vercel 운영 환경: DATABASE_URL 설정 시 Postgres(store_pg)로 재바인딩.
# ---------------------------------------------------------------------------
if os.environ.get("DATABASE_URL"):
    try:
        import store_pg as _pg

        pg_vars: dict[str, object] = dict(vars(_pg))
        globals().update(
            {k: v for k, v in pg_vars.items() if not k.startswith("_")}
        )
    except ImportError:  # psycopg 미설치(로컬 표준라이브러리 모드) → SQLite 유지
        pass
