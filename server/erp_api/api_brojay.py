# -*- coding: utf-8 -*-
"""브로제이 매출·입장 적재분 읽기 API (읽기 전용 · 배 959). app.py 가 api_*.py 를 자동 등록한다.

  GET /api/brojay/sales?date=2026-09-03            그날 저장된 브로제이 응답 그대로
  GET /api/brojay/sales?from=&to=                  구간 — [{date, data}] 목록
  GET /api/brojay/entries?date= | ?from=&to=       입장(출입) 같은 모양
  GET /api/brojay/health                           kind 별 일수·최근 날짜·마지막 성공/실패

정본은 브로제이 — 응답마다 _source=brojay. 칸 이름은 브로제이가 준 그대로 두고 가공하지 않는다
(대조·집계는 화면 몫). nginx auth_request 뒤에서만 열린다(무쿠키 401).
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common import db  # noqa: E402

SOURCE = "brojay"
KINDS = ("sales", "entries")
KST = timezone(timedelta(hours=9))
router = APIRouter(prefix="/api/brojay")


def _conn():
    try:
        return db.connect(readonly=True)
    except db.Error as e:
        raise HTTPException(503, "DB 열기 실패: %s" % e)


def _range(kind, frm, to):
    conn = _conn()
    with conn:
        rows = conn.execute(
            "SELECT key, data, synced_at FROM brojay_records WHERE tenant_id=%s AND kind=%s AND key BETWEEN %s AND %s"
            " ORDER BY key", (db.TENANT, kind, frm, to)).fetchall()
    conn.close()
    return [{"date": r["key"], "synced_at": r["synced_at"], "data": json.loads(r["data"])} for r in rows]


def _serve(kind, date, frm, to):
    if date:
        got = _range(kind, date, date)
        if not got:
            raise HTTPException(404, "적재된 %s 없음: %s" % (kind, date))
        d = dict(got[0])
        d["_source"] = SOURCE
        return d
    today = datetime.now(KST).strftime("%Y-%m-%d")
    frm, to = frm or today, to or today
    got = _range(kind, frm, to)
    return {"from": frm, "to": to, "count": len(got), "days": got, "_source": SOURCE}


@router.get("/sales")
def sales(date: Optional[str] = None, frm: Optional[str] = Query(None, alias="from"), to: Optional[str] = None):
    return _serve("sales", date, frm, to)


@router.get("/entries")
def entries(date: Optional[str] = None, frm: Optional[str] = Query(None, alias="from"), to: Optional[str] = None):
    return _serve("entries", date, frm, to)


@router.get("/health")
def health():
    try:
        conn = db.connect(readonly=True)
    except db.Error as e:
        return {"ok": False, "detail": "DB 열기 실패: %s" % e, "_source": SOURCE}
    with conn:
        rows = conn.execute(
            "SELECT kind, COUNT(*) c, MIN(key) a, MAX(key) b FROM brojay_records WHERE tenant_id=%s GROUP BY kind",
            (db.TENANT,)).fetchall()
        last, failed = db.meta_get(conn, "brojay_last_sync"), db.meta_get(conn, "brojay_last_failed")
    conn.close()
    by_kind = {r["kind"]: {"days": r["c"], "first": r["a"], "last": r["b"]} for r in rows}
    total = sum(v["days"] for v in by_kind.values())
    return {
        "ok": total > 0 and not failed,
        "days": total,
        "by_kind": {k: by_kind.get(k, {"days": 0, "first": None, "last": None}) for k in KINDS},
        "last_sync_kst": last or "",
        "last_failed_kst": failed or "",
        # 적재가 0이면 이유를 그대로 보여준다 — 화면이 '0건'을 '매출 0원'으로 읽지 않게.
        "detail": "" if total else (failed or "아직 한 번도 적재되지 않음 — 브로제이 API 사양·계정 미수령(배 908)"),
        "_source": SOURCE,
    }
