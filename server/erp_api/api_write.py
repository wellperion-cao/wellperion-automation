# -*- coding: utf-8 -*-
"""쓰기 관문 POST /api/write (write-through · 배 961 · 2026-09-03 시토).

화면(membership.html apiPost)이 GAS 로 보내던 payload 를 그대로 받아
  ① write_log 에 먼저 적고(서버가 먼저 받는 원천)
  ② 같은 payload 를 종전 GAS 에 그대로 POST 해 시트를 유지하고(GAS 판정 로직 재사용)
     — 액션으로 갈라 보낸다: reg_·lf_·voc_·hold_complete = 접수 GAS(RECEPTION_EXEC_URL · 배 960 #4b), 나머지 = FUNNEL_EXEC_URL
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
from api_intake import redact_blobs  # noqa: E402  — 사진·서명 base64 는 원장에 길이·해시만

HERE = os.path.dirname(os.path.abspath(__file__))
router = APIRouter()
FORWARD_TIMEOUT = 55   # 화면 apiPost 상한 60초보다 짧게 — 화면이 끊기 전에 server-forward-failed 를 받게

# 어떤 쓰기가 어느 거울을 더럽히나 — ok 응답 뒤 해당 동기화 스크립트를 1회 돌린다.
#   정본 = 시포 화면 쓰기 액션 전수(배 961 note · 2026-09-03). 빠진 액션이 ok 여도 거울은 5분 옛값이라 전부 적는다.
#   거울 없는 쓰기(staff_feedback_*·ohnutti_*·client_write_fail)는 GAS 전달만 — 여기 없으면 동기화를 안 돌린다.
_MEMBER_WRITES = ("member_active_update", "member_owner_save", "member_registered_add", "member_registered_remove",
                  "member_archive_restore", "member_hold_transition", "member_hold_approve")
_INQUIRY_WRITES = ("member_inquiry_update", "member_inquiry_add", "member_inquiry_delete",
                   "lesson_inquiry_update", "lesson_inquiry_add")
_RECEPTION_WRITES = ("reg_update", "reg_delete", "lf_submit", "lf_handover", "lf_delete", "hold_complete")
# 업무·결재 SSOT 쓰기(배 960 #6b) — 정의서 §4 쓰기 액션 중 원장 행을 건드리는 것 전부.
#   빠진 것: ai_add·ai_delete(AI배 탭 — 거울 없음) · approval_set_pins·todo_orphan_cleanup(행 무변).
_TODO_WRITES = ("todo_add", "todo_update", "todo_delete", "todo_done", "todo_sign", "todo_reset",
                "todo_opinion", "todo_opinion_delete", "todo_upload", "todo_remove_file",
                "approval_rep_escalate", "approval_rep_sign_upload", "approval_rep_cancel")
MIRROR_SYNC = {a: "sync_members.py" for a in _MEMBER_WRITES}
MIRROR_SYNC.update({a: "sync_inquiries.py" for a in _INQUIRY_WRITES})
MIRROR_SYNC.update({a: "sync_reception.py" for a in _RECEPTION_WRITES})
MIRROR_SYNC.update({a: "sync_todo.py" for a in _TODO_WRITES})
_sync_timers = {}


def _now_kst():
    return time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(time.time() + 9 * 3600))


def _gas_key(action):
    """어느 GAS 로 넘길지 — 접수처 액션(reg_·lf_·voc_·hold_complete)은 접수 GAS, 업무·결재 SSOT(todo_·approval_rep_)는
    업무 GAS, 나머지는 종전 회원·문의 GAS. 같은 관문 하나로 세 GAS 를 덮는다(배 960 #4b·#6b · 새 관문·새 인증 만들지 않음).
    ponytail: 접두사 표 한 곳 — 액션이 늘어도 여기만 본다. 액션 이름이 겹치면(현재 겹침 0) 명시 표로 바꾼다."""
    if action.startswith(("reg_", "lf_", "voc_")) or action == "hold_complete":
        return "RECEPTION_EXEC_URL"
    if action.startswith(("todo_", "approval_rep_")):
        return "TODO_GAS_URL"
    return "FUNNEL_EXEC_URL"


def _gas_forward(body, url_key="FUNNEL_EXEC_URL"):
    """GAS 에 같은 본문을 POST. 302 는 urllib 가 GET 으로 따라간다(본문 없이 — GAS 표준 흐름). 반환 dict, 실패 시 예외."""
    url = os.environ.get(url_key, "")
    if not url:
        raise RuntimeError("%s 없음 — /srv/erp/api.env" % url_key)
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
            (db.TENANT, _now_kst(), action, json.dumps(redact_blobs(payload), ensure_ascii=False), user)).fetchone()[0]
    try:
        resp = _gas_forward(body, _gas_key(action))
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


if __name__ == "__main__":   # python3 api_write.py — 갈래·가림 자체점검(서버 없이)
    assert _gas_key("reg_update") == "RECEPTION_EXEC_URL"
    assert _gas_key("lf_submit") == "RECEPTION_EXEC_URL"
    assert _gas_key("hold_complete") == "RECEPTION_EXEC_URL"
    assert _gas_key("member_hold_approve") == "FUNNEL_EXEC_URL"   # member_* 는 접수 GAS 로 새면 안 된다
    assert _gas_key("lesson_inquiry_add") == "FUNNEL_EXEC_URL"
    assert _gas_key("todo_update") == "TODO_GAS_URL" and _gas_key("approval_rep_cancel") == "TODO_GAS_URL"
    assert _gas_key("todo_list") == "TODO_GAS_URL"          # 읽기가 흘러들어와도 목적지는 맞다(화면은 안 보낸다)
    assert MIRROR_SYNC["todo_delete"] == "sync_todo.py" and MIRROR_SYNC["member_owner_save"] == "sync_members.py"
    assert "ai_add" not in MIRROR_SYNC                      # AI배 탭은 거울이 없다 — 헛돌면 안 된다
    r = redact_blobs({"action": "lf_submit", "photo": "d" * 9000, "memo": "짧은 메모"})
    assert r["memo"] == "짧은 메모" and r["action"] == "lf_submit"
    assert r["photo"]["_redacted"] == 9000 and len(r["photo"]["_sha256"]) == 64
    print("자체점검 통과")
