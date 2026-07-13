"""
test_northstar_unstarted.py — 북극성 승인 배 미착수(세션 픽업 대상) 감지기 pytest.
검증 대상: scripts/gm_aide_scan.py 의 scan_northstar_unstarted / northstar_unstarted_worklist.
인라인 fixture(가짜 active·ns_log)만 사용 — 실제 status/_queue.json·northstar_log.jsonl은 건드리지 않는다.
순수 함수 검증 — 파일 IO 없이 인자 주입으로만 테스트한다.
"""

import os
import sys

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_TESTS_DIR)
_SCRIPTS_DIR = os.path.join(_PROJECT_ROOT, "scripts")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

import gm_aide_scan as gas  # noqa: E402


def _approved_event(ship_no, date, role="cmo", title="북극성 추천 승인건"):
    return {"event": "approved", "date": date, "role": role, "title": title,
            "ship_no": ship_no, "via": "callback", "logged_at": f"{date}T09:00:00.000000"}


def _ship(**overrides):
    base = {
        "task_id": "CMO-2026-07-08-NORTHSTAR-676",
        "clevel": "cmo",
        "title": "[북극성추천] 채널별 클릭→문의 전환율 배선",
        "status": "PENDING",
        "priority": "⛴️여객선",
        "enqueued_at": "2026-07-08",
        "ship_no": 676,
        "note": "[웰리 북극성 추천 승인 2026-06-29] 승인건",
        "next": "",
        "depends_on": "",
    }
    base.update(overrides)
    return base


# ── ① PENDING 승인배 감지 ──
def test_detects_pending_approved_ship_by_ship_no():
    active = [_ship()]
    ns_log = [_approved_event(676, "2026-07-08")]
    result = gas.scan_northstar_unstarted(active, ns_log)
    assert len(result) == 1
    assert result[0]["ship_no"] == 676
    assert result[0]["task_id"] == "CMO-2026-07-08-NORTHSTAR-676"
    assert result[0]["clevel"] == "cmo"


def test_detects_via_task_id_northstar_marker_without_log_match():
    # 콜백 유실 재등록 케이스(#849 실사례): ns_log ship_no 불일치여도 task_id/note로 감지.
    active = [_ship(
        task_id="CPO-2026-07-10-NORTHSTAR-849",
        clevel="cpo",
        ship_no=849,
        enqueued_at="2026-07-10",
        note="[웰리 북극성 추천 승인 2026-06-29] 재등록(가역)",
    )]
    ns_log = [_approved_event(835, "2026-07-10", role="cpo")]  # 다른 ship_no로 유실 전 승인 기록
    result = gas.scan_northstar_unstarted(active, ns_log)
    assert len(result) == 1
    assert result[0]["approved_date"] == "2026-07-10"  # ns_log 매칭 실패 → enqueued_at 폴백


# ── ② IN_PROGRESS는 제외(착수됨) ──
def test_excludes_in_progress_status():
    active = [_ship(status="IN_PROGRESS")]
    ns_log = [_approved_event(676, "2026-07-08")]
    result = gas.scan_northstar_unstarted(active, ns_log)
    assert result == []


# ── ③ DONE 제외 ──
def test_excludes_done_status():
    active = [_ship(status="DONE")]
    ns_log = [_approved_event(676, "2026-07-08")]
    result = gas.scan_northstar_unstarted(active, ns_log)
    assert result == []


# ── ④ 승인 이력 없는 일반 PENDING 제외 ──
def test_excludes_ordinary_pending_without_approval_signal():
    active = [_ship(
        task_id="CMO-2026-07-08-MARKETING-LOOP-CLOSE-EVAL-FEEDBACK",
        note="[2026-07-08 GM 승인] 마케팅 루프 ⑤ 평가환류",
        ship_no=743,
    )]
    ns_log = [_approved_event(676, "2026-07-08")]
    result = gas.scan_northstar_unstarted(active, ns_log)
    assert result == []


# ── ⑤ days_waiting 계산 ──
def test_days_waiting_computed_from_approved_date():
    active = [_ship(ship_no=890, task_id="COO-2026-07-11-NORTHSTAR-890", clevel="coo",
                     enqueued_at="2026-07-11")]
    ns_log = [_approved_event(890, "2026-07-11", role="coo")]
    result = gas.scan_northstar_unstarted(active, ns_log)
    assert len(result) == 1
    expected_days = (gas.TODAY - gas._parse_date_loose("2026-07-11")).days
    assert result[0]["days_waiting"] == expected_days


def test_days_waiting_none_when_date_unparseable():
    active = [_ship(enqueued_at="", note="[웰리 북극성 추천 승인 2026-06-29]")]
    ns_log = []
    result = gas.scan_northstar_unstarted(active, ns_log)
    assert len(result) == 1
    assert result[0]["days_waiting"] is None


# ── ⑥ 빈 입력 안전 ──
def test_empty_inputs_return_empty_list():
    assert gas.scan_northstar_unstarted([], []) == []
    assert gas.northstar_unstarted_worklist([], []) == []


def test_worklist_sorts_by_days_waiting_descending():
    active = [
        _ship(ship_no=676, task_id="CMO-2026-07-08-NORTHSTAR-676", clevel="cmo", enqueued_at="2026-07-08"),
        _ship(ship_no=890, task_id="COO-2026-07-11-NORTHSTAR-890", clevel="coo", enqueued_at="2026-07-11",
              note="[웰리 북극성 추천 승인 2026-06-29]"),
    ]
    ns_log = [
        _approved_event(676, "2026-07-08", role="cmo"),
        _approved_event(890, "2026-07-11", role="coo"),
    ]
    result = gas.northstar_unstarted_worklist(active, ns_log)
    assert [r["ship_no"] for r in result] == [676, 890]  # 더 오래 기다린 676이 먼저


def test_queue_not_mutated():
    active = [_ship()]
    ns_log = [_approved_event(676, "2026-07-08")]
    before = _ship()
    gas.scan_northstar_unstarted(active, ns_log)
    assert active[0] == before
