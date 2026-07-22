# -*- coding: utf-8 -*-
"""[스트림 #1] 문의 및 컨택&등록 현황 보고 — 프로덕션 라우터 (CTO 2026-07-22).

확정 포맷(msg5618): report_stream_1_impl.build_digest() 위임.
  - 멤버십 등급만 · 컨택&등록[진행상태] · 담당미배정 리스트노출 + 3일+ 촉구👉

텔레그램: 문의알림방(TELEGRAM_INQUIRY_CHAT_ID, -5516675010) HTML 발송.
카카오톡: ★부서장 (kakao_go=True 시만 실발송 — 기본 드라이런·GM go 게이트).
발사 시각: 매일 22:30 (daily_scheduler.py run_daily_digest 경유) / 독립 실행 가능.
"""
from __future__ import annotations

import html as _html_mod
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import requests

SCRIPTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPTS_DIR.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from report_stream_1_impl import build_digest  # noqa: E402
from publish_digest import _load_env_val  # noqa: E402

TELEGRAM_CHAT_ID = int(os.environ.get("TELEGRAM_INQUIRY_CHAT_ID") or -5516675010)  # 문의알림방
KAKAO_ROOM = "★부서장"
_SENDER = REPO_ROOT / "scripts" / "kakao_report_sender.py"


def build_plain(today: str | None = None) -> str:
    """HTML 태그 제거 + 엔티티 복원 → 카카오 평문."""
    raw = build_digest(today)
    raw = re.sub(r"<pre>\s*", "", raw)
    raw = re.sub(r"\s*</pre>", "", raw)
    return _html_mod.unescape(raw)


def _send_telegram(html_text: str) -> bool:
    token = _load_env_val("TELEGRAM_BOT_TOKEN")
    if not token:
        print("[stream1] TELEGRAM_BOT_TOKEN 미설정", flush=True)
        return False
    r = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data={"chat_id": TELEGRAM_CHAT_ID, "text": html_text, "parse_mode": "HTML"},
        timeout=20,
    )
    r.raise_for_status()
    return r.json().get("ok", False)


def _send_kakao(plain_text: str) -> None:
    try:
        env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
        subprocess.run(
            [sys.executable, str(_SENDER), "--message", plain_text, "--only-room", KAKAO_ROOM],
            cwd=str(REPO_ROOT), capture_output=True, text=True,
            encoding="utf-8", errors="replace", env=env, timeout=180,
        )
    except Exception as e:
        print(f"[stream1] 카카오 예외: {e}", flush=True)


def run(today: str | None = None, dry_run: bool = True, kakao_go: bool = False) -> str:
    """메시지 렌더 + 조건부 발송. 렌더된 HTML 문자열 반환."""
    today = today or datetime.now().strftime("%Y-%m-%d")
    html_text = build_digest(today)
    if dry_run:
        print(f"[stream1] DRY-RUN — chat_id={TELEGRAM_CHAT_ID} 발송 안 함", flush=True)
        return html_text
    ok = _send_telegram(html_text)
    print(f"[stream1] 텔레그램 {'완료' if ok else '실패'} → {TELEGRAM_CHAT_ID}", flush=True)
    if kakao_go:
        _send_kakao(build_plain(today))
        print(f"[stream1] 카카오 → {KAKAO_ROOM}", flush=True)
    else:
        print(f"[stream1] 카카오 SKIP (kakao_go=False — GM go 게이트)", flush=True)
    return html_text


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="스트림 #1 문의+컨택&등록 현황 보고")
    p.add_argument("--live", action="store_true", help="실발송 (기본=dry_run)")
    p.add_argument("--kakao-go", action="store_true", help="카카오 실발송 (GM go 게이트)")
    p.add_argument("--today", default=None, help="날짜 YYYY-MM-DD (기본=오늘)")
    a = p.parse_args()
    result = run(today=a.today, dry_run=not a.live, kakao_go=a.kakao_go)
    print("\n=== 렌더 ===")
    print(result)
