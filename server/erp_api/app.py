# -*- coding: utf-8 -*-
"""웰페리온 문의 미러 API (읽기 전용).

PostgreSQL(common/db.py · ERP_DB_URL) 의 inquiries·members 미러를 읽는다. 쓰기 경로 없음 — 정본은 여전히 구글 시트이고
이 API 는 sync_inquiries.py 가 5분마다 떠온 미러다. 그래서 모든 응답에 _source=sheet-mirror 를 박는다.
nginx 가 앞에서 auth_request 로 로그인 쿠키를 검사하므로 여기서 인증을 다시 하지 않는다.
"""
import json
import os
import sys
from typing import Optional

from fastapi import FastAPI, HTTPException, Query

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # 저장소 server/ = 서버 /srv/erp/
from common import db  # noqa: E402  — DB 를 여는 유일한 자리 · 모든 조회는 tenant_id 로 거른다

SOURCE = "sheet-mirror"

app = FastAPI(title="Wellperion inquiry mirror API", docs_url=None, redoc_url=None)


def _conn():
    # 읽기 전용으로 연다 — 이 프로세스가 미러를 건드릴 수 없게 못을 박는다.
    return db.connect(readonly=True)


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
    except db.Error as e:
        return {"ok": False, "detail": "DB 열기 실패: %s" % e, "_source": SOURCE}
    with conn:
        rows = conn.execute("SELECT type, COUNT(*) c FROM inquiries WHERE tenant_id=%s GROUP BY type", (db.TENANT,)).fetchall()
        meta = dict(conn.execute("SELECT k, v FROM sync_meta WHERE tenant_id=%s", (db.TENANT,)).fetchall())
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
    where, args = ["tenant_id = %s"], [db.TENANT]
    if type:
        where.append("type = %s")
        args.append(type)
    if since:
        where.append("timestamp >= %s")
        args.append(since)
    sql = "SELECT * FROM inquiries WHERE " + " AND ".join(where)
    cnt = "SELECT COUNT(*) FROM inquiries WHERE " + " AND ".join(where)
    sql += " ORDER BY timestamp DESC, id LIMIT %s OFFSET %s"
    try:
        conn = _conn()
    except db.Error as e:
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
    except db.Error as e:
        raise HTTPException(503, "DB 열기 실패: %s" % e)
    with conn:
        r = conn.execute("SELECT * FROM inquiries WHERE tenant_id = %s AND id = %s", (db.TENANT, item_id)).fetchone()
    if r is None:
        raise HTTPException(404, "없는 문의 id")
    return _row(r)


# ── 회원 미러 (sync_members.py · 배 931) ─────────────────────────────────────
# members 표도 읽기 전용. 열쇠 = 회원번호(M00001…). 개인정보가 들어 있으므로 nginx auth_request 뒤에서만.
MEMBER_SCOPES = ("valid", "ended", "corp", "archive")
# 한 회원번호가 여러 scope 에 있을 때(같은 사람의 이력) 대표는 valid — 이 순서로 고른다.
_SCOPE_ORDER = "CASE scope WHEN 'valid' THEN 0 WHEN 'ended' THEN 1 WHEN 'corp' THEN 2 ELSE 3 END"
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
    except db.Error as e:
        raise HTTPException(503, "DB 열기 실패: %s" % e)


@app.get("/api/members/summary")
def members_summary():
    conn = _open()
    with conn:
        rows = conn.execute("SELECT scope, COUNT(*) c FROM members WHERE tenant_id=%s GROUP BY scope", (db.TENANT,)).fetchall()
        meta = dict(conn.execute("SELECT k, v FROM sync_meta WHERE tenant_id=%s AND k LIKE 'members_%%'", (db.TENANT,)).fetchall())
    by_scope = {s: 0 for s in MEMBER_SCOPES}
    by_scope.update({r["scope"]: r["c"] for r in rows})
    return {
        "ok": True,
        "rows": sum(by_scope.values()),
        "by_scope": by_scope,
        "last_sync_kst": meta.get("members_last_sync"),
        "last_failed": meta.get("members_last_failed") or "",
        "unnumbered": int(meta.get("members_unnumbered") or 0),
        "collisions": int(meta.get("members_collisions") or 0),    # 같은 번호·다른 사람 — 등기부 충돌
        "multi_scope": int(meta.get("members_multi_scope") or 0),  # 같은 번호·같은 사람이 여러 scope 에 — 이력(정상)
        "_source": SOURCE,
    }


@app.get("/api/members")
def members(
    scope: Optional[str] = None,          # valid · ended · corp · archive
    q: Optional[str] = None,              # 이름 부분일치 또는 전화 숫자 부분일치(뒷자리)
    limit: int = Query(100, ge=1, le=1000),
    cursor: Optional[str] = None,         # 직전 응답의 next_cursor("회원번호|scope") — 그 다음부터
):
    where, args = ["tenant_id = %s"], [db.TENANT]
    if scope:
        if scope not in MEMBER_SCOPES:
            raise HTTPException(400, "scope 는 %s 중 하나" % "/".join(MEMBER_SCOPES))
        where.append("scope = %s")
        args.append(scope)
    if q:
        digits = "".join(ch for ch in q if ch.isdigit())
        if digits and digits == q.strip():
            where.append("phone LIKE %s")
            args.append("%" + digits)
        else:
            where.append("name LIKE %s")
            args.append("%" + q.strip() + "%")
    cnt_sql = "SELECT COUNT(*) FROM members WHERE " + " AND ".join(where)
    cnt_args = list(args)
    if cursor:
        no, _, sc = cursor.partition("|")
        where.append("(member_no, scope) > (%s, %s)")
        args += [no, sc]
    sql = "SELECT * FROM members WHERE " + " AND ".join(where)
    sql += " ORDER BY member_no, scope LIMIT %s"
    conn = _open()
    with conn:
        total = conn.execute(cnt_sql, cnt_args).fetchone()[0]
        rows = conn.execute(sql, args + [limit]).fetchall()
    return {"total": total, "count": len(rows), "limit": limit,
            "next_cursor": "%s|%s" % (rows[-1]["member_no"], rows[-1]["scope"]) if len(rows) == limit else None,
            "rows": [_member_row(r) for r in rows], "_source": SOURCE}


@app.get("/api/members/{member_no}")
def member(member_no: str):
    """회원 한 사람 + 같은 전화·이름의 문의(정의서 2장 규칙: 전화(정규화)+이름 정확 일치만 '확정').
    전화만 같고 이름이 다른 문의는 합치지 않고 candidates 건수로만 알린다(가족 공유번호·양도 실재).
    같은 번호가 여러 scope 에 있으면 valid 가 대표, 나머지는 scopes 배열(이력)."""
    conn = _open()
    with conn:
        rs = conn.execute("SELECT * FROM members WHERE tenant_id = %s AND member_no = %s ORDER BY " + _SCOPE_ORDER,
                          (db.TENANT, member_no.upper())).fetchall()
        if not rs:
            raise HTTPException(404, "없는 회원번호")
        r = rs[0]
        inq, cand = [], 0
        if r["phone"]:
            inq = conn.execute(
                "SELECT * FROM inquiries WHERE tenant_id = %s AND " + _INQ_PHONE + " = %s AND name = %s ORDER BY timestamp DESC",
                (db.TENANT, r["phone"], r["name"])).fetchall()
            cand = conn.execute(
                "SELECT COUNT(*) FROM inquiries WHERE tenant_id = %s AND " + _INQ_PHONE + " = %s AND name <> %s",
                (db.TENANT, r["phone"], r["name"])).fetchone()[0]
    d = _member_row(r)
    d["scopes"] = [_member_row(x) for x in rs[1:]]
    d["inquiries"] = [_row(x) for x in inq]
    d["inquiry_count"] = len(inq)
    d["candidates"] = cand
    return d


# 매출회원현황보고 2페이지 집계 라우트(/api/report/…) — 배 943 · 본문은 members_report.py
from members_report import router as _mr; app.include_router(_mr)  # noqa: E402,E702

# 모듈별 라우터 자동 등록 — 같은 폴더의 api_*.py 에 `router` 가 있으면 붙인다(2026-09-03 시토).
#   접수·점검·업무 SSOT 처럼 도메인마다 파일 하나씩 두고, 이 파일(app.py)은 손대지 않는다(레인 충돌 방지).
import glob as _glob, importlib as _il, os as _os  # noqa: E402
for _f in sorted(_glob.glob(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "api_*.py"))):
    _m = _il.import_module(_os.path.basename(_f)[:-3])
    if hasattr(_m, "router"):
        app.include_router(_m.router)
