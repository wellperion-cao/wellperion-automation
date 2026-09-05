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
  python3 migrate_hr.py --selftest      DB·네트워크 없이 변환기·매핑표만

── 이 스크립트가 지키는 것 ────────────────────────────────────────────────────────────────────
1) --dry-run 이 기본. --apply 없이는 어떤 표에도 INSERT/UPDATE 를 하지 않는다(진행 기록 표도 안 건드린다).
2) 멱등. 모든 적재는 UNIQUE (tenant_id, legacy_tab, legacy_row) 로 upsert 한다 — 몇 번 돌려도 결과가 같다.
3) 전수 대조 검증(함정노트 #48). 적재 뒤 DB 를 다시 읽어 ①건수 ②열쇠 집합 ③칸 값을 원천과 전부 맞춰 본다.
   재현율이 기준선(기본 99.5퍼센트 · 사내 실적 99.50~99.88)에 못 미치면 실패로 끝낸다.
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

── 이번 범위 밖(일부러 안 한 것) ──────────────────────────────────────────────────────────────
· hr.person 생성·동일인 병합: (이름+생년월일) 일치도 '후보'일 뿐 최종 확인은 사람 몫이고(동명이인 4쌍 실재),
  자동 병합은 연차·평가·급여를 남의 것과 섞는다. 그래서 1단계는 person_id 를 NULL 로 두고 *_name_raw 만 채운다.
· 지원자 memo 분해(hr.applicant_document): 분해 규칙의 재현율을 아직 실증하지 않았다(#48).
· 공휴일·연차원장·보드명단·근무변경신청·명령큐·개인일정: `{db:...}` 계약이 아니라 다른 GAS 액션으로 읽는다.
  특히 명령큐(cmd-pull)는 조회가 상태를 delivered 로 바꾸는 쓰기성 부작용이 있어 확인 전엔 부르지 않는다.
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
# ⛔ 적재에서 통째로 버리는 원천 칸 — 목적 없는 고유식별정보. data JSONB 에도 남기지 않는다.
DROP_FIELDS = ("주민번호", "주민등록번호", "주민 번호")


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

TABS = {
    "emp":        {"label": "현재근무자", "table": "hr.employee", "pk": "employee_id",
                   "legacy_tab": "현재근무자", "map": EMP_MAP, "fixed": {"status": "재직"},
                   "required": ("person_name_raw",)},
    "exitroster": {"label": "퇴사자 명부", "table": "hr.employee", "pk": "employee_id",
                   "legacy_tab": "퇴사자", "map": EXITROSTER_MAP, "fixed": {"status": "퇴사"},
                   "required": ("person_name_raw",)},
    "exit":       {"label": "퇴사처리", "table": "hr.resignation", "pk": "resignation_id",
                   "legacy_tab": "퇴사처리", "map": EXIT_MAP, "fixed": {},
                   "required": ("employee_name_raw",)},
    "appl":       {"label": "지원자", "table": "hr.applicant", "pk": "applicant_id",
                   "legacy_tab": "지원자", "map": APPL_MAP, "fixed": {},
                   "required": ("applicant_name",)},
    "hire":       {"label": "채용공고", "table": "hr.job_posting", "pk": "posting_id",
                   "legacy_tab": "채용공고", "map": HIRE_MAP, "fixed": {},
                   "required": ("title",)},
    "eval":       {"label": "인사평가", "table": "hr.evaluation", "pk": "eval_id",
                   "legacy_tab": "인사평가", "map": EVAL_MAP, "fixed": {},
                   "required": ("subject_name_raw",)},
    "onbo":       {"label": "입사·온보딩", "table": "hr.onboarding_item", "pk": "item_id",
                   "legacy_tab": "입사온보딩", "map": ONBO_MAP, "fixed": {},
                   "required": ("employee_name_raw",)},
    "blacklist":  {"label": "채용블랙리스트", "table": "hr.hire_blacklist", "pk": "blacklist_id",
                   "legacy_tab": "채용블랙리스트", "map": BLACKLIST_MAP, "fixed": {},
                   "required": ("name",)},
    "leave":      {"label": "휴무", "table": "hr.leave_entry", "pk": "leave_id",
                   "legacy_tab": "휴무", "map": LEAVE_MAP, "fixed": {},
                   "required": ("person_name_raw", "work_date")},
}
TAB_ORDER = ["hire", "emp", "exitroster", "exit", "appl", "eval", "onbo", "blacklist", "leave"]
# 개인정보가 아닌 칸만 값 분포를 리포트에 낸다(사람이 코드 뜻을 확인해야 하는 칸).
HISTOGRAM = {"leave": "raw_value", "appl": "stage", "emp": "status", "hire": "status"}


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
def resolve_map(spec, sample_keys):
    """목표 칸 → 실제 원천 칸 이름. 후보 중 응답에 있는 첫 이름만 쓴다(없으면 None = 미해결)."""
    out = {}
    for col, cands, conv in spec["map"]:
        hit = next((c for c in cands if c in sample_keys), None)
        out[col] = (hit, conv)
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
    if spec["table"] == "hr.leave_entry":
        et, st, en, lb = split_leave_value(vals.get("raw_value"))
        vals["entry_type"], vals["shift_start"], vals["shift_end"], vals["shift_label"] = et, st, en, lb
    return vals, unparsed


def sheet_row(rec):
    v = rec.get("_sheet_row")
    return v if isinstance(v, int) else to_int(v)


# ══════════════════════════════════════════════════════════════════════════════════════════
#  적재
# ══════════════════════════════════════════════════════════════════════════════════════════
def load_tab(conn, key, rows, now):
    """탭 하나를 한 트랜잭션으로 upsert. 반환 = (적재, 테스트표시, 건너뜀, 못읽은칸 histogram).
    한 트랜잭션이라 중간에 죽으면 그 탭은 통째로 롤백된다 — 반쪽 탭은 남지 않는다."""
    spec = TABS[key]
    resolved = resolve_map(spec, set().union(*[set(r) for r in rows]) if rows else set())
    cols = sorted(resolved) + list(spec["fixed"])
    if spec["table"] == "hr.leave_entry":
        cols += ["entry_type", "shift_start", "shift_end", "shift_label"]
    cols = sorted(set(cols))
    allcols = ["tenant_id", "legacy_tab", "legacy_row", "is_test", "data", "synced_at"] + cols
    setcols = [c for c in allcols if c not in ("tenant_id", "legacy_tab", "legacy_row")]
    sql = ("INSERT INTO %s (%s) VALUES (%s) ON CONFLICT (tenant_id, legacy_tab, legacy_row) DO UPDATE SET %s"
           % (spec["table"], ", ".join(allcols), ", ".join(["%s"] * len(allcols)),
              ", ".join("%s = EXCLUDED.%s" % (c, c) for c in setcols) + ", updated_at = now()"))
    batch, tests, skipped, unparsed_hist = [], 0, [], {}
    for rec in rows:
        lrow = sheet_row(rec)
        if lrow is None:
            skipped.append("_sheet_row 없음")
            continue
        vals, unparsed = convert(spec, resolved, rec)
        for c in unparsed:
            unparsed_hist[c] = unparsed_hist.get(c, 0) + 1
        missing = [c for c in spec["required"] if not vals.get(c)]
        if missing:
            skipped.append("r%d 필수칸 없음: %s" % (lrow, ",".join(missing)))
            continue
        is_test = db.is_test_payload(rec)
        tests += 1 if is_test else 0
        batch.append([db.TENANT, spec["legacy_tab"], lrow, is_test,
                      json.dumps(rec, ensure_ascii=False), now] + [vals.get(c) for c in cols])
    with conn:
        conn.executemany(sql, batch)
        # rNN 역인덱스 — 사진 파일명·자동화로그·과거 기록이 행번호로 사람을 부른다. 같은 트랜잭션에서 채운다.
        conn.execute(
            "INSERT INTO hr.legacy_row_map (tenant_id, legacy_tab, legacy_row, target_table, target_id)"
            " SELECT tenant_id, legacy_tab, legacy_row, %s, " + spec["pk"] +
            " FROM " + spec["table"] + " WHERE tenant_id=%s AND legacy_tab=%s AND legacy_row IS NOT NULL"
            " ON CONFLICT (tenant_id, legacy_tab, legacy_row)"
            " DO UPDATE SET target_table=EXCLUDED.target_table, target_id=EXCLUDED.target_id, mapped_at=now()",
            (spec["table"], db.TENANT, spec["legacy_tab"]))
    return len(batch), tests, skipped, unparsed_hist, resolved


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
def verify_tab(conn, key, rows):
    """DB 를 다시 읽어 원천과 맞춰 본다. 반환 = 판정 dict(개인정보 값 없음).
      건수  = 원천 행수 vs DB 행수(같은 legacy_tab)
      열쇠  = legacy_row 집합이 정확히 같은가(빠진 행·없던 행)
      칸 값 = 저장된 data JSONB 가 원천 레코드와 같은가 + 정규화 칸이 변환기 결과와 같은가"""
    spec = TABS[key]
    resolved = resolve_map(spec, set().union(*[set(r) for r in rows]) if rows else set())
    src_by_row = {}
    for rec in rows:
        lr = sheet_row(rec)
        if lr is not None:
            src_by_row[lr] = rec
    with conn:
        got = conn.execute("SELECT * FROM " + spec["table"] + " WHERE tenant_id=%s AND legacy_tab=%s",
                           (db.TENANT, spec["legacy_tab"])).fetchall()
    db_by_row = {r["legacy_row"]: r for r in got}
    missing = sorted(set(src_by_row) - set(db_by_row))          # 시트엔 있는데 DB 에 없다 = 적재 누락
    extra = sorted(set(db_by_row) - set(src_by_row))            # DB 엔 있는데 시트엔 없다 = 삭제 미반영·오적재
    matched, field_diff = 0, {}
    for lr, rec in src_by_row.items():
        r = db_by_row.get(lr)
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
        vals, _ = convert(spec, resolved, rec)
        for col, want in vals.items():
            if col not in r.keys():
                continue
            if norm_cmp(r[col]) != norm_cmp(want):               # 정규화 칸 대조
                ok = False
                field_diff[col] = field_diff.get(col, 0) + 1
        matched += 1 if ok else 0
    total = len(src_by_row)
    recall = round(matched * 100.0 / total, 2) if total else 100.0
    return {"tab": key, "label": spec["label"], "source_rows": len(rows), "keyed_rows": total,
            "db_rows": len(got), "missing_rows": missing[:50], "missing_count": len(missing),
            "extra_rows": extra[:50], "extra_count": len(extra), "matched_rows": matched,
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
    return time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(time.time() + 9 * 3600))


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
    print(" 대상 탭 = %s" % ", ".join(tabs))
    print("=" * 78)

    conn = db.connect() if apply_mode else db.connect(readonly=True)
    run_id, report, failed, last_step = None, {"mode": mode, "at": now_kst(), "tabs": []}, [], "시작"
    try:
        if apply_mode:
            db.init_schema(conn)                       # 멱등 — hr 표가 없으면 만든다
            with conn:
                run_id = conn.execute(
                    "INSERT INTO hr.migration_run (tenant_id, mode, host) VALUES (%s,%s,%s) RETURNING run_id",
                    (db.TENANT, mode, os.uname().nodename if hasattr(os, "uname") else "")).fetchone()[0]
            print("[run] run_id=%d — 이 실행이 끝나지 않으면 status 가 running 으로 남아 /api/hr/health 에 보인다" % run_id)

        fetched, emp_rows, emp_resolved = {}, [], {}
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
            print("[fetch] %-11s %-8s %5d행" % (key, TABS[key]["label"], len(rows)))
            step_log(conn, run_id, key, "fetch", ok=True, source_rows=len(rows))

        if not fetched:
            raise RuntimeError("한 탭도 못 읽었다 — 원천 접속·열쇠를 먼저 확인")

        if "emp" in fetched:
            emp_rows = fetched["emp"]
            emp_resolved = resolve_map(TABS["emp"], set().union(*[set(r) for r in emp_rows]) if emp_rows else set())

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
                n, tests, skipped, unparsed, _res = load_tab(conn, key, fetched[key], now_kst())
                print("[load]  %-11s 적재 %5d · 테스트표시 %3d · 건너뜀 %3d%s"
                      % (key, n, tests, len(skipped), (" · 변환실패칸 " + str(unparsed)) if unparsed else ""))
                step_log(conn, run_id, key, "load", ok=not skipped, source_rows=len(fetched[key]),
                         loaded_rows=n, skipped_test=tests, failed_rows=len(skipped),
                         detail={"skipped": skipped[:30], "unparsed_fields": unparsed})
                if skipped:
                    failed.append("%s 건너뛴 행 %d건" % (key, len(skipped)))
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
        if apply_mode and run_id:
            try:
                with conn:
                    conn.execute("UPDATE hr.migration_run SET finished_at=now(), status=%s, note=%s"
                                 " WHERE run_id=%s", (status, " / ".join(failed)[:900] or None, run_id))
            except db.Error as e:
                print("[warn] run 마감 기록 실패(수동 확인 필요): %s" % str(e)[:120])
        conn.close()

    report["status"] = status
    report["failed"] = failed
    report["last_step"] = last_step
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
    resolved = resolve_map(spec, set().union(*[set(r) for r in rows]) if rows else set())
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
        keys = set().union(*[set(r) for r in rows]) if rows else set()
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
    assert TAB_ORDER.index("hire") < TAB_ORDER.index("appl"), "공고를 먼저 넣어야 지원자 FK 를 이을 수 있다"
    assert TAB_ORDER.index("emp") < TAB_ORDER.index("leave"), "직원을 먼저 넣어야 휴무 FK 를 이을 수 있다"
    # 대조 정규화
    assert norm_cmp(datetime.date(2026, 9, 5)) == "2026-09-05" and norm_cmp(None) is None
    assert norm_cmp(4.50001) == 4.5 and norm_cmp(True) is True
    # 매핑 리포트에 값이 안 실리는지
    rep = mapping_report({"emp": [{"성명": "홍길동", "이상한칸": "x", "_sheet_row": 5}]})
    blob = json.dumps(rep, ensure_ascii=False)
    assert "홍길동" not in blob and "이상한칸" in blob, "칸 이름만 싣는다(값 금지)"
    # 기본값이 dry-run 인지 — 인자 없이 파싱했을 때 apply 가 꺼져 있어야 한다
    a = build_parser().parse_args([])
    assert a.apply is False and a.min_recall == DEFAULT_MIN_RECALL
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
    p.add_argument("--selftest", action="store_true", help="DB·네트워크 없이 변환기·매핑표만 점검")
    return p


if __name__ == "__main__":
    _args = build_parser().parse_args()
    sys.exit(selftest() if _args.selftest else run(_args))
