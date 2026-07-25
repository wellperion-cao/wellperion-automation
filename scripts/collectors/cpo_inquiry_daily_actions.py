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

_LINK = "https://wellperion-cao.github.io/wellperion-automation/cpo/member/membership.html"
# 강습은 같은 페이지의 다른 관리 그룹(?manage=lesson)으로 들어가야 한다 — 기본 링크는 멤버십으로 열려서
# 강습 미응대를 안내하면서 멤버십 화면을 띄우는 어긋남이 있었다(2026-07-23 GM 지적).
_LINK_LESSON = _LINK + "?manage=lesson"


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

    # 강습 미응대(흔적 0) — 2026-07-23 GM 지침. 건별 반복 알림은 혼란스러워 금지하고,
    # 하루 일과 정리에만 '최근 30일 누적' 한 줄로 모아 보여준다(같은 문의가 여러 번 안 튀게).
    # 이 칸이 없어서 강습 166건(2026-03~)이 아무 화면에도 안 잡히고 방치됐다.
    lesson_un = cpo_report.lesson_unassigned_summary(days=30)

    metrics = [
        {"label": "오늘 신규 문의", "value": len(today_new)},
        {"label": "미컨택(연락기록 0건)", "value": len(uncontacted)},
        {"label": "오늘 상담·체험 예약", "value": len(todays_res)},
        {"label": "이탈위험 후보(추정)", "value": len(churn_cands)},
        {"label": "강습 미응대 30일(담당자 미배정)",
         "value": lesson_un["total"] if lesson_un else "미측정"},
        # 숨은 재고를 지표에 드러낸다(2026-07-25 GM) — 30일이 지난 건은 그동안 어디에도
        # 안 나타나 2021년 문의까지 남아 있었다. 별도 목록을 만들지 않고 이 한 칸으로 밝힌다.
        {"label": "강습 미응대 전체(오래된 것 포함)",
         "value": lesson_un.get("total_all", "미측정") if lesson_un else "미측정"},
    ]
    summary = (
        f"신규 {len(today_new)}건 · 미컨택 {len(uncontacted)}건 · "
        f"오늘예약 {len(todays_res)}건 · 이탈위험(추정) {len(churn_cands)}건"
    )
    if lesson_un:
        bt = lesson_un.get("by_type") or {}
        detail = " / ".join(
            f"{k} {v}" for k, v in bt.items() if isinstance(v, int)
        )
        _all = lesson_un.get("total_all")
        if lesson_un["total"]:
            summary += f" · ⚠️ 강습 미응대 30일 {lesson_un['total']}건"
            if detail:
                summary += f"({detail})"
            if isinstance(_all, int) and _all > lesson_un["total"]:
                summary += f" · 전체 {_all}건"
            summary += f" → {_LINK_LESSON}"   # 강습 건은 강습 화면으로(멤버십 링크로 보내지 않는다)
        elif isinstance(_all, int) and _all:
            # 최근 30일은 0이어도 옛 재고가 남아 있으면 그대로 밝힌다(0건으로 끝내면 또 숨는다).
            summary += f" · 강습 미응대 30일 0건 · 전체 {_all}건 → {_LINK_LESSON}"
        else:
            summary += " · 강습 미응대 0건"
        # 오늘 처리할 몫만 조금씩 — 별도 목록 대신 가장 오래된 몇 건만 이름을 밝혀 손이 가게 한다.
        _old = lesson_un.get("oldest") or []
        if _old:
            _head = " / ".join(f"{o['date']} {o['name'] or '이름미상'}" for o in _old[:3])
            summary += f"\n  ▸ 오래된 순: {_head}"
    else:
        summary += " · 강습 미응대 미측정(조회 실패)"

    return make_payload(
        title="문의 라이프사이클 일일 액션",
        summary_line=summary,
        metrics=metrics,
        honesty_tag="부분",
        link=_LINK,
    )


if __name__ == "__main__":
    print(json.dumps(collect(), ensure_ascii=False, indent=2))
