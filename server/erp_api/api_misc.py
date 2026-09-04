# -*- coding: utf-8 -*-
"""소형 GAS 읽기 거울 API (배 960 #9). sync_misc.py 가 떠온 misc_cache 를 GAS 콜백 페이로드 모양 그대로 돌려준다.
  GET /api/misc/{gas}/{action}   renewal/stats — cpo/member/renewal.html 상단 월별 통계(PIN 없이 보는 공개 집계)
  GET /api/misc/health
거울에 없으면 그 자리에서 GAS 1회(느림) 후 저장. 화면은 ERP 도메인에서만 이 주소를 먼저 부르고 실패하면
GAS(JSONP) 로 조용히 돌아간다 — PIN 뒤 명단(PII)은 이 API 를 거치지 않는다(그대로 GAS 직결).
app.py 가 같은 폴더의 api_*.py 를 자동 등록한다 — app.py 본문은 건드리지 않는다.

자체점검: python3 api_misc.py --selftest  (같은 DB 의 tenant 'selftest' · 네트워크 없음)
"""
import json
import os
import sys

from fastapi import APIRouter, HTTPException

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sync_misc import ACTIONS, _kst_now, db, gas_call, load_env, store  # noqa: E402

SOURCE = "sheet-mirror"
router = APIRouter(prefix="/api/misc")
load_env()


@router.get("/health")
def health():
    conn = db.connect(readonly=True)
    with conn:
        rows = conn.execute("SELECT gas, action, COUNT(*) c, MAX(synced_at) s FROM misc_cache WHERE tenant_id=%s"
                            " GROUP BY gas, action", (db.TENANT,)).fetchall()
        meta = dict(conn.execute("SELECT k, v FROM sync_meta WHERE tenant_id=%s AND k LIKE 'misc_last%%'", (db.TENANT,)).fetchall())
    conn.close()
    return {"ok": True, "rows": sum(r["c"] for r in rows),
            "actions": {"%s/%s" % (r["gas"], r["action"]): {"count": r["c"], "synced_at": r["s"]} for r in rows},
            "last_sync_kst": meta.get("misc_last_sync"), "last_failed": meta.get("misc_last_failed") or "", "_source": SOURCE}


@router.get("/{gas}/{action}")
def misc(gas: str, action: str):
    if action not in ACTIONS.get(gas, ()):
        raise HTTPException(404, "모르는 액션: %s/%s" % (gas, action))
    conn = db.connect()
    with conn:
        r = conn.execute("SELECT data, synced_at FROM misc_cache WHERE tenant_id=%s AND gas=%s AND action=%s AND params=''",
                         (db.TENANT, gas, action)).fetchone()
    if r:
        data, synced = json.loads(r["data"]), r["synced_at"]
    else:                                                     # 거울 없음 → GAS 1회(느림) → 저장
        data = gas_call(gas, action)
        if data is None:
            conn.close()
            raise HTTPException(502, "GAS 조회 실패: %s/%s" % (gas, action))
        synced = _kst_now()
        store(conn, gas, action, "", data, synced)
    conn.close()
    data["_source"], data["_synced_at"] = SOURCE, synced
    return data


# ── 자체점검 ──────────────────────────────────────────────────────────────

def selftest():
    db.TENANT = "selftest"                       # 같은 DB · 다른 tenant — 실데이터는 한 줄도 안 건드린다
    conn = db.connect()
    db.init_schema(conn)
    try:
        with conn:
            conn.execute("DELETE FROM misc_cache WHERE tenant_id=%s", (db.TENANT,))
        store(conn, "renewal", "stats", "", {"updated": "t0", "months": [{"num": 8, "done": 55}]}, "t0")
        d = misc("renewal", "stats")
        assert d["months"][0]["done"] == 55 and d["_source"] == SOURCE and d["_synced_at"] == "t0", d
        for g, a in (("renewal", "nope"), ("nope", "stats")):
            try:
                misc(g, a)
                raise AssertionError("404 이어야: %s/%s" % (g, a))
            except HTTPException as e:
                assert e.status_code == 404
        h = health()
        assert h["rows"] == 1 and "renewal/stats" in h["actions"], h
    finally:
        with conn:
            conn.execute("DELETE FROM misc_cache WHERE tenant_id=%s", (db.TENANT,))
        conn.close()
    print("selftest ok")
    return 0


if __name__ == "__main__":
    sys.exit(selftest() if "--selftest" in sys.argv else 2)
