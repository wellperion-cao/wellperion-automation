# -*- coding: utf-8 -*-
"""인사(CHRO) 시트 → hr 스키마 적재 (인사 데이터 AWS 이관 1단계 · 2026-09-05 CHRO/A-5).

원천 = 현행 인사 백엔드(Apps Script /exec)의 읽기 계약 `{db:"<열쇠>"}` → `{ok, results:[...]}`.
대상 = common/schema.sql 의 hr 스키마. 읽기 라우트 = api_hr.py.
시트·GAS 는 절대 쓰지 않는다(읽기 단방향). 이 단계에서 정본은 여전히 시트다(회신 §2 ①읽기 미러).

  python3 migrate_hr.py                 ← 기본값 = --dry-run. DB 에 한 글자도 쓰지 않는다(CTO 명시).
  python3 migrate_hr.py --apply         실제 적재(+ 확정 가능한 FK 연결 + 전수 대조 검증)
  python3 migrate_hr.py --verify        적재 없이 DB↔시트 전수 대조만
  python3 migrate_hr.py --tab appl      한 탭만 (여러 번 줄 수 있다)
  python3 migrate_hr.py --report x.json 리포트를 파일로 (개인정보 원문 없음)
  python3 migrate_hr.py --selftest      DB·네트워크 없이 변환기·매핑표·스키마 대조만
  python3 migrate_hr.py --apply --allow-masked-source   원천이 마스킹본이어도 적재(기본은 거절)

── 이 스크립트가 지키는 것 ────────────────────────────────────────────────────────────────────
1) --dry-run 이 기본. --apply 없이는 어떤 표에도 INSERT/UPDATE 를 하지 않는다(진행 기록 표도 안 건드린다).
2) 멱등. 적재는 탭마다 정해진 '적재 열쇠'(TABS 의 conflict)로 upsert 한다 — 몇 번 돌려도 결과가 같다.
   8탭은 (tenant_id, legacy_tab, legacy_row) · 휴무만 (tenant_id, person_name_raw, work_date).
   ★열쇠는 대상 표에 실제로 선언된 유일 제약과 정확히 같아야 한다. 다르면 '해당 제약 없음' 오류가 나고
     그 탭 트랜잭션이 통째로 롤백된다 — --selftest 가 schema.sql 본문을 읽어 그 일치를 먼저 검사한다(DB 없이).
3) 전수 대조 검증(함정노트 #48). 적재 뒤 DB 를 다시 읽어 ①건수 ②열쇠 집합 ③칸 값을 원천과 전부 맞춰 본다.
   재현율이 기준선(기본 99.5퍼센트 · 사내 실적 99.50~99.88)에 못 미치면 실패로 끝낸다.
   ★대조 색인은 행번호가 아니라 '그 탭의 적재 열쇠'로 잡는다(휴무 = 성명·날짜). 행번호로 잡으면 같은
     legacy_row 두 행이 하나로 뭉개져, 원천에서 사라진 행이 미러에 살아 있어도 잉여 판정에 안 걸린다.
     적재는 upsert 전용(삭제 없음)이라 원천에서 사라진 짝은 계속 남는다 — 지우지는 않되 반드시 보고한다.
4) 부분 적재 상태로 조용히 끝나지 않는다. --apply 는 hr.migration_run/step 에 진행을 남기고,
   중간에 죽으면 run 이 'failed' 로 닫히며(닫지도 못하면 'running' 으로 남아 api_hr /health 의 stale_run 이 켜진다)
   종료 코드가 0 이 아니고 마지막 줄에 어디까지 갔는지 찍는다. 탭 하나는 한 트랜잭션 — 반쪽 탭은 남지 않는다.
5) ⛔ 오류·리포트에 개인정보 원문을 찍지 않는다(함정노트 #43 실사고). 남기는 것은 칸 이름 · 시트 행번호 · 건수뿐이고,
   사람 이름이 꼭 필요한 자리는 마스킹(첫 글자 + O)한다. 원문 값 histogram 은 개인정보가 아닌 칸만.
6) ⛔ 주민번호는 읽지도 적재하지도 않는다 — 현행 '퇴사자 명부' 시트에 열이 있으나 목적 없는 고유식별정보라
   이관 대상에서 뺐다(진단 D-1). DROP_FIELDS 가 원본 보관(data JSONB)에서도 지운다.
7) 칸 이름을 지어내지 않는다. 목표 칸마다 '후보 이름 목록'을 두고 실제 응답에 있는 이름만 쓴다.
   못 맞춘 목표 칸과 못 쓴 원천 칸은 리포트에 그대로 올라온다 — 사람이 보고 후보 목록을 고친 뒤 --apply 한다.
   ★어느 경우에도 원본 레코드 통째가 data JSONB 에 남으므로 매핑을 못 맞춰도 사실은 유실되지 않는다.
8) 테스트/더미 행은 쓰기 관문과 같은 판정(common/db.py is_test_payload)으로 is_test=TRUE 표시만 하고 버리지 않는다.
   ★그 판정기가 보는 칸 이름은 전부 영문이라, 한글 칸인 인사 원천은 투영(TEST_PROBE)을 거쳐 넘긴다 —
     새 판정 함수를 만들지 않는다(회신 §3). 투영을 안 하면 어느 칸도 검사되지 않아 인사 더미가 전혀 안 잡힌다.
9) 원천이 '마스킹본'이면 적용을 거절한다. 적재에 뷰어용 열쇠를 쓰면 가려진 값이 서버 정본으로 굳는데,
   되돌리기가 사실상 재적재라 코드에서 먼저 막는다(--allow-masked-source 를 명시할 때만 진행).
   ★'표본을 하나도 못 봤다'와 '원문이다'를 구분한다 — 탐지 칸이 매핑되지 않는 탭만 돌리면(예: --tab leave)
     판정 근거가 0 이다. 그때는 원천 종류를 '미확인'으로 두고 적용도 같이 막는다. 근거 0 을 '원문'으로
     단정하면 실행 기록(hr.migration_run.note)과 리포트에 사실과 다른 '원천=원문'이 박히고, 하필
     퇴사처리의 면담 내용·인사평가의 피드백은 현행 GAS 가 뷰어에게 패턴 치환해 주는 자유 텍스트라
     가려진 본문이 그대로 서버 정본이 되는 비가역 사고 경로가 열린다.

── 이번 범위 밖(일부러 안 한 것) ──────────────────────────────────────────────────────────────
· hr.person 생성·동일인 병합: (이름+생년월일) 일치도 '후보'일 뿐 최종 확인은 사람 몫이고(동명이인 4쌍 실재),
  자동 병합은 연차·평가·급여를 남의 것과 섞는다. 그래서 1단계는 person_id 를 NULL 로 두고 *_name_raw 만 채운다.
· 지원자 memo 분해(hr.applicant_document): 분해 규칙의 재현율을 아직 실증하지 않았다(#48).
· 미적재 7탭(자동화로그·명령큐·근무변경신청·연차원장·보드명단·공휴일·개인일정) = 아래 OUT_OF_SCOPE 상수가 정본.
  hr 스키마는 21표인데 이 스크립트가 적재하는 것은 9탭뿐이다 — '표가 있으니 적재됐겠지'로 읽히지 않게
  사유와 함께 코드에 박아 두고, 실행 머리말과 리포트 JSON 에 '이번 범위 밖'으로 그대로 찍는다.
"""
import argparse
import datetime
import decimal
import json
import os
import re
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # 저장소 server/ = 서버 /srv/erp/
from common import db  # noqa: E402  — DB 를 여는 유일한 자리 · 모든 조회는 tenant_id 로 거른다

ENV_FILE = os.environ.get("ERP_API_ENV", "/srv/erp/api.env")
DEFAULT_MIN_RECALL = 99.5          # 함정노트 #48 · 사내 실적(휴무 99.50 · 원장 99.88)을 기준선으로
FETCH_TIMEOUT = 120                # db:leave 는 실측 24~52초가 나온다 — 넉넉히
FETCH_GAP_SEC = 1.5                # 연속 호출 간격(핵심규칙 9) — 이관 뒤에는 필요 없어지는 규칙이지만 지금은 지킨다
KST = datetime.timezone(datetime.timedelta(hours=9))   # 적재 시각은 오프셋을 붙여 만든다(C-04) — 아래 now_kst 참고
# ⛔ 적재에서 통째로 버리는 원천 칸 — 목적 없는 고유식별정보. data JSONB 에도 남기지 않는다.
DROP_FIELDS = ("주민번호", "주민등록번호", "주민 번호")

# ── 이번 범위 밖 = 적재하지 않는 7탭 (C-03) ────────────────────────────────────────────────────
# hr 스키마에는 표가 있으나 이 스크립트는 채우지 않는다. 사유를 세 갈래로 갈라 적는다 —
# 지어내지 않고 '미확인'은 미확인으로 남긴다(현행 백엔드의 db 읽기 열쇠는 10종인데 여기서 쓰는 것은 9종이다).
SCOPE_ACTION = "별도 액션 원천"       # `{db:...}` 읽기 계약이 아니라 다른 GAS 액션으로 읽는다
SCOPE_SIDEEFFECT = "조회 부작용"      # 조회 자체가 상태를 바꾼다
SCOPE_UNKNOWN = "원천 계약 미확인"    # db 읽기 계약인지 아직 확인되지 않았다
OUT_OF_SCOPE = [
    ("자동화로그", "hr.automation_log", SCOPE_UNKNOWN,
     "현행 db 읽기 열쇠 10종 중 이 스크립트가 쓰는 9종을 뺀 나머지 1종이 이 탭인지 다른 것인지 미확인"),
    ("명령큐", "hr.command_queue", SCOPE_SIDEEFFECT,
     "cmd-pull 이 조회만으로 상태를 delivered 로 바꾼다 — 확인 전에는 부르지 않는다"),
    ("근무변경신청", "hr.schedule_change_request", SCOPE_ACTION, "전용 액션으로 읽는다"),
    ("연차원장", "hr.leave_ledger", SCOPE_ACTION, "전용 액션으로 읽는다 · 적재 열쇠는 (성명, 연도)"),
    ("보드명단", "hr.department.board_group", SCOPE_ACTION, "전용 액션으로 읽는다"),
    ("공휴일", "hr.holiday", SCOPE_ACTION, "전용 액션으로 읽는다 · 기본키는 날짜이고 행번호 칸 자체가 없다"),
    ("개인일정", "hr.personal_calendar_event", SCOPE_ACTION, "전용 액션으로 읽는다"),
]

# ── 마스킹된 원천 판별 (C-08) ──────────────────────────────────────────────────────────────────
# 현행 백엔드는 뷰어 열쇠로 부르면 PII 를 가려서 준다. 가린 모양(실측) =
#   연락처 '010-****-5678' · 주민번호 '900101-*******' · 축약형 셀 전체 '*******'.
# 그 모양이 보이면 적용 모드를 거절한다 — 마스킹본이 서버 정본으로 굳으면 되돌리기가 사실상 재적재다.
MASKED_VALUE_RE = re.compile(r"^\d{2,4}-\*{4}-\d{4}$|\d{6}-\*{7}|^\*{7}$")
MASKED_WHOLE_RE = re.compile(r"^(?:\d{2,4}-\*{4}-\d{4}|\d{6}-\*{7}|\*{7})$")   # 셀 전체가 가린 값일 때만
MASK_PROBE_COLS = ("phone", "phone_last4")     # 연락처 계열 목표 칸 — 값 어디에 있어도 본다
# 자유 텍스트 목표 칸 — '셀 전체 일치'일 때만 마스킹으로 센다(자유 텍스트를 부분 일치로 보면 과탐이 난다).
#   ★목적이 둘이다: ①가린 값 탐지 ②'표본을 보기는 했다'는 근거 확보. 연락처 칸이 없는 탭(퇴사처리·인사평가)도
#     이 칸들 덕분에 판정 근거를 갖는다 — 근거가 0 이면 아래 run() 이 원천 종류를 '미확인'으로 둔다.
MASK_PROBE_TEXT_COLS = ("interview_note", "feedback", "memo", "note")
MASK_SAMPLE_ROWS = 200                         # 표본. 전수를 볼 이유가 없다 — 마스킹은 응답 전체에 일괄로 걸린다


# ══════════════════════════════════════════════════════════════════════════════════════════
#  값 변환기 — 시트 문자열을 DB 타입으로. 못 읽으면 조용히 None 이 아니라 '못 읽음'으로 세어 리포트에 올린다.
# ══════════════════════════════════════════════════════════════════════════════════════════
_DATE_RE = re.compile(r"^(\d{4})[-./](\d{1,2})[-./](\d{1,2})")
_TIME_RE = re.compile(r"^(\d{1,2}):(\d{2})(?::(\d{2}))?$")
_RANGE_RE = re.compile(r"^(\d{1,2}:\d{2})\s*[-~]\s*(\d{1,2}:\d{2})$")
SHIFT_LABELS = ("오픈", "마감", "쇼", "오/마")     # 진단 §1.5 에서 '근무조 라벨'로 확인된 값 — 휴무 코드가 아니다
UNDECIDED_LEAVE = ("-",)                          # 뜻 미확정(57건) — 해석 칸을 채우지 않는다(체크리스트 C-1)


def s(v):
    return "" if v is None else str(v).strip()


def to_date(v):
    t = s(v)
    if not t:
        return None
    m = _DATE_RE.match(t)
    if not m:
        return None
    try:
        return datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def to_time(v):
    m = _TIME_RE.match(s(v))
    if not m:
        return None
    try:
        return datetime.time(int(m.group(1)), int(m.group(2)), int(m.group(3) or 0))
    except ValueError:
        return None


def to_int(v):
    t = re.sub(r"[^\d-]", "", s(v))
    try:
        return int(t) if t not in ("", "-") else None
    except ValueError:
        return None


def to_num(v):
    t = re.sub(r"[^\d.-]", "", s(v))
    try:
        return float(t) if t not in ("", "-", ".") else None
    except ValueError:
        return None


def to_bool(v):
    t = s(v).lower()
    if t in ("예", "y", "yes", "true", "완료", "지급", "o", "1"):
        return True
    if t in ("아니오", "아니요", "n", "no", "false", "미지급", "x", "0"):
        return False
    return None


def to_text(v):
    return s(v) or None


def to_last4(v):
    d = re.sub(r"\D", "", s(v))
    return d[-4:] if len(d) >= 4 else None


def mask(name):
    """리포트·오류에 사람 이름이 꼭 필요할 때만 — 첫 글자 + O. 개인정보 원문은 어디에도 찍지 않는다."""
    t = s(name)
    return (t[0] + "O" * (len(t) - 1)) if t else ""


def split_leave_value(raw):
    """휴무 '값' 한 칸(코드·출근시간·근무조 라벨이 섞여 있다) → (entry_type, start, end, label).
    ★해석하지 않는다 — 확실히 아는 것만 제자리에 놓고 나머지는 NULL 로 둔다. 원문은 raw_value 에 항상 남는다.
      · 근무조 라벨(오픈·마감·쇼·오/마) = 진단에서 라벨로 확인된 값 → shift_label
      · '09:00' · '09:00-18:00' = 출근시간 → shift_start/shift_end
      · '-' = 뜻 미확정(C-1 매니저 판정 대기) → 전부 NULL
      · 그 밖의 짧은 한글 코드 = 휴무 코드 → entry_type 에 원문 그대로(표준 코드 집합으로의 매핑은 하지 않는다)"""
    t = s(raw)
    if not t or t in UNDECIDED_LEAVE:
        return None, None, None, None
    if t in SHIFT_LABELS:
        return None, None, None, t
    m = _RANGE_RE.match(t)
    if m:
        return None, to_time(m.group(1)), to_time(m.group(2)), None
    one = to_time(t)
    if one:
        return None, one, None, None
    if len(t) <= 8 and not any(c.isdigit() for c in t):
        return t, None, None, None
    return None, None, None, None


# ══════════════════════════════════════════════════════════════════════════════════════════
#  탭 정의 — (목표 칸, 원천 칸 후보들, 변환기).
#  ★후보 목록은 '실제 응답에 있는 이름만 쓴다'는 장치다. 하나도 안 맞으면 그 칸은 NULL 이고 리포트에 미해결로 올라온다.
#    시트 헤더는 바뀌므로(헤더 오염 실사례 있음) 후보를 넉넉히 두되, 맞은 이름을 리포트에 찍어 사람이 확인하게 한다.
# ══════════════════════════════════════════════════════════════════════════════════════════
EMP_MAP = [
    ("person_name_raw", ("성명", "이름"), to_text),
    ("dept_name_raw", ("부서", "소속"), to_text),
    ("roster_display_name", ("표기명", "보드명"), to_text),
    ("position", ("직급", "직책"), to_text),
    ("employment_type", ("고용 형태", "고용형태"), to_text),
    ("hire_date", ("입사일",), to_date),
    ("birth_date", ("생년월일", "bday", "생일"), to_date),
    ("phone", ("연락처", "전화번호"), to_text),
    ("email", ("이메일",), to_text),
    ("work_hours", ("근무시간",), to_text),
    ("note", ("비고",), to_text),
]
EXITROSTER_MAP = [
    ("person_name_raw", ("성명", "이름"), to_text),
    ("dept_name_raw", ("부서", "소속"), to_text),
    ("hire_date", ("입사일",), to_date),
    ("resign_date", ("퇴사일",), to_date),
    ("birth_date", ("생년월일", "생일", "bday"), to_date),
    ("phone", ("연락처", "전화번호"), to_text),
    ("note", ("비고",), to_text),
]
EXIT_MAP = [
    ("employee_name_raw", ("연결 임직원", "성명", "이름"), to_text),
    ("last_work_date", ("퇴사일", "최종 근무일", "마지막 근무일"), to_date),
    ("reason", ("퇴사 사유", "사유"), to_text),
    ("interview_note", ("면담 내용",), to_text),
    ("severance_paid", ("퇴직금 지급 여부",), to_bool),
    ("severance_date", ("퇴직금 지급일",), to_date),
    ("handled_by", ("담당자", "처리자"), to_text),
]
APPL_MAP = [
    ("applicant_name", ("지원자명", "성명", "이름"), to_text),
    ("posting_name_raw", ("연결 공고", "지원 포지션", "포지션"), to_text),
    ("stage", ("전형 단계", "단계", "전형단계"), to_text),
    ("applied_at", ("지원일", "접수일", "등록일"), to_date),
    ("source", ("지원 경로", "채널", "출처"), to_text),
    ("rating", ("면접 평점", "평점", "서류 평점"), to_num),
    ("interviewer", ("면접관",), to_text),
    ("phone", ("연락처", "전화번호"), to_text),
    ("email", ("이메일",), to_text),
    ("photo_file", ("사진",), to_text),
    ("memo", ("메모",), to_text),
]
HIRE_MAP = [
    ("title", ("포지션명", "공고명", "제목", "포지션"), to_text),
    ("dept_name_raw", ("부서", "소속"), to_text),
    ("status", ("상태", "공고 상태"), to_text),
    ("employment_type", ("고용 형태", "고용형태"), to_text),
    ("headcount", ("모집인원", "모집 인원"), to_int),
    ("start_date", ("게시일", "시작일"), to_date),
    ("end_date", ("마감일", "종료일"), to_date),
    ("channels", ("채널", "게시 채널"), to_text),
    ("owner_clevel", ("담당 C-Level", "담당 C레벨", "담당"), to_text),
    ("detail_url", ("상세 링크", "링크", "URL"), to_text),
]
EVAL_MAP = [
    ("subject_name_raw", ("대상자", "피평가자"), to_text),
    ("evaluator_name_raw", ("평가자",), to_text),
    ("title", ("평가명", "제목"), to_text),
    ("period_start", ("평가 시작일", "시작일"), to_date),
    ("period_end", ("평가 종료일", "종료일", "평가일"), to_date),
    ("total_score", ("총점",), to_num),
    ("bonus_points", ("가산점",), to_num),
    ("grade", ("평가 등급", "등급"), to_text),
    ("feedback", ("피드백", "종합 의견"), to_text),
]
ONBO_MAP = [
    ("employee_name_raw", ("대상 신입 직원", "대상자", "성명"), to_text),
    ("track", ("트랙", "구분", "유형"), to_text),
    ("week_no", ("주차",), to_int),
    ("title", ("항목", "제목", "내용"), to_text),
    ("due_date", ("예정일", "기한", "일자"), to_date),
    ("done", ("완료", "완료 여부"), to_bool),
    ("done_at", ("완료일",), to_date),
    ("owner", ("담당자",), to_text),
    ("note", ("비고",), to_text),
]
BLACKLIST_MAP = [
    ("name", ("성명", "이름"), to_text),
    ("birth_year", ("생년",), to_int),
    ("phone_last4", ("연락처", "연락처 뒤4자리"), to_last4),
    ("reason", ("사유",), to_text),
    ("registered_at", ("등록일",), to_date),
    ("registered_by", ("등록자",), to_text),
]
LEAVE_MAP = [
    ("person_name_raw", ("성명", "이름"), to_text),
    ("dept_name_raw", ("부서", "소속"), to_text),
    ("work_date", ("날짜", "일자"), to_date),
    ("raw_value", ("값", "휴무"), to_text),
]

# 적재 열쇠(conflict) = upsert 의 ON CONFLICT 대상. ★대상 표에 실제로 선언된 유일 제약과 같아야 한다(C-01).
#   8탭 = 시트 1행이 DB 1행이라 (tenant_id, legacy_tab, legacy_row).
#   휴무만 다르다 — hr.leave_entry 의 유일 제약이 (tenant_id, person_name_raw, work_date) 하나뿐이라
#   행번호 열쇠로 upsert 하면 '해당 제약 없음' 오류가 나고 그 탭이 통째로 롤백된다(적용 모드에서만 터진다).
ROW_KEY = ("tenant_id", "legacy_tab", "legacy_row")
LEAVE_KEY = ("tenant_id", "person_name_raw", "work_date")
# 원천 칸이 아니라 변환기가 만들어 내는 칸(convert 참고) — 적재 칸 목록과 스키마 대조가 같은 정본을 본다.
DERIVED = {"hr.leave_entry": ("entry_type", "shift_start", "shift_end", "shift_label")}

TABS = {
    "emp":        {"label": "현재근무자", "table": "hr.employee", "pk": "employee_id",
                   "legacy_tab": "현재근무자", "map": EMP_MAP, "fixed": {"status": "재직"},
                   "required": ("person_name_raw",), "conflict": ROW_KEY},
    "exitroster": {"label": "퇴사자 명부", "table": "hr.employee", "pk": "employee_id",
                   "legacy_tab": "퇴사자", "map": EXITROSTER_MAP, "fixed": {"status": "퇴사"},
                   "required": ("person_name_raw",), "conflict": ROW_KEY},
    "exit":       {"label": "퇴사처리", "table": "hr.resignation", "pk": "resignation_id",
                   "legacy_tab": "퇴사처리", "map": EXIT_MAP, "fixed": {},
                   "required": ("employee_name_raw",), "conflict": ROW_KEY},
    "appl":       {"label": "지원자", "table": "hr.applicant", "pk": "applicant_id",
                   "legacy_tab": "지원자", "map": APPL_MAP, "fixed": {},
                   "required": ("applicant_name",), "conflict": ROW_KEY},
    "hire":       {"label": "채용공고", "table": "hr.job_posting", "pk": "posting_id",
                   "legacy_tab": "채용공고", "map": HIRE_MAP, "fixed": {},
                   "required": ("title",), "conflict": ROW_KEY},
    "eval":       {"label": "인사평가", "table": "hr.evaluation", "pk": "eval_id",
                   "legacy_tab": "인사평가", "map": EVAL_MAP, "fixed": {},
                   "required": ("subject_name_raw",), "conflict": ROW_KEY},
    "onbo":       {"label": "입사·온보딩", "table": "hr.onboarding_item", "pk": "item_id",
                   "legacy_tab": "입사온보딩", "map": ONBO_MAP, "fixed": {},
                   "required": ("employee_name_raw",), "conflict": ROW_KEY},
    "blacklist":  {"label": "채용블랙리스트", "table": "hr.hire_blacklist", "pk": "blacklist_id",
                   "legacy_tab": "채용블랙리스트", "map": BLACKLIST_MAP, "fixed": {},
                   "required": ("name",), "conflict": ROW_KEY},
    "leave":      {"label": "휴무", "table": "hr.leave_entry", "pk": "leave_id",
                   "legacy_tab": "휴무", "map": LEAVE_MAP, "fixed": {},
                   "required": ("person_name_raw", "work_date"), "conflict": LEAVE_KEY},
}
TAB_ORDER = ["hire", "emp", "exitroster", "exit", "appl", "eval", "onbo", "blacklist", "leave"]
# 개인정보가 아닌 칸만 값 분포를 리포트에 낸다(사람이 코드 뜻을 확인해야 하는 칸).
HISTOGRAM = {"leave": "raw_value", "appl": "stage", "emp": "status", "hire": "status"}
# 건너뛴 사유 3갈래 — 요약표·리포트가 같은 이름을 쓴다(C-06). '행번호 없음'은 적을 번호가 없어 건수만 센다.
SKIP_NO_ROW, SKIP_REQUIRED, SKIP_DUP = "행번호 없음", "필수칸 없음", "중복 열쇠"
SKIP_REASONS = (SKIP_REQUIRED, SKIP_NO_ROW, SKIP_DUP)

# 공용 테스트 판정기(common/db.is_test_payload)가 보는 칸 이름 → 인사 목표 칸 (C-05).
# ★판정기 자체는 그대로 쓴다 — 여기서는 한글 칸 레코드를 판정기가 보는 이름으로 '투영'만 한다.
#   투영하지 않으면 판정기가 검사하는 칸이 하나도 없어 인사 더미가 전혀 안 잡힌다(그 반대의 오분류도 난다).
TEST_PROBE = {
    "name":    ("person_name_raw", "applicant_name", "employee_name_raw", "subject_name_raw", "name"),
    "phone":   ("phone",),
    "title":   ("title",),
    "memo":    ("memo",),
    "note":    ("note",),
    "content": ("interview_note", "feedback"),
    "reason":  ("reason",),
}


# ══════════════════════════════════════════════════════════════════════════════════════════
#  원천 읽기
# ══════════════════════════════════════════════════════════════════════════════════════════
def load_env():
    try:
        with open(ENV_FILE, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    except OSError:
        pass


def fetch(dbkey, timeout=FETCH_TIMEOUT):
    """현행 백엔드 읽기 1회 → results 배열. 실패하면 None(지어내지 않는다).
    ★HR_GAS_URL·HR_GAS_PASSWORD 는 서버 api.env 에서만 온다 — 저장소에 값을 두지 않는다(공개 저장소).
    ★POST 본문을 보내고 302 를 따라간다 = curl 의 `-L --data` 와 같은 동작(함정노트 #5). urllib 의
      기본 리다이렉트 처리가 302 를 GET 으로 바꿔 따라가므로 `-X POST` 강제와 달리 정상 동작한다."""
    url = os.environ.get("HR_GAS_URL", "")
    pw = os.environ.get("HR_GAS_PASSWORD", "")
    if not url or not pw:
        raise SystemExit("HR_GAS_URL / HR_GAS_PASSWORD 없음 — %s 를 확인(값은 저장소에 두지 않는다)" % ENV_FILE)
    body = json.dumps({"db": dbkey, "password": pw}).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "text/plain;charset=utf-8",
                                                          "User-Agent": "wellperion-erp-api"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print("[warn] db:%s 조회 실패: %s: %s" % (dbkey, type(e).__name__, str(e)[:120]))
        return None
    rows = data.get("results")
    if not isinstance(rows, list):
        print("[warn] db:%s 응답에 results 배열이 없다" % dbkey)
        return None
    for rec in rows:                      # ⛔ 주민번호 계열은 여기서 즉시 떨어뜨린다 — 메모리에도 오래 두지 않는다
        if isinstance(rec, dict):
            for f in DROP_FIELDS:
                rec.pop(f, None)
    return rows


# ══════════════════════════════════════════════════════════════════════════════════════════
#  변환
# ══════════════════════════════════════════════════════════════════════════════════════════
def source_keys(rows):
    """응답에 실제로 있는 원천 칸 이름 전체(헤더가 행마다 다른 사례가 있어 합집합으로 본다)."""
    return set().union(*[set(r) for r in rows]) if rows else set()


def resolve_map(spec, sample_keys):
    """목표 칸 → 실제 원천 칸 이름. 후보 중 응답에 있는 첫 이름만 쓴다(없으면 None = 미해결)."""
    out = {}
    for col, cands, conv in spec["map"]:
        hit = next((c for c in cands if c in sample_keys), None)
        out[col] = (hit, conv)
    return out


def src_value(resolved, rec, col):
    """목표 칸 하나의 원천 값(문자열). 매핑이 안 붙은 칸이면 ''."""
    srckey = resolved.get(col, (None, None))[0]
    return s(rec.get(srckey)) if srckey else ""


def test_probe(resolved, rec):
    """원천 레코드(한글 칸) → 공용 판정기가 보는 칸 이름만 담은 얇은 투영본 (C-05).
    ★새 판정 함수를 만들지 않는다 — 투영본을 common/db.is_test_payload 에 그대로 넘긴다.
      투영에 쓰는 원천 칸은 이미 붙여 놓은 칸 매핑(resolved) 결과를 재사용한다."""
    out = {}
    for probe, cols in TEST_PROBE.items():
        for col in cols:
            v = src_value(resolved, rec, col)
            if v:
                out[probe] = v
                break
    return out


def convert(spec, resolved, rec):
    """원천 레코드 1개 → (칸값 dict, 못 읽은 칸 목록). 개인정보 값은 반환만 하고 절대 출력하지 않는다."""
    vals, unparsed = {}, []
    for col, (srckey, conv) in resolved.items():
        if srckey is None:
            vals[col] = None
            continue
        raw = rec.get(srckey)
        v = conv(raw)
        if v is None and s(raw):
            unparsed.append(col)          # 원천에 값이 있는데 타입 변환에 실패 — 리포트에 칸 이름만 올린다
        vals[col] = v
    vals.update(spec["fixed"])
    if spec["table"] in DERIVED:
        et, st, en, lb = split_leave_value(vals.get("raw_value"))
        vals["entry_type"], vals["shift_start"], vals["shift_end"], vals["shift_label"] = et, st, en, lb
    return vals, unparsed


def sheet_row(rec):
    v = rec.get("_sheet_row")
    return v if isinstance(v, int) else to_int(v)


def conflict_value(spec, vals, lrow, col):
    """적재 열쇠 칸 하나의 값. tenant_id·legacy_tab 은 탭 안에서 상수이고 legacy_row 만 원천 행번호다."""
    if col == "tenant_id":
        return db.TENANT
    if col == "legacy_tab":
        return spec["legacy_tab"]
    if col == "legacy_row":
        return lrow
    return norm_cmp(vals.get(col))


def preflight(key, rows):
    """적재 전 훑기 — 무엇이 안 들어가는지를 적재 '전에' 정한다 (C-02·C-05·C-06).
    ★--apply 없이(미리보기)도 돌아 리포트에 그대로 올라간다 — 승인 근거가 되는 자료다.
    ⛔ 값·이름은 담지 않는다. 남기는 것은 사유 · 시트 행번호 · 건수뿐이다.

      행번호 없음 = _sheet_row 가 없어 어느 행인지 특정할 수 없다(번호를 적을 수 없어 건수만 센다)
      필수칸 없음 = 그 표의 NOT NULL 칸이 비었다
      중복 열쇠   = 원천에 적재 열쇠가 같은 행이 둘 이상이다 → 행번호가 작은 행을 남기고 뒤 행은 건너뛴다
                    (현행 set-leave 의 '첫 행만 갱신 · 중복행 보존'과 같은 방향. 조용히 덮어쓰지 않는다)"""
    spec = TABS[key]
    resolved = resolve_map(spec, source_keys(rows))
    order = sorted(range(len(rows)),
                   key=lambda i: (sheet_row(rows[i]) is None, sheet_row(rows[i]) or 0, i))
    skip_idx, skip_rows = {}, {r: [] for r in SKIP_REASONS}
    dup_kept, test_idx, test_rows, unparsed_hist, seen = {}, set(), [], {}, {}
    for i in order:
        rec = rows[i]
        lrow = sheet_row(rec)
        if lrow is None:
            skip_idx[i] = SKIP_NO_ROW
            continue
        vals, unparsed = convert(spec, resolved, rec)
        for c in unparsed:
            unparsed_hist[c] = unparsed_hist.get(c, 0) + 1
        if [c for c in spec["required"] if not vals.get(c)]:
            skip_idx[i] = SKIP_REQUIRED
            skip_rows[SKIP_REQUIRED].append(lrow)
            continue
        ckey = tuple(conflict_value(spec, vals, lrow, c) for c in spec["conflict"])
        if ckey in seen:
            skip_idx[i] = SKIP_DUP
            skip_rows[SKIP_DUP].append(lrow)
            dup_kept[str(lrow)] = seen[ckey]           # 어느 행을 남겼는지 — 행번호끼리라 개인정보가 아니다
            continue
        seen[ckey] = lrow
        if db.is_test_payload(test_probe(resolved, rec)):
            test_idx.add(i)
            test_rows.append(lrow)
    counts = {r: len(skip_rows[r]) for r in SKIP_REASONS}
    counts[SKIP_NO_ROW] = sum(1 for r in skip_idx.values() if r == SKIP_NO_ROW)
    return {"resolved": resolved, "skip_idx": skip_idx, "skip_rows": skip_rows, "skip_count": counts,
            "duplicate_kept": dup_kept, "test_idx": test_idx, "test_rows": sorted(test_rows),
            "unparsed": unparsed_hist, "loadable": len(rows) - len(skip_idx)}


def masked_source(key, rows):
    """원천 응답이 마스킹본인지 표본으로 본다 (C-08). 반환 = (판정, {칸: 건수}, 본 값 개수).
    ⛔ 값은 반환하지도 찍지도 않는다 — 칸 이름과 건수만.
    ★세 번째 반환값(seen)이 '판정 근거를 몇 개나 봤는가'다. 0 이면 '마스킹본이 아니다'가 아니라
      '알 수 없다'이다 — 부르는 쪽(run)이 그 둘을 반드시 구분해야 한다. 탐지 칸이 매핑되지 않는 탭
      (휴무·채용공고)만 돌리면 seen 이 0 이 되고, 그때 '원문'으로 단정하면 뷰어 열쇠로 받은 마스킹본이
      그대로 서버 정본이 된다(면담 내용·피드백은 현행 GAS 가 뷰어에게 패턴 치환해 주는 자유 텍스트다)."""
    resolved = resolve_map(TABS[key], source_keys(rows))
    hits, seen = {}, 0
    for rec in rows[:MASK_SAMPLE_ROWS]:
        for col in MASK_PROBE_COLS:
            v = src_value(resolved, rec, col)
            if not v:
                continue
            seen += 1
            if MASKED_VALUE_RE.search(v):
                hits[col] = hits.get(col, 0) + 1
        for col in MASK_PROBE_TEXT_COLS:
            v = src_value(resolved, rec, col)
            if not v:
                continue
            seen += 1
            if MASKED_WHOLE_RE.match(v.strip()):     # 자유 텍스트는 셀 전체 일치일 때만
                hits[col] = hits.get(col, 0) + 1
    return bool(hits), hits, seen


# ══════════════════════════════════════════════════════════════════════════════════════════
#  적재
# ══════════════════════════════════════════════════════════════════════════════════════════
def row_map_sql(spec):
    """rNN 역인덱스(hr.legacy_row_map) 적재문. 사진 파일명·자동화로그·과거 기록이 행번호로 사람을 부른다.

    ★DISTINCT ON 이 반드시 있어야 한다 (C-01 후속).
      legacy_row_map 의 기본키는 (tenant_id, legacy_tab, legacy_row) 인데, 적재 열쇠가 ROW_KEY 가 아닌 탭
      (=휴무)은 대상 표에서 그 세 칸이 '유일하지 않은' 보조 인덱스일 뿐이다(schema.sql ix_hr_leave_legacy).
      그러면 SELECT 결과에 같은 legacy_row 가 둘 나올 수 있고, PostgreSQL 이
      21000 'ON CONFLICT DO UPDATE command cannot affect row a second time' 로 끊어 그 탭 트랜잭션이
      통째로 롤백된다 — 앞선 8탭은 이미 커밋된 뒤라 C-01 이 없애려던 부분 적재 상태가 그대로 다시 생긴다.
      첫 실행은 통과하고 2회차부터 터지므로 '멱등' 계약도 같이 깨진다.
    ★중복이 생기는 경로는 가설이 아니라 상시 경로다: 현행 GAS handleSetLeave_ 는 값이 빈 문자열이면
      휴무 시트 행을 물리 삭제하고(휴무 탭은 행 고정 계약 대상이 아니다) 아래 행이 한 칸씩 올라온다.
      (성명·날짜)로 upsert 하는 휴무는 살아 있는 짝의 legacy_row 만 새 번호로 갱신하고, 사라진 짝의
      옛 행은 손대지 않은 채 옛 번호를 들고 남는다 → 두 행이 같은 legacy_row 를 갖는다.
    ★남길 한 행 = 가장 최근에 적재된 행(synced_at 내림차순 · 같으면 pk 내림차순)."""
    keycols = "tenant_id, legacy_tab, legacy_row"
    return ("INSERT INTO hr.legacy_row_map (tenant_id, legacy_tab, legacy_row, target_table, target_id)"
            " SELECT DISTINCT ON (" + keycols + ") " + keycols + ", %s, " + spec["pk"] +
            " FROM " + spec["table"] + " WHERE tenant_id=%s AND legacy_tab=%s AND legacy_row IS NOT NULL"
            " ORDER BY " + keycols + ", synced_at DESC NULLS LAST, " + spec["pk"] + " DESC"
            " ON CONFLICT (" + keycols + ")"
            " DO UPDATE SET target_table=EXCLUDED.target_table, target_id=EXCLUDED.target_id,"
            " mapped_at=now()")


def load_tab(conn, key, rows, now, pre=None):
    """탭 하나를 한 트랜잭션으로 upsert. 반환 = (적재, 테스트표시, 건너뜀{사유:행번호들}, 못읽은칸 histogram, 매핑).
    건너뛸 행·테스트 표시·중복 열쇠는 preflight 가 이미 정해 둔 것을 그대로 쓴다(같은 판정을 두 번 하지 않는다).
    한 트랜잭션이라 중간에 죽으면 그 탭은 통째로 롤백된다 — 반쪽 탭은 남지 않는다."""
    spec = TABS[key]
    pre = pre or preflight(key, rows)
    resolved = pre["resolved"]
    cols = sorted(resolved) + list(spec["fixed"]) + list(DERIVED.get(spec["table"], ()))
    cols = sorted(set(cols))
    allcols = ["tenant_id", "legacy_tab", "legacy_row", "is_test", "data", "synced_at"] + cols
    # 적재 열쇠는 탭마다 다르다(C-01) — 갱신 칸 목록 = 전체 칸 - 열쇠 칸.
    conflict = tuple(spec["conflict"])
    absent = [c for c in conflict if c not in allcols]
    if absent:
        raise RuntimeError("%s 적재 열쇠 칸이 적재 대상 칸에 없다: %s" % (key, ", ".join(absent)))
    setcols = [c for c in allcols if c not in conflict]
    sql = ("INSERT INTO %s (%s) VALUES (%s) ON CONFLICT (%s) DO UPDATE SET %s"
           % (spec["table"], ", ".join(allcols), ", ".join(["%s"] * len(allcols)), ", ".join(conflict),
              ", ".join("%s = EXCLUDED.%s" % (c, c) for c in setcols) + ", updated_at = now()"))
    batch = []
    for i, rec in enumerate(rows):
        if i in pre["skip_idx"]:
            continue
        vals, _unparsed = convert(spec, resolved, rec)
        batch.append([db.TENANT, spec["legacy_tab"], sheet_row(rec), i in pre["test_idx"],
                      json.dumps(rec, ensure_ascii=False), now] + [vals.get(c) for c in cols])
    with conn:
        conn.executemany(sql, batch)
        # rNN 역인덱스 — 같은 트랜잭션에서 채운다. legacy_row 중복은 DISTINCT ON 이 걷어낸다(row_map_sql 참고).
        conn.execute(row_map_sql(spec), (spec["table"], db.TENANT, spec["legacy_tab"]))
    return len(batch), len(pre["test_idx"]), pre["skip_rows"], pre["unparsed"], resolved


# 확정적으로만 잇는다 — 이름이 정확히 같고 후보가 딱 하나일 때만. 애매하면 NULL 로 두고 건수만 보고한다.
LINKS = [
    ("hr.employee", "dept_id", "dept_name_raw", "hr.department", "dept_id", "name", "부서"),
    ("hr.leave_entry", "employee_id", "person_name_raw", "hr.employee", "employee_id", "person_name_raw", "휴무→직원"),
    ("hr.resignation", "employee_id", "employee_name_raw", "hr.employee", "employee_id", "person_name_raw", "퇴사처리→직원"),
    ("hr.onboarding_item", "employee_id", "employee_name_raw", "hr.employee", "employee_id", "person_name_raw", "온보딩→직원"),
    ("hr.applicant", "posting_id", "posting_name_raw", "hr.job_posting", "posting_id", "title", "지원자→공고"),
]


def link_fks(conn):
    """이름 문자열 연결 → ID 참조. ★동명이인·중복 제목이면 잇지 않는다(오연결이 데이터 오염보다 나쁘다)."""
    out = []
    for tbl, fkcol, namecol, ref, refpk, refname, label in LINKS:
        with conn:
            n = conn.execute(
                "UPDATE " + tbl + " t SET " + fkcol + " = ("
                "  SELECT MIN(x." + refpk + ") FROM " + ref + " x"
                "  WHERE x.tenant_id = t.tenant_id AND x." + refname + " = t." + namecol +
                "  HAVING COUNT(*) = 1)"                       # 후보가 둘 이상이면 NULL — 동명이인 오연결 차단
                " WHERE t.tenant_id = %s AND t." + namecol + " IS NOT NULL AND t." + fkcol + " IS NULL",
                (db.TENANT,)).rowcount                         # 이미 이어진 행은 건드리지 않는다(사람이 고친 값 보호)
            orphan = conn.execute(
                "SELECT COUNT(*) FROM " + tbl + " WHERE tenant_id=%s AND " + namecol +
                " IS NOT NULL AND " + fkcol + " IS NULL", (db.TENANT,)).fetchone()[0]
        out.append({"link": label, "scanned": n, "orphan": orphan})
    return out


def seed_departments(conn, emp_rows, resolved):
    """부서 마스터 = 현재근무자에 실제로 나온 부서 이름들. 없는 것을 지어내지 않는다.
    ⚠️ leave_applicable(연차 적용 여부)은 기본 TRUE 로 둔다 — 강습 6부서·외주는 FALSE 여야 하지만
       그 목록이 이 스크립트가 읽는 원천에 없다. 적재 뒤 사람이 지정한다(리포트에 미결로 올린다)."""
    src = resolved.get("dept_name_raw", (None, None))[0]
    names = sorted({s(r.get(src)) for r in emp_rows if s(r.get(src))}) if src else []
    with conn:
        for i, nm in enumerate(names):
            conn.execute("INSERT INTO hr.department (tenant_id, name, sort_order) VALUES (%s,%s,%s)"
                         " ON CONFLICT (tenant_id, name) DO NOTHING", (db.TENANT, nm, i))
    return names


# ══════════════════════════════════════════════════════════════════════════════════════════
#  전수 대조 검증 (함정노트 #48) — 건수 · 열쇠 · 칸 값
# ══════════════════════════════════════════════════════════════════════════════════════════
def db_conflict_value(spec, r, col):
    """DB 행에서 적재 열쇠 칸 하나의 값 — conflict_value(원천 쪽)와 같은 모양으로 정규화해 짝을 맞춘다."""
    if col == "tenant_id":
        return db.TENANT
    if col == "legacy_tab":
        return spec["legacy_tab"]
    return norm_cmp(r[col]) if col in r.keys() else None


def verify_tab(conn, key, rows):
    """DB 를 다시 읽어 원천과 맞춰 본다. 반환 = 판정 dict(개인정보 값 없음).
      건수  = 원천 행수 vs DB 행수(같은 legacy_tab)
      열쇠  = 적재 열쇠 집합이 정확히 같은가(빠진 행·없던 행)
      칸 값 = 저장된 data JSONB 가 원천 레코드와 같은가 + 정규화 칸이 변환기 결과와 같은가

    ★대조 색인은 legacy_row 가 아니라 '그 탭의 적재 열쇠'로 잡는다(휴무 = 성명·날짜).
      행번호로 잡으면 같은 legacy_row 두 행이 하나로 뭉개져 잉여(extra) 판정에 안 걸린다 —
      원천에서 사라진 휴무가 서버에 살아 있는데 전수 대조가 OK 로 끝나는 조용한 결함이 그 자리다.
      적재가 upsert 전용(삭제 없음)이라 사라진 짝은 미러에 계속 남으므로, 지우지는 않되 반드시 보고한다.
    ⛔ 열쇠 자체는 리포트에 담지 않는다(휴무 열쇠에 성명이 들어간다) — 담는 것은 그 행의 시트 행번호뿐이다."""
    spec = TABS[key]
    resolved = resolve_map(spec, source_keys(rows))
    # 원천 쪽 — preflight 와 같은 순서(행번호 오름차순)로 훑어 중복 열쇠는 '행번호가 작은 행'을 남긴다.
    src_by_key, src_key_row, unloadable = {}, {}, 0
    order = sorted(range(len(rows)), key=lambda i: (sheet_row(rows[i]) is None, sheet_row(rows[i]) or 0, i))
    for i in order:
        rec = rows[i]
        lr = sheet_row(rec)
        if lr is None:
            unloadable += 1
            continue
        vals, _u = convert(spec, resolved, rec)
        if [c for c in spec["required"] if not vals.get(c)]:
            unloadable += 1          # 애초에 적재되지 않는 행 — 대조 대상이 아니다(건수는 남긴다)
            continue
        k = tuple(conflict_value(spec, vals, lr, c) for c in spec["conflict"])
        if k in src_by_key:
            unloadable += 1          # 열쇠 중복 — 적재는 행번호가 작은 행만 넣는다(preflight 와 같은 규칙)
            continue
        src_by_key[k] = (rec, vals)      # 변환 결과를 같이 들고 간다 — 아래 칸 대조에서 다시 변환하지 않는다
        src_key_row[k] = lr
    with conn:
        got = conn.execute("SELECT * FROM " + spec["table"] + " WHERE tenant_id=%s AND legacy_tab=%s",
                           (db.TENANT, spec["legacy_tab"])).fetchall()
    db_by_key, db_key_row = {}, {}
    for r in got:
        k = tuple(db_conflict_value(spec, r, c) for c in spec["conflict"])
        db_by_key[k] = r
        db_key_row[k] = r["legacy_row"] if "legacy_row" in r.keys() else None
    missing_keys = set(src_by_key) - set(db_by_key)             # 시트엔 있는데 DB 에 없다 = 적재 누락
    extra_keys = set(db_by_key) - set(src_by_key)               # DB 엔 있는데 시트엔 없다 = 삭제 미반영·오적재
    missing = sorted(v for v in (src_key_row[k] for k in missing_keys) if v is not None)
    extra = sorted(v for v in (db_key_row[k] for k in extra_keys) if v is not None)
    matched, field_diff = 0, {}
    for k, (rec, vals) in src_by_key.items():
        r = db_by_key.get(k)
        if r is None:
            continue
        ok = True
        stored = r["data"]
        if isinstance(stored, str):
            try:
                stored = json.loads(stored)
            except (TypeError, ValueError):
                stored = None
        if stored != rec:                                        # 원본 레코드 통째 대조
            ok = False
            field_diff["_data"] = field_diff.get("_data", 0) + 1
        for col, want in vals.items():
            if col not in r.keys():
                continue
            if norm_cmp(r[col]) != norm_cmp(want):               # 정규화 칸 대조
                ok = False
                field_diff[col] = field_diff.get(col, 0) + 1
        matched += 1 if ok else 0
    total = len(src_by_key)
    recall = round(matched * 100.0 / total, 2) if total else 100.0
    # ★건수는 열쇠 집합에서 세고, 행번호 목록은 '알 수 있는 것만' 담는다(열쇠에 성명이 든 탭 보호).
    return {"tab": key, "label": spec["label"], "source_rows": len(rows), "keyed_rows": total,
            "compare_key": list(spec["conflict"]), "unloadable_rows": unloadable,
            "db_rows": len(got), "missing_rows": missing[:50], "missing_count": len(missing_keys),
            "extra_rows": extra[:50], "extra_count": len(extra_keys), "matched_rows": matched,
            "recall_pct": recall, "field_diff": field_diff}


def norm_cmp(v):
    """대조용 정규화 — Decimal/float, date/문자열 표기 차이로 가짜 불일치가 나지 않게."""
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    if isinstance(v, (datetime.date, datetime.time, datetime.datetime)):
        return v.isoformat()
    if isinstance(v, decimal.Decimal):
        return round(float(v), 4)
    if isinstance(v, float):
        return round(v, 4)
    return v


# ══════════════════════════════════════════════════════════════════════════════════════════
#  실행
# ══════════════════════════════════════════════════════════════════════════════════════════
def now_kst():
    """적재 시각 — 한국 시간에 오프셋(+09:00)까지 붙여서 만든다 (C-04).
    ★오프셋 없는 문자열을 TIMESTAMPTZ 칸에 넣으면 DB 가 '세션 시간대'로 해석한다. 서버가 UTC 면 저장값이
      9시간 앞서 기록돼 최신성 판정·3일 대조가 어긋난다. 오프셋을 명시하면 서버 시간대가 무엇이든 값이 옳다."""
    return datetime.datetime.now(KST).replace(microsecond=0).isoformat()


def print_scope():
    """이번 범위 밖 = 적재하지 않는 7탭 (C-03). '표가 있으니 적재됐겠지'로 읽히지 않게 머리말에 박아 둔다."""
    print(" 이번 범위 밖 = %d탭 (표는 있으나 이 실행이 채우지 않는다)" % len(OUT_OF_SCOPE))
    for reason in (SCOPE_ACTION, SCOPE_SIDEEFFECT, SCOPE_UNKNOWN):
        names = [t for t, _tbl, r, _n in OUT_OF_SCOPE if r == reason]
        if names:
            print("   %-14s : %s" % (reason, " · ".join(names)))


def scope_report():
    return [{"tab": t, "table": tbl, "reason": r, "note": n} for t, tbl, r, n in OUT_OF_SCOPE]


def summarize(tabs, fetched, pres, verified, loaded, failed):
    """탭별 요약 한 줄씩 (C-06). 건너뜀은 사유별로 갈라 '전건'을 행번호로 담는다 — 값·이름은 담지 않는다."""
    vmap = {v["tab"]: v for v in verified}
    empty_skip = {r: 0 for r in SKIP_REASONS}
    out = []
    for key in tabs:
        pre, rows = pres.get(key), fetched.get(key)
        out.append({
            "tab": key, "label": TABS[key]["label"], "conflict_key": list(TABS[key]["conflict"]),
            "source_rows": len(rows) if rows is not None else 0,
            "loaded_rows": loaded.get(key, 0),
            "loadable_rows": pre["loadable"] if pre else 0,
            "db_rows": vmap.get(key, {}).get("db_rows", 0),
            "test_marked": len(pre["test_idx"]) if pre else 0,
            "test_rows": pre["test_rows"] if pre else [],
            "skipped": pre["skip_count"] if pre else dict(empty_skip),
            "skipped_rows": pre["skip_rows"] if pre else {r: [] for r in SKIP_REASONS},
            "duplicate_kept": pre["duplicate_kept"] if pre else {},
            "unparsed_fields": pre["unparsed"] if pre else {},
            "failed": " / ".join(f for f in failed if f.startswith(key + " ")),
        })
    return out


def print_summary(rows_):
    """적재 요약표 (C-06) — 승인 근거가 되는 자료라 한 화면에 모은다. ⛔ 값·이름 없음(건수와 행번호만).
    '적재'는 이번 실행이 실제로 넣은 행수(미리보기면 0)이고, '가능'은 건너뜀을 뺀 나머지다."""
    print("=" * 78)
    print(" 적재 요약 — 건너뜀은 사유별 '전건'이 리포트 JSON 에 행번호로 들어간다(값·이름 없음)")
    print(" %-11s %6s %6s %6s %6s %7s %7s %7s  %s"
          % ("탭", "원천", "적재", "가능", "테스트", "필수칸", "행번호", "중복", "실패"))
    for r in rows_:
        print(" %-11s %6d %6d %6d %6d %7d %7d %7d  %s"
              % (r["tab"], r["source_rows"], r["loaded_rows"], r["loadable_rows"], r["test_marked"],
                 r["skipped"][SKIP_REQUIRED], r["skipped"][SKIP_NO_ROW], r["skipped"][SKIP_DUP],
                 r["failed"] or "-"))


def run(args):
    load_env()
    tabs = [t for t in TAB_ORDER if (not args.tab or t in args.tab)]
    unknown = [t for t in (args.tab or []) if t not in TABS]
    if unknown:
        raise SystemExit("모르는 탭: %s (가능: %s)" % (", ".join(unknown), ", ".join(TAB_ORDER)))
    apply_mode = bool(args.apply)
    mode = "apply" if apply_mode else ("verify" if args.verify else "dry-run")
    strict = apply_mode or bool(args.verify)     # 검증 미달을 실패로 볼 모드. dry-run 은 적재 전이라 제외.
    print("=" * 78)
    print(" 인사 시트 → hr 스키마 · 모드 = %s%s" % (mode, "" if apply_mode else "  (DB 에 쓰지 않는다)"))
    print(" 대상 탭 = %s  (1단계 적재 범위 = %d탭)" % (", ".join(tabs), len(TAB_ORDER)))
    print_scope()
    print("=" * 78)

    conn = db.connect() if apply_mode else db.connect(readonly=True)
    run_id, failed, last_step = None, [], "시작"
    report = {"mode": mode, "at": now_kst(), "scope_tabs": list(TAB_ORDER),
              "out_of_scope": scope_report(), "tabs": [], "summary": []}
    fetched, pres, loaded, masked_tabs, source_kind = {}, {}, {}, [], "미확인"
    probe_seen = 0                                 # 원천 종류 판정 근거를 이번 실행에서 몇 개나 봤는가(C-08)
    try:
        if apply_mode:
            db.init_schema(conn)                       # 멱등 — hr 표가 없으면 만든다
            with conn:
                run_id = conn.execute(
                    "INSERT INTO hr.migration_run (tenant_id, mode, host) VALUES (%s,%s,%s) RETURNING run_id",
                    (db.TENANT, mode, os.uname().nodename if hasattr(os, "uname") else "")).fetchone()[0]
            print("[run] run_id=%d — 이 실행이 끝나지 않으면 status 가 running 으로 남아 /api/hr/health 에 보인다" % run_id)

        emp_rows, emp_resolved = [], {}
        for i, key in enumerate(tabs):
            last_step = "fetch %s" % key
            if i:
                time.sleep(FETCH_GAP_SEC)              # 연속 호출 간격(핵심규칙 9)
            rows = fetch(key)
            if rows is None:
                failed.append("%s 조회 실패" % key)
                step_log(conn, run_id, key, "fetch", ok=False, detail={"error": "fetch-failed"})
                continue
            fetched[key] = rows
            is_masked, mask_hits, mask_seen = masked_source(key, rows)   # 마스킹본 판별(C-08)
            probe_seen += mask_seen                 # ★판정 근거 누계 — 0 이면 '원문'이 아니라 '미확인'이다
            if is_masked:
                masked_tabs.append(key)
            print("[fetch] %-11s %-8s %5d행%s"
                  % (key, TABS[key]["label"], len(rows), "  ⚠️ 마스킹본으로 보인다" if is_masked else ""))
            step_log(conn, run_id, key, "fetch", ok=True, source_rows=len(rows),
                     detail={"masked_source": is_masked, "masked_fields": mask_hits, "probed": mask_seen})

        if not fetched:
            raise RuntimeError("한 탭도 못 읽었다 — 원천 접속·열쇠를 먼저 확인")

        # ── 원천 종류 판정(C-08) ────────────────────────────────────────────────────────
        # 적재에 뷰어용 열쇠를 쓰면 가려진 값이 서버 정본으로 굳는다 — 되돌리기가 사실상 재적재라 먼저 막는다.
        # ★'표본을 하나도 못 봤다'와 '원문이다'를 구분한다 — 구분하지 않으면 --tab leave 처럼 탐지 칸이
        #   매핑되지 않는 탭만 돌렸을 때 뷰어 열쇠로 받은 마스킹본도 '원천=원문'으로 기록에 박힌다.
        last_step = "원천 종류 판정"
        source_kind = "마스킹본" if masked_tabs else ("원문" if probe_seen else "미확인")
        report["source"] = {"kind": source_kind, "masked_tabs": masked_tabs, "probed_values": probe_seen,
                            "probe_cols": list(MASK_PROBE_COLS) + list(MASK_PROBE_TEXT_COLS)}
        if masked_tabs:
            print("[source] 원천이 마스킹본으로 보인다 — 탭: %s" % ", ".join(masked_tabs))
            if apply_mode and not args.allow_masked_source:
                raise RuntimeError("마스킹본을 정본으로 적재하지 않는다 — 관리자 열쇠로 다시 받거나,"
                                   " 정말 이대로 굳힐 것이면 --allow-masked-source 를 명시한다")
        elif not probe_seen:
            print("[source] 원천 종류 = 미확인 (판정 근거 없음 — 이번 실행의 탭에 연락처·자유텍스트"
                  " 탐지 칸이 하나도 매핑되지 않았다)")
            if apply_mode and not args.allow_masked_source:
                raise RuntimeError("원천이 원문인지 마스킹본인지 확인할 근거가 없다 — 탐지 칸이 있는 탭을"
                                   " 함께 돌리거나(예: --tab emp), 근거 없이 그대로 굳힐 것이면"
                                   " --allow-masked-source 를 명시한다")
        else:
            print("[source] 원천 = 원문 (탐지 칸 표본 %d개에서 가린 모양이 안 보인다)" % probe_seen)

        # ── 적재 전 훑기 — 미리보기에서도 돈다(C-02·C-05·C-06) ──────────────────────────
        for key in tabs:
            if key not in fetched:
                continue
            last_step = "preflight %s" % key
            pres[key] = preflight(key, fetched[key])
            c = pres[key]["skip_count"]
            if c[SKIP_DUP]:
                print("[dup]   %-11s 적재 열쇠(%s) 중복 %d건 — 행번호가 작은 행을 남기고 뒤 행은 건너뛴다"
                      % (key, ", ".join(TABS[key]["conflict"]), c[SKIP_DUP]))

        if "emp" in fetched:
            emp_rows = fetched["emp"]
            emp_resolved = resolve_map(TABS["emp"], source_keys(emp_rows))

        # ── 적재 ────────────────────────────────────────────────────────────────────────
        if apply_mode:
            last_step = "부서 마스터"
            depts = seed_departments(conn, emp_rows, emp_resolved)
            print("[load]  부서 마스터 %d개%s" % (len(depts), " (연차 적용 여부는 사람이 지정해야 한다)" if depts else ""))
            report["departments"] = len(depts)
            for key in tabs:
                if key not in fetched:
                    continue
                last_step = "load %s" % key
                pre = pres[key]
                n, tests, skipped, unparsed, _res = load_tab(conn, key, fetched[key], now_kst(), pre)
                loaded[key] = n
                nskip = sum(pre["skip_count"].values())
                print("[load]  %-11s 적재 %5d · 테스트표시 %3d · 건너뜀 %3d%s"
                      % (key, n, tests, nskip, (" · 변환실패칸 " + str(unparsed)) if unparsed else ""))
                # ⛔ detail 은 개인정보 원문 금지 — 사유·행번호·건수만. 행번호 전건은 리포트 JSON 쪽에 담는다.
                step_log(conn, run_id, key, "load", ok=not nskip, source_rows=len(fetched[key]),
                         loaded_rows=n, skipped_test=tests, failed_rows=nskip,
                         detail={"skipped": pre["skip_count"], "unparsed_fields": unparsed,
                                 "duplicate_rows": skipped[SKIP_DUP][:100]})
                if nskip:
                    failed.append("%s 건너뛴 행 %d건" % (key, nskip))
            last_step = "FK 연결"
            links = link_fks(conn)
            for l in links:
                print("[link]  %-12s 고아 %d건" % (l["link"], l["orphan"]))
            report["links"] = links

        # ── 검증 ────────────────────────────────────────────────────────────────────────
        for key in tabs:
            if key not in fetched:
                continue
            last_step = "verify %s" % key
            v = verify_tab(conn, key, fetched[key])
            v["histogram"] = histogram(fetched[key], key)
            report["tabs"].append(v)
            ok = (v["missing_count"] == 0 and v["extra_count"] == 0 and v["recall_pct"] >= args.min_recall)
            # dry-run 은 아직 적재 전이라 '안 맞는 것'이 정상이다 — 판정을 FAIL 로 찍어 겁주지 않는다.
            verdict = "OK" if ok else ("미적재" if (not strict and v["db_rows"] == 0) else "FAIL")
            print("[verify]%-11s 시트 %5d · DB %5d · 누락 %3d · 잉여 %3d · 재현율 %6.2f%%  %s"
                  % (key, v["keyed_rows"], v["db_rows"], v["missing_count"], v["extra_count"],
                     v["recall_pct"], verdict))
            if v["field_diff"]:
                print("         칸별 불일치: %s" % v["field_diff"])   # 칸 이름·건수만 — 값은 찍지 않는다
            step_log(conn, run_id, key, "verify", ok=ok, source_rows=v["keyed_rows"],
                     loaded_rows=v["db_rows"], matched_rows=v["matched_rows"], recall_pct=v["recall_pct"],
                     detail={"missing": v["missing_rows"], "extra": v["extra_rows"], "field_diff": v["field_diff"]})
            if not ok and strict:
                failed.append("%s 검증 미달(누락 %d · 잉여 %d · 재현율 %.2f / 기준 %.2f)"
                              % (key, v["missing_count"], v["extra_count"], v["recall_pct"], args.min_recall))

        # ── 매핑 리포트 ─────────────────────────────────────────────────────────────────
        last_step = "매핑 리포트"
        report["mapping"] = mapping_report(fetched)
        print_mapping(report["mapping"])

    except Exception as e:                              # noqa: BLE001 — 어떤 실패든 흔적을 남기고 끝낸다
        failed.append("%s 에서 예외: %s: %s" % (last_step, type(e).__name__, str(e)[:160]))
    finally:
        status = "ok" if not failed else "failed"
        # 실행 기록 비고 = 원천이 원문이었는지 마스킹본이었는지 + 실패 사유(C-08 — 사후에 어느 쪽이었는지 대조용).
        note = "원천=%s(근거 %d)%s" % (source_kind, probe_seen,
                                     (" / " + " / ".join(failed)) if failed else "")
        if apply_mode and run_id:
            try:
                with conn:
                    conn.execute("UPDATE hr.migration_run SET finished_at=now(), status=%s, note=%s"
                                 " WHERE run_id=%s", (status, note[:900], run_id))
            except db.Error as e:
                print("[warn] run 마감 기록 실패(수동 확인 필요): %s" % str(e)[:120])
        conn.close()

    report["status"] = status
    report["failed"] = failed
    report["last_step"] = last_step
    # 요약은 실패로 끝났을 때가 오히려 더 필요하다 — try 밖에서 만든다(C-06).
    report["summary"] = summarize(tabs, fetched, pres, report["tabs"], loaded, failed)
    print_summary(report["summary"])
    if args.report:
        with open(args.report, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print("[report] %s" % args.report)

    print("=" * 78)
    if failed:
        print(" [FAILED] %s" % " / ".join(failed))
        if apply_mode:
            print(" ⚠️ 부분 적재일 수 있다 — 탭 단위로는 통째 롤백이지만, 앞선 탭은 이미 들어가 있다.")
            print("    run_id=%s 의 hr.migration_step 을 보면 어느 탭까지 갔는지 나온다. 고친 뒤 같은 명령을 다시" % run_id)
            print("    돌리면 된다(upsert 라 멱등). 되돌리려면 그 legacy_tab 행을 지우면 원상 복구된다.")
        else:
            print(" (dry-run 이라 DB 는 그대로다. 위 문제를 고친 뒤 --apply)")
        return 1
    print(" [OK] %s — 모든 탭 검증 통과" % mode)
    if not apply_mode:
        print(" DB 에 아무것도 쓰지 않았다. 실제 적재는 --apply 를 붙여야 한다.")
    return 0


def step_log(conn, run_id, tab, phase, ok=True, source_rows=0, loaded_rows=0, skipped_test=0,
             failed_rows=0, matched_rows=0, recall_pct=None, detail=None):
    """--apply 일 때만 기록(dry-run 은 DB 를 안 건드린다). ⛔ detail 에 개인정보 원문 금지 — 칸 이름·행번호·건수만."""
    if not run_id:
        return
    try:
        with conn:
            conn.execute(
                "INSERT INTO hr.migration_step (run_id, tenant_id, tab, phase, source_rows, loaded_rows,"
                " skipped_test, failed_rows, matched_rows, recall_pct, ok, detail)"
                " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (run_id, db.TENANT, tab, phase, source_rows, loaded_rows, skipped_test, failed_rows,
                 matched_rows, recall_pct, ok, json.dumps(detail or {}, ensure_ascii=False)))
    except db.Error as e:
        print("[warn] step 기록 실패: %s" % str(e)[:120])


def histogram(rows, key):
    """개인정보가 아닌 칸만 값 분포를 낸다 — 사람이 코드 뜻(휴무 '값' 202셀 등)을 확인하기 위한 자료."""
    col = HISTOGRAM.get(key)
    if not col:
        return {}
    spec = TABS[key]
    resolved = resolve_map(spec, source_keys(rows))
    srckey = resolved.get(col, (None, None))[0]
    if srckey is None:
        return {}
    h = {}
    for r in rows:
        v = s(r.get(srckey))
        h[v] = h.get(v, 0) + 1
    return dict(sorted(h.items(), key=lambda kv: -kv[1])[:40])


def mapping_report(fetched):
    """목표 칸 ↔ 원천 칸이 실제로 어떻게 붙었는지. 못 붙은 목표 칸과 안 쓴 원천 칸을 둘 다 보여 준다.
    ★칸 '이름'만 다룬다 — 값은 한 개도 싣지 않는다."""
    out = {}
    for key, rows in fetched.items():
        spec = TABS[key]
        keys = source_keys(rows)
        resolved = resolve_map(spec, keys)
        used = {v[0] for v in resolved.values() if v[0]}
        out[key] = {
            "resolved": {c: v[0] for c, v in resolved.items() if v[0]},
            "unresolved_targets": sorted(c for c, v in resolved.items() if not v[0]),
            "unused_source_fields": sorted(k for k in keys if k not in used and not k.startswith("_")),
        }
    return out


def print_mapping(rep):
    print("-" * 78)
    print(" 칸 매핑 — 못 맞춘 목표 칸은 NULL 로 들어간다(원본은 data JSONB 에 남는다)")
    for key, m in sorted(rep.items()):
        if m["unresolved_targets"]:
            print("  %-11s 미해결 목표 칸: %s" % (key, ", ".join(m["unresolved_targets"])))
        if m["unused_source_fields"]:
            print("  %-11s 안 쓴 원천 칸  : %s" % (key, ", ".join(m["unused_source_fields"])))
    print("-" * 78)


# ══════════════════════════════════════════════════════════════════════════════════════════
#  스키마 파일 대조 가드 (C-07) — DB 없이 schema.sql 본문만 읽어 탭 정의와 맞춰 본다.
#  ★휴무 열쇠 불일치는 DB 없이도 이 대조만 있었으면 잡혔을 종류였다. 미적재 7탭을 나중에 붙일 때도
#    같은 형태가 반복되므로(연차원장 = (성명, 연도) · 공휴일 = 날짜 기본키에 행번호 칸 자체가 없음)
#    가드를 먼저 두어 적재 코드를 붙이는 순간 점검이 막게 한다.
# ══════════════════════════════════════════════════════════════════════════════════════════
_CREATE_TABLE_RE = re.compile(r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([\w.]+)\s*\((.*?)\n\);",
                              re.S | re.I)
_TABLE_KEY_RE = re.compile(r"^(?:UNIQUE|PRIMARY\s+KEY)\s*\((.*?)\)", re.I)
_COLUMN_RE = re.compile(r"^([A-Za-z_]\w*)\s+\S")
_NOT_A_COLUMN = ("unique", "primary", "check", "foreign", "constraint", "exclude", "like")
# 적재가 탭마다 반드시 채우는 공통 칸 — 대상 표에 하나라도 없으면 적재문이 실행 시점에 깨진다.
SCHEMA_COMMON_COLS = ("tenant_id", "legacy_tab", "legacy_row", "is_test", "data", "synced_at")


def parse_schema(text):
    """schema.sql 본문 → {표 이름: {"columns": set, "keys": set(칸 튜플)}}.
    표 안에 선언된 UNIQUE(...) · PRIMARY KEY(...) 만 본다 — ON CONFLICT 가 잡을 수 있는 것이 그것이다."""
    out = {}
    for m in _CREATE_TABLE_RE.finditer(text):
        cols, keys = set(), set()
        for line in m.group(2).splitlines():
            line = line.split("--", 1)[0].strip().rstrip(",").strip()
            if not line:
                continue
            km = _TABLE_KEY_RE.match(line)
            if km:
                keys.add(tuple(c.strip().lower() for c in km.group(1).split(",")))
                continue
            cm = _COLUMN_RE.match(line)
            if cm and cm.group(1).lower() not in _NOT_A_COLUMN:
                cols.add(cm.group(1).lower())
        out[m.group(1).lower()] = {"columns": cols, "keys": keys}
    return out


def check_schema_contract(text):
    """탭 정의 ↔ 스키마 파일 대조. 반환 = 어긋난 것 목록(빈 목록이면 통과).
      1) 적재 열쇠가 그 표에 실제로 선언된 유일 제약과 정확히 같은가
      2) 적재가 채우는 공통 칸(원본 레코드·탭·행번호·테스트표시·동기시각)과 목표 칸이 그 표에 다 있는가"""
    tables, bad = parse_schema(text), []
    for key in TAB_ORDER:
        spec = TABS[key]
        t = tables.get(spec["table"].lower())
        if t is None:
            bad.append("%s: 스키마 파일에 %s 표가 없다" % (key, spec["table"]))
            continue
        want = tuple(c.lower() for c in spec["conflict"])
        if want not in t["keys"]:
            bad.append("%s: 적재 열쇠 (%s) 가 %s 의 유일 제약이 아니다 — 선언된 것 = %s"
                       % (key, ", ".join(spec["conflict"]), spec["table"],
                          " / ".join("(" + ", ".join(k) + ")" for k in sorted(t["keys"])) or "없음"))
        targets = [c for c, _cands, _conv in spec["map"]] + list(spec["fixed"]) \
            + list(DERIVED.get(spec["table"], ()))
        miss = [c for c in list(SCHEMA_COMMON_COLS) + targets if c.lower() not in t["columns"]]
        if miss:
            bad.append("%s: %s 에 적재가 채우는 칸이 없다: %s" % (key, spec["table"], ", ".join(sorted(set(miss)))))
    return bad


# ══════════════════════════════════════════════════════════════════════════════════════════
#  자체점검 — DB·네트워크 없이 변환기·매핑·검증 산식만
# ══════════════════════════════════════════════════════════════════════════════════════════
def selftest():
    assert to_date("2026-09-05") == datetime.date(2026, 9, 5)
    assert to_date("2026.9.5") == datetime.date(2026, 9, 5)
    assert to_date("2026-09-05T00:00:00.000Z") == datetime.date(2026, 9, 5)
    assert to_date("") is None and to_date("미정") is None and to_date("2026-13-40") is None
    assert to_time("09:00") == datetime.time(9, 0) and to_time("9:5") is None
    assert to_int("3명") == 3 and to_int("") is None and to_num("4.5점") == 4.5
    assert to_bool("예") is True and to_bool("아니오") is False and to_bool("검토중") is None
    assert to_last4("010-1234-5678") == "5678" and to_last4("123") is None
    assert mask("홍길동") == "홍OO" and mask("") == ""
    # 휴무 '값' 분해 — 확실한 것만 제자리에, 나머지는 NULL(원문은 늘 raw_value 에 남는다)
    assert split_leave_value("마감") == (None, None, None, "마감")
    assert split_leave_value("오/마") == (None, None, None, "오/마")
    assert split_leave_value("-") == (None, None, None, None), "뜻 미확정은 해석하지 않는다(C-1)"
    assert split_leave_value("") == (None, None, None, None)
    assert split_leave_value("09:00") == (None, datetime.time(9, 0), None, None)
    assert split_leave_value("09:00-18:00") == (None, datetime.time(9, 0), datetime.time(18, 0), None)
    assert split_leave_value("휴") == ("휴", None, None, None)
    assert split_leave_value("휴(7월소급)")[0] is None, "긴 자유문구는 해석하지 않는다"
    # 매핑 — 응답에 있는 이름만 쓰고, 없으면 미해결로 남는다
    res = resolve_map(TABS["emp"], {"성명", "부서", "입사일"})
    assert res["person_name_raw"][0] == "성명" and res["dept_name_raw"][0] == "부서"
    assert res["email"][0] is None, "응답에 없는 칸은 지어내지 않는다"
    vals, unparsed = convert(TABS["emp"], res, {"성명": "홍길동", "부서": "운영부", "입사일": "몰라"})
    assert vals["person_name_raw"] == "홍길동" and vals["status"] == "재직" and vals["hire_date"] is None
    assert unparsed == ["hire_date"], "값은 있는데 못 읽은 칸은 이름만 보고한다"
    # 휴무 변환 — raw_value 보존 + 분해
    lres = resolve_map(TABS["leave"], {"성명", "날짜", "값"})
    lv, _ = convert(TABS["leave"], lres, {"성명": "홍길동", "날짜": "2026-09-05", "값": "마감"})
    assert lv["raw_value"] == "마감" and lv["shift_label"] == "마감" and lv["entry_type"] is None
    assert lv["work_date"] == datetime.date(2026, 9, 5)
    # 주민번호는 응답에서 즉시 떨어진다 — fetch 의 그 부분만 떼서 확인
    rec = {"성명": "홍길동", "주민번호": "900101-1"}
    for f in DROP_FIELDS:
        rec.pop(f, None)
    assert "주민번호" not in rec, "고유식별정보는 메모리에도 남기지 않는다"
    # 탭 정의 정합
    assert set(TABS) == set(TAB_ORDER)
    for k, spec in TABS.items():
        assert spec["table"].startswith("hr.") and spec["pk"] and spec["legacy_tab"], k
        for col in spec["required"]:
            assert col in [c for c, _c2, _f in spec["map"]] or col in spec["fixed"], (k, col)
        assert spec["conflict"] and "tenant_id" in spec["conflict"], (k, "적재 열쇠는 tenant_id 를 포함한다")
    assert TAB_ORDER.index("hire") < TAB_ORDER.index("appl"), "공고를 먼저 넣어야 지원자 FK 를 이을 수 있다"
    assert TAB_ORDER.index("emp") < TAB_ORDER.index("leave"), "직원을 먼저 넣어야 휴무 FK 를 이을 수 있다"
    # 적재 열쇠 — 휴무만 (성명, 날짜)다(C-01). 행번호 열쇠로 적재하면 적용 모드에서 그 탭이 통째로 롤백된다.
    assert TABS["leave"]["conflict"] == LEAVE_KEY
    assert all(TABS[k]["conflict"] == ROW_KEY for k in TAB_ORDER if k != "leave")
    # 스키마 파일 대조(C-07) — DB 없이 schema.sql 본문만 읽는다. 이번 결함이 잡혔을 자리다.
    with open(db.SCHEMA_FILE, encoding="utf-8") as f:
        _schema_text = f.read()
    _bad = check_schema_contract(_schema_text)
    assert not _bad, "스키마 대조 실패:\n  " + "\n  ".join(_bad)
    _parsed = parse_schema(_schema_text)
    assert ("tenant_id", "person_name_raw", "work_date") in _parsed["hr.leave_entry"]["keys"]
    assert ("tenant_id", "legacy_tab", "legacy_row") not in _parsed["hr.leave_entry"]["keys"], \
        "휴무에는 행번호 유일 제약이 없다 — 이것이 열쇠를 탭별로 둔 이유다"
    # 가드가 실제로 막는지 — 열쇠를 행번호로 되돌리면 점검이 먼저 실패해야 한다
    _saved = TABS["leave"]["conflict"]
    TABS["leave"]["conflict"] = ROW_KEY
    try:
        assert check_schema_contract(_schema_text), "열쇠가 어긋났는데 가드가 통과시켰다"
    finally:
        TABS["leave"]["conflict"] = _saved
    # 이번 범위 밖 목록(C-03) — 사유는 세 갈래 중 하나여야 하고, 적재 탭과 겹치지 않는다
    assert len(OUT_OF_SCOPE) == 7 and len(TAB_ORDER) == 9
    assert all(r in (SCOPE_ACTION, SCOPE_SIDEEFFECT, SCOPE_UNKNOWN) for _t, _tb, r, _n in OUT_OF_SCOPE)
    assert [t for t, _tb, r, _n in OUT_OF_SCOPE if r == SCOPE_UNKNOWN] == ["자동화로그"]
    assert not {t for t, _tb, _r, _n in OUT_OF_SCOPE} & {TABS[k]["legacy_tab"] for k in TAB_ORDER}
    # 적재 시각(C-04) — 시간대 오프셋이 붙어 있어야 한다. 없으면 DB 가 세션 시간대로 해석해 9시간 어긋난다.
    assert now_kst().endswith("+09:00"), "TIMESTAMPTZ 칸에 넣을 문자열은 오프셋을 달고 나온다"
    assert datetime.datetime.fromisoformat(now_kst()).utcoffset() == datetime.timedelta(hours=9)
    # 테스트/더미 판정 투영(C-05) — 한글 칸 레코드를 공용 판정기가 보는 이름으로 옮긴 뒤 판정한다
    ares = resolve_map(TABS["appl"], {"지원자명", "연락처", "메모", "_sheet_row"})
    assert test_probe(ares, {"지원자명": "홍길동", "메모": "경력 3년"}) == {"name": "홍길동", "memo": "경력 3년"}
    assert db.is_test_payload(test_probe(ares, {"지원자명": "테스트", "메모": "x"})) is True
    assert db.is_test_payload({"지원자명": "테스트"}) is False, "투영 없이 넘기면 아무 칸도 검사되지 않는다"
    assert db.is_test_payload(test_probe(ares, {"지원자명": "홍길동", "연락처": "010-0000-0000"})) is False
    _probe = test_probe(ares, {"지원자명": "홍길동", "연락처": "010-1234-5678", "메모": "x"})
    assert set(_probe) <= {"name", "phone", "title", "memo", "note", "content", "reason"}
    # 마스킹된 원천 판별(C-08) — 가린 모양이 보이면 적용을 거절할 판정이 선다
    _mrows = [{"지원자명": "홍길동", "연락처": "010-****-5678", "_sheet_row": 5}]
    assert masked_source("appl", _mrows)[0] is True
    assert masked_source("appl", [{"지원자명": "홍길동", "연락처": "010-1234-5678", "_sheet_row": 5}])[0] is False
    assert masked_source("appl", [{"지원자명": "홍길동", "_sheet_row": 5}])[0] is False, "값이 없으면 판정하지 않는다"
    assert MASKED_VALUE_RE.search("900101-*******") and MASKED_VALUE_RE.search("*******")
    # ★'표본을 하나도 못 봤다'(seen=0)와 '원문이다'는 다른 결론이다 — 부르는 쪽이 그 둘을 구분해야 한다
    assert masked_source("leave", [{"성명": "홍길동", "날짜": "2026-09-05", "값": "휴", "_sheet_row": 5}]) \
        == (False, {}, 0), "탐지 칸이 없는 탭은 판정 근거가 0 이다(원문이라는 뜻이 아니다)"
    assert masked_source("appl", [{"지원자명": "홍길동", "연락처": "010-1234-5678", "_sheet_row": 5}])[2] == 1
    # 자유 텍스트 목표 칸 — 근거는 세되(seen), 마스킹 판정은 셀 전체 일치일 때만(과탐 방지)
    _erows = [{"연결 임직원": "홍길동", "면담 내용": "정상 종료 · 900101-1234567 확인", "_sheet_row": 5}]
    assert masked_source("exit", _erows) == (False, {}, 1), "연락처 칸이 없는 탭도 근거는 갖는다"
    assert masked_source("exit", [{"연결 임직원": "홍", "면담 내용": "900101-*******", "_sheet_row": 5}])[0] is True
    assert MASK_PROBE_TEXT_COLS == ("interview_note", "feedback", "memo", "note")
    # 역인덱스 적재문 — 적재 열쇠가 ROW_KEY 가 아닌 탭은 legacy_row 중복을 허용하지 않아야 한다(C-01 후속).
    #   허용하면 ON CONFLICT DO UPDATE 가 같은 행을 두 번 건드려 21000 으로 그 탭이 통째 롤백된다.
    assert [k for k in TAB_ORDER if TABS[k]["conflict"] != ROW_KEY] == ["leave"]
    for _k in TAB_ORDER:
        _rms = row_map_sql(TABS[_k])
        assert "DISTINCT ON (tenant_id, legacy_tab, legacy_row)" in _rms, _k
        assert "ORDER BY tenant_id, legacy_tab, legacy_row" in _rms, _k
        assert "ON CONFLICT (tenant_id, legacy_tab, legacy_row)" in _rms, _k
        assert _rms.count("%s") == 3, (_k, "자리표시자 3개(target_table · tenant · legacy_tab)")
    # 대조 색인 — 열쇠가 (성명, 날짜)인 탭은 DB 쪽도 그 열쇠로 잡아야 뭉개짐이 안 생긴다
    class _R(dict):                                   # DictRow 흉내 — r["col"] · r.keys()
        pass
    _leave_r = _R({"person_name_raw": "홍길동", "work_date": datetime.date(2026, 9, 5), "legacy_row": 12})
    assert db_conflict_value(TABS["leave"], _leave_r, "person_name_raw") == "홍길동"
    assert db_conflict_value(TABS["leave"], _leave_r, "work_date") == "2026-09-05"
    assert db_conflict_value(TABS["leave"], _leave_r, "tenant_id") == db.TENANT
    assert db_conflict_value(TABS["emp"], _R({"legacy_row": 7}), "legacy_tab") == TABS["emp"]["legacy_tab"]
    _lv, _ = convert(TABS["leave"], resolve_map(TABS["leave"], {"성명", "날짜", "값"}),
                     {"성명": "홍길동", "날짜": "2026-09-05", "값": "휴"})
    assert tuple(conflict_value(TABS["leave"], _lv, 12, c) for c in LEAVE_KEY) \
        == tuple(db_conflict_value(TABS["leave"], _leave_r, c) for c in LEAVE_KEY), \
        "원천 쪽 열쇠와 DB 쪽 열쇠가 같은 모양으로 정규화돼야 짝이 맞는다"
    # 전수 대조 — 원천에서 사라진 (성명·날짜) 행이 '잉여'로 잡히는가. 현행 GAS 가 휴무 시트 행을 물리 삭제해
    #   아래 행이 올라오면 두 DB 행이 같은 legacy_row 를 갖게 되는데, 행번호로 색인하면 그 둘이 하나로
    #   뭉개져 잉여 판정이 통째로 사라진다(삭제된 휴무가 서버에 살아 있는데 대조는 OK 로 끝난다).

    class _FakeConn(object):
        """DB 없이 verify_tab 만 태우기 위한 최소 흉내 — with · execute().fetchall()."""
        def __init__(self, rows):
            self._rows = rows

        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

        def execute(self, _sql, _args=None):
            return self

        def fetchall(self):
            return self._rows

    _vsrc = [{"성명": "홍길동", "날짜": "2026-09-05", "값": "휴", "_sheet_row": 11}]
    _vdb = [_R({"person_name_raw": "홍길동", "work_date": datetime.date(2026, 9, 5), "raw_value": "휴",
                "legacy_tab": "휴무", "legacy_row": 11, "data": dict(_vsrc[0])}),
            _R({"person_name_raw": "김철수", "work_date": datetime.date(2026, 9, 5), "raw_value": "휴",
                "legacy_tab": "휴무", "legacy_row": 11, "data": None})]   # 삭제로 행이 올라와 번호가 겹친 짝
    _v = verify_tab(_FakeConn(_vdb), "leave", _vsrc)
    assert _v["extra_count"] == 1 and _v["extra_rows"] == [11], \
        "원천에서 사라진 짝이 잉여로 잡혀야 한다(행번호 색인이면 뭉개져 0 이 된다)"
    assert _v["missing_count"] == 0 and _v["matched_rows"] == 1 and _v["recall_pct"] == 100.0
    assert _v["compare_key"] == list(LEAVE_KEY)
    assert "홍길동" not in json.dumps(
        {k: _v[k] for k in ("missing_rows", "extra_rows", "field_diff", "compare_key")}, ensure_ascii=False), \
        "대조 결과에는 행번호·칸 이름만 담는다(휴무 열쇠에는 성명이 들어가므로 열쇠 자체는 안 담는다)"
    # 적재 전 훑기(C-02·C-06) — 열쇠 중복은 뒤 행을 건너뛰고, 남긴 행번호를 같이 남긴다
    _lrows = [{"성명": "홍길동", "날짜": "2026-09-05", "값": "휴", "_sheet_row": 12},
              {"성명": "홍길동", "날짜": "2026-09-05", "값": "연차", "_sheet_row": 7},
              {"성명": "김철수", "날짜": "2026-09-05", "값": "휴", "_sheet_row": 9},
              {"성명": "", "날짜": "2026-09-05", "값": "휴", "_sheet_row": 20},
              {"성명": "박영희", "날짜": "2026-09-05", "값": "휴"}]
    _pre = preflight("leave", _lrows)
    assert _pre["skip_count"] == {SKIP_REQUIRED: 1, SKIP_NO_ROW: 1, SKIP_DUP: 1}
    assert _pre["skip_rows"][SKIP_DUP] == [12] and _pre["duplicate_kept"] == {"12": 7}, \
        "행번호가 작은 행을 남기고 뒤 행을 건너뛴다"
    assert _pre["skip_rows"][SKIP_REQUIRED] == [20] and _pre["loadable"] == 2
    _blob = json.dumps(_pre["skip_rows"], ensure_ascii=False) + json.dumps(_pre["duplicate_kept"])
    assert "홍길동" not in _blob and "김철수" not in _blob, "건너뜀은 사유와 행번호만 남긴다(값·이름 금지)"
    # 행번호 열쇠 탭은 행번호가 겹칠 때만 중복으로 잡힌다 — 이름이 같아도 별개 행이다(재지원 중복행 보존)
    _arows = [{"지원자명": "홍길동", "_sheet_row": 30}, {"지원자명": "홍길동", "_sheet_row": 31}]
    assert preflight("appl", _arows)["skip_count"][SKIP_DUP] == 0
    # 대조 정규화
    assert norm_cmp(datetime.date(2026, 9, 5)) == "2026-09-05" and norm_cmp(None) is None
    assert norm_cmp(4.50001) == 4.5 and norm_cmp(True) is True
    # 매핑 리포트에 값이 안 실리는지
    rep = mapping_report({"emp": [{"성명": "홍길동", "이상한칸": "x", "_sheet_row": 5}]})
    blob = json.dumps(rep, ensure_ascii=False)
    assert "홍길동" not in blob and "이상한칸" in blob, "칸 이름만 싣는다(값 금지)"
    # 요약표(C-06) — 미리보기에서도 탭별 한 줄이 나오고, 값·이름은 안 실린다
    _sum = summarize(["leave"], {"leave": _lrows}, {"leave": _pre}, [], {}, [])
    assert len(_sum) == 1 and _sum[0]["source_rows"] == 5 and _sum[0]["loadable_rows"] == 2
    assert _sum[0]["conflict_key"] == list(LEAVE_KEY) and _sum[0]["loaded_rows"] == 0
    assert "홍길동" not in json.dumps(_sum, ensure_ascii=False), "요약에도 개인정보 원문은 없다"
    # 기본값이 dry-run 인지 — 인자 없이 파싱했을 때 apply 가 꺼져 있어야 한다
    a = build_parser().parse_args([])
    assert a.apply is False and a.min_recall == DEFAULT_MIN_RECALL
    assert a.allow_masked_source is False, "마스킹본 적재는 명시할 때만 열린다(C-08)"
    assert build_parser().parse_args(["--apply"]).apply is True
    print("selftest ok")
    return 0


def build_parser():
    p = argparse.ArgumentParser(description="인사 시트 → hr 스키마 적재 (기본 = dry-run)")
    p.add_argument("--apply", action="store_true", help="실제 적재. 없으면 DB 에 한 글자도 쓰지 않는다")
    p.add_argument("--verify", action="store_true", help="적재 없이 DB↔시트 전수 대조만")
    p.add_argument("--tab", action="append", help="한 탭만 (여러 번 가능): " + ", ".join(TAB_ORDER))
    p.add_argument("--report", help="리포트 JSON 경로(개인정보 원문 없음)")
    p.add_argument("--min-recall", type=float, default=DEFAULT_MIN_RECALL, dest="min_recall",
                   help="검증 통과 기준 재현율 (기본 %.1f)" % DEFAULT_MIN_RECALL)
    p.add_argument("--allow-masked-source", action="store_true", dest="allow_masked_source",
                   help="원천이 마스킹본이거나 원문·마스킹본을 가릴 근거가 없어도 적재"
                        "(기본은 둘 다 거절 — 마스킹본이 정본으로 굳으면 되돌리기가 재적재다)")
    p.add_argument("--selftest", action="store_true", help="DB·네트워크 없이 변환기·매핑표·스키마 대조를 점검")
    return p


if __name__ == "__main__":
    _args = build_parser().parse_args()
    sys.exit(selftest() if _args.selftest else run(_args))
