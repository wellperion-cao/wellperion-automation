# -*- coding: utf-8 -*-
"""회원 쓰기 서버 원장 — POST /api/members/write (배1050 1단계 · 배1054 2·3·4단계 · 시토).

member_owner_save(종목별 담당자 5칸 · 1단계) · member_hold_transition(휴회접수상태 1칸 · 2단계) ·
member_active_update(칸 자유 쓰기 · 3단계) · member_hold_approve(휴회 승인/반려 · 2원장 · 4단계) 를
여기서 서버 원장(members + hold_items)에 먼저 쓴다 — ①검증 ②서버 원장 갱신 + member_change_log 이력
1줄(한 트랜잭션 · 값 같으면 이력 없이 ok) ③기존 GAS 로 write-through(시트도 유지 · api_write._gas_forward
재사용 · 실패해도 서버 저장은 이미 끝남 — 응답 gas_status 로만 알린다).
나머지 3종(member_registered_add 등)은 아직 이 라우트에 안 왔다 — 501 로 /api/write(GAS 경로)를 쓰라고
안내한다(화면이 잘못 붙어도 조용히 실패하지 않게).
정본 = status/briefs/CPO-2026-09-05-회원쓰기7종-서버원장-스펙.md §2-1·2-2·2-6·2-7.

행 찾기 — member_hold_approve(_handle_member_hold_approve): 접수 행 = hold_items 미러(intake_row 열쇠 ·
sync_reception.py 가 5분마다 GAS member_hold_intake_list 를 그대로 얹는다) 를 FOR UPDATE 로 잠그고 그
자리에서 status 를 재검사한다 — GAS 원본(Survey.js L10708~10783)은 접수 상태를 전혀 안 보고 그대로
증분해 같은 승인을 두 번 누르면 횟수·누적일이 두 번 오르는 결함이 있다(시포 스펙 §2-7 결함②). 서버는
status != '접수대기' 면 GAS 로 넘기지 않고 즉시 no-op 을 돌려준다(회원 원장 무변경·이력 없음·GAS 미호출 —
GAS 로 넘기면 GAS 자신의 결함으로 거기서도 두 번째 증분이 일어난다). 회원 행은 접수 행의 전화(mirror
phone)로 찾는다(GAS 와 동일한 fail-closed: 0건=member-not-found·2건+=member-ambiguous).

행 찾기 — member_owner_save·member_hold_transition(_find_and_lock): payload 에 member_no 가 있으면
번호로 먼저 찾고 전화도 일치해야 한다(불일치=400 거부 · GAS 는 member_no 를 무시하고 그대로 write-through).
member_no 가 없으면 전화 정규화 첫 매칭 1행(member_no 오름차순 — 시트엔 없는 순서 개념이라 이걸로 대신한다).
두 경우 다 SQL 이 phone=%s 로 필터링해 행의 전화가 비어 있으면 애초에 안 걸린다 — GAS keyPhone 폴백의
fail-open(행 전화 빈칸이면 통과 · Survey.js L10808)이 서버에는 구조적으로 없다(결함① 반영 · 배1054).
'컬럼 미발견'·'유효회원 시트 없음' 류 오류는 서버에서 뺐다 — schema.sql 이 컬럼을 고정 보장해 발생할 수 없다.

행 찾기 — member_active_update(_resolve_active_row): 화면이 아직 rowIndex+rowKey(또는 keyPhone)를 보낸다
(물리 시트 행 좌표 — 서버엔 그런 개념이 없다). rowIndex 는 서버 쪽 조회에 안 쓴다 — GAS 로 그대로
write-through 될 때 GAS 자신의 지문 스캔이 시트 물리 행을 다시 확정하므로(약속 L21·행 재구현 금지), 서버는
member_no 하나만 확정하면 된다. 변환은 3단 그대로: ① member_no 명시 시 그 행 + 전화 대조 ② rowKey
('tsNorm|phoneNorm[|nameNorm]') — 미러 members.data JSON 의 rowKey(=GAS 가 같은 재료로 계산해 매 sync 마다
실어 보내는 값)와 정확히 같은 행을 찾는다(전수 스캔 대신 값 대조 — 결과는 같다: 1건=확정) · 0건이면 keyPhone/
rowKey 의 전화 조각으로 단독 매칭 1건일 때만 복구(GAS Survey.js L9708 이식) · 2건+(가족 동일 지문)는 서버엔
물리행 후보 비교가 없어 rowkey-ambiguous 로 거부(회원번호로 재시도 요구) ③ 지문 없으면 keyPhone 단독 매칭.
저장 칸 = 화이트리스트 없음(GAS 그대로) — 미리 약속한 21칸(_ACTIVE_COL_MAP, 이미 있던 sync 컬럼 12 + 배1054
3단계 신설 9)은 실컬럼에, 그 밖의 칸은 members.data(JSON) 에 직접 patch(jsonb_set) 한다 — GAS 가 실제로
그 헤더를 못 찾으면 write-through 가 gas-error 로 거부하고 우리 쪽도 되돌린다(_finish revert). updates[]
(최대 30건 일괄)는 GAS 와 같은 재진입 방식 — 항목마다 부모 payload 를 상속해 단건 경로를 그대로 다시 탄다.

테스트/더미 payload(db.is_test_payload — /api/write·/api/intake 와 같은 판별기)는 tenant 'selftest' 에서만
행을 찾고 고친다(실 회원 tenant 'wellperion' 은 안 건드림) · GAS 전달도 안 한다(gas_status='skipped-test' ·
dry-run · 배1054 검증 반영 2026-09-06).

자체점검: python3 api_members_write.py   (DB·네트워크 없음 — 필드매핑·마스킹·직원표기·상태검증 판정만)
"""
import json
import os
import re
import sys

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # 저장소 server/ = 서버 /srv/erp/
from common import db  # noqa: E402  — DB 를 여는 유일한 자리
import api_write  # noqa: E402  — GAS 포워드·거울 재동기화 재사용(로직 중복 금지)

router = APIRouter(prefix="/api/members")

# 화이트리스트 5칸 — GAS mosAllowed 그대로(Survey.js L10329~10367). 늘리려면 schema.sql 컬럼도 같이 추가.
FIELD_TO_COL = {
    "PT 담당자": "owner_pt", "골프 담당자": "owner_golf", "P.L 담당자": "owner_pl",
    "스쿼시 담당자": "owner_squash", "수영 담당자": "owner_swim",
}
HOLD_STATUSES = ("완료", "진행중")            # GAS 화이트리스트 그대로(Survey.js L10793)
HOLD_COL = "hold_status"
HOLD_FIELD_LABEL = "휴회접수상태"              # member_change_log 의 field 칸 · GAS 헤더명과 동일
# 아직 이 라우트가 처리 안 하는 나머지 3종(시포 스펙 §2-3~2-5) — 501 안내에만 쓴다(화이트리스트 아님).
_NOT_YET = ("member_registered_add", "member_registered_remove", "member_archive_restore")
_IMPLEMENTED = ("member_owner_save", "member_hold_transition", "member_active_update", "member_hold_approve")

# member_hold_approve(4단계 · 배1054) — 승인 시 갱신 6칸(GAS Survey.js L10762~10766 이식). schema.sql 이
# 2단계 때 미리 만들어 둔 hold_* 칸(hold_status 는 2단계가 이미 씀 · 나머지 5개는 이 단계가 처음 쓴다) —
# sync_members.py OWNER_COLS·reconcile_dual_write.py 대조가 같은 라벨을 재사용한다(순환 임포트 방지 사본).
HOLD_PERIOD_LABEL = "휴회기간(휴회일수)"       # GAS HOLD_PERIOD_COL 상수와 같은 값
HOLD_APPROVE_COL_MAP = {
    "hold_period": HOLD_PERIOD_LABEL, "hold_start_date": "휴회시작일", "hold_end_date": "휴회종료일",
    "hold_count": "휴회횟수", "hold_cum_days": "휴회누적일수", "hold_status": HOLD_FIELD_LABEL,
}
HOLD_MAX_COUNT, HOLD_MAX_TOTAL, HOLD_MIN_ONCE, HOLD_MAX_ONCE = 3, 60, 7, 60   # GAS HLD_* 상수 그대로
HOLD_KIND_EXTEND = "연장"                     # GAS HLD_KIND_EXTEND — 연장은 1회 하한이 면제(1~60일)

# member_active_update(3단계 · 배1054) — 칸 이름(공백 제거 정규화) → 실컬럼. GAS 는 화이트리스트 없이 시트
# 헤더에 있는 칸이면 뭐든 쓰지만(_auFindCol), 서버는 미리 컬럼을 둔 칸만 실컬럼에 쓰고 나머지는
# members.data(JSON) 에 직접 patch 한다(_active_write_one 참조) — 자유 쓰기 계약은 그대로 유지된다.
# 앞 12개는 sync_members.py COLS 가 이미 미러링하는 기존 실컬럼 재사용(새 스키마 불필요 · 5분 배치가 항상
# 최신으로 되돌려 놓으므로 sync_owner_cols 예외 대상이 아니다). 뒤 9개는 배1054 3단계 신설(schema.sql) —
# replace_scope() 가 안 건드리는 칸이라 OWNER_COLS 에도 넣어(sync_members.py) 얼어붙지 않게 한다.
_ACTIVE_COL_MAP = {
    "회원명": "name", "회원구분": "kind", "세부구분": "kind2", "수강반종목명": "program",
    "등록분류": "reg_class", "등록회차": "reg_seq", "등록일자": "reg_date",
    "시작일자": "start_date", "종료일자": "end_date", "LOSS일자": "loss_date",
    "잔여일(일)": "remain_days", "담당자": "owner",
    "주소": "address", "비고": "note", "나이": "age",
    "재등록상담날짜": "reg_consult_date", "재등록상담시간": "reg_consult_time", "재등록상담내용": "reg_consult_note",
    "재등록예약목록": "reg_reservation", "종료사유": "end_reason", "종료사유메모": "end_reason_memo",
}
ACT_RES_COL = "재등록예약목록"   # GAS Survey.js L2356 상수와 같은 값 — 저장 시 재등록상담 3칸으로 미러(L9854~9862 이식)
_ACTIVE_ERRORS = {   # GAS 오류 문구 그대로(Survey.js L9678·9691·9743·9762·9776) — 서버는 물리행 대신 member_no 로 판정
    "unverified": {"ok": False, "error": "row-key-unverified",
                   "detail": "행 확인 불가 — 연락처 확인 후 목록 새로고침하여 다시 시도하세요"},
    "not_found": {"ok": False, "error": "rowkey-not-found",
                  "detail": "행 확인 불가(지문 불일치) — 목록 새로고침 후 다시 시도하세요"},
    "ambiguous": {"ok": False, "error": "rowkey-ambiguous", "noRetry": True,
                  "detail": "지문키 중복 매칭 — 회원번호(member_no)를 포함해 다시 시도하세요"},
    "member_no_mismatch": {"ok": False, "error": "member_no-phone-mismatch", "noRetry": True,
                           "detail": "회원번호와 전화번호가 일치하지 않습니다"},
}


def _norm_phone(v):
    return re.sub(r"\D", "", str(v or ""))


def _hold_min_once(kind):
    """GAS _holdMinOnce_ 이식 — 연장은 1일부터, 신규는 최소 7일(Survey.js L10566)."""
    return 1 if kind == HOLD_KIND_EXTEND else HOLD_MIN_ONCE


def _hold_end_calc(start, days):
    """GAS _holdEndCalc_ 이식(Survey.js L10571) — 시작일 + (일수-1)일 = 종료일."""
    from datetime import datetime, timedelta   # noqa: PLC0415 — 이 함수 하나만 쓴다
    d = datetime.strptime(start, "%Y-%m-%d") + timedelta(days=days - 1)
    return d.strftime("%Y-%m-%d")


def _hold_num(v):
    """GAS _amNum 이식(Survey.js L10741 부근) — 숫자·부호 아닌 문자 제거 후 parseInt, 실패하면 0.
    hold_count·hold_cum_days 는 schema.sql 에 TEXT 로 있다(GAS 시트 셀 값 그대로 옮긴 사본)."""
    raw = re.sub(r"[^0-9\-]", "", str(v or ""))
    try:
        return int(raw)
    except ValueError:
        return 0


def _norm_col(v):
    """칸 이름 정규화 — 공백·줄바꿈 전부 제거(GAS `.replace(/\\s/g,'')`와 동일). 헤더가 '잔여일\\n(일)'처럼
    줄바꿈이 섞여 있어도 매칭되게 한다."""
    return re.sub(r"\s+", "", str(v or ""))


_ACTIVE_BLOCKED_FIELDS = ("휴대폰", "회원번호")   # 부분일치(포함) 차단 — 열쇠 칸은 이 라우트로 못 고친다
_ACTIVE_BLOCKED_KEYS = ("rowkey", "rowindex")      # 정확일치 차단(영문 지문키 필드명 · 시트 헤더가 아니다)


def _is_active_blocked_field(fname):
    n = _norm_col(fname)
    if any(b in n for b in _ACTIVE_BLOCKED_FIELDS):
        return True
    return n.lower() in _ACTIVE_BLOCKED_KEYS


def _data_get_norm(data_obj, fname):
    """members.data(JSON) 키를 공백 정규화로 찾는다(원본 JSON 은 시트 헤더 그대로라 공백이 섞일 수 있다 ·
    reconcile_dual_write.py 대조와 같은 정규화, 배1054 검토⑤·⑥ 사본). 반환 (실제 키, 발견 여부)."""
    nk = _norm_col(fname)
    for k in data_obj:
        if _norm_col(k) == nk:
            return k, True
    return fname, False


def _mask_phone(v):
    """GAS _logMaskPhone_ 이식(Survey.js L1260) — 뒤 4자리를 가리고 앞은 그대로(010-1234-****). 8자리 미만은 원본."""
    d = re.sub(r"\D", "", str(v or ""))
    if len(d) < 8:
        return str(v or "")
    head = d[:-4]
    m = re.match(r"(\d{3})(\d+)", head)
    return (m.group(1) + "-" + m.group(2) if m else head) + "-****"


def _log_who(payload, user=""):
    """GAS _logWho_ 이식(Survey.js L1268) 확장 — staff 키 자체가 없으면 요청 헤더 x-erp-user, 그것도
    없으면 '자동'(자동접수). staff 키가 있는데 비어 있으면 '이름미상'(GAS 그대로 · 배1054 검토④)."""
    if not isinstance(payload, dict) or "staff" not in payload:
        return str(user or "").strip() or "자동"
    return str(payload.get("staff") or "").strip() or "이름미상"


def _find_and_lock(conn, tenant, col, member_no_in, phone):
    """member_no 있으면 번호로 찾고 전화 일치 확인(불일치=mismatch) · 없으면 전화 매칭(member_no 오름차순 최대 2건 조회).
    전화 매칭이 2건 이상이면 첫 행에 조용히 쓰지 않고 ambiguous 로 거부한다(GAS Survey.js:10802 규칙 이식 ·
    가족 회원 같은 번호 실사례 · 배1054 검토③). 반환 (row|None, mismatch:bool, ambiguous:bool).
    row 는 member_no·name·phone·val(해당 칸) 을 담은 DictRow."""
    if member_no_in:
        row = conn.execute(
            ("SELECT member_no, name, phone, {col} AS val FROM members"
             " WHERE tenant_id=%s AND scope='valid' AND member_no=%s FOR UPDATE").format(col=col),
            (tenant, member_no_in)).fetchone()
        if row and _norm_phone(row["phone"]) != phone:
            return None, True, False
        return row, False, False
    rows = conn.execute(
        ("SELECT member_no, name, phone, {col} AS val FROM members"
         " WHERE tenant_id=%s AND scope='valid' AND phone=%s ORDER BY member_no LIMIT 2 FOR UPDATE").format(col=col),
        (tenant, phone)).fetchall()
    if len(rows) > 1:
        return None, False, True
    return (rows[0] if rows else None), False, False


def _resolve_active_row(conn, tenant, payload):
    """member_active_update 전용 — rowIndex+rowKey(또는 keyPhone) → member_no 행 변환(FOR UPDATE).
    반환 (row|None, error_code|None). error_code 는 _ACTIVE_ERRORS 의 키 중 하나(성공 시 None).
    GAS 의 지문 3단 복구(Survey.js L9678~9776)를 '물리 행 스캔' 대신 '미러 rowKey 값 대조'로 재현한다 —
    member_no 가 곧 서버의 행 열쇠라 물리행 후보 비교(지문 중복 시 rowIndex 로 고르는 GAS 마지막 단)는
    필요 없다(회원번호 명시를 요구하는 쪽이 더 안전 — INC-020 원칙)."""
    member_no_in = str(payload.get("member_no") or "").strip()
    row_key = str(payload.get("rowKey") or "").strip()
    key_phone = _norm_phone(payload.get("keyPhone"))
    rk_parts = row_key.split("|") if row_key else []
    rk_phone = _norm_phone(rk_parts[1]) if len(rk_parts) > 1 else ""
    phone = key_phone or rk_phone

    if member_no_in:
        if not phone:   # 회원번호만 오고 전화 대조 재료가 없으면 거부(GAS Survey.js:9781 과 동일 · 배1054 검토②)
            return None, "unverified"
        row = conn.execute(
            "SELECT * FROM members WHERE tenant_id=%s AND scope='valid' AND member_no=%s FOR UPDATE",
            (tenant, member_no_in)).fetchone()
        if not row:
            return None, "not_found"
        if _norm_phone(row["phone"]) != phone:
            return None, "member_no_mismatch"
        return row, None

    if row_key:
        rows = conn.execute(
            "SELECT * FROM members WHERE tenant_id=%s AND scope='valid' AND data::jsonb->>'rowKey'=%s FOR UPDATE",
            (tenant, row_key)).fetchall()
        if len(rows) == 1:
            return rows[0], None
        if not rows:
            if phone:   # 지문 미스 복구 — 전화 단독 매칭 정확히 1건일 때만(GAS Survey.js L9708 이식)
                cand = conn.execute(
                    "SELECT * FROM members WHERE tenant_id=%s AND scope='valid' AND phone=%s FOR UPDATE",
                    (tenant, phone)).fetchall()
                if len(cand) == 1:
                    return cand[0], None
            return None, "not_found"
        return None, "ambiguous"   # 2건+(가족 동일 지문) — 물리행 후보비교가 없어 회원번호 명시를 요구한다

    if phone:
        rows = conn.execute(
            "SELECT * FROM members WHERE tenant_id=%s AND scope='valid' AND phone=%s FOR UPDATE",
            (tenant, phone)).fetchall()
        if len(rows) == 1:
            return rows[0], None
        if not rows:
            return None, "not_found"
        return None, "ambiguous"

    return None, "unverified"


_CONTACT_BY_RE = re.compile(r"\s*\(컨택:([^()]*)\)\s*$")   # GAS CONTACT_BY_RE(Survey.js L2371) 사본


def _parse_first_reservation(raw):
    """ACT_RES_COL(재등록예약목록) 값(JSON 배열 문자열 또는 이미 파싱된 리스트)의 첫 '유효' 예약 date/time/note.
    GAS `_resParse_`(Survey.js L2384) 이식 — date/time/note/by 가 전부 빈 항목은 건너뛰고 첫 유효 항목을
    쓴다(배열 첫 칸이 빈 값으로 밀린 옛 데이터 대비). note 끝의 '(컨택:이름)' 마커(GAS `_ctBySplit_`)는
    떼어내고 저장한다. ponytail: 날짜·시간 정규화(_miToISO_·_miTime_)는 생략하고 원본 문자열을 그대로 쓴다
    — 이 미러는 달력 폴백 안전망일 뿐 주 저장소가 아니다(재등록예약목록 원본은 그대로 남아 무손실).
    정규화가 필요해지면 그때 추가한다."""
    try:
        arr = raw if isinstance(raw, list) else json.loads(str(raw or "").strip() or "[]")
    except Exception:
        return "", "", ""
    if not isinstance(arr, list):
        return "", "", ""
    for it in arr:
        if not isinstance(it, dict):
            continue
        d = str(it.get("date") or "")
        t = str(it.get("time") or "")
        n = "" if it.get("note") is None else str(it.get("note"))
        by = str(it.get("by") or "").strip()
        m = _CONTACT_BY_RE.search(n)
        if m:
            n = _CONTACT_BY_RE.sub("", n).strip()
            by = by or m.group(1).strip()
        if not d and not t and not n and not by:
            continue
        return d, t, n
    return "", "", ""


def _finish(conn, body, log_id, is_test, extra, revert=None):
    """두 세 액션 공통 꼬리 — GAS write-through + write_log.gas_status 갱신 + 거울 재동기화 스케줄.
    extra(dict) 를 응답에 얹는다. is_test 면 GAS 는 아예 안 부른다(dry-run).
    GAS 가 거부하거나(예: {ok:false,error:'hold-gated'}) 안 닿으면(forward-failed), 서버 원장은 이미
    갱신된 뒤이므로 revert(있으면 · 값이 실제로 바뀐 호출만) 로 보상 UPDATE + 취소 이력을 남기고
    ok=False + GAS 의 error 를 그대로 실어 돌려준다 — membership.html 의 d.ok===false/hold-gated
    분기가 살아난다(배1054 검토②).
    revert = 단일 dict(owner_save·hold_transition — 기존 그대로) 또는 dict 의 리스트(member_active_update·
    member_hold_approve — 한 저장이 여러 칸/두 표를 동시에 바꿀 수 있어 항목마다 하나씩). 각 항목의
    kind='json' 이면 실컬럼이 아니라 members.data(JSON) 를 되돌리고, kind='hold' 면 hold_items(접수 행)
    status·data 를 되돌린다(회원 이력 없음 — 4단계). kind 없음/'col'=기존처럼 members 실컬럼 UPDATE(하위호환)."""
    reverts = revert if isinstance(revert, list) else ([revert] if revert else [])
    if is_test:
        conn.close()
        return dict(extra, ok=True, _source="server", gas_status="skipped-test")
    try:
        resp = api_write._gas_forward(body, "FUNNEL_EXEC_URL")
        gas_status = "ok" if resp.get("ok") else "gas-error"
    except Exception as e:
        resp = {"ok": False, "error": "server-forward-failed", "detail": "%s: %s" % (type(e).__name__, str(e)[:200]), "noRetry": False}
        gas_status = "forward-failed"
    gas_ok = gas_status == "ok"
    try:
        with conn:
            conn.execute("UPDATE write_log SET gas_status=%s, gas_response=%s WHERE id=%s",
                         (gas_status, json.dumps(resp, ensure_ascii=False)[:20000], log_id))
            if not gas_ok:
                for rv in reverts:
                    if rv.get("kind") == "hold":   # member_hold_approve(4단계) — 접수 행 상태·JSON 복원, 회원 이력 없음
                        conn.execute("UPDATE hold_items SET status=%s, data=%s WHERE tenant_id=%s AND intake_row=%s",
                                     (rv["old_status"], rv["old_data"], rv["tenant"], rv["intake_row"]))
                        continue
                    if rv.get("kind") == "json":
                        if rv.get("had_key", True):
                            conn.execute(
                                "UPDATE members SET data=jsonb_set(data::jsonb, %s, to_jsonb(%s::text), true)::text"
                                " WHERE tenant_id=%s AND member_no=%s AND scope='valid'",
                                ([rv["json_field"]], rv["old_value"], rv["tenant"], rv["member_no"]))
                        else:   # 원래 키 자체가 없었다 — ""로 되돌리면 빈 그림자 키가 남는다(배1054 검토⑦)
                            conn.execute(
                                "UPDATE members SET data=(data::jsonb - %s)::text"
                                " WHERE tenant_id=%s AND member_no=%s AND scope='valid'",
                                (rv["json_field"], rv["tenant"], rv["member_no"]))
                    else:
                        conn.execute(
                            "UPDATE members SET {col}=%s WHERE tenant_id=%s AND member_no=%s AND scope='valid'".format(col=rv["col"]),
                            (rv["old_value"], rv["tenant"], rv["member_no"]))
                    conn.execute(
                        "INSERT INTO member_change_log (tenant_id, at, staff, member_no, member_name, phone_masked,"
                        " field, old_value, new_value, screen) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                        (rv["tenant"], api_write._now_kst(), "시스템(GAS거부롤백)", rv["member_no"], rv["name"],
                         rv["phone_masked"], rv["field"], rv["new_value"], rv["old_value"], "멤버십"))
    except Exception:
        conn.close()
        raise
    conn.close()
    if not gas_ok:
        return dict(extra, ok=False, _source="server", gas_status=gas_status,
                    error=(resp.get("error") or "gas-error"), detail=resp.get("detail"))
    api_write._schedule_sync("sync_members.py")
    out = dict(extra, ok=True, _source="server", gas_status=gas_status)
    if isinstance(resp.get("saved"), dict):   # GAS 되읽은 값 우선(화면 _verifySavedInline 이 조용한 거부를 잡게 · 배1054 검토③)
        out["saved"] = resp["saved"]
    return out


def _member_no_mismatch(member_no_in):
    return JSONResponse(status_code=400, content={
        "ok": False, "error": "member_no-phone-mismatch", "noRetry": True,
        "detail": "회원번호(%s)와 전화번호가 일치하지 않습니다" % member_no_in})


def _member_active_update_one(payload, raw_body, user):
    """member_active_update 한 건 — 행 변환 → 칸 저장(실컬럼 우선·나머지 data JSON patch) → 이력 →
    write_log → GAS write-through(_finish). 항상 plain dict 를 돌려준다(일괄 처리가 그대로 모아 쓴다).
    GAS 원본(Survey.js L9624~9880) 대비: rowIndex 필수 검증·컬럼 미발견 오류는 뺐다(서버는 물리행이 없고
    schema.sql 이 칸을 고정 보장) — 그 대신 write-through 가 gas-error 로 걸러 준다."""
    fields = payload.get("fields") if isinstance(payload.get("fields"), dict) else None
    col = str(payload.get("col") or "").strip()
    if not fields and not col:
        return {"ok": False, "error": "col 또는 fields 필수"}

    now = api_write._now_kst()
    is_test = db.is_test_payload(payload)
    tenant = "selftest" if is_test else db.TENANT

    try:
        conn = db.connect()
    except db.Error as e:
        return {"ok": False, "error": "server-forward-failed", "detail": "DB 열기 실패: %s" % e, "noRetry": False}

    err_code, log_id, reverts, extra = None, None, None, None
    try:
        with conn:
            row, err_code = _resolve_active_row(conn, tenant, payload)
            if not row and err_code in ("not_found", "ambiguous"):
                # 서버 미러엔 회원번호 없어 못 찾거나(시트 원행에 회원번호가 없어 애초에 안 실림) 전화
                # 지문이 겹쳐 후보가 여럿이라(②) 서버는 못 고르지만, GAS 는 물리 시트를 직접 스캔해
                # rowIndex 로 확정할 수 있다 — 서버 원장은 안 건드리고 GAS 로만 그대로 전달한다
                # (pass-through · 응답은 GAS 것을 그대로 · 배1054 검토③). keyPhone 자체가 빈 'unverified'는
                # 여전히 fail-closed(서버가 판단할 재료가 아예 없다).
                payload_log = dict(payload)
                log_id = conn.execute(
                    "INSERT INTO write_log (tenant_id, at, action, payload, user_email, gas_status, raw_body)"
                    " VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                    (tenant, now, "member_active_update", json.dumps(payload_log, ensure_ascii=False), user,
                     "test" if is_test else "pending", None)
                ).fetchone()[0]
                extra = {"passThrough": True}
                err_code = None
            elif row:
                row = dict(row)
                member_no = row["member_no"]
                staff = _log_who(payload, user)
                try:
                    data_obj = json.loads(row["data"]) if row["data"] else {}
                    if not isinstance(data_obj, dict):
                        data_obj = {}
                except Exception:
                    data_obj = {}

                # 대상 칸 목록 — fields(다중) 우선, 없으면 col/value 단건(휴대폰은 GAS 그대로 거부/스킵)
                targets = []
                if fields:
                    for fk, fv in fields.items():
                        fname = str(fk).strip()
                        if not fname or _is_active_blocked_field(fname):
                            continue   # 전화·회원번호·지문키 칸은 조용히 스킵(GAS L9849 + 배1054 검토⑥)
                        targets.append((fname, fv))
                    if ACT_RES_COL in fields:   # 재등록예약목록 → 재등록상담 3칸 미러(GAS L9854~9862 이식)
                        d, t, n = _parse_first_reservation(fields[ACT_RES_COL])
                        targets += [("재등록상담 날짜", d), ("재등록상담 시간", t), ("재등록상담 내용", n)]
                elif _is_active_blocked_field(col):
                    err_code = "phone-blocked"
                else:
                    targets.append((col, payload.get("value")))

                if not err_code:
                    saved, wrote_names, promoted_names, reverts = {}, [], [], []
                    for fname, fv in targets:
                        new_val = "" if fv is None else str(fv)
                        dbcol = _ACTIVE_COL_MAP.get(_norm_col(fname))
                        if dbcol:
                            old_val = "" if row.get(dbcol) is None else str(row[dbcol])
                            if old_val != new_val:   # 멱등 — 같은 값 재저장은 이력 안 남기고 ok
                                promoted_names.append(fname)   # sync_members.py 예외 대상은 실제로 값이 바뀐 칸만(배1054 검토①)
                                conn.execute(
                                    "UPDATE members SET {c}=%s WHERE tenant_id=%s AND member_no=%s AND scope='valid'"
                                    .format(c=dbcol), (new_val, tenant, member_no))
                                conn.execute(
                                    "INSERT INTO member_change_log (tenant_id, at, staff, member_no, member_name,"
                                    " phone_masked, field, old_value, new_value, screen) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                                    (tenant, now, staff, member_no, row["name"] or "", _mask_phone(row["phone"]),
                                     fname, old_val, new_val, "멤버십"))
                                reverts.append({"kind": "col", "col": dbcol, "field": fname, "tenant": tenant,
                                                "member_no": member_no, "old_value": old_val, "new_value": new_val,
                                                "name": row["name"] or "", "phone_masked": _mask_phone(row["phone"])})
                                row[dbcol] = new_val   # 같은 요청 안 재조회 대비
                        else:
                            dkey, had_key = _data_get_norm(data_obj, fname)   # 공백 정규화 키 대조(배1054 검토⑤·⑥)
                            old_val = str(data_obj.get(dkey) or "") if had_key else ""
                            if old_val != new_val:
                                conn.execute(
                                    "UPDATE members SET data=jsonb_set(data::jsonb, %s, to_jsonb(%s::text), true)::text"
                                    " WHERE tenant_id=%s AND member_no=%s AND scope='valid'",
                                    ([dkey], new_val, tenant, member_no))
                                conn.execute(
                                    "INSERT INTO member_change_log (tenant_id, at, staff, member_no, member_name,"
                                    " phone_masked, field, old_value, new_value, screen) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                                    (tenant, now, staff, member_no, row["name"] or "", _mask_phone(row["phone"]),
                                     fname, old_val, new_val, "멤버십"))
                                reverts.append({"kind": "json", "json_field": dkey, "had_key": had_key, "field": fname,
                                                "tenant": tenant, "member_no": member_no, "old_value": old_val,
                                                "new_value": new_val, "name": row["name"] or "",
                                                "phone_masked": _mask_phone(row["phone"])})
                                data_obj[dkey] = new_val
                        saved[fname] = new_val
                        wrote_names.append(fname)

                    payload_log = dict(payload)
                    payload_log["_member_no"] = member_no    # 대조 전용(reconcile_dual_write.py)
                    payload_log["_cols"] = promoted_names    # sync_members.py::sync_owner_cols 예외 대상(실컬럼만)
                    payload_log["_saved"] = saved            # 대조 전용 — 실제로 저장한 값(실컬럼+JSON patch 전부)
                    log_id = conn.execute(
                        "INSERT INTO write_log (tenant_id, at, action, payload, user_email, gas_status, raw_body)"
                        " VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                        (tenant, now, "member_active_update", json.dumps(payload_log, ensure_ascii=False), user,
                         "test" if is_test else "pending", None)
                    ).fetchone()[0]
                    extra = {"rowIndex": member_no, "member_no": member_no, "saved": saved}
                    if fields:
                        extra["cols"] = wrote_names
                    else:
                        extra["col"] = col
    except Exception:
        conn.close()
        raise
    if err_code == "phone-blocked":
        conn.close()
        return {"ok": False, "error": "전화·회원번호·지문키 칸은 이 경로로 수정할 수 없습니다"}
    if err_code:
        conn.close()
        return _ACTIVE_ERRORS[err_code]
    return _finish(conn, raw_body, log_id, is_test, extra, reverts or None)


def _handle_member_active_update(payload, raw_body, user):
    """member_active_update 진입점 — updates[](최대 30건 일괄)면 GAS 와 같은 재진입 방식으로 항목마다
    부모 payload 를 상속해 단건 경로(_member_active_update_one)를 그대로 다시 태운다(로직 복제 금지 ·
    Survey.js L9624~9638 이식). 한 건이 실패해도 나머지는 계속한다."""
    updates = payload.get("updates")
    if isinstance(updates, list) and updates:
        if len(updates) > 30:
            return {"ok": False, "error": "updates-too-many", "detail": "한 번에 30건까지 — 나눠 보내세요"}
        results, ok_count = [], 0
        for item in updates:
            one = {k: v for k, v in payload.items() if k != "updates"}
            if isinstance(item, dict):
                one.update(item)
            one["action"] = "member_active_update"
            one.pop("updates", None)   # 재귀 폭주 차단(항목이 updates 를 품고 와도 무시 · GAS 동일)
            try:
                one_body = json.dumps(one, ensure_ascii=False).encode("utf-8")
                r = _member_active_update_one(one, one_body, user)
            except Exception as e:
                r = {"ok": False, "error": "batch-item-failed", "detail": str(e)}
            if r.get("ok"):
                ok_count += 1
            results.append(r)
        return {"ok": ok_count == len(updates), "count": len(updates), "okCount": ok_count, "results": results}
    return _member_active_update_one(payload, raw_body, user)


def _handle_member_hold_approve(payload, raw_body, user):
    """member_hold_approve(4단계 · 배1054) — 접수 행(hold_items 미러) FOR UPDATE 잠금 → 상태 재검사(결함②
    가드) → (approve 시) 회원 매칭·한도 검증·6칸 갱신 → 접수 행 상태 갱신 → GAS write-through(_finish).
    GAS 원본(Survey.js L10708~10783) 대비: reject 는 회원 조회조차 없다(접수 행만 갱신) — 그대로 이식."""
    decision = str(payload.get("decision") or "").strip()
    if decision not in ("approve", "reject"):
        return {"ok": False, "error": "decision=approve|reject"}
    try:
        intake_row_n = int(str(payload.get("intakeRow") or "").strip())
    except (TypeError, ValueError):
        return {"ok": False, "error": "intakeRow 필수(2 이상)"}
    if intake_row_n < 2:
        return {"ok": False, "error": "intakeRow 필수(2 이상)"}
    intake_row = str(intake_row_n)
    key_phone = _norm_phone(payload.get("keyPhone"))
    staff = _log_who(payload, user)
    now = api_write._now_kst()
    is_test = db.is_test_payload(payload)
    tenant = "selftest" if is_test else db.TENANT

    try:
        conn = db.connect()
    except db.Error as e:
        return {"ok": False, "error": "server-forward-failed", "detail": "DB 열기 실패: %s" % e, "noRetry": False}

    # err_response 에 값이 들어가면 그 자리에서 확정(with 블록을 정상 종료시켜 커밋한 뒤 밖에서 close+반환) —
    # with 블록 '안'에서 conn.close()+return 하면 __exit__ 가 닫힌 커넥션에 커밋을 시도해 500 이 난다
    # (배1054 검토 · 실측: psycopg2.InterfaceError: connection already closed). stage1~3 의 err_code 패턴과
    # 같은 이유로 여기서도 조건을 끝까지 평가해 with 블록이 스스로 끝나게 한다.
    err_response, log_id, reverts, extra = None, None, None, None
    try:
        with conn:
            intake = conn.execute(
                "SELECT status, data FROM hold_items WHERE tenant_id=%s AND intake_row=%s FOR UPDATE",
                (tenant, intake_row)).fetchone()
            if not intake:
                err_response = {"ok": False, "error": "접수 행 없음"}
            else:
                try:
                    idata = json.loads(intake["data"]) if intake["data"] else {}
                    if not isinstance(idata, dict):
                        idata = {}
                except Exception:
                    idata = {}
                old_status = intake["status"] or idata.get("status") or ""
                intake_phone = _norm_phone(idata.get("phone"))
                if key_phone and key_phone != intake_phone:   # GAS L10723 그대로 — 접수 전화가 비어도 대조는 건다
                    err_response = {"ok": False, "error": "row-key-mismatch",
                                    "detail": "접수 행 검증 실패 — 새로고침 후 다시 시도하세요"}
                elif old_status and old_status != "접수대기":
                    # 결함② 멱등 가드 — 이미 승인/반려된 접수는 GAS 로 넘기지 않는다(GAS 는 상태를 안 보고 그대로
                    # 증분해 두 번째 요청도 거기서 카운트가 오른다 · 시포 스펙 §2-7). 회원 원장 무변경·이력 없음.
                    err_response = {"ok": True, "decision": decision, "intakeRow": intake_row_n, "noop": True,
                                    "_source": "server", "detail": "이미 처리된 접수입니다(상태=%s)" % old_status}
                elif decision == "reject":   # GAS 원본대로 reject 는 회원 조회조차 없다(접수 행만 갱신)
                    reverts = [{"kind": "hold", "tenant": tenant, "intake_row": intake_row,
                                "old_status": old_status, "old_data": intake["data"]}]
                    extra = {"decision": "reject", "intakeRow": intake_row_n}
                    idata["status"] = "반려"
                    conn.execute("UPDATE hold_items SET status=%s, data=%s WHERE tenant_id=%s AND intake_row=%s",
                                 ("반려", json.dumps(idata, ensure_ascii=False), tenant, intake_row))
                    log_id = conn.execute(
                        "INSERT INTO write_log (tenant_id, at, action, payload, user_email, gas_status, raw_body)"
                        " VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                        (tenant, now, "member_hold_approve", json.dumps(dict(payload), ensure_ascii=False), user,
                         "test" if is_test else "pending", None)
                    ).fetchone()[0]
                else:   # decision == "approve"
                    req_start = str(idata.get("start") or "").strip()
                    req_days = idata.get("wishDays")
                    if not re.match(r"^\d{4}-\d{2}-\d{2}$", req_start) or not isinstance(req_days, int) or isinstance(req_days, bool):
                        err_response = {"ok": False, "error": "bad-request", "detail": "접수 기간/일수 불량"}
                    else:
                        kind = str(idata.get("kind") or "").strip() or "신규"
                        m_hits = conn.execute(
                            "SELECT * FROM members WHERE tenant_id=%s AND scope='valid' AND phone=%s FOR UPDATE",
                            (tenant, intake_phone)).fetchall()
                        if not m_hits:
                            err_response = {"ok": False, "error": "member-not-found",
                                            "detail": "회원DB에서 일치 회원을 찾을 수 없습니다(전화 확인)"}
                        elif len(m_hits) > 1:
                            err_response = {"ok": False, "error": "member-ambiguous", "detail": "동일 전화 회원 다수 — 데스크 확인"}
                        else:
                            mrow = dict(m_hits[0])
                            member_no = mrow["member_no"]
                            am_c, am_d = _hold_num(mrow.get("hold_count")), _hold_num(mrow.get("hold_cum_days"))
                            min_once = _hold_min_once(kind)
                            if req_days < min_once or req_days > HOLD_MAX_ONCE:
                                err_response = {"ok": False, "error": "휴회 일수 범위(%s %d~%d일) 위반: %d일"
                                               % (kind, min_once, HOLD_MAX_ONCE, req_days)}
                            elif am_c + 1 > HOLD_MAX_COUNT:
                                err_response = {"ok": False, "error": "휴회 횟수 한도 초과(최대 %d회, 현재 %d회)" % (HOLD_MAX_COUNT, am_c)}
                            elif am_d + req_days > HOLD_MAX_TOTAL:
                                err_response = {"ok": False, "error": "누적 휴회일수 한도 초과(최대 %d일, 현재 %d+%d일)"
                                               % (HOLD_MAX_TOTAL, am_d, req_days)}
                            else:
                                req_end = _hold_end_calc(req_start, req_days)
                                new_vals = {
                                    "hold_period": "%s ~ %s (%d일)" % (req_start, req_end, req_days),
                                    "hold_start_date": req_start, "hold_end_date": req_end,
                                    "hold_count": str(am_c + 1), "hold_cum_days": str(am_d + req_days), "hold_status": "진행중",
                                }
                                reverts = [{"kind": "hold", "tenant": tenant, "intake_row": intake_row,
                                            "old_status": old_status, "old_data": intake["data"]}]
                                saved, changed_labels = {}, []
                                for col, new_val in new_vals.items():
                                    label = HOLD_APPROVE_COL_MAP[col]
                                    old_val = mrow.get(col) or ""
                                    saved[label] = new_val
                                    if old_val != new_val:   # 멱등 — 같은 값이면 이력 없이 스킵(stage1~3 과 같은 규칙)
                                        changed_labels.append(label)
                                        conn.execute(
                                            "UPDATE members SET {c}=%s WHERE tenant_id=%s AND member_no=%s AND scope='valid'"
                                            .format(c=col), (new_val, tenant, member_no))
                                        conn.execute(
                                            "INSERT INTO member_change_log (tenant_id, at, staff, member_no, member_name,"
                                            " phone_masked, field, old_value, new_value, screen) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                                            (tenant, now, staff, member_no, mrow.get("name") or "", _mask_phone(mrow.get("phone")),
                                             label, old_val, new_val, "멤버십"))
                                        reverts.append({"kind": "col", "col": col, "field": label, "tenant": tenant,
                                                        "member_no": member_no, "old_value": old_val, "new_value": new_val,
                                                        "name": mrow.get("name") or "", "phone_masked": _mask_phone(mrow.get("phone"))})
                                idata["status"] = "승인"
                                conn.execute("UPDATE hold_items SET status=%s, data=%s WHERE tenant_id=%s AND intake_row=%s",
                                             ("승인", json.dumps(idata, ensure_ascii=False), tenant, intake_row))
                                extra = {"decision": "approve", "intakeRow": intake_row_n, "memberRow": member_no,
                                        "member_no": member_no, "count": am_c + 1, "cumDays": am_d + req_days,
                                        "period": "%s ~ %s" % (req_start, req_end), "extended": False}
                                payload_log = dict(payload)
                                payload_log["_member_no"] = member_no    # 대조 전용(reconcile_dual_write.py)
                                payload_log["_cols"] = changed_labels    # sync_members.py::sync_owner_cols 예외 대상(실컬럼만)
                                payload_log["_saved"] = saved            # 대조 전용 — 실제로 저장한 값(변경 없어도 전부)
                                log_id = conn.execute(
                                    "INSERT INTO write_log (tenant_id, at, action, payload, user_email, gas_status, raw_body)"
                                    " VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                                    (tenant, now, "member_hold_approve", json.dumps(payload_log, ensure_ascii=False), user,
                                     "test" if is_test else "pending", None)
                                ).fetchone()[0]
    except Exception:
        conn.close()
        raise
    if err_response is not None:
        conn.close()
        return err_response
    return _finish(conn, raw_body, log_id, is_test, extra, reverts)


@router.post("/write")
async def members_write(request: Request):
    body = await request.body()
    try:
        payload = json.loads(body.decode("utf-8"))
        action = str(payload["action"])
    except Exception:
        return {"ok": False, "error": "bad-payload", "detail": "JSON 객체에 action 이 있어야 합니다", "noRetry": True}
    if action not in _IMPLEMENTED:
        return JSONResponse(status_code=501, content={
            "ok": False, "error": "not-implemented", "noRetry": False,
            "detail": "회원 쓰기 서버 이관은 아직 %s 를 처리하지 않습니다. "
                      "%s 는 GAS 경로(/api/write)를 쓰세요." % (", ".join(_IMPLEMENTED), action[:60])})

    if action == "member_active_update":   # 3단계(배1054) — 칸 자유 쓰기·행 변환·일괄이 나머지 둘과 모양이 달라 갈라둔다
        return _handle_member_active_update(payload, body, request.headers.get("x-erp-user", ""))
    if action == "member_hold_approve":    # 4단계(배1054) — 2원장(members+hold_items)·멱등 가드가 따로 필요해 갈라둔다
        return _handle_member_hold_approve(payload, body, request.headers.get("x-erp-user", ""))

    user = request.headers.get("x-erp-user", "")
    now = api_write._now_kst()
    is_test = db.is_test_payload(payload)
    tenant = "selftest" if is_test else db.TENANT
    member_no_in = str(payload.get("member_no") or "").strip()

    try:
        conn = db.connect()
    except db.Error as e:
        return {"ok": False, "error": "server-forward-failed", "detail": "DB 열기 실패: %s" % e, "noRetry": False}

    if action == "member_owner_save":
        field = str(payload.get("field") or "").strip()
        col = FIELD_TO_COL.get(field)
        if not col:
            conn.close()
            return {"ok": False, "error": "bad field"}
        phone = _norm_phone(payload.get("phone"))
        if not phone:
            conn.close()
            return {"ok": False, "error": "no member"}
        value = str(payload.get("value") if payload.get("value") is not None else "").strip()
        staff = _log_who(payload, user)

        not_found, mismatch, ambiguous, member_no, log_id, revert = False, False, False, None, None, None
        try:
            with conn:
                row, mismatch, ambiguous = _find_and_lock(conn, tenant, col, member_no_in, phone)
                if not row:
                    not_found = not mismatch and not ambiguous
                else:
                    member_no = row["member_no"]
                    old_value = row["val"] or ""
                    if old_value != value:   # 멱등 — 같은 값 재저장은 이력 안 남기고 ok(시포 스펙 "서버 재구현 주의")
                        conn.execute(
                            "UPDATE members SET {col}=%s WHERE tenant_id=%s AND member_no=%s AND scope='valid'".format(col=col),
                            (value, tenant, member_no))
                        conn.execute(
                            "INSERT INTO member_change_log (tenant_id, at, staff, member_no, member_name, phone_masked,"
                            " field, old_value, new_value, screen) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                            (tenant, now, staff, member_no, row["name"] or "", _mask_phone(row["phone"]),
                             field, old_value, value, "멤버십"))
                        revert = {"col": col, "field": field, "tenant": tenant, "member_no": member_no,
                                  "old_value": old_value, "new_value": value, "name": row["name"] or "",
                                  "phone_masked": _mask_phone(row["phone"])}
                    payload_log = dict(payload)
                    payload_log["_member_no"] = member_no   # 대조 전용(reconcile_dual_write.py) — 화면이 보낸 값이 아니다
                    log_id = conn.execute(
                        "INSERT INTO write_log (tenant_id, at, action, payload, user_email, gas_status, raw_body)"
                        " VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                        (tenant, now, action, json.dumps(payload_log, ensure_ascii=False), user,
                         "test" if is_test else "pending", None)
                    ).fetchone()[0]
        except Exception:
            conn.close()
            raise
        if ambiguous:
            conn.close()
            return {"ok": False, "error": "rowkey-ambiguous", "noRetry": True,
                    "detail": "전화번호 중복 매칭(다중 회원) — 회원번호(member_no)를 포함해 다시 시도하세요"}
        if mismatch:
            conn.close()
            return _member_no_mismatch(member_no_in)
        if not_found:
            conn.close()
            return {"ok": False, "error": "no member"}
        return _finish(conn, body, log_id, is_test,
                       {"phone": phone, "field": field, "value": value, "rowIndex": member_no, "member_no": member_no},
                       revert)

    # action == "member_hold_transition" (2단계 · 배1054)
    status = str(payload.get("status") or "").strip()
    if status not in HOLD_STATUSES:
        conn.close()
        return {"ok": False, "error": "status=완료|진행중 중 하나"}
    phone = _norm_phone(payload.get("phone") or payload.get("keyPhone"))
    if not phone:
        conn.close()
        return {"ok": False, "error": "row-key-unverified", "detail": "행 확인 불가 — 연락처 확인 후 목록 새로고침하여 다시 시도하세요"}
    staff = _log_who(payload, user)

    not_found, mismatch, ambiguous, member_no, log_id, revert = False, False, False, None, None, None
    try:
        with conn:
            row, mismatch, ambiguous = _find_and_lock(conn, tenant, HOLD_COL, member_no_in, phone)
            if not row:
                not_found = not mismatch and not ambiguous
            else:
                member_no = row["member_no"]
                old_value = row["val"] or ""
                if old_value != status:   # 멱등 — 같은 상태 재저장은 이력 안 남기고 ok
                    conn.execute(
                        "UPDATE members SET {col}=%s WHERE tenant_id=%s AND member_no=%s AND scope='valid'".format(col=HOLD_COL),
                        (status, tenant, member_no))
                    conn.execute(
                        "INSERT INTO member_change_log (tenant_id, at, staff, member_no, member_name, phone_masked,"
                        " field, old_value, new_value, screen) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                        (tenant, now, staff, member_no, row["name"] or "", _mask_phone(row["phone"]),
                         HOLD_FIELD_LABEL, old_value, status, "멤버십"))
                    revert = {"col": HOLD_COL, "field": HOLD_FIELD_LABEL, "tenant": tenant, "member_no": member_no,
                              "old_value": old_value, "new_value": status, "name": row["name"] or "",
                              "phone_masked": _mask_phone(row["phone"])}
                payload_log = dict(payload)
                payload_log["_member_no"] = member_no   # 대조 전용(reconcile_dual_write.py) — 화면이 보낸 값이 아니다
                log_id = conn.execute(
                    "INSERT INTO write_log (tenant_id, at, action, payload, user_email, gas_status, raw_body)"
                    " VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                    (tenant, now, action, json.dumps(payload_log, ensure_ascii=False), user,
                     "test" if is_test else "pending", None)
                ).fetchone()[0]
    except Exception:
        conn.close()
        raise
    if ambiguous:
        conn.close()
        return {"ok": False, "error": "rowkey-ambiguous", "noRetry": True,
                "detail": "전화번호 중복 매칭(다중 회원) — 회원번호(member_no)를 포함해 다시 시도하세요"}
    if mismatch:
        conn.close()
        return _member_no_mismatch(member_no_in)
    if not_found:
        conn.close()
        return {"ok": False, "error": "rowkey-not-found", "detail": "회원 행 확인 불가 — 목록 새로고침 후 다시 시도하세요"}
    return _finish(conn, body, log_id, is_test,
                   {"status": status, "rowIndex": member_no, "member_no": member_no},
                   revert)


def _selftest_finish_revert():
    """단위 자체점검(DB·네트워크 없음) — GAS 거부 시 _finish 가 ok=False + 보상 UPDATE·취소이력을
    내는지 확인(배1054 검토② · api_write._gas_forward 를 스텁으로 교체)."""
    class _FakeCur:
        def fetchone(self):
            return [1]

    class _FakeConn:
        def __init__(self):
            self.executed = []
            self.closed = False

        def execute(self, sql, args=()):
            self.executed.append((sql, args))
            return _FakeCur()

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def close(self):
            self.closed = True

    orig_forward = api_write._gas_forward
    api_write._gas_forward = lambda body, url_key="FUNNEL_EXEC_URL": {
        "ok": False, "error": "hold-gated", "detail": "휴회 상태 반영은 GM 검증 후 개통됩니다(현재 미개통)"}
    try:
        conn = _FakeConn()
        revert = {"col": HOLD_COL, "field": HOLD_FIELD_LABEL, "tenant": "wellperion", "member_no": "M00001",
                  "old_value": "진행중", "new_value": "완료", "name": "테스트", "phone_masked": "010-1234-****"}
        out = _finish(conn, b"{}", 1, False, {"status": "완료", "member_no": "M00001"}, revert)
    finally:
        api_write._gas_forward = orig_forward
    assert out["ok"] is False and out["error"] == "hold-gated", out
    assert conn.closed
    assert any("UPDATE members SET hold_status" in sql for sql, _ in conn.executed), conn.executed
    assert any("member_change_log" in sql for sql, _ in conn.executed), conn.executed

    # member_active_update(3단계) 다건 revert — 리스트 안에 실컬럼(col)·JSON patch(json) 두 종류가 섞여도
    # 둘 다 되돌아가고 이력이 두 줄 남는지(배1054 검토② 일반화). GAS 거부(가상)로 forward 를 스텁.
    api_write._gas_forward = lambda body, url_key="FUNNEL_EXEC_URL": {"ok": False, "error": "컬럼 미발견: X"}
    try:
        conn2 = _FakeConn()
        reverts = [
            {"kind": "col", "col": "note", "field": "비고", "tenant": "wellperion", "member_no": "M00002",
             "old_value": "old", "new_value": "new", "name": "테스트", "phone_masked": "010-1234-****"},
            {"kind": "json", "json_field": "PT Contact", "field": "PT Contact", "tenant": "wellperion",
             "member_no": "M00002", "old_value": "old2", "new_value": "new2", "name": "테스트",
             "phone_masked": "010-1234-****"},
        ]
        out2 = _finish(conn2, b"{}", 1, False, {"rowIndex": "M00002"}, reverts)
    finally:
        api_write._gas_forward = orig_forward
    assert out2["ok"] is False and conn2.closed
    assert any("UPDATE members SET note" in sql for sql, _ in conn2.executed), conn2.executed
    assert any("jsonb_set" in sql for sql, _ in conn2.executed), conn2.executed
    assert sum("member_change_log" in sql for sql, _ in conn2.executed) == 2, conn2.executed

    # JSON 칸 되돌리기 — 원래 키가 없었으면(had_key=False) ""로 되돌리지 않고 키 자체를 지운다(배1054 검토⑦).
    api_write._gas_forward = lambda body, url_key="FUNNEL_EXEC_URL": {"ok": False, "error": "컬럼 미발견: X"}
    try:
        conn3 = _FakeConn()
        revert3 = {"kind": "json", "json_field": "PT Contact", "had_key": False, "field": "PT Contact",
                   "tenant": "wellperion", "member_no": "M00003", "old_value": "", "new_value": "new3",
                   "name": "테스트", "phone_masked": "010-1234-****"}
        out3 = _finish(conn3, b"{}", 1, False, {"rowIndex": "M00003"}, revert3)
    finally:
        api_write._gas_forward = orig_forward
    assert out3["ok"] is False and conn3.closed
    assert any("data::jsonb - " in sql or "data::jsonb -" in sql for sql, _ in conn3.executed), conn3.executed
    assert not any("jsonb_set" in sql for sql, _ in conn3.executed), conn3.executed

    # member_hold_approve(4단계) revert — kind='hold' 는 hold_items 상태·data 만 되돌리고 member_change_log
    # 는 안 남긴다(회원 원장을 안 건드린 reject 케이스도 이 kind 하나로 되돌아간다 · 배1054 검토②).
    api_write._gas_forward = lambda body, url_key="FUNNEL_EXEC_URL": {"ok": False, "error": "hold-gated"}
    try:
        conn4 = _FakeConn()
        reverts4 = [
            {"kind": "hold", "tenant": "wellperion", "intake_row": "5", "old_status": "접수대기",
             "old_data": '{"status":"접수대기"}'},
            {"kind": "col", "col": "hold_status", "field": HOLD_FIELD_LABEL, "tenant": "wellperion",
             "member_no": "M00004", "old_value": "", "new_value": "진행중", "name": "테스트",
             "phone_masked": "010-1234-****"},
        ]
        out4 = _finish(conn4, b"{}", 1, False, {"decision": "approve", "intakeRow": 5}, reverts4)
    finally:
        api_write._gas_forward = orig_forward
    assert out4["ok"] is False and conn4.closed
    assert any("UPDATE hold_items SET status" in sql for sql, _ in conn4.executed), conn4.executed
    assert any("UPDATE members SET hold_status" in sql for sql, _ in conn4.executed), conn4.executed
    assert sum("member_change_log" in sql for sql, _ in conn4.executed) == 1, conn4.executed   # hold 항목은 이력 없음


if __name__ == "__main__":   # python3 api_members_write.py — 갈래·마스킹·직원표기·상태검증 자체점검(서버·DB 없이)
    assert FIELD_TO_COL["PT 담당자"] == "owner_pt" and FIELD_TO_COL["수영 담당자"] == "owner_swim"
    assert len(FIELD_TO_COL) == 5
    assert set(_IMPLEMENTED) == {"member_owner_save", "member_hold_transition", "member_active_update", "member_hold_approve"}
    assert not set(_IMPLEMENTED) & set(_NOT_YET)
    # member_hold_approve(4단계) 헬퍼 — GAS _holdMinOnce_·_holdEndCalc_·_amNum 이식.
    assert _hold_min_once("신규") == 7 and _hold_min_once("연장") == 1 and _hold_min_once("") == 7
    assert _hold_end_calc("2026-08-01", 30) == "2026-08-30"   # 시작+29일
    assert _hold_end_calc("2026-08-01", 1) == "2026-08-01"    # 1일이면 당일 종료
    assert _hold_num("3") == 3 and _hold_num("") == 0 and _hold_num(None) == 0 and _hold_num("12일") == 12
    assert set(HOLD_APPROVE_COL_MAP) == {"hold_period", "hold_start_date", "hold_end_date",
                                         "hold_count", "hold_cum_days", "hold_status"}
    assert HOLD_APPROVE_COL_MAP["hold_period"] == "휴회기간(휴회일수)" and HOLD_APPROVE_COL_MAP["hold_status"] == HOLD_FIELD_LABEL
    # member_active_update(3단계) 칸 매핑 — 헤더에 줄바꿈·공백이 섞여도 정규화로 잡힌다.
    assert _norm_col("잔여일\n(일)") == "잔여일(일)" and _norm_col(" 재등록상담 날짜 ") == "재등록상담날짜"
    assert _ACTIVE_COL_MAP["재등록상담날짜"] == "reg_consult_date"
    assert _ACTIVE_COL_MAP["잔여일(일)"] == "remain_days"   # sync_members.py COLS 재사용(새 스키마 불필요)
    assert _ACTIVE_COL_MAP["주소"] == "address" and _ACTIVE_COL_MAP["종료사유메모"] == "end_reason_memo"
    assert len(_ACTIVE_COL_MAP) == 21
    assert set(_ACTIVE_ERRORS) == {"unverified", "not_found", "ambiguous", "member_no_mismatch"}
    # 재등록예약목록 첫 예약 파싱(GAS _resParse_ 이식) — 빈 값·이상값은 무손실 스킵.
    assert _parse_first_reservation('[{"date":"2026-09-10","time":"14:00","note":"전화상담"}]') \
        == ("2026-09-10", "14:00", "전화상담")
    assert _parse_first_reservation("") == ("", "", "")
    assert _parse_first_reservation("[]") == ("", "", "")
    assert _parse_first_reservation("not-json") == ("", "", "")
    assert _parse_first_reservation([{"date": "2026-09-11"}]) == ("2026-09-11", "", "")
    # 첫 항목이 완전히 빈 값이면 건너뛰고 다음 유효 항목을 쓴다 · note 끝 '(컨택:이름)' 마커는 떼어낸다(배1054 검토④).
    assert _parse_first_reservation(
        '[{"date":"","time":"","note":""},{"date":"2026-09-12","time":"10:00","note":"상담 (컨택:임정은)"}]'
    ) == ("2026-09-12", "10:00", "상담")
    # 열쇠 칸(전화·회원번호·rowKey·rowIndex)은 member_active_update 로 못 고친다(배1054 검토⑥).
    assert _is_active_blocked_field("휴대폰번호") and _is_active_blocked_field("회원번호")
    assert _is_active_blocked_field("rowKey") and _is_active_blocked_field("rowIndex")
    assert not _is_active_blocked_field("주소")
    # members.data 키가 공백·줄바꿈 섞여도 정규화 대조로 찾는다(reconcile_dual_write.py 대조와 같은 규칙).
    assert _data_get_norm({"PT\nContact": "x"}, "PT Contact") == ("PT\nContact", True)
    assert _data_get_norm({}, "PT Contact") == ("PT Contact", False)
    assert HOLD_STATUSES == ("완료", "진행중") and HOLD_COL == "hold_status"
    assert _norm_phone("010-1234-5678") == "01012345678" and _norm_phone(None) == ""
    assert _mask_phone("010-1234-5678") == "010-1234-****"        # 뒤 4자리만 가림 · 앞은 그대로
    assert _mask_phone("01012345678") == "010-1234-****"          # 구분자 없어도 같은 결과
    assert _mask_phone("123") == "123"                            # 8자리 미만은 원본 그대로(GAS 그대로)
    assert _log_who({}) == "자동"                                  # staff 키 자체가 없음, 헤더도 없음 = 자동접수
    assert _log_who({}, "임정은") == "임정은"                       # staff 키 없음 → x-erp-user 헤더로 대체(배1054 검토④)
    assert _log_who({"staff": ""}) == "이름미상"                    # 키는 있는데 비어 있음
    assert _log_who({"staff": " 임정은 "}) == "임정은"
    # 배1054 dry-run 갈래 — 더미 전화(이름 칸 없음)는 테스트로 잡혀 tenant 'selftest' 로만 향해야 한다.
    assert db.is_test_payload({"field": "PT 담당자", "phone": "010-0000-0000", "value": "x"})
    assert not db.is_test_payload({"field": "PT 담당자", "phone": "010-2781-7262", "value": "x"})
    assert db.is_test_payload({"keyPhone": "010-0000-0000", "status": "완료"})   # 검토① member_hold_transition 열쇠
    assert db.is_test_payload({"decision": "approve", "intakeRow": 5, "keyPhone": "010-0000-0000"})   # member_hold_approve
    _selftest_finish_revert()
    print("자체점검 통과")
