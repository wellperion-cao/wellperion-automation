# -*- coding: utf-8 -*-
"""US-002 라우터 테스트 — 3부울 변주 6케이스."""
import reversibility as rv


def test_route_all_clean_auto():
    assert rv.route({"revert_ok": True, "external": False, "data_loss": False}) == "auto"


def test_route_not_reversible_propose():
    assert rv.route({"revert_ok": False, "external": False, "data_loss": False}) == "propose"


def test_route_external_propose():
    assert rv.route({"revert_ok": True, "external": True, "data_loss": False}) == "propose"


def test_route_data_loss_propose():
    assert rv.route({"revert_ok": True, "external": False, "data_loss": True}) == "propose"


def test_route_unknown_revert_propose():
    assert rv.route({"revert_ok": None, "external": False, "data_loss": False}) == "propose"


def test_route_missing_field_propose():
    assert rv.route({"revert_ok": True, "external": False}) == "propose"


# ── split_lanes: 배237(b) 반반 라우팅(정체→surface·재개가능→auto) ──
def _flags():
    return {"revert_ok": True, "external": False, "data_loss": False}


def _resumable(sn):
    g = {"kind": "resumable", "ship_no": sn, "clevel": "cto"}
    g.update(_flags())
    return g


def _stalled(sn):
    g = {"kind": "stalled", "ship_no": sn, "clevel": "coo"}
    g.update(_flags())
    return g


def test_split_resumable_goes_auto():
    resumable_auto, stall_surface, propose = rv.split_lanes([_resumable(11)])
    assert [g["ship_no"] for g in resumable_auto] == [11]
    assert stall_surface == [] and propose == []


def test_split_stalled_goes_surface_never_auto_or_propose():
    # 정체는 가역 플래그가 깨끗해도(auto 자격) surface-only 로만 분리 — 하드 분리
    resumable_auto, stall_surface, propose = rv.split_lanes([_stalled(5)])
    assert resumable_auto == [] and propose == []
    assert [g["ship_no"] for g in stall_surface] == [5]


def test_split_mixed_partition():
    gaps = [_stalled(1), _resumable(2), _stalled(3), _resumable(4)]
    resumable_auto, stall_surface, propose = rv.split_lanes(gaps)
    assert sorted(g["ship_no"] for g in resumable_auto) == [2, 4]
    assert sorted(g["ship_no"] for g in stall_surface) == [1, 3]
    assert propose == []


def test_split_resumable_not_reversible_goes_propose():
    g = {"kind": "resumable", "ship_no": 7, "revert_ok": False,
         "external": False, "data_loss": False}
    resumable_auto, stall_surface, propose = rv.split_lanes([g])
    assert resumable_auto == [] and stall_surface == []
    assert [x["ship_no"] for x in propose] == [7]
