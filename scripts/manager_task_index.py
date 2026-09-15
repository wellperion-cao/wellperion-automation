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
  · send_ops_digest 07:50 이 매일 build() 를 다시 돌린다 → 책임 항목 실측 스냅숏 원장
    status/manager_eval_history.json 의 이번 달 키가 매일 자동 갱신된다(분기·연 누적 · GM 지시 2026-09-15).

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


def week_block(seen: dict) -> str:
    """이번 주 한 장 (GM 지시 2026-09-14 「1주 단위로 진행된 업무·놓치는 업무도 체크해서 정리」).
    새 원장을 만들지 않는다 — 이미 있는 확인요청 원장의 날짜만 센다(약속 L21).
      · 끝난 것 = 최근 7일 안에 닫힌 번호
      · 새로 뜬 것 = 최근 7일 안에 원장에 처음 실린 번호
      · 멈춘 것 = 열려 있는데 7일 넘게 원장에 아무 기록이 없는 번호 — 이것이 놓치는 자리다.
    """
    first = first_seen_by_no()
    done, fresh, stuck = [], [], []
    for n, (d, it) in seen.items():
        closed = str(it.get("status", "")).lower() in DONE
        age = days_since(d)
        if closed and age <= 7:
            done.append((n, d, it))
        elif not closed:
            if days_since(first.get(n, d)) <= 7:
                fresh.append((n, d, it))
            elif age > 7:
                stuck.append((n, d, it))
    stuck.sort(key=lambda x: days_since(x[1]), reverse=True)
    done.sort(key=lambda x: x[1], reverse=True)
    fresh.sort(key=lambda x: x[0], reverse=True)

    def lines(rows, tail):
        if not rows:
            return '<div class="wk-none">없음</div>'
        out = []
        for n, d, it in rows[:12]:
            who = html.escape(str(it.get("owner") or "담당 미정").strip() or "담당 미정")
            ttl = html.escape(short(str(it.get("issue") or ""), 46))
            out.append(f'<li><b>#{n}</b> {ttl} <span class="wk-who">{who}</span>'
                       f'<span class="wk-age">{tail(d)}</span></li>')
        more = f'<li class="wk-none">외 {len(rows) - 12}건</li>' if len(rows) > 12 else ''
        return f'<ul class="wk-list">{"".join(out)}{more}</ul>'

    return f'''  <section class="week">
    <h2>이번 주 <span class="sub">최근 7일 · 끝난 것 {len(done)} · 새로 뜬 것 {len(fresh)} ·
      한 주 넘게 멈춘 것 {len(stuck)}</span></h2>
    <div class="wk-cols">
      <div class="wk-col"><h3>🏁 끝난 것</h3>{lines(done, lambda d: f"{d[5:]} 닫힘")}</div>
      <div class="wk-col"><h3>🆕 새로 뜬 것</h3>{lines(fresh, lambda d: f"{d[5:]} 접수")}</div>
      <div class="wk-col wk-warn"><h3>⏸ 멈춘 것 — 여기가 놓치는 자리</h3>{lines(stuck, lambda d: f"{days_since(d)}일째")}</div>
    </div>
  </section>'''


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
RESP_PEOPLE = ["김남욱 GM", "이경연 실장", "이정헌 소장", "나우열M"]
_NO_MEASURE = "미수집"
SSOT_DONE = {"완료", "폐기", "완료됨"}
OPS_DEPT_STAFF = ["이경연 실장", "최준용M", "임정은M", "윤병현AM", "백승화 사원", "진수아 사원", "이지영 사원"]
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
    """종합접수처 부서별 열린·7일↑·담당 미배정 — 건별 목록①과 같은 필터(분실물 제외)로 센다
    (GM 지적 2026-09-14 — 목록은 5건인데 칸은 27건으로 분실물이 섞여 있었다).
    1영업일 첫처리는 첫처리 시각 필드가 없어 잴 수 없다(지어내지 않는다·기준 칸에만 남긴다)."""
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
    """업무·결재 SSOT(운영부 전원) — 진행중·보류(건별 목록②와 같은 수) · 지난주/이번 주 완료(기준 15) ·
    기한 지난 · 결재대기. 「대상행」(완료 행까지 센 수라 뜻 없음) 대신 목록②와 같은 원천으로 센다
    (GM 지적 2026-09-14 — 월요일 아침에 「이번 주 0」만 보이면 오해)."""
    if rows is None:
        return f"{_NO_MEASURE}(업무 SSOT 조회 실패)", False
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)
    last_monday = monday - timedelta(days=7)
    last_sunday = monday - timedelta(days=1)
    mine = [r for r in rows if str(r.get("담당자") or "").strip() in OPS_DEPT_STAFF]

    def done_between(start: date, end: date) -> int:
        n = 0
        for r in mine:
            if str(r.get("상태") or "") in SSOT_DONE:
                cd = _parse_ymd(r.get("완료일")) or _parse_ymd(r.get("수정일"))
                if cd and start <= cd <= end:
                    n += 1
        return n

    done_last = done_between(last_monday, last_sunday)
    done_week = done_between(monday, sunday)
    open_rows = ssot_ops_detail_rows(rows) or []
    overdue = sum(1 for r in open_rows if (d := _parse_ymd(r.get("종료일"))) and d < today)
    pend = sum(1 for r in mine if str(r.get("결재요청") or "").strip() and str(r.get("결재상태") or "") != "결재완료")
    md = lambda d: f"{d.month}/{d.day}"
    text = (f"진행중·보류 {len(open_rows)}건 · 지난주({md(last_monday)}~{md(last_sunday)}) 완료 {done_last}/15 · "
            f"이번 주 완료 {done_week}/15 · 기한 지난 {overdue}건 · 결재대기 {pend}건")
    return text, done_week < 15 or overdue > 0


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


def _no_measure_cell(reason: str) -> tuple[str, bool]:
    return f"{_NO_MEASURE}({reason})", False


RESP_HEAD = ('<tr><th class="ri">항목</th><th class="rc">기준(어떻게 평가)</th>'
             '<th class="rp">이번 달 진척(실측)</th><th class="rg">잘한 것</th>'
             '<th class="rf">보완할 것</th></tr>')


def _plain(s: str) -> str:
    """진척 막대 HTML(raw=True) 행의 실측 칸 → 태그 벗긴 텍스트(원장 저장용)."""
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s))).strip()


def resp_table(person: str, rows_def: list, ev: dict) -> tuple[str, dict]:
    """행별 detail_fn(5번째 자리)이 있으면 그 행을 토글로 만든다 — 클릭하면 바로 아래 tr 에
    내역이 펼쳐진다(GM 지시 2026-09-14 "종합접수처 내역들은 토글로 열면은 내역볼 수 있게").
    새 상태 저장소는 안 만든다 — 펼침 여부는 화면에서만(기본 접힘), 원장은 그대로.
    돌려주는 둘째 값 = 이 사람의 실측 스냅숏 {항목: {text, bad, good, fix}} — 표와 원장이 같은 계산을 한 번만 쓴다."""
    trs = []
    snap: dict = {}
    for entry in rows_def:
        item, crit, fn = entry[0], entry[1], entry[2]
        raw = entry[3] if len(entry) > 3 else False  # True = fn 이 이미 안전한 진척 막대 HTML 을 낸다
        detail_fn = entry[4] if len(entry) > 4 else None
        text, bad = fn()
        good, fix = eval_cell(ev, person, item)
        snap[item] = {"text": _plain(text) if raw else text, "bad": bool(bad), "good": good, "fix": fix}
        cls = "rp bad" if bad else "rp"
        item_cell = (f'<span class="rp-arrow">▸</span> {html.escape(item)}' if detail_fn
                     else html.escape(item))
        tr_open = '<tr class="rp-toggle">' if detail_fn else '<tr>'
        trs.append(f'{tr_open}<td class="ri">{item_cell}</td>'
                   f'<td class="rc">{html.escape(crit)}</td>'
                   f'<td class="{cls}">{text if raw else html.escape(text)}</td>'
                   f'<td class="rg">{html.escape(good)}</td>'
                   f'<td class="rf">{html.escape(fix)}</td></tr>')
        if detail_fn:
            trs.append(f'<tr class="rp-detail" hidden><td colspan="5">{detail_fn()}</td></tr>')
    return (f'<table class="resp-tb">\n          {RESP_HEAD}\n          '
            + "\n          ".join(trs) + '\n        </table>'), snap


def save_eval_history(month_snap: dict) -> dict:
    """이번 달 키만 덮어쓴다(그 달의 최신) · 다른 달 키는 그대로(분기·연 누적). 되돌려주는 값 = 원장 전체."""
    try:
        d = json.loads(HIST_PATH.read_text(encoding="utf-8"))
    except Exception:
        d = {}
    months = d.get("months") if isinstance(d.get("months"), dict) else {}
    months[date.today().strftime("%Y-%m")] = month_snap
    d = {"_doc": "중간관리자 책임 항목 실측 스냅숏 — manager_task_index.py 가 렌더 때마다 이번 달 키를 덮어쓴다"
                 "(send_ops_digest 07:50 매일). months[YYYY-MM][사람][항목] = {text 실측, bad 이상, good 잘한 것, fix 보완할 것}."
                 " GM업무 리더 현황 띠·중간관리자 업무목차 「분기 누적」 절이 읽는다. 손으로 고치지 않는다.",
         "updated_at": date.today().isoformat(), "months": dict(sorted(months.items()))}
    HIST_PATH.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    return d


def _quarter_of(ym: str) -> tuple[int, int]:
    y, m = int(ym[:4]), int(ym[5:7])
    return y, (m - 1) // 3 + 1


def _quarter_tables(months: dict, keys: list) -> str:
    """분기 한 개(달 키 3개) → 사람별 표: 항목 | 달1 | 달2 | 달3 | 분기 잘한 것 | 분기 보완할 것."""
    head = ('<tr><th class="ri">항목</th>' + "".join(f'<th class="rq">{int(k[5:7])}월</th>' for k in keys)
            + '<th class="rg">분기 잘한 것</th><th class="rf">분기 보완할 것</th></tr>')
    blocks = []
    for person in RESP_PEOPLE:
        items: list[str] = []
        for k in keys:
            for it in (months.get(k) or {}).get(person) or {}:
                if it not in items:
                    items.append(it)
        trs = []
        for it in items:
            cells, goods, fixes = [], [], []
            for k in keys:
                c = ((months.get(k) or {}).get(person) or {}).get(it)
                if not c:
                    cells.append('<td class="rq">—</td>')
                    continue
                cells.append(f'<td class="{"rq bad" if c.get("bad") else "rq"}">{html.escape(str(c.get("text") or "—"))}</td>')
                for src, dst in ((c.get("good"), goods), (c.get("fix"), fixes)):
                    v = str(src or "").strip()
                    if v and v != "—" and v not in dst:
                        dst.append(v)
            trs.append(f'<tr><td class="ri">{html.escape(it)}</td>{"".join(cells)}'
                       f'<td class="rg">{html.escape(" · ".join(goods) or "—")}</td>'
                       f'<td class="rf">{html.escape(" · ".join(fixes) or "—")}</td></tr>')
        if not trs:
            trs.append(f'<tr><td class="ri">—</td><td class="rq" colspan="{len(keys) + 2}">스냅숏 없음</td></tr>')
        blocks.append(f'      <div class="rp-person">\n        <h3>{html.escape(person)}</h3>\n        '
                      f'<table class="resp-tb">\n          {head}\n          ' + "\n          ".join(trs)
                      + '\n        </table>\n      </div>')
    return "\n".join(blocks)


def quarter_section(hist: dict) -> str:
    """📅 분기 누적 — 이번 분기(오늘 기준) 표 + 지난 분기(원장에 있으면) <details>. GM업무 띠가 #resp-q 로 온다."""
    months = hist.get("months") or {}
    today = date.today()
    y, q = _quarter_of(today.strftime("%Y-%m"))
    cur = [f"{y}-{m:02d}" for m in range(3 * q - 2, 3 * q + 1)]
    past = sorted({_quarter_of(k) for k in months if k not in cur}, reverse=True)
    past_html = "".join(
        f'\n    <details><summary>{py}년 {pq}분기</summary>\n'
        f'{_quarter_tables(months, [f"{py}-{mm:02d}" for mm in range(3 * pq - 2, 3 * pq + 1)])}\n    </details>'
        for py, pq in past)
    return f'''  <section class="resp-q" id="resp-q">
    <h2>📅 분기 누적 — 책임 항목 <span class="sub">{y}년 {q}분기 · 달마다 마지막 실측이 남습니다(매일 07:50 자동)</span></h2>
{_quarter_tables(months, cur)}{past_html}
  </section>'''


def resp_section(seen: dict, ssot_rows: "list | None", sales_data: "dict | None" = None) -> str:
    ev = load_eval()
    objs = load_month_objectives()
    mgr_names = ["이경연 실장", "이정헌 소장", "나우열M"]

    rows_def = {
        # GM 확정 2026-09-14 16:5x 「자동화 및 자율화(ERP+브로제이) 진척율 // 웰페리온 비즈니스 확장건 //
        #   회장님&대표님 지시 이렇게 3개로만」 — 종전 4개(카드 진척·회신 짝·결재 처리·주간 미팅)는 뺐다.
        "김남욱 GM": [
            ("자동화·자율화(ERP+브로제이) 진척률", "AWS 이관 표 영역별 완료 · 브로제이 카드 체크 완료율",
             lambda: automation_cell(objs)),
            ("웰페리온 비즈니스 확장", "확장 로드맵 항목 상태 · 시보(확장) 배 진행·완료",
             lambda: expansion_cell()),
            ("회장님·대표님 지시", "지시 카드 체크 완료율 · 기한 지난 것 0",
             lambda: directive_cell(objs)),
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
             "주 15건 완료(운영부 전원 합산) + 기획안·보고는 결재요청 칸까지 채워 제출",
             lambda: ops_ssot_cell(ssot_rows), False, lambda: ssot_detail_html(ssot_rows)),
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
            ("소통", "확인요청 회신율 · 최장 경과일",
             lambda: ledger_reply_cell(seen, "나우열M")),
        ],
    }

    blocks = []
    month_snap: dict = {}
    for person in RESP_PEOPLE:
        tbl, month_snap[person] = resp_table(person, rows_def[person], ev)
        if person == "이경연 실장":
            extra = chief_detail_blocks(ssot_rows)
        else:
            extra = ""
        # 📄 보고 문서 선반은 이 화면에 두지 않는다 (GM 지시 2026-09-14 「보고문서 관련해서는
        # GM업무로 이관해, 중복이네」). 같은 목록이 GM업무 화면에 이미 있다 — 한 곳만 둔다(약속 L01).
        blocks.append(f'      <div class="rp-person">\n        <h3>{html.escape(person)}</h3>\n        '
                       f'{tbl}\n{extra}      </div>')
    hist = save_eval_history(month_snap)   # 표를 만든 그 값으로 원장 이번 달 키 갱신(계산 한 번)
    return f'''  <section class="resp">
    <h2>👤 책임 항목 — 4인</h2>
{chr(10).join(blocks)}
  </section>
{quarter_section(hist)}'''


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


def reception_toggle_detail_html() -> str:
    """책임 표 「종합접수처(운영부)」 행을 클릭하면 펼쳐지는 내역 — 접수자·전달 대상 칸
    포함(GM 지시 2026-09-14 "누가 접수했고, 누구에게 전달해야하는지도 정리가 되면"). 원천은
    reception_dept_detail 그대로(진척 칸과 같은 필터 · 약속 L21)."""
    from collectors.ops_shared import reception_elapsed_days
    rest, lost = reception_dept_detail("운영부")
    if rest is None:
        return (f'<div class="empty" style="padding:8px 14px;">{_NO_MEASURE}(접수처 조회 실패)</div>'
                 '<div class="sub-note">닫는 곳: 종합접수처 화면 처리자·처리메모·전달완료</div>')
    now = datetime.now()
    rest_sorted = sorted(rest, key=lambda r: -reception_elapsed_days(r, now))
    rows = []
    for r in rest_sorted:
        age = reception_elapsed_days(r, now)
        content = str(r.get("content") or "").strip()
        memo_on = "있음" if str(r.get("memo") or "").strip() else "—"
        rows.append(f'<tr><td>#{html.escape(str(r.get("regId") or "—"))}</td>'
                    f'<td>{html.escape(str(r.get("category") or "—"))}</td>'
                    f'<td>{html.escape(_reception_reporter(r))}</td>'
                    f'<td>{html.escape(_reception_deliver_to(r, "운영부"))}</td>'
                    f'<td class="age {age_cls(age)}">{age}일</td>'
                    f'<td title="{html.escape(content)}">{html.escape(short(content) if content else "—")}</td>'
                    f'<td>{memo_on}</td></tr>')
    body = "\n        ".join(rows) or '<tr><td colspan="7" class="empty">열린 건 없음</td></tr>'
    lost_line = ""
    if lost:
        lage = max((reception_elapsed_days(r, now) for r in lost), default=0)
        lost_line = f'<div class="sub-note">분실물 {len(lost)}건(담당 미배정 · 최장 {lage}일)</div>'
    return ('<table><tr><th>번호</th><th>분류</th><th>접수자</th><th>전달 대상</th><th>경과</th>'
            '<th>제목</th><th>처리메모</th></tr>'
            f'{body}</table>{lost_line}'
            '<div class="sub-note">닫는 곳: 종합접수처 화면 처리자·처리메모·전달완료</div>')


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


def check_detail_html(objs: list) -> str:
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
        disp = html.escape(short(title) if title else "—")
        card = (f'<a href="GM업무.html#gm-{html.escape(oid, quote=True)}" target="_blank" '
                f'rel="noopener" title="{html.escape(title)}">{disp}</a>' if oid
                else f'<span title="{html.escape(title)}">{disp}</span>')
        card_cell = ('<td class="ti ti-cont"></td>' if same
                     else f'<td class="ti">{card}{objective_docs_html(o)}</td>')
        body = _CHK_BODY_RE.sub(r"\1", ln)
        owner_text = _check_owner_text(o, ln)
        rows.append(f'<tr>{card_cell}'
                    f'<td title="{html.escape(body)}">{html.escape(short(body))}</td>'
                    f'<td>{html.escape(owner_text)}</td>'
                    f'<td>{html.escape(_check_deliver_to(owner_text))}</td>'
                    f'<td>{html.escape(_check_due_text(ln))}</td></tr>')
    body_html = "\n        ".join(rows) or '<tr><td colspan="5" class="empty">미완 체크 없음</td></tr>'
    return ('<table><tr><th>카드</th><th>체크</th><th>체크 담당</th><th>전달 대상</th><th>완료예정일</th></tr>'
            f'{body_html}</table>'
            '<div class="sub-note">닫는 곳: GM업무 화면 체크</div>')


def chief_detail_blocks(ssot_rows: "list | None") -> str:
    """더는 아래에 따로 펴지 않는다 — 업무·결재 SSOT 목록은 그 행 토글 안으로 들어갔다
    (GM 지시 2026-09-14 「하나로 토글 정리해줘」). 호출부는 그대로 두고 빈 문자열을 돌린다."""
    return ""


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
           f'<span class="pgt">현재 {html.escape(_fmt_amt(cur, "원"))} / 목표 {html.escape(_fmt_amt(target, "원"))}</span></span>')
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
    elif kind_of(it) == "reply":
        ss = '<span class="ss-rc">회신으로 닫힘</span>'
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
    resp_html = resp_section(seen, ssot_rows, sales_data)
    week_html = week_block(seen)   # 📅 이번 주 — 끝난 것·새로 뜬 것·멈춘 것(GM 지시 2026-09-14)   # 👤 책임 항목 4인 — seen·ssot_rows·매출 원자료 그대로 넘긴다
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

    blocks = []
    counts = []  # (표시이름, 총건수, SSOT 미등록건수)
    shown: list[tuple[int, str, dict, str]] = []

    # 실장 지시(GM 2026-09-14 "이경연 실장이 운영부 담당자들 업무들까지 체크") — 실장 아래엔
    #   운영부 팀원 건, 소장 아래엔 시설부(지원부·주차 포함) 팀원 건을 묶어 넣는다. 나우열M 은
    #   본인 담당(인사·파트너)만이라 팀 묶음이 없다.
    TEAM_BY_NAME = {"이경연 실장": (OPS_TEAM, "운영부 담당자 건", "실장이 함께 체크하는"),
                    "이정헌 소장": (FACILITY_TEAM, "시설부 담당자 건", "소장이 함께 체크하는")}

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

        team_html = ""
        if team:
            _, team_title, team_lead = team
            if team_groups:
                inner = "\n        ".join(
                    f'<h3 class="rsp">{html.escape(p)} <span class="gc">{len(rows)}건</span></h3>\n        '
                    + table([row_html(n, d, it) for n, d, it in sorted(rows)], "없음")
                    # 사람 순서 = 명단(OPS_TEAM·FACILITY_TEAM) 순서 — GM 지시 2026-09-14
                    #   「최준용M - 임정은M - 윤병현AM - 백승화 사원 - 진수아 사원 이 순으로」.
                    for p, rows in ((p, team_groups[p]) for p in team[0] if p in team_groups))
            else:
                inner = '<div class="empty" style="padding:8px 14px;">없음</div>'
            team_html = (f'\n        <details open class="grp"><summary>{team_lead} {team_title} '
                         f'<span class="gc">{len(team_rows)}건</span></summary>\n        {inner}\n        </details>')

        blocks.append(f'''      <div class="blk">
        <h2>{html.escape(name)} <span class="sub">{html.escape(dept)} · {html.escape(room)} · 열린 건 {len(person_rows)}건(본인 {len(mine)}건)</span></h2>
        {table([row_html(n, d, it) for n, d, it in mine], "열린 건 없음")}{team_html}
      </div>''')

    # 실장·소장·나우열M 어느 라인도 아닌 담당만 남으면 여기로(있을 때만) — 2026-09-11 사고
    #   재발 방지(담당이 있는데 어디에도 안 걸려 화면에서 사라짐)는 그대로 지킨다.
    line_out = sorted(((n, d, it) for n, (d, it) in opens.items()
                       if str(it.get("owner") or "").strip()), key=lambda x: x[0])
    for n, _d, _it in line_out:
        opens.pop(n)
    if line_out:
        shown += [(n, d, it, str(it.get("owner") or "").strip()) for n, d, it in line_out]
        blocks.append(f'''      <div class="blk">
        <h2>라인 밖 <span class="sub">실장·소장·나우열M 어느 라인도 아닌 담당 · {len(line_out)}건</span></h2>
        {table([row_html(n, d, it) for n, d, it in line_out], "없음")}
      </div>''')

    if ai_items:
        ai_line = " · ".join(f'#{n} {html.escape(str(it.get("issue") or ""))}' for n, _d, it in ai_items)
        blocks.append(f'''      <div class="blk pr-skip">
        <h2>AI 처리 건 <span class="sub">사람 일이 아니라 화면 결함 등 — 사람 목차에서 뺐습니다 · {len(ai_items)}건</span></h2>
        <div style="padding:10px 14px;font-size:13.5px;">{ai_line}</div>
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
    blocks.append(f'''      <div class="blk pr-skip">
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
        blocks.append(f'''      <div class="blk pr-skip">
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

    if aside_reply:
        # 회신 소통건 — 업무가 아니라 답을 기다리는 물음. 사람 목차에서 뺐고(GM 2026-09-14 「업무 SSOT 건만
        #   챙겨줘 · 회신건들은 최종 체크하고 삭제」), 따로 모아 달라는 지시(같은 날 「회신 소통건으로 따로
        #   정리」)대로 맨 아래 접힌 기록 한 곳에만 둔다. 답이 오면 원장이 닫힌다.
        by_who_r: dict[str, list] = {}
        for n, d, it in aside_reply:
            by_who_r.setdefault(str(it.get("owner") or "담당 미정").strip() or "담당 미정", []).append((n, d, it))
        order_r = [m[0] for m in MANAGERS] + OPS_TEAM + FACILITY_TEAM
        names_r = [w for w in order_r if w in by_who_r] + [w for w in by_who_r if w not in order_r]
        inner_r = "\n        ".join(
            f'<h3 class="rsp">{html.escape(w)} <span class="gc">{len(by_who_r[w])}건</span></h3>\n        '
            + table([row_html(n, d, it) for n, d, it in by_who_r[w]], "없음")
            for w in names_r)
        blocks.append(f'''      <div class="blk pr-skip">
        <details class="grp"><summary>회신 소통건 — 업무 아님 · 한 줄 답이 오면 닫힘 <span class="gc">{len(aside_reply)}건</span></summary>
        {inner_r}
        </details>
      </div>''')

    # 닫힌 것·중복 접힘 목록은 화면에서 뺐다 (GM 지적 2026-09-14 「닫은건들은 왜 보이는거야?」).
    #   둘 다 「여기서 하실 일은 없습니다」라고 적어 두고도 자리를 차지했다 — 볼 이유가 없으면 안 그린다.
    #   판정 자체는 그대로 돈다(원장은 안 건드리고, 머리줄 숫자로만 남긴다).

    ssot_note = ""
    if not ssot_ok:
        ssot_note = '<span class="b2 fail">⚠ 업무 SSOT 대조 실패 — 겹친 건이 그대로 보일 수 있습니다.</span>'
    elif moved:
        ssot_note = (f'<span class="b2">업무·결재 SSOT 에 올라간 것 {len(moved)}건 · 다른 곳에서 닫힌 것 '
                     f'{len(aside_rc)}건 · 중복 {len(aside_dup)}건은 맨 아래 접힘 목록으로 내렸습니다 · '
                     f'<b>여기 남은 {len(shown)}건이 업무 SSOT 에 올려야 하는 것</b>입니다.</span>')

    top5 = sorted(shown, key=lambda x: (-days_since(x[1]), x[0]))[:5]
    head = " · ".join(f"{n} {c}건(SSOT 미등록 {m}건)" for n, c, m in counts)
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
  section.resp, section.resp-q {{ background:#fff; border:1px solid var(--line); margin-top:14px; }}
  section.resp > h2, section.resp-q > h2 {{ background:var(--navy); color:#fff; }}
  /* 📅 분기 누적(GM 지시 2026-09-15) — 같은 .resp-tb, 달 칸(rq)만 추가 */
  section.resp-q > h2 .sub {{ color:#fff; opacity:.8; }}
  section.resp-q th.rq, section.resp-q td.rq {{ width:16%; font-size:13px; }}
  section.resp-q td.rq.bad {{ color:var(--bad); font-weight:700; }}
  section.resp-q details > summary {{ padding:9px 14px; cursor:pointer; color:var(--navy); font-weight:700; border-top:1px solid var(--line); }}
  .rp-person {{ border-top:1px solid var(--line); }}
  .rp-person:first-child {{ border-top:0; }}
  .rp-person h3 {{ padding:9px 14px; font-size:14.5px; color:var(--navy); background:var(--navy-bg); }}
  table.resp-tb th.ri, table.resp-tb td.ri {{ width:15%; font-weight:700; }}
  table.resp-tb th.rc, table.resp-tb td.rc {{ width:24%; color:var(--dim); font-size:13px; }}
  table.resp-tb th.rp, table.resp-tb td.rp {{ width:26%; }}
  table.resp-tb td.rp.bad {{ color:var(--bad); font-weight:700; }}
  table.resp-tb th.rg, table.resp-tb td.rg,
  table.resp-tb th.rf, table.resp-tb td.rf {{ width:17.5%; font-size:13px; }}
  /* 실장 행 토글 — 종합접수처·점검 현황 행을 누르면 바로 아래 tr 에 내역(GM 지시 2026-09-14) */
  tr.rp-toggle {{ cursor:pointer; }}
  tr.rp-toggle:hover {{ background:var(--navy-bg); }}
  tr.rp-toggle .rp-arrow {{ color:var(--dim); }}
  tr.rp-detail td {{ padding:0; background:#FAFBFC; }}
  tr.rp-detail table {{ margin:0; }}
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
  /* ★막대가 찔끔 나오던 것 (GM 지적 2026-09-14 「30%인데 그래프가 찔끔?」).
     .bar 가 span 이라 기본이 inline 이었다 — inline 은 height·width 가 안 먹어 트랙이
     내용 폭(=0)으로 접혔고, 그 0 의 30% 라 막대가 점처럼 보였다. 블록으로 펴고 폭을 준다. */
  /* ★한 줄 + 채움 (GM 지적 2026-09-14 「한 줄로 %랑 같이 · 올 회색이 아니라 41%만큼 색칠」).
     위 .bar(머리 검정 띠) 규칙의 padding·line-height 가 이 트랙에도 먹어 트랙이 20px 로 부풀고
     채움(i)은 내용 높이 0 의 100% = 0px 라 안 보였다 — 트랙·채움 높이를 px 로 못 박고 padding 을 지운다. */
  .pg {{ display:flex; align-items:center; gap:8px; white-space:nowrap; }}
  .pg .bar {{ display:block; flex:1 1 80px; min-width:60px; max-width:180px; height:8px; padding:0; margin:0;
             line-height:0; border-radius:4px; background:var(--line); overflow:hidden; }}
  .pg .bar i {{ display:block; height:8px; }}
  .pg .pg-low {{ background:var(--bad); }}
  .pg .pg-mid {{ background:var(--warn); }}
  .pg .pg-ok {{ background:#2e7d32; }}
  .pg .pgn {{ font-size:11.5px; font-weight:800; margin-right:6px; }}
  .pg .pgt {{ font-size:11px; color:var(--dim); }}
  /* 👤 책임 항목 표 안 매출 진척(span.pg) — td.pg(#132px 고정폭) 재사용, 이 칸은 폭 자유 */
  td.rp .pg {{ display:flex; }}
  td.rp .pg .pgt {{ display:inline; margin:0; }}
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
  /* 📅 이번 주 — 세 칸(끝난 것·새로 뜬 것·멈춘 것). 좁아지면 한 줄씩 쌓인다. */
  .week{{margin:14px 0 18px;border:1px solid var(--line);border-radius:10px;padding:12px 14px;background:#fff}}
  .week>h2{{margin:0 0 10px;font-size:15px;font-weight:800}}
  .week .sub{{font-size:11.5px;font-weight:600;color:var(--dim);margin-left:8px}}
  .wk-cols{{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:12px}}
  .wk-col{{border:1px solid var(--line);border-radius:8px;padding:9px 11px;min-width:0}}
  .wk-col>h3{{margin:0 0 7px;font-size:12.5px;font-weight:800}}
  .wk-warn{{border-color:#e6b3b3;background:#fff8f8}}
  .wk-list{{margin:0;padding-left:16px}}
  .wk-list li{{font-size:12px;line-height:1.65;padding:1px 0}}
  .wk-who{{color:var(--dim);margin-left:6px}}
  .wk-age{{color:var(--dim);margin-left:6px;font-variant-numeric:tabular-nums}}
  .wk-none{{font-size:12px;color:var(--dim);list-style:none;margin-left:-14px}}
  /* A3 요약본(인쇄+PNG) — GM업무.html 과 같은 버튼 3개(GM 지시 2026-09-15). 제목 줄 오른쪽에 상시 노출,
     별도 배지·설명문은 안 둔다. */
  @page {{ size: A3 portrait; margin: 12mm; }}
  .h1row{{display:flex;align-items:baseline;gap:14px;flex-wrap:wrap;}}
  .a3bar{{display:flex;gap:8px;flex-wrap:wrap;margin-left:auto;}}
  .a3bar button{{font-family:inherit;font-size:12.5px;font-weight:700;color:#fff;cursor:pointer;
    background:var(--navy);border:1px solid var(--navy);border-radius:99px;padding:5px 13px;}}
  .a3bar button:hover{{opacity:.85;}}
  .a3bar button:disabled{{opacity:.5;cursor:default;}}
  @media print{{
    .a3bar{{display:none !important;}}
    body{{padding:0;}}
    .wrap{{max-width:100%;}}
    section.resp,.week,.top,.blk{{break-inside:avoid;}}
    .pr-skip{{display:none !important;}}
  }}
</style>
</head>
<body>
<div class="wrap">
  <div class="h1row">
    <h1>중간관리자 업무 목차</h1>
    <div class="a3bar">
      <button type="button" onclick="printA3('landscape');">🖨 A3 가로 인쇄</button>
      <button type="button" onclick="printA3('portrait');">🖨 A3 세로 인쇄</button>
      <button type="button" id="mgr-png-btn" onclick="saveMapPng(this);">🖼 PNG 다운로드</button>
    </div>
  </div>
  <div class="lede">이경연 실장 · 이정헌 소장 · 나우열M 세 사람의 <b>열린 업무</b>를 번호순으로 편 목차입니다.
    회신은 번호로 받습니다 — 「#번호 + 했다/진행중/언제」 한 줄.<br>
    체크는 GM 화면에만 남습니다(이 브라우저). 원장 상태는 실무진 회신이 오면 바뀝니다.</div>
  <div class="bar">기준 {date.today().isoformat()} · 열린 {total}건 · 가장 오래된 것 {oldest}일 · 14일 넘게 답 없는 것 {stale}건
    <span class="b2">{html.escape(head)} · 담당 미정 {len(unassigned)}건 · 진행할 건은 본인이 SSOT 등록</span>
    {ssot_note}</div>

{resp_html}
{week_html}

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
  // A3 요약본(인쇄+PNG) — GM업무.html printA3/saveMapPng 그대로 재사용(GM 지시 2026-09-15 · 새 인쇄
  // 경로·새 라이브러리 금지). 이 화면은 AI 처리건·담당 미정·접힌 기록(.pr-skip)만 @media print 로
  // 숨기면 되고, 나머지 사람별 목록은 이미 펼쳐져 있어 GM업무.html 의 details 강제 오픈이 필요 없다.
  window.printA3 = function (orientation) {{
    var st = document.getElementById('mgr-a3-style');
    if (!st) {{ st = document.createElement('style'); st.id = 'mgr-a3-style'; document.head.appendChild(st); }}
    st.textContent = '@page{{ size: A3 ' + orientation + '; margin: 12mm; }}';
    window.print();
  }};
  var H2C_SRC = 'https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js';
  function loadH2C() {{
    if (typeof html2canvas === 'function') return Promise.resolve();
    return new Promise(function (ok, no) {{
      var s = document.createElement('script');
      s.src = H2C_SRC; s.onload = ok; s.onerror = no;
      document.head.appendChild(s);
    }});
  }}
  function pad2(n) {{ return n < 10 ? '0' + n : '' + n; }}
  window.saveMapPng = function (btn) {{
    var label = btn.textContent;
    btn.textContent = '변환 중…'; btn.disabled = true;
    var d = new Date();
    var name = '중간관리자_업무목차_' + d.getFullYear() + pad2(d.getMonth() + 1) + pad2(d.getDate()) + '.png';
    // html2canvas 는 화면 그대로를 찍어 @media print 규칙(.pr-skip 숨김)이 안 먹는다 — 인쇄와 같은
    // 범위가 되도록 캡처 직전에만 감췄다가 끝나면 되돌린다(인쇄의 details 강제오픈과 대칭인 처리).
    var skipped = Array.prototype.slice.call(document.querySelectorAll('.pr-skip'));
    skipped.forEach(function (el) {{ el.dataset.pngHidden = el.style.display; el.style.display = 'none'; }});
    loadH2C()
      .then(function () {{
        return html2canvas(document.querySelector('.wrap'), {{ scale: 2, backgroundColor: '#ffffff', windowWidth: document.querySelector('.wrap').scrollWidth }});
      }})
      .then(function (c) {{
        var a = document.createElement('a');
        a.download = name; a.href = c.toDataURL('image/png'); a.click();
      }})
      .catch(function () {{ alert('PNG 변환 실패 — [A3 인쇄] 에서 PDF 저장을 쓰세요.'); }})
      .finally(function () {{
        skipped.forEach(function (el) {{ el.style.display = el.dataset.pngHidden; delete el.dataset.pngHidden; }});
        btn.textContent = label; btn.disabled = false;
      }});
  }};

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

  // 종합접수처·점검 현황 행 토글(GM 지시 2026-09-14) — 기본 접힘, 클릭한 행 바로 다음 tr 이 내역.
  document.querySelectorAll('tr.rp-toggle').forEach(function (tr) {{
    tr.addEventListener('click', function () {{
      var det = tr.nextElementSibling;
      if (!det || !det.classList.contains('rp-detail')) return;
      var opening = det.hidden;
      det.hidden = !opening;
      tr.querySelector('.rp-arrow').textContent = opening ? '▾' : '▸';
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
