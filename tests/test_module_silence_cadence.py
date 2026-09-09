# -*- coding: utf-8 -*-
"""
test_module_silence_cadence.py — INC-057 재발방지 자체검사.
─────────────────────────────────────────────────────────────────────────────
사고: coo-monthly-ops(월간운영계획, monthly_ops_sync.py 매일 07:00 갱신)의
notify_spec 3필드가 전부 false 였다 — module_silence_detector.judge_module()은
셋 다 false 면 예상 주기를 못 정해 'active_no_cadence'(840h=35일 넘겨야 겨우
'unmeasurable')로만 판정하고 절대 'silent'로는 못 만든다. 그래서
monthly_ops_sync.py 가 2026-09-01~09-09 9일 연속 크래시해도 감지기가 못 잡았다.

이 테스트는 (1) 그 구조적 사각지대를 9일 침묵 주입으로 재현하고,
(2) 등록부 실물의 coo-monthly-ops.notify_spec.daily 가 계속 true로 남아
있는지(회귀 방지)를 고정한다. 네트워크 0·발신 0(judge_module은 순수 판정 함수).
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_TESTS_DIR)
_SCRIPTS_DIR = os.path.join(_PROJECT_ROOT, "scripts")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

import module_silence_detector as sd  # noqa: E402

_REGISTRY_PATH = os.path.join(_PROJECT_ROOT, "status", "module_registry.json")


def _base_module():
    return {
        "id": "coo-monthly-ops",
        "owner_role": "ceo",
        "owner_nick": "웰리",
        "feature": "월간운영계획(일일 파이프라인)",
        "data_source": {"kind": "json", "ref": "status/monthly_ops_plan.json"},
    }


def test_all_false_cadence_can_never_flag_silent():
    """회귀 재현: notify_spec 3필드가 전부 false면 9일 침묵도 'silent'가 못 된다."""
    now = datetime.now(timezone.utc)
    stale = now - timedelta(days=9)
    mod = _base_module()
    mod["notify_spec"] = {"daily": False, "weekly": False, "monthly": False,
                           "channel": "telegram", "bot_id": None}
    orig = sd.resolve_last_activity
    sd.resolve_last_activity = lambda module, root=sd.PROJECT_ROOT, now=None: (stale, "test", "")
    try:
        result = sd.judge_module(mod, now=now)
    finally:
        sd.resolve_last_activity = orig
    assert result["status"] != "silent", "이 구조적 사각지대가 재현되어야 아래 고침이 의미 있다"
    assert result["status"] == "active_no_cadence"


def test_daily_true_catches_the_same_9day_silence():
    """고침 확인: daily=true면 같은 9일 침묵이 'silent'로 잡힌다."""
    now = datetime.now(timezone.utc)
    stale = now - timedelta(days=9)
    mod = _base_module()
    mod["notify_spec"] = {"daily": True, "weekly": False, "monthly": False,
                           "channel": "telegram", "bot_id": None}
    orig = sd.resolve_last_activity
    sd.resolve_last_activity = lambda module, root=sd.PROJECT_ROOT, now=None: (stale, "test", "")
    try:
        result = sd.judge_module(mod, now=now)
    finally:
        sd.resolve_last_activity = orig
    assert result["status"] == "silent"
    assert result["max_allowed_hours"] == sd.DAILY_MAX_H


def test_registry_coo_monthly_ops_has_cadence_declared():
    """등록부 실물 고정: coo-monthly-ops가 다시 notify_spec 전부 false로 되돌아가면 이 테스트가 깨진다."""
    reg = json.load(open(_REGISTRY_PATH, encoding="utf-8"))
    mod = next(m for m in reg["modules"] if m["id"] == "coo-monthly-ops")
    spec = mod["notify_spec"]
    assert spec["daily"] or spec["weekly"] or spec["monthly"], (
        "coo-monthly-ops notify_spec이 다시 전부 false — INC-057 사각지대 회귀"
    )
    # bot_id는 여전히 null이어야 한다 — 이 필드를 켠 목적은 침묵감지 판정용이지
    # module_reporter.py 실발신용이 아니다(회귀 없음 확인).
    assert spec["bot_id"] is None


if __name__ == "__main__":
    test_all_false_cadence_can_never_flag_silent()
    test_daily_true_catches_the_same_9day_silence()
    test_registry_coo_monthly_ops_has_cadence_declared()
    print("OK — 3/3 통과")
