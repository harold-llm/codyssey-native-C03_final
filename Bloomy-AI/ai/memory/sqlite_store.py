"""SQLite persistence. All child reads and mutations are explicitly scoped."""
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from threading import RLock


class SQLiteMemoryRepository:
    def __init__(self, path):
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._db = sqlite3.connect(str(path), isolation_level=None, timeout=10, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        version = self._db.execute("PRAGMA user_version").fetchone()[0]
        if version not in (0, 1):
            self._db.close()
            raise ValueError(f"unsupported memory schema version: {version}")
        self._db.executescript("""
            PRAGMA foreign_keys=ON;
            PRAGMA secure_delete=ON;
            CREATE TABLE IF NOT EXISTS memory_events (
                child_id INTEGER NOT NULL CHECK(child_id > 0),
                day TEXT NOT NULL,
                event_id TEXT NOT NULL,
                record_hash TEXT NOT NULL,
                feedback_json TEXT NOT NULL,
                content_id TEXT,
                minutes INTEGER,
                request_hash TEXT,
                result_json TEXT,
                PRIMARY KEY(child_id, day),
                UNIQUE(child_id, event_id)
            );
            CREATE TABLE IF NOT EXISTS memory_preferences (
                child_id INTEGER NOT NULL CHECK(child_id > 0),
                effective_date TEXT NOT NULL,
                kind TEXT NOT NULL CHECK(kind IN ('favorite_topics', 'owned_materials')),
                value_json TEXT NOT NULL,
                PRIMARY KEY(child_id, effective_date, kind)
            );
            PRAGMA user_version=1;
        """)

    @contextmanager
    def transaction(self):
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                yield
                self._db.commit()
            except BaseException:
                self._db.rollback()
                raise

    def event(self, child_id, day):
        with self._lock:
            row = self._db.execute("SELECT * FROM memory_events WHERE child_id=? AND day=?", (child_id, day)).fetchone()
            return dict(row) if row else None

    def event_by_id(self, child_id, event_id):
        with self._lock:
            row = self._db.execute("SELECT * FROM memory_events WHERE child_id=? AND event_id=?", (child_id, event_id)).fetchone()
            return dict(row) if row else None

    def events(self, child_id, through):
        with self._lock:
            return [dict(row) for row in self._db.execute(
                "SELECT * FROM memory_events WHERE child_id=? AND day<=? ORDER BY day", (child_id, through))]

    def preferences(self, child_id, through):
        with self._lock:
            return [dict(row) for row in self._db.execute(
                "SELECT * FROM memory_preferences WHERE child_id=? AND effective_date<=? ORDER BY effective_date",
                (child_id, through))]

    def insert_event(self, row):
        self._db.execute("""INSERT INTO memory_events
            (child_id, day, event_id, record_hash, feedback_json, content_id, minutes)
            VALUES (:child_id, :day, :event_id, :record_hash, :feedback_json, :content_id, :minutes)""", row)

    def cache_result(self, child_id, day, signature, result):
        self._db.execute("UPDATE memory_events SET request_hash=?, result_json=? WHERE child_id=? AND day=?",
                         (signature, result, child_id, day))

    def invalidate_from(self, child_id, day):
        self._db.execute("UPDATE memory_events SET result_json=NULL WHERE child_id=? AND day>=?", (child_id, day))

    def set_preferences(self, child_id, day, values):
        for kind, value in values.items():
            self._db.execute("""INSERT INTO memory_preferences VALUES (?, ?, ?, ?)
                ON CONFLICT(child_id, effective_date, kind) DO UPDATE SET value_json=excluded.value_json""",
                (child_id, day, kind, value))
        self.invalidate_from(child_id, day)

    def delete_feedback(self, child_id, day):
        count = self._db.execute("DELETE FROM memory_events WHERE child_id=? AND day=?", (child_id, day)).rowcount
        self.invalidate_from(child_id, day)
        return count

    def delete_child(self, child_id):
        self._db.execute("DELETE FROM memory_events WHERE child_id=?", (child_id,))
        self._db.execute("DELETE FROM memory_preferences WHERE child_id=?", (child_id,))

    def close(self):
        with self._lock:
            self._db.close()
