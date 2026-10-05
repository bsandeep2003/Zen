"""
memory/chat_store.py — Durable per-user chat memory store (SQLite).

This is the *real* fallback that `agent.py` previously only pretended to have:
it used to set the memory client to the string "sqlite_fallback", which made
every read return [] and every write a silent no-op.

The class below is deliberately shaped like the mem0 client so callers can use
either backend interchangeably:

    store.get_all(filters={"user_id": uid})  -> {"results": [ {memory, id, ...}, ... ]}
    store.search(query, user_id=uid)         -> {"results": [...]}
    store.add(messages=[...], user_id=uid)   -> {"results": [...]}

Storage location: <backend>/mem0_storage/chat_memory.db
"""
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

DEFAULT_DB_DIR = Path(__file__).resolve().parent.parent / "mem0_storage"
DEFAULT_DB_NAME = "chat_memory.db"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SqliteMemoryStore:
    """Minimal, dependency-free durable memory store."""

    backend_name = "sqlite"

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            DEFAULT_DB_DIR.mkdir(parents=True, exist_ok=True)
            db_path = str(DEFAULT_DB_DIR / DEFAULT_DB_NAME)
        self.db_path = str(db_path)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    # ── internals ────────────────────────────────────────────────────────────

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self):
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS memories (
                    id          TEXT PRIMARY KEY,
                    user_id     TEXT NOT NULL,
                    memory      TEXT NOT NULL,
                    text_key    TEXT NOT NULL,
                    metadata    TEXT,
                    created_at  TEXT NOT NULL,
                    updated_at  TEXT NOT NULL,
                    UNIQUE(user_id, text_key)
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_memories_user ON memories(user_id)"
            )
            # Ledger of text already forwarded to an upstream memory backend
            # (mem0). Kept separate from `memories` because mem0 rewrites text
            # during extraction, so dedup-on-read cannot detect these.
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS forwarded (
                    user_id   TEXT NOT NULL,
                    text_key  TEXT NOT NULL,
                    forwarded_at TEXT NOT NULL,
                    PRIMARY KEY (user_id, text_key)
                )
                """
            )

    @staticmethod
    def _normalize(text: str) -> str:
        return " ".join((text or "").split()).lower()

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> Dict[str, Any]:
        try:
            metadata = json.loads(row["metadata"]) if row["metadata"] else None
        except Exception:
            metadata = None
        return {
            "id": row["id"],
            "memory": row["memory"],
            "user_id": row["user_id"],
            "metadata": metadata,
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    @staticmethod
    def _resolve_user_id(filters=None, kwargs=None) -> Optional[str]:
        """Accept either mem0-style filters={'user_id': ...} or a bare user_id kwarg."""
        if isinstance(filters, dict) and filters.get("user_id"):
            return str(filters["user_id"])
        if kwargs and kwargs.get("user_id"):
            return str(kwargs["user_id"])
        return None

    # ── write ────────────────────────────────────────────────────────────────

    def add(
        self,
        messages: Optional[List[Dict[str, str]]] = None,
        user_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """Persist the text of each message. Idempotent per (user_id, normalized text)."""
        if not user_id:
            user_id = kwargs.get("user_id")
        if not user_id:
            return {"results": []}

        created: List[Dict[str, Any]] = []
        now = _now()

        with self._connect() as conn:
            for msg in messages or []:
                if isinstance(msg, str):
                    text = msg
                elif isinstance(msg, dict):
                    text = msg.get("content") or msg.get("memory") or ""
                else:
                    text = str(msg)

                text = (text or "").strip()
                if not text:
                    continue

                text_key = self._normalize(text)
                existing = conn.execute(
                    "SELECT id FROM memories WHERE user_id = ? AND text_key = ?",
                    (str(user_id), text_key),
                ).fetchone()
                if existing:
                    # Already remembered — refresh the timestamp instead of duplicating.
                    conn.execute(
                        "UPDATE memories SET updated_at = ? WHERE id = ?",
                        (now, existing["id"]),
                    )
                    continue

                mem_id = str(uuid.uuid4())
                conn.execute(
                    """
                    INSERT INTO memories (id, user_id, memory, text_key, metadata, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        mem_id,
                        str(user_id),
                        text,
                        text_key,
                        json.dumps(metadata) if metadata else None,
                        now,
                        now,
                    ),
                )
                created.append(
                    {
                        "id": mem_id,
                        "memory": text,
                        "user_id": str(user_id),
                        "metadata": metadata,
                        "created_at": now,
                        "updated_at": now,
                    }
                )

        return {"results": created}

    # ── read ─────────────────────────────────────────────────────────────────

    def get_all(self, filters=None, **kwargs) -> Dict[str, Any]:
        """Return every memory for a user, newest first."""
        user_id = self._resolve_user_id(filters, kwargs)
        if not user_id:
            return {"results": []}

        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM memories WHERE user_id = ? ORDER BY created_at DESC",
                (user_id,),
            ).fetchall()

        return {"results": [self._row_to_record(r) for r in rows]}

    def search(
        self,
        query: str = "",
        user_id: Optional[str] = None,
        limit: int = 50,
        filters=None,
        **kwargs,
    ) -> Dict[str, Any]:
        """Keyword-ranked search over the user's memories."""
        if not user_id:
            user_id = self._resolve_user_id(filters, kwargs)
        if not user_id:
            return {"results": []}

        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM memories WHERE user_id = ? ORDER BY created_at DESC",
                (str(user_id),),
            ).fetchall()

        terms = {w for w in self._normalize(query).split() if len(w) > 2}
        scored = []
        for row in rows:
            record = self._row_to_record(row)
            words = set(self._normalize(record["memory"]).split())
            record["score"] = float(len(terms & words)) if terms else 0.0
            scored.append(record)

        if terms:
            scored.sort(key=lambda r: r["score"], reverse=True)
        return {"results": scored[: max(1, int(limit))]}

    def count(self, user_id: Optional[str] = None) -> int:
        with self._connect() as conn:
            if user_id:
                row = conn.execute(
                    "SELECT COUNT(*) AS n FROM memories WHERE user_id = ?",
                    (str(user_id),),
                ).fetchone()
            else:
                row = conn.execute("SELECT COUNT(*) AS n FROM memories").fetchone()
        return int(row["n"]) if row else 0

    def delete(self, memory_id: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM memories WHERE id = ?", (str(memory_id),))
            return cur.rowcount > 0

    # ── forwarding ledger (used when mem0 is the active backend) ─────────────

    def filter_unforwarded(self, user_id: str, texts: List[str]) -> List[str]:
        """Return only the texts not yet forwarded to the upstream backend."""
        if not user_id or not texts:
            return []
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT text_key FROM forwarded WHERE user_id = ?", (str(user_id),)
            ).fetchall()
        seen = {r["text_key"] for r in rows}

        fresh: List[str] = []
        batch_keys = set()
        for text in texts:
            stripped = (text or "").strip()
            if not stripped:
                continue
            key = self._normalize(stripped)
            if key in seen or key in batch_keys:
                continue
            batch_keys.add(key)
            fresh.append(stripped)
        return fresh

    def mark_forwarded(self, user_id: str, texts: List[str]):
        """Record that these texts were handed to the upstream backend."""
        if not user_id or not texts:
            return
        now = _now()
        with self._connect() as conn:
            for text in texts:
                stripped = (text or "").strip()
                if not stripped:
                    continue
                conn.execute(
                    """
                    INSERT OR IGNORE INTO forwarded (user_id, text_key, forwarded_at)
                    VALUES (?, ?, ?)
                    """,
                    (str(user_id), self._normalize(stripped), now),
                )


def get_chat_store() -> SqliteMemoryStore:
    """Process-wide singleton accessor."""
    global _store
    if _store is None:
        _store = SqliteMemoryStore()
    return _store


_store: Optional[SqliteMemoryStore] = None
