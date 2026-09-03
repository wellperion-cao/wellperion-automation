# -*- coding: utf-8 -*-
"""웰페리온 ERP 서버 DB 접속 — 코드 전체에서 DB 를 여는 단 하나의 자리 (장기 결정 2·3 · 2026-09-03).

connect()  ERP_DB_URL(postgresql://erp:***@127.0.0.1/erp) 로 PostgreSQL 에 붙는다. 환경변수가 없으면
           /srv/erp/db.env 한 줄을 읽고, 그래도 없으면 명확한 오류. SQLite 폴백 없음.
TENANT     모든 표의 tenant_id 값. 지금은 'wellperion' 하나(배101 SaaS 전환 때 요청별로 바뀐다).
Conn       sqlite3.Connection 흉내 — execute()/executemany()/with(커밋·롤백)/close(). 호출부 diff 를 줄이려는 얇은 껍데기.
           행은 DictRow(r["col"]·r[0]·keys() 다 된다). 자리표시자는 %s.
init_schema(conn)  schema.sql 적용(멱등). meta_set(conn,k,v)  sync_meta upsert.

RDS 로 옮길 때 = db.env 의 ERP_DB_URL 한 줄만 바꾼다. 파이썬 3.9.
"""
import os

import psycopg2
import psycopg2.extras

Error = psycopg2.Error
IntegrityError = psycopg2.IntegrityError
TENANT = "wellperion"
ENV_FILE = os.environ.get("ERP_DB_ENV", "/srv/erp/db.env")
SCHEMA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schema.sql")


def _url():
    url = os.environ.get("ERP_DB_URL")
    if not url:
        try:
            with open(ENV_FILE, encoding="utf-8") as f:
                for line in f:
                    if line.startswith("ERP_DB_URL="):
                        url = line.split("=", 1)[1].strip().strip('"').strip("'")
        except OSError:
            pass
    if not url:
        raise RuntimeError("ERP_DB_URL 없음 — 환경변수 또는 %s 를 확인" % ENV_FILE)
    return url


class Conn:
    def __init__(self, raw):
        self.raw = raw

    def execute(self, sql, args=()):
        cur = self.raw.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute(sql, args)
        return cur

    def executemany(self, sql, seq):
        with self.raw.cursor() as cur:
            cur.executemany(sql, seq)

    def __enter__(self):
        return self

    def __exit__(self, *exc):          # 정상 종료 = 커밋 · 예외 = 롤백 · 연결은 유지(sqlite 와 같은 뜻)
        return self.raw.__exit__(*exc)

    def close(self):
        self.raw.close()


def connect(readonly=False):
    raw = psycopg2.connect(_url())
    if readonly:                        # 읽기 전용 API 는 미러를 못 건드리게 세션에 못을 박는다
        raw.set_session(readonly=True)
    return Conn(raw)


def init_schema(conn):
    with open(SCHEMA_FILE, encoding="utf-8") as f:
        with conn:
            conn.execute(f.read())


def meta_set(conn, k, v):
    conn.execute("INSERT INTO sync_meta (tenant_id, k, v) VALUES (%s, %s, %s)"
                 " ON CONFLICT (tenant_id, k) DO UPDATE SET v = EXCLUDED.v", (TENANT, k, v))


def meta_get(conn, k):
    r = conn.execute("SELECT v FROM sync_meta WHERE tenant_id=%s AND k=%s", (TENANT, k)).fetchone()
    return r[0] if r else None
