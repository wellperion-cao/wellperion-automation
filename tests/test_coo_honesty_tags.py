# -*- coding: utf-8 -*-
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import coo_registry as R

VALID = {"measured", "partial", "unmeasured"}


def test_all_modules_have_valid_honesty_tags():
    reg = R.load_registry()
    for m in reg["modules"]:
        assert m["honesty_tags"], f"{m['id']} 꼬리표 없음"
        assert set(m["honesty_tags"]).issubset(VALID), f"{m['id']} 잘못된 꼬리표"


def test_enabled_pilot_is_measured():
    reg = R.load_registry()
    assert R.get_module(reg, "check_status")["honesty_tags"] == ["measured"]


def test_stubs_are_unmeasured():
    reg = R.load_registry()
    for m in R.iter_enabled(reg):
        pass
    stubs = [m for m in reg["modules"] if not m["enabled"]]
    assert all("unmeasured" in m["honesty_tags"] for m in stubs)
