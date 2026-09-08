# -*- coding: utf-8 -*-
"""회원 쓰기 서버 원장 — POST /api/members/write (배1050 1단계 · 배1054 2단계 · 시토).

member_owner_save(종목별 담당자 5칸 · 1단계) · member_hold_transition(휴회접수상태 1칸 · 2단계) 만 여기서
서버 원장(members)에 먼저 쓴다 — ①검증 ②서버 원장 갱신 + member_change_log 이력 1줄(한 트랜잭션 · 값 같으면
이력 없이 ok) ③기존 GAS 로 write-through(시트도 유지 · api_write._gas_forward 재사용 · 실패해도 서버 저장은
이미 끝남 — 응답 gas_status 로만 알린다). 나머지 5종(member_active_update 등)은 아직 이 라우트에 안 왔다 —
501 로 /api/write(GAS 경로)를 쓰라고 안내한다(화면이 잘못 붙어도 조용히 실패하지 않게).
정본 = status/briefs/CPO-2026-09-05-회원쓰기7종-서버원장-스펙.md §2-2·2-6.

행 찾기(두 액션 공통 _find_and_lock): payload 에 member_no 가 있으면 번호로 먼저 찾고 전화도 일치해야 한다
(불일치=400 거부 · GAS 는 member_no 를 무시하고 그대로 write-through). member_no 가 없으면 전화 정규화
첫 매칭 1행(member_no 오름차순 — 시트엔 없는 순서 개념이라 이걸로 대신한다). 두 경우 다 SQL 이 phone=%s 로
필터링해 행의 전화가 비어 있으면 애초에 안 걸린다 — GAS keyPhone 폴백의 fail-open(행 전화 빈칸이면 통과 ·
Survey.js L10808)이 서버에는 구조적으로 없다(결함① 반영 · 배1054).
'컬럼 미발견'·'유효회원 시트 없음' 류 오류는 서버에서 뺐다 — schema.sql 이 컬럼을 고정 보장해 발생할 수 없다.

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
# 아직 이 라우트가 처리 안 하는 나머지 5종(시포 스펙 §2-1·2-3~2-5·2-7) — 501 안내에만 쓴다(화이트리스트 아님).
_NOT_YET = ("member_active_update", "member_registered_add", "member_registered_remove",
            "member_archive_restore", "member_hold_approve")
_IMPLEMENTED = ("member_owner_save", "member_hold_transition")


def _norm_phone(v):
    return re.sub(r"\D", "", str(v or ""))


def _mask_phone(v):
    """GAS _logMaskPhone_ 이식(Survey.js L1260) — 뒤 4자리를 가리고 앞은 그대로(010-1234-****). 8자리 미만은 원본."""
    d = re.sub(r"\D", "", str(v or ""))
    if len(d) < 8:
        return str(v or "")
    head = d[:-4]
    m = re.match(r"(\d{3})(\d+)", head)
    return (m.group(1) + "-" + m.group(2) if m else head) + "-****"


def _log_who(payload):
    """GAS _logWho_ 이식(Survey.js L1268) — staff 키 자체가 없으면 '자동'(자동접수), 있는데 비면 '이름미상'."""
    if not isinstance(payload, dict) or "staff" not in payload:
        return "자동"
    return str(payload.get("staff") or "").strip() or "이름미상"


def _find_and_lock(conn, tenant, col, member_no_in, phone):
    """member_no 있으면 번호로 찾고 전화 일치 확인(불일치=mismatch) · 없으면 전화 첫 매칭(member_no 오름차순).
    반환 (row|None, mismatch:bool). row 는 member_no·name·phone·val(해당 칸) 을 담은 DictRow."""
    if member_no_in:
        row = conn.execute(
            ("SELECT member_no, name, phone, {col} AS val FROM members"
             " WHERE tenant_id=%s AND scope='valid' AND member_no=%s FOR UPDATE").format(col=col),
            (tenant, member_no_in)).fetchone()
        if row and _norm_phone(row["phone"]) != phone:
            return None, True
        return row, False
    row = conn.execute(
        ("SELECT member_no, name, phone, {col} AS val FROM members"
         " WHERE tenant_id=%s AND scope='valid' AND phone=%s ORDER BY member_no LIMIT 1 FOR UPDATE").format(col=col),
        (tenant, phone)).fetchone()
    return row, False


def _finish(conn, body, log_id, is_test, extra):
    """두 액션 공통 꼬리 — GAS write-through + write_log.gas_status 갱신 + 거울 재동기화 스케줄.
    extra(dict) 를 응답에 얹는다. is_test 면 GAS 는 아예 안 부른다(dry-run)."""
    if is_test:
        conn.close()
        return dict(extra, ok=True, _source="server", gas_status="skipped-test")
    try:
        resp = api_write._gas_forward(body, "FUNNEL_EXEC_URL")
        gas_status = "ok" if resp.get("ok") else "gas-error"
    except Exception as e:
        resp = {"ok": False, "error": "server-forward-failed", "detail": "%s: %s" % (type(e).__name__, str(e)[:200]), "noRetry": False}
        gas_status = "forward-failed"
    with conn:
        conn.execute("UPDATE write_log SET gas_status=%s, gas_response=%s WHERE id=%s",
                     (gas_status, json.dumps(resp, ensure_ascii=False)[:20000], log_id))
    conn.close()
    api_write._schedule_sync("sync_members.py")
    return dict(extra, ok=True, _source="server", gas_status=gas_status)


def _member_no_mismatch(member_no_in):
    return JSONResponse(status_code=400, content={
        "ok": False, "error": "member_no-phone-mismatch", "noRetry": True,
        "detail": "회원번호(%s)와 전화번호가 일치하지 않습니다" % member_no_in})


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
        staff = _log_who(payload)

        not_found, mismatch, member_no, log_id = False, False, None, None
        with conn:
            row, mismatch = _find_and_lock(conn, tenant, col, member_no_in, phone)
            if not row:
                not_found = not mismatch
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
                payload_log = dict(payload)
                payload_log["_member_no"] = member_no   # 대조 전용(reconcile_dual_write.py) — 화면이 보낸 값이 아니다
                log_id = conn.execute(
                    "INSERT INTO write_log (tenant_id, at, action, payload, user_email, gas_status, raw_body)"
                    " VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                    (tenant, now, action, json.dumps(payload_log, ensure_ascii=False), user,
                     "test" if is_test else "pending", None)
                ).fetchone()[0]
        if mismatch:
            conn.close()
            return _member_no_mismatch(member_no_in)
        if not_found:
            conn.close()
            return {"ok": False, "error": "no member"}
        return _finish(conn, body, log_id, is_test,
                       {"phone": phone, "field": field, "value": value, "rowIndex": member_no, "member_no": member_no})

    # action == "member_hold_transition" (2단계 · 배1054)
    status = str(payload.get("status") or "").strip()
    if status not in HOLD_STATUSES:
        conn.close()
        return {"ok": False, "error": "status=완료|진행중 중 하나"}
    phone = _norm_phone(payload.get("phone") or payload.get("keyPhone"))
    if not phone:
        conn.close()
        return {"ok": False, "error": "row-key-unverified", "detail": "행 확인 불가 — 연락처 확인 후 목록 새로고침하여 다시 시도하세요"}
    staff = _log_who(payload)

    not_found, mismatch, member_no, log_id = False, False, None, None
    with conn:
        row, mismatch = _find_and_lock(conn, tenant, HOLD_COL, member_no_in, phone)
        if not row:
            not_found = not mismatch
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
            payload_log = dict(payload)
            payload_log["_member_no"] = member_no   # 대조 전용(reconcile_dual_write.py) — 화면이 보낸 값이 아니다
            log_id = conn.execute(
                "INSERT INTO write_log (tenant_id, at, action, payload, user_email, gas_status, raw_body)"
                " VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                (tenant, now, action, json.dumps(payload_log, ensure_ascii=False), user,
                 "test" if is_test else "pending", None)
            ).fetchone()[0]
    if mismatch:
        conn.close()
        return _member_no_mismatch(member_no_in)
    if not_found:
        conn.close()
        return {"ok": False, "error": "rowkey-not-found", "detail": "회원 행 확인 불가 — 목록 새로고침 후 다시 시도하세요"}
    return _finish(conn, body, log_id, is_test,
                   {"status": status, "rowIndex": member_no, "member_no": member_no})


if __name__ == "__main__":   # python3 api_members_write.py — 갈래·마스킹·직원표기·상태검증 자체점검(서버·DB 없이)
    assert FIELD_TO_COL["PT 담당자"] == "owner_pt" and FIELD_TO_COL["수영 담당자"] == "owner_swim"
    assert len(FIELD_TO_COL) == 5
    assert set(_IMPLEMENTED) == {"member_owner_save", "member_hold_transition"}
    assert not set(_IMPLEMENTED) & set(_NOT_YET)
    assert HOLD_STATUSES == ("완료", "진행중") and HOLD_COL == "hold_status"
    assert _norm_phone("010-1234-5678") == "01012345678" and _norm_phone(None) == ""
    assert _mask_phone("010-1234-5678") == "010-1234-****"        # 뒤 4자리만 가림 · 앞은 그대로
    assert _mask_phone("01012345678") == "010-1234-****"          # 구분자 없어도 같은 결과
    assert _mask_phone("123") == "123"                            # 8자리 미만은 원본 그대로(GAS 그대로)
    assert _log_who({}) == "자동"                                  # staff 키 자체가 없음 = 자동접수
    assert _log_who({"staff": ""}) == "이름미상"                    # 키는 있는데 비어 있음
    assert _log_who({"staff": " 임정은 "}) == "임정은"
    # 배1054 dry-run 갈래 — 더미 전화(이름 칸 없음)는 테스트로 잡혀 tenant 'selftest' 로만 향해야 한다.
    assert db.is_test_payload({"field": "PT 담당자", "phone": "010-0000-0000", "value": "x"})
    assert not db.is_test_payload({"field": "PT 담당자", "phone": "010-2781-7262", "value": "x"})
    print("자체점검 통과")
