# -*- coding: utf-8 -*-
"""
notify_gm_progress.py — GM 개인 채널로 "완료마다 1줄" 진행 보고 헬퍼.
─────────────────────────────────────────────────────────────────────────────
배경(2026-07-13, GM 지시): 의미 있는 완료(딜리버러블)마다 GM 채널로 짧게
1줄 보고. 채널 = @namuki_report_bot, chat_id GM_CHAT_ID(GM 개인·실측 검증).

clevel_post_action.py 의 정식 L18 완료 보고(C-Level .bat/큐 흐름)와는 별개의
경량 채널 — 세션 중 웰리가 의미 있는 완료를 즉석에서 알릴 때 직접 호출한다.

스팸 방지 3중 게이트:
  1) PROGRESS_REPORT_LIVE env(킬스위치) — "0"/"false"/"off"/"no" 로 끄면 미발송.
  2) dedup — 동일 summary 가 최근 DEDUP_WINDOW_MINUTES 이내 발송된 적 있으면 스킵.
  3) daily cap — 하루 DAILY_CAP 건 초과 시 스킵(폭주 방지 안전판).
  4) 루틴 필터(is_routine) — task_id/커밋 메시지에 ADHOC·auto-log·chore·mirror
     류 마커가 있으면 호출측(clevel_post_action.py 등)이 애초에 notify() 를
     부르지 않도록 판별하는 헬퍼(스팸 원천 차단).

CLI:
  python scripts/notify_gm_progress.py "요약" [링크]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
_ROOT = _SCRIPTS_DIR.parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

# ── 상수 ─────────────────────────────────────────────────────────────────────
GM_CHAT_ID = 8254867551  # GM 개인 채널(@namuki_report_bot) · 2026-07-13 실측 검증
LOG_PATH = _ROOT / "status" / "progress_report_log.jsonl"
DAILY_CAP = 40
DEDUP_WINDOW_MINUTES = 60
KST = timezone(timedelta(hours=9))

_ROUTINE_MARKERS = ("adhoc", "auto-log", "autolog", "chore", "mirror")


# ── 루틴/자동 마커 판별(스팸 원천 차단용 헬퍼 — 호출측이 사용) ────────────────
def is_routine(*texts: str) -> bool:
    """task_id·커밋 메시지 등에 루틴/자동 마커(ADHOC·auto-log·chore·mirror)가
    있으면 True. 대소문자 무시. 호출측(clevel_post_action.py 등)이 완료라도
    notify 호출 자체를 건너뛰는 데 사용한다."""
    for t in texts:
        low = (t or "").lower()
        if any(marker in low for marker in _ROUTINE_MARKERS):
            return True
    return False


def _live() -> bool:
    val = os.environ.get("PROGRESS_REPORT_LIVE", "1").strip().lower()
    return val not in ("0", "false", "off", "no")


def _now_kst() -> datetime:
    return datetime.now(tz=KST)


def _load_log(log_path: Path) -> list:
    if not log_path.exists():
        return []
    out = []
    try:
        for line in log_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:
                continue
    except Exception:
        pass
    return out


def _append_log(log_path: Path, record: dict) -> None:
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _recent_duplicate(summary: str, now: datetime, entries: list) -> bool:
    cutoff = now - timedelta(minutes=DEDUP_WINDOW_MINUTES)
    for rec in entries:
        if rec.get("summary") != summary or not rec.get("sent"):
            continue
        try:
            ts = datetime.fromisoformat(rec["ts"])
        except Exception:
            continue
        if ts >= cutoff:
            return True
    return False


def _today_sent_count(now: datetime, entries: list) -> int:
    today = now.strftime("%Y-%m-%d")
    return sum(1 for rec in entries if rec.get("sent") and str(rec.get("ts", "")).startswith(today))


def notify(summary: str, link: str | None = None, *, dry_run: bool = False,
           now: datetime | None = None, sender=None, log_path=None) -> dict:
    """
    GM 채널로 "✅ [완료] {summary} {link}" 1줄 발송.

    sender: send(chat_id, text) -> bool. None 이면 notify.telegram_send.send 지연 로드.
    dry_run: True 면 실제 발송/로그 기록 없이 payload 만 반환(네트워크 0).
    반환: {"sent": bool, "reason": str, "text": str}
    """
    log_path = Path(log_path) if log_path else LOG_PATH
    now = now or _now_kst()
    text = "✅ [완료] " + summary.strip() + (" " + link.strip() if link else "")

    if dry_run:
        return {"sent": False, "reason": "dry_run", "text": text}

    if not _live():
        return {"sent": False, "reason": "gate_off", "text": text}

    entries = _load_log(log_path)

    if _recent_duplicate(summary.strip(), now, entries):
        return {"sent": False, "reason": "dedup", "text": text}

    if _today_sent_count(now, entries) >= DAILY_CAP:
        return {"sent": False, "reason": "daily_cap", "text": text}

    if sender is None:
        from notify.telegram_send import send as sender  # noqa: PLC0415

    ok = bool(sender(GM_CHAT_ID, text))
    _append_log(log_path, {
        "ts": now.isoformat(), "summary": summary.strip(), "link": link or "",
        "sent": ok, "chat_id": GM_CHAT_ID,
    })
    return {"sent": ok, "reason": "sent" if ok else "send_failed", "text": text}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="GM 개인 채널 진행 보고 1줄 발송 헬퍼")
    ap.add_argument("summary", help='보고 요약 1줄 (예: "발행 파이프라인 배선 완료")')
    ap.add_argument("link", nargs="?", default=None, help="증거/산출물 링크(선택)")
    ap.add_argument("--dry-run", action="store_true", help="실제 발송 없이 payload 미리보기")
    args = ap.parse_args(argv)

    out = notify(args.summary, args.link, dry_run=args.dry_run)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    if args.dry_run or out["reason"] in ("sent", "gate_off", "dedup", "daily_cap"):
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
