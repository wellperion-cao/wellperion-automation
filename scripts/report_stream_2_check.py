# -*- coding: utf-8 -*-
"""[스트림 #2] 시설&지원&주차 점검 및 이슈+종합접수 현황 — 프로덕션 (CTO 2026-07-22).

통일 포맷 [하루 일과 정리]:
  ① 점검 핵심요약 3섹션 (support_check_summary — 텔레그램 점검현황방과 단일 진실)
  ━━━━━━━━━━
  ② 종합접수 현황 병합 (VOC_EXEC_URL reg_list — GM 2026-07-21 지시, 접수처 별도방 폐지)

텔레그램: 점검현황방(TELEGRAM_CHECK_CHAT_ID, -5136037543) 단일 발송.
          종합접수처(-5065206276) 별도 발송 폐지 — 이 메시지에 병합됨.
카카오톡: ★운영+시설+지원+주차 (kakao_go=True 시만 실발송 — GM go 게이트).
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

from collectors.ops_shared import VOC_EXEC_URL, gas_get  # noqa: E402
from publish_digest import _load_env_val  # noqa: E402

TELEGRAM_CHAT_ID = int(os.environ.get("TELEGRAM_CHECK_CHAT_ID") or -5136037543)  # 점검현황방
KAKAO_ROOM = "★운영+시설+지원+주차"
_SENDER = REPO_ROOT / "scripts" / "kakao_report_sender.py"
_WEEKDAY_KOR = ["월", "화", "수", "목", "금", "토", "일"]
_DIVIDER = "━" * 10


def _check_section(today: str) -> str:
    """support_check_summary 공용 모듈로 3섹션 핵심요약 렌더."""
    try:
        import support_check_summary as _scs
        lines, _ = _scs.build_summary_lines(date=today)
        return "\n".join(lines) if lines else "점검 데이터 없음."
    except Exception as e:
        return f"점검 조회 실패: {e}"


def _reception_section(today: str) -> str:
    """VOC_EXEC_URL reg_list → 오늘 종합접수 현황 + 미처리 리스트."""
    resp = gas_get(VOC_EXEC_URL, {"action": "reg_list"}, timeout=20, label="stream2-voc")
    if resp is None:
        return "📮 종합접수 현황\n조회 실패 (GAS 응답 없음)"
    try:
        data = resp.json()
        rows = data.get("data", []) if data.get("ok") else None
    except Exception:
        rows = None
    if rows is None:
        return "📮 종합접수 현황\n응답 파싱 실패"

    today_rows = [r for r in rows if str(r.get("createdAt", "")).startswith(today)]
    if not today_rows:
        return "📮 종합접수 현황\n오늘 신규 접수 없음."

    cat_cnt: dict[str, int] = {}
    undone: list[dict] = []
    for r in today_rows:
        cat = str(r.get("category") or "기타").strip()
        cat_cnt[cat] = cat_cnt.get(cat, 0) + 1
        if str(r.get("status", "")) != "완료":
            undone.append(r)

    cat_str = " · ".join(f"{c}:{n}" for c, n in sorted(cat_cnt.items(), key=lambda x: -x[1]))
    lines = [
        "📮 종합접수 현황",
        f"총 {len(today_rows)}건 (미처리 {len(undone)}건)  {cat_str}",
    ]
    if undone:
        lines.append(f"⚠️ 미처리 {len(undone)}건")
        for r in undone[:5]:
            cat = str(r.get("category") or "").strip()
            content = str(r.get("content") or "").strip()[:28]
            st = str(r.get("status") or "").strip() or "접수"
            lines.append(f"  · [{cat}] {content} — {st}")
        if len(undone) > 5:
            lines.append(f"  · 외 {len(undone) - 5}건")
    return "\n".join(lines)


def build_digest(today: str | None = None) -> str:
    today = today or datetime.now().strftime("%Y-%m-%d")
    weekday = _WEEKDAY_KOR[datetime.strptime(today, "%Y-%m-%d").weekday()]
    header = (
        f"📊 [하루 일과 정리] {today}({weekday})\n"
        "🏗️ 시설&지원&주차 점검 및 이슈+종합접수 현황"
    )
    return f"{header}\n\n{_check_section(today)}\n\n{_DIVIDER}\n{_reception_section(today)}"


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
    p = argparse.ArgumentParser(description="스트림 #2 점검+이슈+종합접수 현황 보고")
    p.add_argument("--live", action="store_true", help="실발송")
    p.add_argument("--kakao-go", action="store_true", help="카카오 실발송 (GM go 게이트)")
    p.add_argument("--today", default=None, help="날짜 YYYY-MM-DD (기본=오늘)")
    a = p.parse_args()
    result = run(today=a.today, dry_run=not a.live, kakao_go=a.kakao_go)
    print("\n=== 렌더 ===")
    print(result)
