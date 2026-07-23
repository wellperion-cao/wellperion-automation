# -*- coding: utf-8 -*-
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import coo_registry as R
import coo_report_line as RL


def _fetch_ok(url):
    if R.TODO_API in url:
        return {"ok": True, "data": [
            {"상태": "진행중", "결재상태": "대기", "종료일": R._kst_today()},
        ]}
    if "dept=facility" in url:
        return {"ok": True, "data": [{"total": 26, "done": 15, "pct": 58}]}
    return {"ok": True, "total": 50, "done": 46, "pct": 92, "allIssues": []}


def test_daily_line_has_check_status():
    lines = RL.build_coo_daily_lines(reg=R.load_registry(), fetch_fn=_fetch_ok)
    joined = "\n".join(lines)
    assert "점검 현황" in joined
    assert "58%" in joined and "92%" in joined


def test_daily_line_has_workapproval_status():
    lines = RL.build_coo_daily_lines(reg=R.load_registry(), fetch_fn=_fetch_ok)
    joined = "\n".join(lines)
    assert "업무·결재" in joined
    assert "활성 1건" in joined and "결재대기 1건" in joined


def test_daily_lines_cover_both_modules_no_anomaly():
    lines = RL.build_coo_daily_lines(reg=R.load_registry(), fetch_fn=_fetch_ok)
    assert len(lines) == 2
    assert "⚠" not in "\n".join(lines)


def test_daily_line_flags_anomaly():
    def _bad(url):
        if R.TODO_API in url:
            return {"ok": True, "data": [
                {"상태": "진행중", "결재상태": "대기", "종료일": R._kst_today()},
            ]}
        if "dept=facility" in url:
            return {"ok": True, "data": [{"total": 15, "done": 100, "pct": 667}]}
        return {"ok": True, "total": 50, "done": 46, "pct": 92, "allIssues": []}
    lines = RL.build_coo_daily_lines(reg=R.load_registry(), fetch_fn=_bad)
    assert any("⚠" in ln for ln in lines)


def test_only_daily_join_modules_appear():
    lines = RL.build_coo_daily_lines(reg=R.load_registry(), fetch_fn=_fetch_ok)
    # 스텁 모듈(daily_join=false)은 미출현
    assert all("리셉션" not in ln for ln in lines)
