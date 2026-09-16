# -*- coding: utf-8 -*-
"""중간관리자 3인 업무 목차 — GM 이 목차로 체크하는 한 장.

만드는 이유(GM 지시 2026-09-09): "실장님에게 목차 리스트를 줘서 내가 업무를 체크하는게 훨씬 효율적"
새 원장을 만들지 않는다(약속 L21) — 이미 매일 쌓이는 `_digest_ledger.json` 의 번호(no) 건을 사람별로 갈라 렌더할 뿐이다.
GM 이 화면에서 체크한 것은 그 브라우저에만 남는다(localStorage) — 원장 상태는 실무진 회신으로만 바뀐다.

화면 순서(GM 지시 2026-09-15 「최상단 책임항목 - 놓친 것 - 현재 업무」):
  · 👤 책임 항목 3인(이경연 실장·이정헌 소장·나우열M) — GM 책임 항목은 GM업무.html 띠로 옮겼다
    (같은 원장 status/manager_eval_history.json 을 읽는다 · 값 복제 없음)
  · ⚠ 놓친 것 — 종전 「먼저 볼 것」+「멈춘 것」 병합 · 기한 지난 것이 맨 위 · 사람별 · 경과 긴 순
  · 📋 현재 업무 — 사람별 블록 · 블록마다 「🖨 A3 요약본」(그 사람의 책임 항목+놓친 것+현재 업무만)
  · 📅 분기 누적 책임항목 평가 — 맨 위 오른쪽 버튼 하나 · 절은 접힌 <details id="resp-q"> 로 맨 아래
  · 체크리스트 대신 건마다 「다음 한 걸음 · 기한 · 회신 규격(#N 했다)」 한 줄 — 원장 next_step·due 칸
    (빈 값 허용 · 없으면 「다음 한 걸음 미정 — 담당이 한 줄로」) · 회신 「#N 했다」가 오면 자동 종결
    (send_ops_digest.sync_ledger_replies) · 3일째 답 없으면 07:50 통이 「N일째」로 재게재(같은 파일 build_reply_nudge_items)
  · 「최근 상황」은 40자까지만 보이고 전문은 title · 경과 14일↑ 빨강 / 7~13일 주황

갱신: python scripts/manager_task_index.py            (화면만 다시 쓴다)
      python scripts/manager_task_index.py --publish  (다시 쓰고 저장·배포까지 = regenerate_and_publish)
  · 「바로 반영」(GM 지시 2026-09-15 「#283 완료했는데 바로 반영이 안됨」) — 원장이 바뀌는 자리 셋
    (send_ops_digest --resolve · sync_ledger_replies 회신 매칭 · 07:50 통)이 모두 regenerate_and_publish() 를
    부른다 → 책임 항목 실측 스냅숏 원장 status/manager_eval_history.json 이번 달 키도 그때마다 갱신.

업무 SSOT 와 안 겹치게(나우열M 지적 2026-09-10 "직원들은 SSOT 와 너가 준 페이지 두 개를
중복으로 확인하는 비효율적인 상황"): 렌더 때마다 업무 SSOT(GAS todo_list)를 읽어 제목이
닮은 건은 사람별 표에서 빼고 맨 아래 접힘 목록("업무 SSOT 로 넘어간 것")으로 옮긴다.
SSOT 조회가 실패하면 대조 없이 종전대로 렌더하고 화면에 실패를 적는다.
"""
from __future__ import annotations

import argparse
import calendar
import difflib
import html
import json
import os
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent.parent
# 원장은 방마다 한 벌씩 있다. 이 화면이 보여 주는 세 사람(실장·소장·나우열M)에게 실제로
# 통이 나가는 곳은 ★중간관리자 방이고, 07:50 아침 통(send_ops_digest.MGR_LEDGER)도 그 원장을
# 읽는다. 그런데 이 화면만 ★운영부 원장을 읽고 있어 두 목록이 어긋났다 — 2026-09-10 실측:
# ★중간관리자 10:36 갱신·번호 230까지 / ★운영부 07:34 갱신·번호 226까지. GM 결재 3건을
# ★중간관리자에 등록했더니 이 화면에만 안 떴다. 보내는 곳과 보는 곳을 같은 원장으로 맞춘다.
LEDGER = ROOT / "1. AI자료_아카이브" / "11_카카오톡" / "★중간관리자" / "_digest_ledger.json"
OUT = ROOT / "3. 웰페리온 가이드" / "coo" / "chairman" / "중간관리자_업무목차.html"

MANAGERS = [("이경연 실장", "운영부", "★중간관리자 방"),
            ("이정헌 소장", "시설부", "★중간관리자 방"),
            ("나우열M", "인사·파트너", "텔레그램 업무관리 방")]
DONE = {"resolved", "done", "closed", "완료", "취소", "삭제"}
CAT = {"1": "매출·영업", "2": "인사", "3": "파트너팀", "4": "운영 정책", "5": "시설·환경",
       "6": "회원·CS", "7": "IT·자동화", "8": "교육·조직문화", "9": "회의"}

# 담당 미정 건을 성격으로 가르는 기준 — 원장의 category 가 먼저, 없거나 안 맞으면 제목·상황의 낱말로.
GROUPS = [
    ("안전·시설", {"시설·환경", "시설 및 환경"},
     ("안전", "소방", "미끄러", "사우나", "수리", "고장", "청소", "설치", "공조", "칠러",
      "정비", "주차", "시설", "환경", "타석", "청정기", "점검", "휴관")),
    ("회원·응대", {"회원·CS"},
     ("회원", "컴플레인", "분실", "환불", "문의", "안내", "접수", "응대", "공지", "강습")),
    ("매출·영업", {"매출·영업"},
     ("매출", "LOSS", "요금", "견적", "결제", "영업", "선물세트", "쿠팡", "보고서")),
    ("시스템·IT", {"IT·자동화", "IT·시스템·자동화"},
     ("서버", "ERP", "AWS", "자동", "시스템", "PC", "화면", "링크", "로그인", "데이터")),
]
# 「먼저 볼 것」에 붙는 성격 딱지 — 왜 급한지 한 낱말로 보인다.
FLAGS = [("안전", ("안전", "소방", "미끄러", "화재", "사고")),
         ("법정·규정", ("법", "변호사", "규정", "계약", "노동", "점검 의무")),
         ("회원", ("회원", "컴플레인", "환불", "분실", "고객"))]


def latest_by_no() -> dict[int, tuple[str, dict]]:
    """번호마다 가장 최근 기록 하나만 남긴다 — 같은 건이 날짜마다 다시 실리기 때문."""
    rows = json.loads(LEDGER.read_text(encoding="utf-8"))
    seen: dict[int, tuple[str, dict]] = {}
    for e in rows:
        for it in e.get("issues") or []:
            n = it.get("no")
            if n is None:
                continue
            d = str(e.get("date") or "")
            if n not in seen or d >= seen[n][0]:
                seen[n] = (d, it)
    return seen


def first_seen_by_no() -> dict[int, str]:
    """번호마다 원장에 처음 실린 날짜 — 「이번 주 새로 뜬 것」을 가리는 데 쓴다."""
    rows = json.loads(LEDGER.read_text(encoding="utf-8"))
    first: dict[int, str] = {}
    for e in rows:
        for it in e.get("issues") or []:
            n = it.get("no")
            if n is None:
                continue
            d = str(e.get("date") or "")
            if n not in first or d < first[n]:
                first[n] = d
    return first


def days_since(d: str) -> int:
    try:
        return (date.today() - datetime.strptime(d[:10], "%Y-%m-%d").date()).days
    except Exception:
        return 0


def fetch_ssot_rows() -> list | None:
    """업무 SSOT(GAS todo_list) 전체 행 — 이 목차와 겹치는 건을 가려낼 때만 쓴다(읽기 전용).
    gmkey 없이 부르면 GM 행이 통째로 빠진다(2026-09-07 실측) — 반드시 넣는다.
    조회 실패(느림·타임아웃)면 None — 호출부가 '대조 없이 종전대로'로 처리한다."""
    try:
        from collectors.ops_shared import SSOT_API_URL, gas_get
    except Exception:
        return None
    resp = gas_get(SSOT_API_URL, params={"action": "todo_list", "include_gm": "1", "gmkey": "1531"},
                    timeout=90, label="manager_task_index")
    if resp is None:
        return None
    try:
        data = resp.json()
        rows = data.get("data") or data.get("rows") or []
        return rows if isinstance(rows, list) else None
    except Exception:
        return None


# ═══ 👤 책임 항목 4인(GM 지시 2026-09-14) ═══════════════════════════════════
#   김남욱 GM·이경연 실장·이정헌 소장·나우열M — 항목마다 기준(고정 문구)·이번 달 실측·
#   잘한 것/보완할 것(status/manager_eval.json, 사람이 고침). 못 재는 값은 지어내지 않고
#   미수집 그대로 적는다. 진척이 기준에 못 미치면 그 값만 빨갛게(rp.bad).
EVAL_PATH = ROOT / "status" / "manager_eval.json"
# 책임 항목 실측 스냅숏 원장(GM 지시 2026-09-15 「평가체계를 가지고 계속 자동으로 · 분기 단위로 누적」) —
#   렌더 때마다 이번 달 키만 덮어쓰고 다른 달은 그대로 둔다. GM업무 「리더 현황」띠도 이 파일을 읽는다.
HIST_PATH = ROOT / "status" / "manager_eval_history.json"
RESP_PEOPLE = ["김남욱 GM", "이경연 실장", "이정헌 소장", "나우열M"]   # 원장(manager_eval_history) 키 — 4인 그대로
# 이 화면에 그리는 사람 = 3인(GM 지시 2026-09-15 「책임항목 4인에서 GM 빼고 3인으로」). GM 은 원장에만
#   남고 GM업무.html 「👤 GM 책임 항목」 띠가 같은 원장을 읽어 그린다 — 값을 두 곳에 두지 않는다.
MGR_PEOPLE = [m[0] for m in MANAGERS]
_NO_MEASURE = "미수집"

# ═══ --backfill 지난 달 소급 실측(GM 지시 2026-09-16) ═══════════════════════════════
# PERIOD 가 있으면 측정fn 들이 "오늘" 대신 그 달 말일을 기준으로 잰다 — 날짜(생성일·완료일·회신일·
# 카드가 속한 달)로 거를 수 있는 값만 이렇게 다시 잰다. 지금 상태만 있는 값(라이브 조회·현재 필드)은
# _period_no_history() 로 "당시 값 없음"을 적는다 — 지어내지 않는다.
PERIOD: "date | None" = None


def _today() -> date:
    return PERIOD or date.today()


def _period_ym() -> str:
    return _today().strftime("%Y-%m")


def _period_no_history(reason: str) -> "tuple[str, bool] | None":
    """PERIOD(과거 달) 소급 중일 때만 '당시 값 없음'을 돌려준다 — None 이면 호출부가 평소대로 잰다."""
    if PERIOD is None:
        return None
    # 칸 한 줄로(GM 지적 2026-09-16 「칸 축소·밸런스」) — 이유는 첫 구절만.
    short = re.split(r"[(—·]", str(reason or ""), 1)[0].strip()
    return f"당시 원장 없음" + (f" · {short}" if short else ""), False


SSOT_DONE = {"완료", "폐기", "완료됨"}
OPS_DEPT_STAFF = ["이경연 실장", "최준용M", "임정은M", "윤병현AM", "백승화 사원", "진수아 사원"]
# GM 확정 2026-09-16 「운영부 직원이 실장 포함 6명」 — 이지영 사원은 9월 일용근무 전환이라 정원 밖(행이 있으면 세긴 한다).
DAILY_CAP_PER_PERSON = 3   # 하루 1인당 최대 3건 등록·완료(GM 2026-09-16) — 목표가 아니라 상한
# 중간관리자 목차 개편(GM 지시 2026-09-14 "실장이 운영부 담당자들 업무들까지 체크해야") —
#   실장·소장 라인 밑에 팀원 담당 건을 묶어 넣는다. 본인(실장·소장) 이름은 뺀다.
OPS_TEAM = [s for s in OPS_DEPT_STAFF if s != "이경연 실장"]
# 종합접수처·점검 내역 「전달 대상」 기본값(GM 지시 2026-09-14) — 처리 담당(자)이 비어 있을 때만 쓴다.
DEPT_DEFAULT_HANDLER = {"운영부": "이경연 실장", "지원부": "이연희 반장",
                        "시설부": "이정헌 소장", "P.T팀": "팀장"}
FACILITY_TEAM = ["김종현 차장", "박호균 과장", "양상규 고문"]  # 시설부·주차 — 지원부 인원이 생기면 여기 추가


def load_eval() -> dict:
    try:
        return json.loads(EVAL_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def eval_cell(ev: dict, person: str, item: str) -> tuple[str, str]:
    row = (ev.get(person) or {}).get(item) or {}
    return (str(row.get("good") or "").strip() or "—", str(row.get("fix") or "").strip() or "—")


def _norm(s) -> str:
    return re.sub(r"\s+", "", str(s or ""))


def _parse_ymd(s) -> "date | None":
    try:
        return datetime.strptime(str(s)[:10], "%Y-%m-%d").date()
    except Exception:
        return None


def load_month_objectives() -> list:
    """월간운영계획 이번 달 카드(status/monthly_ops_plan.json). 조회 실패면 빈 목록."""
    try:
        d = json.loads((ROOT / "status" / "monthly_ops_plan.json").read_text(encoding="utf-8"))
        return d["months"][_period_ym()].get("objectives") or []
    except Exception:
        return []


def load_sales_target(bucket: str) -> "int | None":
    """부서 매출목표 정본 = status/sales_targets.json teams(GM 결재 2026-07-03·재확정 2026-08-24).
    member=멤버십 회원권+옵션(팀 key membership) · lessons=파트너팀 전체(멤버십 제외 전 팀 합, GXE·뮤지컬 포함).
    monthly_ops_plan.json 의 부서 metric.target 은 미연결(null)이라 여기서 안 쓴다 — 등록 안 됐으면
    None(지어내지 않는다 · GM 지시 2026-09-14)."""
    try:
        d = json.loads((ROOT / "status" / "sales_targets.json").read_text(encoding="utf-8"))
        teams = {t.get("key"): t.get("target") for t in d.get("teams") or []}
        if bucket == "member":
            v = teams.get("membership")
            return int(v) if isinstance(v, (int, float)) else None
        if bucket == "lessons":
            others = [v for k, v in teams.items() if k != "membership" and isinstance(v, (int, float))]
            return int(sum(others)) if others else None
        return None
    except Exception:
        return None


def _obj_filter(objs: list, owner: str = "") -> list:
    return [o for o in objs if _norm(o.get("owner")) == _norm(owner)]


def _checkbox_tally(objs: list) -> tuple[int, int]:
    """카드 progress_note 안 ☑(끝)·□(안 끝) 체크박스 합계."""
    done = sum(str(o.get("progress_note") or "").count("☑") for o in objs)
    todo = sum(str(o.get("progress_note") or "").count("□") for o in objs)
    return done, done + todo


def _overdue_objs(objs: list) -> int:
    today = _today()
    return sum(1 for o in objs
               if (due := _parse_ymd(o.get("due"))) and due < today and str(o.get("status") or "") != "완료")


def objective_progress_cell(objs: list) -> tuple[str, bool]:
    if not objs:
        return f"{_NO_MEASURE}(해당 카드 없음)", False
    done, total = _checkbox_tally(objs)
    over = _overdue_objs(objs)
    ck = f"체크 {done}/{total}({round(done / total * 100) if total else 0}%)" if total else "체크 항목 없음"
    return f"카드 {len(objs)}건 · {ck} · 기한 지난 것 {over}건", over > 0


def ledger_reply_cell(seen: dict, owner: str) -> tuple[str, bool]:
    """확인요청 원장(latest_by_no)에서 사람별 회신율 — 닫힌 건/보낸 건 · 최장경과 · 35일↑.
    소급 달(PERIOD)이면 「그 달에 물은 건」만 세고, 닫힘은 지금 상태로 본다(물은 날짜는 원장에 있다)."""
    mine = [(n, d, it) for n, (d, it) in seen.items() if str(it.get("owner") or "").strip() == owner]
    if PERIOD is not None:
        ym = _period_ym()
        mine = [(n, d, it) for n, d, it in mine if str(d)[:7] == ym]
        if not mine:
            return "그 달 물은 건 없음", False
        closed = sum(1 for _n, _d, it in mine if str(it.get("status", "")).lower() in DONE)
        rate = round(closed / len(mine) * 100)
        return f"그 달 물은 {len(mine)}건 · 답 온 {closed}건({rate}%)", rate < 50
    if not mine:
        return f"{_NO_MEASURE}(배정 건 없음)", False
    closed = sum(1 for _n, _d, it in mine if str(it.get("status", "")).lower() in DONE)
    opens = [(n, d, it) for n, d, it in mine if str(it.get("status", "")).lower() not in DONE]
    over35 = sum(1 for _n, d, _it in opens if days_since(d) >= 35)
    max_age = max((days_since(d) for _n, d, _it in opens), default=0)
    rate = round(closed / len(mine) * 100) if mine else 0
    text = f"회신율 {closed}/{len(mine)}({rate}%) · 최장경과 {max_age}일 · 35일↑ {over35}건"
    return text, over35 > 0


def ledger_reply_cell_all(seen: dict, owners: list) -> tuple[str, bool]:
    """세 중간관리자 합산 — GM '중간관리자 회신 짝' 행용."""
    mine = [(n, d, it) for n, (d, it) in seen.items() if str(it.get("owner") or "").strip() in owners]
    if not mine:
        return f"{_NO_MEASURE}(배정 건 없음)", False
    closed = sum(1 for _n, _d, it in mine if str(it.get("status", "")).lower() in DONE)
    opens = [(n, d, it) for n, d, it in mine if str(it.get("status", "")).lower() not in DONE]
    over35 = sum(1 for _n, d, _it in opens if days_since(d) >= 35)
    rate = round(closed / len(mine) * 100) if mine else 0
    return f"회신율 {closed}/{len(mine)}({rate}%) · 35일↑ {over35}건 · 대상 {len(mine)}건", over35 > 0


def reception_dept_cell(dept: str) -> tuple[str, bool]:
    """종합접수처 부서별 열린·7일↑·담당 미배정 — 건별 목록①과 같은 필터(분실물 제외)로 센다
    (GM 지적 2026-09-14 — 목록은 5건인데 칸은 27건으로 분실물이 섞여 있었다).
    1영업일 첫처리는 첫처리 시각 필드가 없어 잴 수 없다(지어내지 않는다·기준 칸에만 남긴다)."""
    if (nh := _period_no_history("종합접수처는 지금 열린 건만 조회됨(과거 스냅숏 없음)")) is not None:
        return nh
    from collectors.ops_shared import reception_elapsed_days
    rest, lost = reception_dept_detail(dept)
    if rest is None:
        return f"{_NO_MEASURE}(접수처 조회 실패)", False
    now = datetime.now()
    stale = sum(1 for r in rest if reception_elapsed_days(r, now) >= 7)
    unassigned = sum(1 for r in rest if _reception_handler(r) == "미배정")
    text = f"열린 {len(rest)}건 · 7일↑ {stale}건 · 담당 미배정 {unassigned}건({dept})"
    if lost:
        text += f" · 분실물 보관 {len(lost)}건 별도"
    return text, stale > 0


def facility_check_cell() -> tuple[str, bool]:
    """시설 점검 이행 — 오늘 회차 입력 수·기준이탈 건(support_check_summary 실측)."""
    if (nh := _period_no_history("점검판은 당일 조회만")) is not None:
        return nh
    try:
        import support_check_summary as scs
        lines, filled = scs.build_facility_section(_today().isoformat())
    except Exception:
        return f"{_NO_MEASURE}(점검판 조회 실패)", False
    if not filled.get("facility_status"):
        return f"{_NO_MEASURE}(오늘 점검 입력 없음)", False
    m = re.search(r"현황\s*(\d+)회차", lines[0])
    sessions = m.group(1) if m else "?"
    oor = filled.get("facility_outofrange", 0)
    return f"오늘 {sessions}회차 입력 · 기준이탈 {oor}건(당일)", oor > 0


def facility_schedule_cell() -> tuple[str, bool]:
    """전사일정 시설부 — 이번 달 완료(last_done)·현재 기한초과(next_due) 건수."""
    try:
        d = json.loads((ROOT / "status" / "schedule_ssot.json").read_text(encoding="utf-8"))
    except Exception:
        return f"{_NO_MEASURE}(전사일정 원장 조회 실패)", False
    items = [it for it in d.get("items") or [] if it.get("dept") == "시설부"]
    mp = _period_ym()
    today = _today()
    done_month = sum(1 for it in items if str(it.get("last_done") or "").startswith(mp))
    if PERIOD is not None:
        # last_done(완료 이력)은 실제 날짜라 그 달 값을 잴 수 있다 — next_due(기한)는 지금 상태만
        # 보관해 당시 값이 아니다(지어내지 않는다).
        return (f"그 달 완료 {done_month}건(전체 시설부 {len(items)}건) · "
                f"기한초과=당시 값 없음(원장은 현재 상태만 보관)"), False
    overdue = sum(1 for it in items if (due := _parse_ymd(it.get("next_due"))) and due < today)
    text = (f"이번 달 완료 {done_month}건 · 현재 기한초과 {overdue}건"
            f"(전체 시설부 {len(items)}건 · 원장 {d.get('updated_at', '?')} 기준)")
    return text, overdue > 0


def manual_count_cell() -> tuple[str, bool]:
    return f"{_NO_MEASURE}(체계 페이지가 매뉴얼 카드를 JS로 그려 정적으로 못 셈 — 소장 회신 대기)", False


def ssot_pending_cell(rows: "list | None") -> tuple[str, bool]:
    """GM 결재 처리 — 결재요청은 있고 결재상태가 결재완료가 아닌 전체 행."""
    if rows is None:
        return f"{_NO_MEASURE}(업무 SSOT 조회 실패)", False
    pend = [r for r in rows if str(r.get("결재요청") or "").strip() and str(r.get("결재상태") or "") != "결재완료"]
    if not pend:
        return "결재 대기 0건", False
    today = date.today()
    waits = [(today - c).days for r in pend if (c := _parse_ymd(r.get("생성일")))]
    if waits:
        avg = round(sum(waits) / len(waits))
        return f"결재 대기 {len(pend)}건 · 평균 대기 {avg}일(생성일 기준)", avg > 3
    return f"결재 대기 {len(pend)}건 · 평균 대기일 {_NO_MEASURE}", False


def ssot_week_cell(rows: "list | None") -> tuple[str, bool]:
    """업무·결재 SSOT(운영부 전원) — 「하루 3건」 루프(GM 2026-09-16 「하루에 3개씩 만들고 완료 · 1인당 최대 3건 ·
    운영부 실장 포함 6명」). 오늘 등록/완료 · 이번 주 누적 · 사람별 오늘 건수(상한 3) · 기한 지난 · 결재대기.
    종전 「주 15건 완료」 기준은 이 루프로 대체. 목록②와 같은 원천(todo_list)만 센다."""
    if rows is None:
        return f"{_NO_MEASURE}(업무 SSOT 조회 실패)", False
    today = _today()
    monday = today - timedelta(days=today.weekday())
    mine = [r for r in rows if str(r.get("담당자") or "").strip() in OPS_DEPT_STAFF]
    staff_n = len(OPS_DEPT_STAFF)

    def _created(r) -> "date | None":
        return _parse_ymd(r.get("생성일"))

    def _done_on(r) -> "date | None":
        if str(r.get("상태") or "") not in SSOT_DONE:
            return None
        return _parse_ymd(r.get("완료일")) or _parse_ymd(r.get("수정일"))

    if PERIOD is not None:
        # 과거 달 — 생성일·완료일(실제 날짜)로 그 달 안(1일~말일) 등록·완료만 잰다.
        # 진행중·보류·기한지난·결재대기·1인당 상한은 지금 상태만 있어 못 잰다(지어내지 않는다).
        first = PERIOD.replace(day=1)
        made_month = sum(1 for r in mine if (c := _created(r)) and first <= c <= PERIOD)
        done_month = sum(1 for r in mine if (d := _done_on(r)) and first <= d <= PERIOD)
        return (f"{_period_ym()} 등록 {made_month}건 · 완료 {done_month}건"
                f" · 진행중·보류/기한지난/결재대기=당시 값 없음(원장 현재상태만)"), False

    made_today = [r for r in mine if _created(r) == today]
    done_today = [r for r in mine if _done_on(r) == today]
    made_week = sum(1 for r in mine if (c := _created(r)) and monday <= c <= today)
    done_week = sum(1 for r in mine if (d := _done_on(r)) and monday <= d <= today)
    per = {}
    for r in made_today:
        per[str(r.get("담당자")).strip()] = per.get(str(r.get("담당자")).strip(), 0) + 1
    over_cap = [f"{k} {v}" for k, v in per.items() if v > DAILY_CAP_PER_PERSON]
    open_rows = ssot_ops_detail_rows(rows) or []
    overdue = sum(1 for r in open_rows if (d := _parse_ymd(r.get("종료일"))) and d < today)
    pend = sum(1 for r in mine if str(r.get("결재요청") or "").strip() and str(r.get("결재상태") or "") != "결재완료")
    md = lambda d: f"{d.month}/{d.day}"
    text = (f"오늘 등록 {len(made_today)}건 · 완료 {len(done_today)}건(1인 최대 {DAILY_CAP_PER_PERSON} · {staff_n}명) · "
            f"이번 주({md(monday)}~) 등록 {made_week} · 완료 {done_week} · 진행중·보류 {len(open_rows)}건 · "
            f"기한 지난 {overdue}건 · 결재대기 {pend}건"
            + (f" · 상한 초과 {', '.join(over_cap)}" if over_cap else ""))
    # 빨강 = 오늘 하나도 안 만들었거나(평일) 기한 지난 것이 있을 때. 상한 초과도 빨강.
    weekday = today.weekday() < 5
    return text, (weekday and not made_today) or overdue > 0 or bool(over_cap)


def find_ssot_row(rows: "list | None", title_contains: str, owner: str = "") -> dict | None:
    if not rows:
        return None
    for r in rows:
        if title_contains in str(r.get("업무명") or "") and (not owner or str(r.get("담당자") or "").strip() == owner):
            return r
    return None


def approval_submit_cell(rows: "list | None") -> tuple[str, bool]:
    """결재 SSOT 제출 — 멤버십 개편 기획안 행의 결재요청 칸 실측."""
    if rows is None:
        return f"{_NO_MEASURE}(업무 SSOT 조회 실패)", False
    if (nh := _period_no_history("결재요청 칸은 지금 상태만 보관")) is not None:
        return nh
    r = find_ssot_row(rows, "멤버십", owner="이경연 실장") or find_ssot_row(rows, "멤버십")
    if r is None:
        return f"{_NO_MEASURE}(멤버십 개편 기획안 SSOT 행 못 찾음)", True
    ap = str(r.get("결재요청") or "").strip()
    return f"결재요청 칸: {ap or '미제출(빈칸)'} · 상태 {r.get('상태') or '-'}", not ap


def _dup_count(rows: list) -> int:
    keys = [k for k in (_title_key(r.get("업무명")) for r in rows) if k]
    n = 0
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            if difflib.SequenceMatcher(None, keys[i], keys[j]).ratio() >= 0.72:
                n += 1
    return n


def chro_ssot_cell(rows: "list | None") -> tuple[str, bool]:
    """인사(CHRO) 업무·결재 SSOT 운영 — 나우열M 담당 행: 진행중·보류·기한 지난 것·중복."""
    if rows is None:
        return f"{_NO_MEASURE}(업무 SSOT 조회 실패)", False
    if (nh := _period_no_history("진행중·보류·중복은 지금 상태만 보관")) is not None:
        return nh
    mine = [r for r in rows if str(r.get("담당자") or "").strip() == "나우열M"]
    today = date.today()
    ip = sum(1 for r in mine if str(r.get("상태") or "") == "진행중")
    hold = sum(1 for r in mine if str(r.get("상태") or "") == "보류")
    overdue = sum(1 for r in mine
                  if str(r.get("상태") or "") not in SSOT_DONE and (d := _parse_ymd(r.get("종료일"))) and d < today)
    dup = _dup_count(mine)
    text = f"진행중 {ip}건 · 보류 {hold}건 · 기한 지난 것 {overdue}건 · 중복 {dup}건 · 전체 {len(mine)}건"
    return text, (overdue > 0 or dup > 0)


def ops_ssot_cell(rows: "list | None") -> tuple[str, bool]:
    """업무·결재 SSOT 한 줄 (GM 지시 2026-09-14 「업무&결재 SSOT + 결재 SSOT 제출 + 토글을 하나로」).
    같은 SSOT 를 두 행으로 나눠 두고 목록은 또 따로 아래에 폈던 것을 한 자리로 모은다."""
    week_text, week_bad = ssot_week_cell(rows)
    appr_text, appr_bad = approval_submit_cell(rows)
    return f"{week_text} · 결재 제출 — {appr_text}", (week_bad or appr_bad)


def automation_cell(objs: list) -> tuple[str, bool]:
    """GM 책임 ① 자동화·자율화(ERP+브로제이) — ERP = AWS 이관 표(status/aws_migration.json · 시토 정본)의
    영역별 전환 완료 수 / 전체, 브로제이 = 이번 달 카드 중 제목·체크에 「브로제이」가 든 카드의 체크 완료율.
    두 원천 다 있는 값만 적는다 — 없으면 없다고 적는다."""
    if (nh := _period_no_history("AWS 이관 표·브로제이 카드는 지금 상태만 보관")) is not None:
        return nh
    parts, warn = [], False
    try:
        d = json.loads((ROOT / "3. 웰페리온 가이드" / "status" / "aws_migration.json").read_text(encoding="utf-8"))
        rows = d.get("rows") or []
        done = sum(1 for r in rows if "완료" in str(r.get("switch_date") or ""))
        pct = round(done / len(rows) * 100) if rows else 0
        parts.append(f"ERP 서버 이관 {done}/{len(rows)}영역({pct}%)")
        warn = warn or pct < 100
    except Exception:
        parts.append("ERP 이관 표 없음")
        warn = True
    bj = [o for o in objs if "브로제이" in f'{o.get("title") or ""} {o.get("progress_note") or ""}']
    if bj:
        dn, tot = _checkbox_tally(bj)
        parts.append(f"브로제이 카드 {len(bj)}장 · 체크 {dn}/{tot}" + (f"({round(dn / tot * 100)}%)" if tot else ""))
        warn = warn or _overdue_objs(bj) > 0
    else:
        parts.append("브로제이 카드 이번 달 없음")
    return " · ".join(parts), warn


def expansion_cell() -> tuple[str, bool]:
    """GM 책임 ② 비즈니스 확장 — 전략 로드맵 「비즈니스 확장」 항목(status/monthly_ops_plan.json strategy_roadmap)
    상태·진척 + 시보(CBO) 배(status/_queue.json) 진행·대기·완료 수."""
    if (nh := _period_no_history("로드맵·배 상태는 지금 값만 보관")) is not None:
        return nh
    parts = []
    try:
        m = json.loads((ROOT / "status" / "monthly_ops_plan.json").read_text(encoding="utf-8"))
        items = (m.get("strategy_roadmap") or {}).get("items") or []
        ex = [i for i in items if "확장" in str(i.get("title") or "")]
        for i in ex:
            parts.append(f"로드맵 「{i.get('title')}」 {i.get('status') or '—'}"
                         + (f" · 진척 {i.get('progress')}" if i.get("progress") not in (None, "") else ""))
    except Exception:
        pass
    try:
        q = json.loads((ROOT / "status" / "_queue.json").read_text(encoding="utf-8"))
        qi = q if isinstance(q, list) else (q.get("items") or q.get("ships") or [])
        st = [str(it.get("status") or "") for it in qi if it.get("clevel") == "cbo"]
        parts.append(f"시보 배 진행 {st.count('IN_PROGRESS')} · 대기 {st.count('PENDING')} · 완료 {st.count('DONE')}")
    except Exception:
        parts.append("시보 배 조회 실패")
    return " · ".join(parts) if parts else f"{_NO_MEASURE}(로드맵·배 없음)", False


def directive_cell(objs: list) -> tuple[str, bool]:
    """GM 책임 ③ 회장님·대표님 지시 — 이번 달 카드 중 제목·체크에 「회장님」「대표님」이 든 카드의 체크 완료율과
    기한 지난 것. 카드가 없으면 잴 수 없다고 적는다(지시를 카드 체크 줄에 「[회장님 지시]」로 적으면 여기서 셈)."""
    ds = [o for o in objs if any(k in f'{o.get("title") or ""} {o.get("progress_note") or ""}' for k in ("회장님", "대표님"))]
    if not ds:
        return f"{_NO_MEASURE}(이번 달 카드에 회장님·대표님 지시 표기 없음 — 카드 체크 줄에 「[회장님 지시]」로 적으면 셉니다)", False
    dn, tot = _checkbox_tally(ds)
    over = _overdue_objs(ds)
    ck = f"체크 {dn}/{tot}({round(dn / tot * 100)}%)" if tot else "체크 항목 없음"
    return f"지시 카드 {len(ds)}장 · {ck} · 기한 지난 것 {over}건", over > 0


# ═══ GM 책임 항목 웰리 추천 2개(GM 2026-09-15 「웰리가 방향 추천해줘도 좋아, 지금 있는 것 +로」) ═══
#   ④ 체계화 = 같은 지시가 두 번 온 건수(0 이 목표) — worklog GM 접수(warn)에서 제목 유사도로 센다.
#   ⑤ 회수 = 사람에게 넘긴 것(원장에 처음 실린 건) 중 그날 안에 회신·종결된 비율.
#   측정식은 여기 코드 한 곳 · 못 재면 「미측정」(지어내지 않는다).
WORKLOG_PATH = ROOT / "status" / "worklog.jsonl"
_GM_AREAS = ("GM요청", "GM지시")


_DIRECTIVE_NOISE_RE = re.compile(r"https?://\S+|[A-Za-z]:[\\/]\S+|\S+@\S+")


def _directive_key(event) -> str:
    """지시 제목 비교 열쇠 — 주소·파일 경로·메일은 뺀다(같은 화면 주소를 붙인 다른 지시가 「같은 지시」로 잡히던 것) · 앞 40자."""
    t = _DIRECTIVE_NOISE_RE.sub(" ", str(event or ""))
    return "".join(ch for ch in t if ch.isalnum())[:40]


def dup_directive_cell() -> tuple[str, bool]:
    """이번 달 GM 접수 제목 중 앞선 날의 다른 접수와 0.8 이상 닮은 것 = 「같은 지시 두 번」."""
    ym = _period_ym()
    try:
        lines = WORKLOG_PATH.read_text(encoding="utf-8").splitlines()
    except Exception:
        return "미측정(worklog 없음)", False
    seen_keys: list[tuple[str, str]] = []   # (day, key)
    total = dup = 0
    for ln in lines:
        try:
            d = json.loads(ln)
        except Exception:
            continue
        ts = str(d.get("ts") or "")
        if not ts.startswith(ym) or d.get("area") not in _GM_AREAS or d.get("result") != "warn":
            continue
        key = _directive_key(d.get("event"))
        if len(key) < 12:
            continue
        total += 1
        day = ts[:10]
        if any(pd != day and difflib.SequenceMatcher(None, key, pk).ratio() >= 0.85 for pd, pk in seen_keys):
            dup += 1
        seen_keys.append((day, key))
    if not total:
        return "미측정(이번 달 접수 없음)", False
    return f"같은 지시 두 번 {dup}건(이번 달 접수 {total}건 · 목표 0)", dup > 0


def handoff_return_cell(seen: dict) -> tuple[str, bool]:
    """이번 달 원장에 처음 실린 담당 있는 건 중 번호가 나간 그날(원장 날짜 다음 날)까지 회신(replied_at)·종결(resolved_at)된 비율."""
    ym = _period_ym()
    first = first_seen_by_no()
    n = k = 0
    for no, (_d, it) in seen.items():
        f = first.get(no, "")
        owner = str(it.get("owner") or "").strip()
        if not f.startswith(ym) or not owner or is_ai_owner(owner):
            continue
        n += 1
        # 번호는 다음 날 07:50 통에서 나가므로 「당일」= 통이 나간 그날(원장 날짜 +1일)까지.
        limit = (datetime.strptime(f, "%Y-%m-%d").date() + timedelta(days=1)).isoformat()
        got = [str(it.get(k_) or "")[:10] for k_ in ("replied_at", "resolved_at")]
        if any(g and g <= limit for g in got):
            k += 1
    if not n:
        return "미측정(이번 달 넘긴 건 없음)", False
    pct = round(k / n * 100)
    return f"당일 회신 {k}/{n}({pct}%)", pct < 50


def _no_measure_cell(reason: str) -> tuple[str, bool]:
    return f"{_NO_MEASURE}({reason})", False


# 문의 회원 연락 — 관리자 평가 항목(GM 결정 2026-09-15 「관리자 점수 깎는 건 어때」).
#   원장 = status/inquiry_contact_watch.json — 07:50 ★중간관리자 통(send_ops_digest.inquiry_contact_section)이
#   매일 적는다. 여기서 다시 세지 않는다(약속 L21) · 감점 판정도 그쪽 상수(ESCALATE_BIZ_DAYS)를 쓴다.
def inquiry_contact_cell(line: str) -> tuple[str, bool]:
    if (nh := _period_no_history("연락 감시 원장은 지금 값만 보관")) is not None:
        return nh
    try:
        w = json.loads((ROOT / "status" / "inquiry_contact_watch.json").read_text(encoding="utf-8"))
        from send_ops_digest import stalled_biz_days, ESCALATE_BIZ_DAYS
    except Exception:
        return f"{_NO_MEASURE}(연락 감시 원장 없음 — 07:50 통이 첫 기록을 남긴 뒤 켜짐)", False
    lg = w.get(line) or {}
    if not lg:
        return f"{_NO_MEASURE}(연락 감시 원장에 아직 기록 없음)", False
    last = max(lg)
    rec = lg[last] or {}
    mp = date.today().strftime("%Y-%m")
    moved_month = sum(int((v or {}).get("resolved") or 0) for d, v in lg.items() if d.startswith(mp))
    stalled = stalled_biz_days(lg)
    text = (f"연락 없음 {rec.get('count', 0)}건({last[5:].replace('-', '/')}) · 이번 달 정리 {moved_month}건"
            f" · 움직임 없음 {stalled}영업일")
    if stalled >= ESCALATE_BIZ_DAYS:
        text += f" — 감점({ESCALATE_BIZ_DAYS}영업일 이상)"
    return text, stalled >= ESCALATE_BIZ_DAYS


RESP_HEAD = ('<tr><th class="ri">항목</th><th class="rc">기준(어떻게 평가)</th>'
             '<th class="rp">이번 달 진척(실측)</th><th class="rg">잘한 것</th>'
             '<th class="rf">보완할 것</th></tr>')


def _plain(s: str) -> str:
    """진척 막대 HTML(raw=True) 행의 실측 칸 → 태그 벗긴 텍스트(원장 저장용)."""
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s))).strip()


def resp_table(person: str, rows_def: list, ev: dict) -> tuple[list, dict]:
    """(행 모델 목록, 이 사람의 실측 스냅숏). 행 = {item, crit, raw, detail} — 실측 text/bad 와 잘한 것/보완할 것은
    원장(manager_eval_history · manager_eval)에서 화면 JS 가 읽는다(값을 두 곳에 두지 않는다). detail = 토글 내역
    {rows, empty, note, title} (종합접수처·점검 현황·업무&결재 SSOT · GM 지시 2026-09-14)."""
    rows = []
    snap: dict = {}
    for entry in rows_def:
        item, crit, fn = entry[0], entry[1], entry[2]
        raw = entry[3] if len(entry) > 3 else False  # True = fn 이 이미 안전한 진척 막대 HTML 을 낸다
        detail_fn = entry[4] if len(entry) > 4 else None
        text, bad = fn()
        good, fix = eval_cell(ev, person, item)
        snap[item] = {"text": _plain(text) if raw else text, "bad": bool(bad), "good": good, "fix": fix}
        rows.append({"item": item, "crit": crit, "raw": bool(raw),
                     "html": text if raw else "", "detail": detail_fn() if detail_fn else None})
    return rows, snap


def save_eval_history(month_snap: dict) -> dict:
    """그 달(PERIOD 있으면 그 달·없으면 이번 달) 키만 덮어쓴다 · 다른 달 키는 그대로(분기·연 누적 ·
    --backfill 소급도 이 함수를 그대로 쓴다). 되돌려주는 값 = 원장 전체."""
    try:
        d = json.loads(HIST_PATH.read_text(encoding="utf-8"))
    except Exception:
        d = {}
    months = d.get("months") if isinstance(d.get("months"), dict) else {}
    months[_period_ym()] = month_snap
    d = {"_doc": "중간관리자 책임 항목 실측 스냅숏 — manager_task_index.py 가 렌더 때마다 이번 달 키를 덮어쓴다"
                 "(send_ops_digest 07:50 매일). months[YYYY-MM][사람][항목] = {text 실측, bad 이상, good 잘한 것, fix 보완할 것}."
                 " GM업무 리더 현황 띠·중간관리자 업무목차 「분기 누적」 절이 읽는다. 손으로 고치지 않는다.",
         "updated_at": date.today().isoformat(), "months": dict(sorted(months.items()))}
    HIST_PATH.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    return d


def backfill_months(months: list[str], force: bool = False) -> None:
    """지난 달을 그 달 말일(PERIOD) 기준으로 실측해 원장(manager_eval_history) 그 달 키에 적는다
    (GM 지시 2026-09-16). 날짜(생성일·완료일·회신일·카드가 속한 달)로 거를 수 있는 항목만 그 달 값을
    다시 잰다 — 나머지는 각 측정fn 이 스스로 '당시 값 없음'을 적는다(_period_no_history · 지어내지 않는다).
    이미 있는 달 키는 건드리지 않는다(--force 없이는) — 이번 달(현재) 키는 PERIOD 가 그 달을 안 가리켜
    아예 손대지 않는다."""
    global PERIOD
    seen = latest_by_no()
    ssot_rows = fetch_ssot_rows()
    ev = load_eval()
    try:
        existing = json.loads(HIST_PATH.read_text(encoding="utf-8")).get("months", {})
    except Exception:
        existing = {}
    try:
        for ym in months:
            if ym in existing and not force:
                print(f"[backfill] {ym} 이미 있음 — 건너뜀(--force 로 덮어쓰기)")
                continue
            y, m = (int(x) for x in ym.split("-"))
            PERIOD = date(y, m, calendar.monthrange(y, m)[1])
            sales_data = fill_sales_current(seen)
            objs = load_month_objectives()
            rows_def = resp_rows_def(seen, ssot_rows, sales_data, objs)
            month_snap: dict = {"_소급": "2026-09-16 실측(웰리)"}
            for person in RESP_PEOPLE:
                _, month_snap[person] = resp_table(person, rows_def[person], ev)
            save_eval_history(month_snap)
            print(f"[backfill] {ym} 기록 완료 · PERIOD={PERIOD.isoformat()}")
    finally:
        PERIOD = None


def resp_rows_def(seen: dict, ssot_rows: "list | None", sales_data: "dict | None", objs: list) -> dict:
    """책임 항목 4인 정의 {사람: [(항목, 기준, 측정fn[, raw[, detail_fn]]), …]}. 책임 표(resp_section)와
    주간 회의자료 A3(build_meeting_a3)가 같은 정의를 쓴다 — 두 곳에 두지 않는다."""
    return {
        # GM 확정 2026-09-14 16:5x 「자동화 및 자율화(ERP+브로제이) 진척율 // 웰페리온 비즈니스 확장건 //
        #   회장님&대표님 지시 이렇게 3개로만」 — 종전 4개(카드 진척·회신 짝·결재 처리·주간 미팅)는 뺐다.
        "김남욱 GM": [
            ("자동화·자율화(ERP+브로제이) 진척률", "AWS 이관 표 영역별 완료 · 브로제이 카드 체크 완료율",
             lambda: automation_cell(objs)),
            ("웰페리온 비즈니스 확장", "확장 로드맵 항목 상태 · 시보(확장) 배 진행·완료",
             lambda: expansion_cell()),
            ("회장님·대표님 지시", "지시 카드 체크 완료율 · 기한 지난 것 0",
             lambda: directive_cell(objs)),
            # 웰리 추천 2개(GM 2026-09-15 「+로」) — 이름 끝 「(웰리 추천)」 딱지가 원장 키에도 그대로 남는다.
            ("체계화 — 같은 지시 두 번 (웰리 추천)", "같은 지시가 두 번 온 건수 0 · worklog GM 접수 제목 유사도",
             lambda: dup_directive_cell()),
            ("회수 — 당일 회신 비율 (웰리 추천)", "사람에게 넘긴 것 중 번호가 나간 그날까지 회신·종결 비율 · 50% 미만 감점",
             lambda: handoff_return_cell(seen)),
        ],
        "이경연 실장": [
            ("매출(회원권+옵션)", "월 매출목표 대비 달성률 · 옵션 포함",
             lambda: sales_bucket_cell(sales_data, "member"), True),
            ("종합접수처(운영부)", "1영업일 안 첫 처리 · 7일 안 닫기 · 담당 미배정 0",
             lambda: reception_dept_cell("운영부"), False, reception_toggle_detail_html),
            ("점검 현황(운영부)", "요금 변경 준비·사우나 정비 체크리스트 진행률"
                             "(월간운영계획 체크 중 담당 이경연/운영부)",
             lambda: _ops_progress_cell(objs), False, lambda: check_detail_html(objs)),
            ("업무·결재 SSOT(운영부 전원)",
             "하루 3건 루프 — 매일 만들고 끝낸다(1인당 최대 3건 · 실장 포함 6명) + 기획안·보고는 결재요청 칸까지 채워 제출",
             lambda: ops_ssot_cell(ssot_rows), False, lambda: ssot_detail_html(ssot_rows)),
            ("문의 회원 연락(멤버십)", "임정은M 라인 연락 기록 없는 문의 0 · 3영업일 움직임 없으면 감점",
             lambda: inquiry_contact_cell("member")),
            ("소통", "확인요청 회신율 · 최장 경과일",
             lambda: ledger_reply_cell(seen, "이경연 실장")),
        ],
        "이정헌 소장": [
            ("시설 점검 이행", "회차별 측정값 입력률 · 기준이탈 건 당일 처리(입력률로 잰다)",
             lambda: facility_check_cell()),
            ("종합접수처(시설부)", "시설부 배정 건 7일 안 닫기 · 미배정 0",
             lambda: reception_dept_cell("시설부")),
            ("설비·시설 업무 일정", "전사일정 시설부 이번 달 건수 · 완료 · 놓친 건(감점)",
             lambda: facility_schedule_cell()),
            ("설비 매뉴얼", "ERP 시설부 체계 등록 N/전체 · 올해 말 마무리 목표",
             lambda: manual_count_cell()),
            ("소통", "확인요청 회신율 · 최장 경과일",
             lambda: ledger_reply_cell(seen, "이정헌 소장")),
        ],
        "나우열M": [
            ("파트너팀 매출 관리", "월 매출목표 대비 달성률 · 파트너팀=강습 전체",
             lambda: sales_bucket_cell(sales_data, "lessons"), True),
            ("인사(CHRO) — 업무·결재 SSOT 운영", "진행중·보류·기한 지난 행 정리 · 중복 행 0",
             lambda: chro_ssot_cell(ssot_rows)),
            ("매출·지출(CFO) — 체계·시스템 구축", "매출보고 담당 건 회신 · 강습(파트너팀) 매출 마감 정확도",
             lambda: _no_measure_cell("자동 집계 원장 없음")),
            ("문의 회원 연락(강습)", "파트너팀 리더 라인 연락 기록 없는 문의 0 · 3영업일 움직임 없으면 감점",
             lambda: inquiry_contact_cell("lesson")),
            ("소통", "확인요청 회신율 · 최장 경과일",
             lambda: ledger_reply_cell(seen, "나우열M")),
        ],
    }


def resp_section(seen: dict, ssot_rows: "list | None", sales_data: "dict | None" = None) -> tuple[dict, dict]:
    """돌려주는 값 = ({사람: 행 모델 목록} 3인, 원장 전체). 스냅숏은 4인(GM 포함) — GM업무 띠가 그 원장을 읽는다."""
    ev = load_eval()
    objs = load_month_objectives()
    rows_def = resp_rows_def(seen, ssot_rows, sales_data, objs)
    model: dict = {}
    month_snap: dict = {}
    for person in RESP_PEOPLE:
        rows, month_snap[person] = resp_table(person, rows_def[person], ev)
        if person in MGR_PEOPLE:        # 화면은 3인만(GM 지시 2026-09-15)
            model[person] = rows
    hist = save_eval_history(month_snap)   # 표를 만든 그 값으로 원장 이번 달 키 갱신(계산 한 번)
    return model, hist


# ═══ 실장 건별 목록 3종(GM 지시 2026-09-14 "종합접수처 건·업무SSOT 건·점검현황 건별로 보고") ═══
#   책임 표(요약 한 줄)로는 뭐가 몇 건인지만 보이고 "그래서 뭔데"가 안 보인다는 지적 —
#   이경연 실장 표 바로 아래 건별 목록 3개를 편다. 원천은 이미 있는 함수가 쓰는 것 그대로
#   (접수 GAS reg_list·업무 SSOT todo_list·월간운영계획) — 새 원장을 만들지 않는다(약속 L21).

def _reception_handler(r: dict) -> str:
    hc = r.get("handlerCanon") or []
    h = str(hc[0]) if hc else str(r.get("handler") or "").strip()
    return h or "미배정"


def _reception_reporter(r: dict) -> str:
    """접수자 — 원장(reg_list)의 reporter 칸 그대로(회원이 적은 접수는 '회원')."""
    return str(r.get("reporter") or "").strip() or "—"


def _reception_deliver_to(r: dict, dept: str) -> str:
    """전달 대상 — 처리자가 있으면 그 사람, 비면 부서 기본값(GM 지시 2026-09-14).
    담당 미배정 집계(reception_dept_cell)는 그대로 _reception_handler 를 쓴다 — 여긴 표시용."""
    h = _reception_handler(r)
    if h != "미배정":
        return h
    default = DEPT_DEFAULT_HANDLER.get(dept)
    return f"{default}(기본)" if default else "미배정"


def reception_dept_detail(dept: str = "운영부") -> "tuple[list, list] | tuple[None, None]":
    """부서 열린 건(분실물 제외) + 분실물 목록 — 진척 칸(reception_dept_cell)과 건별 목록①이
    같은 함수를 쓴다(원천 이중화 금지). 조회 실패면 (None, None)."""
    try:
        from collectors.ops_shared import RECEPTION_EXEC_URL, gas_get, reception_rows
        resp = gas_get(RECEPTION_EXEC_URL, params={"action": "reg_list"}, timeout=20,
                       label="manager_task_index 접수 건별")
        if resp is None:
            return None, None
        data = resp.json()
        if not data.get("ok"):
            return None, None
        rows = reception_rows(data.get("data", []))
    except Exception:
        return None, None
    mine = [r for r in rows if str(r.get("dept") or "") == dept and str(r.get("status") or "") != "완료"]
    lost = [r for r in mine if "분실물" in str(r.get("category") or "")]
    rest = [r for r in mine if "분실물" not in str(r.get("category") or "")]
    return rest, lost


# ═══ 토글 상세표 공통 틀(GM 지적 2026-09-15 「번호가 왼쪽 벽에 붙고 칸 정렬이 안 맞는다 · 셋 다」) ═══
#   종합접수처·점검 현황·업무&결재 SSOT 세 표가 같은 6열(번호|내용|담당|기한|경과|비고) · colgroup +
#   table-layout:fixed 로 열 폭을 못 박는다 — 표마다 열 폭 배열이 같아야 머리행과 값 칸이 맞는다.
DT_COLS = [("번호", "dt-no"), ("내용", "dt-ti"), ("담당·전달", "dt-who"),
           ("기한", "dt-due"), ("경과", "dt-age"), ("비고", "dt-etc")]


def detail_table(rows: list[list[str]], empty: str, note: str, title: str = "") -> dict:
    """토글 내역 모델 — rows = escape 된 셀 HTML 6개짜리 목록(순서 = DT_COLS). 화면 JS 가 colgroup 표로 그린다."""
    return {"rows": rows, "empty": empty, "note": note, "title": title}


def _age_td(age: "int | None") -> str:
    """경과 칸 내용 — 값이 없으면 —. 색은 age_cls 그대로."""
    if age is None:
        return "—"
    return f'<span class="age {age_cls(age)}">{age}일</span>'


def reception_toggle_detail_html() -> dict:
    """책임 표 「종합접수처(운영부)」 행을 클릭하면 펼쳐지는 내역 — 접수자·전달 대상 칸
    포함(GM 지시 2026-09-14 "누가 접수했고, 누구에게 전달해야하는지도 정리가 되면"). 원천은
    reception_dept_detail 그대로(진척 칸과 같은 필터 · 약속 L21)."""
    from collectors.ops_shared import reception_elapsed_days
    rest, lost = reception_dept_detail("운영부")
    if rest is None:
        return detail_table([], f"{_NO_MEASURE}(접수처 조회 실패)", "닫는 곳: 종합접수처 화면 처리자·처리메모·전달완료")
    now = datetime.now()
    rest_sorted = sorted(rest, key=lambda r: -reception_elapsed_days(r, now))
    rows = []
    for r in rest_sorted:
        age = reception_elapsed_days(r, now)
        content = _mask(str(r.get("content") or "").strip())
        memo_on = "처리메모 있음" if str(r.get("memo") or "").strip() else "처리메모 —"
        cat = html.escape(str(r.get("category") or ""))
        rows.append([f'#{html.escape(str(r.get("regId") or "—"))}',
                     f'<span title="{html.escape(content)}">{html.escape(short(content) if content else "—")}</span>'
                     + (f'<span class="cat">{cat}</span>' if cat else ""),
                     html.escape(_reception_deliver_to(r, "운영부")),
                     "—",
                     _age_td(age),
                     f'접수 {html.escape(_reception_reporter(r))} · {memo_on}'])
    lost_line = ""
    if lost:
        lage = max((reception_elapsed_days(r, now) for r in lost), default=0)
        lost_line = f'분실물 {len(lost)}건(담당 미배정 · 최장 {lage}일) · '
    return detail_table(rows, "열린 건 없음", lost_line + "닫는 곳: 종합접수처 화면 처리자·처리메모·전달완료")


def ssot_ops_detail_rows(rows: "list | None") -> "list | None":
    """운영부 전원(OPS_DEPT_STAFF) 진행중·보류 행 — 담당자 순 · 그 안에서 기한 지난 순."""
    if rows is None:
        return None
    mine = [r for r in rows if str(r.get("담당자") or "").strip() in OPS_DEPT_STAFF
            and str(r.get("상태") or "") in ("진행중", "보류")]
    today = date.today()

    def overdue(r: dict) -> int:
        d = _parse_ymd(r.get("종료일"))
        return (today - d).days if d else -1

    order = {n: i for i, n in enumerate(OPS_DEPT_STAFF)}
    mine.sort(key=lambda r: (order.get(str(r.get("담당자") or "").strip(), 99), -overdue(r)))
    return mine


# ═══ 문서가 따라다니게 (GM 지시 2026-09-14) ════════════════════════════════════
#   "GM업무에서 중간관리자 업무로 넘어가면 A3 요약본·폼 등 문서가 다 사라진다."
#   업무 SSOT 화면은 이미 딥링크를 갖고 있다 — ?item=ID(카드로 이동) · ?doc=ID&which=plan|result
#   (기획안·결과보고 뷰어). 여기서는 그 주소를 만들어 붙이기만 한다(새 화면·새 원장 0).
SSOT_PAGE = "../todo/업무 현황 SSOT.html"


def doc_urls(r: dict) -> list[str]:
    """업무 SSOT 행에 붙은 첨부 주소 — 파일URL 칸은 줄바꿈으로 여러 개가 들어온다."""
    out: list[str] = []
    for key in ("파일URL", "링크"):
        for u in str(r.get(key) or "").split("\n"):
            u = u.strip()
            if u.startswith("http") and u not in out:
                out.append(u)
    return out


def ssot_links(r: dict) -> str:
    """업무 SSOT 행 하나를 문서까지 딸린 한 칸으로. 업무명 = 그 카드로, 📄/🎯 = 문서 뷰어로,
    📎 = 첨부 주소로. 없는 링크는 만들지 않는다(주소를 지어내지 않는다)."""
    tid = str(r.get("id") or "").strip()
    title = str(r.get("업무명") or "").strip()
    disp = html.escape(short(title) if title else "—")
    tip = html.escape(title)
    if tid:
        q = quote(tid, safe="")
        head = (f'<a href="{SSOT_PAGE}?item={q}" target="_blank" rel="noopener" title="{tip}">{disp}</a>')
    else:
        head = f'<span title="{tip}">{disp}</span>'
    tail = []
    body = str(r.get("내용") or "")
    if tid and "===PLAN===" in body:
        tail.append(f'<a class="dc" href="{SSOT_PAGE}?doc={q}&amp;which=plan" '
                    f'target="_blank" rel="noopener">📄 기획안</a>')
    if tid and "===RESULT===" in body:
        tail.append(f'<a class="dc" href="{SSOT_PAGE}?doc={q}&amp;which=result" '
                    f'target="_blank" rel="noopener">🎯 결과보고</a>')
    for i, u in enumerate(doc_urls(r), 1):
        tail.append(f'<a class="dc" href="{html.escape(u, quote=True)}" target="_blank" '
                    f'rel="noopener" title="{html.escape(u)}">📎 첨부{i}</a>')
    return head + (f'<div class="dcs">{" ".join(tail)}</div>' if tail else "")


def objective_docs_html(o: dict) -> str:
    """월간운영계획 카드에 달린 자료 링크 — GM업무 화면이 읽는 그 칸(docs[]·doc) 그대로.
    docs 원소는 {label, href} 도 있고 주소 문자열만 있는 것도 있다. 두 화면이 같은 폴더에
    있어 주소를 바꿀 것이 없다."""
    raw = list(o.get("docs") or [])
    if o.get("doc"):
        raw.append(o["doc"])
    seen, out = set(), []
    for d in raw:
        href = str((d.get("href") if isinstance(d, dict) else d) or "").strip()
        if not href or href in seen:
            continue
        seen.add(href)
        label = str((d.get("label") if isinstance(d, dict) else "") or "").strip() or href.split("/")[-1]
        out.append(f'<a class="dc" href="{html.escape(href, quote=True)}" target="_blank" '
                   f'rel="noopener" title="{html.escape(label)}">📎 {html.escape(short(label, 22))}</a>')
    return f'<div class="dcs">{" ".join(out)}</div>' if out else ""


def ssot_detail_html(ssot_rows: "list | None") -> dict:
    mine = ssot_ops_detail_rows(ssot_rows)
    if mine is None:
        return detail_table([], f"{_NO_MEASURE}(업무 SSOT 조회 실패)", "닫는 곳: 업무 현황 SSOT 화면 상태·종료일",
                            title="② 업무·결재 SSOT(운영부 전원)")
    today = date.today()
    rows = []
    for r in mine:
        d = _parse_ymd(r.get("종료일"))
        due_disp = d.isoformat() if d else (str(r.get("종료일") or "").strip()[:10] or "—")
        od = (today - d).days if d else None
        ap = str(r.get("결재요청") or "").strip()
        rows.append([html.escape(str(r.get("id") or "—")),
                     ssot_links(r),
                     html.escape(str(r.get("담당자") or "—")),
                     html.escape(due_disp),
                     _age_td(od if od and od > 0 else None),
                     f'결재요청 {html.escape(ap)}' if ap else "—"])
    return detail_table(rows, "진행중·보류 없음", "닫는 곳: 업무 현황 SSOT 화면 상태·종료일 · 경과 = 종료일 지난 일수",
                        title=f"② 업무·결재 SSOT(운영부 전원) {len(mine)}건")


_CHK_BODY_RE = re.compile(r"^\s*□\s*\d*\)?\s*(.+)$")
_OWNER_TAG_RE = re.compile(r"담당:\s*([^·\n]+)")
_DUE_TAG_RE = re.compile(r"기한:\s*([^·\n]+)")


def _ops_dept_cards(objs: list) -> list:
    """담당 이경연 실장 또는 dept 에 '운영부'가 든 카드 — 점검 현황 진척 칸과 건별 목록③이
    같은 필터를 쓴다(GM 지적 2026-09-14 — 칸은 카드 1건, 목록은 5건으로 어긋났었다)."""
    return [o for o in objs
            if str(o.get("owner") or "").strip() == "이경연 실장" or "운영부" in str(o.get("dept") or "")]


def _check_owner_text(o: dict, ln: str) -> str:
    """체크 담당 — 체크 줄 「담당:」 표기가 먼저, 없으면 카드 담당, 그것도 없으면 담당 없음."""
    m = _OWNER_TAG_RE.search(ln)
    v = m.group(1).strip() if m else ""
    if v and v != "(미정)":
        return v
    v2 = str(o.get("owner") or "").strip()
    return v2 or "담당 없음"


def _ops_check_lines(objs: list) -> list[tuple[dict, str, bool]]:
    """(카드, 체크줄, 완료여부) — _ops_dept_cards 카드의 체크 줄(☑·□) 중 담당이 운영부인 것만
    (GM 지적 2026-09-14 — 카드는 운영부·파트너팀 혼합인데 줄은 cpo·coo·시우·나우열M·김남욱GM 몫이 섞여
    실장 점검으로 보였다). 담당 판정 = _check_owner_text(줄 「담당:」 우선, 없으면 카드 담당).
    점검 현황 진척 칸(_ops_progress_cell)·실장 토글 내역(check_ops_detail_rows)이 같은 원천을 쓴다."""
    out = []
    for o in _ops_dept_cards(objs):
        for raw in str(o.get("progress_note") or "").split("\n"):
            s = raw.strip()
            done = s.startswith("☑")
            if not done and not s.startswith("□"):
                continue
            owner_text = _check_owner_text(o, s)
            if owner_text in OPS_DEPT_STAFF or owner_text == "운영부":
                out.append((o, s, done))
    return out


def check_ops_detail_rows(objs: list) -> list[tuple[dict, str]]:
    """(카드, 체크줄) — _ops_check_lines 중 미완만.
    카드 dict 를 그대로 돌려준다 — 카드 id(GM업무 딥링크)와 docs(자료 링크)가 필요하다."""
    return [(o, ln) for o, ln, done in _ops_check_lines(objs) if not done]


def _ops_progress_cell(objs: list) -> tuple[str, bool]:
    """점검 현황(운영부) 진척 칸 — _ops_check_lines 와 같은 원천(카드 수는 그 줄이 실제로 걸린
    카드만 · GM 지시 2026-09-14, 진척 칸이 실장 토글 내역과 같은 건수를 내게 한다)."""
    lines = _ops_check_lines(objs)
    if not lines:
        return f"{_NO_MEASURE}(해당 카드 없음)", False
    cards, seen = [], set()
    for o, _ln, _done in lines:
        if id(o) not in seen:
            seen.add(id(o))
            cards.append(o)
    done = sum(1 for _o, _ln, d in lines if d)
    total = len(lines)
    over = _overdue_objs(cards)
    ck = f"체크 {done}/{total}({round(done / total * 100) if total else 0}%)" if total else "체크 항목 없음"
    return f"카드 {len(cards)}건 · {ck} · 기한 지난 것 {over}건", over > 0


def _check_due_text(ln: str) -> str:
    m = _DUE_TAG_RE.search(ln)
    v = m.group(1).strip() if m else ""
    return v if v and v != "(미정)" else "—"


def _check_deliver_to(owner_text: str) -> str:
    """전달 대상 — 담당 표기가 운영부 실무진이면 그 사람, 아니면 운영부 카드 기본값(이경연 실장)."""
    if owner_text in OPS_DEPT_STAFF:
        return owner_text
    default = DEPT_DEFAULT_HANDLER["운영부"]
    return f"{default}(기본)"


def check_detail_html(objs: list) -> dict:
    """책임 표 「점검 현황(운영부)」 행을 클릭하면 펼쳐지는 내역 — 체크 담당·전달 대상 칸
    포함(GM 지시 2026-09-14). 원천은 check_ops_detail_rows 그대로(진척 칸과 같은 필터)."""
    pairs = check_ops_detail_rows(objs)
    rows = []
    # ★카드 제목은 카드마다 한 번만 (GM 지적 2026-09-14 「카드제목 중복된 값을 저렇게 하는게 있다고?」).
    #   종전엔 체크 줄마다 같은 제목을 다시 적어, 한 카드에 체크가 일곱이면 제목이 일곱 번 보였다.
    #   둘째 줄부터 제목 칸을 비운다 — 값이 사라지는 것이 아니라 반복이 사라진다.
    last_card = None
    for o, ln in pairs:
        title = str(o.get("title") or "").strip()
        same = (title == last_card)
        last_card = title
        oid = str(o.get("id") or "").strip()
        disp = html.escape(short(title, 28) if title else "—")
        card = (f'<a href="GM업무.html#gm-{html.escape(oid, quote=True)}" target="_blank" '
                f'rel="noopener" title="{html.escape(title)}">{disp}</a>' if oid
                else f'<span title="{html.escape(title)}">{disp}</span>')
        body = _mask(_CHK_BODY_RE.sub(r"\1", ln))
        owner_text = _check_owner_text(o, ln)
        rows.append([html.escape(oid or "—"),
                     f'<span title="{html.escape(body)}">{html.escape(short(body))}</span>',
                     html.escape(_check_deliver_to(owner_text)),
                     html.escape(_check_due_text(ln)),
                     "—",
                     ('〃' if same else card + objective_docs_html(o))])
    return detail_table(rows, "미완 체크 없음", "닫는 곳: GM업무 화면 체크 · 비고 = 카드(같은 카드는 〃)")


def _title_key(t: str) -> str:
    """한글·영문·숫자만 남기고 앞 24자 — 웰리 실측(09-10)과 같은 대조 기준."""
    return "".join(ch for ch in str(t or "") if ch.isalnum())[:24]


def find_ssot_match(issue: str, ssot_rows: list) -> dict | None:
    """제목이 0.62 이상 닮은 SSOT 행 하나. 완료·폐기 여부는 안 가린다 — 끝난 건도 목차에
    남아 있으면 안 된다(GM 지시)."""
    key = _title_key(issue)
    if not key:
        return None
    for r in ssot_rows:
        rk = _title_key(r.get("업무명"))
        if rk and difflib.SequenceMatcher(None, key, rk).ratio() >= 0.62:
            return r
    return None


def cat_name(it: dict) -> str:
    """category 칸이 '5' · '시설 및 환경' · '[6] 회원·CS' 로 섞여 들어온다 — 이름 하나로 편다."""
    raw = str(it.get("category") or "").strip().lstrip("[").replace("]", " ").strip()
    if not raw:
        return ""
    head = raw.split()[0]
    if head in CAT:
        return CAT[head]
    return raw


def group_of(it: dict) -> str:
    cn = cat_name(it)
    text = f'{it.get("issue") or ""} {it.get("note") or ""}'
    for name, cats, words in GROUPS:
        if cn in cats:
            return name
    for name, cats, words in GROUPS:
        if any(w in text for w in words):
            return name
    return "기타"


def flags_of(it: dict) -> list[str]:
    text = f'{it.get("issue") or ""} {it.get("note") or ""}'
    return [n for n, words in FLAGS if any(w in text for w in words)]


def short(t: str, n: int = 40) -> str:
    """첫 문장 또는 40자까지만 — 전문은 지우지 않고 title 로 접어 둔다."""
    s = t.split(". ")[0].strip()
    if len(s) > n:
        return s[:n].rstrip() + "…"
    return s + "…" if len(s) < len(t) else s


def age_cls(age: int) -> str:
    return "old" if age >= 14 else ("warn" if age >= 7 else "")


# 담당 후보 — 부서 순서대로(GM 지시 2026-09-10). 운영부 6 · 시설부 3 · 그 밖 5.
#   2026-09-11 GM 지적("담당칸에 각 부서장이 담당자 배정까지도 할 수 있게 드랍다운 항목에")으로
#   이 목록을 JS 에서 파이썬으로 옮겼다 — 담당칸이 datalist(입력칸 자동완성)라 칸에 이름이 이미
#   있으면 눌러도 목록이 안 펼쳐졌다. 이제 <select> 로 서버에서 찍는다.
OWNER_CHOICES = [
    "이경연 실장", "최준용M", "임정은M", "윤병현AM", "백승화 사원", "진수아 사원",   # 운영부
    "이정헌 소장", "김종현 차장", "박호균 과장",                                    # 시설부
    "나우열M", "이연희 반장", "박남일 반장", "양상규 고문", "김남욱 GM",            # 그 밖
]


def owner_select(no: int, who: str) -> str:
    """담당 드롭다운. 원장 값이 후보에 없는 이름이면 그 이름을 옵션으로 더해 선택 상태로 둔다
    (값을 잃지 않게). 저장 자리는 종전과 같은 공용 보드 MGR_TASK_OWNER 다."""
    opts = ['<option value="">— 미지정 —</option>']
    opts += [f'<option value="{html.escape(n)}"{" selected" if n == who else ""}>{html.escape(n)}</option>'
             for n in OWNER_CHOICES]
    if who and who not in OWNER_CHOICES:
        opts.append(f'<option value="{html.escape(who)}" selected>{html.escape(who)}</option>')
    return f'<select class="own-sel" data-o="{no}">{"".join(opts)}</select>'


def is_ai_owner(owner) -> bool:
    """담당이 사람이 아니라 AI 판정 건 — 사람 목차에서 빼고 「AI 처리 건」 한 줄로만 보인다."""
    return str(owner or "").strip().startswith("AI ")


def _fmt_amt(v, unit: str) -> str:
    """금액은 억·만 단위로 접어 읽는다 — 0 이 여덟 개면 사람이 못 읽는다."""
    try:
        n = int(v)
    except Exception:
        return f"{v}{unit}"
    if unit != "원":
        return f"{n:,}{unit}"
    if n >= 100000000:
        eok, rest = divmod(n, 100000000)
        man = rest // 10000
        return f"{eok}억" + (f" {man:,}만" if man else "")
    return f"{n // 10000:,}만" if n >= 10000 else f"{n:,}원"


def progress_cell(it: dict) -> str:
    """목표가 적힌 항목만 진척을 보인다(GM 지시 2026-09-11 「9월 매출 목표 … 진척율도 보여주면 좋을듯」).
    목표가 없으면 빈 칸 — 없는 숫자를 지어 채우지 않는다."""
    tgt = it.get("target")
    if not tgt:
        return '<td class="pg">—</td>'
    cur = it.get("current") or 0
    unit = str(it.get("unit") or "")
    try:
        pct = max(0, min(100, round(int(cur) / int(tgt) * 100)))
    except Exception:
        return '<td class="pg">—</td>'
    cls = "pg-ok" if pct >= 80 else ("pg-mid" if pct >= 40 else "pg-low")
    return (f'<td class="pg" title="{_fmt_amt(cur, unit)} / {_fmt_amt(tgt, unit)}">'
            f'<div class="bar"><i class="{cls}" style="width:{pct}%"></i></div>'
            f'<span class="pgn">{pct}%</span>'
            f'<span class="pgt">{_fmt_amt(cur, unit)} / {_fmt_amt(tgt, unit)}</span></td>')


def fill_sales_current(seen: dict) -> None:
    """매출 책임 줄의 현재값을 이번 달 실측으로 채운다 — 손으로 적으면 하루 만에 낡는다.
    값을 못 가져오면 아무것도 바꾸지 않는다(0 으로 덮지 않는다 · 지어 채우지 않는다).
    출처는 아침 통이 쓰는 그 경로 하나다(sales_month · 새 경로를 만들지 않는다 · 약속 L21).

    사람마다 재는 범위가 다르다(GM 지시 2026-09-11). 항목의 sales_bucket 이 어느 통을 볼지 정한다:
      member  = 멤버십 회원권 + 옵션 (운영부 · 이경연 실장)
      lessons = 파트너팀 전체 (나우열M · GXE 포함 · 뮤지컬도 이 통에 들어 있다)
      total   = 전사 합계 (버킷을 안 적은 옛 항목의 기본값 — 종전 동작 그대로)
    sales_month 응답이 이미 member·lessons·total 셋으로 갈라 주므로 새 집계를 만들지 않는다.

    올려 준 data(member·lessons·total)는 호출부가 👤 책임 항목 매출 진척 칸에도 그대로 돌려 쓴다
    (같은 통을 두 번 부르지 않는다 — 약속 L21) — 조회 실패면 None."""
    rows = [it for _n, (_d, it) in seen.items()
            if it.get("target") and str(it.get("unit") or "") == "원"]
    try:
        import ops_daily_digest as o
        resp = o._gas_get(o.PROC_EXEC_URL,
                          {"action": "sales_month", "password": o._proc_password()},
                          timeout=60, label="manager_task_index 매출")
        data = resp.json() if resp is not None else {}
        if not data.get("ok"):
            return None
        mi = _today().month - 1
        for it in rows:
            bucket = str(it.get("sales_bucket") or "total")
            cur = (data.get(bucket) or [None] * 12)[mi]
            if cur is not None:
                it["current"] = int(cur)
        return data
    except Exception:
        return None


def sales_bucket_cell(sales_data: "dict | None", bucket: str) -> tuple[str, bool]:
    """월 매출 실측 진척 — sales_month 의 bucket(member/lessons) 값 · 목표는
    status/sales_targets.json(정본) 에 등록된 것만 쓴다. 등록 안 됐으면
    '목표 미등록'만 적고 %·막대는 안 켠다(지어내지 않는다 · GM 지시 2026-09-14)."""
    if not sales_data:
        return f"{_NO_MEASURE}(매출 조회 실패)", False
    mi = _today().month - 1
    cur = (sales_data.get(bucket) or [None] * 12)[mi]
    if cur is None:
        return f"{_NO_MEASURE}(매출 자료 없음)", False
    cur = int(cur)
    target = load_sales_target(bucket)
    if not target:
        return f"현재 {_fmt_amt(cur, '원')} · 목표 미등록(status/sales_targets.json 미확인)", False
    pct = max(0, min(100, round(cur / target * 100)))
    cls = "pg-ok" if pct >= 80 else ("pg-mid" if pct >= 40 else "pg-low")
    bar = (f'<span class="pg"><span class="bar"><i class="{cls}" style="width:{pct}%"></i></span>'
           f'<span class="pgn">{pct}%</span> '
           f'<span class="pgt">현재 {html.escape(_fmt_amt(cur, "원"))} / 목표 {html.escape(_fmt_amt(target, "원"))}</span></span>')
    return bar, False


def _mask(text: str) -> str:
    """사람 원문을 공개 스냅숏에 옮기는 자리는 전부 이 함수를 거친다(2026-09-15 대장 규칙 · kakao_room_listen.mask_secrets)."""
    try:
        from kakao_room_listen import mask_secrets
        return mask_secrets(text)
    except Exception:
        return text


def is_overdue(it: dict) -> bool:
    d = _parse_ymd(str(it.get("due") or "")[:10])
    return bool(d and d < date.today())


NEXT_STEP_MISSING = "다음 한 걸음 미정 — 담당이 한 줄로"


def row_model(no: int, seen_date: str, it: dict) -> dict:
    """열린 건 하나 → 공개 스냅숏 행. 담는 것 = 번호·제목·담당·함께·기한·다음 한 걸음·경과·구분·SSOT 열쇠·진척 —
    카톡 원문(note)·전화·비밀값은 싣지 않는다(공개 저장소·Pages 에 배포되는 파일)."""
    cn = cat_name(it)
    todo_id = str(it.get("todo_id") or "").strip()
    ss = "ssot" if todo_id else ("reception" if is_reception_item(it) else ("reply" if kind_of(it) == "reply" else "none"))
    out = {"no": no, "date": seen_date, "age": days_since(seen_date),
           "issue": _mask(str(it.get("issue") or "")), "cat": cn,
           "owner": str(it.get("owner") or "").strip(), "with": str(it.get("with") or "").strip(),
           "due": str(it.get("due") or "").strip()[:10], "overdue": is_overdue(it),
           "next_step": _mask(str(it.get("next_step") or "").strip()),
           "todo_id": todo_id, "ss": ss, "flags": flags_of(it)}
    if it.get("target"):
        out["target"], out["current"], out["unit"] = it.get("target"), it.get("current") or 0, str(it.get("unit") or "")
    return out


# 종합접수처에서 들어와 접수처에서 닫는 건 — 업무 SSOT 에 올릴 것이 아니다(GM 2026-09-10
#   "종합접수처까지 내용이 다 올라가있는데, 이것을 SSOT에 올리는건 아닌 것 같아").
#   접수는 접수번호로 열리고 그 화면에서 닫힌다. 여기서는 「접수처에서 닫음」으로만 표시하고
#   「SSOT 미등록」 셈에서 뺀다 — 안 그러면 실무진이 같은 건을 두 곳에 올리게 된다.
_RECEPTION_MARK = re.compile(r"접수\s*\d+|RECEPTION-\d+|접수ID|FB\d{6}|종합접수처")
_RECEPTION_WORDS = ("컴플레인", "분실물", "미끄러", "고장", "청결", "매너", "자리 부족")


def is_reception_item(it: dict) -> bool:
    text = f'{it.get("issue") or ""} {it.get("note") or ""}'
    if _RECEPTION_MARK.search(text):
        return True
    return any(w in text for w in _RECEPTION_WORDS)


# 업무 구분 (GM 2026-09-11 「중간관리자 업무에 종합접수처 등의 내용까지 업무화 시켜놨던데,
#   업무구분이 명확해야할 것 같아」). 낱말 추측보다 원장의 kind 값이 먼저다 — 추측은 kind 가
#   없을 때만 쓴다. 값을 두 곳에 두지 않으려고 판정은 이 함수 하나만 쓴다.
#     routine   = 끝나지 않는 상시 책임(주간 점검·접수 마무리·점검 이행·SSOT 갱신)
#     reception = 종합접수처에서 열려 그 화면에서 닫히는 건
#     task      = 기한이 있고 끝나면 닫히는 일 — 이것만이 「업무」다
#     reply     = 방에 물은 것·확인 요청 — 한 줄 답이 오면 닫히는 「회신 소통건」. 업무 SSOT 에 올릴 것이
#                 아니다(GM 2026-09-14 「업무 SSOT 에 올릴 건과 회신건은 많이 구분이 되어야」 · 「회신건들은
#                 최종 체크하고 삭제」) — 사람 목차에서 빼고 맨 아래 접힌 기록으로만 둔다.
KINDS = ("routine", "reception", "task", "reply")


def kind_of(it: dict) -> str:
    k = str(it.get("kind") or "").strip().lower()
    if k in KINDS:
        return k
    return "reception" if is_reception_item(it) else "task"


OWNER_BOARD_KEY = "MGR_TASK_OWNER"      # 목차에서 GM 이 지정한 담당(공용 보드) — 체크(MGR_TASK_DONE)와 같은 보드
BOARD_URL = ("https://script.google.com/macros/s/"
             "AKfycbyXw4ZaA6hLK567GC7NY33Y8SvNPW6kNtrXFz2OsSdFVBmCnZP-2oD-RQiX0IpekBu1/exec")


def fetch_owner_board() -> dict:
    """목차 화면에서 지정한 담당 — 다음 갱신 때 원장 owner 빈칸을 이 값으로 채운다.
    조회 실패면 빈 dict(담당 지정이 없던 것과 같게 — 지어내지 않는다)."""
    import urllib.request
    try:
        with urllib.request.urlopen(f"{BOARD_URL}?action=board&key={OWNER_BOARD_KEY}", timeout=30) as r:
            d = json.loads(r.read().decode("utf-8"))
        return d.get("board") or {} if d.get("ok") else {}
    except Exception:
        return {}


# ── ② 화면 청소 (GM 2026-09-11 "쓸데없는게 너무 많던데") ────────────────────────────────
#   원장 status 는 건드리지 않는다 — 사람이 답한 증거 없이 닫는 것은 금지. 화면에서만 가른다.
def find_dups(opens: dict[int, tuple[str, dict]]) -> dict[int, int]:
    """같은 일이 번호만 달리 두 줄로 있는 것 — {접을 옛 번호: 살릴 새 번호}.
    판정 근거 두 가지뿐: ① 제목이 다른 열린 번호를 (#NNN) 으로 가리킨다(사람이 손으로
    이어 적은 건) ② 제목 앞 24자가 0.72 이상 닮았다. 날짜가 뒤인 쪽을 살린다."""
    out: dict[int, int] = {}

    def mark(a: int, b: int) -> None:
        old, new = (a, b) if opens[a][0] <= opens[b][0] else (b, a)
        if old not in out and new not in out:
            out[old] = new

    for n, (_d, it) in opens.items():
        for m in re.finditer(r"[(（]#(\d+)[)）]", str(it.get("issue") or "")):
            t = int(m.group(1))
            if t != n and t in opens:
                mark(t, n)
    keys = sorted(opens)
    for i, n1 in enumerate(keys):
        for n2 in keys[i + 1:]:
            # ★담당이 다르면 같은 일이 아니다 (GM 지적 2026-09-14 「중복건들은 다 검토해서」).
            #   제목만 보던 판정이 「매출보고 임정은M 담당 4건 현황 회신」·「…윤병현AM 담당 2건…」·
            #   「…나우열M 담당 8건…」 세 사람 건을 한 건으로 접어, 두 사람 일이 화면에서 사라졌다.
            #   사람이 다르면 할 일도 다르다 — 제목이 닮아도 접지 않는다.
            o1 = str(opens[n1][1].get("owner") or "").strip()
            o2 = str(opens[n2][1].get("owner") or "").strip()
            if o1 and o2 and o1 != o2:
                continue
            k1, k2 = _title_key(opens[n1][1].get("issue")), _title_key(opens[n2][1].get("issue"))
            if k1 and k2 and difflib.SequenceMatcher(None, k1, k2).ratio() >= 0.72:
                mark(n1, n2)
    return out


# ── ③ 원장 note 청소 (GM 2026-09-11) ─────────────────────────────────────────────────
#   우리가 방에 보낸 공고문이 회신으로 잘못 쌓였다. 사람이 쓴 회신은 절대 안 지운다.
_OUR_NOTICE = ("한 줄이면 됩니다",            # 공고문 예시 문구
               "그 번호로 진행을 체크하고")    # 같은 공고문의 뒷부분(예시 괄호가 잘려 들어온 조각)


def is_our_echo(frag: str, issue: str) -> bool:
    """이 note 조각이 우리 발신인가. 「회신: #번호 + 그 건 자기 제목」도 우리 공고문이다 —
    사람은 자기가 답하는 건의 제목을 그대로 되풀이하지 않는다."""
    if any(w in frag for w in _OUR_NOTICE):
        return True
    m = re.match(r"회신:\s*#\d+\s+(.+)$", frag.strip(), re.S)
    if not m:
        return False
    title = _title_key(issue)
    return len(title) >= 10 and _title_key(m.group(1)).startswith(title[:10])


def clean_notes(dry: bool = True) -> int:
    """원장 note 에서 우리 발신 조각과 똑같이 겹친 조각을 걷어낸다. 고치는 유일한 원장 항목."""
    rows = json.loads(LEDGER.read_text(encoding="utf-8"))
    hit = 0
    for e in rows:
        for it in e.get("issues") or []:
            note = str(it.get("note") or "")
            if not note:
                continue
            issue = str(it.get("issue") or "")
            kept, dropped, saw = [], [], set()
            for f in (p.strip() for p in note.split(" · ")):
                if not f:
                    continue
                if is_our_echo(f, issue) or f in saw:
                    dropped.append(f)
                    continue
                saw.add(f)
                kept.append(f)
            if not dropped:
                continue
            hit += 1
            print(f'#{it.get("no")} {e.get("date")} {issue}')
            for f in dropped:
                print("   − " + f.replace("\n", " ")[:96])
            print("   ⇒ " + (" · ".join(kept).replace("\n", " ")[:130] or "(빈 값)"))
            if not dry:
                it["note"] = " · ".join(kept)
    if not dry:
        tmp = LEDGER.with_suffix(".tmp")
        tmp.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, LEDGER)
    print(f"[clean-notes] {'(미리보기) ' if dry else ''}{hit}건")
    return hit


def selfcheck() -> None:
    t = "수영장 타일 사이 오염 부분 청소 가능 여부"
    assert is_our_echo(f"회신: #149 {t} — 9/12", t)
    assert is_our_echo("회신: #174 키즈락커\n👉 회신·보고는 「#번호 + 했다」 한 줄이면 됩니다(예:", "키즈락커 짤순이")
    assert not is_our_echo('회신: 이정헌 소장 13:17 "#149 진행중(휴관일에 실리콘작업하기로 정함)"', t)
    assert not is_our_echo("회신: #149 진행중(휴관일에 실리콘작업하기로 정함)", t)
    assert not is_our_echo("회신: #163 했다", "에스컬레이터 정밀진단 소견서·견적서 접수(#163)")
    o = {1: ("2026-09-01", {"issue": "회원 접수 4건 처리 방향 미정"}),
         2: ("2026-09-07", {"issue": "회원 접수 4건 처리방향 미정(#1)"}),
         3: ("2026-09-05", {"issue": "에스컬레이터 견적"})}
    assert find_dups(o) == {1: 2}, find_dups(o)
    # ⚠ 놓친 것 — 기한 지난 것이 맨 위, 그다음 경과 긴 순 · 7일 미만·기한 안 지난 건은 안 잡힌다
    today = date.today()
    shown = [(1, (today - timedelta(days=3)).isoformat(), {"issue": "a", "due": (today - timedelta(days=1)).isoformat()}, "이정헌 소장"),
             (2, (today - timedelta(days=20)).isoformat(), {"issue": "b"}, "이경연 실장"),
             (3, (today - timedelta(days=2)).isoformat(), {"issue": "c"}, "나우열M"),
             (4, (today - timedelta(days=9)).isoformat(), {"issue": "d", "next_step": "견적 회신"}, "담당 미정")]
    assert [r[0] for r in missed_items(shown)] == [1, 2, 4], missed_items(shown)
    rm = row_model(7, (today - timedelta(days=3)).isoformat(),
                   {"issue": "네이버 계정 비밀번호 abc!2345678 전달", "note": "카톡 원문 010-1234-5678", "due": "2026-01-01"})
    assert rm["overdue"] and "note" not in rm and "[가림]" in rm["issue"] and "abc!2345678" not in rm["issue"]
    # 뼈대 렌더 — 스냅숏 인라인 · JS 가 6열 colgroup 으로 그린다 · 라이브 못 읽음 문구 존재
    page = render_page({"generated_at": "t", "today": "2026-09-15", "resp": {}, "people": [], "missed": [],
                        "line_out": [], "ai": [], "unassigned": [], "moved": [], "routine": [], "reply": [],
                        "counts": [], "total": 0, "missed_n": 0, "unassigned_n": 0, "oldest": 0, "stale": 0,
                        "rc_n": 0, "dup_n": 0, "ssot_ok": True, "owner_choices": [], "people_order": MGR_PEOPLE,
                        "next_step_missing": NEXT_STEP_MISSING})
    assert 'id="snap"' in page and "라이브 원장을 못 읽었습니다" in page and "DT_COLS" in page and "manager_ledger_snapshot.json" in page
    print("[selfcheck] 담당 드롭다운·중복 판정·note 청소·놓친 것·스냅숏 가림·뼈대 렌더 OK")


def approval_badge(m: dict) -> dict:
    """업무·결재 SSOT 행 하나의 진행·결재 상태 — 값이 없으면 안 지어낸다."""
    st = str(m.get("상태") or "").strip() or "상태없음"
    ap_req = str(m.get("결재요청") or "").strip()
    ap_st = str(m.get("결재상태") or "").strip()
    gm_sign = bool(str(m.get("GM싸인") or "").strip())
    rep_sign = bool(str(m.get("대표싸인") or "").strip())
    ap = ""
    if ap_st == "결재완료":
        who = "GM·대표" if (gm_sign and rep_sign) else ("GM" if gm_sign else "")
        ap = "done:결재완료" + ((" " + who) if who else "")
    elif ap_req:
        ap = "wait:결재대기 " + ap_req
    return {"st": st, "ap": ap}


def missed_items(shown: list) -> list:
    """⚠ 놓친 것 = 기한 지난 것 + 7일 넘게 원장에 기록 없는 것(종전 「먼저 볼 것」+「멈춘 것」 병합 ·
    GM 지시 2026-09-15). 기한 지난 것이 맨 위, 그다음 경과 긴 순. 돌려주는 값 = shown 과 같은 4-튜플."""
    out = [row for row in shown if is_overdue(row[2]) or days_since(row[1]) >= 7]
    out.sort(key=lambda x: (not is_overdue(x[2]), -days_since(x[1]), x[0]))
    return out


def build_model() -> dict:
    seen = latest_by_no()
    sales_data = fill_sales_current(seen)
    opens = {n: v for n, v in seen.items() if str(v[1].get("status", "")).lower() not in DONE}

    # 목차 화면에서 GM 이 지정한 담당을 원장 빈칸에 채운다(GM 2026-09-10 "SSOT 등록건은 담당자도
    #   설정할 수 있어야해"). 원장에 이미 사람이 적혀 있으면 그 값이 먼저다 — 화면 입력이 실무진
    #   회신으로 들어온 담당을 덮지 않는다.
    owner_board = fetch_owner_board()
    if owner_board:
        for n, (d, it) in opens.items():
            picked = str(owner_board.get(f"mgr-{n}") or "").strip()
            if picked and not str(it.get("owner") or "").strip():
                it["owner"] = picked

    ssot_rows = fetch_ssot_rows()
    ssot_ok = ssot_rows is not None
    resp_model, _hist = resp_section(seen, ssot_rows, sales_data)   # 👤 책임 3인(원장 이번 달 키 갱신 포함)
    moved: list[tuple[int, str, dict, dict, str]] = []  # (no, date, it, ssot_row, matched_by) — 업무 SSOT 로 넘어간 것
    if ssot_ok:
        # 번호가 유사도보다 먼저다(GM 규칙) — 원장 todo_id 가 있으면 그 id 로 바로 맞춘다.
        by_id = {str(r.get("id")): r for r in ssot_rows if r.get("id")}
        remain = {}
        for n, (d, it) in opens.items():
            todo_id = str(it.get("todo_id") or "").strip()
            m = by_id.get(todo_id) if todo_id else None
            matched_by = "id" if m else ""
            if not m:
                m = find_ssot_match(str(it.get("issue") or ""), ssot_rows)
                matched_by = "title" if m else ""
            if m:
                moved.append((n, d, it, m, matched_by))
            else:
                remain[n] = (d, it)
        opens = remain

    # ② 열린 목록에서 가를 것 넷 — 원장은 그대로 두고 화면에서만 가른다.
    dup_of = find_dups(opens)
    aside_dup = [(n, *opens.pop(n)) for n in sorted(dup_of)]
    aside_rt = [(n, *opens.pop(n)) for n in sorted(n for n, (_d, it) in opens.items()
                                                   if kind_of(it) == "routine")]
    aside_rc = [(n, *opens.pop(n)) for n in sorted(n for n, (_d, it) in opens.items()
                                                   if kind_of(it) == "reception")]
    aside_reply = [(n, *opens.pop(n)) for n in sorted(n for n, (_d, it) in opens.items()
                                                      if kind_of(it) == "reply")]
    # AI 판정 건(owner="AI …")은 사람 목차에서 빼고 한 줄로만 보인다(GM 지시 2026-09-14).
    ai_items = [(n, *opens.pop(n)) for n in sorted(n for n, (_d, it) in opens.items()
                                                   if is_ai_owner(it.get("owner")))]

    def ssot_missing(it: dict) -> bool:
        return not str(it.get("todo_id") or "").strip() and not is_reception_item(it)

    def pop_team(team: list[str]) -> dict[str, list]:
        """team 이름이 owner 안에 든 건을 opens 에서 꺼내 사람별로 묶는다("윤병현AM · 백승화 사원"
        같은 복합 담당도 양쪽 다 걸린다)."""
        out: dict[str, list] = {}
        for n in sorted(opens):
            owner = str(opens[n][1].get("owner") or "").strip()
            hit = next((p for p in team if p in owner), None)
            if hit:
                d, it = opens.pop(n)
                out.setdefault(hit, []).append((n, d, it))
        return out

    counts = []  # (표시이름, 총건수, SSOT 미등록건수)
    shown: list[tuple[int, str, dict, str]] = []
    TEAM_BY_NAME = {"이경연 실장": (OPS_TEAM, "운영부 담당자 건", "실장이 함께 체크하는"),
                    "이정헌 소장": (FACILITY_TEAM, "시설부 담당자 건", "소장이 함께 체크하는")}
    people = []
    for name, dept, room in MANAGERS:
        mine = sorted(((n, d, it) for n, (d, it) in opens.items()
                       if str(it.get("owner") or "").strip() == name), key=lambda x: x[0])
        for n, _d, _it in mine:
            opens.pop(n)
        team = TEAM_BY_NAME.get(name)
        team_groups = pop_team(team[0]) if team else {}
        team_rows = sorted((row for rows in team_groups.values() for row in rows), key=lambda x: x[0])
        person_rows = mine + team_rows
        shown += [(n, d, it, name) for n, d, it in person_rows]
        counts.append((name, len(person_rows), sum(1 for _n, _d, it in person_rows if ssot_missing(it))))
        people.append({"name": name, "dept": dept, "room": room,
                       "mine": [row_model(n, d, it) for n, d, it in mine],
                       "team_title": team[1] if team else "", "team_lead": team[2] if team else "",
                       # 사람 순서 = 명단(OPS_TEAM·FACILITY_TEAM) 순서 — GM 지시 2026-09-14
                       "team": [{"who": p_, "rows": [row_model(n, d, it) for n, d, it in sorted(team_groups[p_])]}
                                for p_ in (team[0] if team else []) if p_ in team_groups]})

    line_out = sorted(((n, d, it) for n, (d, it) in opens.items()
                       if str(it.get("owner") or "").strip()), key=lambda x: x[0])
    for n, _d, _it in line_out:
        opens.pop(n)
    shown += [(n, d, it, str(it.get("owner") or "").strip()) for n, d, it in line_out]
    unassigned = sorted(((n, d, it) for n, (d, it) in opens.items()
                         if not str(it.get("owner") or "").strip()), key=lambda x: x[0])
    shown += [(n, d, it, "담당 미정") for n, d, it in unassigned]
    buckets: dict[str, list] = {k: [] for k in [g[0] for g in GROUPS] + ["기타"]}
    for n, d, it in unassigned:
        buckets[group_of(it)].append(row_model(n, d, it))

    def by_owner(rows_, order_):
        by: dict[str, list] = {}
        for n, d, it in rows_:
            by.setdefault(str(it.get("owner") or "담당 미정").strip() or "담당 미정", []).append(row_model(n, d, it))
        names = [w for w in order_ if w in by] + [w for w in by if w not in order_]
        return [{"who": w, "rows": by[w]} for w in names]

    missed = missed_items(shown)
    mm: dict[str, list] = {}
    for no, d, it, who in missed:
        mm.setdefault(who, []).append(row_model(no, d, it))
    m_order = MGR_PEOPLE + [w for w in mm if w not in MGR_PEOPLE and w != "담당 미정"] + ["담당 미정"]
    return {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"), "today": date.today().isoformat(),
        "ssot_ok": ssot_ok, "owner_choices": OWNER_CHOICES, "next_step_missing": NEXT_STEP_MISSING,
        "resp": resp_model, "people_order": MGR_PEOPLE,
        "missed": [{"who": w, "rows": mm[w]} for w in m_order if w in mm],
        "people": people,
        "line_out": [row_model(n, d, it) for n, d, it in line_out],
        "ai": [{"no": n, "issue": _mask(str(it.get("issue") or ""))} for n, _d, it in ai_items],
        "unassigned": [{"group": k, "rows": v} for k, v in buckets.items() if v],
        "moved": [{"no": no, "issue": _mask(str(it.get("issue") or "")), "ssot_id": str(m.get("id") or ""),
                   "ssot_title": str(m.get("업무명") or ""), "by": matched_by, **approval_badge(m)}
                  for no, d, it, m, matched_by in sorted(moved, key=lambda x: x[0])],
        "routine": by_owner(aside_rt, [m_[0] for m_ in MANAGERS]),
        "reply": by_owner(aside_reply, [m_[0] for m_ in MANAGERS] + OPS_TEAM + FACILITY_TEAM),
        "counts": counts, "total": len(shown), "missed_n": len(missed), "unassigned_n": len(unassigned),
        "oldest": max((days_since(d) for _, d, _, _ in shown), default=0),
        "stale": sum(1 for _, d, _, _ in shown if days_since(d) >= 14),
        "rc_n": len(aside_rc), "dup_n": len(aside_dup),
    }


SNAP_PATH = ROOT / "status" / "manager_ledger_snapshot.json"


def save_snapshot(model: dict) -> None:
    """공개 가능한 스냅숏(GM 지시 2026-09-15 ⑦ 라이브) — 화면이 열 때마다 /repo/ 로 fetch 한다. 사람 이름·번호·제목·
    상태·기한·next_step·경과일만 · 카톡 원문·전화·비밀값 없음(row_model 이 note 를 싣지 않고 원문 칸은 _mask)."""
    SNAP_PATH.write_text(json.dumps({"_doc": "중간관리자 업무 화면 라이브 스냅숏 — manager_task_index.build_model() 이 쓴다. "
                                             "손으로 고치지 않는다. 카톡 원문·비밀값을 싣지 않는다.", **model},
                                    ensure_ascii=False, indent=1), encoding="utf-8")


def build() -> str:
    model = build_model()
    save_snapshot(model)
    # 인라인 정적본 폴백용으로만 이번 분기 3인 실측 달 키를 싣는다(공개 스냅숏 파일에는 안 싣는다 — 원장 하나가 정본).
    try:
        months = json.loads(HIST_PATH.read_text(encoding="utf-8")).get("months") or {}
    except Exception:
        months = {}
    t = date.today()
    q0 = 3 * ((t.month - 1) // 3) + 1
    keys = [f"{t.year}-{m:02d}" for m in range(q0, q0 + 3)]
    model = dict(model, _hist={"months": {k: {p_: v for p_, v in (months.get(k) or {}).items() if p_ in MGR_PEOPLE} for k in keys if k in months}})
    return render_page(model)


def render_page(model: dict) -> str:
    """뼈대(HTML 틀 + CSS + JS) — 값은 JS 가 그린다. 인라인 스냅숏은 라이브 원장을 못 읽을 때(Pages·로컬 파일)의
    정적본 폴백이며, 그때는 화면에 「라이브 원장을 못 읽었습니다 — 정적본」이라 적는다(0 이 아님)."""
    payload = json.dumps(model, ensure_ascii=False).replace("</", "<\\/")
    return PAGE_TEMPLATE.replace("__SNAP__", payload)


PAGE_TEMPLATE = r'''<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>중간관리자 업무</title>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;700;900&family=Noto+Serif+KR:wght@700&display=swap" rel="stylesheet">
<style>
  * { box-sizing:border-box; margin:0; padding:0; }
  :root { --ink:#101418; --navy:#14304E; --navy-bg:#EDF1F6; --line:#E3E7EB; --dim:#6B7683; --warn:#96601A; --bad:#9E2A2A; }
  body { font-family:'Noto Sans KR',sans-serif; color:var(--ink); background:#F4F6F8; padding:22px 18px 60px; }
  .wrap { max-width:100%; margin:0; }
  h1 { font-family:'Noto Serif KR',serif; font-size:27px; letter-spacing:-.6px; }
  .lede { margin-top:6px; color:var(--dim); font-size:14px; line-height:1.7; }
  .bar { margin-top:14px; background:var(--navy); color:#fff; padding:10px 14px; font-size:14px; font-weight:700; line-height:1.6; }
  .bar .b2 { display:block; font-weight:400; font-size:13px; opacity:.85; }
  .blk { background:#fff; border:1px solid var(--line); margin-top:14px; }
  /* 사람별 업무 표 — 같은 열 폭(colgroup·fixed) · 첫 칸은 블록 선에서 14px 띄운다(GM 지적 2026-09-16) */
  table.tk { table-layout:fixed; }
  table.tk col.own { width:120px; } table.tk col.nx { width:190px; } table.tk col.ss { width:112px; }
  table.tk th:first-child, table.tk td:first-child { padding-left:14px; }
  table.tk th:last-child, table.tk td:last-child { padding-right:14px; }
  table.tk td { overflow-wrap:anywhere; }
  .blk h3.rsp { padding-left:14px; }
  h2 { font-size:16px; padding:10px 14px; background:var(--navy-bg); color:var(--navy); border-bottom:1px solid var(--line); }
  h2 .sub { font-weight:400; color:var(--dim); font-size:13px; margin-left:8px; }
  /* 👤 책임 항목 4인(GM 지시 2026-09-14) — .blk·table 결 그대로, 칸 너비만 추가 */
  section.resp, details.resp-q { background:#fff; border:1px solid var(--line); margin-top:14px; }
  section.resp > h2, section.resp-q > h2 { background:var(--navy); color:#fff; }
  /* 📅 분기 누적(GM 지시 2026-09-15) — 같은 .resp-tb, 달 칸(rq)만 추가 */
  details.resp-q > summary .sub { color:#fff; opacity:.8; font-weight:400; font-size:13px; margin-left:8px; }
  details.resp-q th.rq, details.resp-q td.rq { width:16%; font-size:13px; }
  details.resp-q td.rq.bad { color:var(--bad); font-weight:700; }
  details.resp-q details > summary { padding:9px 14px; cursor:pointer; color:var(--navy); font-weight:700; border-top:1px solid var(--line); }
  .rp-person { border-top:1px solid var(--line); }
  .rp-person:first-child { border-top:0; }
  .rp-person h3 { padding:9px 14px; font-size:14.5px; color:var(--navy); background:var(--navy-bg); }
  table.resp-tb th.ri, table.resp-tb td.ri { width:15%; font-weight:700; }
  table.resp-tb th.rc, table.resp-tb td.rc { width:24%; color:var(--dim); font-size:13px; }
  table.resp-tb th.rp, table.resp-tb td.rp { width:26%; }
  table.resp-tb td.rp.bad { color:var(--bad); font-weight:700; }
  table.resp-tb th.rg, table.resp-tb td.rg,
  table.resp-tb th.rf, table.resp-tb td.rf { width:17.5%; font-size:13px; }
  /* 실장 행 토글 — 종합접수처·점검 현황 행을 누르면 바로 아래 tr 에 내역(GM 지시 2026-09-14) */
  tr.rp-toggle { cursor:pointer; }
  tr.rp-toggle:hover { background:var(--navy-bg); }
  tr.rp-toggle .rp-arrow { color:var(--dim); }
  tr.rp-detail td { padding:0; background:#FAFBFC; }
  tr.rp-detail table { margin:0; }
  table { width:100%; border-collapse:collapse; font-size:14px; }
  th, td { padding:8px 10px; border-bottom:1px solid var(--line); vertical-align:top; text-align:left; }
  th { background:#FAFBFC; font-size:12.5px; color:var(--dim); font-weight:700; }
  td.ck, th.ck { width:34px; text-align:center; }
  td.no, th.no { width:62px; color:var(--dim); font-weight:700; }
  td.due, th.due { width:104px; }
  td.age, th.age { width:64px; text-align:right; color:var(--dim); font-variant-numeric:tabular-nums; }
  td.age.warn { color:var(--warn); font-weight:700; }
  td.age.old { color:var(--bad); font-weight:900; }
  td.note { color:var(--dim); }
  /* 진척 칸·함께 하는 사람·책임 사람머리 (GM 지시 2026-09-11) */
  td.pg, th.pg { width:132px; }
  th.pg { display:table-cell; }   /* 아래 .pg flex 규칙이 머리칸까지 먹어 머리행 배경이 끊기던 것 */
  /* ★막대가 찔끔 나오던 것 (GM 지적 2026-09-14 「30%인데 그래프가 찔끔?」).
     .bar 가 span 이라 기본이 inline 이었다 — inline 은 height·width 가 안 먹어 트랙이
     내용 폭(=0)으로 접혔고, 그 0 의 30% 라 막대가 점처럼 보였다. 블록으로 펴고 폭을 준다. */
  /* ★한 줄 + 채움 (GM 지적 2026-09-14 「한 줄로 %랑 같이 · 올 회색이 아니라 41%만큼 색칠」).
     위 .bar(머리 검정 띠) 규칙의 padding·line-height 가 이 트랙에도 먹어 트랙이 20px 로 부풀고
     채움(i)은 내용 높이 0 의 100% = 0px 라 안 보였다 — 트랙·채움 높이를 px 로 못 박고 padding 을 지운다. */
  /* ★td.pg 는 표 칸으로 남긴다(GM 지적 2026-09-16 「진척칸이 또 깨져있네」) — 종전 .pg{display:flex} 가
     td.pg 에도 먹어 칸이 표 격자에서 떨어져 나가 선이 끊기고 옆 표와 열이 안 맞았다. flex 는 책임 표 안
     span.pg 에만, td.pg 안 막대는 inline-block 으로 한 줄. */
  span.pg { display:flex; align-items:center; gap:8px; white-space:nowrap; }
  td.pg { display:table-cell; white-space:nowrap; }
  td.pg .bar { display:inline-block; width:72px; vertical-align:middle; margin-right:6px; }
  .pg .bar { display:block; flex:1 1 80px; min-width:60px; max-width:180px; height:8px; padding:0; margin:0;
             line-height:0; border-radius:4px; background:var(--line); overflow:hidden; }
  .pg .bar i { display:block; height:8px; }
  .pg .pg-low { background:var(--bad); }
  .pg .pg-mid { background:var(--warn); }
  .pg .pg-ok { background:#2e7d32; }
  .pg .pgn { font-size:11.5px; font-weight:800; margin-right:6px; }
  .pg .pgt { font-size:11px; color:var(--dim); }
  /* 👤 책임 항목 표 안 매출 진척(span.pg) — td.pg(#132px 고정폭) 재사용, 이 칸은 폭 자유 */
  td.rp .pg { display:flex; }
  td.rp .pg .pgt { display:inline; margin:0; }
  td.own .with { font-size:11.5px; color:var(--dim); margin-top:3px; }
  h3.rsp { margin:16px 0 6px; font-size:14px; font-weight:800; }
  h3.rsp .gc { font-size:12px; font-weight:600; color:var(--dim); margin-left:6px; }
  .cat { display:inline-block; margin-left:6px; font-size:11.5px; color:var(--dim); border:1px solid var(--line); padding:0 5px; }
  tr.done td.ti { text-decoration:line-through; color:var(--dim); }
  .empty { color:var(--dim); }
  /* 먼저 볼 것 */
  .top { background:#fff; border:1px solid var(--line); border-left:4px solid var(--bad); margin-top:14px; padding:12px 14px 14px; }
  .top h2 { background:none; border:0; padding:0 0 8px; font-size:16px; }
  .top .why { color:var(--dim); font-size:13px; font-weight:400; margin-left:8px; }
  .top-i { display:flex; gap:12px; align-items:baseline; padding:7px 0; border-top:1px solid var(--line); }
  .top-age { flex:0 0 58px; text-align:right; font-size:16px; font-weight:900; color:var(--dim); font-variant-numeric:tabular-nums; }
  .top-age.warn { color:var(--warn); }
  .top-age.old { color:var(--bad); }
  .top-b { flex:1 1 auto; min-width:0; }
  .top-b b { font-size:15px; }
  .top-w { color:var(--dim); font-size:13px; margin-top:2px; }
  .fl { display:inline-block; margin-left:6px; font-size:11.5px; font-weight:700; color:var(--bad); border:1px solid var(--bad); padding:0 5px; vertical-align:middle; }
  /* 담당 미정 성격별 묶음 */
  .grps { padding:6px 0; }
  .grp { border-bottom:1px solid var(--line); }
  .grp > summary { cursor:pointer; padding:9px 14px; font-size:14px; font-weight:700; color:var(--navy); list-style:none; }
  .grp > summary::-webkit-details-marker { display:none; }
  .grp > summary::before { content:"▸ "; color:var(--dim); }
  .grp[open] > summary::before { content:"▾ "; }
  .grp .gc { font-weight:400; color:var(--dim); font-size:13px; margin-left:6px; }
  .grp .gw { font-weight:400; color:var(--dim); font-size:12.5px; margin-left:6px; }
  /* 실장 건별 목록 3종(GM 지시 2026-09-14) — .grp details 재사용, 맨 아래 안내줄만 추가 */
  .sub-note { padding:6px 14px 10px; font-size:12.5px; color:var(--dim); border-top:1px solid var(--line); }
  .own { white-space:nowrap; }
  .own-sel { max-width:118px; padding:3px 4px; border:1px solid var(--line); border-radius:6px;
              background:#fff; color:inherit; font:inherit; font-size:12.5px; }
  .own-sel:focus { outline:2px solid rgba(183,159,138,0.5); }
  .own-sel.saved { border-color:#6abf7b; }
  .ss-rc { display:inline-block; padding:1px 6px; border-radius:6px; font-size:11.5px;
            background:rgba(255,255,255,0.08); color:var(--dim); }
  .ss { white-space:nowrap; }
  .ss-no { display:inline-block; padding:1px 6px; border-radius:6px; font-size:11.5px;
            background:rgba(237,91,63,0.14); color:#ED5B3F; }
  .ss-link { display:inline-block; padding:1px 6px; border-radius:6px; font-size:11.5px;
              background:rgba(255,255,255,0.08); color:inherit; text-decoration:underline dotted; }
  /* 문서 링크 줄 — 업무명·카드명 아래 📄 기획안 · 🎯 결과보고 · 📎 첨부 */
  .dcs { margin-top:3px; display:flex; flex-wrap:wrap; gap:4px; }
  .dc { display:inline-block; padding:1px 6px; border-radius:6px; font-size:11.5px;
         background:rgba(255,255,255,0.08); color:var(--dim); text-decoration:none; }
  .dc:hover { color:inherit; text-decoration:underline; }
  .ss-st { display:inline-block; padding:1px 6px; border-radius:6px; font-size:11.5px;
            background:rgba(255,255,255,0.08); color:var(--dim); margin-right:4px; }
  .ss-ap { display:inline-block; padding:1px 6px; border-radius:6px; font-size:11.5px; }
  .ss-ap.done { background:rgba(106,191,123,0.16); color:#6abf7b; }
  .ss-ap.wait { background:rgba(230,200,78,0.16); color:#e6c84e; }
  .mvlist { list-style:none; padding:2px 14px 10px; }
  .mvlist li { padding:5px 0; font-size:13.5px; border-top:1px solid var(--line); }
  .mvlist li:first-child { border-top:0; }
  .mvd { display:block; color:var(--dim); font-size:12.5px; margin-top:2px; }
  .mvd-link { color:inherit; text-decoration:underline dotted; }
  .mvd-id { color:#888; font-size:.85em; margin-left:.4em; }
  .bar .fail { color:#FFD37A; }
  .foot { margin-top:16px; color:var(--dim); font-size:13px; line-height:1.8; }
  @media (max-width:640px) {
    body { padding:16px 10px 50px; }
    h1 { font-size:21px; }
    table { font-size:13px; }
    th, td { padding:6px 6px; }
    td.due, th.due { width:72px; }
    td.no, th.no { width:46px; }
    td.age, th.age { width:48px; }
    /* 좁은 폭에서 표를 억지로 구겨 넣지 않는다 — 블록만 옆으로 밀어서 본다. */
    .blk { overflow-x:auto; }
    .blk table { min-width:620px; }
    .top-age { flex:0 0 46px; font-size:15px; }
  }
  /* A3 요약본(인쇄+PNG) — GM업무.html 과 같은 버튼 3개(GM 지시 2026-09-15). 제목 줄 오른쪽에 상시 노출,
     별도 배지·설명문은 안 둔다. */
  @page { size: A3 portrait; margin: 12mm; }
  .h1row{display:flex;align-items:baseline;gap:14px;flex-wrap:wrap;}
  .a3bar{display:flex;gap:8px;flex-wrap:wrap;margin-left:auto;}
  .a3bar button{font-family:inherit;font-size:12.5px;font-weight:700;color:#fff;cursor:pointer;
    background:var(--navy);border:1px solid var(--navy);border-radius:99px;padding:5px 13px;}
  .a3bar button:hover{opacity:.85;}
  .a3bar button:disabled{opacity:.5;cursor:default;}
  /* 사람별 A3 요약본 막대 — GM업무.html .mapbar 와 같은 구성 */
  .mapbar{position:sticky;top:0;z-index:20;display:flex;align-items:center;gap:8px;flex-wrap:wrap;
    background:var(--navy);color:#fff;padding:8px 14px;margin:-22px -18px 14px;font-size:13px;}
  .mapbar .t{flex:1 1 auto;font-weight:700;}
  .mapbar button{font-family:inherit;font-size:12.5px;font-weight:700;color:var(--navy);background:#fff;border:0;border-radius:99px;padding:5px 13px;cursor:pointer;}
  .mapbar button.x{background:transparent;color:#fff;border:1px solid rgba(255,255,255,.6);}
  .a3-hide{display:none !important;}
  body[data-a3] .pr-skip, body[data-a3] .cur-h{display:none !important;}
  /* 사람 블록 「🖨 A3 요약본」 버튼 — GM업무.html .sec-act 와 같은 규격(알약·테두리 1px·12.5px·700) */
  h2 .sec-act{font-family:inherit;font-size:12.5px;font-weight:700;color:var(--navy);background:#fff;cursor:pointer;
    border:1px solid var(--navy);border-radius:99px;padding:3px 11px;margin-left:auto;white-space:nowrap;}
  h2 .sec-act:hover{background:var(--navy);color:#fff;}
  .blk > h2{display:flex;align-items:center;gap:8px;flex-wrap:wrap;}
  h2.cur-h{margin-top:18px;background:var(--navy);color:#fff;border:1px solid var(--navy);}
  h2.cur-h .sub{color:#fff;opacity:.8;}
  /* ⚠ 놓친 것 — 사람별 묶음 */
  .top-who{margin-top:6px;}
  .top-who h3{font-size:14px;font-weight:800;color:var(--navy);margin:8px 0 2px;}
  .top-who h3 .gc{font-size:12px;font-weight:600;color:var(--dim);margin-left:6px;}
  /* 다음 한 걸음 칸(체크리스트 대신) */
  td.nx, th.nx{width:190px;font-size:13px;}
  .nx-none{color:var(--warn);}
  .nx-reply{font-size:11px;color:var(--dim);margin-top:2px;}
  td.due.old{color:var(--bad);font-weight:800;}
  /* 토글 상세표 공통 6열(colgroup + table-layout:fixed) — 세 표가 같은 열 폭 · 번호 칸은 표 안 첫 칸 */
  table.dt{table-layout:fixed;width:100%;}
  table.dt col.dt-no{width:150px;} table.dt col.dt-who{width:150px;} table.dt col.dt-due{width:104px;}
  table.dt col.dt-age{width:70px;} table.dt col.dt-etc{width:220px;}
  table.dt th, table.dt td{overflow:hidden;text-overflow:ellipsis;}
  table.dt th.dt-no, table.dt td.dt-no{padding-left:24px;color:var(--dim);font-weight:700;white-space:nowrap;}
  table.dt td.dt-age .age{font-variant-numeric:tabular-nums;} table.dt td.dt-age .age.warn{color:var(--warn);font-weight:700;}
  table.dt td.dt-age .age.old{color:var(--bad);font-weight:900;}
  /* 📅 분기 누적 — 접힌 details */
  details.resp-q > summary{list-style:none;cursor:pointer;font-size:16px;font-weight:700;padding:10px 14px;background:var(--navy);color:#fff;}
  details.resp-q > summary::-webkit-details-marker{display:none;}
  details.resp-q > summary::before{content:"▸ ";opacity:.8;}
  details.resp-q[open] > summary::before{content:"▾ ";}
  @media print{
    .a3bar,.mapbar{display:none !important;}
    body{padding:0;}
    .wrap{max-width:100%;}
    section.resp,.top,.blk,.top-who{break-inside:avoid;}
    .pr-skip{display:none !important;}
  }
  /* ⑦ 라이브(GM 지시 2026-09-15) — 상태 줄 · 지난달 대비 칸 */
  .live{margin-top:8px;font-size:12.5px;color:var(--dim);}
  .live.off{color:var(--bad);font-weight:700;}
  table.resp-tb th.rd, table.resp-tb td.rd{width:9%;font-size:12.5px;white-space:nowrap;}
  .rd .up{color:#2e7d32;font-weight:800;} .rd .dn{color:var(--bad);font-weight:800;}
  table.resp-tb th.ri, table.resp-tb td.ri{width:14%;}
  table.resp-tb th.rc, table.resp-tb td.rc{width:21%;}
  table.resp-tb th.rp, table.resp-tb td.rp{width:24%;}
  table.resp-tb th.rg, table.resp-tb td.rg, table.resp-tb th.rf, table.resp-tb td.rf{width:16%;}
  /* 📅 분기 누적 열 밸런스(GM 지시 2026-09-16) — 책임 표(section.resp)는 위 generic 폭 그대로,
     여기 details.resp-q 로 이름 붙은 것만 덮어쓴다(항목12·달×3=16·분기합7·잘한것16.5·보완할것16.5). */
  details.resp-q th.ri, details.resp-q td.ri{width:12%;}
  details.resp-q th.rq, details.resp-q td.rq{width:16%;font-size:13px;}
  details.resp-q th.rs, details.resp-q td.rs{width:7%;font-size:13px;}
  details.resp-q th.rg, details.resp-q td.rg, details.resp-q th.rf, details.resp-q td.rf{width:16.5%;font-size:13px;}
  .rq-back{display:inline-block;margin-left:4px;padding:0 4px;border-radius:3px;background:var(--navy-bg);color:var(--navy);font-size:10px;font-weight:700;vertical-align:middle;}
  td.nx, th.nx{width:190px;font-size:13px;}
</style>
</head>
<body>
<div class="mapbar" id="mapbar" style="display:none;">
  <span class="t">🖨 A3 요약본 — <b id="a3name"></b> · 책임 항목 + 놓친 것 + 현재 업무만 인쇄·저장됩니다</span>
  <button type="button" onclick="printA3('landscape');">🖨 A3 가로 인쇄</button>
  <button type="button" onclick="printA3('portrait');">🖨 A3 세로 인쇄</button>
  <button type="button" id="mgr-png-btn" onclick="saveMapPng(this);">🖼 PNG 다운로드</button>
  <button type="button" class="x" onclick="closePersonA3();">✕ 닫기</button>
</div>
<div class="wrap">
  <div class="h1row">
    <h1>중간관리자 업무 목차</h1>
    <div class="a3bar">
      <button type="button" onclick="openQuarter();">📅 분기 누적 책임항목 평가</button>
    </div>
  </div>
  <div class="lede">이경연 실장 · 이정헌 소장 · 나우열M 세 사람의 <b>열린 업무</b>를 번호순으로 편 목차입니다.
    회신은 번호로 받습니다 — 「#번호 + 했다/진행중/언제」 한 줄.<br>
    회신이 오면 원장이 닫히고 이 화면이 바로 다시 만들어집니다(체크리스트 없음) · 열 때마다 원장을 새로 읽습니다.</div>
  <div class="live" id="live">원장을 읽는 중…</div>
  <div class="bar" id="bar"></div>

  <section class="resp" id="resp"></section>
  <div class="top" id="missed"></div>
  <h2 class="cur-h">📋 현재 업무 <span class="sub">사람별 · 번호순 · 담당 칸은 GM 이 바꿀 수 있습니다</span></h2>
  <div id="cur"></div>
  <details class="resp-q pr-skip" id="resp-q"><summary>📅 분기 누적 책임항목 평가 <span class="sub" id="rq-sub"></span></summary><div id="rq"></div></details>
  <div class="foot">
    <b>이 목록은 무엇인가</b><br>
    ① 값은 매일 아침 카카오·텔레그램 방을 정리해 쌓는 원장(<code>_digest_ledger.json</code>)에서 옵니다 — 이 화면은 그 공개 스냅숏(<code>status/manager_ledger_snapshot.json</code>)과 평가 원장 두 개(<code>manager_eval_history.json</code>·<code>manager_eval.json</code>)를 열 때마다 읽어 그립니다.<br>
    ② 번호(#)는 건마다 처음 잡힌 그대로 고정입니다 — 목록이 바뀌어도 번호는 안 바뀌므로 그 번호로 이야기하시면 됩니다.<br>
    ③ 회신은 번호로 붙습니다 — 실무진이 방에 「#번호 + 했다」로 답하면 그 건이 닫히고 스냅숏이 다시 저장·배포됩니다(1분 안) · 답이 없으면 07:50 통에 「N일째」로 다시 실립니다.<br>
    ④ 「다음 한 걸음」은 원장 next_step 칸입니다 — 비어 있으면 담당이 한 줄로 채웁니다(지어 넣지 않습니다).<br>
    ⑤ 책임 항목 「지난달 대비」는 평가 원장의 달별 스냅숏(말일 21:00 마감 실측)끼리 비교합니다 · 잘한 것/보완할 것은 GM·웰리가 manager_eval.json 에 적는 그대로입니다.<br>
    갱신 = <code>python scripts/manager_task_index.py --publish</code> · 경과 색 = 14일 이상 빨강 · 7~13일 주황.
  </div>
</div>
<script id="snap" type="application/json">__SNAP__</script>
<script>
(function () {
  'use strict';
  var INLINE = JSON.parse(document.getElementById('snap').textContent || '{}');
  var ERP_API_ON = /^(erp[.]wellperion[.]com|15[.]164[.]151[.]105)$/.test(location.hostname);
  var RAW_BASE = '/repo/';   // GM업무 A3 정본과 같은 방식 — erp 도메인에서만 값이 붙는다
  var DT_COLS = [['번호', 'dt-no'], ['내용', 'dt-ti'], ['담당·전달', 'dt-who'], ['기한', 'dt-due'], ['경과', 'dt-age'], ['비고', 'dt-etc']];
  var COLG = '<colgroup><col class="no"><col><col class="own"><col class="due"><col class="nx"><col class="pg"><col class="ss"><col class="age"></colgroup>';
  var HEAD_ROW = '<tr><th class="no">번호</th><th>업무</th><th class="own">담당</th><th class="due">기한</th><th class="nx">다음 한 걸음</th><th class="pg">진척</th><th class="ss">업무·결재 SSOT</th><th class="age">경과</th></tr>';
  var SSOT_PAGE = '../todo/업무 현황 SSOT.html';
  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }
  function ageCls(a) { return a >= 14 ? 'old' : (a >= 7 ? 'warn' : ''); }
  function fmtAmt(v, unit) {
    var n = parseInt(v, 10); if (isNaN(n)) return v + unit;
    if (unit !== '원') return n.toLocaleString() + unit;
    if (n >= 100000000) { var eok = Math.floor(n / 100000000), man = Math.floor((n % 100000000) / 10000); return eok + '억' + (man ? ' ' + man.toLocaleString() + '만' : ''); }
    return n >= 10000 ? Math.floor(n / 10000).toLocaleString() + '만' : n.toLocaleString() + '원';
  }
  function fetchJson(rel) {
    return fetch(RAW_BASE + rel + '?cb=' + Date.now(), { cache: 'no-store' }).then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); });
  }

  // ── 행(현재 업무) ──────────────────────────────────────────────────────────────
  function ownerSelect(r) {
    var opts = ['<option value="">— 미지정 —</option>'].concat((M.owner_choices || []).map(function (n) { return '<option value="' + esc(n) + '"' + (n === r.owner ? ' selected' : '') + '>' + esc(n) + '</option>'; }));
    if (r.owner && (M.owner_choices || []).indexOf(r.owner) < 0) opts.push('<option value="' + esc(r.owner) + '" selected>' + esc(r.owner) + '</option>');
    return '<select class="own-sel" data-o="' + r.no + '">' + opts.join('') + '</select>';
  }
  function progressCell(r) {
    if (!r.target) return '<td class="pg">—</td>';
    var pct = Math.max(0, Math.min(100, Math.round((parseInt(r.current, 10) || 0) / parseInt(r.target, 10) * 100)));
    if (isNaN(pct)) return '<td class="pg">—</td>';
    var cls = pct >= 80 ? 'pg-ok' : (pct >= 40 ? 'pg-mid' : 'pg-low');
    return '<td class="pg" title="' + esc(fmtAmt(r.current, r.unit) + ' / ' + fmtAmt(r.target, r.unit)) + '"><div class="bar"><i class="' + cls + '" style="width:' + pct + '%"></i></div><span class="pgn">' + pct + '%</span><span class="pgt">' + esc(fmtAmt(r.current, r.unit) + ' / ' + fmtAmt(r.target, r.unit)) + '</span></td>';
  }
  function ssCell(r) {
    if (r.ss === 'ssot') return '<a class="ss-link" href="' + SSOT_PAGE + '?item=' + encodeURIComponent(r.todo_id) + '" target="_blank" rel="noopener">SSOT 열기</a>';
    if (r.ss === 'reception') return '<span class="ss-rc">접수처에서 닫음</span>';
    if (r.ss === 'reply') return '<span class="ss-rc">회신으로 닫힘</span>';
    return '<span class="ss-no">SSOT 미등록</span>';
  }
  function nextStep(r) {
    return (r.next_step ? esc(r.next_step) : '<span class="nx-none">' + esc(M.next_step_missing) + '</span>') + '<div class="nx-reply">회신 「#' + r.no + ' 했다」 한 줄이면 닫힘</div>';
  }
  function rowHtml(r) {
    return '<tr data-no="' + r.no + '"><td class="no">#' + r.no + '</td><td class="ti">' + esc(r.issue) + (r.cat ? '<span class="cat">' + esc(r.cat) + '</span>' : '') + '</td>' +
      '<td class="own">' + ownerSelect(r) + (r['with'] ? '<div class="with">함께 ' + esc(r['with']) + '</div>' : '') + '</td>' +
      '<td class="due' + (r.overdue ? ' old' : '') + '">' + esc(r.due || '—') + '</td><td class="nx">' + nextStep(r) + '</td>' + progressCell(r) +
      '<td class="ss">' + ssCell(r) + '</td><td class="age ' + ageCls(r.age) + '">' + r.age + '일</td></tr>';
  }
  function table(rows, empty) { return '<table class="tk">' + COLG + HEAD_ROW + (rows.length ? rows.map(rowHtml).join('') : '<tr><td colspan="8" class="empty">' + empty + '</td></tr>') + '</table>'; }
  function groupTables(groups) { return groups.map(function (g) { return '<h3 class="rsp">' + esc(g.who) + ' <span class="gc">' + g.rows.length + '건</span></h3>' + table(g.rows, '없음'); }).join(''); }

  // ── 토글 내역 표(6열 colgroup · 세 표 같은 틀) ────────────────────────────────────
  function detailTable(d) {
    var cg = '<colgroup>' + DT_COLS.map(function (c) { return '<col class="' + c[1] + '">'; }).join('') + '</colgroup>';
    var head = '<tr>' + DT_COLS.map(function (c) { return '<th class="' + c[1] + '">' + c[0] + '</th>'; }).join('') + '</tr>';
    var body = d.rows.length ? d.rows.map(function (r) { return '<tr>' + r.map(function (cell, i) { return '<td class="' + DT_COLS[i][1] + '">' + cell + '</td>'; }).join('') + '</tr>'; }).join('')
      : '<tr><td colspan="6" class="empty">' + esc(d.empty) + '</td></tr>';
    var t = '<table class="dt">' + cg + head + body + '</table><div class="sub-note">' + esc(d.note) + '</div>';
    return d.title ? '<details open class="grp"><summary>' + esc(d.title) + '</summary>' + t + '</details>' : t;
  }

  // ── 책임 항목 3인 — 실측·잘한 것·보완할 것은 원장(hist·ev)에서 · 지난달 대비 ▲▼ ────────
  function ym(d) { return d.getFullYear() + '-' + ('0' + (d.getMonth() + 1)).slice(-2); }
  var NOW = new Date(), YM = ym(NOW), PREV = ym(new Date(NOW.getFullYear(), NOW.getMonth() - 1, 1));
  function firstNum(t) { var m = /(\d+(?:\.\d+)?)\s*%/.exec(t || '') || /(\d+(?:\.\d+)?)/.exec(t || ''); return m ? parseFloat(m[1]) : null; }
  function delta(cur, prev) {
    if (!prev) return '<span class="rd-none">— (지난달 없음)</span>';
    var a = firstNum(cur && cur.text), b = firstNum(prev.text);
    if (a != null && b != null && a !== b) return a > b ? '<span class="up">▲ ' + (a - b) + '</span>' : '<span class="dn">▼ ' + (b - a) + '</span>';
    if (cur && !!cur.bad !== !!prev.bad) return cur.bad ? '<span class="dn">▼ 이상 발생</span>' : '<span class="up">▲ 이상 해소</span>';
    return '<span>= 변동 없음</span>';
  }
  function respHtml(hist, ev) {
    var months = (hist && hist.months) || {};
    var head = '<tr><th class="ri">항목</th><th class="rc">기준(어떻게 평가)</th><th class="rp">이번 달 실측(자동)</th><th class="rd">지난달 대비</th><th class="rg">잘한 것</th><th class="rf">보완할 것</th></tr>';
    var out = '<h2>👤 책임 항목 — 3인 <span class="sub">GM 책임 항목은 GM업무 화면 띠에 있습니다(같은 원장) · 실측 = 매일 07:50 + 회신 반영 즉시</span></h2>';
    (M.people_order || []).forEach(function (person) {
      var rows = M.resp[person] || [];
      var trs = rows.map(function (r) {
        var cur = ((months[YM] || {})[person] || {})[r.item], prev = ((months[PREV] || {})[person] || {})[r.item];
        var e = ((ev || {})[person] || {})[r.item] || {};
        var text = r.raw ? r.html : esc(cur ? cur.text : '미측정(원장에 없음)');
        var bad = cur ? cur.bad : false;
        var tr = '<tr' + (r.detail ? ' class="rp-toggle"' : '') + '><td class="ri">' + (r.detail ? '<span class="rp-arrow">▸</span> ' : '') + esc(r.item) + '</td><td class="rc">' + esc(r.crit) + '</td>' +
          '<td class="' + (bad ? 'rp bad' : 'rp') + '">' + text + '</td><td class="rd">' + delta(cur, prev) + '</td>' +
          '<td class="rg">' + esc(e.good || (cur && cur.good) || '—') + '</td><td class="rf">' + esc(e.fix || (cur && cur.fix) || '—') + '</td></tr>';
        if (r.detail) tr += '<tr class="rp-detail" hidden><td colspan="6">' + detailTable(r.detail) + '</td></tr>';
        return tr;
      }).join('');
      out += '<div class="rp-person" data-person="' + esc(person) + '"><h3>' + esc(person) + '</h3><table class="resp-tb">' + head + trs + '</table></div>';
    });
    return out;
  }
  // 📅 분기 누적 — 달 3칸 + 분기 합(이상 달 수) + 분기 잘한 것/보완할 것
  function quarterHtml(hist) {
    var months = (hist && hist.months) || {};
    var y = NOW.getFullYear(), q = Math.floor(NOW.getMonth() / 3) + 1;
    var keys = [0, 1, 2].map(function (i) { return y + '-' + ('0' + (3 * q - 2 + i)).slice(-2); });
    document.getElementById('rq-sub').textContent = y + '년 ' + q + '분기 · 달마다 마지막 실측(말일 21:00 마감)이 남습니다 · 매월 평가해 다음 달과 비교';
    var head = '<tr><th class="ri">항목</th>' + keys.map(function (k) {
      var back = (months[k] || {})._소급;
      return '<th class="rq">' + parseInt(k.slice(5), 10) + '월' + (back ? '<span class="rq-back" title="' + esc(back) + '">소급</span>' : '') + '</th>';
    }).join('') + '<th class="rs">분기 합</th><th class="rg">분기 잘한 것</th><th class="rf">분기 보완할 것</th></tr>';
    return (M.people_order || []).map(function (person) {
      var items = [];
      keys.forEach(function (k) { Object.keys((months[k] || {})[person] || {}).forEach(function (it) { if (items.indexOf(it) < 0) items.push(it); }); });
      var trs = items.map(function (it) {
        var cells = '', goods = [], fixes = [], badN = 0, have = 0;
        keys.forEach(function (k) {
          var c = ((months[k] || {})[person] || {})[it];
          if (!c) { cells += '<td class="rq">—</td>'; return; }
          have++; if (c.bad) badN++;
          cells += '<td class="rq' + (c.bad ? ' bad' : '') + '">' + esc(c.text || '—') + '</td>';
          [[c.good, goods], [c.fix, fixes]].forEach(function (p) { var v = String(p[0] || '').trim(); if (v && v !== '—' && p[1].indexOf(v) < 0) p[1].push(v); });
        });
        var sum = have ? ('<span class="' + (badN ? 'dn' : 'up') + '">' + badN + '/' + have + '</span>') : '—';
        return '<tr><td class="ri">' + esc(it) + '</td>' + cells + '<td class="rs">' + sum + '</td><td class="rg">' + esc(goods.join(' · ') || '—') + '</td><td class="rf">' + esc(fixes.join(' · ') || '—') + '</td></tr>';
      }).join('') || '<tr><td class="ri">—</td><td class="rq" colspan="5">스냅숏 없음</td></tr>';
      return '<div class="rp-person"><h3>' + esc(person) + '</h3><table class="resp-tb">' + head + trs + '</table></div>';
    }).join('');
  }

  // ── ⚠ 놓친 것 ────────────────────────────────────────────────────────────────────
  function missedHtml() {
    var groups = (M.missed || []).map(function (g) {
      var lines = g.rows.map(function (r) {
        var fl = (r.overdue ? '<span class="fl">기한 지남 ' + esc(r.due) + '</span>' : '') + (r.flags || []).map(function (f) { return '<span class="fl">' + esc(f) + '</span>'; }).join('');
        return '<div class="top-i"><span class="top-age ' + ageCls(r.age) + '">' + r.age + '일째</span><div class="top-b"><b>#' + r.no + ' ' + esc(r.issue) + '</b>' + fl +
          '<div class="top-w">기한 ' + esc(r.due || '—') + ' · ' + (r.next_step ? '다음 한 걸음: ' + esc(r.next_step) : '<span class="nx-none">' + esc(M.next_step_missing) + '</span>') + ' · 회신 「#' + r.no + ' 했다」</div></div></div>';
      }).join('');
      return '<div class="top-who" data-person="' + esc(g.who) + '"><h3>' + esc(g.who) + ' <span class="gc">' + g.rows.length + '건</span></h3>' + lines + '</div>';
    }).join('') || '<div class="empty" style="padding:6px 0;">없음 — 기한 지난 것·7일 넘게 멈춘 것이 없습니다</div>';
    return '<h2>⚠ 놓친 것 <span class="why">기한 지난 것이 맨 위 · 7일 넘게 답 없는 것 · 사람별 · ' + (M.missed_n || 0) + '건 — 여기부터 답을 받으세요</span></h2>' + groups;
  }

  // ── 📋 현재 업무 ──────────────────────────────────────────────────────────────────
  function curHtml() {
    var out = (M.people || []).map(function (p) {
      var n = p.mine.length + p.team.reduce(function (a, g) { return a + g.rows.length; }, 0);
      var teamN = n - p.mine.length;
      var team = p.team_title ? '<details open class="grp"><summary>' + esc(p.team_lead) + ' ' + esc(p.team_title) + ' <span class="gc">' + teamN + '건</span></summary>' +
        (p.team.length ? groupTables(p.team) : '<div class="empty" style="padding:8px 14px;">없음</div>') + '</details>' : '';
      return '<div class="blk" data-person="' + esc(p.name) + '"><h2>' + esc(p.name) + ' <span class="sub">' + esc(p.dept) + ' · ' + esc(p.room) + ' · 열린 건 ' + n + '건(본인 ' + p.mine.length + '건)</span>' +
        '<button type="button" class="sec-act" onclick="openPersonA3(this.closest(\'.blk\').dataset.person);">🖨 A3 요약본</button></h2>' + table(p.mine, '열린 건 없음') + team + '</div>';
    });
    if (M.routine && M.routine.length) out.push('<div class="blk pr-skip"><h2>책임 <span class="sub">끝나는 일이 아니라 계속 보는 자리 · 이 줄은 완료로 닫지 않습니다</span></h2>' + groupTables(M.routine) + '</div>');
    if (M.line_out && M.line_out.length) out.push('<div class="blk"><h2>라인 밖 <span class="sub">실장·소장·나우열M 어느 라인도 아닌 담당 · ' + M.line_out.length + '건</span></h2>' + table(M.line_out, '없음') + '</div>');
    if (M.ai && M.ai.length) out.push('<div class="blk pr-skip"><h2>AI 처리 건 <span class="sub">사람 일이 아니라 화면 결함 등 — 사람 목차에서 뺐습니다 · ' + M.ai.length + '건</span></h2><div style="padding:10px 14px;font-size:13.5px;">' + M.ai.map(function (a) { return '#' + a.no + ' ' + esc(a.issue); }).join(' · ') + '</div></div>');
    var ug = (M.unassigned || []).map(function (g) { return '<details class="grp"><summary>' + esc(g.group) + ' <span class="gc">' + g.rows.length + '건</span></summary>' + table(g.rows, '없음') + '</details>'; }).join('');
    out.push('<div class="blk pr-skip"><h2>담당 미정 <span class="sub">GM 이 세 사람 중 누구 몫인지 정하면 그 사람 목차로 옮긴다 · ' + (M.unassigned_n || 0) + '건 · 성격별로 묶어 접어 뒀습니다</span></h2><div class="grps">' + (ug || '<div class="empty" style="padding:10px 14px;">없음</div>') + '</div></div>');
    if (M.moved && M.moved.length) out.push('<div class="blk pr-skip"><details class="grp"><summary>업무 SSOT 로 넘어간 것 <span class="gc">' + M.moved.length + '건</span></summary><ul class="mvlist">' + M.moved.map(function (m) {
      var ap = m.ap ? '<span class="ss-ap ' + m.ap.split(':')[0] + '">' + esc(m.ap.split(':')[1]) + '</span>' : '';
      return '<li>#' + m.no + ' ' + esc(m.issue) + '<span class="mvd">→ <a class="mvd-link" target="_blank" rel="noopener" href="' + SSOT_PAGE + (m.ssot_id ? '?item=' + encodeURIComponent(m.ssot_id) : '') + '">SSOT: ' + esc(m.ssot_title) + '</a> <span class="ss-st">' + esc(m.st) + '</span>' + ap + '<span class="mvd-id">' + (m.by === 'id' ? 'id로 연결' : '제목으로 연결') + '</span></span></li>';
    }).join('') + '</ul></details></div>');
    if (M.reply && M.reply.length) out.push('<div class="blk pr-skip"><details class="grp"><summary>회신 소통건 — 업무 아님 · 한 줄 답이 오면 닫힘 <span class="gc">' + M.reply.reduce(function (a, g) { return a + g.rows.length; }, 0) + '건</span></summary>' + groupTables(M.reply) + '</details></div>');
    return out.join('');
  }
  function barHtml() {
    var head = (M.counts || []).map(function (c) { return c[0] + ' ' + c[1] + '건(SSOT 미등록 ' + c[2] + '건)'; }).join(' · ');
    var note = !M.ssot_ok ? '<span class="b2 fail">⚠ 업무 SSOT 대조 실패 — 겹친 건이 그대로 보일 수 있습니다.</span>'
      : (M.moved && M.moved.length ? '<span class="b2">업무·결재 SSOT 에 올라간 것 ' + M.moved.length + '건 · 다른 곳에서 닫힌 것 ' + M.rc_n + '건 · 중복 ' + M.dup_n + '건은 맨 아래 접힘 목록으로 내렸습니다 · <b>여기 남은 ' + M.total + '건이 업무 SSOT 에 올려야 하는 것</b>입니다.</span>' : '');
    return '기준 ' + esc(M.today) + ' · 열린 ' + M.total + '건 · 가장 오래된 것 ' + M.oldest + '일 · 14일 넘게 답 없는 것 ' + M.stale + '건<span class="b2">' + esc(head) + ' · 담당 미정 ' + M.unassigned_n + '건 · 놓친 것 ' + M.missed_n + '건 · 진행할 건은 본인이 SSOT 등록</span>' + note;
  }

  var M = INLINE;
  function render(model, hist, ev, live) {
    M = model || INLINE;
    var lv = document.getElementById('live');
    if (live) { lv.className = 'live'; lv.textContent = '● 라이브 — 원장 스냅숏 ' + (M.generated_at || '') + ' 생성 · 회신 종결 뒤 저장·배포 1분 안에 바뀝니다'; }
    else { lv.className = 'live off'; lv.textContent = '⚠ 라이브 원장을 못 읽었습니다(erp 도메인에서만 값이 붙습니다) — 아래 값은 ' + (M.generated_at || '') + ' 정적본 · 0 이 아니라 못 읽은 것'; }
    document.getElementById('bar').innerHTML = barHtml();
    document.getElementById('resp').innerHTML = respHtml(hist, ev);
    document.getElementById('missed').innerHTML = missedHtml();
    document.getElementById('cur').innerHTML = curHtml();
    document.getElementById('rq').innerHTML = quarterHtml(hist);
    wire();
  }

  // ── 동작: 토글 · 담당 지정(공용 보드 MGR_TASK_OWNER · 새 저장소 없음) ─────────────────
  var BOARD_URL = 'https://script.google.com/macros/s/AKfycbyXw4ZaA6hLK567GC7NY33Y8SvNPW6kNtrXFz2OsSdFVBmCnZP-2oD-RQiX0IpekBu1/exec';
  var OWNER_KEY = 'MGR_TASK_OWNER';
  function readOwnerBoard() {
    var gas = function () { return fetch(BOARD_URL + '?action=board&key=' + OWNER_KEY, { cache: 'no-store' }).then(function (r) { return r.json(); }); };
    if (!ERP_API_ON) return gas();
    return fetch('/api/board/' + OWNER_KEY, { cache: 'no-store' }).then(function (r) { if (!r.ok) throw new Error('api ' + r.status); return r.json(); }).catch(gas);
  }
  function wire() {
    document.querySelectorAll('tr.rp-toggle').forEach(function (tr) {
      tr.addEventListener('click', function () {
        var det = tr.nextElementSibling; if (!det || !det.classList.contains('rp-detail')) return;
        var opening = det.hidden; det.hidden = !opening; tr.querySelector('.rp-arrow').textContent = opening ? '▾' : '▸';
      });
    });
    var owns = Array.prototype.slice.call(document.querySelectorAll('select[data-o]'));
    var before = {};
    owns.forEach(function (inp) { before[inp.dataset.o] = inp.value; });
    readOwnerBoard().then(function (j) {
      var b = (j && j.ok && j.board) ? j.board : {};
      owns.forEach(function (inp) {
        var v = b['mgr-' + inp.dataset.o];
        if (!v || inp.value) return;             // 원장에 이미 사람이 있으면 그 값을 덮지 않는다
        if (!inp.querySelector('option[value="' + v.replace(/"/g, '&quot;') + '"]')) { var o = document.createElement('option'); o.value = v; o.textContent = v; inp.appendChild(o); }
        inp.value = v; before[inp.dataset.o] = v;
      });
    }).catch(function (e) { console.warn('[목차] 담당 보드 읽기 실패', e && e.message); });
    owns.forEach(function (inp) {
      inp.addEventListener('change', function () {
        var v = inp.value.trim(), was = before[inp.dataset.o];
        if (v === was) return;
        inp.disabled = true;
        readOwnerBoard().then(function (j) {
          var fresh = (j && j.ok && j.board) ? j.board : {};
          if (v) fresh['mgr-' + inp.dataset.o] = v; else delete fresh['mgr-' + inp.dataset.o];
          return fetch(BOARD_URL, { method: 'POST', headers: { 'Content-Type': 'text/plain;charset=UTF-8' }, body: JSON.stringify({ action: 'saveBoard', key: OWNER_KEY, board: fresh }), redirect: 'follow' }).then(function (r) { return r.json(); });
        }).then(function (res) {
          inp.disabled = false;
          if (res && res.ok) { before[inp.dataset.o] = v; inp.classList.add('saved'); setTimeout(function () { inp.classList.remove('saved'); }, 1500); }
          else { inp.value = was; alert('담당을 저장하지 못했습니다 — 잠시 뒤 다시 시도해 주세요.'); }
        }).catch(function () { inp.disabled = false; inp.value = was; alert('담당을 저장하지 못했습니다 — 잠시 뒤 다시 시도해 주세요.'); });
      });
    });
  }

  // ── A3 요약본(사람별) · 분기 누적 버튼 · 인쇄 · PNG ───────────────────────────────
  window.printA3 = function (orientation) {
    var st = document.getElementById('mgr-a3-style');
    if (!st) { st = document.createElement('style'); st.id = 'mgr-a3-style'; document.head.appendChild(st); }
    st.textContent = '@page{ size: A3 ' + orientation + '; margin: 12mm; }';
    window.print();
  };
  window.openPersonA3 = function (name) {
    document.body.dataset.a3 = name;
    document.querySelectorAll('[data-person]').forEach(function (el) { el.classList.toggle('a3-hide', el.dataset.person !== name); });
    document.getElementById('a3name').textContent = name;
    document.getElementById('mapbar').style.display = 'flex';
    document.getElementById('resp-q').open = false;
    window.scrollTo(0, 0);
  };
  window.closePersonA3 = function () {
    delete document.body.dataset.a3;
    document.querySelectorAll('.a3-hide').forEach(function (el) { el.classList.remove('a3-hide'); });
    document.getElementById('mapbar').style.display = 'none';
  };
  window.openQuarter = function () { var d = document.getElementById('resp-q'); d.open = true; d.scrollIntoView({ behavior: 'smooth', block: 'start' }); };
  var H2C_SRC = 'https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js';
  function loadH2C() { if (typeof html2canvas === 'function') return Promise.resolve(); return new Promise(function (ok, no) { var s = document.createElement('script'); s.src = H2C_SRC; s.onload = ok; s.onerror = no; document.head.appendChild(s); }); }
  function pad2(n) { return n < 10 ? '0' + n : '' + n; }
  window.saveMapPng = function (btn) {
    var label = btn.textContent; btn.textContent = '변환 중…'; btn.disabled = true;
    var d = new Date(), who = document.body.dataset.a3 ? '_' + document.body.dataset.a3.replace(/[ ]+/g, '') : '';
    var name = '중간관리자_업무' + who + '_' + d.getFullYear() + pad2(d.getMonth() + 1) + pad2(d.getDate()) + '.png';
    var skipped = Array.prototype.slice.call(document.querySelectorAll('.pr-skip'));
    skipped.forEach(function (el) { el.dataset.pngHidden = el.style.display; el.style.display = 'none'; });
    loadH2C().then(function () { return html2canvas(document.querySelector('.wrap'), { scale: 2, backgroundColor: '#ffffff', windowWidth: document.querySelector('.wrap').scrollWidth }); })
      .then(function (c) { var a = document.createElement('a'); a.download = name; a.href = c.toDataURL('image/png'); a.click(); })
      .catch(function () { alert('PNG 변환 실패 — [A3 인쇄] 에서 PDF 저장을 쓰세요.'); })
      .finally(function () { skipped.forEach(function (el) { el.style.display = el.dataset.pngHidden; delete el.dataset.pngHidden; }); btn.textContent = label; btn.disabled = false; });
  };

  // ── 부팅: 라이브 원장 3개 fetch → 실패하면 인라인 정적본(못 읽었다고 적는다) ────────────
  Promise.all([fetchJson('status/manager_ledger_snapshot.json'), fetchJson('status/manager_eval_history.json'), fetchJson('status/manager_eval.json').catch(function () { return {}; })])
    .then(function (r) { render(r[0], r[1], r[2], true); })
    .catch(function () { render(INLINE, INLINE._hist || null, null, false); });
})();
</script>
</body>
</html>
'''


# ═══ 📋 주간 회의자료 A3 정본 (GM 지시 2026-09-15 · 카드 2026-09-35 · 운영 기준 10) ═══
#   매주 화 07:50 send_ops_digest.send_weekly_meeting_pack 이 부른다. 달별이 아니라 주별 — 회차는
#   status/weekly_meeting_ledger.json 에 회의일 키로 쌓이고, 화면 하나(중간관리자_회의자료_A3.html)가
#   ?week=YYYY-MM-DD 로 회차를 고른다(인자 없으면 최신 회차). 원장은 HTML 안에 인라인으로 박는다 —
#   /repo/ 원장 fetch 는 erp 도메인에서만 값이 붙어 Pages·file 캡처가 빈 값이 되기 때문(2026-09-15 실측).
#   3열 = 운영부·시설부·경영지원부 · 열마다 ▸사전 보고 ▸실측 이상(책임 항목 bad 셀 재사용) ▸회신 없는 것.
MEETING_OUT = ROOT / "3. 웰페리온 가이드" / "coo" / "chairman" / "중간관리자_회의자료_A3.html"
MEETING_PNG = MEETING_OUT.with_suffix(".png")
MEETING_LEDGER = ROOT / "status" / "weekly_meeting_ledger.json"
WEEKLY_INTAKE = ROOT / "status" / "weekly_meeting_intake.json"
MEETING_COLS = [("운영부", "이경연 실장"), ("시설부", "이정헌 소장"), ("경영지원부", "나우열M")]
MEETING_ATTENDEES = "김남욱 GM · 이경연 실장 · 이정헌 소장 · 김종현 차장 · 나우열M"
_REPORT_DIRS = (ROOT / "3. 웰페리온 가이드" / "reports", ROOT / "3. 웰페리온 가이드" / "coo" / "chairman")


def _meeting_doc_no(meeting: date, rounds: dict) -> str:
    """WP-GM-YYMMDD-NN — 같은 회차가 원장에 있으면 그 번호 재사용, 없으면 그날 A3 파일 수 + 1."""
    prev = (rounds.get(meeting.isoformat()) or {}).get("doc_no")
    if prev:
        return prev
    ymd = meeting.strftime("%y%m%d")
    n = sum(len(list(d.glob(f"{ymd}_*_A3.html"))) for d in _REPORT_DIRS if d.exists())
    return f"WP-GM-{ymd}-{n + 1:02d}"


def _load_intake(meeting: date) -> dict:
    try:
        d = json.loads(WEEKLY_INTAKE.read_text(encoding="utf-8"))
        return d.get("people") or {} if d.get("meeting_date") == meeting.isoformat() else {}
    except Exception:
        return {}


def meeting_round(meeting: date, rounds: dict) -> dict:
    """회차 데이터 한 벌 — 열마다 사전 보고·실측 이상·회신 없는 것·GM 결정 받을 것."""
    seen = latest_by_no()
    sales_data = fill_sales_current(seen)
    ssot_rows = fetch_ssot_rows()
    objs = load_month_objectives()
    rows_def = resp_rows_def(seen, ssot_rows, sales_data, objs)
    intake = _load_intake(meeting)
    try:
        import send_ops_digest as _sod
        nudges = _sod.build_reply_nudge_items(meeting.isoformat(), ssot_rows or [])
    except Exception:
        nudges = []
    cols = {}
    for dept, person in MEETING_COLS:
        p = intake.get(person) or {"submitted": False, "lines": [], "at": ""}
        anomalies = []
        for entry in rows_def.get(person, []):
            item, fn = entry[0], entry[2]
            raw = entry[3] if len(entry) > 3 else False
            try:
                text, bad = fn()
            except Exception:
                continue
            if bad:
                anomalies.append(f"{item} — {_plain(text) if raw else text}")
        open_n = sum(1 for _d, it in seen.values()
                     if str(it.get("owner") or "").strip() == person and str(it.get("status", "")).lower() not in DONE)
        cols[dept] = {"person": person, "submitted": bool(p.get("submitted")), "at": p.get("at", ""),
                      "intake": list(p.get("lines") or []), "open": open_n, "anomalies": anomalies,
                      "nudges": [it["ask"] for it in nudges if it.get("who") == person],
                      "decisions": [ln for ln in (p.get("lines") or []) if re.search(r"④|결정", ln)]}
    y, w, _ = meeting.isocalendar()
    return {"meeting_date": meeting.isoformat(), "week": f"{y}-W{w:02d}", "doc_no": _meeting_doc_no(meeting, rounds),
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"), "attendees": MEETING_ATTENDEES,
            "ssot_ok": ssot_rows is not None, "cols": cols}


MEETING_TEMPLATE = r'''<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<title>중간관리자 회의자료 — 웰페리온 A3 (주별)</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;700;900&family=Noto+Serif+KR:wght@600;700&display=swap" rel="stylesheet">
<style>
  @page { size: A3 landscape; margin: 0; }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  :root{ --ink:#101418; --navy:#14304E; --navy-bg:#EDF1F6; --good:#146B4F; --warn:#96601A; --bad:#9E2A2A; --line:#E3E7EB; }
  html,body{ background:#8A9099; font-family:'Noto Sans KR',sans-serif; color:var(--ink); -webkit-print-color-adjust:exact; print-color-adjust:exact; }
  .bar{ position:fixed; top:0; left:0; right:0; height:46px; background:var(--navy); color:#fff; display:flex; align-items:center; gap:10px; padding:0 18px; z-index:99; font-size:13px; box-shadow:0 2px 8px rgba(0,0,0,.3); }
  .bar b{ font-weight:700; } .bar .sp{ flex:1; } .bar a{ color:#fff; opacity:.85; margin-right:6px; }
  .bar button{ font-family:inherit; font-size:12.5px; font-weight:700; color:var(--navy); background:#fff; border:0; border-radius:3px; padding:7px 15px; cursor:pointer; }
  @media print { .bar{ display:none !important; } html,body{ background:#fff; } .page{ margin:0 !important; box-shadow:none !important; } }
  .page{ width:1587px; height:1123px; background:#fff; margin:66px auto 30px; padding:30px 34px 24px; display:flex; flex-direction:column; box-shadow:0 4px 20px rgba(0,0,0,.35); overflow:hidden; }
  .head{ display:flex; align-items:flex-end; border-bottom:2.5px solid var(--navy); padding-bottom:9px; }
  .brand{ font-family:'Noto Serif KR',serif; font-weight:700; font-size:15px; color:var(--navy); letter-spacing:6px; margin-bottom:5px; }
  .title{ font-family:'Noto Serif KR',serif; font-weight:700; font-size:29px; letter-spacing:-.8px; line-height:1.15; }
  .title small{ font-size:18px; color:#3C464F; font-family:'Noto Sans KR',sans-serif; font-weight:500; }
  .meta{ margin-left:auto; text-align:right; font-size:13px; line-height:1.65; color:#3C464F; } .meta b{ color:var(--ink); }
  .ask{ margin-top:12px; background:var(--navy); color:#fff; display:flex; }
  .ask .lb{ width:118px; flex:none; display:flex; flex-direction:column; align-items:center; justify-content:center; border-right:1px solid rgba(255,255,255,.28); }
  .ask .lb span{ font-size:10.5px; letter-spacing:3px; opacity:.85; } .ask .lb strong{ font-family:'Noto Serif KR',serif; font-size:19px; }
  .ask .it{ flex:1; padding:10px 18px; } .ask .q{ font-size:19px; font-weight:700; line-height:1.35; } .ask .d{ font-size:14.5px; line-height:1.5; opacity:.88; margin-top:3px; }
  .cols{ margin-top:12px; display:flex; gap:11px; flex:1; min-height:0; }
  .box{ flex:1; border:1px solid var(--line); border-top:3px solid var(--navy); padding:12px 16px 10px; overflow:hidden; display:flex; flex-direction:column; }
  .box h3{ font-size:19px; font-weight:700; color:var(--navy); margin-bottom:2px; }
  .box .who{ font-size:14px; color:#3C464F; margin-bottom:8px; }
  .box h4{ font-size:14px; font-weight:700; color:var(--navy); letter-spacing:1px; background:var(--navy-bg); padding:2px 8px; margin:5px 0 5px; }
  .box ol{ list-style:none; counter-reset:n; }
  .box ol li{ font-size:16px; line-height:1.36; padding-left:30px; position:relative; margin-bottom:3px; counter-increment:n; }
  .box ol li::before{ content:counter(n); position:absolute; left:0; top:2px; width:22px; height:22px; border-radius:50%; background:var(--navy); color:#fff; font-size:12.5px; font-weight:700; text-align:center; line-height:22px; }
  .box ul{ list-style:none; }
  .box ul li{ font-size:15.5px; line-height:1.36; padding-left:20px; position:relative; margin-bottom:2px; color:#3C464F; }
  .box ul li::before{ content:'⚠'; position:absolute; left:0; top:0; font-size:12.5px; color:var(--bad); }
  .box .ok{ color:var(--good); font-size:15px; padding-left:4px; }
  .box .miss{ color:var(--bad); font-weight:900; font-size:17px; padding:6px 8px; border:2px solid var(--bad); display:inline-block; margin:2px 0 6px; }
  .gm{ margin-top:12px; border:1.5px solid var(--navy); display:flex; }
  .gm .lb{ width:118px; flex:none; background:var(--navy); color:#fff; display:flex; flex-direction:column; align-items:center; justify-content:center; }
  .gm .lb span{ font-size:10.5px; letter-spacing:3px; opacity:.85; } .gm .lb strong{ font-family:'Noto Serif KR',serif; font-size:19px; text-align:center; line-height:1.2; }
  .gm .items{ flex:1; display:flex; } .gm .it{ flex:1; padding:7px 14px; border-right:1px solid var(--line); } .gm .it:last-child{ border-right:0; }
  .gm .n{ font-size:13px; font-weight:700; color:var(--navy); letter-spacing:1px; margin-bottom:3px; }
  .gm p{ font-size:16px; line-height:1.4; padding-left:14px; position:relative; margin-bottom:2px; } .gm p::before{ content:'·'; position:absolute; left:3px; font-weight:700; }
  .gm p.none{ color:#6B7580; }
  .foot{ margin-top:10px; border-top:1px solid var(--line); padding-top:7px; display:flex; gap:26px; font-size:14px; line-height:1.55; color:#48525B; }
  .foot div{ flex:1; } .foot b{ color:var(--ink); }
</style>
</head>
<body>
<div class="bar">
  <b id="bar-title">중간관리자 회의자료 (A3 1장)</b>
  <span class="sp"></span>
  <span id="weeks"></span>
  <button onclick="window.print()">A3 인쇄</button>
  <button id="png">PNG 다운로드</button>
</div>
<div class="page" id="sheet1"></div>
<script id="rounds" type="application/json">__ROUNDS__</script>
<script>
(function () {
  var ROUNDS = JSON.parse(document.getElementById('rounds').textContent || '{}');
  var keys = Object.keys(ROUNDS).sort();
  var q = new URLSearchParams(location.search).get('week');
  var key = (q && ROUNDS[q]) ? q : keys[keys.length - 1];
  var esc = function (s) { return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) { return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]; }); };
  document.getElementById('weeks').innerHTML = keys.map(function (k) { return '<a href="?week=' + k + '">' + (k === key ? '<b>' + k + '</b>' : k) + '</a>'; }).join('');
  if (!key) { document.getElementById('sheet1').innerHTML = '<p style="padding:40px;font-size:20px">회차 데이터가 없습니다.</p>'; return; }
  var r = ROUNDS[key], d = new Date(key + 'T00:00:00'), md = (d.getMonth() + 1) + '/' + d.getDate();
  var dot = key.slice(0, 4) + '. ' + key.slice(5, 7) + '. ' + key.slice(8, 10) + '.';
  document.title = '중간관리자 회의자료 ' + md + ' — 웰페리온 A3';
  document.getElementById('bar-title').textContent = '중간관리자 회의자료 — ' + key + '(화) 15:00 (A3 1장 · ' + r.week + ')';
  var list = function (arr, tag, empty) {
    if (!arr || !arr.length) return '<div class="ok">' + empty + '</div>';
    return '<' + tag + '>' + arr.map(function (x) { return '<li>' + esc(x) + '</li>'; }).join('') + '</' + tag + '>';
  };
  var cols = '', gm = '';
  ['운영부', '시설부', '경영지원부'].forEach(function (dept) {
    var c = r.cols[dept] || {};
    var intake = c.submitted ? list(c.intake, 'ol', '') : '<div class="miss">사전 보고 미제출</div>';
    cols += '<div class="box"><h3>' + dept + '</h3><div class="who">' + esc(c.person) + ' · 원장 열린 ' + (c.open || 0) + '건'
      + (c.submitted ? ' · 사전 보고 ' + esc(c.at) : '') + '</div>'
      + '<h4>▸ 사전 보고 ①~⑤</h4>' + intake
      + '<h4>▸ 실측 이상 (07:50 자동)</h4>' + list(c.anomalies, 'ul', '이상 없음')
      + '<h4>▸ 회신 없는 것</h4>' + list(c.nudges, 'ol', '없음') + '</div>';
    gm += '<div class="it"><div class="n">' + dept + '</div>'
      + ((c.decisions && c.decisions.length) ? c.decisions.map(function (x) { return '<p>' + esc(x) + '</p>'; }).join('') : '<p class="none">결정 요청 없음</p>') + '</div>';
  });
  document.getElementById('sheet1').innerHTML =
    '<div class="head"><div><div class="brand">WELLPERION</div><div class="title">중간관리자 회의자료 — ' + md + '(화) 15:00<br><small>운영부 · 시설부 · 경영지원부 3라인 · 사전 보고(월 17:00) + 실측 이상(화 07:50 자동) + 회신 없는 것</small></div></div>'
    + '<div class="meta">작성 <b>AI 웰리</b> · 담당 <b>김남욱 GM</b><br>작성일 <b>' + dot + '</b> · 문서번호 <b>' + esc(r.doc_no) + '</b> · <b>1 / 1</b></div></div>'
    + '<div class="ask"><div class="lb"><span>DIRECTION</span><strong>방향</strong></div><div class="it"><div class="q">회의는 이 한 장으로 · 답은 「#번호 + 한 줄」 · 사전 보고 안 낸 열은 회의에서 구두로 ①~⑤</div>'
    + '<div class="d">번호(#)는 중간관리자 업무목차 원장 번호 그대로다. 실측 이상은 매일 07:50 자동 실측값 · 진행할 건은 본인이 업무 SSOT 에 등록한다.' + (r.ssot_ok ? '' : ' ⚠ 이번 회차는 업무 SSOT 조회 실패 — SSOT 항목은 안 잰 값이다.') + '</div></div></div>'
    + '<div class="cols">' + cols + '</div>'
    + '<div class="gm"><div class="lb"><span>DECISION</span><strong>GM 결정<br>받을 것</strong></div><div class="items">' + gm + '</div></div>'
    + '<div class="foot"><div><b>참석</b> — ' + esc(r.attendees) + '. <b>출처</b> — 사전 보고(★중간관리자 방·AtoA 월 00:00~화 08:59) · 중간관리자 업무목차 책임 항목 실측 · 원장 열린 건. 생성 ' + esc(r.generated_at) + '.</div>'
    + '<div><b>다음</b> — 다음 화요일 15:00 · 월 17:00 까지 사전 보고 ①이번 주 한 것 ②다음 주 할 것 ③막힌 것 ④GM 결정 필요 ⑤요청. 회의 결과는 카드·원장에 반영.</div></div>';
  document.getElementById('png').onclick = function () {
    if (typeof html2canvas !== 'function') { alert('이미지 도구를 불러오지 못했습니다 — 새로고침 후 다시 눌러 주세요.'); return; }
    html2canvas(document.getElementById('sheet1'), {scale:2, backgroundColor:'#ffffff', useCORS:true, logging:false}).then(function (c) {
      var a = document.createElement('a'); a.download = key.replace(/-/g, '').slice(2) + '_중간관리자_회의자료_A3.png'; a.href = c.toDataURL('image/png'); a.click();
    });
  };
})();
</script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js"></script>
</body>
</html>
'''


def render_meeting_html(rounds: dict) -> str:
    payload = json.dumps(rounds, ensure_ascii=False).replace("</", "<\\/")
    return MEETING_TEMPLATE.replace("__ROUNDS__", payload)


def capture_meeting_png(html_path: Path, png_path: Path) -> bool:
    """Chrome headless 캡처 — 창은 browser_quiet 로 화면 밖(창 크기만 A3 캡처 크기로 덮는다)."""
    import subprocess
    chrome = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")
    if not chrome.exists():
        return False
    try:
        from browser_quiet import quiet_args
        quiet = [a for a in quiet_args() if not a.startswith("--window-size")]
    except Exception:
        quiet = []
    cmd = [str(chrome), "--headless=new", "--disable-gpu", "--hide-scrollbars", *quiet,
           "--window-size=1660,1260", f"--screenshot={png_path}", "--virtual-time-budget=6000", html_path.as_uri()]
    proc = subprocess.run(cmd, capture_output=True, timeout=90)   # bytes — 크롬 stderr 가 cp949 로 깨져 디코드 오류 내던 것 회피
    return png_path.exists() and proc.returncode == 0


def build_meeting_a3(meeting: date) -> dict:
    """회차 데이터를 원장에 쌓고(회의일 키 · 같은 회차는 교체) 정본 HTML + PNG 를 다시 쓴다. 돌려주는 값 = 이번 회차."""
    try:
        ledger = json.loads(MEETING_LEDGER.read_text(encoding="utf-8"))
    except Exception:
        ledger = {"_doc": "중간관리자 주간 회의자료 회차 원장 — 회의일(화요일) 키 · manager_task_index.build_meeting_a3 가 매주 화 07:50 append", "rounds": {}}
    rounds = ledger.setdefault("rounds", {})
    rnd = meeting_round(meeting, rounds)
    rounds[meeting.isoformat()] = rnd
    MEETING_LEDGER.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    MEETING_OUT.write_text(render_meeting_html(rounds), encoding="utf-8")
    capture_meeting_png(MEETING_OUT, MEETING_PNG)
    return rnd


def _selfcheck_meeting_a3() -> None:
    """미제출 빨강·3열·결정 띠 — 네트워크 없이 렌더만."""
    rounds = {"2026-09-22": {"meeting_date": "2026-09-22", "week": "2026-W39", "doc_no": "WP-GM-260922-01",
                             "generated_at": "2026-09-22 07:50", "attendees": MEETING_ATTENDEES, "ssot_ok": True,
                             "cols": {"운영부": {"person": "이경연 실장", "submitted": True, "at": "2026-09-21 16:40",
                                               "intake": ["① FAQ 취합", "④ 결정: 요금표"], "open": 3,
                                               "anomalies": ["소통 — 회신율 1/3"], "nudges": ["#224 FAQ"],
                                               "decisions": ["④ 결정: 요금표"]},
                                      "시설부": {"person": "이정헌 소장", "submitted": False, "at": "", "intake": [],
                                               "open": 0, "anomalies": [], "nudges": [], "decisions": []},
                                      "경영지원부": {"person": "나우열M", "submitted": False, "at": "", "intake": [],
                                                 "open": 1, "anomalies": [], "nudges": [], "decisions": []}}}}
    out = render_meeting_html(rounds)
    payload = json.loads(out.split('type="application/json">', 1)[1].split("</script>", 1)[0].replace("<\\/", "</"))
    cols = payload["2026-09-22"]["cols"]
    assert len(cols) == 3 and [c["submitted"] for c in cols.values()] == [True, False, False]
    assert ".miss{ color:var(--bad)" in out and "사전 보고 미제출" in out   # 미제출 = 빨강 박스
    assert _meeting_doc_no(date(2026, 9, 22), {"2026-09-22": {"doc_no": "WP-GM-260922-07"}}) == "WP-GM-260922-07"
    print("[selfcheck] meeting_a3 렌더 OK")


def regenerate_and_publish(reason: str = "") -> bool:
    """「바로 반영」 한 관문(GM 지시 2026-09-15 「#283 완료했는데 바로 반영이 안됨」) — 화면 재생성 → 저장·배포.
    원장(_digest_ledger)이 바뀌는 자리(send_ops_digest --resolve · sync_ledger_replies 회신 매칭 · 07:50 통 ·
    GM 채팅 「#N 완료」→ --resolve)가 전부 이 함수를 부른다. 저장은 safe_commit(락·가드) 한 경로 · 푸시까지.
    실패해도 예외를 밖으로 던지지 않는다(통 발송을 막지 않는다) — False 로만 알린다."""
    import subprocess
    import sys
    try:
        OUT.write_text(build(), encoding="utf-8")
    except Exception as exc:
        print(f"[mgr] 재생성 실패: {type(exc).__name__}: {exc}")
        return False
    msg = "chore(mgr): 중간관리자 업무 화면 바로 반영" + (f" — {reason}" if reason else "")
    cmd = [sys.executable, str(ROOT / "scripts" / "safe_commit.py"),
           str(OUT.relative_to(ROOT)), str(HIST_PATH.relative_to(ROOT)), str(SNAP_PATH.relative_to(ROOT)),
           "-m", msg, "--holder", "mgr_publish"]
    try:
        proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, timeout=300)
    except Exception as exc:
        print(f"[mgr] 저장·배포 실패: {type(exc).__name__}: {exc}")
        return False
    tail = (proc.stdout or b"").decode("utf-8", "replace").strip().splitlines()[-1:]
    print(f"[mgr] 재생성 → 저장·배포 rc={proc.returncode} {' '.join(tail)}")
    return proc.returncode == 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="중간관리자 업무 목차 렌더")
    ap.add_argument("--clean-notes", action="store_true",
                    help="원장 note 에서 우리 발신 조각·똑같이 겹친 조각을 걷어낸다(원장을 고침)")
    ap.add_argument("--dry", action="store_true", help="--clean-notes 미리보기 — 파일은 안 고침")
    ap.add_argument("--selfcheck", action="store_true", help="판정 규칙 자가검사")
    ap.add_argument("--publish", action="store_true", help="재생성 뒤 저장·배포까지(regenerate_and_publish)")
    ap.add_argument("--reason", default="", help="--publish 커밋 메시지 꼬리(예: #283 완료)")
    ap.add_argument("--meeting-a3", action="store_true",
                    help="주간 회의자료 A3 정본(중간관리자_회의자료_A3.html + png) 생성 · 회차 원장 append")
    ap.add_argument("--week", default="", help="--meeting-a3 회의일(화요일 YYYY-MM-DD · 기본 오늘이 속한 주 화요일)")
    ap.add_argument("--backfill", nargs="+", default=None, metavar="YYYY-MM",
                    help="지난 달을 그 달 말일 기준으로 실측해 원장(manager_eval_history) 그 달 키에 적는다"
                         "(이미 있는 달은 건너뜀 · --force 로 덮어쓰기)")
    ap.add_argument("--force", action="store_true", help="--backfill 이미 있는 달 키도 덮어쓴다")
    args = ap.parse_args()
    if args.backfill:
        backfill_months(args.backfill, force=args.force)
    elif args.selfcheck:
        selfcheck()
        _selfcheck_meeting_a3()
    elif args.meeting_a3:
        _d = date.fromisoformat(args.week) if args.week else date.today()
        _meeting = _d - timedelta(days=_d.weekday()) + timedelta(days=1)
        _r = build_meeting_a3(_meeting)
        print(f"[meeting-a3] {_r['doc_no']} · {_meeting} · {MEETING_OUT.relative_to(ROOT)} · png={'있음' if MEETING_PNG.exists() else '없음'}")
    elif args.clean_notes:
        clean_notes(dry=args.dry)
    elif args.publish:
        raise SystemExit(0 if regenerate_and_publish(args.reason) else 1)
    else:
        OUT.write_text(build(), encoding="utf-8")
        print(f"[manager_task_index] {OUT.relative_to(ROOT)} · {OUT.stat().st_size:,} bytes")
