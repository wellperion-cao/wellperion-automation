# -*- coding: utf-8 -*-
"""ops_digest_sheet_push.py — 매출 보고 시트 '운영 현황 한눈에' 탭 자동 갱신(2026-08-10 GM 승인).

GM 요청: 매출 보고 시트를 열면 ①인사&파트너팀 진행사항 ②핵심 보고·진행현황 ③시설·지원·주차
운영현황을 한눈에 보고 싶다. 강습팀은 이번엔 뺀다(GM 확정 2026-08-10).

새 집계 없음 — 이미 매일 09:30 도는 값을 그대로 재사용한다:
  ①② report_stream_3_impl.build_digest() (HTML 태그만 제거 — 새 판정 없음)
  ③  support_check_summary.build_summary_lines() (그대로)

쓰기는 .deploy-sales/sales.js 의 신설 액션 ops_digest_write 1개뿐 — 그 탭만 지우고 다시 쓴다
(기존 탭·기존 셀 무접촉, '보고' 탭 H2:S21 포함). daily_scheduler.py run_stream_3_mgmt() 뒤에
한 줄로 얹혀 호출된다(새 예약작업 없음). 실패해도 텔레그램/카카오 발송에는 영향 없다
(best-effort — 여기서 예외를 삼키는 건 호출부 책임, 이 모듈은 예외를 그대로 던진다).
"""
from __future__ import annotations

import html as _html_mod
import json
import re
import sys
from datetime import datetime
from pathlib import Path

import requests

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from report_stream_3_impl import build_digest as _build_mgmt_digest  # noqa: E402
from support_check_summary import build_summary_lines as _build_check_lines  # noqa: E402

SALES_API = "https://script.google.com/macros/s/AKfycbzXcWyi-PgS9vBX5oW384OhnBZXaRwpZCma-hYnkOmTmh_SQ1b4WIg6esKgZw3ZF7-k-A/exec"
PW = "wellperion!@1202"  # .deploy-sales/sales.js 와 동일 게이트 키(코드 원문 그대로 재사용)


def _strip_html(text: str) -> str:
    return _html_mod.unescape(re.sub(r"<[^>]+>", "", text))


def build_text(today: str) -> str:
    mgmt_parts = _build_mgmt_digest(today)  # ①② 인사·파트너팀 + 핵심 업무 현황(지연·건수·임박·결재대기)
    mgmt_plain = _strip_html("\n\n".join(mgmt_parts))

    check_lines, _filled = _build_check_lines(date=today)  # ③ 시설·지원·주차
    check_plain = "\n".join(check_lines)

    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    return (
        f"운영 현황 한눈에 (자동 갱신 {stamp})\n\n"
        f"■ 인사·파트너팀 및 핵심 업무 현황\n{mgmt_plain}\n\n"
        f"■ 시설·지원·주차 운영 현황\n{check_plain}"
    )


def push(today: str | None = None) -> dict:
    today = today or datetime.now().strftime("%Y-%m-%d")
    text = build_text(today)
    resp = requests.post(
        SALES_API,
        data=json.dumps({"action": "ops_digest_write", "password": PW, "text": text}),
        headers={"Content-Type": "text/plain;charset=utf-8"},
        timeout=60,
    )
    result = resp.json()
    result["_sent_text"] = text  # 호출측 대조용(전송 원문 보존)
    return result


if __name__ == "__main__":
    r = push()
    print(json.dumps({k: v for k, v in r.items() if k != "_sent_text"}, ensure_ascii=False, indent=2))
