# -*- coding: utf-8 -*-
"""회원 쓰기 서버 원장 — POST /api/members/write (배1050 1단계 · 배1054 2·3·4·6단계 · 시토).

member_owner_save(종목별 담당자 5칸 · 1단계) · member_hold_transition(휴회접수상태 1칸 · 2단계) ·
member_active_update(칸 자유 쓰기 · 3단계) · member_hold_approve(휴회 승인/반려 · 2원장 · 4단계) ·
member_archive_restore(LOSS보관→유효회원 전환 · 6단계) 를 여기서 서버 원장(members + hold_items)에
먼저 쓴다 — ①검증 ②서버 원장 갱신 + member_change_log 이력 1줄(한 트랜잭션 · 값 같으면 이력 없이 ok)
③기존 GAS 로 write-through(시트도 유지 · api_write._gas_forward 재사용 · 실패해도 서버 저장은 이미
끝남 — 응답 gas_status 로만 알린다).
member_registered_add(직접등록 · 5단계) · member_registered_remove(되돌리기 · 7단계) 까지 들어와 7종이
전부 이 라우트를 탄다(배1050 · 시포 2026-09-09) — 501 안내는 남은 게 없다.
정본 = status/briefs/CPO-2026-09-05-회원쓰기7종-서버원장-스펙.md §2-1~2-7.

행 찾기 — member_registered_add·member_registered_remove: 전화 정규화 한 열쇠. 두 액션이 건드리는 탭은
둘('26년 등록현황' + 유효회원)인데 등록현황은 월별 체크표라 미러에 없다 — 시트 전용으로 두고(시포 스펙
§2-3 판단) 서버는 유효회원만 맡는다. add 는 전화가 정확히 1건일 때만 서버가 고친다(0건=새 회원이라
회원번호 채번이 필요한데 번호는 GAS registry_build 몫이다 · 2건+=GAS 도 phone-ambiguous 로 거부한다 —
둘 다 그대로 GAS 로 넘긴다). remove 는 GAS 와 같은 조건(전화 단독 매칭 + 등록회차 1)일 때만 행을 지우고,
지우기 전에 행 전체를 이력에 남긴다 — 비밀번호 게이트는 GAS 가 판정하고 거부하면 _finish 가 되살린다.

행 찾기 — member_archive_restore(_handle_member_archive_restore): GAS 원본(Survey.js L9892~10024)은
보관 행을 삭제하고 유효회원에 새 행을 append 한다(회원번호는 인계). 서버는 미러 열쇠가 (member_no,scope)
라 같은 행의 scope 만 'archive'→'valid' 로 바꾸는 UPDATE 한 번으로 끝난다 — 새 채번 자체가 없어 결함④
(registry_build 가 새 번호를 먼저 준 뒤 옛 번호로 덮어 번호 1개 낭비)는 서버 원장에서만 사라진다(CTO
배1050 §6 6단계 결정) — GAS write-through 는 그대로 새 행을 append 한 뒤 registry_build 를 타므로 거기선
여전히 번호 1개가 낭비된다(배1054 검토). GAS 의 '새 행'과 결과를 맞추려면 새 행이 안 갖는 옛 칸(종목담당자 5·휴회 6·LOSS일자·
재등록상담 3·재등록예약목록·종료사유 2 = ARCHIVE_RESET_COLS)을 명시적으로 비운다(GM 지시 "이관건이니
기존 자료는 없어져야해"). 경로 A(유효회원에 이미 같은 전화·같은 이름) = 보관 행만 삭제하는 뒷정리.
경로 B(없음) = scope 전환 + 칸 인계. 이름이 다르면 already-active 거부. 보관 행이 아예 없거나(0건)
회원번호 없는 옛 행이라 미러에 안 실렸으면(§2 공통사실) 서버는 판단하지 않고 GAS 로 그대로 넘긴다
(member_active_update 의 passThrough 와 같은 이유).

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
from sync_reception import gas_get  # noqa: E402  — 접수 시트 재독(승인 계산 재료 · 새 경로 금지 · 배1054 재검토①)
# api_reception._add_months 는 말일 클램프라 여기(archive_restore 개월 계산)엔 안 맞는다 — 대신 이 파일의
# _add_months_js(JS setMonth 오버플로 이식)를 쓴다(배1054 검토① · api_reception 임포트 자체가 불필요해졌다).

router = APIRouter(prefix="/api/members")

# 화이트리스트 5칸 — GAS mosAllowed 그대로(Survey.js L10329~10367). 늘리려면 schema.sql 컬럼도 같이 추가.
FIELD_TO_COL = {
    "PT 담당자": "owner_pt", "골프 담당자": "owner_golf", "P.L 담당자": "owner_pl",
    "스쿼시 담당자": "owner_squash", "수영 담당자": "owner_swim",
}
HOLD_STATUSES = ("완료", "진행중")            # GAS 화이트리스트 그대로(Survey.js L10793)
HOLD_COL = "hold_status"
HOLD_FIELD_LABEL = "휴회접수상태"              # member_change_log 의 field 칸 · GAS 헤더명과 동일
_NOT_YET = ()   # 7종 전부 이 라우트가 처리한다(5·7단계 = 배1050 시포 2026-09-09). 501 안내는 남은 게 없다.
_IMPLEMENTED = ("member_owner_save", "member_hold_transition", "member_active_update", "member_hold_approve",
                "member_archive_restore", "member_registered_add", "member_registered_remove")

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

# member_archive_restore(6단계 · 배1054) — GAS MEMBER_DEFAULT_OWNER 상수(Survey.js L2721) 그대로.
MEMBER_DEFAULT_OWNER = "임정은"
# GAS 의 '새 행'이 안 갖는 칸 — scope 전환(경로 B)에서 전부 빈 문자열로 되돌린다(옛 보관 기록이 새 유효회원
# 행으로 새지 않게 · GM 지시 "이관건이니 기존 자료는 없어져야해"). loss_date 도 포함 — 더는 LOSS가 아니다.
# members.data(JSON) 원문도 이 19칸 라벨만 빈 문자열로 덮는다(배1054 검토③ — members_report 가 data 를
# 직독해 실컬럼만 고치면 다음 sync 전까지 화면에 옛 LOSS보관 값이 그대로 보인다). 나머지 필드(이름·주소 등
# 인계값)는 data 원문에 안 손댄다 — 5분 뒤 sync_members.py replace_scope('valid') 가 GAS 의 진짜 새 행으로
# data 를 통째로 갈아끼우고, 그 직후 같은 사이클의 sync_owner_cols() 가 그 새 data 로 이 실컬럼들을 다시
# 채워 자연히 맞아든다(회귀 자가치유 · sync_owner_cols 예외 등록은 그 사이 창에서 옛 data 로 되밀리지
# 않게 하는 것 · sync_members.py _OWNER_SYNC_ACTIONS 참조). GAS write-through 가 실패하지 않는 한
# (그때는 _finish 가 이 UPDATE 자체를 되돌린다) 다시 살아날 옛값이 없다.
ARCHIVE_RESET_COLS = (
    "kind2", "owner_pt", "owner_golf", "owner_pl", "owner_squash", "owner_swim",
    "hold_status", "hold_period", "hold_start_date", "hold_end_date", "hold_count", "hold_cum_days",
    "loss_date", "reg_consult_date", "reg_consult_time", "reg_consult_note",
    "reg_reservation", "end_reason", "end_reason_memo",
)
# ARCHIVE_RESET_COLS(내부 컬럼명) → 시트 라벨 — 기존 역방향 매핑들(FIELD_TO_COL·HOLD_APPROVE_COL_MAP)을
# 재사용해 조립한다(새 사본 유지 금지). kind2·loss_date·재등록/종료사유 6칸은 다른 곳에 col→label 매핑이
# 없어 여기서만 직접 적는다(sync_members.py OWNER_COLS 의 같은 라벨과 값이 같아야 한다 — 어긋나면 sync 쪽
# 예외 등록이 안 먹는다).
_ARCHIVE_RESET_LABELS = dict(HOLD_APPROVE_COL_MAP)
_ARCHIVE_RESET_LABELS.update({col: label for label, col in FIELD_TO_COL.items()})
_ARCHIVE_RESET_LABELS.update({
    "kind2": "세부구분", "loss_date": "LOSS일자",
    "reg_consult_date": "재등록상담 날짜", "reg_consult_time": "재등록상담 시간", "reg_consult_note": "재등록상담 내용",
    "reg_reservation": "재등록예약목록", "end_reason": "종료사유", "end_reason_memo": "종료사유메모",
})


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


def _add_months_js(date_str, months):
    """member_archive_restore(6단계) 전용 개월 덧셈 — GAS `setMonth` 오버플로 이식(배1054 검토①).
    api_reception._add_months 는 말일을 클램프한다(8/31+6→2/28) — 서명 파기예정일처럼 '그 달 안'을
    보장해야 하는 자리엔 맞지만, GAS Survey.js L10004 의 개월 계산은 JS Date.setMonth 그대로라 말일을
    넘기면 다음 달로 밀린다(8/31+6→3/3). 두 계산은 뜻이 달라 하나를 재사용하면 어긋난다 — 이 자리만
    전용 헬퍼를 쓴다(_add_months 재사용 끊음). 실측: 2026-08-31+6→2027-03-03 · 2026-01-31+1→2026-03-03 ·
    2026-05-31+1→2026-07-01(호출부가 이 값에서 -1일 해 최종 종료일을 낸다)."""
    from datetime import date, timedelta   # noqa: PLC0415 — 이 함수 하나만 쓴다
    d = date.fromisoformat(date_str[:10])
    total = d.month - 1 + months
    y, m = d.year + total // 12, total % 12 + 1
    return (date(y, m, 1) + timedelta(days=d.day - 1)).isoformat()


def _hold_num(v):
    """GAS _amNum 이식(Survey.js L10741 부근) — 숫자·부호 아닌 문자 제거 후 parseInt 와 같이 앞자리
    연속 숫자만 취한다(예: "1-2"→1 · 배1054 재검토⑦, 옛 int() 는 "1-2" 에서 ValueError→0 으로 GAS 와 어긋났다).
    hold_count·hold_cum_days 는 schema.sql 에 TEXT 로 있다(GAS 시트 셀 값 그대로 옮긴 사본)."""
    raw = re.sub(r"[^0-9\-]", "", str(v or ""))
    m = re.match(r"-?\d+", raw)
    return int(m.group()) if m else 0


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
                    if rv.get("kind") == "archive_row":   # member_archive_restore(6단계) — 행 전체 스냅샷 복원
                        old_row, cols = rv["old_row"], list(rv["old_row"].keys())
                        if rv.get("cur_scope"):   # 경로 B 되돌리기 — scope='valid' 로 바뀐 행을 옛 값 전체로 UPDATE
                            conn.execute(
                                "UPDATE members SET " + ", ".join("%s=%%s" % c for c in cols)
                                + " WHERE tenant_id=%s AND member_no=%s AND scope=%s",
                                [old_row[c] for c in cols] + [rv["tenant"], rv["member_no"], rv["cur_scope"]])
                        else:   # 경로 A 되돌리기 — DELETE 했던 보관 행을 그대로 재삽입
                            conn.execute(
                                "INSERT INTO members (" + ",".join(cols) + ") VALUES ("
                                + ",".join(["%s"] * len(cols)) + ") ON CONFLICT (tenant_id, member_no, scope) DO NOTHING",
                                [old_row[c] for c in cols])
                        conn.execute(
                            "INSERT INTO member_change_log (tenant_id, at, staff, member_no, member_name, phone_masked,"
                            " field, old_value, new_value, screen) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                            (rv["tenant"], api_write._now_kst(), "시스템(GAS거부롤백)", rv["member_no"],
                             rv.get("name", ""), rv.get("phone_masked", ""), rv.get("field", "LOSS보관 복귀취소"),
                             "GAS거부", "원상복구", "멤버십"))
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
                # 재검토(치명2) — 화면 목록은 GAS 라이브라 5분 미러에 아직 안 실린 신규 접수행이 뜰 수 있다.
                # 접수 없음 거부 대신 GAS 로 그대로 넘긴다(3단계 member_active_update pass-through 와 같은
                # 방식 · members·hold_items 는 서버가 안 건드리고 다음 sync_reception 이 따라잡는다).
                log_id = conn.execute(
                    "INSERT INTO write_log (tenant_id, at, action, payload, user_email, gas_status, raw_body)"
                    " VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                    (tenant, now, "member_hold_approve", json.dumps(dict(payload), ensure_ascii=False), user,
                     "test" if is_test else "pending", None)
                ).fetchone()[0]
                extra = {"passThrough": True, "decision": decision, "intakeRow": intake_row_n}
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
                    idata["_server_edited"] = now   # 재검토(중요3) — sync_reception._replace 가드가 이 행을 시트 값으로 안 덮게
                    conn.execute("UPDATE hold_items SET status=%s, data=%s WHERE tenant_id=%s AND intake_row=%s",
                                 ("반려", json.dumps(idata, ensure_ascii=False), tenant, intake_row))
                    log_id = conn.execute(
                        "INSERT INTO write_log (tenant_id, at, action, payload, user_email, gas_status, raw_body)"
                        " VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                        (tenant, now, "member_hold_approve", json.dumps(dict(payload), ensure_ascii=False), user,
                         "test" if is_test else "pending", None)
                    ).fetchone()[0]
                else:   # decision == "approve"
                    # 재검토(치명1) — 계산 재료(start·wishDays·kind)는 5분 옛 미러(idata) 대신 접수 시트를
                    # 승인 시점에 다시 읽어 쓴다(GAS Survey.js L10745~10751 과 동일 — 직원이 접수 시트에서
                    # 구분·희망일수를 고치는 것이 설계된 흐름이라, 미러 값으로 계산하면 그 수정이 무시된다).
                    # FOR UPDATE 잠금(위 old_status 재검사)은 그대로 미러로 — 여긴 계산 재료만 GAS 원본.
                    if is_test:   # dry-run(tenant selftest) 은 실 GAS 를 안 부른다 — 미러(idata)를 그대로 재료로
                        live_row = idata
                    else:
                        live = gas_get("FUNNEL_EXEC_URL", "member_hold_intake_list")
                        live_row = None
                        for r in (live or {}).get("data") or []:
                            if str(r.get("intakeRow")) == intake_row:
                                live_row = r
                                break
                    if live_row is None:
                        err_response = {"ok": False, "error": "server-forward-failed",
                                        "detail": "접수 시트 재조회 실패 — 잠시 후 다시 시도하세요", "noRetry": False}
                    else:
                        req_start = str(live_row.get("start") or "").strip()
                        req_days = live_row.get("wishDays")
                        if not re.match(r"^\d{4}-\d{2}-\d{2}$", req_start) or not isinstance(req_days, int) or isinstance(req_days, bool):
                            err_response = {"ok": False, "error": "bad-request", "detail": "접수 기간/일수 불량"}
                        else:
                            kind = str(live_row.get("kind") or "").strip() or "신규"
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
                                    idata["_server_edited"] = now   # 재검토(중요3) — sync_reception._replace 가드가 이 행을 시트 값으로 안 덮게
                                    conn.execute("UPDATE hold_items SET status=%s, data=%s WHERE tenant_id=%s AND intake_row=%s",
                                                 ("승인", json.dumps(idata, ensure_ascii=False), tenant, intake_row))
                                    extra = {"decision": "approve", "intakeRow": intake_row_n,
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


def _handle_member_archive_restore(payload, raw_body, user):
    """member_archive_restore(6단계 · 배1054) — 모듈 docstring 상단 '행 찾기' 절 참조. 항상 plain dict
    또는 JSONResponse 를 돌려준다(다른 핸들러와 동형)."""
    from datetime import datetime, timedelta   # noqa: PLC0415 — 이 함수 하나만 쓴다(stage1~4 관례 그대로)

    phone = _norm_phone(payload.get("phone"))
    if not phone:
        return {"ok": False, "error": "phone 필수"}
    now = api_write._now_kst()
    is_test = db.is_test_payload(payload)
    tenant = "selftest" if is_test else db.TENANT
    staff = _log_who(payload, user)

    try:
        conn = db.connect()
    except db.Error as e:
        return {"ok": False, "error": "server-forward-failed", "detail": "DB 열기 실패: %s" % e, "noRetry": False}

    is_dry = payload.get("dryRun") is True or str(payload.get("dryRun")) == "true"
    err_response, log_id, revert, extra = None, None, None, None
    try:
        with conn:
            arch_count = conn.execute(
                "SELECT COUNT(*) FROM members WHERE tenant_id=%s AND scope='archive' AND phone=%s",
                (tenant, phone)).fetchone()[0]
            if arch_count >= 2:
                err_response = {"ok": False, "error": "archive-ambiguous", "noRetry": True,
                                "detail": "LOSS보관에 같은 전화번호가 %d건 있어 어느 분인지 정할 수 없습니다 — 시트에서 직접 확인해주세요" % arch_count}
            elif arch_count == 0:
                # 회원번호 없는 옛 보관 행 등 미러가 못 실은 경우 — 서버는 판단하지 않고 GAS 로 그대로 넘긴다
                # (member_active_update 의 passThrough 와 같은 이유 · 서버 원장은 안 건드림). dryRun 이어도
                # 서버가 판단할 재료가 없으니 그대로 GAS 에 미뤄 GAS 쪽 미리보기를 타게 한다.
                log_id = conn.execute(
                    "INSERT INTO write_log (tenant_id, at, action, payload, user_email, gas_status, raw_body)"
                    " VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                    (tenant, now, "member_archive_restore", json.dumps(dict(payload), ensure_ascii=False), user,
                     "test" if is_test else "pending", None)
                ).fetchone()[0]
                extra = {"passThrough": True}
            else:
                # COUNT(잠금 없음)와 아래 FOR UPDATE 사이에 다른 요청이 먼저 이 행을 이관했을 수 있다
                # (이중클릭 · 배1054 검토⑥) — fetchone() 이 None 이면 이미 처리된 것으로 보고 no-op 응답
                # (4단계 member_hold_approve 의 상태 재검사 가드와 같은 모양 · 회원 원장 무변경·GAS 미호출).
                arch_row = conn.execute(
                    "SELECT * FROM members WHERE tenant_id=%s AND scope='archive' AND phone=%s FOR UPDATE",
                    (tenant, phone)).fetchone()
                if not arch_row:
                    # err_response 를 여기서 정하고 with 블록은 그대로 정상 종료시킨다(밖에서 close+반환) —
                    # with 블록 '안'에서 conn.close()+return 하면 __exit__ 가 닫힌 커넥션에 커밋을 시도해
                    # 500 이 난다(hold_approve 재검토와 같은 함정 · 배1054 검토⑥).
                    err_response = {"ok": True, "phone": payload.get("phone"), "noop": True, "_source": "server",
                                    "detail": "이미 처리된 LOSS보관 복귀입니다(다른 요청이 먼저 처리)"}
                else:
                    arch = dict(arch_row)
                    member_no = arch["member_no"]
                    arch_name = (arch.get("name") or "").strip()
                    # PK(tenant_id,member_no,scope) 충돌 차단(배1054 검토④) — 이 회원번호가 전화번호와 무관하게
                    # 이미 유효회원에도 있으면(데이터 정합 문제) scope 전환 UPDATE 가 PK 를 깨 500 이 난다. 아래
                    # phone 기준 already-active 판정과 별개로, member_no 기준으로 먼저 걸러 서버 예외를 막는다.
                    already_valid = conn.execute(
                        "SELECT 1 FROM members WHERE tenant_id=%s AND member_no=%s AND scope='valid'",
                        (tenant, member_no)).fetchone()
                    if already_valid:
                        err_response = {"ok": False, "error": "already-active", "noRetry": True,
                                        "detail": "회원번호(%s)가 이미 유효회원에도 있습니다 — 데스크에서 회원 정보를 직접 확인해주세요" % member_no}
                    else:
                        # 전화 일치 유효회원 조회 — 가족 공유 전화로 2건+ 나오면 이름이 일치하는 행 하나로
                        # 좁힌다(배1054 검토⑦). 그래도 0건/2건+ 남으면 서버는 못 고르고 GAS pass-through
                        # (물리 시트 스캔은 GAS 만 할 수 있다 · member_active_update 의 ambiguous 와 같은 이유).
                        actives = conn.execute(
                            "SELECT member_no, name FROM members WHERE tenant_id=%s AND scope='valid' AND phone=%s"
                            " ORDER BY member_no", (tenant, phone)).fetchall()
                        active, active_ambiguous = None, False
                        if len(actives) == 1:
                            active = actives[0]
                        elif len(actives) > 1:
                            name_hits = [a for a in actives if (a["name"] or "").strip() == arch_name]
                            active = name_hits[0] if len(name_hits) == 1 else None
                            active_ambiguous = active is None

                        if active_ambiguous:
                            log_id = conn.execute(
                                "INSERT INTO write_log (tenant_id, at, action, payload, user_email, gas_status, raw_body)"
                                " VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                                (tenant, now, "member_archive_restore", json.dumps(dict(payload), ensure_ascii=False), user,
                                 "test" if is_test else "pending", None)
                            ).fetchone()[0]
                            extra = {"passThrough": True}
                        elif active:   # 경로 A — 뒷정리: 이미 유효회원. 이름 같을 때만 보관 행 삭제(GAS L9917~9936 이식).
                            active_name = (active["name"] or "").strip()
                            if not arch_name or arch_name != active_name:
                                err_response = {"ok": False, "error": "already-active",
                                                "detail": "이미 유효회원에 등록된 전화번호입니다 — 보관 기록의 이름(%s)과 유효회원 이름(%s)이 달라 자동 정리하지 않습니다"
                                                          % (arch_name or "?", active_name or "?")}
                            elif is_dry:   # 미리보기 — 치명① 공통 게이트: 쓰기·GAS 호출 없이 판정 결과만
                                err_response = {"ok": True, "dryRun": True, "preview": {
                                    "path": "cleanup", "target": {"name": arch_name, "phone": payload.get("phone"), "archiveRow": member_no},
                                    "activeRow": active["member_no"]}}
                            else:
                                revert = {"kind": "archive_row", "tenant": tenant, "member_no": member_no,
                                          "cur_scope": None, "old_row": arch, "field": "LOSS보관 이관정리",
                                          "name": arch_name, "phone_masked": _mask_phone(phone)}
                                conn.execute("DELETE FROM members WHERE tenant_id=%s AND member_no=%s AND scope='archive'",
                                            (tenant, member_no))
                                conn.execute(
                                    "INSERT INTO member_change_log (tenant_id, at, staff, member_no, member_name, phone_masked,"
                                    " field, old_value, new_value, screen) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                                    (tenant, now, staff, member_no, arch_name, _mask_phone(phone), "LOSS보관 이관정리",
                                     "LOSS보관 삭제 · 원본: %s" % json.dumps(arch, ensure_ascii=False, default=str)[:900],
                                     "유효회원 회원번호 %s" % active["member_no"], "멤버십"))
                                payload_log = dict(payload)
                                payload_log["_member_no"] = member_no   # 대조 전용(reconcile_dual_write.py)
                                log_id = conn.execute(
                                    "INSERT INTO write_log (tenant_id, at, action, payload, user_email, gas_status, raw_body)"
                                    " VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                                    (tenant, now, "member_archive_restore", json.dumps(payload_log, ensure_ascii=False), user,
                                     "test" if is_test else "pending", None)
                                ).fetchone()[0]
                                extra = {"cleaned": True, "name": arch_name, "archiveRow": member_no, "activeRow": active["member_no"]}
                        elif not arch_name:
                            err_response = {"ok": False, "error": "archive-row-invalid", "detail": "보관 행에서 회원명을 읽지 못했습니다"}
                        else:   # 경로 B — 복귀(GAS L9937~10023 이식) — scope 전환 + 칸 인계 한 UPDATE
                            try:
                                data_obj = json.loads(arch["data"]) if arch["data"] else {}
                                if not isinstance(data_obj, dict):
                                    data_obj = {}
                            except Exception:
                                data_obj = {}
                            # 주소·비고·나이는 archive scope 행에 실컬럼이 없다(schema.sql 백필·sync_owner_cols 둘 다
                            # scope='valid' 한정) — data JSON 에서 직접 읽는다(_data_get_norm 재사용).
                            addr_key, addr_hit = _data_get_norm(data_obj, "주소")
                            note_key, note_hit = _data_get_norm(data_obj, "비고")
                            age_key, age_hit = _data_get_norm(data_obj, "나이")
                            carry_addr = str(data_obj.get(addr_key) or "").strip() if addr_hit else ""
                            carry_note = str(data_obj.get(note_key) or "").strip() if note_hit else ""
                            carry_age = str(data_obj.get(age_key) or "").strip() if age_hit else ""
                            carry_kind = (arch.get("kind") or "").strip()
                            carry_owner = (arch.get("owner") or "").strip()
                            seq_raw = arch.get("reg_seq") or ""
                            seq_digits = re.sub(r"[^0-9]", "", str(seq_raw))
                            seq_n = int(seq_digits) if seq_digits else None
                            new_seq = str(seq_n + 1) if (seq_n and seq_n > 0) else str(seq_raw)   # GAS 그대로 — 못 읽으면 원값

                            reg_class = str(payload.get("regClass") or "").strip() or "L재등록"
                            program_new = str(payload.get("program") or "").strip() or (arch.get("program") or "")
                            reg_date = str(payload.get("regDate") or "").strip() or now[:10]
                            try:
                                months_n = int(payload.get("months"))
                            except (TypeError, ValueError):
                                months_n = 0
                            start_in = str(payload.get("startDate") or "").strip()
                            end_in = str(payload.get("endDate") or "").strip()

                            # 시작/종료/잔여일 — 개월수 계산(있으면) 위에 명시적 시작/종료일이 항상 우선(GAS L10004~10011).
                            # 개월 덧셈은 _add_months_js(JS setMonth 오버플로) — api_reception._add_months(말일 클램프)
                            # 와 결과가 다르다(배1054 검토①·8/31+6→클램프 2/28 대신 오버플로 3/3, -1일=3/2).
                            final_start, final_end, final_remain = "", "", ""
                            if months_n > 0:
                                base_start = start_in or reg_date
                                try:
                                    end_calc = _add_months_js(base_start, months_n)
                                    ed = datetime.strptime(end_calc, "%Y-%m-%d") - timedelta(days=1)
                                    final_start, final_end = base_start, ed.strftime("%Y-%m-%d")
                                    now_dt = datetime.strptime(now, "%Y-%m-%d %H:%M:%S")
                                    final_remain = str(round((ed - now_dt).total_seconds() / 86400))
                                except ValueError:
                                    pass
                            if start_in:
                                final_start = start_in
                            if end_in:
                                final_end = end_in
                                try:
                                    ed2 = datetime.strptime(end_in, "%Y-%m-%d")
                                    now_dt = datetime.strptime(now, "%Y-%m-%d %H:%M:%S")
                                    final_remain = str(round((ed2 - now_dt).total_seconds() / 86400))
                                except ValueError:
                                    pass

                            preview = {
                                "target": {"name": arch_name, "phone": payload.get("phone"), "archiveRow": member_no},
                                "carried": {"나이": carry_age, "회원구분": carry_kind, "수강반종목명": arch.get("program") or "",
                                            "담당자": carry_owner, "주소": carry_addr, "비고": carry_note,
                                            "등록회차": "%s → %s" % (str(seq_raw), new_seq)},
                                "newValues": {"regDate": reg_date, "startDate": start_in or None, "endDate": end_in or None,
                                              "months": months_n if months_n > 0 else None, "regClass": reg_class, "program": program_new},
                            }
                            if is_dry:   # 미리보기 — 치명① 공통 게이트: 쓰기·GAS 호출 없이 판정 결과만
                                err_response = {"ok": True, "dryRun": True, "preview": preview}
                            else:
                                set_vals = {
                                    "scope": "valid", "name": arch_name, "program": program_new, "reg_class": reg_class,
                                    "reg_seq": new_seq, "reg_date": reg_date, "start_date": final_start,
                                    "end_date": final_end, "remain_days": final_remain,
                                    "kind": carry_kind, "owner": carry_owner or MEMBER_DEFAULT_OWNER,
                                    "address": carry_addr, "note": carry_note, "age": carry_age,
                                }
                                for c in ARCHIVE_RESET_COLS:
                                    set_vals[c] = ""
                                # data JSON 도 리셋 19칸의 시트 라벨을 빈 문자열로 덮는다(배1054 검토③ — members_report
                                # 가 data 를 직독) · synced_at 도 이 요청 시각으로 갱신한다(배1054 검토⑤ — 이래야
                                # sync_members.py replace_scope 의 diff-삭제 가드가 '이번 배치 시작 뒤 서버가 만든
                                # valid 행'으로 이 행을 알아보고 배치 목록에 아직 없어도 안 지운다).
                                reset_json = json.dumps({v: "" for v in _ARCHIVE_RESET_LABELS.values()}, ensure_ascii=False)
                                set_sql = ", ".join("%s=%%s" % c for c in set_vals)
                                conn.execute(
                                    "UPDATE members SET " + set_sql + ", data=(data::jsonb || %s::jsonb)::text, synced_at=%s"
                                    " WHERE tenant_id=%s AND member_no=%s AND scope='archive'",
                                    list(set_vals.values()) + [reset_json, now, tenant, member_no])
                                revert = {"kind": "archive_row", "tenant": tenant, "member_no": member_no,
                                          "cur_scope": "valid", "old_row": arch, "field": "LOSS보관 재등록복귀",
                                          "name": arch_name, "phone_masked": _mask_phone(phone)}
                                conn.execute(
                                    "INSERT INTO member_change_log (tenant_id, at, staff, member_no, member_name, phone_masked,"
                                    " field, old_value, new_value, screen) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                                    (tenant, now, staff, member_no, arch_name, _mask_phone(phone), "LOSS보관 원본삭제",
                                     "LOSS보관 원본: %s" % json.dumps(arch, ensure_ascii=False, default=str)[:900],
                                     "유효회원 전환(등록분류:%s)" % reg_class, "멤버십"))
                                conn.execute(
                                    "INSERT INTO member_change_log (tenant_id, at, staff, member_no, member_name, phone_masked,"
                                    " field, old_value, new_value, screen) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                                    (tenant, now, staff, member_no, arch_name, _mask_phone(phone), "LOSS보관 재등록복귀",
                                     "LOSS보관 회원번호 %s" % member_no,
                                     "유효회원 회원번호 %s(등록분류:%s)" % (member_no, reg_class), "멤버십"))
                                payload_log = dict(payload)
                                payload_log["_member_no"] = member_no      # 대조 전용(reconcile_dual_write.py)
                                # sync_members.py::sync_owner_cols 예외 대상(배1054 검토② — 되밀림 차단). 라벨
                                # 중 세부구분·LOSS일자 등 OWNER_COLS 밖 2개는 sync 쪽에서 못 찾아 조용히 무시된다
                                # (field_to_col.get() 이 None → skip) — 목록에 다 넣어도 해롭지 않다.
                                payload_log["_cols"] = list(_ARCHIVE_RESET_LABELS.values())
                                payload_log["_saved"] = {"종료일자": final_end, "등록회차": new_seq}   # 대조 전용(경미①)
                                log_id = conn.execute(
                                    "INSERT INTO write_log (tenant_id, at, action, payload, user_email, gas_status, raw_body)"
                                    " VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                                    (tenant, now, "member_archive_restore", json.dumps(payload_log, ensure_ascii=False), user,
                                     "test" if is_test else "pending", None)
                                ).fetchone()[0]
                                extra = {"restored": True, "name": arch_name, "phone": payload.get("phone"),
                                        "archiveRow": member_no, "newRow": member_no, "member_no": member_no,
                                        "regClass": reg_class, "seq": new_seq}
    except Exception:
        conn.close()
        raise
    if err_response is not None:
        conn.close()
        return err_response
    return _finish(conn, raw_body, log_id, is_test, extra, revert)


def _prog_sig(text, months):
    """수강반종목명의 '같은 상품인가' 지문 — GAS _memberProgramCanon_ 안의 _sig(Survey.js L2756) 그대로."""
    t = str(text or "")
    grade = "N" if "노블레스" in t else ("P" if "플래티넘" in t else "")
    if not grade:
        return ""
    golf = "G" if "골프" in t else "-"
    term = "S" if "(단)" in t else ("R" if "(정)" in t else ("S" if (0 < months <= 1) else "R"))
    return grade + golf + term


def _program_canon(conn, tenant, program, months):
    """화면이 보낸 축약 종목명('플래티넘')을 유효회원이 실제로 쓰는 정식명으로 맞춘다 —
    GAS _memberProgramCanon_(Survey.js L2753) 이식. GAS 는 유효회원 시트의 수강반종목명 열을 훑어
    같은 지문 중 가장 많이 쓰인 표기를 고른다. 서버는 그 열의 거울(members.program · scope='valid')을
    같은 방식으로 훑는다 — 거울이 그 시트 열 자체라 결과가 같다. 지문이 안 잡히면(등급 낱말이 없으면)
    원문 그대로 — GAS 와 동일. 동률일 때 먼저 나온 값을 쓰는 것도 같게 하려고 member_no 순으로 읽는다."""
    raw = str(program or "").strip()
    want = _prog_sig(raw, months)
    if not raw or not want:
        return raw
    tally = {}
    for r in conn.execute(
            "SELECT program FROM members WHERE tenant_id=%s AND scope='valid' AND COALESCE(program,'')<>''"
            " ORDER BY member_no", (tenant,)).fetchall():
        v = str(r["program"] or "").strip()
        if not v or _prog_sig(v, 0) != want:   # 기존 값은 months=0 으로 지문을 낸다(GAS _sig(v, 0))
            continue
        tally[v] = tally.get(v, 0) + 1
    best, best_n = "", 0
    for k, n in tally.items():
        if n > best_n:
            best, best_n = k, n
    return best or raw


def _handle_member_registered_add(payload, raw_body, user):
    """member_registered_add(5단계 · 배1050) — 화면 '+직접등록'. GAS Survey.js L9021~9050 + _memberActiveUpsert_
    (L2781~2930) 이식.

    두 탭 중 서버가 맡는 것은 유효회원뿐이다. '26년 등록현황'은 월별 체크표라 미러에 없고 시트 전용으로
    둔다(시포 스펙 §2-3 판단) — GAS write-through 가 그대로 갱신한다.

    행 찾기 = 전화 정규화. 서버가 손대는 경우는 **전화가 정확히 1건 잡힐 때뿐**이다.
      · 0건(새 회원) = 서버가 행을 만들지 않는다. 회원번호는 GAS member_registry_build 가 채번하고
        미러 열쇠가 (member_no, scope) 라서, 서버가 번호를 지어내면 다음 배치와 충돌한다 — GAS 로 넘기고
        5분 뒤 sync 가 그 행을 싣는다(member_active_update 의 passThrough 와 같은 이유).
      · 2건+(가족 공유 전화) = GAS 도 phone-ambiguous 로 거부한다(L2834 · 이때 등록현황 upsert 와 텔레그램은
        이미 나간 뒤다). 서버가 먼저 거부하면 등록현황이 안 갱신돼 결과가 달라지므로 그대로 넘긴다.
    등록회차 = 등록일자가 실제로 바뀔 때만 +1(GAS L2870~2873 판정 그대로 — 분류 글자가 아니라 날짜로 가른다).
    담당자는 GAS 와 같이 항상 MEMBER_DEFAULT_OWNER 로 덮는다(opts.owner 고정 · L2785)."""
    from datetime import datetime, timedelta   # noqa: PLC0415 — 이 함수 하나만 쓴다(다른 핸들러 관례 그대로)

    phone = _norm_phone(payload.get("phone"))
    if not phone:
        return {"ok": False, "error": "전화번호 필수(중복 방지 키)"}
    now = api_write._now_kst()
    is_test = db.is_test_payload(payload)
    tenant = "selftest" if is_test else db.TENANT
    staff = _log_who(payload, user)
    name = str(payload.get("name") or "").strip()
    reg_date = str(payload.get("regDate") or "").strip() or now[:10]
    age = str(payload.get("age") or "").strip()
    try:
        months = int(payload.get("months"))
    except (TypeError, ValueError):
        months = 0

    try:
        conn = db.connect()
    except db.Error as e:
        return {"ok": False, "error": "server-forward-failed", "detail": "DB 열기 실패: %s" % e, "noRetry": False}

    log_id, revert, extra = None, None, None
    try:
        with conn:
            rows = conn.execute(
                "SELECT * FROM members WHERE tenant_id=%s AND scope='valid' AND phone=%s"
                " ORDER BY member_no FOR UPDATE", (tenant, phone)).fetchall()
            payload_log = dict(payload)
            if len(rows) != 1:
                extra = {"passThrough": True, "activeMatched": len(rows)}
            else:
                cur = dict(rows[0])
                member_no = cur["member_no"]
                payload_log["_member_no"] = member_no   # 대조 전용(reconcile_dual_write.py) — 화면이 보낸 값이 아니다
                set_vals = {"owner": MEMBER_DEFAULT_OWNER}
                if name:
                    set_vals["name"] = name
                program = _program_canon(conn, tenant, payload.get("program"), months)
                if program:
                    set_vals["program"] = program
                set_vals["reg_date"] = reg_date
                if age:
                    set_vals["age"] = age
                if months > 0:   # 개월수가 있을 때만 기간 3칸을 쓴다(GAS moN>0 조건 그대로)
                    start = str(payload.get("startDate") or "").strip() or reg_date
                    try:
                        ed = datetime.strptime(_add_months_js(start, months), "%Y-%m-%d") - timedelta(days=1)
                        now_dt = datetime.strptime(now, "%Y-%m-%d %H:%M:%S")
                        set_vals["start_date"] = start
                        set_vals["end_date"] = ed.strftime("%Y-%m-%d")
                        set_vals["remain_days"] = str(round((ed - now_dt).total_seconds() / 86400))
                    except ValueError:
                        pass
                prev_reg = str(cur.get("reg_date") or "").strip()
                if prev_reg and prev_reg != reg_date:   # 재등록 — 옛 등록일자가 있어야 비교가 성립한다(GAS 그대로)
                    digits = re.sub(r"[^0-9]", "", str(cur.get("reg_seq") or ""))
                    prev_seq = int(digits) if digits else 0
                    set_vals["reg_seq"] = str((prev_seq if prev_seq > 0 else 1) + 1)
                changed = {c: v for c, v in set_vals.items() if str(cur.get(c) or "") != str(v)}
                if changed:
                    conn.execute(
                        "UPDATE members SET " + ", ".join("%s=%%s" % c for c in changed) + ", synced_at=%s"
                        " WHERE tenant_id=%s AND member_no=%s AND scope='valid'",
                        list(changed.values()) + [now, tenant, member_no])
                    revert = {"kind": "archive_row", "tenant": tenant, "member_no": member_no,
                              "cur_scope": "valid", "old_row": cur, "field": "등록 추가",
                              "name": cur.get("name") or "", "phone_masked": _mask_phone(phone)}
                    conn.execute(
                        "INSERT INTO member_change_log (tenant_id, at, staff, member_no, member_name, phone_masked,"
                        " field, old_value, new_value, screen) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                        (tenant, now, staff, member_no, cur.get("name") or "", _mask_phone(phone), "등록 추가",
                         json.dumps({c: cur.get(c) for c in changed}, ensure_ascii=False, default=str)[:900],
                         json.dumps(changed, ensure_ascii=False, default=str)[:900], "멤버십"))
                extra = {"member_no": member_no, "updated": sorted(changed)}
            log_id = conn.execute(
                "INSERT INTO write_log (tenant_id, at, action, payload, user_email, gas_status, raw_body)"
                " VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                (tenant, now, "member_registered_add", json.dumps(payload_log, ensure_ascii=False), user,
                 "test" if is_test else "pending", None)
            ).fetchone()[0]
    except Exception:
        conn.close()
        raise
    return _finish(conn, raw_body, log_id, is_test, dict(extra, message="등록 추가되었습니다."), revert)


def _handle_member_registered_remove(payload, raw_body, user):
    """member_registered_remove(7단계 · 배1050) — 화면 '+직접등록' 되돌리기. GAS Survey.js L9055~9065 +
    _regRemove_·_regActiveRemoveIfSole_(L2634~2700) 이식.

    등록현황 탭 삭제는 시트 전용이라 GAS 가 한다(§2-3 과 같은 결정). 서버가 맡는 것은 유효회원 행이고,
    지우는 조건도 GAS 와 같다 — **전화 매칭이 정확히 1건이고 등록회차가 1일 때만**(이전 등록 이력이 있는
    회원은 지우지 않는다 · INC-020). 0건·2건+·회차 2 이상이면 유효회원은 손대지 않는다.

    비밀번호는 서버가 갖고 있지 않다(STAFF_GATE_PW = GAS 속성 · 새 인증체계를 만들지 않는다는 약속 L21).
    게이트는 GAS write-through 가 그대로 판정하고, 거부하면 _finish 가 지운 행을 스냅샷으로 되살린다.
    빈 비밀번호는 GAS 가 반드시 거부하므로 서버가 아예 지우지 않는다 — 오타 한 번에 지웠다 되살리는
    왕복을 만들지 않기 위한 앞단 가드다(판정 자체는 여전히 GAS 몫)."""
    phone = _norm_phone(payload.get("phone"))
    if not phone:
        return {"ok": False, "error": "phone 필수"}
    now = api_write._now_kst()
    is_test = db.is_test_payload(payload)
    tenant = "selftest" if is_test else db.TENANT
    staff = _log_who(payload, user)
    has_pw = str(payload.get("password") or "") != ""

    try:
        conn = db.connect()
    except db.Error as e:
        return {"ok": False, "error": "server-forward-failed", "detail": "DB 열기 실패: %s" % e, "noRetry": False}

    log_id, revert, extra = None, None, None
    try:
        with conn:
            rows = conn.execute(
                "SELECT * FROM members WHERE tenant_id=%s AND scope='valid' AND phone=%s"
                " ORDER BY member_no FOR UPDATE", (tenant, phone)).fetchall()
            payload_log = dict(payload)
            payload_log.pop("password", None)   # 게이트 비밀번호는 원장에 남기지 않는다
            seq_n = None
            if len(rows) == 1:
                digits = re.sub(r"[^0-9]", "", str(dict(rows[0]).get("reg_seq") or ""))
                seq_n = int(digits) if digits else 0
            if has_pw and len(rows) == 1 and seq_n == 1:
                cur = dict(rows[0])
                member_no = cur["member_no"]
                payload_log["_member_no"] = member_no
                conn.execute("DELETE FROM members WHERE tenant_id=%s AND member_no=%s AND scope='valid'",
                             (tenant, member_no))
                revert = {"kind": "archive_row", "tenant": tenant, "member_no": member_no,
                          "cur_scope": None, "old_row": cur, "field": "등록 해제",
                          "name": cur.get("name") or "", "phone_masked": _mask_phone(phone)}
                conn.execute(
                    "INSERT INTO member_change_log (tenant_id, at, staff, member_no, member_name, phone_masked,"
                    " field, old_value, new_value, screen) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (tenant, now, staff, member_no, cur.get("name") or "", _mask_phone(phone), "등록 해제",
                     "유효회원 원본: %s" % json.dumps(cur, ensure_ascii=False, default=str)[:900],
                     "삭제(등록회차 1)", "멤버십"))
                extra = {"activeRemoved": True, "member_no": member_no}
            else:
                extra = {"activeRemoved": False, "activeMatched": len(rows), "regSeq": seq_n}
            log_id = conn.execute(
                "INSERT INTO write_log (tenant_id, at, action, payload, user_email, gas_status, raw_body)"
                " VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                (tenant, now, "member_registered_remove", json.dumps(payload_log, ensure_ascii=False), user,
                 "test" if is_test else "pending", None)
            ).fetchone()[0]
    except Exception:
        conn.close()
        raise
    return _finish(conn, raw_body, log_id, is_test, dict(extra, message="등록이 해제되었습니다."), revert)


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
    try:
        idem_conn = db.connect()
    except db.Error as e:
        return {"ok": False, "error": "server-forward-failed", "detail": "DB 열기 실패: %s" % e, "noRetry": False}
    # /api/write 와 같은 방식(api_write._idem_hit 재사용) — 서버는 처리를 끝냈는데 응답만 유실돼 화면이
    # 같은 idem 열쇠로 재전송하면, 핸들러를 다시 태우지 않고 그때 저장한 응답을 그대로 돌려준다(배1054 경미④).
    prev = api_write._idem_hit(idem_conn, user, payload)
    idem_conn.close()
    if prev is not None:
        return prev

    if action == "member_active_update":   # 3단계(배1054) — 칸 자유 쓰기·행 변환·일괄이 나머지 둘과 모양이 달라 갈라둔다
        return _handle_member_active_update(payload, body, user)
    if action == "member_hold_approve":    # 4단계(배1054) — 2원장(members+hold_items)·멱등 가드가 따로 필요해 갈라둔다
        return _handle_member_hold_approve(payload, body, user)
    if action == "member_archive_restore":  # 6단계(배1054) — phone 열쇠·경로 2갈래(뒷정리/복귀)·dryRun 이 따로 필요해 갈라둔다
        return _handle_member_archive_restore(payload, body, user)
    if action == "member_registered_add":    # 5단계(배1050) — 두 탭 중 유효회원만 서버, 새 회원은 GAS 채번에 맡긴다
        return _handle_member_registered_add(payload, body, user)
    if action == "member_registered_remove":  # 7단계(배1050) — 유효회원 삭제는 '단독·등록회차 1'일 때만
        return _handle_member_registered_remove(payload, body, user)

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

    # member_archive_restore(6단계) revert — kind='archive_row', 경로 B(cur_scope 있음)는 UPDATE 로,
    # 경로 A(cur_scope 없음 · 삭제했던 행)는 INSERT 로 전체 스냅샷을 되돌린다.
    api_write._gas_forward = lambda body, url_key="FUNNEL_EXEC_URL": {"ok": False, "error": "gas-error"}
    try:
        conn5 = _FakeConn()
        revert5 = {"kind": "archive_row", "tenant": "wellperion", "member_no": "M00005", "cur_scope": "valid",
                   "old_row": {"tenant_id": "wellperion", "member_no": "M00005", "scope": "archive", "name": "테스트"},
                   "name": "테스트", "phone_masked": "010-1234-****"}
        out5 = _finish(conn5, b"{}", 1, False, {"restored": True, "member_no": "M00005"}, revert5)
    finally:
        api_write._gas_forward = orig_forward
    assert out5["ok"] is False and conn5.closed
    assert any("UPDATE members SET" in sql and "scope=%s" in sql for sql, _ in conn5.executed), conn5.executed
    assert not any(sql.startswith("INSERT INTO members") for sql, _ in conn5.executed), conn5.executed

    api_write._gas_forward = lambda body, url_key="FUNNEL_EXEC_URL": {"ok": False, "error": "gas-error"}
    try:
        conn6 = _FakeConn()
        revert6 = {"kind": "archive_row", "tenant": "wellperion", "member_no": "M00006", "cur_scope": None,
                   "old_row": {"tenant_id": "wellperion", "member_no": "M00006", "scope": "archive", "name": "테스트"},
                   "name": "테스트", "phone_masked": "010-1234-****"}
        out6 = _finish(conn6, b"{}", 1, False, {"cleaned": True}, revert6)
    finally:
        api_write._gas_forward = orig_forward
    assert out6["ok"] is False and conn6.closed
    assert any(sql.startswith("INSERT INTO members") for sql, _ in conn6.executed), conn6.executed
    assert sum("member_change_log" in sql for sql, _ in conn6.executed) == 1, conn6.executed


class _FakeHoldCur:
    """member_hold_approve 단위 검증용 최소 커서 — fetchone/fetchall 만 미리 정한 값을 돌려준다."""
    def __init__(self, one=None, many=None):
        self._one, self._many = one, many

    def fetchone(self):
        return self._one

    def fetchall(self):
        return self._many or []


class _FakeHoldConn:
    """member_hold_approve 단위 검증용 최소 DB 스텁(네트워크·실 DB 없음) — SQL 앞부분으로 결과를 골라 돌려준다."""
    def __init__(self, hold_row=None, member_rows=None):
        self.executed = []
        self.hold_row, self.member_rows = hold_row, member_rows

    def execute(self, sql, args=()):
        self.executed.append((sql, args))
        if "SELECT status, data FROM hold_items" in sql:
            return _FakeHoldCur(one=self.hold_row)
        if "SELECT * FROM members" in sql:
            return _FakeHoldCur(many=self.member_rows)
        if "RETURNING id" in sql:
            return _FakeHoldCur(one=[1])
        return _FakeHoldCur()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def close(self):
        pass


def _selftest_hold_approve_passthrough():
    """member_hold_approve(4단계) 재검토(치명2) — 접수 행이 미러에 없으면(화면은 GAS 라이브라 5분 미러가
    아직 못 따라간 신규 접수일 수 있다) 거부 대신 GAS pass-through 로 넘어가는지(DB·네트워크 없음 · is_test
    payload 라 gas_status=skipped-test 로 확인)."""
    fake = _FakeHoldConn(hold_row=None)
    orig_connect = db.connect
    db.connect = lambda: fake
    try:
        out = _handle_member_hold_approve(
            {"decision": "approve", "intakeRow": 9, "keyPhone": "010-0000-0000"}, b"{}", "테스트")
    finally:
        db.connect = orig_connect
    assert out["ok"] is True and out["gas_status"] == "skipped-test" and out.get("passThrough") is True, out
    assert not any("UPDATE hold_items" in sql or "UPDATE members" in sql for sql, _ in fake.executed), fake.executed


def _selftest_hold_approve_gas_reread():
    """member_hold_approve(4단계) 재검토(치명1) — 승인 계산 재료가 5분 옛 미러(idata)가 아니라 gas_get 재조회
    값으로 쓰이는지 단위 검증(DB·네트워크 없음 · gas_get 스텁). 미러는 옛 값(연장·2026-01-01·5일)을,
    GAS 재조회는 다른 값(신규·2026-09-10·14일)을 돌려준다 — 응답 period 가 재조회 값 기준
    (2026-09-10~2026-09-23)이면 통과, 미러 값 기준이면 실패."""
    stale_idata = {"phone": "01099998888", "status": "접수대기", "start": "2026-01-01", "wishDays": 5, "kind": "연장"}
    live_row = {"intakeRow": 7, "start": "2026-09-10", "wishDays": 14, "kind": "신규", "phone": "01099998888"}
    member_row = {"member_no": "M00099", "phone": "01099998888", "name": "테스트", "hold_count": "0",
                  "hold_cum_days": "0", "hold_period": "", "hold_start_date": "", "hold_end_date": "",
                  "hold_status": ""}
    fake = _FakeHoldConn(hold_row={"status": "접수대기", "data": json.dumps(stale_idata, ensure_ascii=False)},
                         member_rows=[member_row])
    orig_connect, orig_gas_get, orig_forward = db.connect, globals()["gas_get"], api_write._gas_forward
    db.connect = lambda: fake
    globals()["gas_get"] = lambda url_key, action, params=None, timeout=90: {"ok": True, "data": [live_row]}
    api_write._gas_forward = lambda body, url_key="FUNNEL_EXEC_URL": {"ok": False, "error": "test-reject"}
    try:
        out = _handle_member_hold_approve(
            {"decision": "approve", "intakeRow": 7, "keyPhone": "010-9999-8888"}, b"{}", "테스트")
    finally:
        db.connect, api_write._gas_forward = orig_connect, orig_forward
        globals()["gas_get"] = orig_gas_get
    assert out["period"] == "2026-09-10 ~ 2026-09-23", out   # GAS 재조회 값 기준(미러 값이면 2026-01-05)
    assert out["count"] == 1 and out["cumDays"] == 14, out
    hold_updates = [a for sql, a in fake.executed if "UPDATE hold_items SET status" in sql]
    assert hold_updates and '"_server_edited"' in hold_updates[0][1], hold_updates   # 재검토(중요3)


class _FakeArchiveCur:
    """member_archive_restore 단위 검증용 최소 커서 — fetchone/fetchall 만 미리 정한 값을 돌려준다."""
    def __init__(self, one=None, many=None):
        self._one, self._many = one, many

    def fetchone(self):
        return self._one

    def fetchall(self):
        return self._many or []


class _FakeArchiveConn:
    """member_archive_restore 단위 검증용 최소 DB 스텁(네트워크·실 DB 없음) — SQL 앞부분으로 결과를 골라 돌려준다."""
    def __init__(self, arch_count=1, arch_row=None, already_valid=None, actives=None):
        self.executed = []
        self.arch_count, self.arch_row = arch_count, arch_row
        self.already_valid, self.actives = already_valid, actives

    def execute(self, sql, args=()):
        self.executed.append((sql, args))
        if "SELECT COUNT(*) FROM members" in sql:
            return _FakeArchiveCur(one=[self.arch_count])
        if "FROM members" in sql and "scope='archive'" in sql and "FOR UPDATE" in sql:
            return _FakeArchiveCur(one=self.arch_row)
        if "SELECT 1 FROM members" in sql and "scope='valid'" in sql:
            return _FakeArchiveCur(one=self.already_valid)
        if "SELECT member_no, name FROM members" in sql:
            return _FakeArchiveCur(many=self.actives)
        if "RETURNING id" in sql:
            return _FakeArchiveCur(one=[1])
        return _FakeArchiveCur()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def close(self):
        pass


_ARCH_ROW_STUB = {"member_no": "M00010", "name": "복귀테스트", "phone": "01011112222", "kind": "일반",
                  "owner": "김담당", "program": "PT", "reg_seq": "1", "data": "{}"}


def _selftest_archive_restore_dry_run_gate():
    """member_archive_restore(6단계) 치명① — dryRun 이면 arch_count==1 판정 직후 공통 게이트에서 막혀
    실제 UPDATE/DELETE·write_log INSERT·GAS 전달 없이 판정(preview)만 나가는지(DB·네트워크 없음)."""
    fake = _FakeArchiveConn(arch_count=1, arch_row=dict(_ARCH_ROW_STUB), already_valid=None, actives=[])
    orig_connect = db.connect
    db.connect = lambda: fake
    try:
        out = _handle_member_archive_restore(
            {"phone": "010-1111-2222", "dryRun": True, "months": 6}, b"{}", "테스트")
    finally:
        db.connect = orig_connect
    assert out["ok"] is True and out["dryRun"] is True and "preview" in out, out
    assert not any(sql.startswith(("UPDATE", "DELETE", "INSERT")) for sql, _ in fake.executed), fake.executed


def _selftest_archive_restore_pk_guard():
    """member_archive_restore 재검토④ — 이 회원번호가 이미 scope='valid' 에도 있으면 PK(tenant_id,member_no,
    scope) 충돌 UPDATE 를 시도하기 전에 already-active 로 거른다(DB·네트워크 없음)."""
    fake = _FakeArchiveConn(arch_count=1, arch_row=dict(_ARCH_ROW_STUB, member_no="M00011"),
                            already_valid=[1], actives=[])
    orig_connect = db.connect
    db.connect = lambda: fake
    try:
        out = _handle_member_archive_restore({"phone": "010-1111-2222"}, b"{}", "테스트")
    finally:
        db.connect = orig_connect
    assert out["ok"] is False and out["error"] == "already-active", out
    assert not any(sql.startswith("UPDATE") for sql, _ in fake.executed), fake.executed


def _selftest_archive_restore_double_click_noop():
    """member_archive_restore 재검토⑥ — COUNT(잠금 없음) 뒤 FOR UPDATE 가 빈 손이면(이중클릭으로 다른
    요청이 먼저 처리) no-op 으로 끝난다 — with 블록 안에서 close+return 하지 않아 __exit__ 커밋 실패가
    안 난다(hold_approve 와 같은 함정 회피 확인, DB·네트워크 없음)."""
    fake = _FakeArchiveConn(arch_count=1, arch_row=None)
    orig_connect = db.connect
    db.connect = lambda: fake
    try:
        out = _handle_member_archive_restore({"phone": "010-1111-2222"}, b"{}", "테스트")
    finally:
        db.connect = orig_connect
    assert out["ok"] is True and out.get("noop") is True, out


def _selftest_archive_restore_active_ambiguous():
    """member_archive_restore 재검토⑦ — 같은 전화 유효회원이 2건+ 인데 이름이 일치하는 행이 정확히 1건이
    아니면(0건·2건+) 서버는 안 고르고 GAS pass-through 로 넘긴다(DB·네트워크 없음 · is_test payload 라
    gas_status=skipped-test 로 확인)."""
    actives = [{"member_no": "M00001", "name": "아빠"}, {"member_no": "M00002", "name": "엄마"}]
    fake = _FakeArchiveConn(arch_count=1, arch_row=dict(_ARCH_ROW_STUB, member_no="M00012", name="가족회원"),
                            already_valid=None, actives=actives)
    orig_connect = db.connect
    db.connect = lambda: fake
    try:
        out = _handle_member_archive_restore({"phone": "010-0000-0000"}, b"{}", "테스트")
    finally:
        db.connect = orig_connect
    assert out["ok"] is True and out.get("passThrough") is True and out["gas_status"] == "skipped-test", out
    assert not any(sql.startswith(("UPDATE", "DELETE")) for sql, _ in fake.executed), fake.executed


def _selftest_archive_restore_write_paths():
    """member_archive_restore 경로 A·B 실제 실행 자체점검(배1054 경미⑤) — _FakeArchiveConn 재활용,
    DB·네트워크 없음(is_test payload 라 GAS 호출도 없다). 경로 A(뒷정리)는 DELETE 만, 경로 B(복귀)는
    UPDATE 가 실제로 나가는지 + 개월 계산(_add_months_js)·19칸 리셋(실컬럼·data JSON 둘 다)이 맞는지
    값까지 확인한다(기존 3점검이 상수·가드 갈래만 봤다면 여긴 계산·값 산출까지 본다)."""
    from datetime import datetime, timedelta   # noqa: PLC0415 — 이 함수 하나만 쓴다
    orig_now, orig_connect = api_write._now_kst, db.connect
    api_write._now_kst = lambda: "2026-09-08 12:00:00"   # 개월 계산 기준 시각 고정 — 실행 시각에 안 흔들린다
    try:
        # 경로 A — 뒷정리: 이미 유효회원(이름 일치) → 보관 행 DELETE 만 나가고 UPDATE 는 없어야 한다.
        arch_a = dict(_ARCH_ROW_STUB, member_no="M00020", name="정리대상")
        fake_a = _FakeArchiveConn(arch_count=1, arch_row=arch_a, already_valid=None,
                                  actives=[{"member_no": "M00001", "name": "정리대상"}])
        db.connect = lambda: fake_a
        out_a = _handle_member_archive_restore({"phone": "010-0000-0000"}, b"{}", "테스트")
        assert out_a["ok"] is True and out_a.get("cleaned") is True and out_a["gas_status"] == "skipped-test", out_a
        assert any(sql.startswith("DELETE FROM members") for sql, _ in fake_a.executed), fake_a.executed
        assert not any(sql.startswith("UPDATE members") for sql, _ in fake_a.executed), fake_a.executed

        # 경로 B — 복귀: 유효회원 없음 → scope 전환 UPDATE 한 번. 개월(6)+고정 시각으로 종료일을 직접
        # 계산해 대조하고, 리셋 19칸이 실컬럼·data JSON 둘 다 빈 문자열인지 값으로 확인한다.
        arch_b = dict(_ARCH_ROW_STUB, member_no="M00021", name="복귀대상", reg_seq="3")
        fake_b = _FakeArchiveConn(arch_count=1, arch_row=arch_b, already_valid=None, actives=[])
        db.connect = lambda: fake_b
        out_b = _handle_member_archive_restore({"phone": "010-0000-0000", "months": 6}, b"{}", "테스트")
        assert out_b["ok"] is True and out_b.get("restored") is True and out_b["seq"] == "4", out_b
        upd_sql, upd_args = next((sql, a) for sql, a in fake_b.executed if sql.startswith("UPDATE members"))
        expected_end = (datetime.strptime(_add_months_js("2026-09-08", 6), "%Y-%m-%d")
                        - timedelta(days=1)).strftime("%Y-%m-%d")
        assert upd_args[7] == expected_end, (upd_args[7], expected_end)          # set_vals 순서 8번째 = end_date
        assert all(upd_args[14 + i] == "" for i in range(len(ARCHIVE_RESET_COLS))), upd_args   # 리셋 19칸(실컬럼)
        reset_json = json.loads(upd_args[-4])                                   # data JSON 오버레이 값
        assert set(reset_json) == set(_ARCHIVE_RESET_LABELS.values()) and all(v == "" for v in reset_json.values()), reset_json
        assert "data=(data::jsonb || " in upd_sql and "synced_at=%s" in upd_sql, upd_sql
    finally:
        api_write._now_kst, db.connect = orig_now, orig_connect


class _FakeRegConn:
    """member_registered_add/remove 단위 검증용 최소 DB 스텁 — SQL 앞부분으로 결과를 골라 돌려준다."""
    def __init__(self, actives=None, programs=()):
        self.executed = []
        self.actives = actives or []
        self.programs = [{"program": p} for p in programs]

    def execute(self, sql, args=()):
        self.executed.append((sql, args))
        if "SELECT program FROM members" in sql:
            return _FakeArchiveCur(many=self.programs)
        if "SELECT * FROM members" in sql and "FOR UPDATE" in sql:
            return _FakeArchiveCur(many=self.actives)
        if "RETURNING id" in sql:
            return _FakeArchiveCur(one=[1])
        return _FakeArchiveCur()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def close(self):
        pass


def _run_reg(handler, payload, conn):
    orig_connect = db.connect
    db.connect = lambda: conn
    try:
        return handler(payload, b"{}", "테스트")
    finally:
        db.connect = orig_connect


def _selftest_registered_add_passthrough():
    """전화가 0건(새 회원)·2건+(가족 공유)면 서버는 회원 원장을 안 건드리고 GAS 로 넘긴다 —
    회원번호 채번은 GAS registry_build 몫이고, 2건+는 GAS 도 거부하되 등록현황 갱신은 이미 끝난 뒤다."""
    for actives in ([], [{"member_no": "M1"}, {"member_no": "M2"}]):
        conn = _FakeRegConn(actives=actives)
        out = _run_reg(_handle_member_registered_add,
                       {"name": "[테스트] 등록추가", "phone": "010-1111-2222", "months": 3}, conn)
        assert out["ok"] is True and out.get("passThrough") is True, out
        assert out["gas_status"] == "skipped-test", out
        assert not any("UPDATE members" in s for s, _ in conn.executed), conn.executed


def _selftest_registered_add_reg_seq_and_period():
    """전화 단독 매칭이면 서버가 고친다 — 등록일자가 바뀌었으니 등록회차 +1, 개월수가 있으니 기간 3칸,
    담당자는 GAS 와 같이 항상 임정은으로 덮는다."""
    cur = {"member_no": "M00007", "name": "박기순", "phone": "01011112222", "program": "플래티넘(정)",
           "reg_date": "2026-01-10", "reg_seq": "8", "owner": "김담당", "age": "", "start_date": "",
           "end_date": "", "remain_days": ""}
    conn = _FakeRegConn(actives=[cur])
    out = _run_reg(_handle_member_registered_add,
                   {"name": "[테스트] 등록추가", "phone": "010-1111-2222", "regDate": "2026-09-09",
                    "months": 6, "program": "플래티넘"}, conn)
    assert out["ok"] is True and out["member_no"] == "M00007", out
    upd = [(s, a) for s, a in conn.executed if "UPDATE members" in s]
    assert len(upd) == 1, conn.executed
    sql, args = upd[0]
    cols = [p.split("=")[0].strip() for p in sql.split("SET", 1)[1].split(", synced_at")[0].split(",")]
    vals = dict(zip(cols, args))
    assert vals["reg_seq"] == "9", vals            # 8 → 9 (등록일자가 실제로 바뀔 때만 · GAS L2870)
    assert vals["reg_date"] == "2026-09-09", vals
    assert vals["owner"] == MEMBER_DEFAULT_OWNER, vals
    assert vals["start_date"] == "2026-09-09" and vals["end_date"] == "2027-03-08", vals   # 시작+6개월−1일
    assert "등록 추가" in json.dumps(conn.executed, ensure_ascii=False, default=str)


def _selftest_registered_add_same_date_is_idempotent():
    """같은 등록일자로 다시 저장하면 회차가 안 오른다(GAS 멱등 규칙 그대로) — 옛 등록일자가 비어 있어도 안 올린다."""
    for prev_reg in ("2026-09-09", ""):
        cur = {"member_no": "M1", "name": "재저장", "phone": "01011112222", "program": "",
               "reg_date": prev_reg, "reg_seq": "3", "owner": MEMBER_DEFAULT_OWNER}
        conn = _FakeRegConn(actives=[cur])
        _run_reg(_handle_member_registered_add,
                 {"name": "[테스트] 등록추가", "phone": "010-1111-2222", "regDate": "2026-09-09"}, conn)
        upd = [s for s, _ in conn.executed if "UPDATE members" in s]
        assert not any("reg_seq" in s for s in upd), upd


def _selftest_program_canon():
    """축약 종목명을 유효회원이 실제로 쓰는 정식명으로 맞춘다 — 같은 지문 중 최다 표기(GAS 이식).
    등급 낱말이 없으면 지문이 안 서므로 원문 그대로."""
    conn = _FakeRegConn(programs=("플래티넘(정)6개월", "플래티넘(정)6개월", "플래티넘 골프(정)", "노블레스(정)"))
    assert _program_canon(conn, "t", "플래티넘", 6) == "플래티넘(정)6개월"
    assert _program_canon(conn, "t", "플래티넘 골프", 6) == "플래티넘 골프(정)"
    assert _program_canon(conn, "t", "PT 10회", 0) == "PT 10회"      # 등급 없음 = 원문
    assert _program_canon(conn, "t", "", 0) == ""
    assert _prog_sig("플래티넘", 1) == "P-S" and _prog_sig("플래티넘", 6) == "P-R"   # 1개월 이하 = 단기
    assert _prog_sig("노블레스 골프(단)", 12) == "NGS"                # 글자 표기가 개월수보다 우선


def _selftest_registered_remove_sole_and_seq1():
    """유효회원 삭제는 전화 단독 매칭 + 등록회차 1일 때만 — 회차 2 이상·2건+·0건은 손대지 않는다(INC-020)."""
    cur = {"member_no": "M5", "name": "직접등록", "phone": "01011112222", "reg_seq": "1"}
    conn = _FakeRegConn(actives=[cur])
    out = _run_reg(_handle_member_registered_remove,
                   {"name": "[테스트] 해제", "phone": "010-1111-2222", "password": "x"}, conn)
    assert out["ok"] is True and out["activeRemoved"] is True, out
    assert any("DELETE FROM members" in s for s, _ in conn.executed), conn.executed
    assert any("유효회원 원본" in json.dumps(a, ensure_ascii=False, default=str)
               for s, a in conn.executed if "member_change_log" in s), conn.executed

    for actives in ([dict(cur, reg_seq="2")], [], [cur, dict(cur, member_no="M6")]):
        conn2 = _FakeRegConn(actives=actives)
        out2 = _run_reg(_handle_member_registered_remove,
                        {"name": "[테스트] 해제", "phone": "010-1111-2222", "password": "x"}, conn2)
        assert out2["activeRemoved"] is False, out2
        assert not any("DELETE FROM members" in s for s, _ in conn2.executed), conn2.executed


def _selftest_registered_remove_needs_password():
    """비밀번호가 비면 GAS 가 반드시 거부한다 — 서버가 지웠다 되살리는 왕복을 만들지 않는다(판정은 GAS 몫)."""
    conn = _FakeRegConn(actives=[{"member_no": "M5", "name": "직접등록", "phone": "01011112222", "reg_seq": "1"}])
    out = _run_reg(_handle_member_registered_remove, {"name": "[테스트] 해제", "phone": "010-1111-2222"}, conn)
    assert out["activeRemoved"] is False, out
    assert not any("DELETE FROM members" in s for s, _ in conn.executed), conn.executed
    assert _handle_member_registered_remove({"name": "[테스트]"}, b"{}", "")["error"] == "phone 필수"
    assert _handle_member_registered_add({"name": "[테스트]"}, b"{}", "")["error"] == "전화번호 필수(중복 방지 키)"


if __name__ == "__main__":   # python3 api_members_write.py — 갈래·마스킹·직원표기·상태검증 자체점검(서버·DB 없이)
    assert FIELD_TO_COL["PT 담당자"] == "owner_pt" and FIELD_TO_COL["수영 담당자"] == "owner_swim"
    assert len(FIELD_TO_COL) == 5
    assert set(_IMPLEMENTED) == {"member_owner_save", "member_hold_transition", "member_active_update",
                                 "member_hold_approve", "member_archive_restore",
                                 "member_registered_add", "member_registered_remove"}
    assert not set(_IMPLEMENTED) & set(_NOT_YET)
    assert _NOT_YET == ()   # 7종 전부 이 라우트가 처리한다 — 화면이 GAS 경로로 되돌아갈 액션이 없다
    # member_archive_restore(6단계) 상수 — GAS MEMBER_DEFAULT_OWNER·새 행이 안 갖는 칸 목록.
    assert MEMBER_DEFAULT_OWNER == "임정은"
    assert len(ARCHIVE_RESET_COLS) == 19 and len(set(ARCHIVE_RESET_COLS)) == 19
    assert "owner_pt" in ARCHIVE_RESET_COLS and "hold_status" in ARCHIVE_RESET_COLS and "loss_date" in ARCHIVE_RESET_COLS
    assert "address" not in ARCHIVE_RESET_COLS and "note" not in ARCHIVE_RESET_COLS and "age" not in ARCHIVE_RESET_COLS
    # _ARCHIVE_RESET_LABELS — ARCHIVE_RESET_COLS 19칸 전부 라벨이 있어야 한다(sync_members.py OWNER_COLS 의
    # 같은 칸과 값이 같아야 sync 예외 등록이 먹는다 · 배1054 검토②).
    assert set(_ARCHIVE_RESET_LABELS) == set(ARCHIVE_RESET_COLS) and len(_ARCHIVE_RESET_LABELS) == 19
    assert _ARCHIVE_RESET_LABELS["owner_pt"] == "PT 담당자" and _ARCHIVE_RESET_LABELS["hold_status"] == "휴회접수상태"
    assert _ARCHIVE_RESET_LABELS["hold_period"] == "휴회기간(휴회일수)" and _ARCHIVE_RESET_LABELS["loss_date"] == "LOSS일자"
    assert _ARCHIVE_RESET_LABELS["kind2"] == "세부구분" and _ARCHIVE_RESET_LABELS["reg_reservation"] == "재등록예약목록"
    # _add_months_js(GAS setMonth 오버플로 이식 · 배1054 검토①) — api_reception._add_months(말일 클램프)와
    # 갈라지는 지점(말일+개월이 그 달에 없는 날짜)에서 GAS 실측값과 일치해야 한다.
    assert _add_months_js("2026-08-31", 6) == "2027-03-03"   # 클램프면 2027-02-28 — GAS 는 오버플로
    assert _add_months_js("2026-01-31", 1) == "2026-03-03"   # 클램프면 2026-02-28
    assert _add_months_js("2026-05-31", 1) == "2026-07-01"   # 클램프면 2026-06-30
    assert _add_months_js("2026-01-15", 2) == "2026-03-15"   # 말일 아니면 클램프와 결과가 같다
    # member_hold_approve(4단계) 헬퍼 — GAS _holdMinOnce_·_holdEndCalc_·_amNum 이식.
    assert _hold_min_once("신규") == 7 and _hold_min_once("연장") == 1 and _hold_min_once("") == 7
    assert _hold_end_calc("2026-08-01", 30) == "2026-08-30"   # 시작+29일
    assert _hold_end_calc("2026-08-01", 1) == "2026-08-01"    # 1일이면 당일 종료
    assert _hold_num("3") == 3 and _hold_num("") == 0 and _hold_num(None) == 0 and _hold_num("12일") == 12
    assert _hold_num("1-2") == 1   # 재검토⑦ — GAS parseInt("1-2")==1 과 같게(옛 int() 는 ValueError→0 이었다)
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
    assert db.is_test_payload({"phone": "010-0000-0000", "regDate": "2026-09-08"})   # member_archive_restore
    _selftest_finish_revert()
    _selftest_hold_approve_passthrough()
    _selftest_hold_approve_gas_reread()
    _selftest_archive_restore_dry_run_gate()
    _selftest_archive_restore_pk_guard()
    _selftest_archive_restore_double_click_noop()
    _selftest_archive_restore_active_ambiguous()
    _selftest_archive_restore_write_paths()
    # member_registered_add·member_registered_remove(5·7단계 · 배1050)
    _selftest_program_canon()
    _selftest_registered_add_passthrough()
    _selftest_registered_add_reg_seq_and_period()
    _selftest_registered_add_same_date_is_idempotent()
    _selftest_registered_remove_sole_and_seq1()
    _selftest_registered_remove_needs_password()
    print("자체점검 통과")
