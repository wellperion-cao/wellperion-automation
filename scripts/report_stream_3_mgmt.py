# -*- coding: utf-8 -*-
"""[스트림 #3] 매출 및 운영+인사 현황 보고 — 프로덕션 라우터 (CTO 2026-07-22).

확정 포맷(msg5624 v3 · GM '너무길다' 54% 압축 후 ok 확정):
  report_stream_3_impl.build_digest() 위임 (list[str] — 4096자 분할).
  ⏰지연 체크리스트 + 카테고리 건수요약 + ⏳임박D7 + 📋결재대기 + 🎯분기목표.

텔레그램: GM 업무보고방(8254867551) 발송 — 실무진방 발송은 GM go 후속과제.
카카오톡: 차의주 회장님 · 웰페리온 관리부 · ★ 운영부 3방
          (kakao_go=True 시만 실발송 — GM go 게이트).
발사 시각: 매일 09:30 (daily_scheduler.py run_stream_3_mgmt 경유) / 독립 실행 가능.
시우(COO) 최종목표 씨앗: 완전 자율화 시 COO 도메인 인계 예정.
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

from report_stream_3_impl import build_digest  # noqa: E402
from publish_digest import _load_env_val  # noqa: E402
from tg_outbound_log import send as _tg_gateway_send  # noqa: E402 — 발신 관문(페이싱+429재시도+계측, 배99)

TELEGRAM_CHAT_ID = 8254867551  # GM 업무보고방 — 안전 우선 (실무진방 발송=GM go 후속)
KAKAO_ROOMS = ["차의주 회장님", "웰페리온 관리부", "★ 운영부"]  # kakao_rooms.json 동일 순서
_SENDER = REPO_ROOT / "scripts" / "kakao_report_sender.py"


def _strip_html(text: str) -> str:
    """HTML 태그 제거 + 엔티티 복원 → 카카오 평문."""
    return _html_mod.unescape(re.sub(r"<[^>]+>", "", text))


def _send_telegram_parts(parts: list[str]) -> bool:
    token = _load_env_val("TELEGRAM_BOT_TOKEN")
    if not token:
        print("[stream3] TELEGRAM_BOT_TOKEN 미설정", flush=True)
        return False
    # 배99(2026-07-25): 직접 requests.post → tg_outbound_log.send 관문 경유로 수렴.
    # 전역 페이싱·429 자가재시도·logs/telegram_sent-*.log 계측이 자동 편입된다(L21).
    ok_all = True
    for i, text in enumerate(parts, 1):
        ok = _tg_gateway_send(
            token, TELEGRAM_CHAT_ID, text,
            source="report_stream_3_mgmt", extra={"parse_mode": "HTML"},
        )
        if not ok:
            ok_all = False
        print(f"[stream3] 텔레그램 파트{i}/{len(parts)} {'완료' if ok else '실패'}", flush=True)
    return ok_all


def _send_kakao(parts: list[str]) -> None:
    plain = "\n\n".join(_strip_html(p) for p in parts)
    for room in KAKAO_ROOMS:
        try:
            env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
            subprocess.run(
                [sys.executable, str(_SENDER), "--message", plain, "--only-room", room],
                cwd=str(REPO_ROOT), capture_output=True, text=True,
                encoding="utf-8", errors="replace", env=env, timeout=180,
            )
            print(f"[stream3] 카카오 → {room}", flush=True)
        except Exception as e:
            print(f"[stream3] 카카오 {room} 예외: {e}", flush=True)


def run(today: str | None = None, dry_run: bool = True, kakao_go: bool = False,
        prefix_parts: list[str] | None = None) -> list[str]:
    """메시지 렌더 + 조건부 발송. 렌더된 파트 리스트 반환.

    prefix_parts: 배10011(2026-07-24) — 09:10 모듈데일리(자동화현황방, GM 2인 전용이라
    흡수 가능·GM 결정)에서 흡수한 텍스트를 맨 앞 파트로 얹는다. HTML 파싱 모드라 태그
    깨짐 방지로 html.escape 후 붙인다. None/빈 리스트면 기존과 동일(무영향)."""
    today = today or datetime.now().strftime("%Y-%m-%d")
    parts = build_digest(today)
    if prefix_parts:
        escaped = [_html_mod.escape(p, quote=False) for p in prefix_parts]
        header = "📊 자동화현황(09:10 흡수)\n" + "\n\n".join(escaped)
        parts = [header] + parts
    if dry_run:
        print(f"[stream3] DRY-RUN — {len(parts)}파트 chat_id={TELEGRAM_CHAT_ID} 발송 안 함", flush=True)
        return parts
    ok = _send_telegram_parts(parts)
    print(f"[stream3] 텔레그램 {'완료' if ok else '일부실패'} → {TELEGRAM_CHAT_ID}", flush=True)
    if kakao_go:
        _send_kakao(parts)
    else:
        print(f"[stream3] 카카오 SKIP (kakao_go=False — GM go 게이트)", flush=True)
    return parts


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="스트림 #3 매출+운영+인사 현황 보고")
    p.add_argument("--live", action="store_true", help="실발송")
    p.add_argument("--kakao-go", action="store_true", help="카카오 실발송 (GM go 게이트)")
    p.add_argument("--today", default=None, help="날짜 YYYY-MM-DD (기본=오늘)")
    a = p.parse_args()
    parts = run(today=a.today, dry_run=not a.live, kakao_go=a.kakao_go)
    print(f"\n=== 렌더 ({len(parts)}파트) ===")
    for i, pt in enumerate(parts, 1):
        print(f"--- 파트 {i}/{len(parts)} ({len(pt)}자) ---")
        print(pt)
