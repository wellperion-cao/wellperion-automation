#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Synthetic test for 3-sector board render."""
import sys
import io
from pathlib import Path

# UTF-8 stdout (only wrap if not already wrapped)
if not getattr(sys, "_welp_stdout_wrapped", False):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys._welp_stdout_wrapped = True

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

import hangro_board as hb
from ship_classify import classify_ship

items = [
    {
        "id": "T1", "title": "#18 아침보고편 발행", "owner": "CMO",
        "status": "IN_PROGRESS", "end_date": "", "mod_date": "",
        "priority": "NORMAL", "needs_gm_appr": False, "appr_inflight": False,
        "terminal": False, "next": "19편 기획", "source": "queue",
        "간단설명": "검증 후 발행완료", "핵심조언": "IG 노출 확인 필수",
    },
    {
        "id": "T2", "title": "3섹터 표 양식 통일", "owner": "CTO",
        "status": "PENDING", "end_date": "", "mod_date": "",
        "priority": "HIGH", "needs_gm_appr": False, "appr_inflight": False,
        "terminal": False, "next": "", "source": "queue",
        "간단설명": "전 표면 일치", "핵심조언": "검증 후 푸시",
    },
    {
        "id": "T3", "title": "보류 테스트 건", "owner": "COO",
        "status": "ON_HOLD", "end_date": "", "mod_date": "",
        "priority": "NORMAL", "needs_gm_appr": False, "appr_inflight": False,
        "terminal": False, "next": "", "source": "queue",
        "간단설명": "멈춤 중", "핵심조언": "재개 조건: GM 방향 확인 후",
    },
    {
        "id": "T4", "title": "아이콘 표준 정리", "owner": "CEO",
        "status": "DONE", "end_date": "2026-06-18", "mod_date": "2026-06-18",
        "priority": "NORMAL", "needs_gm_appr": False, "appr_inflight": False,
        "terminal": False, "next": "전 표면 반영", "source": "queue",
        "간단설명": "완료", "핵심조언": "약속 L16 정본 업데이트",
    },
    {
        "id": "T5", "title": "표류 테스트 건", "owner": "CMO",
        "status": "DONE", "end_date": "2026-06-18", "mod_date": "2026-06-18",
        "priority": "LOW", "needs_gm_appr": False, "appr_inflight": False,
        "terminal": False, "next": "", "source": "queue",
        "간단설명": "완료인데 다음 없음", "핵심조언": "후속 모듈 설계 전 GM 확인 필요",
    },
]

for it in items:
    it["_ship"] = classify_ship({
        "title": it["title"],
        "priority": it["priority"],
        "deadline": it["end_date"],
    })

board, secs = hb.build_board([], items)
print(board)
print("\n--- 섹션 카운트 ---")
for k, v in secs.items():
    print(f"  {k}: {len(v)}")
