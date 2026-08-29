#!/usr/bin/env python3
"""예약해 둔 카톡을 정해진 시각이 지나면 보낸다 — 예약 발송 큐 (2026-08-25 시우).

왜 만들었나
  GM 이 "이 내용은 내일 오전에 실장님께 전달해 줘" 처럼 **시각을 지정한 발송**을 요청한다.
  그때마다 1회성 예약작업을 만들면 작업 목록이 지저분해지고, 실행 뒤에도 껍데기가 남는다.
  그래서 잡은 하나만 두고(매일 09:00), 보낼 것이 큐에 있을 때만 보낸다 — 큐가 비면 아무 일도 안 한다.

어떻게 쓰나
  ① 예약: status/pending_kakao/ 에 JSON 한 장을 둔다.
     {"send_after": "2026-08-26 09:00", "room": "★중간관리자", "text": "...", "why": "GM 지시 ..."}
  ② 발송: 이 스크립트가 send_after 가 지난 것만 골라 보낸다.
  ③ 뒤처리: 보낸 파일은 status/pending_kakao/sent/ 로 옮긴다(기록 보존 · 두 번 안 나간다).

발신 관문은 기존 kakao_report_sender 하나뿐이다(약속 L21) — 여기서 직접 카톡 창을 만지지 않는다.
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
QUEUE = ROOT / "status" / "pending_kakao"
SENT = QUEUE / "sent"
SENDER = ROOT / "scripts" / "kakao_report_sender.py"


def _due(item: dict, now: datetime) -> bool:
    raw = str(item.get("send_after") or "").strip()
    if not raw:
        return True                      # 시각을 안 적었으면 다음 회차에 바로
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt) <= now
        except ValueError:
            continue
    print(f"[pending-kakao] 시각을 못 읽었다: {raw!r} — 보내지 않고 둔다", flush=True)
    return False


def run(dry_run: bool = True, now: datetime | None = None) -> list[Path]:
    now = now or datetime.now()
    if not QUEUE.exists():
        print("[pending-kakao] 큐 없음 — 할 일 없다", flush=True)
        return []
    sent: list[Path] = []
    for path in sorted(QUEUE.glob("*.json")):
        try:
            item = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:                                    # noqa: BLE001
            print(f"[pending-kakao] {path.name} 읽기 실패({e}) — 건너뛴다", flush=True)
            continue
        if not _due(item, now):
            continue
        room, text = str(item.get("room") or "").strip(), str(item.get("text") or "").strip()
        if not room or not text:
            print(f"[pending-kakao] {path.name} 방·본문이 비었다 — 건너뛴다", flush=True)
            continue
        if dry_run:
            print(f"[pending-kakao] DRY-RUN {room} ← {path.name}\n{text}\n", flush=True)
            continue
        # --sender 웰리 — 이 큐는 웰리가 초안 잡아 GM 승인 뒤 나가는 경로다(kakao_report_sender
        # 사람 방 발신 가드, 배 11070 ⑤).
        r = subprocess.run([sys.executable, str(SENDER), "--message", text,
                            "--only-room", room, "--sender", "웰리"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        ok = r.returncode == 0 and "DONE: 전송 완료" in (r.stdout or "")
        if not ok:
            tail = [ln for ln in (r.stdout or "").splitlines() if ln.strip()][-1:]
            print(f"[pending-kakao] 발송 실패({room}): {tail[0] if tail else '출력 없음'}", flush=True)
            continue                                              # 실패분은 큐에 남겨 다음 회차에 재시도
        SENT.mkdir(parents=True, exist_ok=True)
        path.rename(SENT / path.name)
        sent.append(path)
        print(f"[pending-kakao] 보냄 {room} ← {path.name}", flush=True)
    if not sent and not dry_run:
        print("[pending-kakao] 보낼 것 없음", flush=True)
    return sent


def _selftest() -> None:
    """예약 시각 판정만 확인 — 발송은 안 한다."""
    now = datetime(2026, 8, 26, 9, 0)
    assert _due({"send_after": "2026-08-26 09:00"}, now) is True
    assert _due({"send_after": "2026-08-26 08:59"}, now) is True
    assert _due({"send_after": "2026-08-26 09:01"}, now) is False
    assert _due({"send_after": "2026-08-27"}, now) is False
    assert _due({}, now) is True                       # 시각 미지정 = 다음 회차
    assert _due({"send_after": "내일 아침"}, now) is False   # 못 읽으면 안 보낸다
    print("자체검사 통과")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _selftest()
    else:
        run(dry_run="--live" not in sys.argv)
