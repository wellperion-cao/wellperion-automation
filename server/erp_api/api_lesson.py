# -*- coding: utf-8 -*-
"""강습 회원관리 미러 API (읽기 전용 · 배 922 레인 W). app.py 가 api_*.py 를 자동 등록한다.

  GET /api/lesson/stats?type=성인강습&scope=year|all   lesson_stats 응답 그대로
  GET /api/lesson/roster?type=성인강습                 lesson_registered_roster 응답 그대로
  GET /api/lesson/registry?type=성인강습&from=&to=     lesson_registry_list 응답 모양 — 등록일 from~to(기본 오늘 KST) 로 자른 data·count
  GET /api/lesson/health                              미러 건수 · 마지막 동기화
정본은 시트 — 응답마다 _source=sheet-mirror. nginx auth_request 뒤에서만 열린다(무쿠키 401).
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common import db  # noqa: E402

SOURCE = "sheet-mirror"
KST = timezone(timedelta(hours=9))
router = APIRouter(prefix="/api/lesson")


def _get(kind, key):
    try:
        conn = db.connect(readonly=True)
    except db.Error as e:
        raise HTTPException(503, "DB 열기 실패: %s" % e)
    with conn:
        r = conn.execute("SELECT data, synced_at FROM lesson_records WHERE tenant_id=%s AND kind=%s AND key=%s",
                         (db.TENANT, kind, key)).fetchone()
    conn.close()
    if r is None:
        raise HTTPException(404, "미러에 없음: %s %s" % (kind, key))
    d = json.loads(r["data"])
    d["_synced_at"] = r["synced_at"]
    d["_source"] = SOURCE
    return d


@router.get("/stats")
def stats(type: str = "성인강습", scope: str = "year"):
    return _get("stats", type + "|" + ("all" if scope == "all" else "year"))


@router.get("/roster")
def roster(type: str = "성인강습"):
    return _get("roster", type)


def slice_registry(d, frm, to):
    """GAS 와 같은 규칙 — 등록일 앞 10자가 from~to 안이면 남긴다. count 도 다시 센다."""
    rows = [r for r in d.get("data") or [] if frm <= str(r.get("등록일") or "")[:10] <= to]
    d.update({"from": frm, "to": to, "count": len(rows), "data": rows})
    return d


@router.get("/registry")
def registry(type: str = "성인강습", frm: Optional[str] = Query(None, alias="from"), to: Optional[str] = None):
    today = datetime.now(KST).strftime("%Y-%m-%d")
    return slice_registry(_get("registry", type), frm or today, to or today)


@router.get("/health")
def health():
    try:
        conn = db.connect(readonly=True)
    except db.Error as e:
        return {"ok": False, "detail": "DB 열기 실패: %s" % e, "_source": SOURCE}
    with conn:
        rows = conn.execute("SELECT kind, key, data FROM lesson_records WHERE tenant_id=%s ORDER BY kind, key", (db.TENANT,)).fetchall()
        last, failed = db.meta_get(conn, "lesson_last_sync"), db.meta_get(conn, "lesson_last_failed")
    conn.close()
    counts = {}
    for r in rows:
        d = json.loads(r["data"])
        counts[r["kind"] + ":" + r["key"]] = d.get("total") if r["kind"] != "registry" else d.get("count")
    return {"ok": len(rows) == 8, "records": len(rows), "counts": counts, "last_sync_kst": last, "last_failed_kst": failed or "", "_source": SOURCE}


if __name__ == "__main__" and "--selftest" in sys.argv:
    d = slice_registry({"data": [{"등록일": "2026-09-01"}, {"등록일": "2026-09-03T10:00"}, {}]}, "2026-09-03", "2026-09-03")
    assert d["count"] == 1 and d["data"][0]["등록일"].startswith("2026-09-03"), d
    print("selftest ok")
