# -*- coding: utf-8 -*-
"""
test_module_reporter.py — 모듈 자동보고 리포터 pytest (공유 SSOT 소비 기준).
정본 등록부 스키마 = status/module_registry.json (시우/COO 소유):
  notify_spec{daily,weekly,monthly,channel,bot_id}. 리포터는 이 한 곳을 소비한다.
네트워크 0(sender mock)·임시파일(tmp_path)로 실발송·영속 부작용 없이 검증.
"""
import json
import os
import sys
from datetime import datetime, timedelta
from unittest.mock import MagicMock

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_TESTS_DIR)
_SCRIPTS_DIR = os.path.join(_PROJECT_ROOT, "scripts")
_STATUS_DIR = os.path.join(_PROJECT_ROOT, "status")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

import module_reporter as reporter  # noqa: E402
import module_decisions_surface as decisions  # noqa: E402
from collectors import base  # noqa: E402
from collectors import cto_automation_health  # noqa: E402


# ── 테스트용 수집기 더블 (importlib.import_module 대체) ──────────────────────
class _FakeCollector:
    def __init__(self, fn):
        self._fn = fn

    def collect(self, module=None):
        return self._fn()


def _good_payload():
    return base.make_payload("좋은 모듈", "요약", [{"label": "a", "value": 1}], "측정", "http://x")


def _fake_import(name):
    """id 규약으로 해소된 collector 모듈명(collectors.*)에 대응하는 더블 반환."""
    if name == "collectors.good":
        return _FakeCollector(_good_payload)
    if name == "collectors.bad":
        def _boom():
            raise RuntimeError("boom")
        return _FakeCollector(_boom)
    raise ImportError(name)


def _write(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)


def _mk_registry(tmp_path, modules):
    p = tmp_path / "registry.json"
    _write(p, {"modules": modules})
    return str(p)


def _mk_rooms(tmp_path, rooms):
    p = tmp_path / "rooms.json"
    _write(p, rooms)
    return str(p)


def _mod(id="good", *, weekly=False, daily=False, monthly=False,
         channel="telegram", bot_id=None, **over):
    """공유 스키마(notify_spec) 준수 모듈 카드 생성."""
    spec = {"daily": daily, "weekly": weekly, "monthly": monthly,
            "channel": channel, "bot_id": bot_id}
    m = {
        "id": id, "owner_role": "cto", "owner_nick": "시토",
        "feature": "테스트 모듈",
        "data_source": {"kind": "json", "ref": "status/erp_status.json"},
        "notify_spec": spec,
        "front_card": {"window": "자율현황", "anchor": "x"},
        "autonomy": "mech", "ai_free_fallback": "무인 가동",
        "feedback": {"enabled": True, "audience": "gm+clevel", "entries": []},
        "reversible": True,
    }
    m.update(over)
    return m


# ── 공유 SSOT 소비: load_registry 로 실제 등록부를 읽어 소비 ──────────────────
def test_consumes_shared_registry_via_load_registry(tmp_path, monkeypatch):
    # 리포터가 module_registry.load_registry 를 통해 등록부를 소비하는지: 임시 등록부
    # 경로를 넘겨 그 모듈만 처리됨을 확인(별도 스키마 로더 없음).
    monkeypatch.setattr(reporter.importlib, "import_module", _fake_import)
    reg = _mk_registry(tmp_path, [_mod(id="good", weekly=True, bot_id=999)])
    rooms = _mk_rooms(tmp_path, {})
    sender = MagicMock(return_value=True)
    out = reporter.run_report(
        "weekly", registry_path=reg, rooms_path=rooms,
        log_path=str(tmp_path / "log.jsonl"), decisions_path=str(tmp_path / "d.json"),
        sender=sender,
    )
    sent = [r for r in out["results"] if r["action"] == "sent"]
    assert len(sent) == 1 and sent[0]["module"] == "good"


# ── 선택 규칙: notify_spec[cadence]==True AND channel==telegram ───────────────
def test_cadence_selection_by_notify_spec(tmp_path, monkeypatch):
    monkeypatch.setattr(reporter.importlib, "import_module", _fake_import)
    reg = _mk_registry(tmp_path, [
        _mod(id="good", weekly=True, bot_id=999),          # 선택됨
        _mod(id="good", daily=True, bot_id=999),           # 미선택(daily)
        _mod(id="good", monthly=True, bot_id=999),         # 미선택(monthly)
    ])
    rooms = _mk_rooms(tmp_path, {})
    sender = MagicMock(return_value=True)
    out = reporter.run_report(
        "weekly", registry_path=reg, rooms_path=rooms,
        log_path=str(tmp_path / "log.jsonl"), decisions_path=str(tmp_path / "d.json"),
        sender=sender,
    )
    # weekly 로 선택된 모듈만 처리(1건). 나머지 cadence 는 결과에 없음.
    assert len(out["results"]) == 1
    assert out["results"][0]["module"] == "good"


def test_non_telegram_channel_excluded(tmp_path, monkeypatch):
    monkeypatch.setattr(reporter.importlib, "import_module", _fake_import)
    reg = _mk_registry(tmp_path, [_mod(id="good", weekly=True, channel="email", bot_id=999)])
    rooms = _mk_rooms(tmp_path, {})
    sender = MagicMock(return_value=True)
    out = reporter.run_report(
        "weekly", registry_path=reg, rooms_path=rooms,
        log_path=str(tmp_path / "log.jsonl"), decisions_path=str(tmp_path / "d.json"),
        sender=sender,
    )
    sender.assert_not_called()
    assert out["results"] == []


# ── 라이브 게이트: bot_id=null → 발송 스킵(killswitch 등가) ───────────────────
def test_bot_id_null_skips_send(tmp_path, monkeypatch):
    monkeypatch.setattr(reporter.importlib, "import_module", _fake_import)
    reg = _mk_registry(tmp_path, [_mod(id="good", weekly=True, bot_id=None)])
    rooms = _mk_rooms(tmp_path, {})
    sender = MagicMock(return_value=True)
    out = reporter.run_report(
        "weekly", registry_path=reg, rooms_path=rooms,
        log_path=str(tmp_path / "log.jsonl"), decisions_path=str(tmp_path / "d.json"),
        sender=sender,
    )
    sender.assert_not_called()
    assert any(r["action"] == "skip" and r.get("reason") == "bot_id_null"
               for r in out["results"])


# ── chat_id 해소: bot_id int → 그대로 chat_id ───────────────────────────────
def test_bot_id_int_is_chat_id(tmp_path, monkeypatch):
    monkeypatch.setattr(reporter.importlib, "import_module", _fake_import)
    reg = _mk_registry(tmp_path, [_mod(id="good", weekly=True, bot_id=12345)])
    rooms = _mk_rooms(tmp_path, {})
    sender = MagicMock(return_value=True)
    out = reporter.run_report(
        "weekly", registry_path=reg, rooms_path=rooms,
        log_path=str(tmp_path / "log.jsonl"), decisions_path=str(tmp_path / "d.json"),
        sender=sender,
    )
    sender.assert_called_once()
    assert sender.call_args[0][0] == 12345
    assert any(r["action"] == "sent" for r in out["results"])


# ── chat_id 해소: bot_id str → telegram_rooms.json 방이름 해소 ───────────────
def test_bot_id_str_resolved_via_rooms(tmp_path, monkeypatch):
    monkeypatch.setattr(reporter.importlib, "import_module", _fake_import)
    reg = _mk_registry(tmp_path, [_mod(id="good", weekly=True, bot_id="점검관리방")])
    rooms = _mk_rooms(tmp_path, {"점검관리방": -5136037543})
    sender = MagicMock(return_value=True)
    out = reporter.run_report(
        "weekly", registry_path=reg, rooms_path=rooms,
        log_path=str(tmp_path / "log.jsonl"), decisions_path=str(tmp_path / "d.json"),
        sender=sender,
    )
    sender.assert_called_once()
    assert sender.call_args[0][0] == -5136037543


def test_bot_id_str_unresolved_room_skips(tmp_path, monkeypatch):
    monkeypatch.setattr(reporter.importlib, "import_module", _fake_import)
    reg = _mk_registry(tmp_path, [_mod(id="good", weekly=True, bot_id="자동화현황방")])
    rooms = _mk_rooms(tmp_path, {"자동화현황방": None})
    sender = MagicMock(return_value=True)
    out = reporter.run_report(
        "weekly", registry_path=reg, rooms_path=rooms,
        log_path=str(tmp_path / "log.jsonl"), decisions_path=str(tmp_path / "d.json"),
        sender=sender,
    )
    sender.assert_not_called()
    assert any(r.get("reason") == "room_unresolved" for r in out["results"])


# ── dry-run → payload 프리뷰 · 네트워크 0 ────────────────────────────────────
def test_dryrun_payload_no_network(tmp_path, monkeypatch):
    monkeypatch.setattr(reporter.importlib, "import_module", _fake_import)
    reg = _mk_registry(tmp_path, [_mod(id="good", weekly=True, bot_id=None)])
    rooms = _mk_rooms(tmp_path, {})
    sender = MagicMock(return_value=True)
    out = reporter.run_report(
        "weekly", dry_run=True, registry_path=reg, rooms_path=rooms,
        log_path=str(tmp_path / "log.jsonl"), decisions_path=str(tmp_path / "d.json"),
        sender=sender,
    )
    dry = [r for r in out["results"] if r["action"] == "dry-run"]
    assert len(dry) == 1
    assert base.validate_payload(dry[0]["payload"]) == []
    sender.assert_not_called()                 # 네트워크 0


# ── id → collector 규약 ──────────────────────────────────────────────────────
def test_id_to_collector_convention():
    assert reporter.collector_module_name("cto-automation-health") == "collectors.cto_automation_health"
    assert reporter.collector_module_name("cto-check-gas") == "collectors.cto_check_gas"


# ── 미구현 collector → 로그+스킵(오류 아님) ──────────────────────────────────
def test_missing_collector_skips_not_error(tmp_path, monkeypatch):
    monkeypatch.setattr(reporter.importlib, "import_module", _fake_import)
    # id 'missing' → collectors.missing → _fake_import ImportError
    reg = _mk_registry(tmp_path, [_mod(id="missing", weekly=True, bot_id=999)])
    rooms = _mk_rooms(tmp_path, {})
    sender = MagicMock(return_value=True)
    out = reporter.run_report(
        "weekly", registry_path=reg, rooms_path=rooms,
        log_path=str(tmp_path / "log.jsonl"), decisions_path=str(tmp_path / "d.json"),
        sender=sender,
    )
    sender.assert_not_called()
    actions = {r["module"]: r for r in out["results"]}
    assert actions["missing"]["action"] == "skip"
    assert actions["missing"]["reason"] == "collector_missing"
    assert out["pending_decisions"] == 0       # 오류 아님 → 결정 적재 없음


# ── 멱등: 발송 1회 후 재실행 중복 0 (dedup 키=module|date|cadence) ────────────
def test_idempotent_cadence_dedup(tmp_path, monkeypatch):
    monkeypatch.setattr(reporter.importlib, "import_module", _fake_import)
    reg = _mk_registry(tmp_path, [_mod(id="good", weekly=True, bot_id=999)])
    rooms = _mk_rooms(tmp_path, {})
    log = str(tmp_path / "log.jsonl")
    dec = str(tmp_path / "d.json")
    sender = MagicMock(return_value=True)
    now = datetime(2026, 7, 9, 9, 0, 0)

    out1 = reporter.run_report("weekly", registry_path=reg, rooms_path=rooms,
                               log_path=log, decisions_path=dec, sender=sender, now=now)
    assert any(r["action"] == "sent" for r in out1["results"])
    assert sender.call_count == 1

    out2 = reporter.run_report("weekly", registry_path=reg, rooms_path=rooms,
                               log_path=log, decisions_path=dec, sender=sender, now=now)
    assert sender.call_count == 1              # 재발송 없음
    assert any(r["action"] == "skip" and r.get("reason") == "dedup"
               for r in out2["results"])


# ── collector 예외 격리: 한 수집기 예외가 다른 모듈 발송 중단 안 함 ──────────
def test_collector_exception_isolation(tmp_path, monkeypatch):
    monkeypatch.setattr(reporter.importlib, "import_module", _fake_import)
    reg = _mk_registry(tmp_path, [
        _mod(id="bad", weekly=True, bot_id=999),
        _mod(id="good", weekly=True, bot_id=999),
    ])
    rooms = _mk_rooms(tmp_path, {})
    sender = MagicMock(return_value=True)
    out = reporter.run_report("weekly", registry_path=reg, rooms_path=rooms,
                              log_path=str(tmp_path / "log.jsonl"),
                              decisions_path=str(tmp_path / "d.json"),
                              decision_log_path=str(tmp_path / "dlog.jsonl"), sender=sender)
    actions = {r["module"]: r["action"] for r in out["results"]}
    assert actions["bad"] == "error"           # 격리됨
    assert actions["good"] == "sent"           # 다른 모듈 정상 발송
    assert out["pending_decisions"] >= 1       # 실패는 결정 후보로 적재


# ── collector 표준 payload 규격 (cto_automation_health 함수흡수 보강경로) ─────
def test_collector_payload_spec_fallback(monkeypatch):
    import integration_health
    import learning_effect_meter
    monkeypatch.setattr(integration_health, "check_bridges",
                        lambda: [("다리1", True, "ok"), ("다리2", False, "끊김")])
    monkeypatch.setattr(learning_effect_meter, "measure_all", lambda dry_run=False: [{"id": "c1"}])

    # data_source 를 존재하지 않는 파일로 지정 → 보강(함수흡수) 경로 진입
    payload = cto_automation_health.collect({"data_source": {"kind": "json", "ref": "status/__nope__.json"}})
    assert base.validate_payload(payload) == []
    assert payload["honesty_tag"] in base.HONESTY_TAGS
    labels = [m["label"] for m in payload["metrics"]]
    assert "연동 다리 가동" in labels


# ── collector 1차 소스: erp_status.json 직독 → '측정' 꼬리표 ─────────────────
def test_collector_reads_declared_data_source(tmp_path):
    erp = tmp_path / "erp_status.json"
    _write(erp, {"automation_health": {"summary": "자동화 21/23 정상 (91%)",
                                       "total": 23, "healthy": 21, "rate": 91}})
    payload = cto_automation_health.collect({"data_source": {"kind": "json", "ref": str(erp)}})
    assert base.validate_payload(payload) == []
    assert payload["honesty_tag"] == "측정"
    assert "21/23" in payload["summary_line"]


def test_base_validate_catches_violations():
    assert base.validate_payload({}) != []
    bad = base.make_payload("t", "s", [{"label": "a"}], "측정", "")  # value 누락
    assert any("metrics" in v for v in base.validate_payload(bad))
    good = base.make_payload("t", "s", [{"label": "a", "value": 1}], "측정", "")
    assert base.validate_payload(good) == []


# ── 결정 큐 dedup · cap · 만료 (module_decisions_surface — 기존 유지) ────────
def test_decision_dedup(tmp_path):
    path = str(tmp_path / "d.json")
    log = str(tmp_path / "dlog.jsonl")
    cand = [{"type": "이상징후", "module": "m1", "summary": "s", "options": ["재시도"]}]
    r1 = decisions.append_decisions(cand, path=path, log_path=log)
    assert r1["registered"] == 1
    r2 = decisions.append_decisions(cand, path=path, log_path=log)   # 동일 open 키
    assert r2["registered"] == 0 and r2["skipped_dedup"] == 1


def test_decision_cap(tmp_path):
    path = str(tmp_path / "d.json")
    log = str(tmp_path / "dlog.jsonl")
    cand = [{"type": "이상징후", "module": f"m{i}", "summary": "s", "options": ["재시도"]}
            for i in range(decisions.MAX_DECISIONS_PER_RUN + 3)]
    r = decisions.append_decisions(cand, path=path, log_path=log)
    assert r["registered"] == decisions.MAX_DECISIONS_PER_RUN
    assert r["overflow"] == 3


def test_decision_expiry(tmp_path):
    path = str(tmp_path / "d.json")
    log = str(tmp_path / "dlog.jsonl")
    past = datetime.now() - timedelta(days=30)
    decisions.append_decisions(
        [{"type": "이상징후", "module": "m1", "summary": "s", "options": ["재시도"]}],
        path=path, log_path=log, now=past, ttl_days=1,
    )
    pend = decisions.list_pending(path=path, log_path=log)
    assert pend == []
    r = decisions.append_decisions(
        [{"type": "이상징후", "module": "m1", "summary": "s2", "options": ["재시도"]}],
        path=path, log_path=log,
    )
    assert r["registered"] == 1


# ── .bat 3종이 리포터를 각 cadence 로 호출하도록 배선 ────────────────────────
def test_bat_files_wire_reporter():
    ops = os.path.join(_PROJECT_ROOT, "ops")
    for cad in ("daily", "weekly", "monthly"):
        p = os.path.join(ops, f"module_report_{cad}.bat")
        assert os.path.exists(p), f"{p} 없음"
        body = open(p, encoding="utf-8").read()
        assert "module_reporter.py" in body
        assert f"--cadence {cad}" in body
        assert "PYTHONIOENCODING=utf-8" in body
