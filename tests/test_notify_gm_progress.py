# -*- coding: utf-8 -*-
"""
test_notify_gm_progress.py — GM 채널 진행 보고 헬퍼 pytest.
검증 대상: scripts/notify_gm_progress.py
네트워크 0(sender mock)·임시 로그 경로(tmp_path)로 실발송·영속 부작용 없이 검증.
"""
import os
import sys
from datetime import datetime
from unittest.mock import MagicMock

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_TESTS_DIR)
_SCRIPTS_DIR = os.path.join(_PROJECT_ROOT, "scripts")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

import notify_gm_progress as ngp  # noqa: E402

AUTOMATION_ROOM_CHAT_ID = -5498808140  # status/telegram_rooms.json "자동화현황방"


def _rooms_file(tmp_path, chat_id=AUTOMATION_ROOM_CHAT_ID):
    """resolve_room() 이 읽는 telegram_rooms.json 을 tmp_path 에 격리 생성한다
    (실제 status/telegram_rooms.json 에 의존하지 않게 네트워크·프로덕션 데이터 0)."""
    import json

    path = tmp_path / "telegram_rooms.json"
    path.write_text(json.dumps({ngp.ROOM_KEY: chat_id}, ensure_ascii=False), encoding="utf-8")
    return path


# ── 루틴 마커 판별 ───────────────────────────────────────────────────────────
def test_is_routine_detects_markers():
    assert ngp.is_routine("CTO-2026-07-13-ADHOC-786c82e3")
    assert ngp.is_routine("CMO-2026-07-13-auto-log-sync")
    assert ngp.is_routine("", "chore(erp): 시스템 현황 자동 발행")
    assert ngp.is_routine("MIRROR-sync-task")


def test_is_routine_false_for_real_completion():
    assert not ngp.is_routine("CTO-2026-07-13-TELEGRAM-PROGRESS-REPORT")
    assert not ngp.is_routine("CMO-2026-07-10-PUBLISH-FORTRESS", "feat: 발행 요새화 1단계")


# ── 게이트 OFF 시 미발송 ─────────────────────────────────────────────────────
def test_gate_off_skips_send(tmp_path, monkeypatch):
    monkeypatch.setenv("PROGRESS_REPORT_LIVE", "0")
    sender = MagicMock(return_value=True)
    out = ngp.notify("요약", sender=sender, log_path=tmp_path / "log.jsonl",
                     rooms_path=_rooms_file(tmp_path))
    sender.assert_not_called()
    # 게이트 OFF 는 방 해소보다 먼저 걸려 chat_id 는 None 이다.
    assert out == {"sent": False, "reason": "gate_off", "text": "✅ 요약", "chat_id": None}


def test_gate_on_by_default(tmp_path, monkeypatch):
    monkeypatch.delenv("PROGRESS_REPORT_LIVE", raising=False)
    sender = MagicMock(return_value=True)
    out = ngp.notify("기본 게이트 확인", sender=sender, log_path=tmp_path / "log.jsonl")
    sender.assert_called_once()
    assert out["sent"] is True


# ── dry-run: 네트워크 0 ──────────────────────────────────────────────────────
def test_dry_run_no_network(tmp_path):
    sender = MagicMock(return_value=True)
    out = ngp.notify("드라이런 확인", dry_run=True, sender=sender, log_path=tmp_path / "log.jsonl")
    sender.assert_not_called()
    assert out["reason"] == "dry_run"
    assert out["sent"] is False


# ── 정상 발송: 링크 포함 텍스트 조립 ─────────────────────────────────────────
def test_notify_sends_with_link(tmp_path):
    sender = MagicMock(return_value=True)
    log = tmp_path / "log.jsonl"
    out = ngp.notify("완료 보고", "http://example.com/evidence", sender=sender, log_path=log,
                     rooms_path=_rooms_file(tmp_path))
    # 목적지 = AI 진행현황방(구 자동화현황방), GM 개인방(ngp.GM_CHAT_ID) 아님.
    sender.assert_called_once_with(AUTOMATION_ROOM_CHAT_ID, "✅ 완료 보고 http://example.com/evidence")
    assert out["sent"] is True
    assert out["chat_id"] == AUTOMATION_ROOM_CHAT_ID
    assert log.exists()


# ── dedup: 동일 조립본문(text) 최근 재발송 금지 ──────────────────────────────
def test_dedup_blocks_recent_duplicate(tmp_path):
    sender = MagicMock(return_value=True)
    log = tmp_path / "log.jsonl"
    rooms = _rooms_file(tmp_path)
    now = datetime(2026, 7, 13, 9, 0, tzinfo=ngp.KST)

    out1 = ngp.notify("중복 방지 확인", sender=sender, log_path=log, rooms_path=rooms, now=now)
    assert out1["sent"] is True
    assert out1["chat_id"] == AUTOMATION_ROOM_CHAT_ID
    assert sender.call_count == 1

    later = datetime(2026, 7, 13, 9, 30, tzinfo=ngp.KST)  # 30분 후(윈도우 이내)
    out2 = ngp.notify("중복 방지 확인", sender=sender, log_path=log, rooms_path=rooms, now=later)
    assert out2["reason"] == "dedup"
    assert sender.call_count == 1  # 재발송 없음


# ── dedup: 같은 배라도 단계(step)가 다르면 서로 삼키지 않는다(2026-07-25 핵심) ──
def test_dedup_same_ship_different_step_both_sent(tmp_path):
    sender = MagicMock(return_value=True)
    log = tmp_path / "log.jsonl"
    rooms = _rooms_file(tmp_path)
    now = datetime(2026, 7, 25, 9, 0, tzinfo=ngp.KST)

    out1 = ngp.notify("작업 진행", ship="시토 81", step="1단계", state="doing",
                      sender=sender, log_path=log, rooms_path=rooms, now=now)
    later = datetime(2026, 7, 25, 9, 5, tzinfo=ngp.KST)  # dedup 윈도우 이내(60분)
    out2 = ngp.notify("작업 진행", ship="시토 81", step="2단계", state="doing",
                      sender=sender, log_path=log, rooms_path=rooms, now=later)

    assert out1["sent"] is True
    assert out2["sent"] is True  # 요약이 같아도 단계가 다르면 dedup 에 삼켜지지 않는다
    assert out1["text"] != out2["text"]
    assert sender.call_count == 2


def test_dedup_window_expires(tmp_path):
    sender = MagicMock(return_value=True)
    log = tmp_path / "log.jsonl"
    now = datetime(2026, 7, 13, 9, 0, tzinfo=ngp.KST)

    ngp.notify("윈도우 만료 확인", sender=sender, log_path=log, now=now)
    later = datetime(2026, 7, 13, 10, 30, tzinfo=ngp.KST)  # 90분 후(윈도우 밖)
    out2 = ngp.notify("윈도우 만료 확인", sender=sender, log_path=log, now=later)
    assert out2["sent"] is True
    assert sender.call_count == 2


# ── 하루 cap 초과 시 스킵 ────────────────────────────────────────────────────
def test_daily_cap_blocks_after_limit(tmp_path):
    sender = MagicMock(return_value=True)
    log = tmp_path / "log.jsonl"
    now = datetime(2026, 7, 13, 9, 0, tzinfo=ngp.KST)

    for i in range(ngp.DAILY_CAP):
        out = ngp.notify(f"건-{i}", sender=sender, log_path=log, now=now)
        assert out["sent"] is True

    out_over = ngp.notify("한도 초과 건", sender=sender, log_path=log, now=now)
    assert out_over["reason"] == "daily_cap"
    assert sender.call_count == ngp.DAILY_CAP


# ── 발송 실패(API 실패) 시 sent=False ───────────────────────────────────────
def test_send_failure_reflected(tmp_path):
    sender = MagicMock(return_value=False)
    out = ngp.notify("실패 케이스", sender=sender, log_path=tmp_path / "log.jsonl")
    assert out["sent"] is False
    assert out["reason"] == "send_failed"


# ── build_text: state 4종 아이콘 ─────────────────────────────────────────────
def test_build_text_state_icons():
    assert ngp.build_text("문구", state="start").startswith("🚀 ")
    assert ngp.build_text("문구", state="doing").startswith("⏳ ")
    assert ngp.build_text("문구", state="done").startswith("✅ ")
    assert ngp.build_text("문구", state="blocked").startswith("⚓ ")


# ── build_text: 배·단계 유무에 따른 형식 ─────────────────────────────────────
def test_build_text_ship_step_format():
    assert ngp.build_text("요약") == "✅ 요약"
    assert ngp.build_text("요약", ship="시토 81") == "✅ 시토 81 — 요약"
    assert ngp.build_text("요약", step="2단계") == "✅ 2단계 — 요약"
    assert ngp.build_text("요약", ship="시토 81", step="2단계") == "✅ 시토 81 · 2단계 — 요약"
    assert ngp.build_text("요약", "http://x", ship="시토 81", step="2단계") == \
        "✅ 시토 81 · 2단계 — 요약 http://x"


# ── resolve_room: 방 해소 실패 시 발송하지 않고 room_unresolved ─────────────
def test_resolve_room_missing_file_returns_none(tmp_path):
    missing = tmp_path / "no_such_rooms.json"
    assert ngp.resolve_room(rooms_path=missing) is None


def test_notify_room_unresolved_skips_send(tmp_path):
    sender = MagicMock(return_value=True)
    log = tmp_path / "log.jsonl"
    missing_rooms = tmp_path / "no_such_rooms.json"

    out = ngp.notify("요약", sender=sender, log_path=log, rooms_path=missing_rooms)

    sender.assert_not_called()
    assert out["sent"] is False
    assert out["reason"] == "room_unresolved"
    assert out["chat_id"] is None
    assert log.exists()  # 조용한 실패를 남기지 않으려 로그에는 기록된다


# ── CLI: 종료코드 ────────────────────────────────────────────────────────────
def test_cli_dry_run_returns_zero(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    rc = ngp.main(["CLI 테스트", "--dry-run"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "CLI 테스트" in out
