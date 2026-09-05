# -*- coding: utf-8 -*-
"""매출보고서 서버 판 읽기 라우트 (읽기 전용 · 배1071 · 시토).

  GET /api/report/sales_report_cells?date=YYYY-MM-DD (기본 어제 KST)
새 계산 없음 — sales_report_render.build_report(ref_date) 결과를 그대로 JSON 으로 낸다.
app.py 가 같은 폴더의 api_*.py 를 자동 등록한다(app.py 본문은 건드리지 않는다) — nginx 가 앞에서
auth_request 로 로그인 쿠키를 검사하므로 여기서 인증을 다시 하지 않는다(api_todo.py 와 같은 게이트).
"""
import os
import re
import sys

from fastapi import APIRouter, HTTPException, Query

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sales_report_render import build_report  # noqa: E402

router = APIRouter(prefix="/api/report")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@router.get("/sales_report_cells")
def sales_report_cells(date: str = Query(None)):
    if date is not None and not _DATE_RE.match(date):
        raise HTTPException(400, "date 는 YYYY-MM-DD")
    report = build_report(ref_date=date)
    if report is None:
        raise HTTPException(503, "시트 미러 없음(sync_sales.py 미동기화)")
    return {k: report[k] for k in
            ("cells", "final", "overrides", "matched", "total", "mismatches", "ref_date", "synced_at")}
