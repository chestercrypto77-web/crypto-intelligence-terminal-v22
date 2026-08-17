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
            conn=psycopg.connect(self.url)
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
            return row[0] if row else default

    def migrate(self):
        schema = Path(__file__).resolve().parents[1]/"migrations"/("001_sqlite.sql" if self.kind=="sqlite" else "001_postgres.sql")
        text=schema.read_text(encoding="utf-8")
        with self.connect() as c:
            if self.kind=="sqlite":
                c.executescript(text)
            else:
                cur=c.cursor()
                for stmt in [x.strip() for x in text.split(";") if x.strip()]:
                    cur.execute(stmt)

    def insert_event(self, table, fields: dict):
        keys=list(fields); vals=[fields[k] for k in keys]
        ph=",".join(["?"]*len(keys)) if self.kind=="sqlite" else ",".join(["%s"]*len(keys))
        sql=f"INSERT INTO {table} ({','.join(keys)}) VALUES ({ph})"
        self.execute(sql, vals)
