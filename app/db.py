"""SQLite access. One connection per thread (ThreadingHTTPServer)."""
from __future__ import annotations

import sqlite3
import threading
from typing import Any, Iterable, List, Optional

from . import config
from .geo import haversine_km

_local = threading.local()


def connect() -> sqlite3.Connection:
    conn = getattr(_local, "conn", None)
    if conn is None:
        conn = sqlite3.connect(str(config.DB_PATH), timeout=15.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        # Distance maths lives in Python so we don't depend on SQLite being
        # compiled with the optional math functions.
        conn.create_function("haversine", 4, haversine_km, deterministic=True)
        _local.conn = conn
    return conn


def init_db() -> None:
    sql = config.SCHEMA_PATH.read_text(encoding="utf-8")
    conn = connect()
    conn.executescript(sql)
    conn.commit()


def query(sql: str, params: Iterable[Any] = ()) -> List[sqlite3.Row]:
    return connect().execute(sql, tuple(params)).fetchall()


def query_one(sql: str, params: Iterable[Any] = ()) -> Optional[sqlite3.Row]:
    return connect().execute(sql, tuple(params)).fetchone()


def execute(sql: str, params: Iterable[Any] = ()) -> sqlite3.Cursor:
    conn = connect()
    cur = conn.execute(sql, tuple(params))
    conn.commit()
    return cur


def executemany(sql: str, seq: Iterable[Iterable[Any]]) -> None:
    conn = connect()
    conn.executemany(sql, [tuple(r) for r in seq])
    conn.commit()


def scalar(sql: str, params: Iterable[Any] = ()) -> Any:
    row = query_one(sql, params)
    return None if row is None else row[0]
