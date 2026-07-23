# -*- coding: utf-8 -*-
"""
cpo_member_rollup.py — 모듈 cpo-member-rollup 수집기(공유 SSOT 정합).
─────────────────────────────────────────────────────────────────────────────
등록부의 모듈 id `cpo-member-rollup` → id 규약으로 collectors.cpo_member_rollup
로 해소된다. notify_spec={weekly:true, monthly:true} 양쪽 cadence에서 동일
collect()가 호출된다(cmo-marketing-funnel 등 기존 수집기와 동일 패턴).

로직 재사용(중복 복사 금지): cpo_report.py 의 fetch_member_inquiries·
fetch_cpo_today_stats·fetch_cpo_churn_stats(GAS 사전집계 조회)를 그대로
호출한다. 전환율은 GAS 집계값(monthInquiry/monthReg)에 cpo_report.py
build_monthly_report와 동일한 근사 공식만 표시용으로 재계산 — 새 비즈니스
로직 없음.

정직 꼬리표: GAS 실측 집계는 있으나 전환율이 서로 다른 코호트 근사 → 부분.
전체 조회 실패 = 미측정.
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
import cpo_report  # noqa: E402 — 기존 fetch 로직 재사용(중복 복사 금지)

_LINK = "https://wellperion-cao.github.io/wellperion-automation/cpo/member/membership.html"


def collect(module=None) -> dict:
    """표준 payload 반환. today_stats(월간 GAS 집계)·churn(이탈 GAS 집계)·
    rows(예약활성 카운트용)를 cpo_report.py fetch 함수로 그대로 가져온다."""
    today_stats = cpo_report.fetch_cpo_today_stats()
    churn = cpo_report.fetch_cpo_churn_stats()
    rows = cpo_report.fetch_member_inquiries()

    if today_stats is None and churn is None and rows is None:
        return make_payload(
            title="회원 현황 롤업",
            summary_line="전체 소스 조회 실패(GAS 응답 없음)",
            metrics=[],
            honesty_tag="미측정",
            link=_LINK,
        )

    metrics = []
    summary_parts = []

    if today_stats is not None:
        mi = today_stats.get("monthInquiry")
        mr = today_stats.get("monthReg")
        ml = today_stats.get("monthLoss")
        conv = None
        if isinstance(mi, (int, float)) and mi > 0 and isinstance(mr, (int, float)):
            conv = round(mr / mi * 100, 1)
        metrics.append({"label": "이번달 신규문의", "value": mi if mi is not None else "미측정"})
        metrics.append({"label": "이번달 신규등록", "value": mr if mr is not None else "미측정"})
        metrics.append({"label": "문의→가입 전환율(근사)", "value": f"{conv}%" if conv is not None else "미측정"})
        metrics.append({"label": "이번달 LOSS", "value": ml if ml is not None else "미측정"})
        summary_parts.append(
            f"신규문의 {mi if mi is not None else '-'}건 · 신규등록 {mr if mr is not None else '-'}건"
        )
    else:
        summary_parts.append("이번달 문의·등록 집계: 데이터 없음")

    if rows is not None:
        today = cpo_report._today_str()
        month = today[:7]
        month_res = 0
        for r in rows:
            for res in (r.get("reservations") or []):
                if str(res.get("date", "")).startswith(month):
                    month_res += 1
        metrics.append({"label": "이번달 상담·체험 예약 활성", "value": month_res})
        summary_parts.append(f"예약활성 {month_res}건")
    else:
        metrics.append({"label": "예약 활성 건수", "value": "미측정"})

    if churn is not None:
        metrics.append({"label": "유효회원", "value": churn.get("activeCount", "-")})
        metrics.append({"label": "당월 LOSS율", "value": f"{churn.get('monthLossRate', '-')}%"})
        metrics.append({"label": "30일내 갱신임박", "value": churn.get("renewCount", "-")})
        summary_parts.append(
            f"LOSS율 {churn.get('monthLossRate', '-')}% · 갱신임박 {churn.get('renewCount', '-')}명"
        )
    else:
        metrics.append({"label": "이탈방지 성과", "value": "미측정"})

    summary = " · ".join(summary_parts) if summary_parts else "데이터 없음"

    return make_payload(
        title="회원 현황 롤업",
        summary_line=summary,
        metrics=metrics,
        honesty_tag="부분",
        link=_LINK,
    )


if __name__ == "__main__":
    print(json.dumps(collect(), ensure_ascii=False, indent=2))
