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

SCRIPTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPTS_DIR.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from report_stream_1_impl import build_digest, seed_completion_cursor  # noqa: E402
from publish_digest import _load_env_val  # noqa: E402
try:  # 발신 관문(best-effort) — 임포트 실패해도 발신 무영향
    from tg_outbound_log import send as _tg_send
except Exception:
    def _tg_send(*a, **k):
        return False

TELEGRAM_CHAT_ID = int(os.environ.get("TELEGRAM_INQUIRY_CHAT_ID") or -5516675010)  # 문의알림방
KAKAO_ROOM = "★부서장"
_SENDER = REPO_ROOT / "scripts" / "kakao_report_sender.py"

# ── 「급할 때만」 강등 스위치 (배 11070 잔여 · 발신 체계 확정안 텔레그램 11곳 중 하나) ──
# status/telegram_urgent_only.json 하나를 3개 스트림(문의·점검·접수)이 같이 쓴다(약속 L21).
# urgent_only=false(기본) 면 지금처럼 매번 전문 발송 — 카카오 ★부서장 실발신이 확인되고
# 2주 병행이 끝난 뒤에만 true 로 켠다.
_URGENT_ONLY_FLAG = REPO_ROOT / "status" / "telegram_urgent_only.json"
_URGENT_MARKERS = ("👉", "❗", "🔴", "기한 초과", "촉구")


def _urgent_only_enabled(stream_key: str) -> bool:
    try:
        import json
        cfg = json.loads(_URGENT_ONLY_FLAG.read_text(encoding="utf-8"))
        return bool((cfg.get(stream_key) or {}).get("urgent_only", False))
    except Exception:
        return False  # 못 읽으면 안전측(종전처럼 매번 발송)


def _looks_urgent(text: str) -> bool:
    """이상 신호 마커가 있는가 — 담당미배정 3일+ 촉구(👉)·기준이탈(❗🔴)·기한 초과."""
    return any(m in text for m in _URGENT_MARKERS)


def build_plain(today: str | None = None) -> str:
    """HTML 태그 제거 + 엔티티 복원 → 카카오 평문.

    ★2026-08-05 시토 수리 — persist_completion=False 필수. run()이 먼저 build_digest()를
    persist_completion=not dry_run 으로 호출해 완료통보 커서를 이미 전진시킨 뒤, 카카오용
    평문을 뽑으려고 이 함수가 build_digest()를 다시 부른다. 인자 없이 부르면 기본값 True라
    같은 회차에 커서가 두 번 전진해, 방금 전 텔레그램에 실린 "✅ 처리 완료 알림" 블록이
    카카오 쪽에서는 이미 seen 처리돼 사라진다(같은 내용이 채널마다 달라지는 조용한 드리프트
    — bb89e240d 의 dry-run 커서 가드가 놓친 세 번째 호출 지점)."""
    raw = build_digest(today, persist_completion=False)
    raw = re.sub(r"<pre>\s*", "", raw)
    raw = re.sub(r"\s*</pre>", "", raw)
    return _html_mod.unescape(raw)


def _send_telegram(html_text: str) -> bool:
    token = _load_env_val("TELEGRAM_BOT_TOKEN")
    if not token:
        print("[stream1] TELEGRAM_BOT_TOKEN 미설정", flush=True)
        return False
    return _tg_send(token, TELEGRAM_CHAT_ID, html_text, source="report_stream_1_inquiry._send_telegram",
                     extra={"parse_mode": "HTML"}, timeout=20)


def _send_kakao(plain_text: str) -> None:
    try:
        env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
        subprocess.run(
            # --sender 문의정리 — ★부서장이 사람 방 가드(약속 L24)에 들어가며 추가.
            [sys.executable, str(_SENDER), "--message", plain_text, "--only-room", KAKAO_ROOM,
             "--sender", "문의정리"],
            cwd=str(REPO_ROOT), capture_output=True, text=True,
            encoding="utf-8", errors="replace", env=env, timeout=180,
        )
    except Exception as e:
        print(f"[stream1] 카카오 예외: {e}", flush=True)


def run(today: str | None = None, dry_run: bool = True, kakao_go: bool = False) -> str:
    """메시지 렌더 + 조건부 발송. 렌더된 HTML 문자열 반환."""
    today = today or datetime.now().strftime("%Y-%m-%d")
    html_text = build_digest(today, persist_completion=not dry_run)
    if dry_run:
        print(f"[stream1] DRY-RUN — chat_id={TELEGRAM_CHAT_ID} 발송 안 함", flush=True)
        return html_text
    if _urgent_only_enabled("inquiry") and not _looks_urgent(html_text):
        print(f"[stream1] 텔레그램 SKIP — 급할 때만 모드·이상 신호 없음", flush=True)
    else:
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
    p.add_argument("--seed-completion", action="store_true",
                    help="처리완료 통보 커서 시딩(enabled:true 켜기 직전 1회 — 백로그 통보 방지)")
    a = p.parse_args()
    if a.seed_completion:
        n = seed_completion_cursor()
        print(f"[stream1] 완료 커서 시딩 완료 — 현재 배정·등록 {n}건을 '이미 통보됨'으로 표시")
        sys.exit(0)
    result = run(today=a.today, dry_run=not a.live, kakao_go=a.kakao_go)
    print("\n=== 렌더 ===")
    print(result)
