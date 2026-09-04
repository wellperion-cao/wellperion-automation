# -*- coding: utf-8 -*-
"""시모 퍼널 거울 API (읽기 · 배 960 레인 U). sync_funnel.py 가 5분마다 떠온 funnel_cache 를 GAS 응답 모양 그대로 돌려준다.
  GET /api/funnel/{action}?<GAS 와 같은 쿼리>   action = period_breakdown · funnel_conversion · funnel_conversion_detail · lesson_breakdown
  GET /api/funnel/health
캐시에 없는 범위(예: 화면이 고른 옛 달)는 그 자리에서 GAS 1회 호출해 채운다 — 첫 조회만 느리고 이후는 서버.
화면(월간마케팅보고서·콘텐츠문의현황)은 GAS_URL + '?action=…' 을 이 주소로 바꾸면 된다(응답 키 동일 · _source 만 추가).
"""
import json
import os
import sys

from fastapi import APIRouter, HTTPException, Request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sync_funnel import _kst_now, db, gas_get, key_of, load_env, store  # noqa: E402

ACTIONS = ("period_breakdown", "funnel_conversion", "funnel_conversion_detail", "lesson_breakdown")
SOURCE = "sheet-mirror"
router = APIRouter(prefix="/api/funnel")
load_env()


@router.get("/health")
def health():
    conn = db.connect(readonly=True)
    with conn:
        rows = conn.execute("SELECT action, COUNT(*) c, MAX(synced_at) s FROM funnel_cache WHERE tenant_id=%s GROUP BY action", (db.TENANT,)).fetchall()
        meta = dict(conn.execute("SELECT k, v FROM sync_meta WHERE tenant_id=%s AND k LIKE 'funnel_last%%'", (db.TENANT,)).fetchall())
    conn.close()
    return {"ok": True, "actions": {r["action"]: {"count": r["c"], "synced_at": r["s"]} for r in rows},
            "last_sync_kst": meta.get("funnel_last_sync"), "last_failed": meta.get("funnel_last_failed") or "", "_source": SOURCE}


@router.get("")
@router.get("/")
def funnel_qs(request: Request):
    """화면(_api.js wpCmoFetch·wpCmoRead)은 GAS 모양 그대로 `?action=...` 로 부른다 — 같은 캐시로 넘긴다.
    이 줄이 없으면 두 화면이 404 를 받고 조용히 GAS 폴백만 타서 거울이 한 번도 안 쓰인다(2026-09-04 실측)."""
    return funnel(request.query_params.get("action", ""), request)


@router.get("/{action}")
def funnel(action: str, request: Request):
    if action not in ACTIONS:
        raise HTTPException(404, "모르는 액션: %s" % action)
    params = dict(request.query_params)
    conn = db.connect()
    with conn:
        r = conn.execute("SELECT data, synced_at FROM funnel_cache WHERE tenant_id=%s AND action=%s AND params=%s",
                         (db.TENANT, action, key_of(params))).fetchone()
    if r:
        data, synced = json.loads(r["data"]), r["synced_at"]
    else:                                                     # 캐시 없음 → GAS 1회(느림) → 저장
        data = gas_get(action, {k: v for k, v in params.items() if k not in ("action", "_pv")})
        if data is None:
            conn.close()
            raise HTTPException(502, "GAS 조회 실패: %s" % action)
        synced = _kst_now()
        store(conn, action, params, data, synced)
    conn.close()
    data["_source"], data["_synced_at"] = SOURCE, synced
    return data
