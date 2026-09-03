# -*- coding: utf-8 -*-
"""쓰기 관문 POST /api/write (write-through · 배 961 · 2026-09-03 시토).

화면(membership.html apiPost)이 GAS 로 보내던 payload 를 그대로 받아
  ① write_log 에 먼저 적고(서버가 먼저 받는 원천)
  ② 같은 payload 를 종전 GAS(api.env FUNNEL_EXEC_URL)에 그대로 POST 해 시트를 유지하고(GAS 판정 로직 재사용)
  ③ GAS 응답(ok·error·detail·noRetry)을 그대로 돌려준다 — 화면 재시도·오류 코드 무변경.
GAS 에 못 닿거나 응답이 JSON 이 아니면 {ok:false, error:'server-forward-failed', noRetry:false} — 화면이 GAS 직접 경로로 폴백한다.
거울 즉시 반영: 회원·문의 쓰기가 ok 면 sync_members / sync_inquiries 전체 동기화를 뒤에서 1회 돌린다(5분 지연 소멸).
nginx 가 앞에서 auth_request 로 로그인 쿠키를 검사하고 X-Erp-User 를 넘긴다(api.nginx.conf).
"""
import json
import os
import subprocess
import sys
import threading
import time
import urllib.request

from fastapi import APIRouter, Request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common import db  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
router = APIRouter()
FORWARD_TIMEOUT = 55   # 화면 apiPost 상한 60초보다 짧게 — 화면이 끊기 전에 server-forward-failed 를 받게

# 어떤 쓰기가 어느 거울을 더럽히나 — ok 응답 뒤 해당 동기화 스크립트를 1회 돌린다.
MIRROR_SYNC = {
    "member_active_update": "sync_members.py",
    "member_inquiry_update": "sync_inquiries.py",
    "lesson_inquiry_update": "sync_inquiries.py",
}
_sync_timers = {}


def _now_kst():
    return time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(time.time() + 9 * 3600))


def _gas_forward(body):
    """GAS 에 같은 본문을 POST. 302 는 urllib 가 GET 으로 따라간다(본문 없이 — GAS 표준 흐름). 반환 dict, 실패 시 예외."""
    url = os.environ.get("FUNNEL_EXEC_URL", "")
    if not url:
        raise RuntimeError("FUNNEL_EXEC_URL 없음 — /srv/erp/api.env")
    req = urllib.request.Request(url, data=body, method="POST",
                                 headers={"Content-Type": "text/plain;charset=utf-8", "User-Agent": "wellperion-erp-api"})
    with urllib.request.urlopen(req, timeout=FORWARD_TIMEOUT) as r:
        data = json.loads(r.read().decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("GAS 응답이 객체가 아님")
    return data


def _schedule_sync(script):
    # ponytail: 키 1건만 다시 당기는 함수가 없어 전체 동기화를 3초 디바운스로 1회 — 연속 저장은 한 번으로 모은다.
    #   cron 5분 동기화와 겹쳐도 같은 열쇠 upsert 라 마지막 커밋이 이긴다(둘 다 GAS 원천). 건별 갱신은 GAS 에 단건 조회가 생기면.
    def run():
        _sync_timers.pop(script, None)
        with open("/srv/erp/%s.log" % script[:-3], "a") as log:
            subprocess.Popen([sys.executable, os.path.join(HERE, script)], stdout=log, stderr=subprocess.STDOUT)
    t = _sync_timers.pop(script, None)
    if t:
        t.cancel()
    t = threading.Timer(3, run)
    t.daemon = True
    _sync_timers[script] = t
    t.start()


@router.post("/api/write")
async def write(request: Request):
    body = await request.body()
    try:
        payload = json.loads(body.decode("utf-8"))
        action = str(payload["action"])
    except Exception:
        return {"ok": False, "error": "bad-payload", "detail": "JSON 객체에 action 이 있어야 합니다", "noRetry": True}
    user = request.headers.get("x-erp-user", "")
    try:
        conn = db.connect()
    except db.Error as e:
        return {"ok": False, "error": "server-forward-failed", "detail": "DB 열기 실패: %s" % e, "noRetry": False}
    with conn:
        log_id = conn.execute(
            "INSERT INTO write_log (tenant_id, at, action, payload, user_email, gas_status) VALUES (%s,%s,%s,%s,%s,'pending') RETURNING id",
            (db.TENANT, _now_kst(), action, json.dumps(payload, ensure_ascii=False), user)).fetchone()[0]
    try:
        resp = _gas_forward(body)
        status = "ok" if resp.get("ok") else "gas-error"
    except Exception as e:
        resp = {"ok": False, "error": "server-forward-failed", "detail": "%s: %s" % (type(e).__name__, str(e)[:200]), "noRetry": False}
        status = "forward-failed"
    with conn:
        conn.execute("UPDATE write_log SET gas_status=%s, gas_response=%s WHERE id=%s",
                     (status, json.dumps(resp, ensure_ascii=False)[:20000], log_id))
    conn.close()
    if status == "ok" and action in MIRROR_SYNC:
        _schedule_sync(MIRROR_SYNC[action])
    return resp
