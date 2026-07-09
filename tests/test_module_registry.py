"""
test_module_registry.py — 모듈 등록부(SSOT) 스키마·로더 pytest.
검증 대상: scripts/module_registry.py
"""

import copy
import os
import sys

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_TESTS_DIR)
_SCRIPTS_DIR = os.path.join(_PROJECT_ROOT, "scripts")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

import module_registry as mr  # noqa: E402

COMPLETE_MODULE = {
    "id": "cto-automation-health",
    "owner_role": "cto",
    "owner_nick": "시토",
    "feature": "자동화 건강 점수판 — 예약작업 실행결과 30분 갱신",
    "data_source": {"kind": "json", "ref": "erp_status.json"},
    "notify_spec": {"daily": False, "weekly": True, "monthly": False, "channel": "telegram", "bot_id": None},
    "front_card": {"window": "자율현황", "anchor": "layer-automation"},
    "autonomy": "auto",
    "ai_free_fallback": "예약작업이 사람 세션 없이 상시 가동",
    "feedback": {"enabled": True, "audience": "gm+clevel", "entries": []},
    "reversible": True,
}


def test_module_fields_tuple_matches_schema():
    # 계획 스키마의 11개 필드와 정확히 일치해야 함(순서 무관·집합 비교)
    assert set(mr.MODULE_FIELDS) == set(COMPLETE_MODULE.keys())


def test_autonomy_levels_allowed_values():
    assert mr.AUTONOMY_LEVELS == ("auto", "semi", "mech", "propose", "manual")


def test_validate_module_empty_dict_returns_violations():
    violations = mr.validate_module({})
    assert isinstance(violations, list)
    assert len(violations) > 0
    # 모든 필수 필드 누락이 각각 보고되어야 함
    for field in mr.MODULE_FIELDS:
        assert any(field in v for v in violations)


def test_validate_module_complete_module_passes():
    violations = mr.validate_module(COMPLETE_MODULE)
    assert violations == []


def test_validate_module_bad_autonomy_value():
    mod = copy.deepcopy(COMPLETE_MODULE)
    mod["autonomy"] = "godmode"
    violations = mr.validate_module(mod)
    assert len(violations) > 0
    assert any("autonomy" in v for v in violations)


def test_validate_module_reversible_non_bool():
    mod = copy.deepcopy(COMPLETE_MODULE)
    mod["reversible"] = "yes"
    violations = mr.validate_module(mod)
    assert len(violations) > 0
    assert any("reversible" in v for v in violations)


def test_load_registry_returns_modules_array(tmp_path):
    reg_file = tmp_path / "module_registry.json"
    reg_file.write_text(
        '{"_doc": "test", "modules": [' + "]}",
        encoding="utf-8",
    )
    # 위 write는 modules 빈 배열 — 아래로 실제 데이터 있는 케이스도 확인
    import json
    payload = {"_doc": "test", "modules": [COMPLETE_MODULE]}
    reg_file.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    registry = mr.load_registry(str(reg_file))
    assert isinstance(registry, dict)
    assert "modules" in registry
    assert isinstance(registry["modules"], list)
    assert len(registry["modules"]) == 1
    assert registry["modules"][0]["id"] == "cto-automation-health"


def test_load_registry_default_path_reads_project_ssot():
    # path=None → status/module_registry.json 기본경로. 초기값은 빈 배열이어도 통과.
    registry = mr.load_registry()
    assert isinstance(registry, dict)
    assert "modules" in registry
    assert isinstance(registry["modules"], list)


def test_get_modules_by_role_filters_by_owner_role():
    other_module = copy.deepcopy(COMPLETE_MODULE)
    other_module["id"] = "cmo-something"
    other_module["owner_role"] = "cmo"

    registry = {"_doc": "test", "modules": [COMPLETE_MODULE, other_module]}
    cto_modules = mr.get_modules_by_role("cto", registry=registry)
    assert isinstance(cto_modules, list)
    assert len(cto_modules) == 1
    assert cto_modules[0]["id"] == "cto-automation-health"

    cmo_modules = mr.get_modules_by_role("cmo", registry=registry)
    assert len(cmo_modules) == 1
    assert cmo_modules[0]["id"] == "cmo-something"

    none_modules = mr.get_modules_by_role("cfo", registry=registry)
    assert none_modules == []


def test_registry_all_modules_pass_validation():
    # 실제 등록부(status/module_registry.json)의 신규 스키마 모듈이 validate_module 통과(위반 0).
    # 레거시 module_reporter.py 소비 스키마(owner_role 없이 owner·cadence·collector 사용,
    # _reporter_schema 태그로 명시)는 별도 계약이라 이 검증 대상에서 제외한다.
    registry = mr.load_registry()
    for mod in registry["modules"]:
        if "owner_role" not in mod:
            continue
        violations = mr.validate_module(mod)
        assert violations == [], f"{mod.get('id')} 위반: {violations}"


def test_registry_has_at_least_3_cto_modules():
    # 시토(CTO) 도메인 모듈 최소 3개 등록 확인
    cto_modules = mr.get_modules_by_role("cto")
    assert len(cto_modules) >= 3
