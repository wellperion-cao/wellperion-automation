#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
manager_directive_track.py — 사람 관리자 지시 추적 (배 2766 · GM 09-18)

정본 = status/briefs/CEO-2026-09-18-GM지시-자동화-파이프라인.md §7.
AI 지시 이행 점검(gm_directive_loop.py)과 같은 엔진·같은 이월 원장(status/gm_directive_carry.json)을
사람 관리자 3인(이경연 실장·이정헌 소장·나우열M)에게 그대로 확장한다 — 새 원장을 안 만든다(약속 L21).
「사람 지시」 판정·업무 SSOT 조회는 기존 관문(manager_task_index.fetch_ssot_rows)을 그대로 쓴다.

사용:
  manager_directive_track.py --top3 [--person "이경연 실장"] [--date 2026-09-18]
  manager_directive_track.py --remind [--send]
  manager_directive_track.py --morning
  manager_directive_track.py --selfcheck
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
REPO = SCRIPTS_DIR.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from manager_task_index import MANAGERS, MGR_PEOPLE as PEOPLE, fetch_ssot_rows  # noqa: E402
from gm_directive_loop import (  # noqa: E402
    _last_date_in, _evidence_tail, bump_carry, _load_json, _write_json_atomic,
)
from rep_approval_relay import _in_quiet_window  # noqa: E402
from collectors.ops_shared import gas_date10, TODO_DONE_STATUSES  # noqa: E402

PY = sys.executable
SSOT_URL = "https://erp.wellperion.com/erp/ (업무&결재)"
SENT_PATH = REPO / "status" / "manager_remind_sent.json"
# 방 갈래 — MANAGERS 의 room 설명에서 그대로 파생(값을 두 곳에 안 둔다).
ROOM_ROUTE = {name: ("kakao" if "중간관리자" in room else "telegram") for name, _dept, room in MANAGERS}


# 실제 SSOT 내용 칸은 "[GM 지시 2026-09-17 12:5x …]" 처럼 날짜·부연이 붙은 채로 온다 —
# gm_directive_loop.TAGS(카드 제목 정확 일치용)와 달리 여기는 괄호 접두만 본다.
_TAG_PREFIXES = ("[회장님 지시", "[대표님 지시", "[GM 지시")


def _is_tagged(r: dict) -> bool:
    text = f"{r.get('업무명') or ''} {r.get('내용') or ''}"
    return any(t in text for t in _TAG_PREFIXES)


def _is_gm_creator(r: dict) -> bool:
    return "김남욱" in str(r.get("생성자") or "")


def person_rows(rows: list, person: str) -> dict:
    """그 사람 담당 행 중 열린 것 / 그중 태그된 것 / GM 이 직접 생성한 것(count both — 따로 센다)."""
    mine = [r for r in rows if str(r.get("담당자") or "").strip() == person]
    open_rows = [r for r in mine if str(r.get("상태") or "") not in TODO_DONE_STATUSES]
    tagged = [r for r in open_rows if _is_tagged(r)]
    gm_direct = [r for r in open_rows if _is_gm_creator(r)]
    return {"open": open_rows, "tagged": tagged, "gm_direct": gm_direct}


def directive_rows_for(rows: list, person: str) -> list:
    """「사람 지시」 행만 — 태그(회장님/대표님/GM 지시) 또는 GM 직접 생성, 열린 것만, id 중복 제거.
    Top3·리마인드·아침 점검은 이 사람이 맡은 전체 업무가 아니라 이 부분집합만 본다(§7 정의)."""
    pr = person_rows(rows, person)
    seen: set = set()
    out = []
    for r in pr["tagged"] + pr["gm_direct"]:
        rid = r.get("id")
        if rid in seen:
            continue
        seen.add(rid)
        out.append(r)
    return out


# ═══ ① 오늘 집중 업무 Top 3 ══════════════════════════════════════════════
def top3(rows: list, person: str, today: str) -> tuple[list, list]:
    """(선택 3건, 역질문 필요 건 — 기한 또는 완료 기준이 빠짐)."""
    tomorrow = (date.fromisoformat(today) + timedelta(days=1)).isoformat()
    mine = directive_rows_for(rows, person)

    def sort_key(r):
        due = gas_date10(r.get("종료일"))
        overdue = bool(due) and due < today
        due_soon = due in (today, tomorrow)
        text = str(r.get("업무명") or "") + str(r.get("내용") or "")
        chairman = "[회장님 지시" in text or "[대표님 지시" in text
        touched = gas_date10(r.get("수정일") or r.get("생성일")) or "9999-99-99"
        return (0 if overdue else 1, 0 if due_soon else 1, 0 if chairman else 1, touched)

    ranked = sorted(mine, key=sort_key)
    ambiguous = [r for r in mine if not gas_date10(r.get("종료일")) or "완료 기준" not in str(r.get("내용") or "")]
    return ranked[:3], ambiguous


_DOD_RE = re.compile(r"완료\s*기준\s*[:：]\s*(.+)")


def dod_of(r: dict) -> str:
    m = _DOD_RE.search(str(r.get("내용") or ""))
    return m.group(1).strip()[:40] if m else "(완료 기준 없음)"


# ═══ ② 리마인드(기한 전일·당일) ═══════════════════════════════════════════
def remind_candidates(rows: list, today: str) -> dict:
    tomorrow = (date.fromisoformat(today) + timedelta(days=1)).isoformat()
    out: dict[str, list] = {}
    for person in PEOPLE:
        mine = [r for r in directive_rows_for(rows, person) if gas_date10(r.get("종료일")) in (today, tomorrow)]
        if mine:
            out[person] = mine
    return out


def build_remind_message(person: str, rows_for_person: list) -> str:
    honor = person if person.endswith("님") else f"{person}님"
    lines = [f"▪ {honor}, 업무&결재 SSOT 마감 리마인드입니다."]
    shown = rows_for_person[:4]
    for r in shown:
        due = gas_date10(r.get("종료일"))
        title = str(r.get("업무명") or "")[:30]
        lines.append(f"  · #{r.get('id')} {title} — 기한 {due}")
    extra = len(rows_for_person) - len(shown)
    if extra > 0:
        lines.append(f"  · 외 {extra}건 더")
    lines.append(f"어디: {SSOT_URL}")
    lines.append("무엇을: 진행 기록 한 줄 남기거나 완료로 표시해 주세요")
    return "\n".join(lines)


def send_reminders(rows: list, today: str, do_send: bool) -> list[tuple[str, str]]:
    """반환 [(person, outcome)] — outcome: dry-run·dedup-skip·quiet-skip·sent·fail."""
    cands = remind_candidates(rows, today)
    sent_log = _load_json(SENT_PATH, {})
    quiet = _in_quiet_window()
    results = []
    dirty = False
    for person, prows in cands.items():
        fresh = [r for r in prows if f"{r.get('id')}:{today}" not in sent_log]
        if not fresh:
            results.append((person, "dedup-skip"))
            continue
        msg = build_remind_message(person, fresh)
        if not do_send:
            print(f"[dry-run] → {person}\n{msg}\n")
            results.append((person, "dry-run"))
            continue
        route = ROOM_ROUTE.get(person, "telegram")
        if route == "kakao" and quiet:
            print(f"[quiet-skip] → {person}(카톡 조용시간대 · 다음 회차)\n{msg}\n")
            results.append((person, "quiet-skip"))
            continue
        if route == "kakao":
            rc = subprocess.run([PY, str(SCRIPTS_DIR / "kakao_report_sender.py"),
                                  "--only-room", "★중간관리자", "--sender", "웰리",
                                  "--message", msg]).returncode
        else:
            rc = subprocess.run([PY, str(SCRIPTS_DIR / "notify" / "telegram_user_send.py"),
                                  "--send", "--chat", "AtoA", "--text", msg]).returncode
        if rc == 0:
            for r in fresh:
                sent_log[f"{r.get('id')}:{today}"] = today
            dirty = True
            results.append((person, "sent"))
        else:
            results.append((person, "fail"))
    if dirty:
        _write_json_atomic(SENT_PATH, sent_log)
    return results


# ═══ ③ 아침 이행 점검 4분류 ═══════════════════════════════════════════════
def classify_person_row(r: dict, today: str) -> tuple[str, str]:
    status = str(r.get("상태") or "")
    note = str(r.get("내용") or "")
    if status in TODO_DONE_STATUSES:
        return "✅완료", _evidence_tail(note)
    last = _last_date_in(note)
    if not last:
        return "❌미착수", "기록 없음(생성 이후 무응답)"
    today_d = date.fromisoformat(today)
    days_since = (today_d - date.fromisoformat(last)).days
    if days_since <= 3:
        return "🔄진행중", _evidence_tail(note)
    due = gas_date10(r.get("종료일"))
    overdue = bool(due) and due < today
    if overdue:
        return "⚠️중단·정체", _evidence_tail(note)
    return "🔄진행중", _evidence_tail(note)  # 기록은 오래됐지만 기한 전 — 아직 여유


def morning_block(today: str) -> str:
    rows = fetch_ssot_rows() or []
    items = []
    for person in PEOPLE:
        for r in directive_rows_for(rows, person):
            icon, evidence = classify_person_row(r, today)
            items.append({"role": person, "key": f"todo:{r.get('id')}",
                          "title": str(r.get("업무명") or "")[:30], "icon": icon, "evidence": evidence})
    items = bump_carry(items)
    lines = [f"## 👥 사람 관리자 지시 이행 ({today})", "",
             "| 담당 | 건 | 상태 | 사유 | 이월 |", "|---|---|---|---|---|"]
    flagged = []
    for it in items:
        flag = " 🚩" if it.get("carry_count", 0) >= 3 else ""
        if flag:
            flagged.append(it)
        lines.append(f"| {it['role']} | {it['title']} | {it['icon']}{flag} | {it['evidence']} | {it.get('carry_count', 0)} |")
    if not items:
        lines.append("| - | 대상 없음 | - | - | - |")
    if flagged:
        lines.append("")
        lines.append("🚩 3회 이월 — GM 결정 필요(계속/중단/재설계)")
    if len(lines) > 20:
        lines = lines[:19] + ["…(생략)"]
    return "\n".join(lines)


# ═══ 자가점검 ════════════════════════════════════════════════════════════
def selfcheck() -> None:
    today = "2026-09-18"
    state_rows = [
        {"id": 1, "담당자": "실테스트", "업무명": "완료건", "상태": "완료", "내용": "[2026-09-17] 됨", "종료일": "2026-09-16"},
        {"id": 2, "담당자": "실테스트", "업무명": "진행건", "상태": "진행", "내용": "[2026-09-17] 진행중", "종료일": "2026-09-20"},
        {"id": 3, "담당자": "실테스트", "업무명": "정체건", "상태": "진행", "내용": "[2026-09-10] 막힘 — 자재 대기", "종료일": "2026-09-15"},
        {"id": 4, "담당자": "실테스트", "업무명": "미착수건", "상태": "", "내용": "", "종료일": "2026-09-25"},
    ]
    icons = {classify_person_row(r, today)[0] for r in state_rows}
    for expect in ("✅완료", "🔄진행중", "⚠️중단·정체", "❌미착수"):
        assert expect in icons, f"selfcheck 실패: {expect} 없음 → {icons}"

    rank_rows = [
        {"id": 10, "담당자": "랭크테스트", "업무명": "여유건", "생성자": "김남욱GM", "상태": "", "내용": "", "종료일": "2026-09-30", "수정일": "2026-09-01"},
        {"id": 11, "담당자": "랭크테스트", "업무명": "지남건", "생성자": "김남욱GM", "상태": "", "내용": "", "종료일": "2026-09-10", "수정일": "2026-09-01"},
        {"id": 12, "담당자": "랭크테스트", "업무명": "회장님건 [회장님 지시]", "상태": "", "내용": "완료 기준: 확인", "종료일": "2026-09-30", "수정일": "2026-09-05"},
    ]
    picked, ambiguous = top3(rank_rows, "랭크테스트", today)
    assert picked and picked[0]["id"] == 11, f"selfcheck 실패: 기한 지남 건이 1순위가 아님 → {picked}"
    assert any(r["id"] == 10 for r in ambiguous), "selfcheck 실패: 완료 기준 없는 건이 역질문 목록에 안 잡힘"

    assert _in_quiet_window(datetime(2026, 9, 18, 7, 30)) is True
    assert _in_quiet_window(datetime(2026, 9, 18, 12, 0)) is False

    print("selfcheck OK")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--top3", action="store_true")
    ap.add_argument("--person", default=None)
    ap.add_argument("--remind", action="store_true")
    ap.add_argument("--send", action="store_true")
    ap.add_argument("--morning", action="store_true")
    ap.add_argument("--selfcheck", action="store_true")
    ap.add_argument("--date", default=date.today().isoformat())
    args = ap.parse_args()

    if args.selfcheck:
        selfcheck()
        return 0

    if args.top3:
        rows = fetch_ssot_rows() or []
        targets = [args.person] if args.person else PEOPLE
        for person in targets:
            picked, ambiguous = top3(rows, person, args.date)
            print(f"### {person} — 오늘 집중 업무 Top 3")
            if not picked:
                print("  (해당 없음)")
            for r in picked:
                due = gas_date10(r.get("종료일")) or "(기한 없음)"
                print(f"▪ #{r.get('id')} {str(r.get('업무명') or '')[:30]} — {due} · {dod_of(r)}")
            if ambiguous:
                print("  역질문 필요(기한 또는 완료 기준 없음):")
                for r in ambiguous[:5]:
                    print(f"    - #{r.get('id')} {str(r.get('업무명') or '')[:30]}")
        return 0

    if args.remind:
        rows = fetch_ssot_rows() or []
        results = send_reminders(rows, args.date, args.send)
        if not results:
            print("(오늘·내일 마감 건 없음 — 보낼 것 없음)")
        for person, outcome in results:
            print(f"{person}: {outcome}")
        return 0

    if args.morning:
        print(morning_block(args.date))
        return 0

    ap.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
