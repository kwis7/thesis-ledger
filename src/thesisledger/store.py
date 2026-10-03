"""A small transactional research store. No personal investment sources are used."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


def encode(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)


def decode(value: str | None, default: Any = None) -> Any:
    return json.loads(value) if value is not None else default


SCHEMA = """
CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS companies (
    symbol TEXT PRIMARY KEY, payload TEXT NOT NULL, tier TEXT NOT NULL DEFAULT 'focused',
    watched INTEGER NOT NULL DEFAULT 1, thesis_status TEXT NOT NULL DEFAULT 'unchanged',
    data_status TEXT NOT NULL DEFAULT 'fresh'
);
CREATE TABLE IF NOT EXISTS revisions (
    id TEXT PRIMARY KEY, symbol TEXT NOT NULL, version INTEGER NOT NULL,
    company_json TEXT NOT NULL, valuation_json TEXT NOT NULL,
    reason TEXT NOT NULL, event_id TEXT, created_at TEXT NOT NULL,
    input_hash TEXT NOT NULL, UNIQUE(symbol, version)
);
CREATE TABLE IF NOT EXISTS source_events (
    id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL UNIQUE, symbol TEXT NOT NULL,
    payload TEXT NOT NULL, state TEXT NOT NULL, decision_ts TEXT NOT NULL,
    created_at TEXT NOT NULL, replay_count INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS alerts (
    id TEXT PRIMARY KEY, event_id TEXT NOT NULL UNIQUE, symbol TEXT NOT NULL,
    payload TEXT NOT NULL, review_state TEXT NOT NULL DEFAULT 'new',
    delivery_state TEXT NOT NULL DEFAULT 'delivered_local', created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS outbox (
    id TEXT PRIMARY KEY, alert_id TEXT NOT NULL UNIQUE, channel TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'pending', created_at TEXT NOT NULL,
    attempted_at TEXT, delivered_at TEXT, error_code TEXT, receipt TEXT,
    FOREIGN KEY(alert_id) REFERENCES alerts(id)
);
CREATE TABLE IF NOT EXISTS activity (
    id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, symbol TEXT,
    title TEXT NOT NULL, at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS reports (
    id TEXT PRIMARY KEY, symbol TEXT NOT NULL, title TEXT NOT NULL,
    markdown TEXT NOT NULL, snapshot_json TEXT NOT NULL, status TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS forecasts (
    id TEXT PRIMARY KEY, symbol TEXT NOT NULL, revision_id TEXT NOT NULL,
    horizon TEXT NOT NULL, metric TEXT NOT NULL, predicted REAL NOT NULL,
    frozen_at TEXT NOT NULL, observed REAL, observed_at TEXT,
    FOREIGN KEY(revision_id) REFERENCES revisions(id)
);
CREATE INDEX IF NOT EXISTS event_symbol ON source_events(symbol, created_at);
CREATE INDEX IF NOT EXISTS alert_symbol ON alerts(symbol, created_at);
"""


class Store:
    def __init__(self, workspace: str | Path):
        self.workspace = Path(workspace).resolve()
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.path = self.workspace / "research.sqlite3"
        with self.connect() as connection:
            connection.executescript(SCHEMA)

    @contextmanager
    def connect(self, *, write: bool = False) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=15)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA journal_mode=WAL")
        try:
            if write:
                connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def rows(self, sql: str, parameters: tuple = ()) -> list[dict]:
        with self.connect() as connection:
            return [dict(row) for row in connection.execute(sql, parameters)]

    def metadata(self, key: str, default: Any = None) -> Any:
        rows = self.rows("SELECT value FROM metadata WHERE key=?", (key,))
        return decode(rows[0]["value"], default) if rows else default

    @staticmethod
    def set_metadata(connection: sqlite3.Connection, key: str, value: Any) -> None:
        connection.execute(
            "INSERT INTO metadata(key,value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, encode(value))
        )

    @staticmethod
    def activity(connection: sqlite3.Connection, kind: str, title: str, at: str,
                 symbol: str | None = None) -> None:
        connection.execute(
            "INSERT INTO activity(kind,symbol,title,at) VALUES(?,?,?,?)",
            (kind, symbol, title, at),
        )
