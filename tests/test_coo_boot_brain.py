# -*- coding: utf-8 -*-
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import coo_registry as R
import coo_boot_brain as B


def test_reversible_actions_go_auto():
    reg = R.load_registry()
    actions = B.build_module_actions(reg=reg, status_map={"coo-check-status": {"anomaly": False}})
    lanes = B.route_actions(actions)
    auto_names = {a["action"] for a in lanes["auto"]}
    assert {"aggregate", "report", "route"}.issubset(auto_names)
    assert "flag" not in auto_names  # status_map anomaly=False → flag 액션 없어야 함


def test_gated_actions_go_propose():
    reg = R.load_registry()
    actions = B.build_module_actions(reg=reg, status_map={"coo-check-status": {"anomaly": False}})
    lanes = B.route_actions(actions)
    propose_names = {a["action"] for a in lanes["propose"]}
    assert {"sheet_edit", "gas_deploy", "security"}.issubset(propose_names)


def test_gate_off_writes_nothing():
    reg = R.load_registry()
    res = B.run_boot_brain(reg=reg, status_map={"coo-check-status": {"anomaly": False}}, apply_gate=False)
    assert res["queue_delta"] == 0
    assert res["applied"] == 0


def test_anomaly_adds_flag_action():
    reg = R.load_registry()
    actions = B.build_module_actions(reg=reg, status_map={"coo-check-status": {"anomaly": True}})
    flags = [a for a in actions if a["action"] == "flag"]
    assert len(flags) == 1
    assert flags[0]["revert_ok"] is True  # 표시=가역
