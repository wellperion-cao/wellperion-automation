# -*- coding: utf-8 -*-
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import coo_registry as R

VALID = {"measured", "estimated", "unmeasured"}


def test_all_coo_modules_have_valid_honesty_default():
    reg = R.load_registry()
    for m in R.iter_coo(reg):
        assert m.get("honesty_default"), f"{m['id']} 정직 배지 없음"
        assert m["honesty_default"] in VALID, f"{m['id']} 잘못된 정직 배지"


def test_enabled_pilot_is_measured():
    reg = R.load_registry()
    assert R.get_module(reg, "coo-check-status")["honesty_default"] == "measured"
