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
    fetch = _fake_fetch({
        "dept=facility": {"ok": True, "data": [{"date": "any", "total": 26, "done": 15, "pct": 58}]},
        "dept=support": {"ok": True, "total": 50, "done": 46, "pct": 92, "allIssues": []},
    })
    st = R.fetch_check_status(fetch_fn=fetch)
    assert st["depts"]["facility"]["pct"] == 58
    assert st["depts"]["support"]["pct"] == 92
    assert st["anomaly"] is False
    assert st["tag"] == "measured"


def test_fetch_check_status_display_field():
    fetch = _fake_fetch({
        "dept=facility": {"ok": True, "data": [{"date": "any", "total": 26, "done": 15, "pct": 58}]},
        "dept=support": {"ok": True, "total": 50, "done": 46, "pct": 92, "allIssues": []},
    })
    st = R.fetch_check_status(fetch_fn=fetch)
    assert st["display"] == "시설 58% · 지원 92%"
    assert st["metrics"] == {"facility_pct": 58, "support_pct": 92}


def test_fetch_check_status_display_shows_dash_when_pct_none():
    fetch = _fake_fetch({
        "dept=facility": {"ok": True, "data": [{"date": "any", "total": 0, "done": 0, "pct": None}]},
        "dept=support": {"ok": True, "total": 50, "done": 46, "pct": 92, "allIssues": []},
    })
    st = R.fetch_check_status(fetch_fn=fetch)
    assert st["display"] == "시설 -% · 지원 92%"


def test_fetch_detects_pct_overflow_anomaly():
    fetch = _fake_fetch({
        "dept=facility": {"ok": True, "data": [{"date": "any", "total": 15, "done": 100, "pct": 667}]},
        "dept=support": {"ok": True, "total": 50, "done": 46, "pct": 92, "allIssues": []},
    })
    st = R.fetch_check_status(fetch_fn=fetch)
    assert st["anomaly"] is True
    assert any("100%" in r or "667" in r for r in st["reasons"])


def test_fetch_detects_issue_anomaly():
    fetch = _fake_fetch({
        "dept=facility": {"ok": True, "data": [{"date": "any", "total": 26, "done": 26, "pct": 100}]},
        "dept=support": {"ok": True, "total": 50, "done": 40, "pct": 80, "allIssues": ["시설부 여 3항목 미입력"]},
    })
    st = R.fetch_check_status(fetch_fn=fetch)
    assert st["anomaly"] is True
    assert any("미입력" in r for r in st["reasons"])


def test_fetch_issue_dict_rendered_as_text_not_repr():
    fetch = _fake_fetch({
        "dept=facility": {"ok": True, "data": [{"date": "any", "total": 26, "done": 26, "pct": 100}]},
        "dept=support": {"ok": True, "total": 50, "done": 40, "pct": 80, "allIssues": [
            {"gender": "m", "roundKey": "am1", "itemId": "c1",
             "issue": "지하2층 남자화장실 변기 시트 뒷면 이물질 묻어있음", "tip": "", "by": "박호균 과장"},
        ]},
    })
    st = R.fetch_check_status(fetch_fn=fetch)
    assert st["anomaly"] is True
    assert not any(r.startswith("support: {") for r in st["reasons"])
    assert any("이물질" in r for r in st["reasons"])


def test_issue_text_helper_prefers_known_keys():
    assert R._issue_text("이미 문자열") == "이미 문자열"
    assert R._issue_text({"issue": "핵심 메시지", "by": "홍길동"}) == "핵심 메시지"
    assert R._issue_text({"foo": "", "bar": "값1", "baz": "값2"}) == "값1 값2"


def test_pick_today_matches_kst_date_not_last_element():
    today = R._kst_today()
    resp = {"data": [
        {"date": "2020-01-01", "total": 10, "done": 1, "pct": 10},
        {"date": today, "total": 20, "done": 20, "pct": 100},
        {"date": "2099-01-01", "total": 5, "done": 5, "pct": 100},
    ]}
    row = R._pick_today(resp)
    assert row["date"] == today
    assert row["total"] == 20


def test_pick_today_falls_back_to_last_when_no_date_matches():
    resp = {"data": [
        {"date": "2020-01-01", "total": 10, "done": 1, "pct": 10},
        {"date": "2020-01-02", "total": 20, "done": 20, "pct": 100},
    ]}
    row = R._pick_today(resp)
    assert row["date"] == "2020-01-02"


def test_fetch_workapproval_active_and_pending_counted():
    today = R._kst_today()
    rows = [
        {"상태": "진행중", "결재상태": "대기", "종료일": today},
        {"상태": "진행중", "결재상태": "부서장 완료", "종료일": today},
        {"상태": "완료", "결재상태": "결재완료", "종료일": "2020-01-01"},
        # 결재상태는 활성/완료 여부와 무관하게 전체 rows 기준 집계(스펙 §1) — 보류 건도 결재대기에 포함
        {"상태": "보류", "결재상태": "대기", "종료일": today},
    ]
    st = R.fetch_workapproval_status(fetch_fn=lambda url: {"ok": True, "count": len(rows), "data": rows})
    assert st["display"] == "활성 2건 · 결재대기 3건"
    assert st["anomaly"] is False
    assert st["tag"] == "measured"
    assert st["metrics"] == {"active": 2, "pending": 3, "overdue": 0, "rejected": 0}


def test_fetch_workapproval_detects_overdue_anomaly():
    rows = [{"상태": "진행중", "결재상태": "대기", "종료일": "2020-01-01"}]
    st = R.fetch_workapproval_status(fetch_fn=lambda url: {"ok": True, "data": rows})
    assert st["anomaly"] is True
    assert any("마감 초과 1건" in r for r in st["reasons"])


def test_fetch_workapproval_detects_rejected_anomaly():
    rows = [{"상태": "진행중", "결재상태": "부서장 반려", "종료일": None}]
    st = R.fetch_workapproval_status(fetch_fn=lambda url: {"ok": True, "data": rows})
    assert st["anomaly"] is True
    assert any("반려 1건" in r for r in st["reasons"])
    # 반려 건은 결재대기 산식에서 명시적으로 제외(스펙 §1)
    assert st["metrics"]["pending"] == 0


def test_fetch_workapproval_no_anomaly_when_clean():
    today = R._kst_today()
    rows = [{"상태": "진행중", "결재상태": "결재완료", "종료일": today}]
    st = R.fetch_workapproval_status(fetch_fn=lambda url: {"ok": True, "data": rows})
    assert st["anomaly"] is False
    assert st["reasons"] == []


def test_status_fetchers_map_has_all_wired_modules():
    assert set(R.STATUS_FETCHERS.keys()) == {"coo-check-status", "coo-work-approval", "coo-notice"}
    assert R.STATUS_FETCHERS["coo-work-approval"] is R.fetch_workapproval_status
    assert R.STATUS_FETCHERS["coo-notice"] is R.fetch_notice_status


def test_fetch_notice_status_counts_saved_and_active():
    today = R._kst_today()
    rows = [
        {"id": "1", "startDate": "2026-01-01", "endDate": "2020-01-01"},  # 기간 만료
        {"id": "2", "startDate": today, "endDate": today},                 # 기간중
        {"id": "3", "startDate": "", "endDate": ""},                       # 상시(기간 미지정)
    ]
    st = R.fetch_notice_status(fetch_fn=lambda url: {"ok": True, "count": len(rows), "data": rows})
    assert st["display"] == "저장 3건 · 기간중 1건"
    assert st["anomaly"] is False
    assert st["tag"] == "measured"
    assert st["metrics"] == {"total": 3, "active": 1}


def test_fetch_notice_status_empty_list_is_safe():
    st = R.fetch_notice_status(fetch_fn=lambda url: {"ok": True, "data": []})
    assert st["display"] == "저장 0건 · 기간중 0건"
    assert st["anomaly"] is False
