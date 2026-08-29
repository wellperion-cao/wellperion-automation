# -*- coding: utf-8 -*-
"""
cpo_member_rollup.py — 모듈 cpo-member-rollup 수집기(공유 SSOT 정합).
─────────────────────────────────────────────────────────────────────────────
등록부의 모듈 id `cpo-member-rollup` → id 규약으로 collectors.cpo_member_rollup
로 해소된다. notify_spec={weekly:true, monthly:true} 양쪽 cadence에서 동일
collect()가 호출된다(cmo-marketing-funnel 등 기존 수집기와 동일 패턴).
notify_spec.daily=false — 일일 발송 없음(cpo_report.py의 build_daily_report와는
무관한 별개 계통 · module_report_weekly.bat/monthly.bat만 이 collect()를 부른다).

배312(2026-08-08, GM 확정 2026-08-03 기준 교체) — 옛 문의퍼널 기준(신규문의·전환율·
LOSS율·예약활성)을 폐기하고 「멤버십 회원관리 기준」 5줄로 교체:
  ① 회원 구성(정회원/대기/법인) ② 이번 주 등록·LOSS ③ 문의→등록 ④ 데이터 위생 ⑤ 데이터 완성도.
★GM 확정(2026-08-13) — 유효회원 수가 전체이고, **대기는 그 안에 든 인원**이다(999명 중 대기 8명·
  중단기 3명). 더해서 쓰지 않는다. 대기 판정은 등록 분류(또는 재등록 분류) 칸에 '대기'라고
  적힌 회원 — '시작일자가 아직 안 왔다'로 세던 옛 방식(28명)은 대기가 아니라 '시작 예정'이었다.

로직 재사용(중복 복사 금지): cpo_report.py 의 fetch_member_inquiries·fetch_cpo_today_stats·
fetch_cpo_churn_stats·fetch_active_members(기존)에 더해 fetch_member_registered_list·
fetch_lesson_roster(신규 thin wrapper — 기존 GAS 액션 member_registered_list·
lesson_registered_roster 재호출일 뿐, 새 GAS 액션 아님) 재사용. 새 집계기·새 백엔드 없음.

판정 기준(전부 membership.html 라이브 판정과 동일 소스 재사용 — 새 판정 로직 없음):
  · 대기 판정 = 시작일자가 오늘보다 미래(_isFutureStart와 동일 문자열 비교).
  · 회원구분 오타 정규화 = '맴버십'/'멥버십' → '멤버십'(member_active_summary MA_TYPO와 동일).
  · 신규/재등록 = member_registered_list newOnly(=_isNewRegistration_, 서버 판정) 재사용.
  · LOSS 날짜 우선순위 = LOSS일자→이탈일→해지일→종료일(member_active_summary와 동일 체인,
    2026-08-10 배483 — 시트 헤더 '이탈일'→'LOSS일자' 개명).
  · 데이터 완성도(멤버십) = _activeCompletenessGaps(담당 미배정·연락기록 없음·등록분류 상충).
  · 데이터 완성도(강습) = _lessonMemGapOf(담당 미배정·연락기록 없음·상태 미입력).

정직 꼬리표: 각 줄은 소스 조회 실패 시 그 줄만 "측정 안 됨"(날조 금지). honesty_tag는
데이터 상태에서 그대로 파생한다(하드코딩 아님) — 전 소스 실패="미측정", 요약에 "측정 안 됨"이
하나라도 남으면 "부분", 없으면 "측정".

'지난주 대비' 이력: 새 파일 생성 없이(약속 L21) module_reporter.py가 이미 매 발송마다
payload.metrics를 status/module_report_log.jsonl에 적재하는 경로를 그대로 쓴다 —
데이터 위생 5수치를 metrics로 실어 보내고, 다음 회차 collect() 호출 때 그 로그의 직전
항목(module_reporter._last_metrics 재사용)을 읽어 증감을 계산한다.
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timedelta

_SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # scripts/
_PROJECT_ROOT = os.path.dirname(_SCRIPTS_DIR)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from collectors.base import make_payload  # noqa: E402
import cpo_report  # noqa: E402 — 기존 fetch 로직 재사용(중복 복사 금지)
from module_reporter import REPORT_LOG_PATH, _last_metrics  # noqa: E402 — 지난주 대비용 로그 재사용(새 파일 금지)

_LINK = "https://wellperion-cao.github.io/wellperion-automation/cpo/member/membership.html"
_MODULE_ID = "cpo-member-rollup"

_TYPO_MAP = {"맴버십": "멤버십", "멥버십": "멤버십"}
# 회원 구분 정본 6종(GM 확정 2026-08-13). 법인은 별도 시트라 이 집계에선 0이지만 목록에는 둔다.
_KNOWN_TYPES = ["멤버십", "입주민", "보증금", "FAN VIP", "중단기", "법인"]
# 등록 분류 정본 7종(GM 확정 2026-08-13) — 신규·재등록·양수·환불·L재등록·L-가망·대기.
# 이 중 '대기'만 상태 판정에 쓴다. '재등록대기'는 옛 표기라 하위호환으로 함께 본다.
_WAIT_VALUES = {"대기", "재등록대기"}

# 유효회원 시트 완성도 판정 재료(membership.html OWNER_ASSIGN_SPORTS 그대로) — (담당자칸, Contact칸)
_OWNER_SPORTS = [
    ("PT 담당자", "PT Contact"),
    ("골프 담당자", "GOLF Contact"),
    ("P.L 담당자", "P.L Contact"),
    ("스쿼시 담당자", "스쿼시 Contact"),
    ("수영 담당자", "수영 Contact"),
]
_UNASSIGNED_OPTION = "담당자 X"  # LESSON_UNASSIGNED_OPTION과 동일값 — 명시적 미배정은 채운 것으로 안 침


def _norm_key(k) -> str:
    return str(k).replace(" ", "").replace("\n", "")


def _find_col(row: dict, fragment: str):
    frag = _norm_key(fragment)
    for k in row.keys():
        if frag in _norm_key(k):
            return k
    return None


def _cell(row: dict, fragment: str) -> str:
    k = _find_col(row, fragment)
    return str(row.get(k, "")).strip() if k else ""


def _regclass_conflict(row: dict) -> bool:
    """「등록 분류」·「재등록 분류」 두 칸이 신규/재등록으로 서로 어긋나는지 —
    membership.html _regClassMerged().conflict 와 동일 판정(새 판정 로직 아님)."""
    a = row.get("등록 분류", "") or ""
    a = str(a).strip()
    b_key = None
    for k in row.keys():
        nk = _norm_key(k)
        if "재등록" in nk and "분류" in nk:
            b_key = k
            break
    b = str(row.get(b_key, "") or "").strip() if b_key else ""
    if not b or b == a:
        return False
    return a == "신규" and b == "재등록"


def _active_completeness_gap(row: dict) -> bool:
    """멤버십 유효회원 완성도 결측 판정 — membership.html _activeCompletenessGaps 재현
    (담당 미배정·연락기록 없음·등록분류 상충 중 하나라도 있으면 True)."""
    has_owner = any(
        str(row.get(c, "") or "").strip() not in ("", _UNASSIGNED_OPTION) for c, _ in _OWNER_SPORTS
    )
    has_contact = any(str(row.get(ct, "") or "").strip() for _, ct in _OWNER_SPORTS)
    return (not has_owner) or (not has_contact) or _regclass_conflict(row)


def _lesson_gap(row: dict) -> bool:
    """강습 회원 관리 완성도 결측 판정 — membership.html _lessonMemGapOf 재현
    (담당 미배정·연락기록 없음·상태 미입력 중 하나라도 있으면 True)."""
    owner_missing = not str(row.get("owner", "") or "").strip()
    contact_missing = not (row.get("contacts") or [])
    status_missing = not str(row.get("status", "") or "").strip()
    return owner_missing or contact_missing or status_missing


def _lesson_completeness_pct(lesson_type: str):
    """강습(성인/유소년) 데이터 완성도 %. 조회 실패·명단 0건이면 None(미측정)."""
    roster = cpo_report.fetch_lesson_roster(lesson_type)
    if roster is None:
        return None
    named = [r for r in roster if str(r.get("name", "") or "").strip()]
    if not named:
        return None
    gaps = sum(1 for r in named if _lesson_gap(r))
    return round((len(named) - gaps) / len(named) * 100)


_DATE_OK = re.compile(r"^\s*\d{4}[-./]\d{1,2}[-./]\d{1,2}")
_DATE_COLS = ("등록일자", "시작일자", "종료일자", "LOSS일자")


def _broken_date_cols(row: dict) -> int:
    """값은 있는데 날짜로 안 읽히는 칸 수. 2026-08-14 시포 — 위생 5번째 항목.

    2026-08-08 에 김영경1 의 시작일자가 '25. 10 .15' 로 깨져 있었고, 집계가 그걸
    미래 날짜로 오판해 대기 인원을 1명 더 세었다. 사람이 보면 바로 아는 오타인데
    기계는 조용히 틀린 숫자를 냈다 — 그래서 위생 줄에 띄운다.
    """
    n = 0
    for col in _DATE_COLS:
        v = _cell(row, col)
        if v and not _DATE_OK.match(v):
            n += 1
    return n


def _member_composition(active_rows: list[dict], today: str) -> dict:
    """유효회원 시트(scope=valid) 전체를 정회원/대기로 가르고, 정회원만 회원구분별로
    집계 + 데이터 위생(오타·미기재·이름중복·잔여일 공백·날짜형식) 동시 산출 — 시트 1회 순회로 재사용."""
    total = len(active_rows)
    waiting = 0
    type_counts = {t: 0 for t in _KNOWN_TYPES}
    other = 0
    typo_count = 0
    blank_type_count = 0
    remain_blank = 0
    date_broken = 0
    gaps = 0
    name_seen: dict[str, int] = {}

    for r in active_rows:
        if not isinstance(r, dict):
            continue
        name = _cell(r, "회원명")
        if name:
            name_seen[name] = name_seen.get(name, 0) + 1

        # 대기 판정 = 실무진이 분류 칸에 '대기'라고 적어 둔 회원(GM 확정 2026-08-13 · 8명).
        # 그전엔 '시작일자가 아직 안 왔다'로 세어 28명이 나왔는데 그건 대기가 아니라 '시작 예정'이다.
        # 화면(membership.html _isFutureStart)이 이미 이 규칙으로 세고 있었다 — 여기만 달라서 숫자가 갈렸다.
        is_waiting = _cell(r, "등록분류") in _WAIT_VALUES or _cell(r, "재등록분류") in _WAIT_VALUES
        if is_waiting:
            waiting += 1

        raw_type = _cell(r, "회원구분")
        if raw_type in _TYPO_MAP:
            typo_count += 1
        if not raw_type:
            blank_type_count += 1
        norm_type = _TYPO_MAP.get(raw_type, raw_type)
        # 유형별은 유효회원 **전체** 기준이다(GM 확정 2026-08-13 — "999명 중 대기 8명·중단기 3명").
        # 대기를 빼고 세면 유형별 합이 전체와 안 맞아, 보는 사람이 어느 쪽이 맞는지 알 수 없어진다.
        if norm_type in _KNOWN_TYPES:
            type_counts[norm_type] += 1
        else:
            other += 1

        if not _cell(r, "잔여일"):
            remain_blank += 1

        if _active_completeness_gap(r):
            gaps += 1

        date_broken += _broken_date_cols(r)

    dup_count = sum(c - 1 for c in name_seen.values() if c > 1)
    return {
        "total": total,
        "waiting": waiting,
        "regular": total - waiting,
        "type_counts": type_counts,
        "other": other,
        "typo_count": typo_count,
        "blank_type_count": blank_type_count,
        "remain_blank": remain_blank,
        "date_broken": date_broken,
        "dup_count": dup_count,
        "gaps": gaps,
    }


def _hygiene_metrics(comp: dict) -> dict:
    """데이터 위생 5수치 → {라벨: 값}(module_report_log.jsonl 적재용 · '지난주 대비' 재료)."""
    return {
        "오타": comp["typo_count"],
        "미기재": comp["blank_type_count"],
        "이름중복": comp["dup_count"],
        "잔여일 공백": comp["remain_blank"],
        "날짜형식 깨짐": comp["date_broken"],
    }


def _hygiene_delta_tail(prev: dict | None, cur: dict) -> str:
    """위생 줄 꼬리표 — 이력 없으면 첫 측정, 있으면 바뀐 수치만 표기."""
    if not prev:
        return "(지난주 대비 비교 이력 없음 — 첫 측정)"
    parts = [
        f"{label} {prev[label]}→{now_v}({now_v - prev[label]:+d})"
        for label, now_v in cur.items()
        if label in prev and prev[label] != now_v
    ]
    if not parts:
        return "(지난주 대비 변동 없음)"
    return "(지난주 대비 " + " · ".join(parts) + ")"


def _fmt_names(items: list, limit: int = 5) -> str:
    """이름 목록을 괄호 병기용 문자열로("(이름1·이름2·… 외 N명)"). 빈 목록이면 빈 문자열."""
    names = [str(n or "").strip() for n in items]
    names = [n for n in names if n]
    if not names:
        return ""
    shown = names[:limit]
    tail = f" 외 {len(names) - limit}명" if len(names) > limit else ""
    return "(" + "·".join(shown) + tail + ")"


def collect(module=None) -> dict:
    """표준 payload 반환 — summary_line 안에 GM 확정 5줄(■ 회원 구성/이번 주 등록·LOSS/
    문의에서 등록까지/데이터 위생/데이터 완성도)을 그대로 담는다(metrics는 비움 — module_reporter
    의 "  · label: value" 나열 형식이 이 5줄 표기와 안 맞아, summary_line 통짜로 렌더)."""
    today = cpo_report._today_str()
    week_start = (datetime.strptime(today, "%Y-%m-%d") - timedelta(days=6)).strftime("%Y-%m-%d")

    active_rows = cpo_report.fetch_active_members("valid")
    ended_rows = cpo_report.fetch_active_members("ended")
    today_stats = cpo_report.fetch_cpo_today_stats()
    churn = cpo_report.fetch_cpo_churn_stats()
    inq_rows = cpo_report.fetch_member_inquiries()
    new_regs = cpo_report.fetch_member_registered_list(week_start, today, new_only=True)
    all_regs = cpo_report.fetch_member_registered_list(week_start, today, new_only=False)

    if active_rows is None and ended_rows is None and today_stats is None and churn is None and inq_rows is None:
        return make_payload(
            title="회원 현황 롤업",
            summary_line="전체 소스 조회 실패(GAS 응답 없음)",
            metrics=[],
            honesty_tag="미측정",
            link=_LINK,
        )

    comp = _member_composition(active_rows, today) if active_rows is not None else None

    # ── ① 회원 구성 ──────────────────────────────────────────────────────────
    if comp is not None:
        tc = comp["type_counts"]
        type_str = "·".join(f"{t} {tc[t]}" for t in _KNOWN_TYPES if tc[t])
        if comp["other"]:
            type_str += ("·" if type_str else "") + f"기타 {comp['other']}"
        corp_n = today_stats.get("memberCorp") if today_stats else None
        corp_str = f"{corp_n}명(별도 시트)" if isinstance(corp_n, (int, float)) else "측정 안 됨"
        # 유효회원이 전체이고 대기는 그 안에 든 인원이다(GM 확정 2026-08-13) — 더하는 값이 아니다.
        line1 = (
            f"■ 회원 구성 — 유효회원 {comp['total']}명({type_str}) · "
            f"그중 대기 {comp['waiting']}명 · 법인 {corp_str}"
        )
    else:
        line1 = "■ 회원 구성 — 측정 안 됨(유효회원 조회 실패)"

    # ── ② 이번 주 등록·LOSS ─────────────────────────────────────────────────
    if new_regs is not None:
        new_str = f"{len(new_regs)}건{_fmt_names([r.get('name') for r in new_regs])}"
    else:
        new_str = "측정 안 됨"
    if all_regs is not None:
        re_regs = [
            r for r in all_regs
            if "재등록" in str(r.get("regClass", "") or "") or "재등록" in str(r.get("regClass2", "") or "")
        ]
        re_str = f"{len(re_regs)}건{_fmt_names([r.get('name') for r in re_regs])}"
    else:
        re_str = "측정 안 됨"
    if ended_rows is not None:
        loss_col = None
        for frag in ("LOSS일자", "이탈일", "해지일", "종료일"):
            if ended_rows and _find_col(ended_rows[0], frag):
                loss_col = frag
                break
        loss_week = []
        for r in ended_rows:
            name = _cell(r, "회원명")
            if not name or not loss_col:
                continue
            d = _cell(r, loss_col)[:10]
            if d and week_start <= d <= today:
                loss_week.append(name)
        loss_str = f"{len(loss_week)}건{_fmt_names(loss_week)}"
    else:
        loss_str = "측정 안 됨"
    wait_str = f"{comp['waiting']}명" if comp is not None else "측정 안 됨"
    renew = churn.get("renewCount") if churn is not None else None
    renew_str = f"{renew}명" if isinstance(renew, (int, float)) else "측정 안 됨"
    line2 = (
        f"■ 이번 주 등록·LOSS — 신규 {new_str} · 재등록 {re_str} · LOSS {loss_str} · "
        f"대기 {wait_str} · 갱신임박 30일 이내 {renew_str}"
    )

    # ── ③ 문의에서 등록까지 ─────────────────────────────────────────────────
    if inq_rows is not None:
        week_inq = [r for r in inq_rows if (r.get("timestamp") or "") >= week_start]
        contacted = [r for r in week_inq if r.get("contacts")]
        registered = [r for r in week_inq if str(r.get("status", "") or "") in cpo_report._SUCCESS_STATUSES]
        reg_names = _fmt_names([r.get("name") for r in registered])
        line3 = (
            f"■ 문의에서 등록까지 — 신규문의 {len(week_inq)} · 컨택 {len(contacted)} · "
            f"등록 {len(registered)}{reg_names}"
        )
    else:
        line3 = "■ 문의에서 등록까지 — 측정 안 됨(문의 데이터 조회 실패)"

    # ── ④ 데이터 위생 ────────────────────────────────────────────────────────
    hygiene_metrics: dict = {}
    if comp is not None:
        hygiene_metrics = _hygiene_metrics(comp)
        prev_hygiene = _last_metrics(REPORT_LOG_PATH, _MODULE_ID)
        tail = _hygiene_delta_tail(prev_hygiene, hygiene_metrics)
        line4 = (
            f"■ 데이터 위생 — 회원구분 오타 {comp['typo_count']} · 미기재 {comp['blank_type_count']} · "
            f"이름중복 {comp['dup_count']} · 잔여일 공백 {comp['remain_blank']} · "
            f"날짜형식 깨짐 {comp['date_broken']} {tail}"
        )
    else:
        line4 = "■ 데이터 위생 — 측정 안 됨(유효회원 조회 실패)"

    # ── ⑤ 데이터 완성도 ──────────────────────────────────────────────────────
    active_pct = round((comp["total"] - comp["gaps"]) / comp["total"] * 100) if comp and comp["total"] else None
    adult_pct = _lesson_completeness_pct("성인강습")
    youth_pct = _lesson_completeness_pct("유소년강습")
    line5 = (
        f"■ 데이터 완성도 — 멤버십 유효회원 {f'{active_pct}%' if active_pct is not None else '측정 안 됨'} · "
        f"강습 성인 {f'{adult_pct}%' if adult_pct is not None else '측정 안 됨'} · "
        f"강습 유소년 {f'{youth_pct}%' if youth_pct is not None else '측정 안 됨'}"
    )

    summary = "\n".join([line1, line2, line3, line4, line5])
    all_failed = comp is None and inq_rows is None and ended_rows is None
    if all_failed:
        honesty_tag = "미측정"
    elif "측정 안 됨" in summary:
        honesty_tag = "부분"
    else:
        honesty_tag = "측정"

    metrics = [{"label": k, "value": v} for k, v in hygiene_metrics.items()]

    return make_payload(
        title="회원 현황 롤업",
        summary_line=summary,
        metrics=metrics,
        honesty_tag=honesty_tag,
        link=_LINK,
    )


if __name__ == "__main__":
    print(json.dumps(collect(), ensure_ascii=False, indent=2))
