# -*- coding: utf-8 -*-
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import coo_registry as R


def test_registry_loads_six_modules():
    reg = R.load_registry()
    assert len(reg["modules"]) == 6


def test_registry_schema_valid():
    reg = R.load_registry()
    assert R.validate_registry(reg) == []


def test_pilot_check_status_enabled_and_wired():
    reg = R.load_registry()
    m = R.get_module(reg, "check_status")
    assert m is not None
    assert m["enabled"] is True
    assert m["telegram"]["daily_join"] is True
    assert m["telegram"]["anomaly_immediate"] is True
    assert m["data_source"]["endpoint"].startswith("https://script.google.com")


def test_five_stub_modules_disabled():
    reg = R.load_registry()
    stubs = [m for m in reg["modules"] if m["id"] != "check_status"]
    assert len(stubs) == 5
    assert all(m["enabled"] is False for m in stubs)
    assert all(m["telegram"]["daily_join"] is False for m in stubs)


def test_iter_enabled_returns_only_pilot():
    reg = R.load_registry()
    enabled = R.iter_enabled(reg)
    assert [m["id"] for m in enabled] == ["check_status"]
