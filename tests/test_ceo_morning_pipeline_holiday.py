"""
test_ceo_morning_pipeline_holiday.py — 휴관일 once-per-day 가드 회귀 방지 (배518).
검증 대상: wellperion-agents/scripts/ceo_morning_pipeline.py run_pipeline() 휴관 분기.

배경: 휴관 분기가 today_marker() 파일을 안 써서 once-per-day 가드가 안 걸렸다.
세션시작 훅이 GM 세션마다 재호출되므로, 휴관일엔 세션을 열 때마다 휴관 안내문이
중복 발송됐고 동시에 그날 morning_plans/*.json 이 저장소에 안 남았다
(08-09 공백의 실제 원인 — 08-09=2·4주 일요일). 실제 텔레그램은 절대 호출하지 않는다
(is_closed·build_holiday_notice·send_reports 전부 monkeypatch).
"""

import os
import sys

import pytest

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_TESTS_DIR)
_AGENT_SCRIPTS_DIR = os.path.join(_PROJECT_ROOT, "wellperion-agents", "scripts")
if _AGENT_SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _AGENT_SCRIPTS_DIR)

import ceo_morning_pipeline as m  # noqa: E402


def test_holiday_marker_blocks_duplicate_send(tmp_path, monkeypatch):
    monkeypatch.setattr(m, "PLAN_DIR", tmp_path)
    monkeypatch.setattr(m, "is_closed", lambda d: True)
    monkeypatch.setattr(m, "build_holiday_notice", lambda a, b: "[TEST] holiday notice")
    sent_calls = []
    monkeypatch.setattr(m, "send_reports", lambda report, q, dry_run: sent_calls.append(1) or True)

    rc1 = m.run_pipeline(dry_run=False, as_json=False, once_per_day=True)
    assert rc1 == 0
    assert len(sent_calls) == 1
    assert m.today_marker().exists()  # 근본수리: 마커가 남아야 가드가 작동한다

    # 같은 날 세션이 또 열려도(세션시작 훅 재호출) 재발송하지 않는다.
    rc2 = m.run_pipeline(dry_run=False, as_json=False, once_per_day=True)
    assert rc2 == 0
    assert len(sent_calls) == 1  # 여전히 1 — 중복 발송 없음


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
