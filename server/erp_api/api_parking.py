# -*- coding: utf-8 -*-
"""주차 매출 원천(랩스 ppark-wall) 적재분 읽기 API (읽기 전용 · 배 2668). app.py 가 api_*.py 를 자동 등록한다.

  GET /api/parking/daily?date=2026-09-14            그날 저장된 원문 + revenue_krw
  GET /api/parking/daily?from=&to=                  구간 — [{date, revenue_krw, raw, synced_at}] + revenue_total_krw
  GET /api/parking/daily?month=YYYY-MM               그 달 전체(from/to 대신)
  GET /api/parking/health                            일수·최근 날짜·마지막 성공/실패

정본은 랩스(ppark-wall) — 칸 이름은 원문 그대로 raw 에 둔다(가공은 화면 몫). revenue_krw 는
sync_parking.PARKING_REVENUE_FIELD 로 뽑은 값이라 그 env 가 비면 항상 null 이다(추정하지 않는다).
nginx auth_request 뒤에서만 열린다(무쿠키 401).
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common import db  # noqa: E402

SOURCE = "parking"
KIND = "daily"
KST = timezone(timedelta(hours=9))
router = APIRouter(prefix="/api/parking")


def _conn():
    try:
        return db.connect(readonly=True)
    except db.Error as e:
        raise HTTPException(503, "DB 열기 실패: %s" % e)


def _month_range(month):
    """'YYYY-MM' → (첫날, 말일). 모양이 아니면 400."""
    try:
        y, m = int(month[:4]), int(month[5:7])
        assert len(month) == 7 and month[4] == "-" and 1 <= m <= 12
    except (ValueError, AssertionError):
        raise HTTPException(400, "month 는 YYYY-MM 모양: %r" % month)
    first = datetime(y, m, 1)
    last = (datetime(y + (m == 12), m % 12 + 1, 1) - timedelta(days=1))
    return first.strftime("%Y-%m-%d"), last.strftime("%Y-%m-%d")


def _row(r):
    d = json.loads(r["data"])
    return {"date": r["key"], "revenue_krw": d.get("revenue_krw"), "raw": d.get("raw"), "synced_at": r["synced_at"]}


def _range(frm, to):
    conn = _conn()
    with conn:
        rows = conn.execute(
            "SELECT key, data, synced_at FROM parking_records WHERE tenant_id=%s AND kind=%s AND key BETWEEN %s AND %s"
            " ORDER BY key", (db.TENANT, KIND, frm, to)).fetchall()
    conn.close()
    return [_row(r) for r in rows]


@router.get("/daily")
def daily(date: Optional[str] = None, frm: Optional[str] = Query(None, alias="from"), to: Optional[str] = None,
          month: Optional[str] = None):
    if month and not date:
        frm, to = _month_range(month)
    if date:
        got = _range(date, date)
        if not got:
            raise HTTPException(404, "적재된 주차 매출 없음: %s" % date)
        d = dict(got[0])
        d["_source"] = SOURCE
        return d
    today = datetime.now(KST).strftime("%Y-%m-%d")
    frm, to = frm or today, to or today
    got = _range(frm, to)
    total = sum(r["revenue_krw"] for r in got if r["revenue_krw"] is not None)
    return {"from": frm, "to": to, "count": len(got), "days": got, "revenue_total_krw": total, "_source": SOURCE}


@router.get("/health")
def health():
    try:
        conn = db.connect(readonly=True)
    except db.Error as e:
        return {"ok": False, "detail": "DB 열기 실패: %s" % e, "_source": SOURCE}
    with conn:
        row = conn.execute(
            "SELECT COUNT(*) c, MIN(key) a, MAX(key) b FROM parking_records WHERE tenant_id=%s AND kind=%s",
            (db.TENANT, KIND)).fetchone()
        last, failed = db.meta_get(conn, "parking_last_sync"), db.meta_get(conn, "parking_last_failed")
    conn.close()
    total = row["c"] or 0
    return {
        "ok": total > 0 and not failed,
        "days": total, "first": row["a"], "last": row["b"],
        "last_sync_kst": last or "", "last_failed_kst": failed or "",
        "detail": "" if total else (failed or "아직 한 번도 적재되지 않음 — parking 계정 미수령(배 2668)"),
        "_source": SOURCE,
    }


def _selfcheck():
    assert _month_range("2026-09") == ("2026-09-01", "2026-09-30")
    assert _month_range("2026-12") == ("2026-12-01", "2026-12-31")
    for bad in ("2026-9", "2026-13", "abcd-ef"):
        try:
            _month_range(bad)
        except HTTPException as e:
            assert e.status_code == 400
        else:
            raise AssertionError("걸렀어야 한다: %r" % bad)
    row = {"key": "2026-09-14", "data": json.dumps({"revenue_krw": 5000, "raw": {"x": 1}}), "synced_at": "t"}
    got = _row(row)
    assert got == {"date": "2026-09-14", "revenue_krw": 5000, "raw": {"x": 1}, "synced_at": "t"}, got
    print("selfcheck ok")


if __name__ == "__main__":
    _selfcheck()
