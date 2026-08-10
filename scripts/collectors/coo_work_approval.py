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

[2026-08-10 GM 지시 — "숫자만 있고 무엇인지 없다"] fetch_workapproval_status() 는
건수만 반환한다(항목 단위 없음) — 이름이 필요한 여기서는 **같은 읽기 경로(TODO_API
todo_list)를 그대로 재호출**해 **동일 필터 조건을 재적용**한다. 이 패턴은 새 판정
로직이 아니다 — worklog_gaps.py 의 rule_approval_stale_pending·
rule_task_deadline_passed_active 가 이미 같은 이유로 같은 방식을 쓴다(신규 도입 아님,
기존 관례 재사용). summary_line 5줄(■ 소제목)은 cpo_member_rollup.py 와 동일 표준.

정직 꼬리표: 조회 성공이면 '측정'. GAS 응답 실패 등 조회 자체가 예외를 던지면 '미측정'.

신호등(🟢) 안내: 제목 앞 색동그라미는 anomaly(마감 초과 등) 판정이 아니라
clevel_colors.CLEVEL_INFO 의 **부서 고정색**(COO=🟢, 2026-07-18 GM 확정 · 전 C-Level
모듈 공통)이다 — "이상 있으면 색이 바뀌는" 신호등이 아니라 "이 보고가 시우(COO) 소관"
이라는 소속 표시. 여기만 anomaly 연동으로 바꾸면 다른 5개 C-Level 모듈과 표기 규칙이
어긋난다(clevel_colors.py:3 "다른 포맷터는 이 값을 복사하지 말고 이 모듈을 import").
그래서 색동그라미 자체는 그대로 두고, 대신 마감 초과·결재 대기를 본문(summary_line)
안에 이름과 함께 또렷이 적어 "초록인데 괜찮나?" 의문을 본문에서 해소한다.
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone

_SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # scripts/
_PROJECT_ROOT = os.path.dirname(_SCRIPTS_DIR)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from collectors.base import make_payload  # noqa: E402
import coo_registry  # noqa: E402 — TODO_API·_http_get_json 재사용(중복 복사 금지)

_LINK = "https://wellperion-cao.github.io/wellperion-automation/wellperion_guide(main).html#O1"

_KST = timezone(timedelta(hours=9))
_DEPT_RE = re.compile(r"^\[\d+\]\s*(.+)$")  # 카테고리 "[4] 운영 정책" → "운영 정책"


def _dept(row: dict) -> str:
    raw = str(row.get("카테고리", "") or "").strip()
    m = _DEPT_RE.match(raw)
    return m.group(1) if m else (raw or "부서 미기재")


def _name(row: dict) -> str:
    return str(row.get("업무명", "") or "").strip() or str(row.get("id", "") or "이름 정보 없음")


def _owner(row: dict) -> str:
    return str(row.get("담당자", "") or "").strip() or "담당 미기재"


def _dept_breakdown(rows: list) -> str:
    counts: dict[str, int] = {}
    for r in rows:
        d = _dept(r)
        counts[d] = counts.get(d, 0) + 1
    if len(counts) <= 1:
        return ""
    ordered = sorted(counts.items(), key=lambda kv: -kv[1])
    return " · 부서별 " + "·".join(f"{d} {n}" for d, n in ordered)


def collect(module=None) -> dict:
    """표준 payload 반환 — summary_line 안에 ■ 소제목 4줄(진행 중/마감 넘긴 일/결재
    기다리는 것/반려)을 담는다(cpo_member_rollup.py 와 동일 표준). metrics는 비움(영문
    키 노출 금지 — GM 2026-08-10 지시)."""
    try:
        rows = coo_registry._http_get_json(f"{coo_registry.TODO_API}?action=todo_list").get("data", [])
    except Exception as e:
        return make_payload(
            title="전사 업무·결재",
            summary_line=f"조회 실패({type(e).__name__})",
            metrics=[],
            honesty_tag="미측정",
            link=_LINK,
        )

    # 필터 조건 = coo_registry.fetch_workapproval_status() 와 동일(그대로 재적용 — 신규 판정 로직 아님).
    active = [r for r in rows if r.get("상태") not in ("완료", "보류")]
    pending = [
        r for r in rows
        if (r.get("결재상태") or r.get("결재요청")) and r.get("결재상태") != "결재완료"
        and "반려" not in (r.get("결재상태") or "")
    ]
    today = datetime.now(_KST).strftime("%Y-%m-%d")
    overdue = [r for r in active if r.get("종료일") and r["종료일"] < today]
    rejected = [r for r in rows if "반려" in (r.get("결재상태") or "")]

    line1 = f"■ 진행 중 — 활성 {len(active)}건"

    if overdue:
        today_d = datetime.now(_KST).date()
        with_days = []
        for r in overdue:
            end = str(r["종료일"])[:10]
            try:
                d = (today_d - datetime.strptime(end, "%Y-%m-%d").date()).days
            except ValueError:
                d = None
            with_days.append((r, d))
        with_days.sort(key=lambda t: (t[1] is None, -(t[1] or 0)))  # 가장 오래 넘긴 순
        top = with_days[:5]
        detail = ", ".join(
            f"{_name(r)}({_dept(r)}·{_owner(r)}·{d if d is not None else '?'}일 초과)" for r, d in top
        )
        tail = f" 외 {len(overdue) - 5}건" if len(overdue) > 5 else ""
        line2 = f"■ 마감 넘긴 일 — {len(overdue)}건 · {detail}{tail}{_dept_breakdown(overdue)}"
    else:
        line2 = "■ 마감 넘긴 일 — 없음"

    if pending:
        top = pending[:5]
        detail = ", ".join(
            f"{_name(r)}({_dept(r)}·{_owner(r)}·{r.get('결재상태') or r.get('결재요청') or '대기'})"
            for r in top
        )
        tail = f" 외 {len(pending) - 5}건" if len(pending) > 5 else ""
        line3 = f"■ 결재 기다리는 것 — {len(pending)}건 · {detail}{tail}"
    else:
        line3 = "■ 결재 기다리는 것 — 없음"

    if rejected:
        top = rejected[:5]
        detail = ", ".join(f"{_name(r)}({_dept(r)}·{_owner(r)})" for r in top)
        tail = f" 외 {len(rejected) - 5}건" if len(rejected) > 5 else ""
        line4 = f"■ 반려 — {len(rejected)}건 · {detail}{tail}"
    else:
        line4 = "■ 반려 — 없음"

    summary = "\n".join([line1, line2, line3, line4])

    return make_payload(
        title="전사 업무·결재",
        summary_line=summary,
        metrics=[],
        honesty_tag="측정",
        link=_LINK,
    )


if __name__ == "__main__":
    print(json.dumps(collect(), ensure_ascii=False, indent=2))
