from __future__ import annotations
import json, sqlite3, time
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlparse

class Database:
    def __init__(self, url: str):
        self.url=url
        self.kind="postgres" if url.startswith(("postgres://","postgresql://")) else "sqlite"
        if self.kind=="sqlite":
            raw=url.replace("sqlite:///","",1)
            self.path=Path(raw)
            self.path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def connect(self):
        if self.kind=="sqlite":
            conn=sqlite3.connect(self.path, timeout=30)
            conn.row_factory=sqlite3.Row
        else:
            try:
                import psycopg
            except ImportError as e:
                raise RuntimeError("PostgreSQL mode requires psycopg[binary]>=3.2") from e
            from psycopg.rows import dict_row
            conn=psycopg.connect(self.url, row_factory=dict_row)
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def execute(self, sql, params=()):
        with self.connect() as c:
            cur=c.cursor()
            cur.execute(sql, params)
            return cur

    def query(self, sql, params=()):
        with self.connect() as c:
            cur=c.cursor()
            cur.execute(sql, params)
            rows=cur.fetchall()
            return [dict(r) if hasattr(r,"keys") else r for r in rows]

    def scalar(self, sql, params=(), default=None):
        with self.connect() as c:
            cur=c.cursor(); cur.execute(sql,params); row=cur.fetchone()
            if not row:
                return default
            if isinstance(row, dict):
                return next(iter(row.values()))
            return row[0]

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
                    for stmt in [x.strip() for x in text.split(";") if x.strip()]:
                        cur.execute(stmt)

    def insert_event(self, table, fields: dict):
        keys=list(fields); vals=[fields[k] for k in keys]
        ph=",".join(["?"]*len(keys)) if self.kind=="sqlite" else ",".join(["%s"]*len(keys))
        sql=f"INSERT INTO {table} ({','.join(keys)}) VALUES ({ph})"
        self.execute(sql, vals)
