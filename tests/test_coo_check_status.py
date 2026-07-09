# -*- coding: utf-8 -*-
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import coo_registry as R


def _fake_fetch(mapping):
    def _f(url):
        for key, resp in mapping.items():
            if key in url:
                return resp
        raise AssertionError(f"예상 못한 URL: {url}")
    return _f


def test_fetch_normal_no_anomaly():
    reg = R.load_registry()
    m = R.get_module(reg, "coo-check-status")
    fetch = _fake_fetch({
        "dept=facility": {"ok": True, "data": [{"date": "any", "total": 26, "done": 15, "pct": 58}]},
        "dept=support": {"ok": True, "total": 50, "done": 46, "pct": 92, "allIssues": []},
    })
    st = R.fetch_check_status(m, fetch_fn=fetch)
    assert st["depts"]["facility"]["pct"] == 58
    assert st["depts"]["support"]["pct"] == 92
    assert st["anomaly"] is False
    assert st["tag"] == "measured"


def test_fetch_detects_pct_overflow_anomaly():
    reg = R.load_registry()
    m = R.get_module(reg, "coo-check-status")
    fetch = _fake_fetch({
        "dept=facility": {"ok": True, "data": [{"date": "any", "total": 15, "done": 100, "pct": 667}]},
        "dept=support": {"ok": True, "total": 50, "done": 46, "pct": 92, "allIssues": []},
    })
    st = R.fetch_check_status(m, fetch_fn=fetch)
    assert st["anomaly"] is True
    assert any("100%" in r or "667" in r for r in st["reasons"])


def test_fetch_detects_issue_anomaly():
    reg = R.load_registry()
    m = R.get_module(reg, "coo-check-status")
    fetch = _fake_fetch({
        "dept=facility": {"ok": True, "data": [{"date": "any", "total": 26, "done": 26, "pct": 100}]},
        "dept=support": {"ok": True, "total": 50, "done": 40, "pct": 80, "allIssues": ["시설부 여 3항목 미입력"]},
    })
    st = R.fetch_check_status(m, fetch_fn=fetch)
    assert st["anomaly"] is True
    assert any("미입력" in r for r in st["reasons"])
