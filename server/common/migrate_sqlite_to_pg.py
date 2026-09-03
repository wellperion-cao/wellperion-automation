# -*- coding: utf-8 -*-
"""SQLite(auth.db·erp.db) → PostgreSQL 이관 (멱등 · 건수 출력 · 2026-09-03).

    python3 /srv/erp/common/migrate_sqlite_to_pg.py [--keep]

1) schema.sql 적용  2) users(perms 포함)·inquiries·members·sync_meta 를 그대로 upsert
3) SQLite 파일은 지우지 않고 *.bak-20260903 으로 이름만 바꾼다(--keep 이면 그대로 둠).
되돌리기 = 서비스 env 에서 ERP_DB_URL 제거 + .bak 를 원래 이름으로.
"""
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common import db  # noqa: E402

AUTH_DB = os.environ.get("ERP_AUTH_DB", "/srv/erp/auth.db")
ERP_DB = os.environ.get("ERP_DB", "/srv/erp/erp.db")
BAK = ".bak-20260903"

TABLES = {   # 표 → (SQLite 파일, 충돌 열쇠)
    "users": (AUTH_DB, "id"),
    "inquiries": (ERP_DB, "tenant_id, id"),
    "members": (ERP_DB, "tenant_id, member_no, scope"),
    "sync_meta": (ERP_DB, "tenant_id, k"),
}


def _sqlite_rows(path, table):
    if not os.path.exists(path):
        return None
    c = sqlite3.connect(path)
    c.row_factory = sqlite3.Row
    try:
        if not c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone():
            return None
        return [dict(r) for r in c.execute("SELECT * FROM %s" % table)]
    finally:
        c.close()


def upsert(conn, table, rows, key):
    if not rows:
        return 0
    cols = list(rows[0].keys())
    if "tenant_id" not in cols:
        cols.append("tenant_id")
    sql = "INSERT INTO %s (%s) VALUES (%s) ON CONFLICT (%s) DO UPDATE SET %s" % (
        table, ", ".join(cols), ", ".join(["%s"] * len(cols)), key,
        ", ".join("%s = EXCLUDED.%s" % (c, c) for c in cols if c not in key.replace(" ", "").split(",")))
    with conn:
        conn.executemany(sql, [tuple(dict(r, tenant_id=db.TENANT).get(c) for c in cols) for r in rows])
    return len(rows)


def pg_count(conn, table):
    return conn.execute("SELECT COUNT(*) FROM %s WHERE tenant_id=%%s" % table, (db.TENANT,)).fetchone()[0]


def main():
    keep = "--keep" in sys.argv
    conn = db.connect()
    db.init_schema(conn)
    print("schema 적용 완료")
    for table, (path, key) in TABLES.items():
        rows = _sqlite_rows(path, table)
        if rows is None:
            print("[skip] %s — SQLite 없음(%s)" % (table, path))
            continue
        n = upsert(conn, table, rows, key)
        print("[ok] %-10s sqlite %5d → pg %5d" % (table, n, pg_count(conn, table)))
    with conn:   # users.id 를 직접 넣었으니 시퀀스를 그 뒤로 옮긴다(다음 가입이 충돌하지 않게)
        conn.execute("SELECT setval(pg_get_serial_sequence('users','id'), COALESCE(MAX(id),0)+1, false) FROM users")
    conn.close()
    if not keep:
        for path in {AUTH_DB, ERP_DB}:
            if os.path.exists(path):
                os.rename(path, path + BAK)
                print("[bak] %s → %s" % (path, path + BAK))
    return 0


if __name__ == "__main__":
    sys.exit(main())
