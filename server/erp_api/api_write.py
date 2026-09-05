# -*- coding: utf-8 -*-
"""쓰기 관문 POST /api/write (write-through · 배 961 · 2026-09-03 시토).

화면(membership.html apiPost)이 GAS 로 보내던 payload 를 그대로 받아
  ① write_log 에 먼저 적고(서버가 먼저 받는 원천)
  ② 같은 payload 를 종전 GAS 에 그대로 POST 해 시트를 유지하고(GAS 판정 로직 재사용)
     — 액션으로 갈라 보낸다: reg_·lf_·voc_·hold_complete = 접수 GAS(RECEPTION_EXEC_URL · 배 960 #4b),
       todo_·approval_rep_ = 업무 GAS(TODO_GAS_URL · #6b), 점검 3부서 = 점검 GAS(CHECK_GAS_URL · #5b),
       save_schedule = 전사일정 GAS(SCHEDULE_GAS_URL · #5b), 구매요청·자산 = 운영요약 GAS(PROC_GAS_URL · #H),
       나머지 = FUNNEL_EXEC_URL
  ③ GAS 응답(ok·error·detail·noRetry)을 그대로 돌려준다 — 화면 재시도·오류 코드 무변경.
영역별 원본 스위치(origin_switch.py · 배 960 레인 J): 그 영역이 server 면 ②③ 을 건너뛰고 원장에만 적은 뒤 즉시
  {ok:true, queued:true} 를 돌려준다 — 시트는 pushback.py(1분 cron)가 되밀고 거울도 그때 다시 뜬다. 되돌리기 = 스위치를 dual 로.
  ★ server 모드는 GAS 응답값(새 행 id·검증 거부 문구)을 화면에 못 준다 — 응답값을 쓰는 액션이 있는 영역은 전환 대상이 아니다.
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
from fastapi.responses import JSONResponse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import origin_switch  # noqa: E402  — 영역별 dual/server 스위치(배 960 레인 J)
from common import db  # noqa: E402
from api_intake import redact_blobs  # noqa: E402  — 사진·서명 base64 는 원장에 길이·해시만
# 리셉션 업무·라커관리(배 960 #9i) — 액션 이름(update·append)이 흔해 접두사로 못 가른다. 목적지 판정 정본은 그 파일.
from api_reception_ops import forget as _rc_forget, write_gas_key as _rc_gas_key  # noqa: E402
import gas_key  # noqa: E402  — 접수 GAS 게이트 열쇠(RECEPTION_TOKEN). 비어 있으면 본문 무변경.

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
# 점검 3부서 쓰기(배 960 #5b) — 정의서 §4. 원장·스냅샷·항목 마스터를 건드리는 것만 거울을 다시 떠온다.
#   빠진 것: fcheck_ranges_save·vendor_save(점검기준·거래업체는 거울에 없다) · notify/notify_round(텔레그램만) ·
#            saveBoard 는 화면이 /api/board/{key}/refresh 로 그 열쇠만 즉시 갱신하지만
#            FACILITY_CHECK_ 열쇠는 check_records(facility board)도 겸해서 여기에도 넣는다.
_CHECK_WRITES = ("save", "saveBoard", "saveItems", "snapshot_append", "unlock_round",
                 "save_facility_measure", "save_facility_notes")
# 점검 GAS 로 넘길 쓰기 전수(거울 유무와 무관) — _gas_key 목적지 표. 화면 관문(erp_write.js CHECK_WRITE)과 같은 목록.
_CHECK_GAS_ACTIONS = _CHECK_WRITES + ("save_insp_memo", "fcheck_ranges_save", "vendor_save")
# 구매요청·자산대장 쓰기(배 960 #H · CFO 매출지출현황) — 운영요약 GAS(PROC_GAS_URL · 레인 E 가 이미 쓰는 같은 열쇠).
#   화면 관문(erp_write.js PROC_WRITE)과 같은 목록. 읽기(list·asset_list)는 여기 없다 — 거울에 안 얹고 GAS 직행.
#   ★이름이 짧고 흔하다 — 명시 목록으로만 갈라 회원(member_*)·접수(reg_*) 쪽을 삼키지 않게 한다(자체점검이 지킨다).
_PROC_GAS_ACTIONS = ("add", "delete", "status", "photo",
                     "asset_update", "asset_label", "asset_issue", "asset_del")
# 구매성 지출 집계 거울(proc/proc_summary · 레인 E)은 품의가 늘거나 상태가 바뀌면 바로 옛값이 된다.
#   자산대장(asset_*)은 거울이 없다 — 헛돌지 않게 뺀다.
_PROC_MIRROR_WRITES = ("add", "delete", "status", "photo")
# 회원·문의 GAS(FUNNEL_EXEC_URL)로 보낼 액션 전수 — 시포 화면(cpo/**/*.html)이 실제로 관문에 보내는 것 그대로.
#   종전에는 표 어디에도 없는 액션이 조용히 이 GAS 로 흘렀다(오타·남의 도메인 액션까지) — 배 960 M3.
#   위 네 줄(회원·문의)에 없는 나머지 = 상품기획·직원피드백·오누띠·쓰기실패 보고. 늘어나면 화면과 여기를 같이 고친다.
_FUNNEL_GAS_ACTIONS = _MEMBER_WRITES + _INQUIRY_WRITES + (
    "product_plan_save", "product_plan_delete",
    "staff_feedback_submit", "staff_feedback_list", "staff_feedback_photo",
    "ohnutti_status_update", "ohnutti_team_list", "client_write_fail")
MIRROR_SYNC = {a: "sync_members.py" for a in _MEMBER_WRITES}
MIRROR_SYNC.update({a: "sync_inquiries.py" for a in _INQUIRY_WRITES})
MIRROR_SYNC.update({a: "sync_reception.py" for a in _RECEPTION_WRITES})
MIRROR_SYNC.update({a: "sync_todo.py" for a in _TODO_WRITES})
MIRROR_SYNC.update({a: "sync_check.py" for a in _CHECK_WRITES})
MIRROR_SYNC.update({a: "sync_sales.py" for a in _PROC_MIRROR_WRITES})
# 전사일정 거울(misc_cache schedule/load_schedule · 배990)은 sync_misc.py 가 5분마다 다시 뜬다 — 저장 직후는
# 옛값. save_schedule 도 다른 영역처럼 여기 한 줄만 추가(배 1039-B · 2026-09-05) — 인자 없이 3개 소형 GAS를
# 통째로 다시 뜬다(가벼움 · _SYNC_ARGS 미지정 = main() 전체 실행).
MIRROR_SYNC["save_schedule"] = "sync_misc.py"
# 동기화 스크립트에 붙일 인자 — 점검은 오늘치만 다시 뜬다(전량은 GAS 18호출·수 분, 5분 cron 이 따로 돈다).
#   매출은 한 열쇠만(--only) — 전량은 무거운 집계 20여 호출(수십 초짜리 여럿)이고, proc_summary 는 TTL 30분이라
#   그냥 전량을 돌리면 fresh() 가 건너뛰어 정작 갱신이 안 된다.
_SYNC_ARGS = {"sync_check.py": ["--today"], "sync_sales.py": ["--only", "proc/proc_summary"]}
_sync_timers = {}


def _now_kst():
    return time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(time.time() + 9 * 3600))


def _gas_key(action):
    """어느 GAS 로 넘길지 — 접수처 액션(reg_·lf_·voc_·hold_complete)은 접수 GAS, 업무·결재 SSOT(todo_·approval_rep_)는
    업무 GAS, 점검 3부서는 점검 GAS, 전사일정 저장은 일정 GAS, 나머지는 종전 회원·문의 GAS.
    같은 관문 하나로 다섯 GAS 를 덮는다(배 960 #4b·#5b·#6b · 새 관문·새 인증 만들지 않음).
    ponytail: 접두사 표 한 곳 — 액션이 늘어도 여기만 본다. 점검은 접두사가 안 갈려(save·saveBoard…) 명시 목록.
    ★표 어디에도 없으면 None — 목적지를 지어내지 않는다(배 960 M3). 관문은 그때 400 unknown-action 을 돌려주고,
      화면은 종전대로 GAS 직접 경로로 폴백한다(저장은 되고, 서버 이중기록만 안 남는다)."""
    if action.startswith(("reg_", "lf_", "voc_")) or action == "hold_complete":
        return "RECEPTION_EXEC_URL"
    if action.startswith(("todo_", "approval_rep_")):
        return "TODO_GAS_URL"
    if action in _CHECK_GAS_ACTIONS:
        return "CHECK_GAS_URL"
    if action == "save_schedule":
        return "SCHEDULE_GAS_URL"
    if action in _PROC_GAS_ACTIONS:
        return "PROC_GAS_URL"
    if action in _FUNNEL_GAS_ACTIONS:
        return "FUNNEL_EXEC_URL"
    return None


def _gas_forward(body, url_key="FUNNEL_EXEC_URL"):
    """GAS 에 같은 본문을 POST. 302 는 urllib 가 GET 으로 따라간다(본문 없이 — GAS 표준 흐름). 반환 dict, 실패 시 예외."""
    url = os.environ.get(url_key, "")
    if not url:
        raise RuntimeError("%s 없음 — /srv/erp/api.env" % url_key)
    # 접수 GAS 의 GATED 쓰기(reg_delete·lf_delete·hold_complete·voc_update)는 열쇠가 있어야 통과한다.
    #   RECEPTION_TOKEN 이 비어 있으면 본문 그대로 — 스위치 켜기 전 배포해도 회귀 0.
    body = gas_key.sign_body(url_key, body)
    req = urllib.request.Request(url, data=body, method="POST",
                                 headers={"Content-Type": "text/plain;charset=utf-8", "User-Agent": "wellperion-erp-api"})
    with urllib.request.urlopen(req, timeout=FORWARD_TIMEOUT) as r:
        data = json.loads(r.read().decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("GAS 응답이 객체가 아님")
    return data


IDEM_WINDOW_MIN = 10      # 같은 열쇠를 이 시간 안에 다시 받으면 중복 요청으로 본다


def _idem_hit(conn, user, payload):
    """같은 (사용자, idem) 로 이미 받은 요청이면 그때 돌려준 응답 그대로, 아니면 None (배 960 M7).

    화면은 요청마다 idem 열쇠(uuid)를 본문에 싣는다(_assets/erp_write.js gwPost). 서버가 GAS 쓰기를 끝냈는데
    응답만 유실되면(전파 끊김·탭 닫힘) 화면이 같은 열쇠로 한 번 더 묻는다 — 그때 GAS 를 또 치면
    snapshot_append·todo_add 가 시트에 두 줄이 된다. 여기서 원장을 먼저 보고 저장된 응답을 그대로 돌려준다.
    아직 응답이 없는 행(진행 중)이면 되받은 것으로 치고 queued 를 돌려준다 — 두 번 쓰는 쪽보다 낫다."""
    idem = str((payload or {}).get("idem") or "")[:64]
    if not idem:
        return None
    since = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(time.time() + 9 * 3600 - IDEM_WINDOW_MIN * 60))
    row = conn.execute("SELECT id, gas_response FROM write_log WHERE tenant_id=%s AND user_email=%s"
                       " AND payload->>'idem'=%s AND at >= %s ORDER BY id DESC LIMIT 1",
                       (db.TENANT, user, idem, since)).fetchone()
    if not row:
        return None
    if row["gas_response"]:
        return row["gas_response"] if isinstance(row["gas_response"], dict) else json.loads(row["gas_response"])
    return {"ok": True, "queued": True, "id": row["id"], "duplicate": True}


def _schedule_sync(script):
    # ponytail: 키 1건만 다시 당기는 함수가 없어 전체 동기화를 3초 디바운스로 1회 — 연속 저장은 한 번으로 모은다.
    #   cron 5분 동기화와 겹쳐도 같은 열쇠 upsert 라 마지막 커밋이 이긴다(둘 다 GAS 원천). 건별 갱신은 GAS 에 단건 조회가 생기면.
    def run():
        _sync_timers.pop(script, None)
        with open("/srv/erp/%s.log" % script[:-3], "a") as log:
            subprocess.Popen([sys.executable, os.path.join(HERE, script)] + _SYNC_ARGS.get(script, []),
                         stdout=log, stderr=subprocess.STDOUT)
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
    # 목적지 판정은 아래 전달과 같은 순서로 — 리셉션 업무·라커(#9i)는 스위치 이름이 없어 늘 dual 이다.
    dest = _rc_gas_key(action, payload) or _gas_key(action)
    if dest is None:      # 표에 없는 액션 — 엉뚱한 GAS 로 흘려보내지 않는다(배 960 M3)
        return JSONResponse(status_code=400, content={
            "ok": False, "error": "unknown-action", "noRetry": True,
            "detail": "관문 목적지 표에 없는 액션입니다: %s" % action[:60]})
    try:
        conn = db.connect()
    except db.Error as e:
        return {"ok": False, "error": "server-forward-failed", "detail": "DB 열기 실패: %s" % e, "noRetry": False}
    prev = _idem_hit(conn, user, payload)   # 응답만 유실돼 같은 열쇠로 다시 온 요청 — GAS 를 두 번 치지 않는다
    if prev is not None:
        conn.close()
        return prev
    # 테스트/더미 페이로드 격리(AWS DB 더미 전수정리 · 2026-09-05) — 저장은 하되 GAS 로 안 보내고
    # 미러 동기화·리셉션 실패대비 정본도 안 건드린다. 운영 화면·집계는 gas_status='test' 행을 그대로 뺀다.
    is_test = db.is_test_payload(payload)
    area = origin_switch.WRITE_AREA.get(dest)
    server_mode = bool(area) and origin_switch.mode(area) == "server" and not is_test   # 스위치 한 줄 — 재시작 없이 갈린다
    with conn:
        log_id = conn.execute(
            "INSERT INTO write_log (tenant_id, at, action, payload, user_email, gas_status, raw_body)"
            " VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id",
            (db.TENANT, _now_kst(), action, json.dumps(redact_blobs(payload), ensure_ascii=False), user,
             "test" if is_test else ("queued" if server_mode else "pending"),
             body.decode("utf-8") if server_mode else None)).fetchone()[0]
    if is_test:
        conn.close()
        return {"ok": True, "test": True, "id": log_id}
    if server_mode:
        # 서버 원본 — GAS 왕복을 안 기다린다. 시트는 pushback.py(1분)가 채우고 거울도 그때 다시 뜬다.
        conn.close()
        return {"ok": True, "queued": True, "id": log_id, "mode": "server"}
    try:
        # 리셉션 업무·라커관리는 본문 모양으로만 갈린다(배 960 #9i) — 나머지는 종전 액션 접두사 표.
        resp = _gas_forward(body, dest)
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
    if status == "ok":
        _rc_forget(payload)   # 리셉션 업무·라커 실패대비 정본은 쓰기 직후 버린다(낡은 값 금지 · 배 960 #9i)
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
    # 점검(배 960 #5b) — 이름이 접두사로 안 갈려서 목적지가 새면 회원·문의 GAS 로 간다. 전수 확인.
    for _a in ("save", "saveBoard", "saveItems", "snapshot_append", "unlock_round", "save_insp_memo",
               "save_facility_measure", "save_facility_notes", "fcheck_ranges_save", "vendor_save"):
        assert _gas_key(_a) == "CHECK_GAS_URL", _a
    assert _gas_key("save_schedule") == "SCHEDULE_GAS_URL"   # 전사일정은 별개 GAS — 점검 GAS 로 새면 저장이 사라진다
    assert _gas_key("member_active_update") == "FUNNEL_EXEC_URL"   # 점검 명시 목록이 회원 쪽을 삼키면 안 된다
    assert MIRROR_SYNC["snapshot_append"] == "sync_check.py" and _SYNC_ARGS["sync_check.py"] == ["--today"]
    assert "fcheck_ranges_save" not in MIRROR_SYNC   # 거울 없는 쓰기는 헛돌지 않는다
    assert MIRROR_SYNC["save_schedule"] == "sync_misc.py"   # 전사일정 저장 뒤 misc_cache(schedule) 도 다시 뜬다(배1039-B)
    # 구매요청·자산(배 960 #H) — 이름이 짧아 목적지가 새기 쉽다. 전수 + 다른 도메인이 안 삼키는지 양쪽 확인.
    for _a in ("add", "delete", "status", "photo", "asset_update", "asset_label", "asset_issue", "asset_del"):
        assert _gas_key(_a) == "PROC_GAS_URL", _a
    assert _gas_key("list") is None and _gas_key("asset_list") is None      # 읽기는 관문에 안 온다 — 표에 없으면 400
    assert _gas_key("reg_delete") == "RECEPTION_EXEC_URL" and _gas_key("todo_add") == "TODO_GAS_URL"  # 접두사 표가 먼저다
    assert _gas_key("save") == "CHECK_GAS_URL" and _gas_key("member_registered_add") == "FUNNEL_EXEC_URL"
    assert MIRROR_SYNC["status"] == "sync_sales.py" and _SYNC_ARGS["sync_sales.py"] == ["--only", "proc/proc_summary"]
    assert "asset_issue" not in MIRROR_SYNC and "asset_del" not in MIRROR_SYNC   # 자산대장은 거울이 없다
    # 리셉션 업무·라커(배 960 #9i) — 액션만 보면 전부 FUNNEL 로 샌다. 본문 판정이 먼저 서야 한다.
    assert _rc_gas_key("update", {"tab": "키관리", "row": 2, "col": 7}) == "RCOPS_GAS_URL"
    assert _rc_gas_key("append", {"tab": "시재금입출내역", "values": []}) == "RCOPS_GAS_URL"
    assert _rc_gas_key("update", {"db": "men", "_sheet_row": 3, "fields": {}}) == "LOCKER_GAS_URL"
    assert _rc_gas_key("read", {"tab": "키관리"}) is None                      # 읽기는 /api/reception-ops
    assert _rc_gas_key("member_active_update", {"no": "M1"}) is None           # 회원 쓰기를 삼키면 안 된다
    assert (_rc_gas_key("member_active_update", {"no": "M1"}) or _gas_key("member_active_update")) == "FUNNEL_EXEC_URL"
    assert (_rc_gas_key("save", {"key": "X"}) or _gas_key("save")) == "CHECK_GAS_URL"
    assert "update" not in MIRROR_SYNC and "append" not in MIRROR_SYNC         # 두 화면은 5분 거울이 없다
    r = redact_blobs({"action": "lf_submit", "photo": "d" * 9000, "memo": "짧은 메모"})
    assert r["memo"] == "짧은 메모" and r["action"] == "lf_submit"
    assert r["photo"]["_redacted"] == 9000 and len(r["photo"]["_sha256"]) == 64
    # 스위치(배 960 레인 J) — 모든 목적지에 스위치 이름이 있어야 전환·복귀가 한 줄로 된다.
    for _a in ("reg_update", "todo_add", "save", "save_schedule", "add", "member_owner_save"):
        assert _gas_key(_a) in origin_switch.WRITE_AREA, _a
    assert set(origin_switch.WRITE_AREA.values()) <= set(origin_switch.NAMES)
    # 표에 없는 액션은 목적지를 지어내지 않는다(배 960 M3) — 시포 화면이 실제로 보내는 회원·문의 액션은 전부 있어야 한다.
    for _a in ("member_owner_save", "member_inquiry_delete", "lesson_inquiry_update", "product_plan_save",
               "staff_feedback_submit", "staff_feedback_photo", "ohnutti_team_list", "client_write_fail"):
        assert _gas_key(_a) == "FUNNEL_EXEC_URL", _a
    assert _gas_key("member_owner_sav") is None and _gas_key("drop_table") is None   # 오타·남의 액션은 400

    # 중복 쓰기 가림(배 960 M7) — 같은 (사용자, idem) 두 번째 요청은 저장된 응답을 그대로 돌려준다(GAS 재전송 없음).
    class _C:
        row = None

        def execute(self, q, p=None):
            assert "payload->>'idem'" in q and "user_email" in q
            return self

        def fetchone(self):
            return _C.row

    assert _idem_hit(_C(), "a@b.c", {"action": "todo_add"}) is None          # 열쇠 없으면 가리지 않는다
    assert _idem_hit(_C(), "a@b.c", {"action": "todo_add", "idem": "u1"}) is None   # 처음 보는 열쇠
    _C.row = {"id": 7, "gas_response": {"ok": True, "id": 42}}
    assert _idem_hit(_C(), "a@b.c", {"idem": "u1"}) == {"ok": True, "id": 42}       # 저장된 응답 그대로
    _C.row = {"id": 7, "gas_response": '{"ok":true,"id":42}'}                       # 드라이버가 문자열로 줄 때도
    assert _idem_hit(_C(), "a@b.c", {"idem": "u1"}) == {"ok": True, "id": 42}
    _C.row = {"id": 7, "gas_response": None}
    assert _idem_hit(_C(), "a@b.c", {"idem": "u1"})["queued"] is True                # 아직 진행 중 = 두 번 쓰지 않는다
    print("자체점검 통과")
