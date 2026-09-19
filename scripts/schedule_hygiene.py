# -*- coding: utf-8 -*-
"""전사일정 자동 정리 점검기 — 시우가 GM 말 없이 매일 스스로 정리한다 (GM 지시 2026-09-19).

GM 원문: 「이런건 시우가 좀 관리좀 해줘 자동으로 계속 이야길 해야하네」. 오늘 GM 이 손으로 짚은 것:
  ①같은 건 중복(미소시티 간판 2개) ②지난 대비 필러(추석 연휴대비) ③GM 일정 시간 빈칸
  ④휴관일에 걸린 GM 일정 ⑤지워 달라 했는데 동기화로 되살아날 위험.

원천 = schedule_ssot.pull_from_live()(GAS 라이브). 옛 JSON 만 보고 판정하지 않는다.
새 판정 로직을 다시 짜지 않는다(약속 L21) — 중복 판정은 ops_daily_digest._schedule_is_dup 을,
휴관일 판정은 coo_registry._closed_day 를 그대로 재사용한다.

⑤ 되살아남 점검은 뺐다 — 시우가 지운 배의 삭제 이력을 남기는 원장이 저장소에 아직 없다
(만들면 새 SSOT 가 생긴다 · 약속 L21). 되면 그 원장을 여기서 읽기만 하면 된다.

사용법:
  python scripts/schedule_hygiene.py              # 목록만 출력(사람 말)
  python scripts/schedule_hygiene.py --apply       # ③ GM 시간 빈칸만 자동 채움 + push(①②④는 목록만)
  python scripts/schedule_hygiene.py --selfcheck   # 가짜 항목으로 4종 판정 assert(네트워크 없음)
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import schedule_ssot  # noqa: E402
from coo_registry import _closed_day  # noqa: E402

try:
    from worklog import log as worklog_log
except Exception:
    def worklog_log(*a, **k):
        return False


def _kst_today() -> date:
    return datetime.now(timezone(timedelta(hours=9))).date()


def _parse_date10(s) -> "date | None":
    """'YYYY-MM-DD' 만 date 로. 그 외(빈칸·'YYYY-MM'만)는 None — 지어내지 않는다."""
    s = str(s or "").strip()
    if len(s) != 10:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return None


# ═══════════════════════════════════════════
# ① 중복 — ops_daily_digest 의 기존 판정을 그대로 재사용(gm_aide_scan ⑨닮은제목과 같은 규칙)
# ═══════════════════════════════════════════
def check_duplicates(items: list) -> list:
    try:
        import ops_daily_digest as _o  # noqa: PLC0415 — 무거운 파일, 쓸 때만 임포트
    except Exception:
        return []
    # GM업무 짝(gmwork-*)은 일부러 카드와 같은 제목으로 세운 줄 — 중복이 아니다.
    pool = [it for it in items if not str(it.get("id") or "").startswith("gmwork-")]
    pairs, seen = [], set()
    for i, a in enumerate(pool):
        if not str(a.get("next_due") or "").strip():
            continue
        for b in pool[i + 1:]:
            if not _o._schedule_is_dup(a.get("name") or "", str(a.get("next_due") or ""),
                                        [b], str(a.get("time") or "")):
                continue
            key = tuple(sorted([str(a.get("id")), str(b.get("id"))]))
            if key in seen:
                continue
            seen.add(key)
            pairs.append((a, b))
    return pairs


# ═══════════════════════════════════════════
# ② 지난 필러 — 「대비/준비」인데 기한이 지났고 반복(cycle)도 없는 것
# ═══════════════════════════════════════════
_FILLER_WORDS = ("대비", "준비")
_HOLIDAY_WORDS = ("추석", "설날", "연휴")


def check_stale_filler(items: list, today: date) -> list:
    out = []
    for it in items:
        name = it.get("name") or ""
        if not any(w in name for w in _FILLER_WORDS):
            continue
        due = _parse_date10(it.get("next_due"))
        if not due or due >= today:
            continue
        no_cycle = not str(it.get("cycle") or "").strip()
        has_holiday = any(w in name for w in _HOLIDAY_WORDS)
        if no_cycle or has_holiday:
            out.append(it)
    return out


# ═══════════════════════════════════════════
# ③ GM 시간 빈칸 — 다음 14일 안 GM 일정인데 time 이 빈 것
# ═══════════════════════════════════════════
def check_gm_time_blank(items: list, today: date) -> list:
    horizon = today + timedelta(days=14)
    out = []
    for it in items:
        assignee = it.get("assignee") or ""
        if "GM" not in assignee and "김남욱" not in assignee:
            continue
        due = _parse_date10(it.get("next_due"))
        if not due or not (today <= due <= horizon):
            continue
        if str(it.get("time") or "").strip():
            continue
        out.append(it)
    return out


# ③ --apply 전용 — 안전한 시간 채우기 규칙(회의·방문류는 비워 둔다)
_SKIP_KEYWORDS = ("회의", "미팅", "면접", "면담", "방문", "내방", "상담", "오찬")
_SEND_KEYWORDS = ("발송", "연락", "전달", "컨택", "통보")
_DEADLINE_KEYWORDS = ("마감", "제출", "기한", "마무리")


def _classify_gm_time(name: str) -> "str | None":
    if any(k in name for k in _SKIP_KEYWORDS):
        return None  # 회의·방문은 시간을 지어내지 않는다
    if any(k in name for k in _SEND_KEYWORDS):
        return "10:00"  # 외부 발송·연락
    if any(k in name for k in _DEADLINE_KEYWORDS):
        return "17:00"  # 마감형
    return "14:00"  # 내부 검토(기본)


def _bump_time(base: str, taken: set) -> str:
    t = datetime.strptime(base, "%H:%M")
    while t.strftime("%H:%M") in taken:
        t += timedelta(minutes=30)
    return t.strftime("%H:%M")


def apply_gm_time_fill(items: list, gm_blanks: list) -> int:
    """gm_blanks(items 안의 항목 참조)에 time 을 안전 규칙으로 채운다 — items 를 그 자리에서 수정."""
    taken: dict[str, set] = {}
    for it in items:
        d = str(it.get("next_due") or "")
        t = str(it.get("time") or "").strip()
        if d and t:
            taken.setdefault(d, set()).add(t[:5])
    applied = 0
    for it in gm_blanks:
        base = _classify_gm_time(it.get("name") or "")
        if base is None:
            continue
        d = str(it.get("next_due") or "")
        slot = _bump_time(base, taken.setdefault(d, set()))
        it["time"] = slot
        taken[d].add(slot)
        applied += 1
    return applied


# ═══════════════════════════════════════════
# ④ 휴관일 충돌 — coo_registry._closed_day 재사용
# ═══════════════════════════════════════════
def check_closed_day_conflict(items: list) -> list:
    out = []
    for it in items:
        due = str(it.get("next_due") or "").strip()
        if len(due) != 10:
            continue
        if not (it.get("assignee") or "").strip():
            continue
        if _closed_day(due):
            out.append(it)
    return out


# ═══════════════════════════════════════════
# 보고
# ═══════════════════════════════════════════
def _line(it: dict, reason: str) -> str:
    return f"  - [{it.get('id')}] {(it.get('name') or '')[:40]} · {it.get('next_due')} · {reason}"


def run_report(items: list, today: date, source_note: str) -> dict:
    dups = check_duplicates(items)
    fillers = check_stale_filler(items, today)
    gm_blanks = check_gm_time_blank(items, today)
    closed = check_closed_day_conflict(items)

    print(f"[전사일정 자동 정리 점검] 원천={source_note} · 대상 {len(items)}건")

    print(f"① 중복 {len(dups)}쌍")
    for a, b in dups:
        print(f"  - [{a.get('id')}]↔[{b.get('id')}] {(a.get('name') or '')[:30]} · {a.get('next_due')}")

    print(f"② 지난 필러 {len(fillers)}건")
    for it in fillers:
        print(_line(it, f"cycle={it.get('cycle') or '없음'}"))

    print(f"③ GM 시간 빈칸 {len(gm_blanks)}건")
    for it in gm_blanks:
        print(_line(it, f"assignee={it.get('assignee')}"))

    print(f"④ 휴관일 충돌 {len(closed)}건")
    for it in closed:
        print(_line(it, f"assignee={it.get('assignee')}"))

    print("⑤ 되살아남 — 삭제 이력 원장 없음(점검 생략)")

    if not (dups or fillers or gm_blanks or closed):
        print("→ 진짜 0건" if "라이브" in source_note else "→ 0건이나 원천 못 읽어 판정 보류")

    return {"dups": dups, "fillers": fillers, "gm_blanks": gm_blanks, "closed": closed}


# ═══════════════════════════════════════════
# --selfcheck (네트워크 없음)
# ═══════════════════════════════════════════
def _selfcheck() -> None:
    today = _kst_today()
    fake_today = today.isoformat()
    fake_overdue = (today - timedelta(days=3)).isoformat()
    fake_soon = (today + timedelta(days=3)).isoformat()
    items = [
        {"id": "a1", "name": "골프팀장(위탁사업자) - 편도민면접", "next_due": fake_today, "time": "14:00", "assignee": ""},
        {"id": "a2", "name": "골프팀장 - 편도민 면접", "next_due": fake_today, "time": "14:00", "assignee": ""},
        {"id": "b1", "name": "추석 연휴대비", "next_due": fake_overdue, "cycle": "", "assignee": "시우"},
        {"id": "c1", "name": "매출 결산 보고", "next_due": fake_soon, "time": "", "assignee": "김남욱 GM"},
        {"id": "d1", "name": "세스코 방역 점검", "next_due": "2026-09-25", "assignee": "시설부", "cycle": "월 1회"},
        {"id": "e1", "name": "정상 일정", "next_due": fake_soon, "time": "10:00", "assignee": "박호균 과장"},
    ]

    dups = check_duplicates(items)
    assert any({a.get("id"), b.get("id")} == {"a1", "a2"} for a, b in dups), f"중복 못 잡음: {dups}"

    fillers = check_stale_filler(items, today)
    assert any(it["id"] == "b1" for it in fillers), f"지난 필러 못 잡음: {fillers}"
    assert not any(it["id"] == "e1" for it in fillers)

    gm_blanks = check_gm_time_blank(items, today)
    assert any(it["id"] == "c1" for it in gm_blanks), f"GM 시간 빈칸 못 잡음: {gm_blanks}"
    assert not any(it["id"] == "e1" for it in gm_blanks), "시간 있는 일정을 빈칸으로 오판"

    closed = check_closed_day_conflict(items)
    assert any(it["id"] == "d1" for it in closed), f"휴관일 충돌 못 잡음(2026-09-25=추석 연휴): {closed}"
    assert not any(it["id"] == "e1" for it in closed)

    applied = apply_gm_time_fill(items, gm_blanks)
    assert applied == 1 and items[3]["time"] == "14:00", items[3]  # 기본값 = 내부 검토

    print("[selfcheck] schedule_hygiene 4종 판정 OK")


# ═══════════════════════════════════════════
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="③ GM 시간 빈칸만 안전 규칙으로 채우고 push")
    ap.add_argument("--selfcheck", action="store_true", help="가짜 항목으로 판정 자체점검(네트워크 없음)")
    args = ap.parse_args()

    if args.selfcheck:
        _selfcheck()
        return

    pull = schedule_ssot.pull_from_live()
    source_note = "라이브(GAS)" if pull.get("ok") else f"원천 못 읽음({pull.get('reason')}) · 캐시로 점검"

    cal = schedule_ssot.load()
    items = cal.get("items") or []
    today = _kst_today()

    result = run_report(items, today, source_note)

    if args.apply:
        before = len(items)
        applied = apply_gm_time_fill(items, result["gm_blanks"])
        assert len(items) == before, "건수가 바뀜 — push 중단"  # push 전 건수 assert
        if applied:
            cal["items"] = items
            cal["updated_at"] = today.isoformat()
            schedule_ssot.CAL_PATH.write_text(json.dumps(cal, ensure_ascii=False, indent=2), encoding="utf-8")
            push = schedule_ssot.push_to_live(cal)
            print(f"[적용] ③ GM 시간 빈칸 {applied}건 채움 → push "
                  + ("성공" if push.get("ok") else f"실패: {push.get('reason')}"))
        else:
            print("[적용] 채울 항목 없음")

    counts = {k: len(v) for k, v in result.items()}
    worklog_log(
        "coo", "일정위생",
        f"전사일정 자동 정리 점검 — 중복{counts['dups']}·필러{counts['fillers']}"
        f"·GM빈칸{counts['gm_blanks']}·휴관충돌{counts['closed']}",
        result="ok" if pull.get("ok") else "warn",
        detail=source_note,
        ref="schedule_hygiene",
    )


if __name__ == "__main__":
    main()
