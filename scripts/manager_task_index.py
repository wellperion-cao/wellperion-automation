# -*- coding: utf-8 -*-
"""중간관리자 3인 업무 목차 — GM 이 목차로 체크하는 한 장.

만드는 이유(GM 지시 2026-09-09): "실장님에게 목차 리스트를 줘서 내가 업무를 체크하는게 훨씬 효율적"
새 원장을 만들지 않는다(약속 L21) — 이미 매일 쌓이는 `_digest_ledger.json` 의 번호(no) 건을 사람별로 갈라 렌더할 뿐이다.
GM 이 화면에서 체크한 것은 그 브라우저에만 남는다(localStorage) — 원장 상태는 실무진 회신으로만 바뀐다.

읽기 편하게 다듬음(GM 지시 2026-09-10 "이거 조금 더 친절하게 정리해줄 수 있어? 그리고 GM업무에 붙여줘"):
  · 맨 위 요약 띠 + 「먼저 볼 것」(경과 긴 순 5건)
  · 「최근 상황」은 40자까지만 보이고 전문은 title(마우스 올리면)
  · 경과 14일↑ 빨강 / 7~13일 주황
  · 담당 미정 건은 성격별 <details> 묶음

갱신: python scripts/manager_task_index.py   (매일 아침 정리 뒤 다시 돌리면 최신)

업무 SSOT 와 안 겹치게(나우열M 지적 2026-09-10 "직원들은 SSOT 와 너가 준 페이지 두 개를
중복으로 확인하는 비효율적인 상황"): 렌더 때마다 업무 SSOT(GAS todo_list)를 읽어 제목이
닮은 건은 사람별 표에서 빼고 맨 아래 접힘 목록("업무 SSOT 로 넘어간 것")으로 옮긴다.
SSOT 조회가 실패하면 대조 없이 종전대로 렌더하고 화면에 실패를 적는다.
"""
from __future__ import annotations

import argparse
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
RESP_PEOPLE = ["김남욱 GM", "이경연 실장", "이정헌 소장", "나우열M"]
_NO_MEASURE = "미수집"
SSOT_DONE = {"완료", "폐기", "완료됨"}
OPS_DEPT_STAFF = ["이경연 실장", "최준용M", "임정은M", "윤병현AM", "백승화 사원", "진수아 사원", "이지영 사원"]


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
        return d["months"][date.today().strftime("%Y-%m")].get("objectives") or []
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
    today = date.today()
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
    """확인요청 원장(latest_by_no)에서 사람별 회신율 — 닫힌 건/보낸 건 · 최장경과 · 35일↑."""
    mine = [(n, d, it) for n, (d, it) in seen.items() if str(it.get("owner") or "").strip() == owner]
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
    """종합접수처 부서별 열린·7일↑·전사 미배정 — 1영업일 첫처리는 첫처리 시각 필드가
    없어 잴 수 없다(지어내지 않는다)."""
    try:
        from collectors.ops_shared import RECEPTION_EXEC_URL, gas_get, reception_elapsed_days, reception_rows
        resp = gas_get(RECEPTION_EXEC_URL, params={"action": "reg_list"}, timeout=20,
                       label="manager_task_index 접수")
        if resp is None:
            return f"{_NO_MEASURE}(접수처 조회 실패)", False
        data = resp.json()
        if not data.get("ok"):
            return f"{_NO_MEASURE}(접수처 조회 실패)", False
        rows = reception_rows(data.get("data", []))
    except Exception:
        return f"{_NO_MEASURE}(접수처 조회 실패)", False
    mine = [r for r in rows if str(r.get("dept") or "") == dept]
    opens = [r for r in mine if str(r.get("status") or "") != "완료"]
    now = datetime.now()
    stale = sum(1 for r in opens if reception_elapsed_days(r, now) >= 7)
    unassigned = sum(1 for r in rows if not str(r.get("dept") or "").strip())
    text = (f"열린 {len(opens)}건 · 7일↑ {stale}건 · 전사 미배정 {unassigned}건 · "
            f"1영업일 첫처리={_NO_MEASURE}")
    return text, stale > 0


def facility_check_cell() -> tuple[str, bool]:
    """시설 점검 이행 — 오늘 회차 입력 수·기준이탈 건(support_check_summary 실측)."""
    try:
        import support_check_summary as scs
        lines, filled = scs.build_facility_section(date.today().isoformat())
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
    mp = date.today().strftime("%Y-%m")
    today = date.today()
    done_month = sum(1 for it in items if str(it.get("last_done") or "").startswith(mp))
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
    """업무·결재 SSOT(운영부 전원) — 이번 주(월~일) 완료 건수(기준 15) · 결재대기."""
    if rows is None:
        return f"{_NO_MEASURE}(업무 SSOT 조회 실패)", False
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)
    mine = [r for r in rows if str(r.get("담당자") or "").strip() in OPS_DEPT_STAFF]
    done_week = 0
    for r in mine:
        if str(r.get("상태") or "") in SSOT_DONE:
            cd = _parse_ymd(r.get("완료일")) or _parse_ymd(r.get("수정일"))
            if cd and monday <= cd <= sunday:
                done_week += 1
    pend = sum(1 for r in mine if str(r.get("결재요청") or "").strip() and str(r.get("결재상태") or "") != "결재완료")
    text = f"이번 주 완료 {done_week}건(기준 15) · 결재대기 {pend}건 · 대상행 {len(mine)}건"
    return text, done_week < 15


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
    mine = [r for r in rows if str(r.get("담당자") or "").strip() == "나우열M"]
    today = date.today()
    ip = sum(1 for r in mine if str(r.get("상태") or "") == "진행중")
    hold = sum(1 for r in mine if str(r.get("상태") or "") == "보류")
    overdue = sum(1 for r in mine
                  if str(r.get("상태") or "") not in SSOT_DONE and (d := _parse_ymd(r.get("종료일"))) and d < today)
    dup = _dup_count(mine)
    text = f"진행중 {ip}건 · 보류 {hold}건 · 기한 지난 것 {overdue}건 · 중복 {dup}건 · 전체 {len(mine)}건"
    return text, (overdue > 0 or dup > 0)


def _no_measure_cell(reason: str) -> tuple[str, bool]:
    return f"{_NO_MEASURE}({reason})", False


RESP_HEAD = ('<tr><th class="ri">항목</th><th class="rc">기준(어떻게 평가)</th>'
             '<th class="rp">이번 달 진척(실측)</th><th class="rg">잘한 것</th>'
             '<th class="rf">보완할 것</th></tr>')


def resp_table(person: str, rows_def: list, ev: dict) -> str:
    trs = []
    for entry in rows_def:
        item, crit, fn = entry[0], entry[1], entry[2]
        raw = entry[3] if len(entry) > 3 else False  # True = fn 이 이미 안전한 진척 막대 HTML 을 낸다
        text, bad = fn()
        good, fix = eval_cell(ev, person, item)
        cls = "rp bad" if bad else "rp"
        trs.append(f'<tr><td class="ri">{html.escape(item)}</td>'
                   f'<td class="rc">{html.escape(crit)}</td>'
                   f'<td class="{cls}">{text if raw else html.escape(text)}</td>'
                   f'<td class="rg">{html.escape(good)}</td>'
                   f'<td class="rf">{html.escape(fix)}</td></tr>')
    return (f'<table class="resp-tb">\n          {RESP_HEAD}\n          '
            + "\n          ".join(trs) + '\n        </table>')


def resp_section(seen: dict, ssot_rows: "list | None", sales_data: "dict | None" = None) -> str:
    ev = load_eval()
    objs = load_month_objectives()
    mgr_names = ["이경연 실장", "이정헌 소장", "나우열M"]

    rows_def = {
        "김남욱 GM": [
            ("GM업무 카드 진척", "월간운영계획 카드 체크 완료율 · 기한 지난 목표 0건",
             lambda: objective_progress_cell(_obj_filter(objs, "김남욱 GM"))),
            ("중간관리자 회신 짝", "보낸 확인요청 대비 회신 받은 비율 · 35일 넘긴 건 0",
             lambda: ledger_reply_cell_all(seen, mgr_names)),
            ("결재 처리", "결재요청 대기 건수 · 평균 대기일 3일 안",
             lambda: ssot_pending_cell(ssot_rows)),
            ("주간 미팅", "매주 화요일 15:00 고정 · 안건 = 이 화면 진행 체크",
             lambda: _no_measure_cell("참석·안건 기록 원장 없음")),
        ],
        "이경연 실장": [
            ("종합접수처(운영부)", "1영업일 안 첫 처리 · 7일 안 닫기 · 담당 미배정 0",
             lambda: reception_dept_cell("운영부")),
            ("점검 현황(운영부)", "요금 변경 준비·사우나 정비 체크리스트 진행률"
                             "(월간운영계획 체크 중 담당 이경연/운영부)",
             lambda: objective_progress_cell(_obj_filter(objs, "이경연 실장"))),
            ("업무·결재 SSOT(운영부 전원)", "주 15건 완료 기준 — 운영부 직원 전원 담당 행 합산",
             lambda: ssot_week_cell(ssot_rows)),
            ("결재 SSOT 제출", "기획안·보고는 결재요청 칸까지 채워 제출(멤버십 개편 기획안)",
             lambda: approval_submit_cell(ssot_rows)),
            ("매출(회원권+옵션)", "월 매출목표 대비 달성률 · 옵션 포함",
             lambda: sales_bucket_cell(sales_data, "member"), True),
            ("확인요청 회신", "번호 회신율 · 최장 경과일",
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
            ("확인요청 회신", "번호 회신율 · 최장 경과일",
             lambda: ledger_reply_cell(seen, "이정헌 소장")),
        ],
        "나우열M": [
            ("인사(CHRO) — 업무·결재 SSOT 운영", "진행중·보류·기한 지난 행 정리 · 중복 행 0",
             lambda: chro_ssot_cell(ssot_rows)),
            ("매출·지출(CFO) — 체계·시스템 구축", "매출보고 담당 건 회신 · 강습(파트너팀) 매출 마감 정확도",
             lambda: _no_measure_cell("자동 집계 원장 없음")),
            ("파트너팀 매출 관리", "월 매출목표 대비 달성률 · 파트너팀=강습 전체",
             lambda: sales_bucket_cell(sales_data, "lessons"), True),
            ("확인요청 회신", "번호 회신율 · 최장 경과일",
             lambda: ledger_reply_cell(seen, "나우열M")),
        ],
    }

    blocks = []
    for person in RESP_PEOPLE:
        tbl = resp_table(person, rows_def[person], ev)
        if person == "이경연 실장":
            extra = chief_detail_blocks(ssot_rows, objs)
        elif person == "김남욱 GM":
            extra = f'        {GM_DOC_SHELF}\n'
        else:
            extra = ""
        blocks.append(f'      <div class="rp-person">\n        <h3>{html.escape(person)}</h3>\n        '
                       f'{tbl}\n{extra}      </div>')
    return f'''  <section class="resp">
    <h2>👤 책임 항목 — 4인</h2>
{chr(10).join(blocks)}
  </section>'''


# ═══ 실장 건별 목록 3종(GM 지시 2026-09-14 "종합접수처 건·업무SSOT 건·점검현황 건별로 보고") ═══
#   책임 표(요약 한 줄)로는 뭐가 몇 건인지만 보이고 "그래서 뭔데"가 안 보인다는 지적 —
#   이경연 실장 표 바로 아래 건별 목록 3개를 편다. 원천은 이미 있는 함수가 쓰는 것 그대로
#   (접수 GAS reg_list·업무 SSOT todo_list·월간운영계획) — 새 원장을 만들지 않는다(약속 L21).

def _reception_handler(r: dict) -> str:
    hc = r.get("handlerCanon") or []
    h = str(hc[0]) if hc else str(r.get("handler") or "").strip()
    return h or "미배정"


def reception_ops_detail() -> "tuple[list, list] | tuple[None, None]":
    """운영부 열린 건(분실물 제외) + 분실물 목록. 조회 실패면 (None, None)."""
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
    mine = [r for r in rows if str(r.get("dept") or "") == "운영부" and str(r.get("status") or "") != "완료"]
    lost = [r for r in mine if "분실물" in str(r.get("category") or "")]
    rest = [r for r in mine if "분실물" not in str(r.get("category") or "")]
    return rest, lost


def reception_detail_html() -> str:
    from collectors.ops_shared import reception_elapsed_days
    rest, lost = reception_ops_detail()
    if rest is None:
        return ('<details open class="grp"><summary>① 종합접수처(운영부) '
                 f'<span class="gc">{_NO_MEASURE}</span></summary>'
                 f'<div class="empty" style="padding:8px 14px;">{_NO_MEASURE}(접수처 조회 실패)</div>'
                 '<div class="sub-note">닫는 곳: 종합접수처 화면 처리자·처리메모·전달완료</div></details>')
    now = datetime.now()
    rest_sorted = sorted(rest, key=lambda r: -reception_elapsed_days(r, now))
    rows = []
    for r in rest_sorted:
        age = reception_elapsed_days(r, now)
        content = str(r.get("content") or "").strip()
        memo_on = "있음" if str(r.get("memo") or "").strip() else "—"
        rows.append(f'<tr><td>#{html.escape(str(r.get("regId") or "—"))}</td>'
                    f'<td>{html.escape(str(r.get("category") or "—"))}</td>'
                    f'<td>{html.escape(_reception_handler(r))}</td>'
                    f'<td class="age {age_cls(age)}">{age}일</td>'
                    f'<td title="{html.escape(content)}">{html.escape(short(content) if content else "—")}</td>'
                    f'<td>{memo_on}</td></tr>')
    body = "\n        ".join(rows) or '<tr><td colspan="6" class="empty">열린 건 없음</td></tr>'
    lost_line = ""
    if lost:
        lage = max((reception_elapsed_days(r, now) for r in lost), default=0)
        lost_line = f'<div class="sub-note">분실물 {len(lost)}건(담당 미배정 · 최장 {lage}일)</div>'
    return (f'<details open class="grp"><summary>① 종합접수처(운영부) <span class="gc">{len(rest)}건</span></summary>'
            '<table><tr><th>번호</th><th>분류</th><th>담당</th><th>경과</th><th>제목</th><th>처리메모</th></tr>'
            f'{body}</table>{lost_line}'
            '<div class="sub-note">닫는 곳: 종합접수처 화면 처리자·처리메모·전달완료</div></details>')


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


# 📄 보고 문서 선반 — GM업무 화면이 쓰는 그 원천(erp/modules.json 문서함 · /chairman/)을 읽어
#   같은 모양으로 그린다. 목록을 여기 적지 않는다(약속 L01).
#   회장님 오찬·평가 A3 는 실장·소장이 볼 것이 아니라 /auth/me 의 role 이 admin 일 때만 편다 —
#   이건 보기 편하라고 감추는 것이고, 실제 차단은 관문이 카드 권한으로 한다.
GM_DOC_SHELF = """<details class="grp" id="gm-docs" hidden><summary>📄 보고 문서 <span class="gc" id="gm-docs-cnt">—</span></summary>
        <table><tr><th style="width:340px">문서</th><th>설명</th></tr><tbody id="gm-docs-body"></tbody></table>
        <div class="sub-note">여는 곳: GM업무 화면 📄 보고 문서 — 같은 목록입니다</div></details>
        <script>
        (function(){
          var wrap = document.getElementById('gm-docs'), body = document.getElementById('gm-docs-body'),
              cnt = document.getElementById('gm-docs-cnt');
          fetch('/auth/me', {credentials:'same-origin'}).then(function(r){ return r.ok ? r.json() : null; })
          .then(function(me){
            if (!me || me.role !== 'admin') return;          // 실장·소장 화면엔 안 보인다
            return fetch('../../erp/modules.json?cb=' + Date.now()).then(function(r){ return r.json(); })
              .then(function(d){
                var rows = (d.modules || []).filter(function(m){
                  return m.appgroup === '문서함' && /\\/chairman\\//.test(m.path || ''); });
                if (!rows.length) return;
                rows.sort(function(a, b){ return String(b.path).localeCompare(String(a.path)); });
                cnt.textContent = rows.length + '장';
                body.innerHTML = rows.map(function(m){
                  var f = String(m.path || '').split('/').pop();
                  return '<tr><td><a href="' + f + '" target="_blank" rel="noopener">' +
                         (m.name || f) + '</a></td><td>' + (m.desc || '') + '</td></tr>';
                }).join('');
                wrap.hidden = false; wrap.open = true;
              });
          }).catch(function(){});      // 로컬 파일로 열면 /auth/me 가 없다 — 조용히 접어 둔다
        })();
        </script>"""


def ssot_detail_html(ssot_rows: "list | None") -> str:
    mine = ssot_ops_detail_rows(ssot_rows)
    if mine is None:
        return ('<details open class="grp"><summary>② 업무·결재 SSOT(운영부 전원) '
                 f'<span class="gc">{_NO_MEASURE}</span></summary>'
                 f'<div class="empty" style="padding:8px 14px;">{_NO_MEASURE}(업무 SSOT 조회 실패)</div>'
                 '<div class="sub-note">닫는 곳: 업무 현황 SSOT 화면 상태·종료일</div></details>')
    today = date.today()
    rows = []
    for r in mine:
        d = _parse_ymd(r.get("종료일"))
        due_disp = d.isoformat() if d else (str(r.get("종료일") or "").strip()[:10] or "—")
        od = (today - d).days if d else None
        od_td = f'<td class="age old">{od}일</td>' if od and od > 0 else '<td>—</td>'
        ap = str(r.get("결재요청") or "").strip() or "—"
        rows.append(f'<tr><td>{html.escape(str(r.get("담당자") or "—"))}</td>'
                    f'<td class="ti">{ssot_links(r)}</td>'
                    f'<td>{html.escape(due_disp)}</td>'
                    f'{od_td}'
                    f'<td>{html.escape(ap)}</td></tr>')
    body = "\n        ".join(rows) or '<tr><td colspan="5" class="empty">진행중·보류 없음</td></tr>'
    return (f'<details open class="grp"><summary>② 업무·결재 SSOT(운영부 전원) <span class="gc">{len(mine)}건</span></summary>'
            '<table><tr><th>담당</th><th>업무명</th><th>종료일</th><th>기한지남</th><th>결재요청</th></tr>'
            f'{body}</table>'
            '<div class="sub-note">닫는 곳: 업무 현황 SSOT 화면 상태·종료일</div></details>')


_CHK_BODY_RE = re.compile(r"^\s*□\s*\d*\)?\s*(.+)$")
_OWNER_TAG_RE = re.compile(r"담당:\s*([^·\n]+)")
_DUE_TAG_RE = re.compile(r"기한:\s*([^·\n]+)")


def parse_unchecked(note: str) -> list[str]:
    """progress_note 안 미완(□) 체크 줄만 — 완료(☑)는 뺀다."""
    return [ln.strip() for ln in str(note or "").split("\n") if ln.strip().startswith("□")]


def check_ops_detail_rows(objs: list) -> list[tuple[dict, str]]:
    """(카드, 체크줄) — 담당 이경연 실장 또는 dept 에 '운영부'가 든 카드의 미완 체크 전부.
    카드 dict 를 그대로 돌려준다 — 카드 id(GM업무 딥링크)와 docs(자료 링크)가 필요하다."""
    cards = [o for o in objs
             if str(o.get("owner") or "").strip() == "이경연 실장" or "운영부" in str(o.get("dept") or "")]
    out = []
    for o in cards:
        for ln in parse_unchecked(o.get("progress_note")):
            out.append((o, ln))
    return out


def check_detail_html(objs: list) -> str:
    pairs = check_ops_detail_rows(objs)
    rows = []
    for o, ln in pairs:
        title = str(o.get("title") or "").strip()
        oid = str(o.get("id") or "").strip()
        disp = html.escape(short(title) if title else "—")
        card = (f'<a href="GM업무.html#gm-{html.escape(oid, quote=True)}" target="_blank" '
                f'rel="noopener" title="{html.escape(title)}">{disp}</a>' if oid
                else f'<span title="{html.escape(title)}">{disp}</span>')
        body = _CHK_BODY_RE.sub(r"\1", ln)
        m_owner = _OWNER_TAG_RE.search(ln)
        has_owner = bool(m_owner) and m_owner.group(1).strip() not in ("", "(미정)")
        m_due = _DUE_TAG_RE.search(ln)
        has_due = bool(m_due) and m_due.group(1).strip() not in ("", "(미정)")
        rows.append(f'<tr><td class="ti">{card}{objective_docs_html(o)}</td>'
                    f'<td title="{html.escape(body)}">{html.escape(short(body))}</td>'
                    f'<td>{"있음" if has_owner else "—"}</td>'
                    f'<td>{"있음" if has_due else "—"}</td></tr>')
    body_html = "\n        ".join(rows) or '<tr><td colspan="4" class="empty">미완 체크 없음</td></tr>'
    return (f'<details open class="grp"><summary>③ 점검 현황(운영부) <span class="gc">{len(pairs)}건</span></summary>'
            '<table><tr><th>카드</th><th>체크</th><th>담당표기</th><th>완료예정일</th></tr>'
            f'{body_html}</table>'
            '<div class="sub-note">닫는 곳: GM업무 화면 체크</div></details>')


def chief_detail_blocks(ssot_rows: "list | None", objs: list) -> str:
    return (f'        {reception_detail_html()}\n'
            f'        {ssot_detail_html(ssot_rows)}\n'
            f'        {check_detail_html(objs)}\n')


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
        mi = date.today().month - 1
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
    mi = date.today().month - 1
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
           f'<span class="pgt">현재 {html.escape(_fmt_amt(cur, "원"))} / 목표 {html.escape(_fmt_amt(target, "원"))}'
           f' · 달성 {pct}%</span></span>')
    return bar, False


def row_html(no: int, seen_date: str, it: dict) -> str:
    age = days_since(seen_date)
    due = str(it.get("due") or "").strip() or "—"
    note = str(it.get("note") or "").strip()
    cn = cat_name(it)
    note_td = (f'<td class="note" title="{html.escape(note)}">{html.escape(short(note))}</td>'
               if note else '<td class="note">—</td>')
    # 원장에 업무 SSOT 열쇠(todo_id)가 있으면 그 카드로 바로 간다 — SSOT 조회가 실패한 날에도
    #   문서로 가는 길이 끊기지 않는다(GM 지시 2026-09-14).
    todo_id = str(it.get("todo_id") or "").strip()
    if todo_id:
        ss = (f'<a class="ss-link" href="{SSOT_PAGE}?item={quote(todo_id, safe="")}" '
              f'target="_blank" rel="noopener">SSOT 열기</a>')
    elif is_reception_item(it):
        ss = '<span class="ss-rc">접수처에서 닫음</span>'
    else:
        ss = '<span class="ss-no">SSOT 미등록</span>'
    who = str(it.get("owner") or "").strip()      # owner_select 가 escape 한다
    # 함께 하는 사람(with)은 리드와 한 칸에 두되 눈으로 갈린다 — GM 지시 2026-09-11
    #   「담당자 구분 확실하게」. 리드가 책임지고, 함께는 같이 한다.
    helper = str(it.get("with") or "").strip()
    helper_html = f'<div class="with">함께 {html.escape(helper)}</div>' if helper else ""
    return (f'<tr data-no="{no}"><td class="ck"><input type="checkbox" data-k="mgr-{no}"></td>'
            f'<td class="no">#{no}</td>'
            f'<td class="ti">{html.escape(str(it.get("issue") or ""))}'
            f'{f"<span class=cat>{html.escape(cn)}</span>" if cn else ""}</td>'
            f'<td class="own">{owner_select(no, who)}{helper_html}</td>'
            f'<td class="due">{html.escape(due)}</td>'
            f'{progress_cell(it)}'
            f'<td class="ss">{ss}</td>'
            f'{note_td}'
            f'<td class="age {age_cls(age)}">{age}일</td></tr>')


HEAD_ROW = ('<tr><th class="ck">✓</th><th class="no">번호</th><th>업무</th>'
            '<th class="own">담당</th><th class="due">기한</th><th class="pg">진척</th>'
            '<th class="ss">업무·결재 SSOT</th>'
            '<th>최근 상황</th><th class="age">경과</th></tr>')


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
KINDS = ("routine", "reception", "task")


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
    print("[selfcheck] 담당 드롭다운·중복 판정·note 청소 판정 OK")


def approval_badge(m: dict) -> str:
    """업무·결재 SSOT 행 하나의 진행·결재 상태를 배지 두 개로. 값이 없으면 안 지어낸다."""
    st = str(m.get("상태") or "").strip() or "상태없음"
    ap_req = str(m.get("결재요청") or "").strip()
    ap_st = str(m.get("결재상태") or "").strip()
    gm_sign = bool(str(m.get("GM싸인") or "").strip())
    rep_sign = bool(str(m.get("대표싸인") or "").strip())
    out = [f'<span class="ss-st">{html.escape(st)}</span>']
    if ap_st == "결재완료":
        who = "GM·대표" if (gm_sign and rep_sign) else ("GM" if gm_sign else "")
        out.append(f'<span class="ss-ap done">결재완료{(" " + who) if who else ""}</span>')
    elif ap_req:
        out.append(f'<span class="ss-ap wait">결재대기 {html.escape(ap_req)}</span>')
    return "".join(out)


def table(rows: list[str], empty: str) -> str:
    body = "\n          ".join(rows) or f'<tr><td colspan="9" class="empty">{empty}</td></tr>'
    return f'<table>\n          {HEAD_ROW}\n          {body}\n        </table>'


def top_html(items: list[tuple[int, str, dict, str]]) -> str:
    """먼저 볼 것 — 사람 상관없이 경과가 긴 순 5건."""
    cards = []
    for no, d, it, who in items:
        age = days_since(d)
        fl = "".join(f'<span class="fl">{f}</span>' for f in flags_of(it))
        note = str(it.get("note") or "").strip()
        cards.append(
            f'<div class="top-i"><span class="top-age {age_cls(age)}">{age}일</span>'
            f'<div class="top-b"><b>#{no} {html.escape(str(it.get("issue") or ""))}</b>{fl}'
            f'<div class="top-w">{html.escape(who)}'
            f'{" · " + html.escape(short(note, 46)) if note else ""}</div></div></div>')
    return "\n      ".join(cards)


def build() -> str:
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
    resp_html = resp_section(seen, ssot_rows, sales_data)   # 👤 책임 항목 4인 — seen·ssot_rows·매출 원자료 그대로 넘긴다
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

    # ② 열린 목록에서 가를 것 셋 — 원장은 그대로 두고 화면에서만 가른다.
    dup_of = find_dups(opens)
    aside_dup = [(n, *opens.pop(n)) for n in sorted(dup_of)]
    aside_rt = [(n, *opens.pop(n)) for n in sorted(n for n, (_d, it) in opens.items()
                                                   if kind_of(it) == "routine")]
    aside_rc = [(n, *opens.pop(n)) for n in sorted(n for n, (_d, it) in opens.items()
                                                   if kind_of(it) == "reception")]

    blocks = []
    counts = []
    shown: list[tuple[int, str, dict, str]] = []

    for name, dept, room in MANAGERS:
        mine = sorted(((n, d, it) for n, (d, it) in opens.items()
                       if str(it.get("owner") or "").strip() == name), key=lambda x: x[0])
        counts.append((name, len(mine)))
        shown += [(n, d, it, name) for n, d, it in mine]
        blocks.append(f'''      <div class="blk">
        <h2>{html.escape(name)} <span class="sub">{html.escape(dept)} · {html.escape(room)} · 열린 건 {len(mine)}건</span></h2>
        {table([row_html(n, d, it) for n, d, it in mine], "열린 건 없음")}
      </div>''')

    # ★MANAGERS 밖 담당(예: 최준용M)도 반드시 어딘가에 보인다 — 2026-09-11 사고: 상가 4건 담당을
    #   최준용M 으로 바꾸자 사람별 블록(3인)에도, 담당 미정(빈칸)에도 안 걸려 화면에서 통째로
    #   사라졌다(GM 「업무SSOT에서 분리수거장 시안물 부착 업무가 사라졌어요」). 이름을 늘리는 대신
    #   「그 밖의 담당」 한 자리를 두어, 앞으로 어떤 이름이 와도 사라지지 않게 한다.
    mgr_names = {m[0] for m in MANAGERS}
    others = sorted(((n, d, it) for n, (d, it) in opens.items()
                     if str(it.get("owner") or "").strip()
                     and str(it.get("owner") or "").strip() not in mgr_names), key=lambda x: x[0])
    if others:
        shown += [(n, d, it, str(it.get("owner") or "").strip()) for n, d, it in others]
        blocks.append(f'''      <div class="blk">
        <h2>그 밖의 담당 <span class="sub">위 세 분이 아닌 분께 배정된 것 · {len(others)}건 ·
          그 방에 안 계신 분이면 실장·소장을 거쳐 전달됩니다</span></h2>
        {table([row_html(n, d, it) for n, d, it in others], "없음")}
      </div>''')

    unassigned = sorted(((n, d, it) for n, (d, it) in opens.items()
                         if not str(it.get("owner") or "").strip()), key=lambda x: x[0])
    shown += [(n, d, it, "담당 미정") for n, d, it in unassigned]

    # 성격별 묶음 — 각 묶음은 접힘, 제목에 건수. 어디에도 안 걸리면 「기타」.
    order = [g[0] for g in GROUPS] + ["기타"]
    buckets: dict[str, list] = {k: [] for k in order}
    for n, d, it in unassigned:
        buckets[group_of(it)].append((n, d, it))
    groups_html = "\n        ".join(
        f'<details class="grp"><summary>{html.escape(k)} <span class="gc">{len(v)}건</span></summary>\n        '
        + table([row_html(n, d, it) for n, d, it in v], "없음") + "\n        </details>"
        for k, v in buckets.items() if v)
    blocks.append(f'''      <div class="blk">
        <h2>담당 미정 <span class="sub">GM 이 세 사람 중 누구 몫인지 정하면 그 사람 목차로 옮긴다 · {len(unassigned)}건 · 성격별로 묶어 접어 뒀습니다</span></h2>
        <div class="grps">
        {groups_html or '<div class="empty" style="padding:10px 14px;">없음</div>'}
        </div>
      </div>''')

    if moved:
        moved_sorted = sorted(moved, key=lambda x: x[0])
        moved_rows = "\n        ".join(
            f'<li>#{no} {html.escape(str(it.get("issue") or ""))}'
            f'<span class="mvd">→ <a class="mvd-link" target="_blank" rel="noopener"'
            f' href="{SSOT_PAGE}{("?item=" + quote(str(m.get("id")), safe="")) if m.get("id") else ""}">'
            f'SSOT: {html.escape(str(m.get("업무명") or ""))}</a> '
            f'{approval_badge(m)}'
            f'<span class="mvd-id">{"id로 연결" if matched_by == "id" else "제목으로 연결"}</span></span></li>'
            for no, d, it, m, matched_by in moved_sorted)
        blocks.append(f'''      <div class="blk">
        <details class="grp"><summary>업무 SSOT 로 넘어간 것 <span class="gc">{len(moved)}건</span></summary>
        <ul class="mvlist">
        {moved_rows}
        </ul>
        </details>
      </div>''')

    if aside_rt:
        # 책임은 사람별로 갈라 보인다(GM 지시 2026-09-11 「이경연 실장뿐이 아니라 이정헌 소장,
        #   나우열M 도 지정해줘」·「상시책임보단 책임 으로 단일로」). 한 덩어리로 두면 누가 무엇을
        #   책임지는지가 안 보인다 — 이름이 먼저고 그 아래 자기 줄이다.
        by_who: dict[str, list] = {}
        for n, d, it in aside_rt:
            by_who.setdefault(str(it.get("owner") or "담당 미정").strip() or "담당 미정", []).append((n, d, it))
        order = [m[0] for m in MANAGERS]
        names = [w for w in order if w in by_who] + [w for w in by_who if w not in order]
        inner = "\n        ".join(
            f'<h3 class="rsp">{html.escape(w)} <span class="gc">{len(by_who[w])}건</span></h3>\n        '
            + table([row_html(n, d, it) for n, d, it in by_who[w]], "없음")
            for w in names)
        blocks.insert(0, f'''      <div class="blk">
        <h2>책임 <span class="sub">끝나는 일이 아니라 계속 보는 자리 · {len(aside_rt)}건 ·
          이 줄은 완료로 닫지 않습니다 — 아래 「업무」와 구분해 주십시오</span></h2>
        {inner}
      </div>''')

    if aside_rc:
        blocks.append(f'''      <div class="blk">
        <details class="grp"><summary>다른 곳에서 닫힌 것 <span class="gc">{len(aside_rc)}건</span>
          <span class="gw">종합접수처에서 열리고 그 화면에서 닫는 건 — 여기서 하실 일은 없습니다</span></summary>
        {table([row_html(n, d, it) for n, d, it in aside_rc], "없음")}
        </details>
      </div>''')

    if aside_dup:
        dup_rows = "\n        ".join(
            f'<li>#{n} {html.escape(str(it.get("issue") or ""))}'
            f'<span class="mvd">→ 같은 건이 <b>#{dup_of[n]}</b> 로 새로 잡혀 있습니다(날짜가 뒤인 쪽을 살렸습니다)</span></li>'
            for n, d, it in aside_dup)
        blocks.append(f'''      <div class="blk">
        <details class="grp"><summary>중복 — 새 번호로 이어진 것 <span class="gc">{len(aside_dup)}건</span>
          <span class="gw">원장 상태는 그대로입니다 · 화면에서만 내렸습니다</span></summary>
        <ul class="mvlist">
        {dup_rows}
        </ul>
        </details>
      </div>''')

    ssot_note = ""
    if not ssot_ok:
        ssot_note = '<span class="b2 fail">⚠ 업무 SSOT 대조 실패 — 겹친 건이 그대로 보일 수 있습니다.</span>'
    elif moved:
        ssot_note = (f'<span class="b2">업무·결재 SSOT 에 올라간 것 {len(moved)}건 · 다른 곳에서 닫힌 것 '
                     f'{len(aside_rc)}건 · 중복 {len(aside_dup)}건은 맨 아래 접힘 목록으로 내렸습니다 · '
                     f'<b>여기 남은 {len(shown)}건이 업무 SSOT 에 올려야 하는 것</b>입니다.</span>')

    top5 = sorted(shown, key=lambda x: (-days_since(x[1]), x[0]))[:5]
    head = " · ".join(f"{n} {c}건" for n, c in counts)
    total = len(shown)
    oldest = max((days_since(d) for _, d, _, _ in shown), default=0)
    # 세 번째 숫자는 「급한 것이 몇 개인가」 — 아래 표의 빨간 경과(14일 이상)와 같은 기준이다.
    stale = sum(1 for _, d, _, _ in shown if days_since(d) >= 14)

    return f'''<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>중간관리자 업무</title>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;700;900&family=Noto+Serif+KR:wght@700&display=swap" rel="stylesheet">
<style>
  * {{ box-sizing:border-box; margin:0; padding:0; }}
  :root {{ --ink:#101418; --navy:#14304E; --navy-bg:#EDF1F6; --line:#E3E7EB; --dim:#6B7683; --warn:#96601A; --bad:#9E2A2A; }}
  body {{ font-family:'Noto Sans KR',sans-serif; color:var(--ink); background:#F4F6F8; padding:22px 18px 60px; }}
  .wrap {{ max-width:100%; margin:0; }}
  h1 {{ font-family:'Noto Serif KR',serif; font-size:27px; letter-spacing:-.6px; }}
  .lede {{ margin-top:6px; color:var(--dim); font-size:14px; line-height:1.7; }}
  .bar {{ margin-top:14px; background:var(--navy); color:#fff; padding:10px 14px; font-size:14px; font-weight:700; line-height:1.6; }}
  .bar .b2 {{ display:block; font-weight:400; font-size:13px; opacity:.85; }}
  .blk {{ background:#fff; border:1px solid var(--line); margin-top:14px; }}
  h2 {{ font-size:16px; padding:10px 14px; background:var(--navy-bg); color:var(--navy); border-bottom:1px solid var(--line); }}
  h2 .sub {{ font-weight:400; color:var(--dim); font-size:13px; margin-left:8px; }}
  /* 👤 책임 항목 4인(GM 지시 2026-09-14) — .blk·table 결 그대로, 칸 너비만 추가 */
  section.resp {{ background:#fff; border:1px solid var(--line); margin-top:14px; }}
  section.resp > h2 {{ background:var(--navy); color:#fff; }}
  .rp-person {{ border-top:1px solid var(--line); }}
  .rp-person:first-child {{ border-top:0; }}
  .rp-person h3 {{ padding:9px 14px; font-size:14.5px; color:var(--navy); background:var(--navy-bg); }}
  table.resp-tb th.ri, table.resp-tb td.ri {{ width:15%; font-weight:700; }}
  table.resp-tb th.rc, table.resp-tb td.rc {{ width:24%; color:var(--dim); font-size:13px; }}
  table.resp-tb th.rp, table.resp-tb td.rp {{ width:26%; }}
  table.resp-tb td.rp.bad {{ color:var(--bad); font-weight:700; }}
  table.resp-tb th.rg, table.resp-tb td.rg,
  table.resp-tb th.rf, table.resp-tb td.rf {{ width:17.5%; font-size:13px; }}
  table {{ width:100%; border-collapse:collapse; font-size:14px; }}
  th, td {{ padding:8px 10px; border-bottom:1px solid var(--line); vertical-align:top; text-align:left; }}
  th {{ background:#FAFBFC; font-size:12.5px; color:var(--dim); font-weight:700; }}
  td.ck, th.ck {{ width:34px; text-align:center; }}
  td.no, th.no {{ width:62px; color:var(--dim); font-weight:700; }}
  td.due, th.due {{ width:104px; }}
  td.age, th.age {{ width:64px; text-align:right; color:var(--dim); font-variant-numeric:tabular-nums; }}
  td.age.warn {{ color:var(--warn); font-weight:700; }}
  td.age.old {{ color:var(--bad); font-weight:900; }}
  td.note {{ color:var(--dim); }}
  /* 진척 칸·함께 하는 사람·책임 사람머리 (GM 지시 2026-09-11) */
  td.pg, th.pg {{ width:132px; }}
  .pg .bar {{ height:6px; border-radius:3px; background:var(--line); overflow:hidden; }}
  .pg .bar i {{ display:block; height:100%; }}
  .pg .pg-low {{ background:var(--bad); }}
  .pg .pg-mid {{ background:var(--warn); }}
  .pg .pg-ok {{ background:#2e7d32; }}
  .pg .pgn {{ font-size:11.5px; font-weight:800; margin-right:6px; }}
  .pg .pgt {{ font-size:11px; color:var(--dim); }}
  /* 👤 책임 항목 표 안 매출 진척(span.pg) — td.pg(#132px 고정폭) 재사용, 이 칸은 폭 자유 */
  td.rp .pg {{ display:block; }}
  td.rp .pg .pgt {{ display:block; margin-top:3px; }}
  td.own .with {{ font-size:11.5px; color:var(--dim); margin-top:3px; }}
  h3.rsp {{ margin:16px 0 6px; font-size:14px; font-weight:800; }}
  h3.rsp .gc {{ font-size:12px; font-weight:600; color:var(--dim); margin-left:6px; }}
  .cat {{ display:inline-block; margin-left:6px; font-size:11.5px; color:var(--dim); border:1px solid var(--line); padding:0 5px; }}
  tr.done td.ti {{ text-decoration:line-through; color:var(--dim); }}
  .empty {{ color:var(--dim); }}
  /* 먼저 볼 것 */
  .top {{ background:#fff; border:1px solid var(--line); border-left:4px solid var(--bad); margin-top:14px; padding:12px 14px 14px; }}
  .top h2 {{ background:none; border:0; padding:0 0 8px; font-size:16px; }}
  .top .why {{ color:var(--dim); font-size:13px; font-weight:400; margin-left:8px; }}
  .top-i {{ display:flex; gap:12px; align-items:baseline; padding:7px 0; border-top:1px solid var(--line); }}
  .top-age {{ flex:0 0 58px; text-align:right; font-size:16px; font-weight:900; color:var(--dim); font-variant-numeric:tabular-nums; }}
  .top-age.warn {{ color:var(--warn); }}
  .top-age.old {{ color:var(--bad); }}
  .top-b {{ flex:1 1 auto; min-width:0; }}
  .top-b b {{ font-size:15px; }}
  .top-w {{ color:var(--dim); font-size:13px; margin-top:2px; }}
  .fl {{ display:inline-block; margin-left:6px; font-size:11.5px; font-weight:700; color:var(--bad); border:1px solid var(--bad); padding:0 5px; vertical-align:middle; }}
  /* 담당 미정 성격별 묶음 */
  .grps {{ padding:6px 0; }}
  .grp {{ border-bottom:1px solid var(--line); }}
  .grp > summary {{ cursor:pointer; padding:9px 14px; font-size:14px; font-weight:700; color:var(--navy); list-style:none; }}
  .grp > summary::-webkit-details-marker {{ display:none; }}
  .grp > summary::before {{ content:"▸ "; color:var(--dim); }}
  .grp[open] > summary::before {{ content:"▾ "; }}
  .grp .gc {{ font-weight:400; color:var(--dim); font-size:13px; margin-left:6px; }}
  .grp .gw {{ font-weight:400; color:var(--dim); font-size:12.5px; margin-left:6px; }}
  /* 실장 건별 목록 3종(GM 지시 2026-09-14) — .grp details 재사용, 맨 아래 안내줄만 추가 */
  .sub-note {{ padding:6px 14px 10px; font-size:12.5px; color:var(--dim); border-top:1px solid var(--line); }}
  .own {{ white-space:nowrap; }}
  .own-sel {{ max-width:118px; padding:3px 4px; border:1px solid var(--line); border-radius:6px;
              background:#fff; color:inherit; font:inherit; font-size:12.5px; }}
  .own-sel:focus {{ outline:2px solid rgba(183,159,138,0.5); }}
  .own-sel.saved {{ border-color:#6abf7b; }}
  .ss-rc {{ display:inline-block; padding:1px 6px; border-radius:6px; font-size:11.5px;
            background:rgba(255,255,255,0.08); color:var(--dim); }}
  .ss {{ white-space:nowrap; }}
  .ss-no {{ display:inline-block; padding:1px 6px; border-radius:6px; font-size:11.5px;
            background:rgba(237,91,63,0.14); color:#ED5B3F; }}
  .ss-link {{ display:inline-block; padding:1px 6px; border-radius:6px; font-size:11.5px;
              background:rgba(255,255,255,0.08); color:inherit; text-decoration:underline dotted; }}
  /* 문서 링크 줄 — 업무명·카드명 아래 📄 기획안 · 🎯 결과보고 · 📎 첨부 */
  .dcs {{ margin-top:3px; display:flex; flex-wrap:wrap; gap:4px; }}
  .dc {{ display:inline-block; padding:1px 6px; border-radius:6px; font-size:11.5px;
         background:rgba(255,255,255,0.08); color:var(--dim); text-decoration:none; }}
  .dc:hover {{ color:inherit; text-decoration:underline; }}
  .ss-st {{ display:inline-block; padding:1px 6px; border-radius:6px; font-size:11.5px;
            background:rgba(255,255,255,0.08); color:var(--dim); margin-right:4px; }}
  .ss-ap {{ display:inline-block; padding:1px 6px; border-radius:6px; font-size:11.5px; }}
  .ss-ap.done {{ background:rgba(106,191,123,0.16); color:#6abf7b; }}
  .ss-ap.wait {{ background:rgba(230,200,78,0.16); color:#e6c84e; }}
  .mvlist {{ list-style:none; padding:2px 14px 10px; }}
  .mvlist li {{ padding:5px 0; font-size:13.5px; border-top:1px solid var(--line); }}
  .mvlist li:first-child {{ border-top:0; }}
  .mvd {{ display:block; color:var(--dim); font-size:12.5px; margin-top:2px; }}
  .mvd-link {{ color:inherit; text-decoration:underline dotted; }}
  .mvd-id {{ color:#888; font-size:.85em; margin-left:.4em; }}
  .bar .fail {{ color:#FFD37A; }}
  .foot {{ margin-top:16px; color:var(--dim); font-size:13px; line-height:1.8; }}
  @media (max-width:640px) {{
    body {{ padding:16px 10px 50px; }}
    h1 {{ font-size:21px; }}
    table {{ font-size:13px; }}
    th, td {{ padding:6px 6px; }}
    td.due, th.due {{ width:72px; }}
    td.no, th.no {{ width:46px; }}
    td.age, th.age {{ width:48px; }}
    /* 좁은 폭에서 표를 억지로 구겨 넣지 않는다 — 블록만 옆으로 밀어서 본다. */
    .blk {{ overflow-x:auto; }}
    .blk table {{ min-width:620px; }}
    .top-age {{ flex:0 0 46px; font-size:15px; }}
  }}
</style>
</head>
<body>
<div class="wrap">
  <h1>중간관리자 업무 목차</h1>
  <div class="lede">이경연 실장 · 이정헌 소장 · 나우열M 세 사람의 <b>열린 업무</b>를 번호순으로 편 목차입니다.
    회신은 번호로 받습니다 — 「#번호 + 했다/진행중/언제」 한 줄.<br>
    체크는 GM 화면에만 남습니다(이 브라우저). 원장 상태는 실무진 회신이 오면 바뀝니다.</div>
  <div class="bar">기준 {date.today().isoformat()} · 열린 {total}건 · 가장 오래된 것 {oldest}일 · 14일 넘게 답 없는 것 {stale}건
    <span class="b2">{html.escape(head)} · 담당 미정 {len(unassigned)}건</span>
    {ssot_note}</div>

{resp_html}

  <div class="top">
    <h2>🔺 먼저 볼 것 <span class="why">사람 상관없이 오래 묵은 순 5건 — 여기부터 답을 받으세요</span></h2>
      {top_html(top5)}
  </div>

{chr(10).join(blocks)}
  <div class="foot">
    <b>이 목록은 무엇인가</b><br>
    ① 값은 매일 아침 카카오·텔레그램 방을 정리해 쌓는 원장(<code>_digest_ledger.json</code>)에서 그대로 옵니다 — 이 화면이 따로 적어 두는 건 없습니다.<br>
    ② 번호(#)는 건마다 처음 잡힌 그대로 고정입니다 — 목록이 바뀌어도 번호는 안 바뀌므로 그 번호로 이야기하시면 됩니다.<br>
    ③ 회신은 번호로 붙습니다 — 실무진이 방에 「#번호 + 했다/진행중/언제」로 답하면 다음 날 아침 정리에서 그 건의 「최근 상황」이 바뀌고, 끝난 건은 이 목록에서 내려갑니다.<br>
    갱신 = <code>python scripts/manager_task_index.py</code> · 경과 색 = 14일 이상 빨강 · 7~13일 주황.
  </div>
</div>
<script>
  // 체크 상태는 공용 보드에 남긴다(GM 지적 2026-09-10 "아무 추적 및 연동 관련된 부분이 어설픈데?").
  //   종전엔 localStorage 라 그 브라우저에만 남았다 — 다른 기기로 열거나 다른 사람이 보면
  //   아무 흔적이 없었다. GM_TASK_OWNERS 담당 칸이 쓰는 그 보드(GAS saveBoard)에 키만 하나
  //   더 둔다 — 새 저장소를 만들지 않는다(약속 L21). 저장은 최신 보드를 다시 읽어 내 값 하나만
  //   얹는 방식이라 남의 체크를 덮지 않는다.
  var BOARD_URL = 'https://script.google.com/macros/s/AKfycbyXw4ZaA6hLK567GC7NY33Y8SvNPW6kNtrXFz2OsSdFVBmCnZP-2oD-RQiX0IpekBu1/exec';
  var BOARD_KEY = 'MGR_TASK_DONE';
  var ERP_API_ON = /^(erp[.]wellperion[.]com|15[.]164[.]151[.]105)$/.test(location.hostname);
  var boardCache = {{}};
  function readBoard() {{
    var gas = function () {{
      return fetch(BOARD_URL + '?action=board&key=' + BOARD_KEY, {{cache:'no-store'}})
        .then(function (r) {{ return r.json(); }});
    }};
    if (!ERP_API_ON) return gas();
    return fetch('/api/board/' + BOARD_KEY, {{cache:'no-store'}})
      .then(function (r) {{ if (!r.ok) throw new Error('api ' + r.status); return r.json(); }})
      .catch(gas);
  }}
  function saveCheck(k, on) {{
    return readBoard().then(function (j) {{
      var fresh = (j && j.ok && j.board) ? j.board : {{}};
      if (on) fresh[k] = new Date().toISOString().slice(0, 16).replace('T', ' ');
      else delete fresh[k];
      boardCache = fresh;
      return fetch(BOARD_URL, {{method:'POST', headers:{{'Content-Type':'text/plain;charset=UTF-8'}},
                              body: JSON.stringify({{action:'saveBoard', key: BOARD_KEY, board: fresh}}),
                              redirect:'follow'}}).then(function (r) {{ return r.json(); }});
    }});
  }}
  var boxes = Array.prototype.slice.call(document.querySelectorAll('input[data-k]'));
  readBoard().then(function (j) {{
    boardCache = (j && j.ok && j.board) ? j.board : {{}};
    boxes.forEach(function (b) {{
      var when = boardCache[b.dataset.k];
      if (!when) return;
      b.checked = true;
      b.closest('tr').classList.add('done');
      b.title = '체크 ' + when;
    }});
  }}).catch(function (e) {{ console.warn('[목차] 체크 보드 읽기 실패', e && e.message); }});
  // ── 담당 지정 (GM 2026-09-10 "SSOT 등록건은 담당자도 설정할 수 있어야해") ──────────────
  //   저장 자리 = 같은 공용 보드의 다른 키(MGR_TASK_OWNER). 체크와 같은 방식이라 새 저장소가 없다.
  //   다음 갱신(manager_task_index.py)이 이 값을 읽어 원장 담당 빈칸을 채우고 사람별 표로 옮긴다.
  //   칸은 <select> 다(GM 2026-09-11 "드랍다운 항목에 넣어달라고 했는데") — 종전 datalist 는
  //   칸에 이름이 이미 있으면 목록이 안 펼쳐져 드롭다운으로 보이지 않았다. 후보 14명은
  //   파이썬(OWNER_CHOICES)이 서버에서 찍는다.
  var OWNER_KEY = 'MGR_TASK_OWNER';
  function readOwnerBoard() {{
    var gas = function () {{
      return fetch(BOARD_URL + '?action=board&key=' + OWNER_KEY, {{cache:'no-store'}})
        .then(function (r) {{ return r.json(); }});
    }};
    if (!ERP_API_ON) return gas();
    return fetch('/api/board/' + OWNER_KEY, {{cache:'no-store'}})
      .then(function (r) {{ if (!r.ok) throw new Error('api ' + r.status); return r.json(); }})
      .catch(gas);
  }}
  var owns = Array.prototype.slice.call(document.querySelectorAll('select[data-o]'));
  readOwnerBoard().then(function (j) {{
    var b = (j && j.ok && j.board) ? j.board : {{}};
    owns.forEach(function (inp) {{
      var v = b['mgr-' + inp.dataset.o];
      if (!v || inp.value) return;             // 원장에 이미 사람이 있으면 그 값을 덮지 않는다
      if (!inp.querySelector('option[value="' + v.replace(/"/g, '&quot;') + '"]')) {{
        var o = document.createElement('option'); o.value = v; o.textContent = v; inp.appendChild(o);
      }}
      inp.value = v;
      before[inp.dataset.o] = v;
    }});
  }}).catch(function (e) {{ console.warn('[목차] 담당 보드 읽기 실패', e && e.message); }});
  var before = {{}};
  owns.forEach(function (inp) {{ before[inp.dataset.o] = inp.value; }});
  owns.forEach(function (inp) {{
    inp.addEventListener('change', function () {{
      var v = inp.value.trim(), was = before[inp.dataset.o];
      if (v === was) return;
      inp.disabled = true;
      readOwnerBoard().then(function (j) {{
        var fresh = (j && j.ok && j.board) ? j.board : {{}};
        if (v) fresh['mgr-' + inp.dataset.o] = v; else delete fresh['mgr-' + inp.dataset.o];
        return fetch(BOARD_URL, {{method:'POST', headers:{{'Content-Type':'text/plain;charset=UTF-8'}},
                                body: JSON.stringify({{action:'saveBoard', key: OWNER_KEY, board: fresh}}),
                                redirect:'follow'}}).then(function (r) {{ return r.json(); }});
      }}).then(function (res) {{
        inp.disabled = false;
        if (res && res.ok) {{ before[inp.dataset.o] = v; inp.classList.add('saved');
                             setTimeout(function () {{ inp.classList.remove('saved'); }}, 1500); }}
        else {{ inp.value = was; alert('담당을 저장하지 못했습니다 — 잠시 뒤 다시 시도해 주세요.'); }}
      }}).catch(function () {{
        inp.disabled = false; inp.value = was;
        alert('담당을 저장하지 못했습니다 — 잠시 뒤 다시 시도해 주세요.');
      }});
    }});
  }});

  boxes.forEach(function (b) {{
    b.addEventListener('change', function () {{
      var on = b.checked;
      b.closest('tr').classList.toggle('done', on);
      b.disabled = true;
      saveCheck(b.dataset.k, on).then(function (res) {{
        b.disabled = false;
        if (!(res && res.ok)) {{ b.checked = !on; b.closest('tr').classList.toggle('done', !on);
                                alert('체크를 저장하지 못했습니다 — 잠시 뒤 다시 눌러 주세요.'); }}
      }}).catch(function () {{
        b.disabled = false; b.checked = !on; b.closest('tr').classList.toggle('done', !on);
        alert('체크를 저장하지 못했습니다 — 잠시 뒤 다시 눌러 주세요.');
      }});
    }});
  }});
</script>
</body>
</html>
'''


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="중간관리자 업무 목차 렌더")
    ap.add_argument("--clean-notes", action="store_true",
                    help="원장 note 에서 우리 발신 조각·똑같이 겹친 조각을 걷어낸다(원장을 고침)")
    ap.add_argument("--dry", action="store_true", help="--clean-notes 미리보기 — 파일은 안 고침")
    ap.add_argument("--selfcheck", action="store_true", help="판정 규칙 자가검사")
    args = ap.parse_args()
    if args.selfcheck:
        selfcheck()
    elif args.clean_notes:
        clean_notes(dry=args.dry)
    else:
        OUT.write_text(build(), encoding="utf-8")
        print(f"[manager_task_index] {OUT.relative_to(ROOT)} · {OUT.stat().st_size:,} bytes")
