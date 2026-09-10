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


def resp_ok(data):
    """GAS 응답이 성공인지 판정 — ok 칸 우선, 없으면 success 칸, 둘 다 없으면 성공으로 친다.
    명시적 false 만 실패(배 1067 — 점검 저장이 {success:true} 만 돌려주는데 여기선 resp.get('ok') 만
    보고 gas-error 로, pushback.py 는 data.get('ok', True) 로 ok 로 쳐서 같은 응답을 두 판정이
    서로 다르게 읽었다. 두 곳 모두 이 함수 하나만 쓴다 — pushback.py 가 여기서 import)."""
    if not isinstance(data, dict):
        return True
    if "ok" in data:
        return bool(data["ok"])
    if "success" in data:
        return bool(data["success"])
    return True

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
#   위 네 줄(회원·문의)에 없는 나머지 = 직원피드백(사진 제외)·오누띠·쓰기실패 보고. 늘어나면 화면과 여기를 같이 고친다.
#   product_plan_save/delete 는 여기 없다 — 화면(상품기획.html TODO_API_URL)의 실제 목적지가 업무 GAS 라
#   TODO_GAS_URL 쪽에 있다(배 1039 폼류4종). staff_feedback_photo 도 여기 없다 — 화면(FB_PHOTO_URL)의
#   실제 목적지가 이 다섯 GAS 중 어디에도 없는 별도 프로젝트(콘텐츠 접수 재사용)라 표에 없으면 목적지를
#   지어내지 않는다(배 960 M3 원칙) — 새 env 키가 생기기 전까진 화면이 GAS 직접 경로 그대로.
_FUNNEL_GAS_ACTIONS = _MEMBER_WRITES + _INQUIRY_WRITES + (
    "staff_feedback_submit", "staff_feedback_list",
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
    if action.startswith(("todo_", "approval_rep_")) or action in (
            "notice_save", "notice_delete", "product_plan_save", "product_plan_delete",
            # 카톡 전송방 등록부(cto/automation · 배11299 GAS 정리) — 같은 업무 GAS 프로젝트다.
            "kakao_rooms_save", "kakao_rooms_delete"):
        return "TODO_GAS_URL"   # 공지서식(coo/notice·배 1082)·상품기획(cpo/product·배 1039) — 같은 업무 GAS 프로젝트.
        # 거울 없음 — MIRROR_SYNC 미등록(상품기획 시트는 원본이 시트 자체).
    if action in _CHECK_GAS_ACTIONS:
        return "CHECK_GAS_URL"
    if action == "save_schedule":
        return "SCHEDULE_GAS_URL"
    if action in _PROC_GAS_ACTIONS:
        return "PROC_GAS_URL"
    if action in _FUNNEL_GAS_ACTIONS:
        return "FUNNEL_EXEC_URL"
    if action == "staff_feedback_photo":
        # 실무진 피드백 사진 — 화면의 FB_PHOTO_URL(AKfycbz4wWhqICMQZR…) 은 강사 접수 GAS 와 같은 프로젝트라
        # 서버가 이미 아는 INSTRUCTOR_GAS_URL 로 넘긴다(2026-09-05 실측 · 새 키 없음). 사진 base64 라 본문이 크다.
        return "INSTRUCTOR_GAS_URL"
    return None


# GAS 라우터가 action 칸이 비었을 때만 내는 답. 본문이 doPost 에 닿았으면 action 은 항상 있다 —
# 2026-09-09 실측: 모르는 action 을 보내면 GAS 는 「알 수 없는 action: …」이라 답한다(즉 본문을 봤다).
# 그러니 이 답이 오면 본문이 GAS 에 닿지 않은 것이고, 시트엔 아무것도 안 써졌다 → 다시 보내도 중복이 아니다.
# ★서버 원본 모드 응답에는 절대 "id" 를 담지 않는다 (2026-09-09 시토 · 실측으로 찾은 자리).
#   GAS 응답의 id 는 「업무 id·접수번호」이고 서버가 아는 id 는 「write_log 행번호」다 — 전혀 다른 숫자다.
#   같은 이름으로 돌려주면 화면은 그것을 접수번호라 믿고 그대로 쓴다. 실제로 두 화면이 그렇게 읽고 있었다:
#     · coo/todo/업무 현황 SSOT — todo_add 응답의 id 로 첨부를 붙인다 → 엉뚱한 업무에 사진이 붙는다
#     · cpo/member/실무진피드백 — 접수번호로 화면에 찍는다 → 사람에게 틀린 번호를 보여 준다
#   없는 값을 안 주는 것이 틀린 값을 주는 것보다 낫다. 그래서 logId 라는 다른 이름으로만 준다 —
#   화면은 undefined 를 받고 그 자리에서 눈에 띄게 멈춘다(조용히 틀리지 않는다).
#   success 를 ok 와 함께 싣는 이유: 점검 화면 몇 곳이 d.success 만 본다(주차관리부는 그것 하나로 실패 판정).
BODY_NEVER_ARRIVED = "action 필수"


# ★어떤 스위치가 켜져 있어도 서버 원본으로 안 가는 동작들 (2026-09-09 시토 · 화면 전수 실측에서 나온 것).
#   공통점 하나: 그 동작의 「진짜 결과」가 구글 쪽에만 있고, 서버가 즉시 ok 를 주면 사람에게 거짓말이 된다.
#   영역 스위치(origin_switch.WRITE_AREA)보다 촘촘한 자리다 — 영역 하나에 동작 수십 개가 붙어 있어서,
#   영역을 끊을 준비가 됐어도 이 몇 개는 남겨 둬야 한다. 여기 있으면 dual 로 돌아 종전과 똑같이 동작한다.
NO_SERVER_ACTIONS = {
    "unlock_round": "제출잠금 해제 비밀번호를 GAS 가 검증하고 잠금 원장도 GAS 속성에 있다 — 서버가 ok 를 주면 틀린 비번도 풀린 것처럼 보인다",
    "todo_upload": "첨부 주소가 구글 드라이브 업로드 결과다 — 서버는 그 주소를 만들 수 없고, 없으면 첨부가 통째로 사라진다",
    "save_schedule": "동시편집 판번호(rev)를 GAS 가 매긴다 — 없으면 다음 저장이 전부 막히거나 충돌 감지가 죽는다",
}


def server_ok(log_id, **extra):
    """서버 원본 모드 응답을 만드는 단 한 자리. 위 주석대로 'id' 라는 이름은 여기서 절대 안 나온다."""
    r = {"ok": True, "success": True, "logId": log_id}
    r.update(extra)
    return r


def body_never_arrived(data):
    """GAS 가 '본문을 못 봤다'고 답했나 — 그때만 다시 보내도 안전하다(쓰인 게 없다)."""
    return isinstance(data, dict) and str(data.get("error") or "").strip() == BODY_NEVER_ARRIVED


def _next_proc_no(conn):
    """구매요청 번호 채번(배 1195 ①) — proc_no_seq(schema.sql). reception_seq·lost_found_seq(배984)와
    같은 자리: PostgreSQL SEQUENCE 는 잠금 없이 동시호출해도 절대 같은 값을 두 번 안 준다(트랜잭션이
    롤백돼도 값은 반환 안 됨 — 결번은 나도 중복은 안 난다. FOR UPDATE 잠금보다 이쪽이 이 코드베이스 정본)."""
    return conn.execute("SELECT nextval('proc_no_seq')").fetchone()[0]


def _next_asset_labels(conn, count):
    """자산 라벨 채번(배 1195 ②) — proc_asset_no(schema.sql). GAS assetIssue() 형식(WP{yy2} {4자리}·연도가
    바뀌면 1부터 다시)을 그대로 잇는다. SEQUENCE 는 연도마다 새로 만들 수 없어(리셋을 매년 코드로 챙겨야 함)
    연도별 카운터 행(INSERT...ON CONFLICT DO UPDATE 한 문장)을 쓴다 — 그 한 문장 자체가 원자적이라 동시호출도
    겹치지 않고, 새 연도는 행이 없어 INSERT 가 그대로 그 해 1번부터 시작한다(연도 경계에 손댈 코드가 없다)."""
    year = int(time.strftime("%Y", time.gmtime(time.time() + 9 * 3600)))
    yy2 = "%02d" % (year % 100)
    last = conn.execute(
        "INSERT INTO proc_asset_no (year, next) VALUES (%s, %s)"
        " ON CONFLICT (year) DO UPDATE SET next = proc_asset_no.next + EXCLUDED.next"
        " RETURNING next", (year, count)).fetchone()[0]
    return ["WP%s %04d" % (yy2, n) for n in range(last - count + 1, last + 1)]


class _HopRecorder(urllib.request.HTTPRedirectHandler):
    """리다이렉트로 지나간 자리를 적어 둔다 — 거부당한 쓰기가 '본문이 틀린 것'인지 '본문이 도착도 못 한 것'인지
    다음번엔 가릴 수 있게(2026-09-09 시토).

    urllib 는 302 를 만나면 POST 를 GET 으로 바꾸고 본문을 버린다. Apps Script 표준 흐름
    (POST /exec → 302 → googleusercontent 의 출력)에서는 그게 맞다. 그런데 그 302 가 다시 /exec 을
    가리키면 doPost 대신 doGet 이 빈 손으로 돌아 GAS 가 「action 필수」라 답한다 — 화면엔 '잘못 보냈다'로
    보이지만 실제로는 본문이 GAS 에 닿지도 않은 것이다(2026-09-07 21:26~21:54 회원 7건 · 09-08 강습 1건,
    실무진이 28분간 같은 칸을 손으로 다시 눌렀다).

    지금은 자리만 남기고 동작은 안 바꾼다 — doPost 가 이미 돌았는지 모르는 채 자동 재시도로 돌리면
    결재·회원 쓰기가 두 번 들어간다. 다음 발생 때 _hops 를 보고 정하면 된다.
    """

    def __init__(self, hops):
        self.hops = hops

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        self.hops.append("%s→%s" % (code, str(newurl).split("?")[0]))
        return super().redirect_request(req, fp, code, msg, headers, newurl)


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
    for attempt in (1, 2):
        hops = []
        with urllib.request.build_opener(_HopRecorder(hops)).open(req, timeout=FORWARD_TIMEOUT) as r:
            final = r.geturl()
            data = json.loads(r.read().decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("GAS 응답이 객체가 아님")
        if resp_ok(data):
            return data
        if attempt == 1 and body_never_arrived(data):
            continue          # 본문이 안 닿은 것 — 아무것도 안 써졌으니 한 번 더 보낸다(중복 위험 없음)
        # 거부당한 것만 자취를 싣는다 — 원장(gas_response)에 남아 다음 조사 때 첫 줄이 된다.
        return dict(data, _hops=hops[:3], _final=str(final).split("?")[0], _tries=attempt)
    return data


# 담당 지정 권한 표 (배1182 · 2026-09-09 GM 지시 "각 담당자를 중간관리자들은 설정할 수 있게 해줘,
#   나우열M는 본인만 해야하는데, 다른 관리자들은 각 팀원들 담당자 정할 수 있도록"). GM_TASK_OWNERS 보드
#   (coo/chairman 담당 칸 · saveBoard) 저장 관문 여기 한 곳에서만 판정한다 — 화면(erp_write.js·
#   _owner_directive.js)은 이 규칙을 베끼지 않는다(약속 L01). 정본 = ssot/ownership_map.json 부서_리더.부서
#   (사람이 바뀌면 그 파일이 먼저 바뀐다) — server/** 는 ssot/ 없이 단독 배포돼(scp) sync_todo.STAFF 와
#   같은 방식으로 값을 여기 사본으로 둔다.
TASK_OWNER_TEAMS = {
    "이경연 실장": ["이경연 실장", "최준용M", "임정은M", "윤병현AM", "백승화 사원", "진수아 사원"],
    "이정헌 소장": ["이정헌 소장", "김종현 차장", "박호균 과장"],
    "나우열M": ["나우열M"],
}


def _owner_write_check(conn, user_email, board):
    """GM_TASK_OWNERS 담당 칸 저장 권한 — 이경연 실장·이정헌 소장은 본인 팀원까지, 나우열M 은 본인만
    바꿀 수 있다. GM(role=admin)·아직 개인 계정이 없어 이름이 안 갈리는 계정(사무실 공용 로그인 등)은
    막지 않는다 — 판정이 애매하면 통과시키는 쪽이 안전하다(배1182 note). 반환: (허용여부, 거부 사유)."""
    if not user_email or not isinstance(board, dict):
        return True, ""
    row = conn.execute("SELECT name, role FROM users WHERE tenant_id=%s AND email=%s",
                       (db.TENANT, user_email.strip().lower())).fetchone()
    if not row or row["role"] == "admin":
        return True, ""   # GM·미등록 계정 — 전부 허용
    actor_key = (row["name"] or "").replace(" ", "")
    leader, members = None, None
    for l, m in TASK_OWNER_TEAMS.items():
        if l.replace(" ", "") == actor_key:
            leader, members = l, m
            break
    if leader is None:
        return True, ""   # 실장·소장·나우열M 그 누구도 아님 — 이 규칙 대상이 아니다
    allowed = {m.replace(" ", "") for m in members}
    prev = conn.execute("SELECT data FROM board_cache WHERE tenant_id=%s AND key='GM_TASK_OWNERS'",
                        (db.TENANT,)).fetchone()
    before = (json.loads(prev["data"]).get("board") or {}) if prev else {}
    for task_id, owner in board.items():
        if before.get(task_id, "") == (owner or ""):
            continue   # 안 바뀐 칸 — 이 사람이 건드린 게 아니다
        if (owner or "").replace(" ", "") not in allowed:
            return False, "%s 님은 %s 만 담당으로 지정할 수 있습니다." % (leader, "·".join(members))
    return True, ""


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
    return server_ok(row["id"], queued=True, duplicate=True)


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
    if action == "saveBoard" and str(payload.get("key") or "") == "GM_TASK_OWNERS":
        owner_ok, owner_reason = _owner_write_check(conn, user, payload.get("board"))
        if not owner_ok:
            conn.close()
            return JSONResponse(status_code=403, content={
                "ok": False, "error": "owner-forbidden", "detail": owner_reason, "noRetry": True})
    prev = _idem_hit(conn, user, payload)   # 응답만 유실돼 같은 열쇠로 다시 온 요청 — GAS 를 두 번 치지 않는다
    if prev is not None:
        conn.close()
        return prev
    # 테스트/더미 페이로드 격리(AWS DB 더미 전수정리 · 2026-09-05) — 저장은 하되 GAS 로 안 보내고
    # 미러 동기화·리셉션 실패대비 정본도 안 건드린다. 운영 화면·집계는 gas_status='test' 행을 그대로 뺀다.
    is_test = db.is_test_payload(payload)
    area = origin_switch.WRITE_AREA.get(dest)
    server_mode = (bool(area) and origin_switch.mode(area) == "server" and not is_test
                   and action not in NO_SERVER_ACTIONS)   # 스위치 한 줄 — 재시작 없이 갈린다
    proc_no = None
    asset_labels = None
    if server_mode and dest == "PROC_GAS_URL" and action == "add":
        # 구매요청 번호 서버 채번(배 1195 ①) — GAS addItem() 규칙(열25 최댓값+1)을 서버가 잇는다.
        # payload·raw_body 에 no 를 실어 두면 되밀기(pushback.py)가 그대로 GAS 로 넘기고, GAS 는 그 번호를
        # 그대로 쓴다(procurement.js addItem 수정 — p.no 있으면 자체 채번을 건너뛴다). 새 칸 없이 기존
        # raw_body 왕복 하나로 끝난다.
        proc_no = _next_proc_no(conn)
        payload = dict(payload, no=proc_no)
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    elif server_mode and dest == "PROC_GAS_URL" and action == "asset_issue":
        # 자산 라벨 채번(배 1195 ②) — GAS assetIssue() 와 같은 두 관문(수량 1~100·품의번호 필수)을 먼저 통과시킨다.
        # 여기서 막으면 번호를 안 쓰니 결번도 안 생긴다 — GAS 가 어차피 같은 이유로 거부할 요청에 번호를 안 태운다.
        # 걸리면 labels 없이 그대로 queued 로 넘어간다(1분 뒤 GAS 가 bad_qty·no_req_key 로 거부 — 되밀기가 잡는다).
        try:
            _qty = int(str(payload.get("수량") or "0"))
        except (TypeError, ValueError):
            _qty = 0
        _req_key = str(payload.get("품의번호") or "").strip()
        if 1 <= _qty <= 100 and _req_key:
            asset_labels = _next_asset_labels(conn, _qty)
            payload = dict(payload, labels=asset_labels)
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    with conn:
        log_id = conn.execute(
            "INSERT INTO write_log (tenant_id, at, action, payload, user_email, gas_status, raw_body)"
            " VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id",
            (db.TENANT, _now_kst(), action, json.dumps(redact_blobs(payload), ensure_ascii=False), user,
             "test" if is_test else ("queued" if server_mode else "pending"),
             body.decode("utf-8") if server_mode else None)).fetchone()[0]
    if is_test:
        conn.close()
        return server_ok(log_id, test=True)
    if server_mode:
        # 서버 원본 — GAS 왕복을 안 기다린다. 시트는 pushback.py(1분)가 채우고 거울도 그때 다시 뜬다.
        conn.close()
        extra = {}
        if proc_no is not None:
            extra["no"] = proc_no
        if asset_labels is not None:
            extra["labels"] = asset_labels
        return server_ok(log_id, queued=True, mode="server", **extra)
    try:
        # 리셉션 업무·라커관리는 본문 모양으로만 갈린다(배 960 #9i) — 나머지는 종전 액션 접두사 표.
        resp = _gas_forward(body, dest)
        status = "ok" if resp_ok(resp) else "gas-error"
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
    assert resp_ok({"success": True, "saved": 3}) is True     # 배 1067 — ok 칸 없어도 success 로 성공
    assert resp_ok({"ok": True}) is True
    assert resp_ok({"ok": False, "error": "bad-token"}) is False
    assert resp_ok({"success": False}) is False
    assert resp_ok({}) is True                                 # 둘 다 없으면 성공으로 친다
    assert resp_ok("not-a-dict") is True
    # 본문 미도달 판정 — 이것만 재전송 대상이다(GAS 가 본문을 봤으면 다시 보내면 두 줄이 된다).
    assert body_never_arrived({"ok": False, "error": "action 필수"}) is True
    assert body_never_arrived({"ok": False, "error": "알 수 없는 action: x"}) is False   # 본문은 닿았다
    assert body_never_arrived({"ok": False, "error": "archive-not-found"}) is False
    assert body_never_arrived({"ok": True}) is False and body_never_arrived("x") is False
    assert _gas_key("reg_update") == "RECEPTION_EXEC_URL"
    assert _gas_key("lf_submit") == "RECEPTION_EXEC_URL"
    assert _gas_key("hold_complete") == "RECEPTION_EXEC_URL"
    assert _gas_key("member_hold_approve") == "FUNNEL_EXEC_URL"   # member_* 는 접수 GAS 로 새면 안 된다
    assert _gas_key("lesson_inquiry_add") == "FUNNEL_EXEC_URL"
    assert _gas_key("todo_update") == "TODO_GAS_URL" and _gas_key("approval_rep_cancel") == "TODO_GAS_URL"
    assert _gas_key("notice_save") == "TODO_GAS_URL" and _gas_key("notice_delete") == "TODO_GAS_URL"   # 배 1082
    assert "notice_save" not in MIRROR_SYNC and "notice_delete" not in MIRROR_SYNC   # 거울 없음
    # 배 1039 폼류4종 — 상품기획은 화면 실제 목적지(TODO_API_URL)와 같은 업무 GAS. FUNNEL 로 새면 안 된다.
    assert _gas_key("product_plan_save") == "TODO_GAS_URL" and _gas_key("product_plan_delete") == "TODO_GAS_URL"
    assert "product_plan_save" not in MIRROR_SYNC and "product_plan_delete" not in MIRROR_SYNC   # 거울 없음
    # staff_feedback_photo — 화면 FB_PHOTO_URL 과 서버 INSTRUCTOR_GAS_URL 이 같은 배포 ID(실측 2026-09-05).
    assert _gas_key("staff_feedback_photo") == "INSTRUCTOR_GAS_URL"
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
    for _a in ("member_owner_save", "member_inquiry_delete", "lesson_inquiry_update",
               "staff_feedback_submit", "ohnutti_team_list", "client_write_fail"):
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
    for _a in ("unlock_round", "todo_upload", "save_schedule"):
        assert _a in NO_SERVER_ACTIONS, "%s 를 서버 원본으로 보내면 사람에게 거짓말이 된다" % _a
        assert _gas_key(_a) is not None, "%s 는 목적지 표에 있어야 dual 로 돌아간다" % _a
    assert "id" not in server_ok(9, mode="server"), "서버 응답에 id 를 담으면 화면이 접수번호로 오해한다"
    assert server_ok(9, mode="server") == {"ok": True, "success": True, "logId": 9, "mode": "server"}
    assert _idem_hit(_C(), "a@b.c", {"idem": "u1"})["queued"] is True                # 아직 진행 중 = 두 번 쓰지 않는다

    # 담당 지정 권한(배1182) — GM_TASK_OWNERS saveBoard 판정. 가짜 conn: SELECT 대상(users·board_cache)로 갈라 응답.
    class _OwnerConn:
        def __init__(self, user_row, board_data):
            self.user_row, self.board_data = user_row, board_data

        def execute(self, q, p=None):
            self._q = q
            return self

        def fetchone(self):
            if "FROM users" in self._q:
                return self.user_row
            if "FROM board_cache" in self._q:
                return {"data": json.dumps({"ok": True, "board": self.board_data}, ensure_ascii=False)}
            return None

    _BOARD_NOW = {"t1": "이경연 실장", "t2": "김남욱 GM"}
    _sil = {"name": "이경연 실장", "role": "staff"}
    ok, why = _owner_write_check(_OwnerConn(_sil, _BOARD_NOW), "leekyungyeon@wellperion.com",
                                 {"t1": "최준용M", "t2": "김남욱 GM"})
    assert ok and why == "", why                              # 실장이 본인 팀원(최준용M)으로 바꾼다 — 허용
    ok, why = _owner_write_check(_OwnerConn(_sil, _BOARD_NOW), "leekyungyeon@wellperion.com",
                                 {"t1": "김종현 차장", "t2": "김남욱 GM"})
    assert not ok and "이경연 실장" in why                        # 남의 팀(시설부)으로 바꾼다 — 거부
    ok, why = _owner_write_check(_OwnerConn(_sil, _BOARD_NOW), "leekyungyeon@wellperion.com",
                                 {"t1": "이경연 실장", "t2": "김남욱 GM"})
    assert ok                                                 # 안 바뀐 칸은 검사 대상이 아니다
    _naw = {"name": "나우열M", "role": "staff"}
    ok, why = _owner_write_check(_OwnerConn(_naw, _BOARD_NOW), "nawoolm@wellperion.com", {"t1": "최준용M"})
    assert not ok                                             # 나우열M 은 본인만 지정 가능
    ok, why = _owner_write_check(_OwnerConn(_naw, _BOARD_NOW), "nawoolm@wellperion.com", {"t1": "나우열M"})
    assert ok
    _gm = {"name": "GM", "role": "admin"}
    ok, why = _owner_write_check(_OwnerConn(_gm, _BOARD_NOW), "cao@wellperion.com", {"t1": "아무개나"})
    assert ok                                                 # GM(admin) 은 전부 지정 가능
    _unknown = {"name": "홍길동 매니저", "role": "staff"}
    ok, why = _owner_write_check(_OwnerConn(_unknown, _BOARD_NOW), "hong@wellperion.com", {"t1": "아무개나"})
    assert ok                                                 # 3라인 리더가 아닌 계정 — 이 규칙 대상이 아니다, 막지 않는다
    ok, why = _owner_write_check(_OwnerConn(None, _BOARD_NOW), "unknown@wellperion.com", {"t1": "아무개나"})
    assert ok                                                 # 미등록 계정(개인 계정 발급 전) — 막지 않는다

    # 구매요청 번호 채번(배 1195 ①) — 가짜 시퀀스 conn: nextval 호출마다 1씩 올라간 값을 준다(중복 불가 흉내).
    class _SeqConn:
        n = 130   # 2026-09-10 실측 시트 최댓값(active 20건+done 326건 전수 스캔) — 배포 seed 값과 같아야 한다

        def execute(self, q, p=None):
            assert "nextval" in q and "proc_no_seq" in q
            _SeqConn.n += 1
            self._v = _SeqConn.n
            return self

        def fetchone(self):
            return (self._v,)

    seen = set()
    for _ in range(5):
        n = _next_proc_no(_SeqConn())
        assert n not in seen, "같은 번호가 두 번 나왔다"   # 서버 채번 자체점검 핵심 — 중복 불가
        seen.add(n)
    assert sorted(seen) == list(range(131, 136)), seen        # 130 다음부터 1씩 순서대로
    assert server_ok(9, queued=True, mode="server", no=131) == {
        "ok": True, "success": True, "logId": 9, "queued": True, "mode": "server", "no": 131}

    # 자산 라벨 채번(배 1195 ②) — 가짜 연도별 카운터 conn: INSERT...ON CONFLICT 문 하나만 받는다(원자적 채번 흉내).
    class _AssetConn:
        rows = {}   # {year: next} — 배포 seed(2026:3) 를 흉내

        def execute(self, q, p=None):
            assert "proc_asset_no" in q and "ON CONFLICT" in q
            year, count = p
            _AssetConn.rows[year] = _AssetConn.rows.get(year, 0) + count
            self._v = _AssetConn.rows[year]
            return self

        def fetchone(self):
            return (self._v,)

    _AssetConn.rows = {2026: 3}   # 2026-09-10 실측(라벨 2장·결번 있어 최댓값 3)
    labels1 = _next_asset_labels(_AssetConn(), 2)
    assert labels1 == ["WP26 0004", "WP26 0005"], labels1     # 3 다음부터 이어받는다
    labels2 = _next_asset_labels(_AssetConn(), 1)
    assert labels2 == ["WP26 0006"], labels2                  # 두 번째 호출도 이어서(겹침 없음)
    assert len(set(labels1 + labels2)) == 3, "라벨이 겹쳤다"
    labels3 = _next_asset_labels(_AssetConn(), 3)
    assert labels3 == ["WP26 0007", "WP26 0008", "WP26 0009"], labels3   # 계속 이어감
    assert len(labels3) == 3, "요청 수량과 발급 개수가 다르다"
    _AssetConn.rows = {}   # 새 연도(행 없음) — INSERT 가 1번부터 새로 시작(연도 경계 리셋을 코드 없이 확인)
    labels_ny = _next_asset_labels(_AssetConn(), 2)
    assert labels_ny == ["WP26 0001", "WP26 0002"], labels_ny
    print("자체점검 통과")
