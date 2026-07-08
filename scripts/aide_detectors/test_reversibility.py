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
