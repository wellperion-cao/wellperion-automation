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


# ── 회원 미러 (sync_members.py · 배 931) ─────────────────────────────────────
# members 표도 읽기 전용. 열쇠 = 회원번호(M00001…). 개인정보가 들어 있으므로 nginx auth_request 뒤에서만.
MEMBER_SCOPES = ("valid", "ended", "corp", "archive")
# 문의 표의 전화는 시트 원문("010-1234-5678")이라 조인 때 숫자만 남겨 비교한다.
_INQ_PHONE = "REPLACE(REPLACE(REPLACE(phone,'-',''),' ',''),'.','')"


def _member_row(r):
    d = json.loads(r["data"])
    d["_member_no"] = r["member_no"]
    d["_scope"] = r["scope"]
    d["_phone"] = r["phone"]
    d["_synced_at"] = r["synced_at"]
    d["_source"] = SOURCE
    return d


def _open():
    try:
        return _conn()
    except sqlite3.Error as e:
        raise HTTPException(503, "DB 열기 실패: %s" % e)


@app.get("/api/members/summary")
def members_summary():
    conn = _open()
    with conn:
        rows = conn.execute("SELECT scope, COUNT(*) c FROM members GROUP BY scope").fetchall()
        meta = dict(conn.execute("SELECT k, v FROM sync_meta WHERE k LIKE 'members_%'").fetchall())
    by_scope = {s: 0 for s in MEMBER_SCOPES}
    by_scope.update({r["scope"]: r["c"] for r in rows})
    return {
        "ok": True,
        "rows": sum(by_scope.values()),
        "by_scope": by_scope,
        "last_sync_kst": meta.get("members_last_sync"),
        "last_failed": meta.get("members_last_failed") or "",
        "unnumbered": int(meta.get("members_unnumbered") or 0),
        "collisions": int(meta.get("members_collisions") or 0),  # 같은 회원번호가 두 scope 에 — 등기부 충돌
        "_source": SOURCE,
    }


@app.get("/api/members")
def members(
    scope: Optional[str] = None,          # valid · ended · corp · archive
    q: Optional[str] = None,              # 이름 부분일치 또는 전화 숫자 부분일치(뒷자리)
    limit: int = Query(100, ge=1, le=1000),
    cursor: Optional[str] = None,         # 직전 응답의 next_cursor(회원번호) — 그 다음부터
):
    where, args = [], []
    if scope:
        if scope not in MEMBER_SCOPES:
            raise HTTPException(400, "scope 는 %s 중 하나" % "/".join(MEMBER_SCOPES))
        where.append("scope = ?")
        args.append(scope)
    if q:
        digits = "".join(ch for ch in q if ch.isdigit())
        if digits and digits == q.strip():
            where.append("phone LIKE ?")
            args.append("%" + digits)
        else:
            where.append("name LIKE ?")
            args.append("%" + q.strip() + "%")
    cnt_sql = "SELECT COUNT(*) FROM members" + (" WHERE " + " AND ".join(where) if where else "")
    cnt_args = list(args)
    if cursor:
        where.append("member_no > ?")
        args.append(cursor)
    sql = "SELECT * FROM members" + (" WHERE " + " AND ".join(where) if where else "")
    sql += " ORDER BY member_no LIMIT ?"
    conn = _open()
    with conn:
        total = conn.execute(cnt_sql, cnt_args).fetchone()[0]
        rows = conn.execute(sql, args + [limit]).fetchall()
    return {"total": total, "count": len(rows), "limit": limit,
            "next_cursor": rows[-1]["member_no"] if len(rows) == limit else None,
            "rows": [_member_row(r) for r in rows], "_source": SOURCE}


@app.get("/api/members/{member_no}")
def member(member_no: str):
    """회원 한 사람 + 같은 전화·이름의 문의(정의서 2장 규칙: 전화(정규화)+이름 정확 일치만 '확정').
    전화만 같고 이름이 다른 문의는 합치지 않고 candidates 건수로만 알린다(가족 공유번호·양도 실재)."""
    conn = _open()
    with conn:
        r = conn.execute("SELECT * FROM members WHERE member_no = ?", (member_no.upper(),)).fetchone()
        if r is None:
            raise HTTPException(404, "없는 회원번호")
        inq, cand = [], 0
        if r["phone"]:
            inq = conn.execute(
                "SELECT * FROM inquiries WHERE %s = ? AND name = ? ORDER BY timestamp DESC" % _INQ_PHONE,
                (r["phone"], r["name"])).fetchall()
            cand = conn.execute(
                "SELECT COUNT(*) FROM inquiries WHERE %s = ? AND name <> ?" % _INQ_PHONE,
                (r["phone"], r["name"])).fetchone()[0]
    d = _member_row(r)
    d["inquiries"] = [_row(x) for x in inq]
    d["inquiry_count"] = len(inq)
    d["candidates"] = cand
    return d


# 매출회원현황보고 2페이지 집계 라우트(/api/report/…) — 배 943 · 본문은 members_report.py
from members_report import router as _mr; app.include_router(_mr)  # noqa: E402,E702
