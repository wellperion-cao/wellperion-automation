# -*- coding: utf-8 -*-
"""회장님 회의 2종 리마인드 — 매월 5일·20일 07:5x GM 봇방 한 줄 (웰리 요청 · 회장님 말씀 2026-09-16 · 시토).

  · 5일  → 중간회의(회장님·대표님·GM · 매월 15~20일) — 회장님 일정 확인해 날짜 확정 → 전사일정 evt-20261015-gm-회장님지시… 갱신
  · 20일 → 월말 결산 회의(회장님·대표님·GM·팀 리더 · 매월 첫째 주) — 요일 정해 회장님 일정 확인
    첫 회 10/1(목) = evt-20260930-gm-회장님지시월말결산회의(next_due 10/01 · repeat 매월 첫째 주)

새 예약작업 없음 — scripts/ops_morning_digest.bat(07:30 · 07:50 통 뒤)이 매일 부르고, 이 파일이 날짜를 보고 그날만 보낸다.
같은 날 두 번 안 보낸다(status/monthly_meeting_reminders.json 에 마지막 발송 날짜). 발신 = notify.telegram_send.send
(GM 봇방 = telegram_bot/.env TG_CHAT_ID · 새 발신기 금지). 자체점검: --selfcheck · 미리보기: --dry-run [--date YYYY-MM-DD]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "status" / "monthly_meeting_reminders.json"
sys.path.insert(0, str(ROOT / "scripts"))

REMINDERS = {
    5: ("mid", "📅 중간회의(회장님·대표님·GM · 매월 15~20일) — 회장님 일정 확인해 날짜 확정 → 전사일정 evt-20261015-gm-회장님지시… 갱신"),
    20: ("close", "📅 월말 결산 회의(회장님·대표님·GM·팀 리더 · 매월 첫째 주) — 요일 정해 회장님 일정 확인 (다음 = 전사일정 evt-20260930-gm-회장님지시월말결산회의)"),
}


def due(today: dt.date) -> tuple[str, str] | None:
    """오늘 보낼 리마인드 (키, 본문) — 없으면 None. 순수 함수."""
    return REMINDERS.get(today.day)


def _load_state() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def run(today: dt.date, dry_run: bool) -> int:
    item = due(today)
    if not item:
        print(f"[skip] {today} 리마인드 날 아님(5일·20일)")
        return 0
    key, text = item
    state = _load_state()
    stamp = f"{today.isoformat()}:{key}"
    if state.get("last") == stamp:
        print(f"[skip] 오늘 이미 보냄 {stamp}")
        return 0
    text = f"{text}\n— 회장님 말씀 2026-09-16 · 매월 {today.day}일 자동 리마인드(시토)"
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
        STATE.parent.mkdir(parents=True, exist_ok=True)
        STATE.write_text(json.dumps({"last": stamp, "sent_at": dt.datetime.now().isoformat(timespec="seconds")},
                                    ensure_ascii=False), encoding="utf-8")
    print(f"DONE ok={ok} {stamp}")
    return 0 if ok else 1


def _selfcheck() -> None:
    assert due(dt.date(2026, 10, 5))[0] == "mid" and "중간회의" in due(dt.date(2026, 10, 5))[1]
    assert due(dt.date(2026, 10, 20))[0] == "close" and "결산" in due(dt.date(2026, 10, 20))[1]
    assert due(dt.date(2026, 10, 6)) is None and due(dt.date(2026, 10, 1)) is None
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
