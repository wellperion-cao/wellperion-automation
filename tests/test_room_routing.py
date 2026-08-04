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
sys.path.insert(0, str(ROOT / "ssot"))

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

    # ⑦ GM 손이 필요한 요청(3차 · 2026-08-04) — 러너 모호 배 핑 = gm_action → 업무보고방
    import welly_auto_runner
    assert welly_auto_runner._gm_action_notifier().chat_id == GM_ROOM
    print("[OK] ⑦ 러너 모호 배 핑(GM 손 요청) → 업무보고방")

    # ⑧ 텔레그램 주 발신관문(tg_outbound_log.send) — HTTP 200 이어도 본문 ok:false 면
    #    실패로 잡는지(2026-08-04 시토 · 카톡과 같은 부류의 조용한 실패 점검, 배347/348 대칭)
    import io
    from unittest.mock import patch
    import tg_outbound_log as T

    class _FakeResp(io.BytesIO):
        status = 200
        def __enter__(self): return self
        def __exit__(self, *a): return False

    with patch("urllib.request.urlopen", return_value=_FakeResp(b'{"ok": false, "description": "chat not found"}')):
        result = T.send("fake-token", GM_ROOM, "방 경계 자체 점검", source="test_room_routing", max_attempts=1)
    assert result is False, f"HTTP 200 + ok:false 인데 성공(True)으로 판정됨 — 조용한 실패: {result}"
    print("[OK] ⑧ tg_outbound_log.send: HTTP 200 + ok:false → 실패로 정확히 판정")

    # ⑨ post_commit_push 경보 억제 — 동시 실행 두 프로세스가 같은 사유를 동시에 보내던
    #    레이스(2026-08-04 실사고: 12:02:53·12:02:54 1초 간격 중복) 재현 점검
    import tempfile
    import threading
    import post_commit_push as P
    tmp = tempfile.mkdtemp()
    os.makedirs(os.path.join(tmp, "tmp"), exist_ok=True)
    race_results = []
    barrier = threading.Barrier(5)

    def _racer():
        barrier.wait()
        race_results.append(P._alert_should_send(tmp, "방 경계 자체 점검 — 동시성"))

    threads = [threading.Thread(target=_racer) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sum(race_results) == 1, f"동시 5회 호출인데 True={sum(race_results)}번 — 락 레이스 재발: {race_results}"
    print("[OK] ⑨ post_commit_push._alert_should_send: 동시 5회 중 1번만 발신(락 정상)")

    # ⑩ incident_regression_monitor 경보 내용-지문 억제(2026-08-04 웰리 판정 · 시토 구현)
    #    시간 쿨다운이 아니라 내용으로 가른다: 동일 반복=억제 / 내용변경=즉시재발신 / 해소후재발=재발신
    import pathlib
    import incident_regression_monitor as M
    tmp_baseline = pathlib.Path(tempfile.mkdtemp()) / "incident_baseline.json"
    _orig = dict(baseline=M.BASELINE_FILE, alert=M._alert, div=M._divergence_map,
                 missing=M._missing_assets, unguarded=M._unguarded, leaked=M._leaked_today)
    try:
        M.BASELINE_FILE = tmp_baseline
        alerts = []
        M._alert = lambda text: alerts.append(text)
        M._divergence_map = lambda: {}
        M._leaked_today = lambda: []
        M._unguarded = lambda: []

        M._missing_assets = lambda: ["자산A (x)"]
        assert M.run() == 1 and len(alerts) == 1, "①최초 회귀는 발신"
        assert M.run() == 1 and len(alerts) == 1, "②동일 내용 반복은 억제(추가발신 없음)"
        M._missing_assets = lambda: ["자산B (y)"]
        assert M.run() == 1 and len(alerts) == 2, "③내용이 바뀌면 즉시 재발신"
        M._missing_assets = lambda: []
        assert M.run() == 0 and len(alerts) == 2, "④해소되면 무발신(정상은 조용히)"
        M._missing_assets = lambda: ["자산B (y)"]
        assert M.run() == 1 and len(alerts) == 3, "⑤해소 후 같은 내용 재발 시 다시 발신"
    finally:
        M.BASELINE_FILE, M._alert = _orig["baseline"], _orig["alert"]
        M._divergence_map, M._missing_assets = _orig["div"], _orig["missing"]
        M._unguarded, M._leaked_today = _orig["unguarded"], _orig["leaked"]
    print("[OK] ⑩ incident_regression_monitor: 동일반복 억제·내용변경 즉시재발신·해소후재발 재발신 확인")

    # ⑪ erp_status_publisher 연동다리 경보도 같은 내용-지문 규칙(2026-08-04 웰리 판정)
    #    08-03 21:18·22:17 1시간 간격 재경보를 실측 확인(git log status/erp_status.json —
    #    20:47 정상→21:18 이상→22:17 이상 재검출→22:47 정상) = 플래핑. 시간쿨다운이 아니라
    #    내용지문으로 흡수: 같은사유 지속=억제 / 복구=무발신 / 복구후 같은사유 재발=재발신 / 사유변경=재발신
    import erp_status_publisher as E
    _bl = E.BRIDGE_LAST
    tmp_bridge = pathlib.Path(tempfile.mkdtemp()) / "_bridge_last.json"
    bridge_alerts = []
    _orig_send = E._send_telegram
    try:
        E.BRIDGE_LAST = tmp_bridge
        E._send_telegram = lambda text, kind="tech_check": bridge_alerts.append(text) or True
        broken = [{"name": "시트 GAS(todo_list)", "state": "이상", "detail": "TimeoutError"}]
        ok = [{"name": "시트 GAS(todo_list)", "state": "정상", "detail": "HTTP 200"}]
        diff = [{"name": "시트 GAS(todo_list)", "state": "이상", "detail": "ConnectionError"}]

        E.alert_newly_broken(broken)
        assert len(bridge_alerts) == 1, "①최초 깨짐은 발신"
        E.alert_newly_broken(broken)
        assert len(bridge_alerts) == 1, "②같은 사유 지속은 억제"
        E.alert_newly_broken(ok)
        assert len(bridge_alerts) == 1, "③복구는 무발신"
        E.alert_newly_broken(broken)
        assert len(bridge_alerts) == 2, "④복구 후 같은 사유 재발(플래핑)은 다시 발신"
        E.alert_newly_broken(diff)
        assert len(bridge_alerts) == 3, "⑤사유가 바뀌면 즉시 재발신"
    finally:
        E.BRIDGE_LAST = _bl
        E._send_telegram = _orig_send
    print("[OK] ⑪ erp_status_publisher: 연동다리 경보 내용-지문 억제/재발신 5단계 확인")

    print("ALL OK — 방 경계 점검 통과 (실발신 0)")


if __name__ == "__main__":
    main()
