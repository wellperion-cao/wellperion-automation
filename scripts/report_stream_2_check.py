# -*- coding: utf-8 -*-
"""[스트림 #2] 시설&지원&주차 점검 및 이슈 현황 — 프로덕션 (CTO 2026-07-22).

통일 포맷 [하루 일과 정리]:
  ① 점검 핵심요약 3섹션 (support_check_summary — 텔레그램 점검현황방과 단일 진실)

종합접수 현황은 이 메시지에서 분리됨 — GM 2026-07-22 지시로 배9424(2026-07-21)의
'점검현황방 병합'을 되돌리고 별도 종합접수방으로 복원. 종합접수 현황 발송은
scripts/report_stream_2b_reception.py 참조.

텔레그램: 점검현황방(TELEGRAM_CHECK_CHAT_ID, -5136037543) 단일 발송.
카카오톡: ★운영+시설+지원+주차. 이 파일의 run(kakao_go=True)/--kakao-go는 독립 CLI
실행·수동 검증 전용 경로다. 프로덕션 자동 발송은 daily_scheduler.py run_daily_digest()가
이 모듈의 build_digest() 결과를 그대로 재사용해 별도로 처리한다(종합접수현황과 분리된
메시지 2통 중 하나 — GM 2026-07-22 go, KAKAO_GO_STREAM2 게이트). 두 경로를 동시에 켜면
중복 발송되므로 daily_scheduler.py 경유 시엔 이 CLI를 --kakao-go로 무인 실행하지 말 것.
발사 시각: 매일 22:30 (daily_scheduler.py run_daily_digest 경유) / 독립 실행 가능.
"""
from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import requests

SCRIPTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPTS_DIR.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from publish_digest import _load_env_val  # noqa: E402

TELEGRAM_CHAT_ID = int(os.environ.get("TELEGRAM_CHECK_CHAT_ID") or -5136037543)  # 점검현황방
KAKAO_ROOM = "★운영+시설+지원+주차"
_SENDER = REPO_ROOT / "scripts" / "kakao_report_sender.py"
_WEEKDAY_KOR = ["월", "화", "수", "목", "금", "토", "일"]


def _check_section(today: str) -> str:
    """support_check_summary 공용 모듈로 3섹션 핵심요약 렌더."""
    try:
        import support_check_summary as _scs
        lines, _ = _scs.build_summary_lines(date=today)
        return "\n".join(lines) if lines else "점검 데이터 없음."
    except Exception as e:
        return f"점검 조회 실패: {e}"


def build_digest(today: str | None = None) -> str:
    today = today or datetime.now().strftime("%Y-%m-%d")
    weekday = _WEEKDAY_KOR[datetime.strptime(today, "%Y-%m-%d").weekday()]
    header = (
        f"📊 [하루 일과 정리] {today}({weekday})\n"
        "🏗️ 시설&지원&주차 점검 및 이슈 현황"
    )
    return f"{header}\n\n{_check_section(today)}"


def _send_telegram(text: str) -> bool:
    token = _load_env_val("TELEGRAM_BOT_TOKEN")
    if not token:
        print("[stream2] TELEGRAM_BOT_TOKEN 미설정", flush=True)
        return False
    # parse_mode 미지정 = 평문 전송(점검요약 내 특수문자 MarkdownV2 이스케이프 불필요)
    r = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data={"chat_id": TELEGRAM_CHAT_ID, "text": text},
        timeout=20,
    )
    r.raise_for_status()
    return r.json().get("ok", False)


def _send_kakao(text: str) -> None:
    try:
        env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
        subprocess.run(
            [sys.executable, str(_SENDER), "--message", text, "--only-room", KAKAO_ROOM],
            cwd=str(REPO_ROOT), capture_output=True, text=True,
            encoding="utf-8", errors="replace", env=env, timeout=180,
        )
    except Exception as e:
        print(f"[stream2] 카카오 예외: {e}", flush=True)


def run(today: str | None = None, dry_run: bool = True, kakao_go: bool = False) -> str:
    today = today or datetime.now().strftime("%Y-%m-%d")
    text = build_digest(today)
    if dry_run:
        print(f"[stream2] DRY-RUN — chat_id={TELEGRAM_CHAT_ID} 발송 안 함", flush=True)
        return text
    ok = _send_telegram(text)
    print(f"[stream2] 텔레그램 {'완료' if ok else '실패'} → {TELEGRAM_CHAT_ID}", flush=True)
    if kakao_go:
        _send_kakao(text)
        print(f"[stream2] 카카오 → {KAKAO_ROOM}", flush=True)
    else:
        print(f"[stream2] 카카오 SKIP (kakao_go=False — GM go 게이트)", flush=True)
    return text


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="스트림 #2 점검+이슈 현황 보고")
    p.add_argument("--live", action="store_true", help="실발송")
    p.add_argument("--kakao-go", action="store_true", help="카카오 실발송 (GM go 게이트)")
    p.add_argument("--today", default=None, help="날짜 YYYY-MM-DD (기본=오늘)")
    a = p.parse_args()
    result = run(today=a.today, dry_run=not a.live, kakao_go=a.kakao_go)
    print("\n=== 렌더 ===")
    print(result)
