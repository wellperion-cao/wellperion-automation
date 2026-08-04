#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/_check_sales_report_rate_formula.py — 배351 회귀 감시 (2026-08-04 시토)

배경: 회장님 방 09:30 매출보고 이미지(scripts/generate_sales_report_image.py)의
"총 매출 합계" 행 목표 달성률 셀이 =J{r}/SUM(INDIRECT(...AB70:AB76)) 로 되어 있어
(다른 시트의 팀별 목표 7칸 부분합, 뮤지컬·GXE 목표 2칸 누락) 같은 행 목표(K열, 뮤지컬·
GXE 포함)와 분모가 어긋나 12.32%(정답 11.92%)로 나갔다. GAS에서 =J{r}/K{r}(같은 행
직접 참조, 뮤지컬·GXE 행과 동일 패턴)로 정정(배포 @131, action=daily_report_rate_debug
로 실측). 이 스크립트는 그 정정이 유지되는지 매출보고 발송 전 확인하는 1회성 assert.

사용: python scripts/_check_sales_report_rate_formula.py [--month 8]
"""
import argparse
import sys

import requests

GAS_URL = "https://script.google.com/macros/s/AKfycbxDwFkrxK1YIaEoSNcuw2MiHiZQ-7o5N6311ytksSyeEd86ZFOhLknOWqQgNArQvZ-7/exec"


def check(month: int | None = None) -> None:
    params = {"action": "daily_report_rate_debug"}
    if month:
        params["month"] = month
    resp = requests.get(GAS_URL, params=params, timeout=30)
    data = resp.json()
    assert data.get("ok"), f"GAS 호출 실패: {data}"

    row4 = next((r for r in data["rows"] if "총 매출 합계" in str(r.get("label", ""))), None)
    assert row4 is not None, "'총 매출 합계' 행을 못 찾음 — 시트 구조가 바뀌었을 수 있음"

    formula = row4["rate"]["formula"]
    assert "INDIRECT" not in formula, (
        f"회귀 발생 — 총매출 달성률 수식이 다시 외부 INDIRECT 참조로 바뀜: {formula}"
    )

    month_val = row4["month"]["value"]
    target_val = row4["target"]["value"]
    rate_val = row4["rate"]["value"]
    expected = month_val / target_val
    assert abs(rate_val - expected) < 1e-9, (
        f"달성률 셀 값이 월누적/목표 재계산과 어긋남: 셀={rate_val} 재계산={expected}"
    )

    print(f"PASS — 총매출 달성률 수식={formula}, 값={rate_val * 100:.2f}% "
          f"(월누적 {month_val:,} / 목표 {target_val:,} 재계산 {expected * 100:.2f}%)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--month", type=int, default=None)
    args = ap.parse_args()
    try:
        check(args.month)
    except AssertionError as exc:
        print(f"FAIL — {exc}")
        sys.exit(1)
