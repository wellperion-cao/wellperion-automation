# -*- coding: utf-8 -*-
"""
coo_work_approval.py — 모듈 coo-work-approval 수집기(공유 SSOT 정합).
─────────────────────────────────────────────────────────────────────────────
등록부(module_registry.json)의 모듈 id `coo-work-approval` → id 규약으로
이 모듈명(collectors.coo_work_approval)이 해소된다.

[2026-07-22 GM 지시 — 방4(자동화현황방) collector_missing 정리] 새 로직을 만들지
않는다 — scripts/coo_registry.py 의 기존 fetch_workapproval_status() 를 그대로
재사용한다(08시 통합보고 coo_report_line.build_coo_daily_lines 와 동일 실측 로직).
module_reporter 경로로도 흘려 등록부에 이미 선언된 bot_id="자동화현황방"(방4)에
실제로 닿게 한다(기존엔 collector가 없어 매일 스킵됐다).

정직 꼬리표: fetch_workapproval_status() 는 항상 tag="measured"(실측) → '측정'.
조회 자체가 예외를 던지면(GAS 응답 실패 등) '미측정'.
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
import coo_registry  # noqa: E402 — fetch_workapproval_status() 재사용(중복 복사 금지)

_LINK = "https://wellperion-cao.github.io/wellperion-automation/wellperion_guide(main).html#O1"


def collect(module=None) -> dict:
    """표준 payload 반환. coo_registry.fetch_workapproval_status() 실측 그대로 감싼다."""
    try:
        st = coo_registry.fetch_workapproval_status()
    except Exception as e:
        return make_payload(
            title="전사 업무·결재",
            summary_line=f"조회 실패({type(e).__name__})",
            metrics=[],
            honesty_tag="미측정",
            link=_LINK,
        )

    metrics = [{"label": k, "value": v} for k, v in (st.get("metrics") or {}).items()]
    if st.get("anomaly"):
        for r in (st.get("reasons") or [])[:5]:
            metrics.append({"label": "이상", "value": r})

    return make_payload(
        title="전사 업무·결재",
        summary_line=st.get("display", ""),
        metrics=metrics,
        honesty_tag="측정",
        link=_LINK,
    )


if __name__ == "__main__":
    print(json.dumps(collect(), ensure_ascii=False, indent=2))
