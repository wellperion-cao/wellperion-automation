#!/usr/bin/env python3
"""점검 현황 핵심요약 — 텔레그램 점검관리방 · 카톡 23시 공유방 공용 모듈 (단일 진실).

GM 2026-07-19 지시: 두 채널이 **동일한 3섹션 핵심요약**(🏗 시설부 / 🛠 지원부 / 🅿 주차부)을
내보내게 렌더 로직을 이 한 모듈로 단일화한다. 기존 daily_scheduler.py·kakao_daily_check_share.py에
복붙돼 갈라져 있던 로직을 통합 — 이제 양쪽이 이 모듈을 import 하므로 두 번 다시 갈라지지 않는다.

핵심요약(GM 원안 "이 정도로만"):
  🏗 시설부 = N회 점검 · 이상 유무(+기준이탈 최대 3건)
  🛠 지원부 = 종일 완료율 + 남/여 + 회차분해(요일 반영) + 짚을 점(독려 필요 회차)
  🅿 주차부 = 이슈/현황(없으면 정직 표기)

회차분해 요일 반영(문제1 근본해결):
  서버 today_live는 주말(토·일)이면 pm(오후조) 분모·분자를 0으로 반환한다
  (.deploy-check/지원팀 일일점검.js, 배173·2026-07-04 시우). 따라서 이 모듈은
  **분모(total)>0 회차만 렌더** — 주말이면 오전조·마감조 2회차, 평일이면 오전조·오후조·마감조
  3회차가 자동 정합된다(요일 하드코딩 분기 불필요·서버 스케줄을 단일 진실로 신뢰).
  홈 화면 parseGenderKpi(main.html)와 동일한 total>0 렌더 규칙과도 일치.

데이터 소스(점검 GAS · 실측·지어내기 0):
  지원부: ?action=today_live&dept=support&date=YYYY-MM-DD
  시설부: ?action=board&key=FACILITY_CHECK_YYYY-MM-DD (회수) + ?action=monthly_report&dept=facility (기준이탈)
  주차부: ?action=weekly&dept=parking

사용(라이브 미발송 · 렌더 확인용):
  python scripts/support_check_summary.py --date 2026-07-18   # 주말 렌더 확인
"""
from __future__ import annotations

import argparse
import io
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

# 반복 미완료 감지기(원장 기반) — soft import(없어도 무동작 폴백). GM 2026-07-19 지시3.
_scr_dir = os.path.dirname(os.path.abspath(__file__))
if _scr_dir not in sys.path:
    sys.path.insert(0, _scr_dir)
try:
    import check_incomplete_detector as _cid
    _CID_OK = True
except Exception:
    _cid = None
    _CID_OK = False

# 반복 미완료 누적 원장(지원부 v1) — daily_scheduler가 23시에 적재. status/check_incomplete_ledger.json.
CHECK_INCOMPLETE_LEDGER = Path(_scr_dir).parent / "status" / "check_incomplete_ledger.json"

# 점검 GAS(CHECK_API) — daily_scheduler.py·kakao_daily_check_share.py와 동일 배포 URL(단일 소스)
DEFAULT_GAS_URL = (
    "https://script.google.com/macros/s/"
    "AKfycbyXw4ZaA6hLK567GC7NY33Y8SvNPW6kNtrXFz2OsSdFVBmCnZP-2oD-RQiX0IpekBu1/exec"
)

# 회차 표준(순서 고정) — 라벨은 실제 운영 명칭(오전조/오후조/마감조). 주말은 오후조 미운영(서버가 total=0).
_SHIFTS = [("am", "오전조"), ("pm", "오후조"), ("close", "마감조")]



def _num(n) -> str:
    """정수면 '32', 소수면 '32.2' (%g 스타일 — 불필요한 .0 제거)."""
    try:
        f = float(n)
    except (TypeError, ValueError):
        return str(n)
    return str(int(f)) if f.is_integer() else str(f)


def fetch_gas(params: dict, url: str = DEFAULT_GAS_URL, timeout: float = 20.0) -> dict | None:
    """GAS GET → dict(ok=true)만 반환. 실패·ok=false는 None(정직 — 지어내기 금지)."""
    params = {**params, "_pv": int(time.time())}   # 캐시 버스트(no-store 정합)
    full = url + "?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(urllib.request.Request(full), timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
    except Exception:
        return None
    if not isinstance(data, dict) or not data.get("ok"):
        return None
    return data


# ── 지원부 ────────────────────────────────────────────────────────────────
def support_issues(d: dict) -> list[str]:
    """미점검·미달 회차를 **빠짐없이** 짚음(1개만 X). GM 2026-07-19 피드백1.
    한 구역(남/여) 전체가 0%면 "여성구역 전체 미점검(오전조·마감조)"처럼 통으로 직관 표기.
    부분 미달이면 회차별로 "여성구역 마감조 3/13(23%)". 전부 완료면 [](이상 없음)."""
    g = d.get("byGender", {}) or {}
    out: list[str] = []
    for gk, glabel in (("m", "남성구역"), ("f", "여성구역")):
        part = g.get(gk, {}) or {}
        shifts = [(lbl, int(part.get(k, 0) or 0), int(part.get(k + "Total", 0) or 0))
                  for k, lbl in _SHIFTS if int(part.get(k + "Total", 0) or 0) > 0]
        incomplete = [(lbl, dn, tt) for lbl, dn, tt in shifts if dn < tt]
        if not incomplete:
            continue
        # 구역 전체 미점검(전 회차 0) → 통으로
        if len(incomplete) == len(shifts) and all(dn == 0 for _, dn, _ in shifts):
            out.append(f"{glabel} 전체 미점검({'·'.join(l for l, _, _ in shifts)})")
        else:
            for lbl, dn, tt in incomplete:
                p = round(dn / tt * 100) if tt else 0
                out.append(f"{glabel} {lbl} {dn}/{tt}({p}%)")
    return out


def _pct_str(done: int, total: int) -> str:
    return f"{round(done / total * 100)}%" if total else "-"


def gender_shift_breakdown(part: dict) -> list[tuple[str, int, int, int]]:
    """byGender.{m|f} → [(라벨, done, total, pct)] — 분모>0 회차만(요일 자동 반영)."""
    out = []
    for key, label in _SHIFTS:
        total = int(part.get(key + "Total", 0) or 0)
        if total <= 0:
            continue
        done = int(part.get(key, 0) or 0)
        out.append((label, done, total, round(done / total * 100) if total else 0))
    return out


def recurring_issue_lines(today: str, max_items: int = 3) -> list[str]:
    """반복 미완료(원장 기반) → '이슈사항'으로 승격. 1회성 특이점과 구분(반복만). GM 2026-07-19 지시3.
    콜드스타트·원장부족·0건이면 [](정직 — 가짜 이슈 금지)."""
    if not _CID_OK:
        return []
    try:
        ledger = _cid.load_ledger(CHECK_INCOMPLETE_LEDGER)
        recurring = _cid.detect_recurring(ledger, today)
    except Exception:
        return []
    if not recurring:
        return []
    win = getattr(_cid, "WINDOW_DAYS", 7)
    lines = [f"  🔁 반복 이슈 {len(recurring)}건 (일정 조율 검토)"]
    for r in recurring[:max_items]:
        lines.append(
            f"    · '{r['item']}' ({r['shift_label']}) 최근 {win}일 中 {r['days']}일 미완료")
    if len(recurring) > max_items:
        lines.append(f"    · 외 {len(recurring) - max_items}건")
    return lines


def build_support_section(today: str, url: str = DEFAULT_GAS_URL,
                          data: dict | None = None) -> tuple[list[str], dict]:
    """지원부 핵심요약: 종일 완료율 + **남성구역·여성구역 각각**(회차분해 요일반영) +
    오늘 짚을 점(1회성) + 반복 이슈(원장). GM 2026-07-19 지시2·3.
    data 미지정 시 today_live 직접 조회(공용). 지정 시 그대로 사용(중복 호출 방지)."""
    filled = {"support_status": False, "support_recurring": 0}
    d = data if data is not None else fetch_gas(
        {"action": "today_live", "dept": "support", "date": today}, url)
    if not isinstance(d, dict):
        return (["🛠 지원부 현황: 데이터 조회 실패(정직 표기)"], filled)

    total = int(d.get("total", 0) or 0)
    done = int(d.get("done", 0) or 0)
    if total <= 0:
        return (["🛠 지원부 현황: 오늘 점검 입력 없음"], filled)

    filled["support_status"] = True
    lines = [f"🛠 지원부 현황 {done}/{total}({_pct_str(done, total)})"]

    # 남성구역·여성구역 각각(합산 아님) — 각 구역 완료율 + 회차분해(요일반영·분모>0만·한 줄 콤팩트)
    g = d.get("byGender", {}) or {}
    for gk, glabel in (("m", "남성구역"), ("f", "여성구역")):
        part = g.get(gk, {}) or {}
        g_t = sum(int(part.get(k + "Total", 0) or 0) for k, _ in _SHIFTS)
        g_d = sum(int(part.get(k, 0) or 0) for k, _ in _SHIFTS)
        br = gender_shift_breakdown(part)
        detail = " — " + " · ".join(f"{lb} {dn}/{tt}" for lb, dn, tt, _ in br) if br else ""
        lines.append(f"  {glabel} {g_d}/{g_t}({_pct_str(g_d, g_t)}){detail}")

    # ── 이슈사항(현황과 함께) — 미점검 회차 전부 + 반복 이슈. GM 2026-07-19 피드백1·2 ──
    issues = support_issues(d)          # 1회성 미점검(빠짐없이)
    rec = recurring_issue_lines(today)  # 반복(원장) — 이미 " " 들여쓰기 리스트
    filled["support_recurring"] = max(0, len(rec) - 1) if rec else 0
    if issues:
        lines.append("  ❗ 짚을 점: " + ", ".join(issues) + " — 독려 필요")
    elif not rec:
        lines.append("  ✅ 이상 없음 — 전 회차 완료")
    lines += rec
    return (lines, filled)


_MAX_WORKLOG = 8   # 작업일지 표시 최대 항목(초과 시 '외 N')


def facility_worklog(subs: list) -> tuple[list[str], list[str]]:
    """board submissions → (작업사항 리스트, 특이사항 리스트). GM 2026-07-19 피드백3.
    work=회차 누적이라 '가장 항목 많은' 제출 1개를 대표로(중복 자동 흡수) · note=전 회차 유니크."""
    if not isinstance(subs, list) or not subs:
        return ([], [])

    def _lines(v):
        return [ln.strip() for ln in str(v or "").replace("\r", "").split("\n") if ln.strip()]

    # 작업사항: 누적 필드라 가장 풍부한(항목 최다) 제출을 대표로 사용
    best = max(subs, key=lambda s: len(_lines(s.get("work"))), default=None)
    work_items = _lines(best.get("work")) if best else []

    # 특이사항(note)·기준이탈조치(oocAction) — 전 회차에서 유니크 수집(순서 보존)
    notes: list[str] = []
    seen = set()
    for s in subs:
        for f in ("note", "oocAction"):
            for ln in _lines(s.get(f)):
                if ln not in seen:
                    seen.add(ln)
                    notes.append(ln)
    return (work_items, notes)


# ── 시설부 ────────────────────────────────────────────────────────────────
def build_facility_section(today: str, url: str = DEFAULT_GAS_URL) -> tuple[list[str], dict]:
    """시설부 핵심요약: 회수(board.submissions) + **작업일지(work) + 이슈사항(기준이탈·특이사항note)**.
    회수 = len(board.store.submissions)(정본·페이지 'N회 완료' 일치, GM 2026-07-15). GM 2026-07-19 피드백3."""
    filled = {"facility_status": False, "facility_outofrange": 0, "facility_worklog": False}

    board = fetch_gas({"action": "board", "key": f"FACILITY_CHECK_{today}"}, url)
    subs = (((board or {}).get("board") or {}).get("store") or {}).get("submissions")
    sessions = len(subs) if isinstance(subs, list) else 0

    monthly = fetch_gas({"action": "monthly_report", "dept": "facility", "month": today[:7]}, url)
    today_oor = []
    if isinstance(monthly, dict):
        oor = ((monthly.get("outOfRange") or {}).get("list")) or []
        today_oor = [x for x in oor if str(x.get("date")) == today]
    filled["facility_outofrange"] = len(today_oor)

    lines: list[str] = []
    if not sessions:
        lines.append("🏗 시설부 현황: 오늘 점검 입력 없음")
        return (lines, filled)

    filled["facility_status"] = True
    head = f"🏗 시설부 현황 {sessions}회 점검"
    head += f" · 이상 {len(today_oor)}건" if today_oor else " · 이상 없음"
    lines.append(head)

    # 작업일지(무슨 점검·작업을 했는지) — 실데이터(work). 없으면 정직히 생략(지어내기 금지).
    work_items, notes = facility_worklog(subs)
    if work_items:
        filled["facility_worklog"] = True
        shown = work_items[:_MAX_WORKLOG]
        tail = f" 외 {len(work_items) - _MAX_WORKLOG}건" if len(work_items) > _MAX_WORKLOG else ""
        lines.append("  📋 작업일지: " + " · ".join(shown) + tail)
    else:
        lines.append("  📋 작업일지: 데이터 없음")

    # 이슈사항 = 기준이탈(인라인 압축) + 특이사항(note)
    if today_oor:
        parts = []
        for x in today_oor[:2]:
            name = str(x.get("name", "")).split("(")[0].strip() or str(x.get("name", ""))
            parts.append(f"{name} {_num(x.get('value'))}(기준 {_num(x.get('min'))}~{_num(x.get('max'))})")
        extra = f" 외 {len(today_oor) - 2}건" if len(today_oor) > 2 else ""
        lines.append(f"  ❗ 기준이탈 {len(today_oor)}건: " + " · ".join(parts) + extra)
    if notes:
        note_txt = " / ".join(notes[:2])
        if len(note_txt) > 90:
            note_txt = note_txt[:90] + "…"
        lines.append("  📝 특이사항: " + note_txt)
    return (lines, filled)


# ── 주차부 ────────────────────────────────────────────────────────────────
def build_parking_section(today: str, url: str = DEFAULT_GAS_URL) -> tuple[list[str], dict]:
    """주차부: weekly 오늘 행 있으면 현황, 없으면 '자체점검 준비 중' 정직 표기."""
    filled = {"parking": False}
    data = fetch_gas({"action": "weekly", "dept": "parking"}, url)
    if isinstance(data, dict):
        for row in data.get("data") or []:
            t = row.get("total")
            if str(row.get("date")) == today and isinstance(t, (int, float)) and t:
                filled["parking"] = True
                return ([f"🅿 주차부 이슈사항: 없음 · 점검 {row.get('done', 0)}/{t}({row.get('pct', 0)}%)"], filled)
    return (["🅿 주차부 이슈사항: 없음 (자체점검 준비 중)"], filled)


# ── 통합 3섹션 핵심요약(두 채널 공용 본문 코어) ─────────────────────────────
def build_summary_lines(now: datetime | None = None, date: str | None = None,
                        url: str = DEFAULT_GAS_URL,
                        support_data: dict | None = None) -> tuple[list[str], dict]:
    """3섹션 핵심요약 본문 라인(헤더·푸터 제외 — 채널이 각자 감싼다).
    date 지정 시 그 날짜로 조회(테스트·과거 스냅샷 재현). support_data 지정 시 지원부 재조회 생략."""
    now = now or datetime.now()
    today = date or now.strftime("%Y-%m-%d")

    fac_lines, fac_f = build_facility_section(today, url)
    sup_lines, sup_f = build_support_section(today, url, data=support_data)
    par_lines, par_f = build_parking_section(today, url)

    # 섹션 사이 빈 줄 1칸(가시성) — 🏗 시설부 → 🛠 지원부 → 🅿 주차부. GM 2026-07-19 지시1. 양 채널 동일.
    lines = fac_lines + [""] + sup_lines + [""] + par_lines
    return (lines, {**fac_f, **sup_f, **par_f})


def _weekday_kor(date: str) -> str:
    try:
        return ["월", "화", "수", "목", "금", "토", "일"][datetime.strptime(date, "%Y-%m-%d").weekday()]
    except Exception:
        return "?"


def main() -> int:
    # 콘솔 한글 깨짐 방지 — 스탠드얼론 실행 시에만(import 경로에선 전역 스트림 불건드림)
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="점검 3섹션 핵심요약 렌더(라이브 미발송)")
    ap.add_argument("--date", help="조회 날짜 YYYY-MM-DD(생략 시 오늘). 주말 렌더 확인용.")
    args = ap.parse_args()
    date = args.date or datetime.now().strftime("%Y-%m-%d")
    lines, filled = build_summary_lines(date=date)
    print("=" * 56)
    print(f"[{date}({_weekday_kor(date)}) 점검 핵심요약]")
    print("\n".join(lines))
    print("=" * 56)
    print(f"채워진 필드: {filled}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
