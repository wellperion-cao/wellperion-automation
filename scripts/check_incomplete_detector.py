# -*- coding: utf-8 -*-
"""
점검 미완료 누적 감지기 (지원부 v1) — GM 2026-07-15.

목적: 매일 하루 마감(23시) 시점의 '미완료 항목'을 원장에 적재하고,
      최근 7일 中 4일 이상 미완료였던 항목을 '반복'으로 감지해
      일정(조·시각) 조율 검토를 제안한다.

정직 원칙:
  - 지원부 uncheckedByShift(조별·성별 미체크 항목명)만이 명확한 '미완료 항목' 소스다 → v1은 지원부만.
    시설부는 이벤트/이상 중심이라 '미완료 항목' 개념이 달라 v1 제외.
  - 원장 누적일이 window(기본 7일) 미만이거나 반복 항목 0건이면 제안 줄 자체를 생략(가짜 제안 금지).
  - 라이브 실값만 적재(지어내기 금지). 데이터 없으면 조용히 생략.

순수 함수 위주로 구성 — daily_scheduler(데몬)에서 import해 사용하고, pytest로 단위검증한다.
"""
from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

# 조(shift) → 한글 라벨
SHIFT_LABELS = {"am": "오전조", "pm": "오후조", "close": "마감조", "night": "야간조"}

# 반복적으로 걸리는 조 → 조율(이동) 제안 대상(한 단계 앞당김 휴리스틱).
#   하드 지시 아님 · '검토 제안' 톤. am은 더 앞이 없어 시각 조율만 권유.
_EARLIER_SHIFT = {"pm": "오전조", "close": "오후조", "night": "마감조", "am": "오전조"}

# 원장에서 하루 최종 미완료를 적재할 대상 회차(23시=하루 마감이라 저녁 회차 포함).
LEDGER_SHIFTS = ("pm", "close", "night")

WINDOW_DAYS = 7      # 반복 판정 관찰 창(최근 N일)
THRESHOLD_DAYS = 4   # 창 내 N일 이상 미완료 = '반복'
KEEP_DAYS = 30       # 원장 보존 일수(오래된 날짜 정리)


# ── 원장 I/O ──────────────────────────────────────────────────────────────────
def load_ledger(path) -> dict:
    """원장 JSON 로드. 없거나 깨지면 빈 dict(안전)."""
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_ledger(path, ledger: dict) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(ledger, ensure_ascii=False, indent=2), encoding="utf-8")


# ── 하루 미완료 레코드 조립 ────────────────────────────────────────────────────
def merge_shift_items(unchecked_by_shift: dict, shift: str) -> list[str]:
    """uncheckedByShift[shift]의 남(m)+여(f) 미체크 항목명을 병합·중복제거·정렬."""
    bucket = (unchecked_by_shift or {}).get(shift) or {}
    names = list(bucket.get("m") or []) + list(bucket.get("f") or [])
    cleaned = [str(n).strip() for n in names if str(n or "").strip()]
    return sorted(set(cleaned))


def build_daily_record(unchecked_by_shift: dict, shifts=LEDGER_SHIFTS) -> dict:
    """하루 최종 미완료 레코드 조립 → {"support": {shift: [item, ...], ...}}.
    성별(m/f)은 항목명으로 병합. 비어 있는 회차는 빈 리스트."""
    support = {sh: merge_shift_items(unchecked_by_shift, sh) for sh in shifts}
    return {"support": support}


def append_today(ledger: dict, date_str: str, daily_record: dict, keep_days: int = KEEP_DAYS) -> dict:
    """원장에 오늘 레코드를 멱등 적재.
      - 같은 날짜가 이미 있으면 append 안 함(멱등).
      - 최근 keep_days 날짜만 유지(오래된 날짜 정리).
    새 dict를 반환(입력 dict 비파괴)."""
    out = dict(ledger or {})
    if date_str not in out:
        out[date_str] = daily_record
    # 오래된 날짜 정리 — YYYY-MM-DD 정렬 후 최근 keep_days만.
    try:
        cutoff = (datetime.strptime(date_str, "%Y-%m-%d") - timedelta(days=keep_days)).strftime("%Y-%m-%d")
        out = {d: rec for d, rec in out.items() if d >= cutoff}
    except Exception:
        pass
    return out


# ── 반복 감지 ─────────────────────────────────────────────────────────────────
def _window_dates(today: str, window_days: int) -> list[str]:
    """today 포함 최근 window_days 일자 리스트(YYYY-MM-DD)."""
    base = datetime.strptime(today, "%Y-%m-%d")
    return [(base - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(window_days)]


def detect_recurring(
    ledger: dict,
    today: str,
    window_days: int = WINDOW_DAYS,
    threshold: int = THRESHOLD_DAYS,
    dept: str = "support",
) -> list[dict]:
    """원장에서 최근 window_days 中 threshold일 이상 미완료였던 항목을 감지.

    반환: [{"item": 항목명, "days": 미완료일수, "shift": 최빈조, "shift_label": 라벨}, ...]
          미완료 일수 내림차순 정렬.

    콜드스타트 정직: 원장 누적일이 window_days 미만이면 [] 반환(데이터 부족 → 가짜 제안 금지).
    """
    if not ledger or len(ledger) < window_days:
        return []

    win = set(_window_dates(today, window_days))
    # 항목별: 미완료였던 날짜 집합 + 조 카운터
    day_count: dict[str, set] = {}
    shift_counter: dict[str, Counter] = {}

    for date_str, rec in ledger.items():
        if date_str not in win:
            continue
        by_shift = (rec or {}).get(dept) or {}
        for shift, items in by_shift.items():
            for item in (items or []):
                name = str(item).strip()
                if not name:
                    continue
                day_count.setdefault(name, set()).add(date_str)
                shift_counter.setdefault(name, Counter())[shift] += 1

    recurring = []
    for name, days in day_count.items():
        n = len(days)
        if n >= threshold:
            top_shift = shift_counter[name].most_common(1)[0][0]
            recurring.append({
                "item": name,
                "days": n,
                "shift": top_shift,
                "shift_label": SHIFT_LABELS.get(top_shift, top_shift),
            })
    # 미완료 일수↓, 동률이면 항목명 오름차순(결정적)
    recurring.sort(key=lambda r: (-r["days"], r["item"]))
    return recurring


def format_suggestion_lines(
    recurring: list[dict],
    max_items: int = 3,
    window_days: int = WINDOW_DAYS,
) -> list[str]:
    """반복 항목 → 제안 텍스트 라인 리스트. 항목 0건이면 [](줄 생략)."""
    if not recurring:
        return []
    lines = ["🔁 반복 미완료 — 일정 조율 검토"]
    for r in recurring[:max_items]:
        earlier = _EARLIER_SHIFT.get(r["shift"])
        if earlier and earlier != r["shift_label"]:
            tail = f"{earlier} 이동/점검 시각 조율 제안"
        else:
            tail = "점검 시각 조율 제안"
        lines.append(
            f"  · '{r['item']}' ({r['shift_label']}) "
            f"최근 {window_days}일 中 {r['days']}일 미완료 → {tail}"
        )
    return lines


# ── 편의: 원장 적재 + 제안 라인 조립(daily_scheduler에서 호출) ──────────────────
def append_daily_from_live(ledger_path, date_str: str, unchecked_by_shift: dict) -> dict:
    """라이브 uncheckedByShift로 하루 레코드를 만들어 멱등 적재 후 저장. 저장된 ledger 반환.
    실패해도 예외를 던지지 않음(발신 무영향) — 실패 시 기존 ledger 반환."""
    try:
        ledger = load_ledger(ledger_path)
        record = build_daily_record(unchecked_by_shift)
        ledger = append_today(ledger, date_str, record)
        save_ledger(ledger_path, ledger)
        return ledger
    except Exception:
        return load_ledger(ledger_path)


def suggestion_lines_for_today(ledger_path, today: str) -> list[str]:
    """원장을 읽어 오늘 기준 반복 제안 라인 반환. 실패/콜드스타트 → []."""
    try:
        ledger = load_ledger(ledger_path)
        recurring = detect_recurring(ledger, today)
        return format_suggestion_lines(recurring)
    except Exception:
        return []
