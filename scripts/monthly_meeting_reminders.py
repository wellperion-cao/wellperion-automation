# -*- coding: utf-8 -*-
"""회장님 회의 2종 리마인드 — 매월 5일·20일 07:5x GM 봇방 한 줄 (웰리 요청 · 회장님 말씀 2026-09-16 · 시토).

원장 = status/meeting_system.json(웰리 배 2706 · 정본). 무조건 보내지 않는다 — 판정은 화면(meeting_system_page.py
「알림(원장에서 파생)」 절)과 같은 함수 하나(meeting_system_page.reminder_verdict)를 쓴다:
  · 5일  → 중간회의(mid) 다음 회차의 날짜가 비어 있을 때만 (회장님 일정 확인해 날짜 확정 → 전사일정 갱신)
  · 20일 → 월말 결산 회의(closing) 다음 회차에 「리더별 결산 한 장」 미제출이 있을 때만 (요일 정해 회장님 일정 확인)
보낸 뒤 그 회차 rounds[].reminders 에 날짜를 한 줄 append — 같은 날 두 번 안 보낸다(그게 중복 차단이다 · 별도 상태 파일 없음).
새 예약작업 없음 — scripts/ops_morning_digest.bat(07:30 · 07:50 통 뒤)이 매일 부르고, 이 파일이 날짜를 보고 그날만 보낸다.
발신 = notify.telegram_send.send(GM 봇방 = telegram_bot/.env TG_CHAT_ID · 새 발신기 금지). 자체점검 --selfcheck · 미리보기 --dry-run [--date].
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "status" / "meeting_system.json"
sys.path.insert(0, str(ROOT / "scripts"))
from meeting_system_page import next_round, reminder_verdict  # noqa: E402  — 판정은 한 곳

DAY_TO_MEETING = {5: "mid", 20: "closing"}
TEXT = {
    "mid": "📅 중간회의(회장님·대표님·GM · 매월 15~20일) {ym} — {why} · 회장님 일정 확인해 날짜 확정 → 전사일정 갱신",
    "closing": "📅 월말 결산 회의(회장님·대표님·GM·팀 리더 · 매월 첫째 주) {ym} — {why} · 요일 정해 회장님 일정 확인",
}


def due(today: dt.date, led: dict) -> tuple[dict, str] | None:
    """오늘 보낼 (회차, 본문) — 날이 아니거나 판정이 「안 나감」이거나 오늘 이미 보냈으면 None. 순수 함수."""
    meeting = DAY_TO_MEETING.get(today.day)
    if not meeting:
        return None
    rnd = next_round(led, meeting)
    if not rnd:
        return None
    if today.isoformat() in (rnd.get("reminders") or []):
        return None
    verdict, why = reminder_verdict(meeting, rnd)
    if not verdict:
        return None
    text = TEXT[meeting].format(ym=rnd.get("ym", ""), why=why)
    return rnd, text + f"\n— 회장님 말씀 2026-09-16 · 매월 {today.day}일 자동 리마인드(시토) · 체계 화면 coo/chairman/회의체계.html"


def _load() -> dict:
    return json.loads(LEDGER.read_text(encoding="utf-8"))


def _save(led: dict) -> None:
    fd, tmp = tempfile.mkstemp(dir=str(LEDGER.parent), prefix=".meeting-", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(led, f, ensure_ascii=False, indent=1)
    os.replace(tmp, LEDGER)


def run(today: dt.date, dry_run: bool) -> int:
    led = _load()
    item = due(today, led)
    if not item:
        print(f"[skip] {today} 보낼 리마인드 없음(5·20일 아님 · 판정 안 나감 · 이미 보냄 중 하나)")
        return 0
    rnd, text = item
    if dry_run:
        print("[dry-run] " + text)
        return 0
    from collectors.ops_shared import _env_line
    from notify.telegram_send import send
    chat = _env_line("TG_CHAT_ID")
    if not chat:
        print("[fail] TG_CHAT_ID 없음(telegram_bot/.env)")
        return 1
    ok = send(chat, text)
    if ok:
        rnd.setdefault("reminders", []).append(today.isoformat())
        _save(led)
    print(f"DONE ok={ok} {rnd.get('meeting')} {rnd.get('ym')}")
    return 0 if ok else 1


def _selfcheck() -> None:
    led = {"rounds": [
        {"meeting": "mid", "ym": "2026-10", "date": "", "status": "준비중"},
        {"meeting": "closing", "ym": "2026-10", "date": "2026-10-01", "status": "준비중",
         "checks": {"리더별 결산 한 장 — 이경연 실장님": False}},
    ]}
    assert due(dt.date(2026, 10, 5), led)[0]["meeting"] == "mid"
    assert "미제출 1건" in due(dt.date(2026, 9, 20), led)[1]
    assert due(dt.date(2026, 10, 6), led) is None                       # 날 아님
    led["rounds"][0]["date"] = "2026-10-16"
    assert due(dt.date(2026, 10, 5), led) is None                       # 날짜 확정 → 안 나감
    led["rounds"][1]["reminders"] = ["2026-09-20"]
    assert due(dt.date(2026, 9, 20), led) is None                       # 오늘 이미 보냄
    print("monthly_meeting_reminders selfcheck OK")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--date", help="YYYY-MM-DD (시험용)")
    ap.add_argument("--selfcheck", action="store_true")
    a = ap.parse_args()
    if a.selfcheck:
        _selfcheck()
        return 0
    today = dt.date.fromisoformat(a.date) if a.date else dt.date.today()
    return run(today, a.dry_run)


if __name__ == "__main__":
    sys.exit(main())
