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
    reg = R.load_registry()
    ids = [m["id"] for m in reg["modules"]]
    assert "cto-automation-health" in ids
    assert "cto-aide-gap-detector" in ids
    assert "cto-check-gas" in ids


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


def test_iter_enabled_returns_only_coo_pilot():
    reg = R.load_registry()
    enabled = R.iter_enabled(reg)
    assert [m["id"] for m in enabled] == ["coo-check-status"]
