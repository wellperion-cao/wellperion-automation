# -*- coding: utf-8 -*-
"""카톡전송관리 방 목록 미러 API (읽기 전용 · 배 922 레인 W). app.py 가 api_*.py 를 자동 등록한다.

  GET /api/kakao/rooms    kakao_rooms_get 과 같은 모양 {ok, count, rooms:[{name,prefix}]}
  GET /api/kakao/health   미러 건수 · 마지막 동기화
정본은 시트 — 응답마다 _source=sheet-mirror. nginx auth_request 뒤에서만 열린다(무쿠키 401).
"""
import os
import sys

from fastapi import APIRouter, HTTPException

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common import db  # noqa: E402

SOURCE = "sheet-mirror"
router = APIRouter(prefix="/api/kakao")


def _rows():
    try:
        conn = db.connect(readonly=True)
    except db.Error as e:
        raise HTTPException(503, "DB 열기 실패: %s" % e)
    with conn:
        rows = conn.execute("SELECT name, prefix FROM kakao_rooms WHERE tenant_id=%s ORDER BY ord", (db.TENANT,)).fetchall()
        last, failed = db.meta_get(conn, "kakao_last_sync"), db.meta_get(conn, "kakao_last_failed")
    conn.close()
    return [{"name": r["name"], "prefix": r["prefix"]} for r in rows], last, failed


@router.get("/rooms")
def rooms():
    rs, last, _ = _rows()
    return {"ok": True, "count": len(rs), "rooms": rs, "last_sync_kst": last, "_source": SOURCE}


@router.get("/health")
def health():
    try:
        rs, last, failed = _rows()
    except HTTPException as e:
        return {"ok": False, "detail": e.detail, "_source": SOURCE}
    return {"ok": bool(last), "rows": len(rs), "last_sync_kst": last, "last_failed_kst": failed or "", "_source": SOURCE}
