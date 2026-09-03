# -*- coding: utf-8 -*-
"""웰페리온 문의 미러 API (읽기 전용).

/srv/erp/erp.db 의 inquiries 테이블만 읽는다. 쓰기 경로 없음 — 정본은 여전히 구글 시트이고
이 API 는 sync_inquiries.py 가 5분마다 떠온 미러다. 그래서 모든 응답에 _source=sheet-mirror 를 박는다.
nginx 가 앞에서 auth_request 로 로그인 쿠키를 검사하므로 여기서 인증을 다시 하지 않는다.
"""
import json
import os
import sqlite3
from typing import Optional

from fastapi import FastAPI, HTTPException, Query

DB_PATH = os.environ.get("ERP_DB", "/srv/erp/erp.db")
SOURCE = "sheet-mirror"

app = FastAPI(title="Wellperion inquiry mirror API", docs_url=None, redoc_url=None)


def _conn():
    # 읽기 전용으로 연다 — 이 프로세스가 미러를 건드릴 수 없게 못을 박는다.
    conn = sqlite3.connect("file:%s?mode=ro" % DB_PATH, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _row(r):
    d = json.loads(r["data"])
    d["_id"] = r["id"]
    d["_type"] = r["type"]
    d["_synced_at"] = r["synced_at"]
    d["_source"] = SOURCE
    return d


@app.get("/api/health")
def health():
    try:
        conn = _conn()
    except sqlite3.Error as e:
        return {"ok": False, "detail": "DB 열기 실패: %s" % e, "_source": SOURCE}
    with conn:
        rows = conn.execute("SELECT type, COUNT(*) c FROM inquiries GROUP BY type").fetchall()
        meta = dict(conn.execute("SELECT k, v FROM sync_meta").fetchall())
    by_type = {r["type"]: r["c"] for r in rows}
    return {
        "ok": True,
        "rows": sum(by_type.values()),
        "by_type": by_type,
        "last_sync_kst": meta.get("last_sync"),
        "last_failed": meta.get("last_failed") or "",
        "_source": SOURCE,
    }


@app.get("/api/inquiries")
def inquiries(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    since: Optional[str] = None,   # timestamp 하한 (예 2026-08-01) — 문자열 비교(ISO 라 순서 보존)
    type: Optional[str] = None,    # 멤버십 · 성인강습 · 유소년강습
):
    where, args = [], []
    if type:
        where.append("type = ?")
        args.append(type)
    if since:
        where.append("timestamp >= ?")
        args.append(since)
    sql = "SELECT * FROM inquiries"
    cnt = "SELECT COUNT(*) FROM inquiries"
    if where:
        sql += " WHERE " + " AND ".join(where)
        cnt += " WHERE " + " AND ".join(where)
    sql += " ORDER BY timestamp DESC, id LIMIT ? OFFSET ?"
    try:
        conn = _conn()
    except sqlite3.Error as e:
        raise HTTPException(503, "DB 열기 실패: %s" % e)
    with conn:
        total = conn.execute(cnt, args).fetchone()[0]
        rows = conn.execute(sql, args + [limit, offset]).fetchall()
    return {"total": total, "count": len(rows), "limit": limit, "offset": offset,
            "rows": [_row(r) for r in rows], "_source": SOURCE}


@app.get("/api/inquiries/{item_id:path}")
def inquiry(item_id: str):
    try:
        conn = _conn()
    except sqlite3.Error as e:
        raise HTTPException(503, "DB 열기 실패: %s" % e)
    with conn:
        r = conn.execute("SELECT * FROM inquiries WHERE id = ?", (item_id,)).fetchone()
    if r is None:
        raise HTTPException(404, "없는 문의 id")
    return _row(r)
