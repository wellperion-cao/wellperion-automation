# -*- coding: utf-8 -*-
"""채용 공고 상태 공개 읽기 거울 (배12615 · GM 지시 2026-09-15 「AWS 오늘 100% · 안 되면 구글 폴백」).

채용 화면 6장(chro/recruiting/*.html)은 지원자가 로그인 없이 보는 자리라 인사 GAS(HR_GAS_URL)에
{"action":"public-job-status"} 를 직접 POST 해 「이 공고가 열려 있나」를 그린다. 이 라우트는 그 응답을 서버가
5분 거울로 쥐고 같은 모양으로 내준다 — 화면은 서버를 먼저 보고 안 되면 종전 GAS 로 간다(_assets/erp_write.js erpReadFirst).

  GET|POST /api/jobs/public     {"ok":true,"jobs":[...]} — GAS public-job-status 응답 그대로 + _source·_synced_at
  OPTIONS  /api/jobs/public     CORS preflight (깃허브 사본·다른 origin 에서 부른다)

공개 통로다 — nginx(jobs-public.nginx.conf)가 auth 없이 열고 X-Erp-User 를 지운다. 공고 상태는 GAS 가 이미
누구에게나 내주던 공개 정보라 응답을 거르지 않는다. 거울은 sales_cache(gas='hr') 를 그대로 쓴다 — 새 표 없음.
app.py 가 같은 폴더의 api_*.py 를 자동 등록한다 — app.py 본문은 건드리지 않는다.
자체점검: python3 api_jobs_public.py --selftest   (네트워크·DB 없음 — 판정만)
"""
import json
import os
import sys
import urllib.request

from fastapi import APIRouter, Response
from fastapi.responses import JSONResponse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sync_sales import _kst_now, db, fresh, key_of, load_env, store  # noqa: E402  — 거울 관례 재사용

SOURCE = "sheet-mirror"
GAS = "hr"
ACTION = "public-job-status"
TTL_MIN = 5
CORS = {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type"}
router = APIRouter(prefix="/api/jobs")
load_env()


def gas_fetch(timeout=60):
    """인사 GAS 1회 — 화면과 같은 본문. 성공 시 dict, 실패 시 None(지어내지 않는다)."""
    url = os.environ.get("HR_GAS_URL", "")
    if not url:
        return None
    req = urllib.request.Request(url, data=json.dumps({"action": ACTION}).encode("utf-8"),
                                 headers={"Content-Type": "text/plain;charset=utf-8"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8", "replace"))
    except Exception as e:  # noqa: BLE001
        print("[warn] jobs/public GAS 실패: %s: %s" % (type(e).__name__, str(e)[:120]))
        return None
    return data if usable(data) else None


def usable(data):
    """거울에 넣어도 되는 응답인가 — ok 이고 jobs 가 목록일 때만(구글 안내 HTML·오류 봉투는 안 넣는다)."""
    return isinstance(data, dict) and data.get("ok") is True and isinstance(data.get("jobs"), list)


def _serve():
    conn = db.connect()
    try:
        now = _kst_now()
        row = None
        with conn:
            if fresh(conn, now, GAS, ACTION, {}, TTL_MIN):
                row = conn.execute("SELECT data, synced_at FROM sales_cache WHERE tenant_id=%s AND gas=%s AND action=%s AND params=%s",
                                   (db.TENANT, GAS, ACTION, key_of({}))).fetchone()
        if row:
            data, synced = json.loads(row["data"]), row["synced_at"]
        else:
            data = gas_fetch()
            if data is None:                                   # GAS 도 안 됨 — 있던 거울이라도 낸다(없으면 502)
                with conn:
                    row = conn.execute("SELECT data, synced_at FROM sales_cache WHERE tenant_id=%s AND gas=%s AND action=%s AND params=%s",
                                       (db.TENANT, GAS, ACTION, key_of({}))).fetchone()
                if not row:
                    return JSONResponse({"ok": False, "error": "jobs-unavailable"}, status_code=502, headers=CORS)
                data, synced = json.loads(row["data"]), row["synced_at"]
            else:
                synced = now
                store(conn, GAS, ACTION, {}, data, synced)
    finally:
        conn.close()
    data = dict(data, _source=SOURCE, _synced_at=synced)
    return JSONResponse(data, headers=CORS)


@router.options("/public")
def preflight():
    return Response(status_code=204, headers=CORS)


@router.get("/public")
def jobs_public_get():
    return _serve()


@router.post("/public")
def jobs_public_post():
    return _serve()


def selftest():
    assert usable({"ok": True, "jobs": []}) and usable({"ok": True, "jobs": [{"bucket": "a"}]})
    assert not usable({"ok": False, "jobs": []}) and not usable({"ok": True}) and not usable("<html>")
    assert CORS["Access-Control-Allow-Origin"] == "*" and "OPTIONS" in CORS["Access-Control-Allow-Methods"]
    print("selftest ok")
    return 0


if __name__ == "__main__":
    sys.exit(selftest() if "--selftest" in sys.argv else 0)
