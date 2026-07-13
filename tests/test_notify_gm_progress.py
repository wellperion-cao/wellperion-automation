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
    out = ngp.notify("요약", sender=sender, log_path=tmp_path / "log.jsonl")
    sender.assert_not_called()
    assert out == {"sent": False, "reason": "gate_off", "text": "✅ [완료] 요약"}


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
    out = ngp.notify("완료 보고", "http://example.com/evidence", sender=sender, log_path=log)
    sender.assert_called_once_with(ngp.GM_CHAT_ID, "✅ [완료] 완료 보고 http://example.com/evidence")
    assert out["sent"] is True
    assert log.exists()


# ── dedup: 동일 summary 최근 재발송 금지 ─────────────────────────────────────
def test_dedup_blocks_recent_duplicate(tmp_path):
    sender = MagicMock(return_value=True)
    log = tmp_path / "log.jsonl"
    now = datetime(2026, 7, 13, 9, 0, tzinfo=ngp.KST)

    out1 = ngp.notify("중복 방지 확인", sender=sender, log_path=log, now=now)
    assert out1["sent"] is True
    assert sender.call_count == 1

    later = datetime(2026, 7, 13, 9, 30, tzinfo=ngp.KST)  # 30분 후(윈도우 이내)
    out2 = ngp.notify("중복 방지 확인", sender=sender, log_path=log, now=later)
    assert out2["reason"] == "dedup"
    assert sender.call_count == 1  # 재발송 없음


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


# ── CLI: 종료코드 ────────────────────────────────────────────────────────────
def test_cli_dry_run_returns_zero(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    rc = ngp.main(["CLI 테스트", "--dry-run"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "CLI 테스트" in out
