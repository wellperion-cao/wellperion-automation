# -*- coding: utf-8 -*-
"""매출·지출 집계 거울 API (읽기 · 배 960 레인 E). sync_sales.py 가 떠온 sales_cache 를 GAS 응답 모양 그대로 돌려준다.
  GET /api/sales/{gas}/{action}?<GAS 와 같은 쿼리>
      salesops  sales_dept_pub · sales_instr_pub(&month=) · sales_month · sales_ops · sales_dept · labor_time
      proc      sales_instr_pub(&month=) · proc_summary · sales_dept
      deptrep   dump(&sheet=&range=) · lesson
  GET /api/sales/sheet/{key}   key=labor|expense — sync_sheet.py 가 뜬 gviz 시트 거울(배12615 · CFO 요청서3 §1)
  GET /api/sales/health
거울에 없는 열쇠(예: 화면이 고른 옛 날짜탭)는 그 자리에서 GAS 1회 호출해 채운다 — 첫 조회만 느리고 이후는 서버.
매출 수치는 개인정보가 아니지만 /api 는 로그인 관문 뒤다(app.py 기본). 화면은 ERP 도메인에서만 이 주소를 먼저 부르고
실패하면 종전 GAS 로 조용히 돌아간다. 응답 키는 GAS 와 같고 _source·_synced_at 만 덧붙는다.
app.py 가 같은 폴더의 api_*.py 를 자동 등록한다 — app.py 본문은 건드리지 않는다.

자체점검: python3 api_sales.py --selftest  (같은 DB 의 tenant 'selftest' · 네트워크 없음)
"""
import json
import os
import sys

from fastapi import APIRouter, HTTPException, Request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sync_sales import ACTIONS, _kst_now, db, gas_call, key_of, load_env, report_file, store  # noqa: E402
from sync_sheet import GAS as SHEET_GAS, SHEETS as SHEET_DEFS, gviz_fetch  # noqa: E402

SOURCE = "sheet-mirror"
router = APIRouter(prefix="/api/sales")
load_env()


@router.get("/health")
def health():
    conn = db.connect(readonly=True)
    with conn:
        rows = conn.execute("SELECT gas, action, COUNT(*) c, MAX(synced_at) s FROM sales_cache WHERE tenant_id=%s"
                            " GROUP BY gas, action", (db.TENANT,)).fetchall()
        meta = dict(conn.execute("SELECT k, v FROM sync_meta WHERE tenant_id=%s AND k LIKE 'sales_last%%'", (db.TENANT,)).fetchall())
    conn.close()
    return {"ok": True, "rows": sum(r["c"] for r in rows),
            "actions": {"%s/%s" % (r["gas"], r["action"]): {"count": r["c"], "synced_at": r["s"]} for r in rows},
            "last_sync_kst": meta.get("sales_last_sync"), "last_failed": meta.get("sales_last_failed") or "", "_source": SOURCE}


@router.get("/sheet/{key}")
def sales_sheet(key: str):
    """gviz 시트 거울 — GET /api/sales/sheet/labor|expense. 응답 = sync_sheet.gviz_fetch 와 같은 gviz 모양
    (`{"table":{"cols":...,"rows":...}}` 그대로) + _source·_synced_at. 이 주소도 `/{gas}/{action}` 보다
    먼저 등록해야 매칭된다(FastAPI 는 등록 순서대로 본다) — 아래 generic 라우트 위에 둔다."""
    if key not in SHEET_DEFS:
        raise HTTPException(404, "모르는 시트: %s" % key)
    conn = db.connect()
    with conn:
        r = conn.execute("SELECT data, synced_at FROM sales_cache WHERE tenant_id=%s AND gas=%s AND action=%s AND params=%s",
                         (db.TENANT, SHEET_GAS, key, key_of({}))).fetchone()
    if r:
        data, synced = json.loads(r["data"]), r["synced_at"]
    else:                                                     # 거울 없음 → gviz 1회(느림) → 저장
        data = gviz_fetch(key)
        if data is None:
            conn.close()
            raise HTTPException(502, "시트 조회 실패: %s" % key)
        synced = _kst_now()
        store(conn, SHEET_GAS, key, {}, data, synced)
    conn.close()
    data["_source"], data["_synced_at"] = SOURCE, synced
    return data


@router.get("/{gas}/{action}")
def sales(gas: str, action: str, request: Request):
    if action not in ACTIONS.get(gas, ()):
        raise HTTPException(404, "모르는 액션: %s/%s" % (gas, action))
    params = dict(request.query_params)
    conn = db.connect()
    with conn:
        r = conn.execute("SELECT data, synced_at FROM sales_cache WHERE tenant_id=%s AND gas=%s AND action=%s AND params=%s",
                         (db.TENANT, gas, action, key_of(params))).fetchone()
    if r:
        data, synced = json.loads(r["data"]), r["synced_at"]
    else:                                                     # 거울 없음 → GAS 1회(느림) → 저장
        if gas == "deptrep":
            fid = report_file()
            if fid:
                params = dict(params, file=fid)
        data = gas_call(gas, action, params)
        if data is None:
            conn.close()
            raise HTTPException(502, "GAS 조회 실패: %s/%s" % (gas, action))
        synced = _kst_now()
        store(conn, gas, action, params, data, synced)
    conn.close()
    data["_source"], data["_synced_at"] = SOURCE, synced
    return data


# ── 자체점검 ──────────────────────────────────────────────────────────────

def selftest():
    db.TENANT = "selftest"                      # 같은 DB · 다른 tenant — 실데이터는 한 줄도 안 건드린다
    conn = db.connect()
    db.init_schema(conn)

    class _Req:                                 # FastAPI Request 대역 — 쿼리만 쓴다
        def __init__(self, q):
            self.query_params = q
    try:
        with conn:
            conn.execute("DELETE FROM sales_cache WHERE tenant_id=%s", (db.TENANT,))
        store(conn, "salesops", "sales_dept_pub", {}, {"ok": True, "dept": {"P.T": [1, 2]}}, "t0")
        store(conn, "proc", "sales_instr_pub", {"month": 8}, {"ok": True, "month": 8, "instr": [{"name": "가", "val": 5}]}, "t1")
        store(conn, "deptrep", "dump", {"sheet": 4, "range": "A1:S20"}, {"ok": True, "cells": {"J4": "1,000"}}, "t2")
        store(conn, SHEET_GAS, "labor", {}, {"status": "ok", "table": {"rows": [9]}}, "t3")
        d = sales_sheet("labor")                                                   # 배12615 — 시트 거울(거울 있음)
        assert d["table"]["rows"] == [9] and d["_source"] == SOURCE and d["_synced_at"] == "t3", d
        try:
            sales_sheet("nope")
            raise AssertionError("모르는 시트 키는 404 여야 한다")
        except HTTPException as e:
            assert e.status_code == 404
        d = sales("salesops", "sales_dept_pub", _Req({}))
        assert d["dept"]["P.T"] == [1, 2] and d["_source"] == SOURCE and d["_synced_at"] == "t0", d
        d = sales("proc", "sales_instr_pub", _Req({"month": "8", "_pv": "9"}))    # 캐시깨기는 열쇠에서 빠진다
        assert d["instr"][0]["val"] == 5, d
        d = sales("deptrep", "dump", _Req({"range": "A1:S20", "sheet": "4", "cb": "1", "file": "zzz"}))
        assert d["cells"]["J4"] == "1,000", d                                     # 순서·file 이 달라도 같은 행
        for g, a in (("salesops", "nope"), ("nope", "sales_dept_pub"), ("deptrep", "sales_month")):
            try:
                sales(g, a, _Req({}))
                raise AssertionError("404 이어야: %s/%s" % (g, a))
            except HTTPException as e:
                assert e.status_code == 404
        h = health()
        assert h["rows"] == 4 and "proc/sales_instr_pub" in h["actions"], h
    finally:
        with conn:
            conn.execute("DELETE FROM sales_cache WHERE tenant_id=%s", (db.TENANT,))
        conn.close()
    print("selftest ok")
    return 0


if __name__ == "__main__":
    sys.exit(selftest() if "--selftest" in sys.argv else 2)
