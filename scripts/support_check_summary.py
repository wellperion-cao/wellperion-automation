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
import re
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

# ── 회차수 신뢰 게이트 (2026-07-22 시토) ──
# 근본원인 수리 완료: saveBoard()가 store.submissions[]를 seq 기준 union 병합한다
# (.deploy-check/지원팀 일일점검.js). ★ 라이브 /exec 재배포 완료·검증됨(2026-07-22, deployment
# AKfycbyXw4ZaA6hLK567GC7NY33Y8SvNPW6kNtrXFz2OsSdFVBmCnZP-2oD-RQiX0IpekBu1 @170) —
# 테스트 키(FACILITY_CHECK_TEST_MERGE_20260722)로 7건 저장 후 2건 재저장해도 7건 보존됨을
# 라이브 런타임에서 실증(테스트 키는 검증 후 자가청소함). ScriptProperties 500KB 하드리밋
# 초과분(캐시 프루닝, 5일 유지)도 해소 확인(410,732B, 하드리밋 512,000B 대비 여유 확보).
# sessions=len(submissions) 신뢰 가능 → 게이트 True 전환.
FACILITY_SESSIONS_TRUSTED = True



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


_MAX_ISSUE_DETAIL = 8   # 이슈 상세 표시 최대 건수(초과 시 '외 N건')


def _shift_label_from_roundkey(rk) -> str:
    """roundKey(예 'pm1'·'close1'·'am1') → 회차 라벨(오전조/오후조/마감조). 미상 접두면 원문 그대로."""
    m = re.match(r"([a-zA-Z]+)", str(rk or ""))
    prefix = m.group(1) if m else str(rk or "")
    return dict(_SHIFTS).get(prefix, prefix or "?")


def support_issue_detail_lines(d: dict, max_items: int = _MAX_ISSUE_DETAIL) -> list[str]:
    """today_live.allIssues → 이슈 상세 라인(구역·회차·내용·작성자). GM 2026-07-22 근본수리.
    완료율 기반 '짚을 점'(미달 회차 %)과 별개 — 체크리스트에 실제 적힌 이슈 원문을 그대로 보이게
    (지어내기 금지 — 소스에 없는 필드는 생략)."""
    items = d.get("allIssues")
    if not isinstance(items, list) or not items:
        return []
    glabel = {"m": "남", "f": "여"}
    lines = [f"  📝 이슈 상세 {len(items)}건"]
    for it in items[:max_items]:
        g = glabel.get(str(it.get("gender")), str(it.get("gender") or "?"))
        shift = _shift_label_from_roundkey(it.get("roundKey"))
        text = str(it.get("issue") or "").strip()
        if len(text) > 40:
            text = text[:40] + "…"
        by = str(it.get("by") or "").strip()
        tag = f" ({by})" if by else ""
        lines.append(f"    · [{g}/{shift}] {text}{tag}")
    if len(items) > max_items:
        lines.append(f"   · 외 {len(items) - max_items}건")
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

    # 이슈 상세(체크리스트 원문) — 완료율 짚을 점과 별개, allIssues 그대로 노출. GM 2026-07-22 지시3.
    lines += support_issue_detail_lines(d)
    return (lines, filled)


_MAX_WORKLOG = 12  # 회차별 일지 표시 최대 회차(초과 시 '외 N회차').
                   # 누적 반복을 걷어내 회차당 1줄로 짧아졌으므로 전 회차가 다 보이도록 상향
                   # (기존 8이면 9회차 날 마지막 회차가 잘려 '외 1회차'로 숨었다 — GM 2026-07-23).

# 시설부 측정값 라벨(store.rounds[*] / store.daily 원본 키 → 한글 표기). GM 2026-07-22 렌더심화.
_ROUND_LABELS = {
    "sauna_ontang_a": "온탕A", "sauna_ontang_b": "온탕B",
    "sauna_yeoltang_a": "열탕A", "sauna_yeoltang_b": "열탕B",
    "sauna_dry_a": "건식A", "sauna_dry_b": "건식B",
    "sauna_wet_a": "습식A", "sauna_wet_b": "습식B",
    "sauna_jjim_a": "찜질A", "sauna_jjim_b": "찜질B",
    "pool_ph": "수영장pH", "pool_temp": "수영장온도", "pool_cl": "수영장염소",
    "tank_k2": "탱크K2", "tank_k3": "탱크K3", "tank_k4": "탱크K4",
    "ahu_AHU1": "AHU1", "ahu_AHU2": "AHU2", "ahu_AHU3": "AHU3", "ahu_AHU4": "AHU4",
}
_DAILY_LABELS = {
    "fc_eq_night": "심야전기", "fc_eq_tank1": "1번탱크", "fc_eq_gas": "가스검침",
    "fc_eq_hotw": "고온수기", "fc_eq_pump": "연동펌프",
}


def _lines(v) -> list[str]:
    return [ln.strip() for ln in str(v or "").replace("\r", "").split("\n") if ln.strip()]


def facility_worklog(subs: list) -> tuple[list[str], list[str]]:
    """board submissions → (회차별 일지 라인 리스트, 특이사항 리스트). GM 2026-07-22 근본수리.
    이전엔 work 최다 '대표 제출 1건'만 썼음(다른 회차 작업내용 유실) — seq 순 전체 회차를 루프해
    "N회차 HH:MM~HH:MM(소요 M분) · 점검자 · 작업요약" 라인으로 전부 가시화(데이터 없는 회차는 시간만).
    note=전 회차 유니크(기존 로직 유지 — 이미 전체 순회라 손상 아님)."""
    if not isinstance(subs, list) or not subs:
        return ([], [])

    ordered = sorted(subs, key=lambda s: s.get("seq") if isinstance(s.get("seq"), (int, float)) else 0)
    work_items: list[str] = []
    seen_work: set[str] = set()   # 앞 회차에 이미 나온 작업 — 반복 출력 차단
    for i, s in enumerate(ordered, start=1):
        start, end = s.get("startHHMM"), s.get("endHHMM")
        time_part = f"{start}~{end}" if start and end else (str(s.get("at") or "").split(" ")[-1] or "?")
        dur = s.get("durMin")
        dur_part = f"({dur}분)" if dur not in (None, "") else ""
        insp = s.get("inspector") or "?"
        head = f"{i}회차 {time_part}{dur_part} · {insp}"

        # work 는 '그 회차까지의 누적 작업목록'으로 들어온다(현장 입력 방식).
        # 그대로 찍으면 뒤 회차일수록 앞 내용을 통째로 반복해 8회차엔 9줄이 겹쳤다
        # → 화면이 길어져 정작 '오늘 새로 한 일'이 안 보인다(GM 2026-07-23 지적).
        # 그래서 앞 회차에 없던 항목만 남긴다. 데이터는 손대지 않고 표시만 줄인다.
        fresh = [w for w in _lines(s.get("work")) if w not in seen_work]
        seen_work.update(fresh)
        if fresh:
            marker = "" if i == 1 else "+ "
            work_items.append(f"{head} · {marker}{' / '.join(fresh)}")
        else:
            work_items.append(f"{head} · (추가 작업 없음)")

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


def facility_measurements(store: dict, today_oor_fields: set[str]) -> list[str]:
    """store.rounds[*]·store.daily(장비값) → 측정값 요약 라인. GM 2026-07-22 렌더심화 지시2.
    소스에 있는 값만 그대로 표기(창작 금지) · today_oor_fields에 든 필드는 ❗ 표시(기존 기준이탈 판정 재사용)."""
    out: list[str] = []

    rounds = store.get("rounds") if isinstance(store.get("rounds"), dict) else {}
    for rk in sorted(rounds.keys()):
        vals = rounds.get(rk) or {}
        if not isinstance(vals, dict) or not vals:
            continue
        parts = []
        for k in sorted(vals.keys()):
            key = k[3:] if k.startswith("fc_") else k
            label = _ROUND_LABELS.get(key, key)
            mark = "❗" if key in today_oor_fields else ""
            parts.append(f"{mark}{label} {vals[k]}")
        tag = f" [{rk}]" if len(rounds) > 1 else ""
        out.append(f"  🌡 측정{tag}: " + " · ".join(parts))

    daily = store.get("daily") if isinstance(store.get("daily"), dict) else {}
    eq_parts = [f"{_DAILY_LABELS[k]} {daily[k]}" for k in _DAILY_LABELS if daily.get(k) not in (None, "")]
    if eq_parts:
        out.append("  ⚙ 설비: " + " · ".join(eq_parts))
    return out


# ── 시설부 ────────────────────────────────────────────────────────────────
def build_facility_section(today: str, url: str = DEFAULT_GAS_URL) -> tuple[list[str], dict]:
    """시설부 핵심요약: 회차별 일지(submissions 전체) + 측정값(rounds·daily) +
    이슈사항(기준이탈·특이사항note). GM 2026-07-22 근본수리(렌더심화·회차수 정직표기).
    회차수(sessions=len(submissions))는 GAS saveBoard union 병합 수리·라이브 배포·런타임 검증
    완료(FACILITY_SESSIONS_TRUSTED=True) — 신뢰 가능."""
    filled = {"facility_status": False, "facility_outofrange": 0, "facility_worklog": False}

    board = fetch_gas({"action": "board", "key": f"FACILITY_CHECK_{today}"}, url)
    store = (((board or {}).get("board") or {}).get("store") or {})
    subs = store.get("submissions")
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
    # 회차수 표기 — FACILITY_SESSIONS_TRUSTED=False(기본)면 GAS 재배포 전이라 '(확인중)' 꼬리표
    # 유지(거짓 확정 금지). GM이 라이브 배포 검증 후 플래그를 True로 바꾸면 정확 회차수로 전환.
    if FACILITY_SESSIONS_TRUSTED:
        head = f"🏗 시설부 현황 {sessions}회차"
    else:
        head = f"🏗 시설부 현황 board 기록 {sessions}건(회차 확인중)"
    head += f" · 이상 {len(today_oor)}건" if today_oor else " · 이상 없음"
    lines.append(head)

    # 회차별 일지(전 회차 개별 라인) — 실데이터(work). 없으면 정직히 시간만(지어내기 금지).
    today_oor_fields = {str(x.get("field")) for x in today_oor if x.get("field")}
    work_items, notes = facility_worklog(subs)
    if work_items:
        filled["facility_worklog"] = True
        shown = work_items[:_MAX_WORKLOG]
        tail = f" · 외 {len(work_items) - _MAX_WORKLOG}회차" if len(work_items) > _MAX_WORKLOG else ""
        lines.append("  📋 회차별 일지 (새로 추가된 작업만 · 앞 회차 반복 생략)")
        for ln in shown:
            lines.append(f"    · {ln}")
        if tail:
            lines.append(f"   {tail}")
    else:
        lines.append("  📋 회차별 일지: 데이터 없음")

    # 측정값(사우나·수영장·탱크·공조기·설비) — store.rounds/store.daily 원본. 기준이탈 필드는 ❗.
    meas_lines = facility_measurements(store, today_oor_fields)
    lines += meas_lines

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
