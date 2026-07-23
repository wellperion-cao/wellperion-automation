# -*- coding: utf-8 -*-
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import coo_registry as R
import coo_check_anomaly as A


class _FakeNotifier:
    def __init__(self):
        self.sent = []
    def send(self, message, reply_markup=None):
        self.sent.append(message)
        return {"ok": True}


def _fetch_anomaly(url):
    if "dept=facility" in url:
        return {"ok": True, "data": [{"total": 26, "done": 26, "pct": 100}]}
    return {"ok": True, "total": 50, "done": 40, "pct": 80, "allIssues": ["시설부 여 3항목 미입력"]}


def _fetch_clean(url):
    if "dept=facility" in url:
        return {"ok": True, "data": [{"total": 26, "done": 15, "pct": 58}]}
    return {"ok": True, "total": 50, "done": 46, "pct": 92, "allIssues": []}


def test_anomaly_triggers_send_when_not_dry():
    n = _FakeNotifier()
    res = A.run_anomaly_check(reg=R.load_registry(), fetch_fn=_fetch_anomaly, notifier=n, dry_run=False)
    assert res["sent"] == 1
    assert n.sent and "미입력" in n.sent[0]


def test_no_anomaly_no_send():
    n = _FakeNotifier()
    res = A.run_anomaly_check(reg=R.load_registry(), fetch_fn=_fetch_clean, notifier=n, dry_run=False)
    assert res["sent"] == 0
    assert n.sent == []


def test_dry_run_never_sends():
    n = _FakeNotifier()
    res = A.run_anomaly_check(reg=R.load_registry(), fetch_fn=_fetch_anomaly, notifier=n, dry_run=True)
    assert res["sent"] == 0
    assert len(res["alerts"]) == 1
    assert n.sent == []
