"""Simple SQLite-backed cache for enrichment results.

Keyed by (namespace, key). Namespaces map to the CACHE_TTL entries in config.
"""
from __future__ import annotations
import json
import logging
import sqlite3
import threading
import time
from typing import Any, Optional

from .config import CACHE_PATH, CACHE_TTL

log = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS cache (
    namespace TEXT NOT NULL,
    key       TEXT NOT NULL,
    payload   TEXT NOT NULL,
    stored_at INTEGER NOT NULL,
    PRIMARY KEY (namespace, key)
);
"""


class Cache:
    def __init__(self, path: str = CACHE_PATH):
        self.path = path
        self._lock = threading.Lock()
        self._ensure_schema()

    def _connect(self):
        # check_same_thread=False because we serialize via self._lock ourselves
        conn = sqlite3.connect(self.path, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL;")
        return conn

    def _ensure_schema(self):
        with self._lock, self._connect() as conn:
            conn.executescript(_SCHEMA)

    def get(self, namespace: str, key: str) -> Optional[Any]:
        ttl = CACHE_TTL.get(namespace, 0)
        if ttl <= 0:
            return None
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT payload, stored_at FROM cache WHERE namespace=? AND key=?",
                (namespace, key),
            ).fetchone()
        if row is None:
            return None
        payload, stored_at = row
        if (time.time() - stored_at) > ttl:
            return None
        try:
            return json.loads(payload)
        except json.JSONDecodeError:
            return None

    def set(self, namespace: str, key: str, value: Any) -> None:
        serialized = json.dumps(value, default=str)
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO cache (namespace, key, payload, stored_at) "
                "VALUES (?, ?, ?, ?)",
                (namespace, key, serialized, int(time.time())),
            )
            conn.commit()

    def clear(self, namespace: Optional[str] = None) -> None:
        with self._lock, self._connect() as conn:
            if namespace:
                conn.execute("DELETE FROM cache WHERE namespace=?", (namespace,))
            else:
                conn.execute("DELETE FROM cache")
            conn.commit()


_cache_singleton: Optional[Cache] = None


def get_cache() -> Cache:
    global _cache_singleton
    if _cache_singleton is None:
        _cache_singleton = Cache()
    return _cache_singleton
