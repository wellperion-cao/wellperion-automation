# -*- coding: utf-8 -*-
"""hangro_review 계약 테스트 — 외부(claude·telegram·queue) 전부 주입 격리."""
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "aide_detectors"))

import hangro_review as hr


def test_module_imports():
    assert hasattr(hr, "audit_ships")


def test_ledger_key_changes_with_context():
    a = {"ship_no": 42, "title": "T", "note": "n1", "next": "", "status": "DONE"}
    b = {**a, "note": "n2 실질변경"}
    assert hr.ledger_key(a).startswith("42|")
    assert hr.ledger_key(a) != hr.ledger_key(b)   # 문맥 변하면 key 변함


def test_already_decided_roundtrip(tmp_path):
    p = tmp_path / "dec.jsonl"
    ship = {"ship_no": 42, "title": "T", "note": "n", "next": "", "status": "DONE"}
    key = hr.record_decision(p, ship, "approved")
    decisions = hr.load_decisions(p)
    assert hr.already_decided(key, decisions) is True
    # 문맥이 바뀐 같은 배 = 새 key → 재핑 허용(미결정)
    ship2 = {**ship, "note": "바뀜"}
    assert hr.already_decided(hr.ledger_key(ship2), decisions) is False


def test_audit_flags_stale_via_stall_watch():
    q = [{"ship_no": 7, "task_id": "CTO-x", "clevel": "cto", "title": "정체배",
          "status": "IN_PROGRESS", "priority": "🛳️크루즈",
          "enqueued_at": "2026-07-01", "note": "", "next": ""}]
    findings = hr.audit_ships(q, drift_ids=set(), today=date(2026, 7, 21))
    stale = [f for f in findings if f["verdict"] == "stale"]
    assert len(stale) == 1 and stale[0]["ship_no"] == 7
    assert "임계" in stale[0]["evidence"]


def test_audit_is_read_only(tmp_path):
    qf = tmp_path / "_queue.json"
    raw = [{"ship_no": 7, "task_id": "CTO-x", "clevel": "cto", "title": "t",
            "status": "IN_PROGRESS", "priority": "🛳️크루즈", "enqueued_at": "2026-07-01"}]
    import json as _j
    qf.write_text(_j.dumps(raw, ensure_ascii=False), encoding="utf-8")
    before = qf.read_bytes()
    hr.audit_ships(raw, drift_ids=set(), today=date(2026, 7, 21))
    assert qf.read_bytes() == before   # 검수는 상태 불변(read-only)


def test_audit_done_look_not_done():
    q = [{"ship_no": 1, "task_id": "A", "clevel": "cmo", "title": "배",
          "status": "IN_PROGRESS", "priority": "⛵돛단배",
          "note": "작업 완료했고 입항 처리함", "next": "", "enqueued_at": "2026-07-21"}]
    f = hr.audit_ships(q, drift_ids=set(), today=date(2026, 7, 21))
    assert f[0]["verdict"] == "done_look_not_done"


def test_audit_drift_uses_injected_ids():
    q = [{"ship_no": 2, "task_id": "B", "clevel": "coo", "title": "완료배",
          "status": "DONE", "priority": "⛵돛단배", "note": "", "next": "",
          "enqueued_at": "2026-07-20"}]
    f = hr.audit_ships(q, drift_ids={"B"}, today=date(2026, 7, 21))
    assert f[0]["verdict"] == "drift"


def test_audit_no_destination():
    q = [{"ship_no": 3, "task_id": "C", "clevel": "cpo", "title": "활성무종착",
          "status": "PENDING", "priority": "⛵돛단배", "note": "", "next": "",
          "enqueued_at": "2026-07-21"}]
    f = hr.audit_ships(q, drift_ids=set(), today=date(2026, 7, 21))
    assert f[0]["verdict"] == "no_destination"


def _fake_claude_ok(prompt, *, label=""):
    import json as _j
    return _j.dumps({"next_step": "예약 폼 A/B", "final_destination": "CMO 전환 북극성",
                     "path_map": "🌟→📍→👉", "confidence": 0.82}), "claude-opus-4-8"


def _fake_claude_fail(prompt, *, label=""):
    return None, None


def test_generate_destination_llm_ok():
    ship = {"ship_no": 5, "title": "문의 전환", "clevel": "cmo",
            "note": "", "next": "", "verdict": "no_destination"}
    card = hr.generate_destination(ship, run_claude=_fake_claude_ok)
    assert card["next_step"] == "예약 폼 A/B"
    assert card["confidence"] == 0.82 and card["low_confidence"] is False


def test_generate_destination_fallback_is_low_confidence():
    ship = {"ship_no": 5, "title": "문의 전환", "clevel": "cmo",
            "note": "", "next": "", "verdict": "drift"}
    card = hr.generate_destination(ship, run_claude=_fake_claude_fail)
    assert card["low_confidence"] is True          # 규칙 폴백 = 저확신 제안
    assert card["next_step"]                        # 빈 종착지 금지(무언가는 제안)
    assert card["confidence"] < hr.CONFIDENCE_THRESHOLD


def _fake_garbage(prompt, *, label=""):
    """LLM이 JSON이 아닌 텍스트 반환 시뮬레이션."""
    return "이것은 JSON이 아님", "model"


def test_generate_destination_malformed_json_falls_back():
    """malformed-JSON 폴백 회귀보호 — LLM이 JSON 아닌 텍스트 반환 시 저확신 규칙 폴백."""
    ship = {"ship_no": 1, "title": "테스트배", "clevel": "ceo",
            "note": "", "next": "", "verdict": "no_destination"}
    d = hr.generate_destination(ship, run_claude=_fake_garbage)
    assert d["low_confidence"] is True
    assert d["next_step"]  # 비어있지 않음(지어내기 아님·저확신 라벨)


def test_ping_gm_spacing_and_dedup():
    """GM 카드 핑: 간격 제어 + dedup 스킵"""
    sent, slept = [], []
    ships = {10: {"ship_no": 10, "title": "A", "note": "n", "next": "", "status": "DONE"},
             11: {"ship_no": 11, "title": "B", "note": "n", "next": "", "status": "DONE"}}
    # 10번은 이미 결정됨(dedup 대상)
    decisions = {hr.ledger_key(ships[10]): {"decision": "approved"}}
    cards = [{"ship_no": 10, "next_step": "x"}, {"ship_no": 11, "next_step": "y"}]
    out = hr.ping_gm(cards, decisions=decisions, ship_by_no=ships,
                     send_fn=lambda c: sent.append(c["ship_no"]),
                     sleep_fn=lambda s: slept.append(s))
    assert sent == [11]                 # 결정된 10 제외, 11만 발송
    assert out == [cards[1]]
    assert slept == []                  # 발송 1건(첫 발송) = 간격 0회


def test_ping_gm_multiple_cards_spacing():
    """(a) 다건 발송: dedup 안 되는 카드 2건 → 사이 간격만(마지막 뒤 X)"""
    sent, slept = [], []
    ships = {20: {"ship_no": 20, "title": "배A", "note": "n", "next": "", "status": "DONE"},
             21: {"ship_no": 21, "title": "배B", "note": "n", "next": "", "status": "DONE"}}
    cards = [{"ship_no": 20, "next_step": "발송A"}, {"ship_no": 21, "next_step": "발송B"}]
    out = hr.ping_gm(cards, decisions={}, ship_by_no=ships,
                     send_fn=lambda c: sent.append(c),
                     sleep_fn=lambda s: slept.append(s))
    assert len(sent) == 2 and sent[0]["ship_no"] == 20 and sent[1]["ship_no"] == 21
    assert len(out) == 2
    assert slept == [hr.MIN_PING_GAP_SEC]   # 사이 간격만 1회(마지막 뒤 X)


def test_ping_gm_low_confidence_label():
    """(b) 저확신 라벨: low_confidence=True 카드 → next_step에 [저확신] 추가"""
    sent = []
    ships = {30: {"ship_no": 30, "title": "배", "note": "", "next": "", "status": "DONE"}}
    cards = [{"ship_no": 30, "next_step": "다음 한 수", "low_confidence": True}]
    out = hr.ping_gm(cards, decisions={}, ship_by_no=ships,
                     send_fn=lambda c: sent.append(c),
                     sleep_fn=lambda s: None)
    assert sent[0]["next_step"] == "[저확신] 다음 한 수"


def test_ping_gm_low_confidence_no_double_label():
    """(c) 이중라벨 방지: next_step이 이미 [저확신]로 시작 → 중복 추가 안 함"""
    sent = []
    ships = {40: {"ship_no": 40, "title": "배", "note": "", "next": "", "status": "DONE"}}
    cards = [{"ship_no": 40, "next_step": "[저확신] 기존 라벨", "low_confidence": True}]
    out = hr.ping_gm(cards, decisions={}, ship_by_no=ships,
                     send_fn=lambda c: sent.append(c),
                     sleep_fn=lambda s: None)
    assert sent[0]["next_step"] == "[저확신] 기존 라벨"  # 중복 [저확신] 없음


class _FakeRun:
    def __init__(self): self.argv = None
    def __call__(self, cmd, **kw):
        self.argv = cmd
        class R: returncode = 0; stdout = ""; stderr = ""
        return R()


def test_apply_gate_off_is_dryrun(tmp_path, monkeypatch):
    monkeypatch.delenv(hr.APPLY_ENV, raising=False)   # 게이트 OFF(기본)
    fr = _FakeRun()
    card = {"ship_no": 9, "task_id": "CTO-z", "clevel": "cto",
            "title": "t", "note": "", "next": "", "status": "DONE",
            "next_step": "다음 한 수"}
    label, changed = hr.apply_on_approval(card, gate_on=False, runner=fr,
                                          decisions_path=tmp_path / "d.jsonl")
    assert "--dry-run" in fr.argv        # OFF = 라이브 델타 0(반드시 dry-run)
    assert changed is False


def test_apply_gate_on_pipes_next(tmp_path):
    fr = _FakeRun()
    card = {"ship_no": 9, "task_id": "CTO-z", "clevel": "cto",
            "title": "t", "note": "", "next": "", "status": "DONE",
            "verdict": "drift", "next_step": "다음 한 수 실행"}
    label, changed = hr.apply_on_approval(card, gate_on=True, runner=fr,
                                          decisions_path=tmp_path / "d.jsonl")
    assert "--dry-run" not in fr.argv
    assert "--next" in fr.argv and "다음 한 수 실행" in fr.argv
    assert changed is True
    assert (tmp_path / "d.jsonl").exists()   # 결정 원장 기록


def _flag_value(argv, flag):
    """argv 리스트에서 --flag 다음 인자값 반환(없으면 None)."""
    if flag not in argv:
        return None
    idx = argv.index(flag)
    return argv[idx + 1] if idx + 1 < len(argv) else None


def test_apply_gate_on_cmd_satisfies_clevel_post_action_contract(tmp_path):
    """clevel_post_action.py 는 --status 완료(→DONE) 시 --artifact-url 을 필수로
    요구(없으면 exit 2). apply_on_approval 이 실제로 넘기는 cmd 를 화이트박스로
    검증해 계약 위반(빈 값 fake runner로는 못 잡던 것)을 잡는다."""
    fr = _FakeRun()
    card = {"ship_no": 9, "task_id": "CTO-z", "clevel": "cto",
            "title": "t", "note": "", "next": "", "status": "DONE",
            "verdict": "drift", "next_step": "다음 한 수 실행"}
    hr.apply_on_approval(card, gate_on=True, runner=fr,
                          decisions_path=tmp_path / "d.jsonl")
    argv = fr.argv
    for flag in ("--clevel", "--task-id", "--status", "--next", "--artifact-url"):
        assert flag in argv, f"{flag} 누락 — clevel_post_action.py 계약 위반"
    assert _flag_value(argv, "--clevel") == "CTO"
    assert _flag_value(argv, "--task-id") == "CTO-z"
    assert _flag_value(argv, "--status") == "완료"
    artifact_url = _flag_value(argv, "--artifact-url")
    assert artifact_url and artifact_url.strip(), "--artifact-url 이 비어있으면 DONE 게이트에서 exit 2"


def test_apply_gate_on_uses_card_artifact_url_when_present(tmp_path):
    fr = _FakeRun()
    card = {"ship_no": 9, "task_id": "CTO-z", "clevel": "cto",
            "title": "t", "note": "", "next": "", "status": "DONE",
            "verdict": "drift", "next_step": "다음 한 수", "artifact_url": "https://example.com/evidence"}
    hr.apply_on_approval(card, gate_on=True, runner=fr,
                          decisions_path=tmp_path / "d.jsonl")
    assert _flag_value(fr.argv, "--artifact-url") == "https://example.com/evidence"


def test_apply_verdict_no_destination_does_not_force_done(tmp_path):
    """활성 배 오완료 방지 — verdict가 COMPLETION_VERDICTS 밖(no_destination 등)이면
    GM 승인이어도 clevel_post_action.py 에 --status 완료(DONE 강제)를 넘기지 않는다."""
    fr = _FakeRun()
    card = {"ship_no": 9, "task_id": "CTO-z", "clevel": "cto",
            "title": "t", "note": "", "next": "", "status": "PENDING",
            "verdict": "no_destination", "next_step": "북극성 종착지 부여"}
    hr.apply_on_approval(card, gate_on=True, runner=fr,
                          decisions_path=tmp_path / "d.jsonl")
    assert _flag_value(fr.argv, "--status") != "완료"          # DONE 강제 없음
    assert _flag_value(fr.argv, "--status") == "PENDING"       # 배의 현재 status 그대로


def test_apply_verdict_drift_still_completes(tmp_path):
    """verdict=drift(COMPLETION_VERDICTS 대상)는 기존대로 완료 경로를 탄다."""
    fr = _FakeRun()
    card = {"ship_no": 9, "task_id": "CTO-z", "clevel": "cto",
            "title": "t", "note": "", "next": "", "status": "DONE",
            "verdict": "drift", "next_step": "다음 한 수"}
    hr.apply_on_approval(card, gate_on=True, runner=fr,
                          decisions_path=tmp_path / "d.jsonl")
    assert _flag_value(fr.argv, "--status") == "완료"


def test_run_dryrun_no_live_delta(tmp_path, monkeypatch):
    import json as _j
    raw = [{"ship_no": 20, "task_id": "D", "clevel": "coo", "title": "표류배",
            "status": "DONE", "priority": "⛵돛단배", "note": "", "next": "",
            "enqueued_at": "2026-07-20"}]
    qf = tmp_path / "_queue.json"
    qf.write_text(_j.dumps(raw, ensure_ascii=False), encoding="utf-8")
    before = qf.read_bytes()
    monkeypatch.setattr(hr, "PENDING_FILE", tmp_path / "hangro_pending.json")
    monkeypatch.setattr(hr, "default_drift_ids", lambda: {"D"})
    monkeypatch.setattr(hr, "generate_destination",
                        lambda ship, **kw: {"ship_no": ship["ship_no"], "title": ship["title"],
                                            "verdict": "drift", "next_step": "다음", "confidence": 0.9,
                                            "low_confidence": False, "final_destination": "", "path_map": ""})
    result = hr.run(send=False, queue_path=qf)
    assert qf.read_bytes() == before                 # ★라이브 델타 0(큐 불변)
    assert (tmp_path / "hangro_pending.json").exists()
    assert result["card_count"] == 1


def test_main_dry_run_flag_suppresses_send(monkeypatch):
    """--send --dry-run 조합: main()이 run(send=False)를 호출하는지 검증"""
    monkeypatch.setattr(sys, "argv", ["script", "--send", "--dry-run"])
    calls = []
    def mock_run(*, send, audit_only):
        calls.append({"send": send, "audit_only": audit_only})
    monkeypatch.setattr(hr, "run", mock_run)
    hr.main()
    assert len(calls) == 1
    assert calls[0]["send"] is False, "--send --dry-run 조합에서 send=False 여야 함"
