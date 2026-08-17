from __future__ import annotations

import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


@dataclass(frozen=True)
class DatabaseHealth:
    kind: str
    reachable: bool
    server_version: str | None
    pooled_endpoint: bool


def _portable_db_value(value):
    """Normalize driver-specific UUID objects at the storage boundary.

    SQLite returns UUID columns as strings while psycopg/Postgres returns
    ``uuid.UUID`` instances. V22 contracts intentionally use string IDs, so a
    Postgres UUID leaking above this boundary can make ``uuid.UUID(value)`` fail
    with ``AttributeError: 'UUID' object has no attribute 'replace'``.

    Keeping this normalization in the database adapter makes SQLite and Neon
    behave identically without weakening the contract validation itself.
    """
    if isinstance(value, uuid.UUID):
        return str(value)
    return value


def _portable_row(row):
    if isinstance(row, dict):
        return {key: _portable_db_value(value) for key, value in row.items()}
    if hasattr(row, "keys"):
        return {key: _portable_db_value(row[key]) for key in row.keys()}
    return tuple(_portable_db_value(value) for value in row)


class Database:
    """Small SQLite/Postgres boundary used by the V22 Brain.

    Postgres mode is intentionally compatible with Neon/serverless execution:
    connections are short-lived, no process-local pool is required, and the
    connection URL remains entirely environment supplied.
    """

    def __init__(self, url: str, *, connect_timeout_seconds: int = 10):
        self.url = (url or "").strip()
        self.kind = "postgres" if self.url.startswith(("postgres://", "postgresql://")) else "sqlite"
        self.connect_timeout_seconds = max(1, int(connect_timeout_seconds))
        if self.kind == "sqlite":
            raw = self.url.replace("sqlite:///", "", 1)
            self.path = Path(raw)
            self.path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def is_neon(self) -> bool:
        return self.kind == "postgres" and ".neon.tech" in (urlsplit(self.url).hostname or "")

    @property
    def uses_pooled_endpoint(self) -> bool:
        host = urlsplit(self.url).hostname or ""
        return "-pooler." in host

    def _postgres_url(self) -> str:
        """Return DSN with safe serverless defaults without exposing it."""
        parts = urlsplit(self.url)
        query = dict(parse_qsl(parts.query, keep_blank_values=True))
        query.setdefault("connect_timeout", str(self.connect_timeout_seconds))
        if self.is_neon:
            query.setdefault("sslmode", "require")
        return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))

    @contextmanager
    def connect(self):
        if self.kind == "sqlite":
            conn = sqlite3.connect(self.path, timeout=30)
            conn.row_factory = sqlite3.Row
        else:
            try:
                import psycopg
            except ImportError as e:
                raise RuntimeError("PostgreSQL/Neon mode requires psycopg[binary]>=3.2") from e
            from psycopg.rows import dict_row
            conn = psycopg.connect(self._postgres_url(), row_factory=dict_row)
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def execute(self, sql, params=()):
        # Never return a cursor whose connection has already been closed.
        with self.connect() as c:
            cur = c.cursor()
            cur.execute(sql, params)
            return cur.rowcount

    def query(self, sql, params=()):
        with self.connect() as c:
            cur = c.cursor()
            cur.execute(sql, params)
            rows = cur.fetchall()
            return [_portable_row(r) for r in rows]

    def scalar(self, sql, params=(), default=None):
        with self.connect() as c:
            cur = c.cursor()
            cur.execute(sql, params)
            row = cur.fetchone()
            if not row:
                return default
            if isinstance(row, dict):
                return _portable_db_value(next(iter(row.values())))
            return _portable_db_value(row[0])

    def healthcheck(self) -> DatabaseHealth:
        if self.kind == "sqlite":
            value = self.scalar("SELECT sqlite_version()")
        else:
            value = self.scalar("SHOW server_version")
        return DatabaseHealth(
            kind=self.kind,
            reachable=bool(value),
            server_version=str(value) if value is not None else None,
            pooled_endpoint=self.uses_pooled_endpoint,
        )

    def migrate(self):
        migration_dir = Path(__file__).resolve().parents[1] / "migrations"
        suffix = "sqlite.sql" if self.kind == "sqlite" else "postgres.sql"
        schemas = sorted(migration_dir.glob(f"*_{suffix}"))
        if not schemas:
            raise RuntimeError(f"No {self.kind} migrations found in {migration_dir}")
        with self.connect() as c:
            for schema in schemas:
                text = schema.read_text(encoding="utf-8")
                if self.kind == "sqlite":
                    c.executescript(text)
                else:
                    cur = c.cursor()
                    # V22 migrations deliberately avoid procedural blocks; simple
                    # semicolon splitting keeps the deploy package dependency-light.
                    for stmt in [x.strip() for x in text.split(";") if x.strip()]:
                        cur.execute(stmt)

    def insert_event(self, table, fields: dict):
        keys = list(fields)
        vals = [fields[k] for k in keys]
        ph = ",".join(["?"] * len(keys)) if self.kind == "sqlite" else ",".join(["%s"] * len(keys))
        sql = f"INSERT INTO {table} ({','.join(keys)}) VALUES ({ph})"
        self.execute(sql, vals)
