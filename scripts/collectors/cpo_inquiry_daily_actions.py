# -*- coding: utf-8 -*-
"""
cpo_inquiry_daily_actions.py — 모듈 cpo-inquiry-daily-actions 수집기(공유 SSOT 정합).
─────────────────────────────────────────────────────────────────────────────
등록부(module_registry.json)의 모듈 id `cpo-inquiry-daily-actions` → id 규약으로
이 모듈명(collectors.cpo_inquiry_daily_actions)이 해소된다.

로직 재사용(중복 복사 금지): scripts/cpo_report.py 의 기존 fetch·분류 함수를
그대로 import·호출한다 — fetch_member_inquiries(GAS member_inquiry_list) +
uncontacted_candidates/todays_reservations/churn_risk_candidates(라이프사이클
분류기). 콘텐츠 엔진(cpo_report.py)은 그대로 두고 이 collector가 표준
payload(base.py)로 감싼다.

정직 꼬리표: 조회 성공(실측 카운트, 이탈위험은 근사치 혼재) = 부분 / 조회 실패 = 미측정.
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
import cpo_report  # noqa: E402 — 기존 fetch·분류 로직 재사용(중복 복사 금지)

_LINK = "https://wellperion-cao.github.io/wellperion-automation/cpo/member/%EB%AC%B8%EC%9D%98%ED%9A%8C%EC%9B%90.html"


def collect(module=None) -> dict:
    """표준 payload 반환. cpo_report.py 의 fetch_member_inquiries + 라이프사이클
    분류기(미컨택·오늘예약·이탈위험)를 그대로 재사용한다."""
    rows = cpo_report.fetch_member_inquiries()
    if rows is None:
        return make_payload(
            title="문의 라이프사이클 일일 액션",
            summary_line="문의 데이터 조회 실패(GAS 응답 없음)",
            metrics=[],
            honesty_tag="미측정",
            link=_LINK,
        )

    today = cpo_report._today_str()
    today_new = [r for r in rows if r.get("timestamp") == today]
    uncontacted = cpo_report.uncontacted_candidates(rows)
    todays_res = cpo_report.todays_reservations(rows, today)
    churn_cands = cpo_report.churn_risk_candidates(rows, today)

    metrics = [
        {"label": "오늘 신규 문의", "value": len(today_new)},
        {"label": "미컨택(연락기록 0건)", "value": len(uncontacted)},
        {"label": "오늘 상담·체험 예약", "value": len(todays_res)},
        {"label": "이탈위험 후보(추정)", "value": len(churn_cands)},
    ]
    summary = (
        f"신규 {len(today_new)}건 · 미컨택 {len(uncontacted)}건 · "
        f"오늘예약 {len(todays_res)}건 · 이탈위험(추정) {len(churn_cands)}건"
    )

    return make_payload(
        title="문의 라이프사이클 일일 액션",
        summary_line=summary,
        metrics=metrics,
        honesty_tag="부분",
        link=_LINK,
    )


if __name__ == "__main__":
    print(json.dumps(collect(), ensure_ascii=False, indent=2))
