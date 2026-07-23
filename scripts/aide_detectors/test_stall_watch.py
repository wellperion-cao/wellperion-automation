# -*- coding: utf-8 -*-
"""US-001 감지기 테스트."""
from datetime import date

import stall_watch as sw


# ── last_activity ──
def test_last_activity_single_bracket():
    ship = {"note": "[2026-07-03 GM] 작업", "enqueued_at": "2026-06-01"}
    assert sw.last_activity(ship) == date(2026, 7, 3)


def test_last_activity_multiple_brackets_takes_max():
    ship = {"note": "[2026-06-24] 시작 [2026-07-04 완료]", "enqueued_at": "2026-06-01"}
    assert sw.last_activity(ship) == date(2026, 7, 4)


def test_last_activity_no_bracket_falls_back_to_enqueued():
    ship = {"note": "브래킷 없는 서술", "enqueued_at": "2026-06-30"}
    assert sw.last_activity(ship) == date(2026, 6, 30)


def test_last_activity_non_date_bracket_ignored():
    ship = {"note": "[GM보좌 제안] 비날짜 [2026-07-02]", "enqueued_at": "2026-06-01"}
    assert sw.last_activity(ship) == date(2026, 7, 2)


def test_last_activity_none_when_no_source():
    assert sw.last_activity({"note": "no dates", "enqueued_at": None}) is None


# ── stall_threshold ──
def test_threshold_by_icon():
    assert sw.stall_threshold({"priority": "🛳️크루즈"}) == 2
    assert sw.stall_threshold({"priority": "⛴️여객선"}) == 3
    assert sw.stall_threshold({"priority": "⛵돛단배"}) == 5
    assert sw.stall_threshold({"priority": "NORMAL"}) == 5
    assert sw.stall_threshold({"priority": None}) == 5


# ── detect_stalled 경계 ±1 ──
def _ship(sn, pri, note, status="IN_PROGRESS", enq="2026-06-01"):
    return {"ship_no": sn, "task_id": f"T-{sn}", "priority": pri,
            "note": note, "status": status, "enqueued_at": enq, "clevel": "coo"}


def test_detect_stalled_boundary_not_over():
    today = date(2026, 7, 8)
    # ⛴️ 임계 3 · idle=3 → not stalled (경계, > 아님)
    q = [_ship(1, "⛴️여객선", "[2026-07-05]")]
    assert sw.detect_stalled(q, today) == []


def test_detect_stalled_boundary_over():
    today = date(2026, 7, 8)
    # ⛴️ 임계 3 · idle=4 → stalled
    q = [_ship(1, "⛴️여객선", "[2026-07-04]")]
    gaps = sw.detect_stalled(q, today)
    assert len(gaps) == 1
    assert gaps[0]["kind"] == "stalled"
    assert gaps[0]["days_idle"] == 4


def test_detect_stalled_by_weight_cruise_strict():
    today = date(2026, 7, 8)
    # 🛳️ 임계 2 · idle=3 → stalled ; NORMAL 임계 5 · idle=3 → not
    q = [_ship(1, "🛳️크루즈", "[2026-07-05]"),
         _ship(2, "NORMAL", "[2026-07-05]")]
    gaps = sw.detect_stalled(q, today)
    assert [g["ship_no"] for g in gaps] == [1]


def test_detect_stalled_ignores_non_in_progress():
    today = date(2026, 7, 8)
    q = [_ship(1, "🛳️크루즈", "[2026-06-01]", status="PENDING")]
    assert sw.detect_stalled(q, today) == []


def test_detect_stalled_no_bracket_uses_enqueued():
    today = date(2026, 7, 8)
    # 무브래킷 → date 소스=enqueued_at, 임계는 아이콘(⛴️=3) 유지. idle=8 → stalled
    q = [_ship(1, "⛴️여객선", "브래킷 없음", enq="2026-06-30")]
    gaps = sw.detect_stalled(q, today)
    assert len(gaps) == 1


def test_detect_stalled_flags_reversible():
    today = date(2026, 7, 8)
    q = [_ship(1, "🛳️크루즈", "[2026-06-01]")]
    g = sw.detect_stalled(q, today)[0]
    assert g["revert_ok"] is True and g["external"] is False and g["data_loss"] is False


# ── detect_resumable ──
def test_detect_resumable_structural_task_id_done():
    q = [
        {"ship_no": 10, "task_id": "CTO-2026-07-06-VOYAGE-MAP-PAGE", "status": "DONE"},
        {"ship_no": 11, "task_id": "T-11", "status": "PENDING",
         "depends_on": "CTO-2026-07-06-VOYAGE-MAP-PAGE", "clevel": "cto"},
    ]
    gaps = sw.detect_resumable(q)
    assert len(gaps) == 1
    assert gaps[0]["ship_no"] == 11
    assert gaps[0]["kind"] == "resumable"


def test_detect_resumable_dep_not_done_excluded():
    q = [
        {"ship_no": 10, "task_id": "CTO-2026-07-06-X", "status": "IN_PROGRESS"},
        {"ship_no": 11, "task_id": "T-11", "status": "PENDING",
         "depends_on": "CTO-2026-07-06-X"},
    ]
    assert sw.detect_resumable(q) == []


def test_detect_resumable_free_text_excluded():
    q = [{"ship_no": 11, "task_id": "T-11", "status": "PENDING",
          "depends_on": "브로제이 이전 100% 완료·검증"}]
    assert sw.detect_resumable(q) == []


def test_detect_resumable_bare_ship_no_done():
    q = [
        {"ship_no": 173, "task_id": "T-173", "status": "DONE"},
        {"ship_no": 200, "task_id": "T-200", "status": "PENDING", "depends_on": 173},
        {"ship_no": 201, "task_id": "T-201", "status": "PENDING", "depends_on": "173"},
    ]
    gaps = sw.detect_resumable(q)
    assert sorted(g["ship_no"] for g in gaps) == [200, 201]


def test_detect_resumable_skips_done_waiting_ship():
    q = [
        {"ship_no": 10, "task_id": "CTO-2026-07-06-X", "status": "DONE"},
        {"ship_no": 11, "task_id": "T-11", "status": "DONE",
         "depends_on": "CTO-2026-07-06-X"},
    ]
    assert sw.detect_resumable(q) == []
