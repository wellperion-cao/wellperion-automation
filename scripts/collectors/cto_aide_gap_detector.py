# -*- coding: utf-8 -*-
"""
cto_aide_gap_detector.py — 모듈 cto-aide-gap-detector 수집기(공유 SSOT 정합).
─────────────────────────────────────────────────────────────────────────────
등록부(module_registry.json)의 모듈 id `cto-aide-gap-detector` → id 규약으로
이 모듈명(collectors.cto_aide_gap_detector)이 해소된다.

[2026-07-22 GM 지시 — 방4(자동화현황방) collector_missing 정리] 새 집계 로직을
만들지 않는다 — 06:30 gm_aide_scan.bat 이 이미 매일 status/gm_aide_scan_log.jsonl
에 남기는 최신 "scan" 이벤트(gap_auto/gap_stall/gap_propose 등, 감지엔진 시토 소유
필드)를 읽기만 한다(scripts/gm_aide_scan.py:read_jsonl 재사용). 같은 로그의
captured/profile_hints 필드는 ceo-gm-aide(웰리 두뇌 소유)라 여기선 다루지 않는다
— 단일 파이프라인·두 소비자(등록부 주석 그대로).

정직 꼬리표: 오늘자 scan 이벤트 존재 = 측정 / 로그 없음·오늘자 없음 = 미측정.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone

_SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # scripts/
_PROJECT_ROOT = os.path.dirname(_SCRIPTS_DIR)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from collectors.base import make_payload  # noqa: E402
import gm_aide_scan  # noqa: E402 — read_jsonl()·SCAN_LOG 재사용(중복 파싱 금지)

_LINK = "https://wellperion-cao.github.io/wellperion-automation/자율현황.html#layer-autonomy"
_KST = timezone(timedelta(hours=9))


def collect(module=None) -> dict:
    """표준 payload 반환. gm_aide_scan_log.jsonl 최신 'scan' 이벤트의 gap_* 필드만 요약."""
    recs = gm_aide_scan.read_jsonl(gm_aide_scan.SCAN_LOG)
    scans = [r for r in recs if isinstance(r, dict) and r.get("event") == "scan"]
    if not scans:
        return make_payload(
            title="자율 틈 감지기",
            summary_line="scan 로그 없음",
            metrics=[],
            honesty_tag="미측정",
            link=_LINK,
        )

    latest = scans[-1]
    gap_auto = latest.get("gap_auto", 0)
    gap_stall = latest.get("gap_stall", 0)
    gap_propose = latest.get("gap_propose", 0)
    logged_at = latest.get("logged_at", "")

    metrics = [
        {"label": "정체 감지(gap_stall)", "value": gap_stall},
        {"label": "자동 재개(gap_auto)", "value": gap_auto},
        {"label": "제안 대기(gap_propose)", "value": gap_propose},
        {"label": "최근 스캔", "value": logged_at},
    ]
    stall_list = latest.get("gap_stall_list") or []
    for s in stall_list[:5]:
        metrics.append({"label": "정체 배", "value": f"#{s.get('ship_no')} {s.get('reason', '')}"})

    summary = f"정체 {gap_stall}건 · 자동재개 {gap_auto}건 · 제안대기 {gap_propose}건 (스캔 {logged_at})"

    # 오늘(KST)자 스캔이면 '측정', 아니면(침묵 가능성) '부분'
    today = datetime.now(_KST).strftime("%Y-%m-%d")
    honesty = "측정" if str(logged_at).startswith(today) else "부분"

    return make_payload(
        title="자율 틈 감지기",
        summary_line=summary,
        metrics=metrics,
        honesty_tag=honesty,
        link=_LINK,
    )


if __name__ == "__main__":
    print(json.dumps(collect(), ensure_ascii=False, indent=2))
