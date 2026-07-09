# -*- coding: utf-8 -*-
"""자동 검증-완결 핸들러 테스트 (AC-1~7 · 거짓완료 0 검증).

AC 매핑:
  AC-1 verify 스펙 없는 배 = 무시(완결 안 됨)            → test_ac1_*
  AC-2 log_contains PASS + gate ON → DONE·terminal·artifact → test_ac2_*
  AC-3 FAIL(match 없음) → status 불변(완결 안 됨)        → test_ac3_*
  AC-4 gate OFF → dryrun_would_close · status 불변       → test_ac4_*
  AC-5 이미 terminal 배 재실행 → skip(멱등)              → test_ac5_*
  AC-7 since 경계 — since 이전 라인 제외                 → test_ac7_*
  (파일 없음 = False)                                    → test_verify_missing_file
  AC-6 = 본 pytest 파일 전체 통과(순수함수·PASS/FAIL/게이트/멱등)
"""
import verify_complete as vc


# ═══ 픽스처 헬퍼 ═══
def _write_log(tmp_path, monkeypatch, rel, lines):
    """tmp_path 를 리포 루트로 치환하고 rel 경로에 로그 라인 기록."""
    monkeypatch.setattr(vc, "ROOT", tmp_path)
    f = tmp_path / rel
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return f


def _verify_ship(**over):
    """검증 대상 배(재개가능 태그 + verify 스펙)."""
    ship = {
        "task_id": "T-599",
        "ship_no": 599,
        "status": "IN_PROGRESS",
        "aide_flags": ["resumable"],
        "verify": {
            "type": "log_contains",
            "path": "telegram_bot/bot.log",
            "match": "chat_id=-5498808140",
            "evidence_label": "자동화현황방 도착",
        },
    }
    ship.update(over)
    return ship


# ═══ verify() 순수함수 (AC-6 일부) ═══
def test_verify_pass(tmp_path, monkeypatch):
    _write_log(tmp_path, monkeypatch, "telegram_bot/bot.log",
               ["2026-07-09 09:30:01 send chat_id=-5498808140 ok"])
    ok, ev = vc.verify({"type": "log_contains", "path": "telegram_bot/bot.log",
                        "match": "chat_id=-5498808140", "evidence_label": "도착"})
    assert ok is True
    assert "도착" in ev and "telegram_bot/bot.log" in ev


def test_verify_fail_no_match(tmp_path, monkeypatch):
    _write_log(tmp_path, monkeypatch, "telegram_bot/bot.log", ["관계없는 라인"])
    ok, ev = vc.verify({"type": "log_contains", "path": "telegram_bot/bot.log",
                        "match": "chat_id=-5498808140"})
    assert ok is False


def test_verify_unsupported_type(tmp_path, monkeypatch):
    monkeypatch.setattr(vc, "ROOT", tmp_path)
    ok, ev = vc.verify({"type": "http_ping", "path": "x", "match": "y"})
    assert ok is False and "미지원" in ev


def test_verify_missing_file(tmp_path, monkeypatch):
    """파일 없음 = False(예외 없이)."""
    monkeypatch.setattr(vc, "ROOT", tmp_path)
    ok, ev = vc.verify({"type": "log_contains", "path": "nope/missing.log",
                        "match": "x"})
    assert ok is False and "없음" in ev


def test_ac7_since_boundary_excludes_older(tmp_path, monkeypatch):
    """AC-7: since 이전 라인은 매칭 제외, 이후 라인만 PASS."""
    _write_log(tmp_path, monkeypatch, "telegram_bot/bot.log", [
        "2026-07-08 23:00:00 chat_id=-5498808140 old",
        "2026-07-09 09:30:00 chat_id=-5498808140 new",
    ])
    spec = {"type": "log_contains", "path": "telegram_bot/bot.log",
            "match": "chat_id=-5498808140", "since": "2026-07-09T00:00:00"}
    ok, ev = vc.verify(spec)
    assert ok is True and "new" in ev  # 이후 라인만 매칭


def test_ac7_since_all_older_fails(tmp_path, monkeypatch):
    """AC-7: match 는 있으나 전부 since 이전 → FAIL(완결 금지)."""
    _write_log(tmp_path, monkeypatch, "telegram_bot/bot.log",
               ["2026-07-08 23:00:00 chat_id=-5498808140 old"])
    spec = {"type": "log_contains", "path": "telegram_bot/bot.log",
            "match": "chat_id=-5498808140", "since": "2026-07-09T00:00:00"}
    ok, _ = vc.verify(spec)
    assert ok is False


# ═══ close_ship() 순수 뮤테이터 ═══
def test_close_ship_sets_fields():
    ship = _verify_ship()
    vc.close_ship(ship, "증거X", today="2026-07-09")
    assert ship["status"] == "DONE"
    assert ship["terminal"] is True
    assert ship["artifact"] == "증거X"
    assert ship["processed_at"] == "2026-07-09"
    assert ship["next"].startswith("🏁")


def test_close_ship_noop_when_terminal():
    ship = _verify_ship(terminal=True, status="DONE", artifact="원본")
    vc.close_ship(ship, "새증거", today="2026-07-09")
    assert ship["artifact"] == "원본"  # 이미 terminal → no-op(멱등)


# ═══ handle() 통합 (AC-1~5) ═══
def test_ac1_ship_without_verify_ignored(tmp_path, monkeypatch):
    """AC-1: verify 스펙 없는 배 = 무시(완결 안 됨·diff 0)."""
    _write_log(tmp_path, monkeypatch, "telegram_bot/bot.log",
               ["chat_id=-5498808140"])
    ship = {"task_id": "T-1", "status": "IN_PROGRESS", "aide_flags": ["resumable"]}
    res = vc.handle([ship], gate_on=True, today="2026-07-09")
    assert res["counts"]["ignored"] == 1
    assert res["counts"]["targets"] == 0
    assert ship.get("status") == "IN_PROGRESS"  # 불변


def test_ac2_pass_gate_on_closes(tmp_path, monkeypatch):
    """AC-2: PASS + gate ON → DONE·terminal·artifact=증거."""
    _write_log(tmp_path, monkeypatch, "telegram_bot/bot.log",
               ["2026-07-09 09:30:01 chat_id=-5498808140 ok"])
    ship = _verify_ship()
    res = vc.handle([ship], gate_on=True, today="2026-07-09")
    assert res["counts"]["closed"] == 1
    assert ship["status"] == "DONE"
    assert ship["terminal"] is True
    assert "자동화현황방 도착" in ship["artifact"]
    assert ship["processed_at"] == "2026-07-09"


def test_ac3_fail_does_not_close(tmp_path, monkeypatch):
    """AC-3: match 없음(FAIL) → 배 완결 안 됨(status 불변)."""
    _write_log(tmp_path, monkeypatch, "telegram_bot/bot.log", ["무관 라인"])
    ship = _verify_ship()
    res = vc.handle([ship], gate_on=True, today="2026-07-09")
    assert res["counts"]["surface"] == 1
    assert res["counts"]["closed"] == 0
    assert ship["status"] == "IN_PROGRESS"  # 불변
    assert "terminal" not in ship


def test_ac4_gate_off_dryrun_no_mutation(tmp_path, monkeypatch):
    """AC-4: PASS 여도 gate OFF → dryrun_would_close · status 불변(라이브 완결 0)."""
    _write_log(tmp_path, monkeypatch, "telegram_bot/bot.log",
               ["2026-07-09 09:30:01 chat_id=-5498808140 ok"])
    ship = _verify_ship()
    res = vc.handle([ship], gate_on=False, today="2026-07-09")
    assert res["counts"]["dryrun_would_close"] == 1
    assert res["counts"]["closed"] == 0
    assert ship["status"] == "IN_PROGRESS"  # 불변
    assert "terminal" not in ship


def test_ac5_already_terminal_skipped(tmp_path, monkeypatch):
    """AC-5: 이미 terminal 배 재실행 → skip(중복 완결 0·멱등)."""
    _write_log(tmp_path, monkeypatch, "telegram_bot/bot.log",
               ["2026-07-09 09:30:01 chat_id=-5498808140 ok"])
    ship = _verify_ship(terminal=True, status="DONE", artifact="원본증거")
    res = vc.handle([ship], gate_on=True, today="2026-07-09")
    assert res["counts"]["skipped_terminal"] == 1
    assert res["counts"]["closed"] == 0
    assert ship["artifact"] == "원본증거"  # 불변


def test_handle_reversibility_route_target(tmp_path, monkeypatch):
    """aide_flags 없이도 route()=='auto'(revert_ok·¬external·¬data_loss)면 대상."""
    _write_log(tmp_path, monkeypatch, "telegram_bot/bot.log",
               ["2026-07-09 09:30:01 chat_id=-5498808140 ok"])
    ship = _verify_ship(aide_flags=None, revert_ok=True, external=False, data_loss=False)
    res = vc.handle([ship], gate_on=True, today="2026-07-09")
    assert res["counts"]["closed"] == 1
