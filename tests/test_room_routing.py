# -*- coding: utf-8 -*-
"""두 텔레그램 방 경계 자체 점검 (2026-08-04 GM "두 방 혼선 정리").

대표 발신 종류마다 목적지가 규약(ssot/자율화규약.md §4 · SKILL §4-2-1)대로 나오는지 확인:
  ① 배 완료·진행 보고(L18, clevel_post_action) → AI 진행현황방 — 역할·대소문자 무관
  ② 진행 1줄 헬퍼(notify_gm_progress)          → AI 진행현황방(-5498808140)
  ③ 하루 일과 정리(report_stream_3_mgmt)        → 업무보고방(8254867551)
  ④ 아침 보고(report_stream_1_impl)             → 업무보고방(8254867551)

전부 dry-run/상수 확인 — 실발신 0. 실행: C:\\Python314\\python.exe tests/test_room_routing.py
"""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

AI_ROOM = -5498808140      # AI 진행현황방 (status/telegram_rooms.json "자동화현황방")
GM_ROOM = 8254867551       # 업무보고방 (GM_DM)


def _post_action_dry(clevel: str, status: str) -> str:
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    cmd = [sys.executable, str(ROOT / "wellperion-agents" / "scripts" / "clevel_post_action.py"),
           "--clevel", clevel, "--task-id", f"{clevel}-ROUTING-CHECK", "--status", status,
           "--summary", "방 경계 자체 점검", "--artifact-url", "tests/test_room_routing.py",
           "--terminal", "--dry-run"]
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", env=env)
    assert p.returncode == 0, f"{clevel}/{status} dry-run rc={p.returncode}\n{p.stderr}"
    return p.stdout


def main() -> None:
    # ① L18 배 보고 — 역할 3종(대문자 포함)·상태 2종 전부 AI 진행현황방으로만
    for clevel, status in (("CMO", "완료"), ("coo", "진행중"), ("CTO", "완료")):
        out = _post_action_dry(clevel, status)
        assert "(AI진행현황방)" in out, f"{clevel}/{status}: AI방 표기 없음\n{out}"
        assert "[DRY-RUN] would send:\n" not in out, f"{clevel}/{status}: 업무보고방 경로로 샘\n{out}"
        print(f"[OK] ① L18 {clevel}/{status} → AI 진행현황방")

    # ② 진행 1줄 헬퍼 목적지 해소
    from notify_gm_progress import notify
    r = notify("방 경계 자체 점검", dry_run=True)
    assert r["chat_id"] == AI_ROOM, f"notify_gm_progress chat_id={r['chat_id']}"
    print("[OK] ② notify_gm_progress → AI 진행현황방")

    # ③④ 업무보고방 고정 발신 2종 — 하루 정리·아침 보고
    import report_stream_3_mgmt, report_stream_1_impl
    assert int(report_stream_3_mgmt.TELEGRAM_CHAT_ID) == GM_ROOM
    assert int(report_stream_1_impl.GM_CHAT_ID) == GM_ROOM
    print("[OK] ③④ 하루 정리·아침 보고 → 업무보고방")

    # ⑤ 경보 분류 관문(alert_router) — tech_check=AI방 / gm_action=업무보고방
    import alert_router
    assert alert_router.route(alert_router.TECH_CHECK) == AI_ROOM
    assert alert_router.route(alert_router.GM_ACTION) == GM_ROOM
    print("[OK] ⑤ alert_router: tech_check → AI방 · gm_action → 업무보고방")

    # ⑥ 카톡 매출보고 실패 경보(2차 · 2026-08-04) — 가짜 발송기를 꽂아 목적지만 검증
    import kakao_auto_daily_report as K
    captured = {}
    K._tg_send = lambda token, chat_id, text, **kw: captured.update(chat_id=chat_id) or True
    K.send_owner_alert("방 경계 자체 점검 — 실발신 아님")
    assert captured.get("chat_id") == AI_ROOM, f"kakao 경보 chat_id={captured.get('chat_id')}"
    print("[OK] ⑥ 카톡 발송실패 경보 → AI 진행현황방")

    print("ALL OK — 방 경계 점검 통과 (실발신 0)")


if __name__ == "__main__":
    main()
