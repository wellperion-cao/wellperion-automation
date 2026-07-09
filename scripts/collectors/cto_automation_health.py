# -*- coding: utf-8 -*-
"""
cto_automation_health.py — 모듈 cto-automation-health 수집기(공유 SSOT 정합).
─────────────────────────────────────────────────────────────────────────────
등록부(module_registry.json)의 모듈 id `cto-automation-health` → id 규약으로
이 모듈명(collectors.cto_automation_health)이 해소된다.

1차 소스 = 모듈의 **선언된 data_source(status/erp_status.json)** 직독.
  erp_status.json 은 erp_status_publisher.py 가 30분 갱신하는 자동화 건강 현황
  (automation_health.summary/total/healthy/rate)을 담는다 → 실측 '측정' 꼬리표.

보강(fallback) = erp_status.json 에 필요한 값이 없을 때만:
  - integration_health.check_bridges()          → 연동 다리 [(name, ok, detail)]
  - learning_effect_meter.measure_all(dry_run=True) → 학습효과 측정 대상(무영속)
  (두 함수는 import·호출만 — 수정하지 않음. dry_run/check 는 side-effect 0.)

정직 꼬리표: 실측 = 측정 / 일부 = 부분 / 데이터 없음 = 미측정.
"""
from __future__ import annotations

import json
import os
import sys

_SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # scripts/
_PROJECT_ROOT = os.path.dirname(_SCRIPTS_DIR)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from collectors.base import make_payload  # noqa: E402

_LINK = "https://wellperion-cao.github.io/wellperion-automation/자율현황.html#health"
_DEFAULT_REF = "status/erp_status.json"


def _load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _resolve_ref(module):
    """모듈의 선언된 data_source.ref → 절대경로(없으면 기본 erp_status.json)."""
    ref = None
    if isinstance(module, dict):
        ds = module.get("data_source") or {}
        ref = ds.get("ref")
    ref = ref or _DEFAULT_REF
    return ref if os.path.isabs(ref) else os.path.join(_PROJECT_ROOT, ref)


def _from_erp_status(erp):
    """erp_status.json 의 automation_health 블록 → 표준 payload(없으면 None)."""
    if not isinstance(erp, dict):
        return None
    ah = erp.get("automation_health")
    if not isinstance(ah, dict) or not ah.get("total"):
        return None

    total = ah.get("total")
    healthy = ah.get("healthy")
    rate = ah.get("rate")

    metrics = [{"label": "자동화 가동", "value": f"{healthy}/{total}"}]
    if rate is not None:
        metrics.append({"label": "가동률", "value": f"{rate}%"})
    if isinstance(total, int) and isinstance(healthy, int):
        metrics.append({"label": "비정상", "value": total - healthy})

    summary = ah.get("summary") or f"자동화 {healthy}/{total} 정상"
    return make_payload(
        title="자율현황 자동화 건강",
        summary_line=summary,
        metrics=metrics,
        honesty_tag="측정",
        link=_LINK,
    )


def _from_functions():
    """보강 경로: check_bridges + measure_all(dry_run=True) 함수호출 흡수."""
    bridges = None
    bridge_err = None
    try:
        import integration_health  # noqa: PLC0415
        bridges = integration_health.check_bridges()  # list[(name, ok, detail)]
    except Exception as e:
        bridge_err = f"{type(e).__name__}: {str(e)[:80]}"

    learn_count = None
    try:
        import learning_effect_meter  # noqa: PLC0415
        # dry_run=True → learning_proposals.json 미영속(멱등·부작용 0)
        changed = learning_effect_meter.measure_all(dry_run=True)
        learn_count = len(changed) if isinstance(changed, list) else 0
    except Exception:
        learn_count = None

    metrics = []
    if bridges is not None:
        total = len(bridges)
        ok = sum(1 for b in bridges if len(b) >= 2 and b[1])
        fail = total - ok
        metrics.append({"label": "연동 다리 가동", "value": f"{ok}/{total}"})
        metrics.append({"label": "다리 실패", "value": fail})
        summary = f"연동 다리 {ok}/{total} 정상 · 실패 {fail}"
        honesty = "측정" if learn_count is not None else "부분"
    else:
        summary = f"연동 다리 점검 실패({bridge_err})"
        honesty = "미측정"

    if learn_count is not None:
        metrics.append({"label": "학습효과 측정대상", "value": learn_count})
        summary += f" · 학습효과 측정대상 {learn_count}건"

    return make_payload(
        title="자율현황 자동화 건강",
        summary_line=summary,
        metrics=metrics,
        honesty_tag=honesty,
        link=_LINK,
    )


def collect(module=None) -> dict:
    """표준 payload 반환. 1차=선언된 data_source(erp_status.json), 보강=함수호출."""
    erp = _load_json(_resolve_ref(module))
    payload = _from_erp_status(erp)
    if payload is not None:
        return payload
    return _from_functions()


if __name__ == "__main__":
    print(json.dumps(collect(), ensure_ascii=False, indent=2))
