# -*- coding: utf-8 -*-
"""self_health_watchdog §5(시트 계약 무결성 편입) + 게이트 회귀 테스트 (2026-07-22 배9420 #5).

핵심 계약:
  - §5 는 cpo_sheet_contract 상태파일을 읽기만 한다(재점검·네트워크 없음).
  - accepted=true(시포 승인) 위반은 재노출하지 않는다.
  - network_fail_streak >= 임계(3)만 연속실패로 노출.
  - LIVE 게이트 OFF면 이상이 있어도 실발신 0(전사 표준 확장 후에도 회귀 없음).
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import self_health_watchdog as W  # noqa: E402


# ── §5 시트 계약 섹션 ────────────────────────────────────────────────────────
def _patch_state(monkeypatch, state):
    monkeypatch.setattr(W._sheet, "load_state", lambda: state)


def test_sheet_contract_surfaces_unresolved_only(monkeypatch):
    _patch_state(monkeypatch, {
        "fingerprints": {
            "a": {"detail": "허용값 밖 값 ['신규']", "accepted": False},
            "b": {"detail": "최근 30행 중 공란 14건(47%)", "accepted": False},
            "c": {"detail": "이건 승인됨", "accepted": True},  # 재노출 금지
        },
        "network_fail_streak": {"member_hold": 1},  # 임계 미만 → 무시
    })
    lines = W.build_section_sheet_contract()
    assert lines is not None
    head = lines[0]
    assert "2건" in head  # accepted 1건 제외 → 2건
    body = "\n".join(lines)
    assert "이건 승인됨" not in body       # accepted 위반은 숨김
    assert "허용값 밖 값" in body
    assert "연속실패" not in body           # streak 1 < 3 → 섹션 없음


def test_sheet_contract_network_streak_surfaces_at_threshold(monkeypatch):
    thr = W._sheet._NETWORK_FAIL_ALERT_STREAK
    _patch_state(monkeypatch, {
        "fingerprints": {},
        "network_fail_streak": {"member_hold": thr, "inquiry_2026": thr - 1},
    })
    lines = W.build_section_sheet_contract()
    assert lines is not None
    body = "\n".join(lines)
    assert "연속실패 1건" in body           # thr 도달분만
    assert "member_hold" in body
    assert "inquiry_2026" not in body        # thr 미달분 제외


def test_sheet_contract_all_clean_returns_none(monkeypatch):
    _patch_state(monkeypatch, {
        "fingerprints": {"x": {"detail": "승인됨", "accepted": True}},
        "network_fail_streak": {"member_hold": 0},
    })
    assert W.build_section_sheet_contract() is None


def test_sheet_contract_failsoft_on_bad_state(monkeypatch):
    def _boom():
        raise RuntimeError("state read fail")
    monkeypatch.setattr(W._sheet, "load_state", _boom)
    assert W.build_section_sheet_contract() is None   # 예외 → None(무발신)


# ── build_digest 통합: §5 가 섹션 dict 에 들어간다 ──────────────────────────────
def test_digest_includes_sheet_contract_section(monkeypatch):
    # 다른 섹션은 정상(None)으로 눌러 §5 만 이상으로 만든다
    monkeypatch.setattr(W, "build_section_silence", lambda now=None: None)
    monkeypatch.setattr(W, "build_section_gas_version", lambda: None)
    monkeypatch.setattr(W, "build_section_erp_status", lambda: None)
    monkeypatch.setattr(W, "build_section_page_hygiene", lambda now=None: None)
    _patch_state(monkeypatch, {
        "fingerprints": {"a": {"detail": "위반X", "accepted": False}},
        "network_fail_streak": {},
    })
    text, sections = W.build_digest()
    assert "sheet_contract" in sections
    assert sections["sheet_contract"] is not None
    assert text is not None and "🔐 시트 계약" in text


# ── 게이트 회귀: LIVE OFF 면 이상이 있어도 실발신 0 ──────────────────────────────
def test_live_gate_off_blocks_send_even_with_issues(monkeypatch, tmp_path):
    # §5 이상 상태를 만들고, 나머지는 None
    monkeypatch.setattr(W, "build_section_silence", lambda now=None: None)
    monkeypatch.setattr(W, "build_section_gas_version", lambda: None)
    monkeypatch.setattr(W, "build_section_erp_status", lambda: None)
    monkeypatch.setattr(W, "build_section_page_hygiene", lambda now=None: None)
    _patch_state(monkeypatch, {
        "fingerprints": {"a": {"detail": "위반X", "accepted": False}},
        "network_fail_streak": {},
    })
    monkeypatch.delenv(W.LIVE_ENV_VAR, raising=False)  # 게이트 OFF

    sent = []
    log = tmp_path / "wd_log.jsonl"
    out = W.run_watchdog(dry_run=False, log_path=str(log),
                         sender=lambda cid, txt: sent.append((cid, txt)) or True)
    assert out["action"] == "skip"
    assert out["reason"].startswith(W.LIVE_ENV_VAR)
    assert sent == []                     # 실발신 0 — 회귀 없음


def test_no_issue_is_noop_no_send(monkeypatch, tmp_path):
    for name in ("build_section_silence", "build_section_page_hygiene"):
        monkeypatch.setattr(W, name, lambda now=None: None)
    monkeypatch.setattr(W, "build_section_gas_version", lambda: None)
    monkeypatch.setattr(W, "build_section_erp_status", lambda: None)
    monkeypatch.setattr(W, "build_section_sheet_contract", lambda: None)
    # §6/§7/§8 도 전부 눌러야 "전 섹션 정상" 시나리오가 결정론적이다(실 저장소/네트워크
    # 상태에 좌우되지 않게 — 2026-07-22 배9420 확장, §7·§8 추가로 patch 필요해짐).
    monkeypatch.setattr(W, "build_section_decision_consistency", lambda now=None: None)
    monkeypatch.setattr(W, "build_section_telegram", lambda: None)
    monkeypatch.setattr(W, "build_section_bridges", lambda: None)
    monkeypatch.setenv(W.LIVE_ENV_VAR, "1")   # 게이트 ON이어도 이상 0이면 무발신
    sent = []
    log = tmp_path / "wd_log.jsonl"
    out = W.run_watchdog(dry_run=False, log_path=str(log),
                         sender=lambda cid, txt: sent.append(1) or True)
    assert out["action"] == "no_op"
    assert sent == []


# ── §7 텔레그램 채널 (telegram_health_check.py 함수 재사용 · 2026-07-22 배9420 확장) ──
def _patch_tg_all_clean(monkeypatch):
    monkeypatch.setattr(W._tghealth, "_load_env", lambda path: {"TELEGRAM_BOT_TOKEN": "t"})
    monkeypatch.setattr(W._tghealth, "_get_bot_info", lambda token: (True, 111, "@bot"))
    monkeypatch.setattr(W._tghealth, "_default_rooms", lambda env: [("점검관리방", -1)])
    monkeypatch.setattr(W._tghealth, "_check_rooms", lambda token, bot_id, rooms: [])
    monkeypatch.setattr(W._tghealth, "_check_log_failures", lambda: [])
    monkeypatch.setattr(W._tghealth, "_check_gas_diag", lambda: [])
    monkeypatch.setattr(W._tghealth, "_check_heartbeat", lambda: [])


def test_telegram_section_none_when_all_clean(monkeypatch):
    _patch_tg_all_clean(monkeypatch)
    assert W.build_section_telegram() is None


def test_telegram_section_surfaces_heartbeat_death(monkeypatch):
    """봇 폴링 하트비트 죽음 — telegram_health_check.py 자체 즉시경보와 별개로
    이 일일 요약 섹션에도 뜨는지(무회귀: 탐지 자체는 telegram_health_check.py 몫,
    여기선 그 결과를 그대로 실어 보이는지만 확인)."""
    _patch_tg_all_clean(monkeypatch)
    monkeypatch.setattr(
        W._tghealth, "_check_heartbeat",
        lambda: ["🔴 봇 폴링 의심 정지 — 하트비트 45분째 미갱신 (bot.py 재기동 필요)"],
    )
    lines = W.build_section_telegram()
    assert lines is not None
    body = "\n".join(lines)
    assert "봇 폴링 의심 정지" in body


def test_telegram_section_surfaces_bot_dead(monkeypatch):
    _patch_tg_all_clean(monkeypatch)
    monkeypatch.setattr(W._tghealth, "_get_bot_info", lambda token: (False, None, "status=0"))
    lines = W.build_section_telegram()
    assert lines is not None
    assert "봇 생존 확인 실패" in "\n".join(lines)


def test_telegram_section_failsoft_on_exception(monkeypatch):
    def _boom(path):
        raise RuntimeError("env read fail")
    monkeypatch.setattr(W._tghealth, "_load_env", _boom)
    lines = W.build_section_telegram()
    assert lines is not None   # 예외여도 크래시 없이 안내 라인(무발신 아님, 가시화)
    assert "점검 실패" in lines[0]


# ── §8 연동 다리 (integration_health.check_bridges() 재사용 · 2026-07-22 배9420 확장) ──
def test_bridges_section_none_when_all_ok(monkeypatch):
    monkeypatch.setattr(W._bridges, "check_bridges", lambda: [("A", True, "ok"), ("B", True, "ok")])
    assert W.build_section_bridges() is None


def test_bridges_section_surfaces_failed_bridge(monkeypatch):
    monkeypatch.setattr(
        W._bridges, "check_bridges",
        lambda: [("G1 큐 라이브", True, "ok"), ("큐 미러 동기", False, "미러 드리프트")],
    )
    lines = W.build_section_bridges()
    assert lines is not None
    body = "\n".join(lines)
    assert "1/2건" in lines[0]
    assert "큐 미러 동기" in body
    assert "미러 드리프트" in body
    assert "G1 큐 라이브" not in body   # 정상 다리는 노출 안 함


def test_bridges_section_failsoft_on_exception(monkeypatch):
    def _boom():
        raise RuntimeError("network down")
    monkeypatch.setattr(W._bridges, "check_bridges", _boom)
    lines = W.build_section_bridges()
    assert lines is not None
    assert "점검 실패" in lines[0]
