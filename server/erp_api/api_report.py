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
    out = {k: report[k] for k in
           ("cells", "final", "overrides", "matched", "total", "mismatches", "ref_date", "synced_at")}
    # 시트 없는 판(브로제이 결제 + ERP 회원 원장 · 배 2523 · GM 지시 2026-09-16) — 같은 칸 이름으로 나란히 낸다.
    # ★GM 2026-09-16 12:5x: 「10/1 까지 기다리지 말고 오늘부터 대양CIS 결제를 손으로 브로제이에 입력한 것을
    #   그대로 가져와라 — 실결제 전에 뭐가 더 필요한지 시험해야 한다」. 그래서 server_final(시트 0칸)을 여기서
    #   완성해 내고, 시트 판과의 칸별 차이(diff)를 그대로 붙인다 — 차이가 곧 「더 필요한 것」 목록이다.
    # 못 계산하면 사유만 적고 시트 판은 그대로 낸다(조용히 0 으로 두지 않는다).
    try:
        from brojay_cells import compute as _brojay  # noqa: PLC0415
        out["brojay"] = _brojay(out["ref_date"]) or {"detail": "그달 브로제이 결제 적재 없음"}
    except Exception as e:  # 원천 하나가 없어도 보고는 나간다 — 조용히 0 으로 두지 않고 사유를 남긴다
        out["brojay"] = {"detail": "계산 실패: %s" % e}
    out["server_final"] = _server_final(out)
    return out


def _server_final(out):
    """시트 0칸 판 — 매출 11칸·등록 6칸 = brojay_cells · 회원 5칸 = members(overrides) · 입장 3칸 = 브로제이 출석.
    각 칸의 원천과 시트 판 대비 차이를 함께 낸다. 원천이 빠진 칸은 값을 지어내지 않고 missing 에 적는다."""
    from sales_report_render import _num  # noqa: PLC0415
    cells, source, missing = {}, {}, []
    bj = out.get("brojay") or {}
    if bj.get("cells"):
        for k, v in bj["cells"].items():
            cells[k] = v
            source[k] = "brojay"
    else:
        missing.append("매출·등록 17칸(브로제이 결제 없음: %s)" % bj.get("detail", ""))
    for k in ("N2", "N3", "N4", "N5", "N6"):
        if k in (out.get("final") or {}):
            cells[k] = out["final"][k]
            source[k] = "erp-members"
    try:
        from api_visitors import visitors as _visitors  # noqa: PLC0415
        v = _visitors(out["ref_date"])
        if v.get("ok"):
            for k, b in (("N13", "정회원"), ("N14", "준회원"), ("N15", "유소년")):
                cells[k] = "%d명" % v["visitors"][b]
                source[k] = "brojay-entries"
        else:
            missing.append("입장 3칸(%s)" % v.get("detail", ""))
    except Exception as e:
        missing.append("입장 3칸(계산 실패: %s)" % e)
    sheet = out.get("cells") or {}
    diff = []
    for k in sorted(cells):
        a, b = _num(cells[k]), _num(sheet.get(k))
        if a != b:
            diff.append({"cell": k, "server": cells[k], "sheet": str(sheet.get(k) or "").strip(), "gap": a - b})
    # 22칸 = sales_report_render 정의서 그대로(I4·I6·I7 + 팀 8 + 회원 5 + 등록 6 = 22). 입장 3칸(N13~N15)과
    # J* 누적은 정의서 밖(화면용)이라 셈에서 뺀다 — 시토 실측 2026-09-16: 입장까지 세면 25, 누적까지 36.
    report22 = ["I4", "I6", "I7"] + ["I%d" % r for r in range(8, 16)] + ["N%d" % r for r in range(2, 13)]
    return {"cells": cells, "source": source, "missing": missing, "diff": diff,
            "cells_total": len(report22), "cells_filled": sum(1 for k in report22 if k in cells),
            "sheet_cells_used": 0}
