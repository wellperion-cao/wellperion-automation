# -*- coding: utf-8 -*-
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import coo_registry as R


def test_registry_loads_shared_file():
    reg = R.load_registry()
    assert isinstance(reg.get("modules"), list)
    assert len(reg["modules"]) >= 1


def test_registry_schema_valid_for_coo_modules():
    reg = R.load_registry()
    assert R.validate_registry(reg) == []


def test_cto_modules_preserved_not_touched_by_coo_consumer():
    # 2026-07-24 웰리 승인 병합(34→26): cto-aide-gap-detector→ceo-gm-aide 흡수,
    # cto-check-gas→coo-check-status 흡수(둘 다 등록부 삭제, 코드 불변). 픽스처를
    # 현재 생존 cto-* id로 갱신 — 테스트 취지(coo 소비자가 타 도메인 모듈을
    # 훼손하지 않는지)는 그대로.
    reg = R.load_registry()
    ids = [m["id"] for m in reg["modules"]]
    assert "cto-automation-health" in ids
    assert "cto-weekly-page-hygiene" in ids
    assert "cto-inquiry-read-snapshot" in ids


def test_iter_coo_returns_only_coo_owned_modules():
    reg = R.load_registry()
    coo_mods = R.iter_coo(reg)
    assert coo_mods, "coo 모듈이 하나도 없음"
    assert all(m["owner_role"] == "coo" for m in coo_mods)
    assert all(not m["id"].startswith("cto-") for m in coo_mods)


def test_pilot_check_status_enabled_and_wired():
    reg = R.load_registry()
    m = R.get_module(reg, "coo-check-status")
    assert m is not None
    assert m["owner_role"] == "coo"
    assert m["enabled"] is True
    assert m["notify_spec"]["daily"] is True
    assert m["data_source"]["kind"] == "gas"


def test_iter_enabled_returns_all_enabled_coo_modules():
    reg = R.load_registry()
    enabled = {m["id"] for m in R.iter_enabled(reg)}
    assert enabled == {"coo-check-status", "coo-work-approval", "coo-schedule-ssot",
                        "coo-monthly-ops", "coo-notice", "coo-ops-fill-board"}


def test_workapproval_module_enabled_and_wired():
    reg = R.load_registry()
    m = R.get_module(reg, "coo-work-approval")
    assert m is not None
    assert m["owner_role"] == "coo"
    assert m["enabled"] is True
    assert m["notify_spec"]["daily"] is True
    assert m["data_source"]["kind"] == "gas"
