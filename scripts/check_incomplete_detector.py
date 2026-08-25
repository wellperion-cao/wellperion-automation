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


# ── 정리 후보(계속 안 되는 항목) 집계 ────────────────────────────────────────
# 판정 기준(2026-08-25 실측 28일치로 결정):
#   미체크율 >= 50%  AND  (미체크율 − 같은 회차 평균) >= 25%p
# 근거 — 회차 제출이 통째로 빠진 날 때문에 회차 전체가 같이 높아지는 것과,
#        그 항목만 유독 높은 것을 가른다. 실측 마진:
#   잡힘 : B-8 개인락커(마감조) 100%/평균43.8%=+56.2%p · B-8(오후조) 67.9%/27.2%=+40.7%p
#          C-8 센터 화분(오후조) 60.7%/27.2%=+33.5%p
#   안잡힘: A-1 사우나 탕(마감조) 57.1%/43.8%=+13.3%p · C-2 복도 휴지통(오후조) 42.9%=+15.7%p
#   → 최대 제외폭 15.7%p 와 최소 포함폭 33.5%p 사이인 25%p 를 컷으로 둔다.
# 회차 평균의 분모 = '원장에 한 번이라도 등장한 항목'만. 한 번도 안 빠진 항목은 원장에
#   기록 자체가 없어 셀 수 없다 — 평균이 실제보다 높게 잡히므로 후보가 덜 나오는(보수적) 쪽이다.
DEAD_MIN_RATE = 0.50
DEAD_MIN_EXCESS = 0.25


def detect_dead_items(
    ledger: dict,
    dept: str = "support",
    min_rate: float = DEAD_MIN_RATE,
    min_excess: float = DEAD_MIN_EXCESS,
) -> list[dict]:
    """원장 전체 기간에서 '같은 회차 평균보다 뚜렷이 안 되는 항목'을 집계.

    반환: [{"shift", "shift_label", "item", "days", "total_days",
            "rate", "shift_avg", "excess"}, ...] 초과폭 내림차순.
    자동 삭제는 하지 않는다 — 사람이 판단할 후보 목록일 뿐.
    """
    dates = sorted(ledger or {})
    total = len(dates)
    if not total:
        return []

    counts: dict[str, Counter] = {}
    for d in dates:
        by_shift = (ledger[d] or {}).get(dept) or {}
        for shift, items in by_shift.items():
            bucket = counts.setdefault(shift, Counter())
            for item in (items or []):
                name = str(item).strip()
                if name:
                    bucket[name] += 1

    out = []
    for shift, bucket in counts.items():
        if not bucket:
            continue
        avg = sum(bucket.values()) / len(bucket) / total
        for name, cnt in bucket.items():
            rate = cnt / total
            if rate >= min_rate and rate - avg >= min_excess:
                out.append({
                    "shift": shift,
                    "shift_label": SHIFT_LABELS.get(shift, shift),
                    "item": name,
                    "days": cnt,
                    "total_days": total,
                    "rate": rate,
                    "shift_avg": avg,
                    "excess": rate - avg,
                })
    out.sort(key=lambda r: (-r["excess"], r["item"]))
    return out


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


if __name__ == "__main__":
    # 자체검사 — 실제 원장으로 판정 기준이 의도대로 가르는지 확인.
    _led = load_ledger(Path(__file__).resolve().parent.parent / "status" / "check_incomplete_ledger.json")
    _rows = detect_dead_items(_led)
    for _r in _rows:
        print("%-6s %5.1f%% (%2d/%d) 평균%4.1f%% 초과+%4.1f%%p  %s" % (
            _r["shift_label"], _r["rate"] * 100, _r["days"], _r["total_days"],
            _r["shift_avg"] * 100, _r["excess"] * 100, _r["item"]))
    _hit = {(r["shift"], r["item"]) for r in _rows}
    assert ("close", "B-8 개인락커 청결 관리(요청 시)") in _hit, "B-8(마감조) 100% 미체크가 후보에서 빠졌다"
    assert ("pm", "C-8 센터 화분") in _hit, "C-8(오후조)가 후보에서 빠졌다"
    assert ("close", "A-1 사우나 탕") not in _hit, "A-1(마감조)은 회차 통째 결측이라 후보가 아니어야 한다"
    assert ("close", "C-1 내부 화장실") not in _hit, "C-1(마감조)은 회차 통째 결측이라 후보가 아니어야 한다"
    print("자체검사 통과 — 후보 %d건" % len(_rows))
