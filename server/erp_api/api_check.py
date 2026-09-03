# -*- coding: utf-8 -*-
"""점검 미러 읽기 라우트 (읽기 전용 · 배 922 레인 S).

check_records(sync_check.py 가 5분마다 점검 GAS 응답을 그대로 떠온 것)를 GAS 와 같은 모양으로 돌려준다.
  /api/check/{dept}/today?date=   시설: {ok,key,board} 그대로 · 지원: today_live + ledger{m,f} · 주차: ledger{m}
  /api/check/{dept}/monthly?month=  monthly_report 응답 그대로
  /api/check/health                 부서·종류별 건수 + 오늘 시설 회차 수 + 마지막 동기화
미러에 없는 날짜·월은 404 — 화면은 404 를 받으면 종전 GAS 로 돌아간다(30일 밖은 GAS 가 정본).
app.py 가 같은 폴더의 api_*.py 를 자동 등록한다 — app.py 본문은 건드리지 않는다.

자체점검: python3 api_check.py --selftest (같은 DB 의 tenant 'selftest' · 네트워크 없음)
"""
import json
import os
import sys
from contextlib import closing
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # 저장소 server/ = 서버 /srv/erp/
from common import db  # noqa: E402  — DB 를 여는 유일한 자리 · 모든 조회는 tenant_id 로 거른다

SOURCE = "sheet-mirror"
KST = timezone(timedelta(hours=9))
DEPTS = ("facility", "support", "parking")
router = APIRouter(prefix="/api/check")


def _conn():
    try:
        return db.connect(readonly=True)
    except db.Error as e:
        raise HTTPException(503, "DB 열기 실패: %s" % e)


def _dept(dept):
    if dept not in DEPTS:
        raise HTTPException(404, "부서 없음: %s" % dept)
    return dept


def _get(conn, dept, kind, key):
    r = conn.execute("SELECT data, synced_at FROM check_records WHERE tenant_id=%s AND dept=%s AND kind=%s AND key=%s",
                     (db.TENANT, dept, kind, key)).fetchone()
    return (json.loads(r["data"]), r["synced_at"]) if r else (None, None)


def _today_payload(conn, dept, d):
    """부서별 '오늘' 묶음. 하나도 없으면 None."""
    if dept == "facility":
        board, at = _get(conn, dept, "board", d)
        if board is None:
            return None
        return dict(board, date=d, synced_at=at, _source=SOURCE)
    genders = ("m", "f") if dept == "support" else ("m",)
    ledger, at = {}, None
    for g in genders:
        v, at_g = _get(conn, dept, "ledger", "%s|%s" % (d, g))
        if v is not None:
            ledger[g] = v
            at = at or at_g
    live = _get(conn, dept, "today_live", d)[0] if dept == "support" else None
    if not ledger and live is None:
        return None
    return {"ok": True, "dept": dept, "date": d, "ledger": ledger, "today_live": live, "synced_at": at, "_source": SOURCE}


@router.get("/health")
def health():
    conn = _conn()
    with closing(conn):
        rows = conn.execute("SELECT dept, kind, COUNT(*) c FROM check_records WHERE tenant_id=%s GROUP BY dept, kind",
                            (db.TENANT,)).fetchall()
        meta = dict(conn.execute("SELECT k, v FROM sync_meta WHERE tenant_id=%s AND k LIKE 'check_%%'", (db.TENANT,)).fetchall())
        today = datetime.now(KST).strftime("%Y-%m-%d")
        board, _ = _get(conn, "facility", "board", today)
    subs = (((board or {}).get("board") or {}).get("store") or {}).get("submissions") or []
    return {"ok": True, "rows": sum(r["c"] for r in rows),
            "by_dept": {"%s/%s" % (r["dept"], r["kind"]): r["c"] for r in rows},
            "today": today, "facility_today_sessions": len(subs),
            "last_sync_kst": meta.get("check_last_sync"), "last_failed": meta.get("check_last_failed") or "",
            "_source": SOURCE}


@router.get("/{dept}/today")
def today(dept: str, date: Optional[str] = None):
    d = date or datetime.now(KST).strftime("%Y-%m-%d")
    conn = _conn()
    with closing(conn):
        out = _today_payload(conn, _dept(dept), d)
    if out is None:
        raise HTTPException(404, "미러에 없는 날짜: %s %s" % (dept, d))
    return out


@router.get("/{dept}/monthly")
def monthly(dept: str, month: Optional[str] = None):
    m = month or datetime.now(KST).strftime("%Y-%m")
    conn = _conn()
    with closing(conn):
        data, at = _get(conn, _dept(dept), "monthly", m)
    if data is None:
        raise HTTPException(404, "미러에 없는 월: %s %s" % (dept, m))
    return dict(data, synced_at=at, _source=SOURCE)


# ── 자체점검 ──────────────────────────────────────────────────────────────

def selftest():
    db.TENANT = "selftest"                      # 같은 DB · 다른 tenant — 실데이터는 한 줄도 안 건드린다
    c = db.connect()
    d = datetime.now(KST).strftime("%Y-%m-%d")
    rows = [("facility", "board", d, {"ok": True, "key": "FACILITY_CHECK_" + d, "board": {"store": {"submissions": [{"seq": 1}, {"seq": 2}]}}}),
            ("support", "ledger", d + "|m", {"date": d, "rows": [1], "checkedLedger": {}}),
            ("support", "today_live", d, {"ok": True, "total": 30, "done": 12}),
            ("parking", "ledger", d + "|m", {"date": d, "rows": []}),
            ("support", "monthly", d[:7], {"ok": True, "dept": "support", "issues": {"list": []}})]
    try:
        with c:
            c.execute("DELETE FROM check_records WHERE tenant_id=%s", (db.TENANT,))
            c.executemany("INSERT INTO check_records (tenant_id,dept,kind,key,data,synced_at) VALUES (%s,%s,%s,%s,%s,'t')",
                          [(db.TENANT, a, b, k, json.dumps(v)) for a, b, k, v in rows])
        f = today("facility")
        assert len(f["board"]["store"]["submissions"]) == 2 and f["key"] == "FACILITY_CHECK_" + d, f
        s = today("support")
        assert set(s["ledger"]) == {"m"} and s["today_live"]["done"] == 12, s
        assert today("parking")["ledger"]["m"]["rows"] == []
        assert monthly("support")["dept"] == "support"
        for fn, args in ((today, ("facility", "1999-01-01")), (monthly, ("facility", d[:7])), (today, ("nope",))):
            try:
                fn(*args)
                raise AssertionError("404 이어야: %s" % (args,))
            except HTTPException as e:
                assert e.status_code == 404
        h = health()
        assert h["facility_today_sessions"] == 2 and h["rows"] == 5, h
    finally:
        with c:
            c.execute("DELETE FROM check_records WHERE tenant_id=%s", (db.TENANT,))
        c.close()
    print("selftest ok")
    return 0


if __name__ == "__main__":
    sys.exit(selftest() if "--selftest" in sys.argv else 2)
