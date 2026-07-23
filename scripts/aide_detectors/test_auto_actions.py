# -*- coding: utf-8 -*-
"""US-003 자율 조치 뮤테이터 테스트 — 멱등성."""
import auto_actions as aa


def test_apply_tag_adds_then_noop():
    ship = {}
    assert aa.apply_tag(ship, "stall") is True
    assert ship["aide_flags"] == ["stall"]
    # 2회차 no-op(멱등)
    assert aa.apply_tag(ship, "stall") is False
    assert ship["aide_flags"] == ["stall"]


def test_apply_tag_preserves_existing_flags_and_note():
    ship = {"aide_flags": ["resumable"], "note": "원문"}
    assert aa.apply_tag(ship, "stall") is True
    assert ship["aide_flags"] == ["resumable", "stall"]
    assert ship["note"] == "원문"  # note 미변경


def test_apply_tag_coerces_non_list():
    ship = {"aide_flags": "corrupt"}
    assert aa.apply_tag(ship, "stall") is True
    assert ship["aide_flags"] == ["stall"]


def test_set_nudge_idempotent_same_clevel():
    ship = {}
    assert aa.set_nudge(ship, "coo") is True
    assert ship["aide_nudge"]["clevel"] == "coo"
    assert aa.set_nudge(ship, "coo") is False


def test_resolve_structural_depends_moves_and_preserves():
    ship = {"depends_on": "CTO-2026-07-06-X"}
    assert aa.resolve_structural_depends(ship) is True
    assert ship["depends_on_resolved"] == "CTO-2026-07-06-X"
    assert ship["depends_on"] == ""
    # 2회차 no-op
    assert aa.resolve_structural_depends(ship) is False


def test_resolve_structural_depends_noop_when_empty():
    assert aa.resolve_structural_depends({"depends_on": ""}) is False
    assert aa.resolve_structural_depends({}) is False
