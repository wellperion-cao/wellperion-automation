"""
test_welly_orchestrate.py — 자율 대상 선별기 + 검증 규칙 1개 pytest.
검증 대상: scripts/welly_orchestrate.py
인라인 fixture(가짜 queue·registry)만 사용 — 실제 status/_queue.json은 건드리지 않는다.
"""

import copy
import os
import sys

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_TESTS_DIR)
_SCRIPTS_DIR = os.path.join(_PROJECT_ROOT, "scripts")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

import welly_orchestrate as wo  # noqa: E402

FAKE_REGISTRY = {
    "modules": [
        {
            "id": "cto-automation-health",
            "owner_role": "cto",
            "owner_nick": "시토",
            "feature": "자동화 건강 점수판",
            "data_source": {"kind": "json", "ref": "erp_status.json"},
            "notify_spec": {"daily": False, "weekly": True, "monthly": False, "channel": "telegram", "bot_id": None},
            "front_card": {"window": "자율현황", "anchor": "layer-automation"},
            "autonomy": "auto",
            "ai_free_fallback": "예약작업이 사람 세션 없이 상시 가동",
            "feedback": {"enabled": True, "audience": "gm+clevel", "entries": []},
            "reversible": True,
        }
    ]
}

EMPTY_REGISTRY = {"modules": []}

BASE_SHIP = {
    "task_id": "CTO-2026-07-09-A",
    "clevel": "cto",
    "title": "가역 배 예시",
    "status": "PENDING",
    "priority": "⛵돛단배",
    "enqueued_at": "2026-07-09",
    "note": "내부 점검 스크립트 patch",
    "next": "",
    "depends_on": "",
    "module": "T2",
    "ship_no": 900,
}


def _ship(**overrides):
    s = copy.deepcopy(BASE_SHIP)
    s.update(overrides)
    return s


# ── (a) 가역·해당clevel·활성·모듈존재 배만 선별 ──
def test_select_returns_reversible_active_matching_clevel_ship():
    queue = [_ship()]
    result = wo.select_autonomous_ships("cto", queue, registry=FAKE_REGISTRY)
    assert len(result) == 1
    assert result[0]["task_id"] == "CTO-2026-07-09-A"


def test_select_includes_in_progress_status():
    queue = [_ship(status="IN_PROGRESS")]
    result = wo.select_autonomous_ships("cto", queue, registry=FAKE_REGISTRY)
    assert len(result) == 1


# ── (b) 비가역 키워드 배 제외 ──
def test_select_excludes_irreversible_keyword_in_note():
    irreversible_notes = [
        "SNS 발행 진행",
        "운영서버 배포 실행",
        "레코드 삭제 처리",
        "외부전송 완료 예정",
        "결제 승인 대기",
        "보안 설정 변경",
        "전략 방향 결정",
        "공식값 갱신",
    ]
    for note in irreversible_notes:
        queue = [_ship(note=note)]
        result = wo.select_autonomous_ships("cto", queue, registry=FAKE_REGISTRY)
        assert result == [], f"비가역 키워드 미차단: {note}"


def test_select_excludes_irreversible_keyword_in_priority_or_title():
    queue = [_ship(title="자율 배포 파이프라인 구축")]
    result = wo.select_autonomous_ships("cto", queue, registry=FAKE_REGISTRY)
    assert result == []


# ── (c) 타 clevel 제외 ──
def test_select_excludes_other_clevel():
    queue = [_ship(clevel="cmo")]
    result = wo.select_autonomous_ships("cto", queue, registry=FAKE_REGISTRY)
    assert result == []


# ── (d) DONE 제외 ──
def test_select_excludes_done_status():
    queue = [_ship(status="DONE")]
    result = wo.select_autonomous_ships("cto", queue, registry=FAKE_REGISTRY)
    assert result == []


# ── (e) 등록부에 해당 role 모듈 없으면 빈 반환 ──
def test_select_returns_empty_when_no_registry_module_for_role():
    queue = [_ship()]
    result = wo.select_autonomous_ships("cto", queue, registry=EMPTY_REGISTRY)
    assert result == []


def test_select_mixed_queue_only_matching_ship_returned():
    queue = [
        _ship(task_id="A", status="PENDING"),
        _ship(task_id="B", clevel="cmo"),
        _ship(task_id="C", status="DONE"),
        _ship(task_id="D", note="계약 삭제 처리"),
    ]
    result = wo.select_autonomous_ships("cto", queue, registry=FAKE_REGISTRY)
    assert [s["task_id"] for s in result] == ["A"]


# ── (f) verify_reversible_meta ──
def test_verify_reversible_meta_done_without_artifact_fails():
    ship = _ship(status="DONE", artifact="")
    result = wo.verify_reversible_meta(ship)
    assert result["passed"] is False
    assert isinstance(result["evidence"], str)


def test_verify_reversible_meta_done_without_artifact_key_fails():
    ship = _ship(status="DONE")
    ship.pop("artifact", None)
    ship.pop("artifact_url", None)
    result = wo.verify_reversible_meta(ship)
    assert result["passed"] is False


def test_verify_reversible_meta_done_with_artifact_passes():
    ship = _ship(status="DONE", artifact="commit:abc1234")
    result = wo.verify_reversible_meta(ship)
    assert result["passed"] is True
    assert "abc1234" in result["evidence"]


def test_verify_reversible_meta_done_with_artifact_url_passes():
    ship = _ship(status="DONE", artifact_url="https://example.com/proof.png")
    result = wo.verify_reversible_meta(ship)
    assert result["passed"] is True
