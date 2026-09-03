# -*- coding: utf-8 -*-
"""종합접수처 미러 API (읽기 전용 · 배 922 · AWS 전환 1호).

sync_reception.py 가 5분마다 떠온 reception_items·lost_found·hold_items 미러를 종합접수처_현황.html 이 쓰는
GAS 응답 모양 그대로 돌려준다 — 화면 코드는 주소만 바꾼다. 쓰기(reg_update·lf_handover·hold_complete…)는 계속 GAS.
app.py 가 같은 폴더의 api_*.py 를 자동 등록한다 — app.py 본문은 건드리지 않는다.
  GET /api/reception/board            reg_board 와 같음 {ok,count,data} + by_status·by_category
  GET /api/reception/lost             lf_list 와 같음 {ok,count,data}
  GET /api/reception/hold             member_hold_intake_list 와 같음 + 행마다 done(hold_done_keys 조인)
  GET /api/reception/scoreboard?period=all|week|month   reg_scoreboard 와 같음 {ok,board}
  GET /api/reception/health           행 수·마지막 동기화
"""
import json
import os
import sys

from fastapi import APIRouter, HTTPException, Query

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # 저장소 server/ = 서버 /srv/erp/
from common import db  # noqa: E402  — DB 를 여는 유일한 자리 · 모든 조회는 tenant_id 로 거른다

SOURCE = "sheet-mirror"
PERIODS = ("all", "week", "month")
router = APIRouter(prefix="/api/reception")


def _open():
    try:
        return db.connect(readonly=True)
    except db.Error as e:
        raise HTTPException(503, "DB 열기 실패: %s" % e)


def _rows(conn, table, order):
    rs = conn.execute("SELECT * FROM %s WHERE tenant_id=%%s ORDER BY %s" % (table, order), (db.TENANT,)).fetchall()
    out = []
    for r in rs:
        d = json.loads(r["data"])
        d["_synced_at"] = r["synced_at"]
        if "done" in r.keys():
            d["done"] = bool(r["done"])
        out.append(d)
    return out


@router.get("/board")
def board():
    conn = _open()
    with conn:
        data = _rows(conn, "reception_items", "created_at DESC, reg_id")   # reg_dashboard 와 같은 정렬(createdAt 최근순)
    by_status, by_cat = {}, {}
    for d in data:
        by_status[d.get("status") or ""] = by_status.get(d.get("status") or "", 0) + 1
        by_cat[d.get("category") or ""] = by_cat.get(d.get("category") or "", 0) + 1
    return {"ok": True, "count": len(data), "data": data, "by_status": by_status, "by_category": by_cat, "_source": SOURCE}


@router.get("/lost")
def lost():
    conn = _open()
    with conn:
        data = _rows(conn, "lost_found", "created_at DESC, found_id")
    return {"ok": True, "count": len(data), "data": data, "_source": SOURCE}


@router.get("/hold")
def hold():
    conn = _open()
    with conn:
        data = _rows(conn, "hold_items", "CAST(intake_row AS INTEGER)")     # GAS 와 같은 시트 행 순서
    return {"ok": True, "count": len(data), "done": sum(1 for d in data if d.get("done")), "data": data, "_source": SOURCE}


@router.get("/scoreboard")
def scoreboard(period: str = Query("month")):
    period = period.strip().lower()
    if period not in PERIODS:
        raise HTTPException(400, "period 는 %s 중 하나" % "/".join(PERIODS))
    conn = _open()
    with conn:
        v = db.meta_get(conn, "reception_scoreboard_" + period)
    d = json.loads(v) if v else {"ok": True, "board": []}
    d["_source"] = SOURCE
    return d


@router.get("/health")
def health():
    conn = _open()
    with conn:
        n = {t: conn.execute("SELECT COUNT(*) FROM %s WHERE tenant_id=%%s" % t, (db.TENANT,)).fetchone()[0]
             for t in ("reception_items", "lost_found", "hold_items")}
        hold_done = conn.execute("SELECT COUNT(*) FROM hold_items WHERE tenant_id=%s AND done", (db.TENANT,)).fetchone()[0]
        meta = dict(conn.execute("SELECT k, v FROM sync_meta WHERE tenant_id=%s AND k LIKE 'reception_last%%'", (db.TENANT,)).fetchall())
    return {"ok": True, "rows": n, "hold_done": hold_done, "last_sync_kst": meta.get("reception_last_sync"),
            "last_failed": meta.get("reception_last_failed") or "", "_source": SOURCE}
