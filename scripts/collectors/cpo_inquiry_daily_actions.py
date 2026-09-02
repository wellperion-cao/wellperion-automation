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

    # 강습 진행상태 빈칸 — GM 지시 2026-09-02. 담당이 붙어 있어도 상태 칸이 비면 컨택했는지
    # 안 했는지 아무도 모르고, 위 미응대 집계에도 안 잡힌다(실측 324건 = 강습 문의의 18%).
    lesson_blank = cpo_report.lesson_status_blank_summary(days=60)

    # 등록(SUC)됐는데 회원 명단에 안 들어간 건 — 2026-08-10 GM 지적으로 여기로 옮겨 왔다.
    # 종전엔 GAS가 등록 전환 순간 즉시 알렸는데, 등록 저장이 두 단계라 정상 흐름마다 울렸다.
    # 하루 지나도 안 들어간 것만 여기서 한 줄로 모아 본다(건별 알림 없음).
    suc_missing = cpo_report.suc_missing_from_member_list(rows)

    metrics = [
        {"label": "오늘 신규 문의", "value": len(today_new)},
        {"label": "미컨택(연락기록 0건)", "value": len(uncontacted)},
        {"label": "오늘 상담·체험 예약", "value": len(todays_res)},
        {"label": "LOSS 예방 대상(추정)", "value": len(churn_cands)},
        {"label": "강습 미응대 30일(담당자 미배정)",
         "value": lesson_un["total"] if lesson_un else "미측정"},
        # 숨은 재고를 지표에 드러낸다(2026-07-25 GM) — 30일이 지난 건은 그동안 어디에도
        # 안 나타나 2021년 문의까지 남아 있었다. 별도 목록을 만들지 않고 이 한 칸으로 밝힌다.
        {"label": "강습 미응대 전체(오래된 것 포함)",
         "value": lesson_un.get("total_all", "미측정") if lesson_un else "미측정"},
        {"label": "등록됐는데 회원 명단에 없음(하루 지난 것)",
         "value": suc_missing["total"] if suc_missing else "미측정"},
        # 컨택 여부를 아무도 모르는 자리. 최근분(60일)을 앞에 두는 이유 = 실무진이 기억하는
        # 건이라야 답이 온다. 전체는 숨지 않게 아래 요약 줄에 함께 적는다.
        {"label": "강습 진행상태 빈칸(최근 60일)",
         "value": lesson_blank["recent"] if lesson_blank else "미측정"},
    ]
    summary = (
        f"신규 {len(today_new)}건 · 미컨택 {len(uncontacted)}건 · "
        f"오늘예약 {len(todays_res)}건 · LOSS 예방 대상(추정) {len(churn_cands)}건"
        + (" · 👉 후속 연락 필요" if churn_cands else "")
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
                # 우리 몫과 외부 응대분(뮤지컬)을 갈라 밝힌다 — 합쳐 두면 우리가 연락해야 할
                # 건이 몇 건인지 알 수 없다(2026-07-25 GM: 외부 응대분도 우리가 머금고 본다).
                _ext = lesson_un.get("total_external") or 0
                summary += f" · 전체 {_all}건"
                if _ext:
                    summary += f"(우리 {lesson_un.get('total_ours', _all - _ext)} · 뮤지컬 외부응대 {_ext})"
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

    if lesson_blank is None:
        summary += " · 강습 진행상태 빈칸 미측정(조회 실패)"
    elif lesson_blank["total"]:
        # 최근분을 앞에 둔다 — 오늘 손이 갈 수 있는 건은 그것뿐이다. 누적은 숨기지 않되
        # 뒤로 보낸다(2021년부터 쌓인 값이라 앞에 두면 숫자에 무감각해진다).
        summary += (f" · 강습 진행상태 빈칸 최근 60일 {lesson_blank['recent']}명"
                    f"(누적 {lesson_blank['total']}명 · 그중 컨택 기록도 없음 {lesson_blank['no_trace']}명)")
        _rc = lesson_blank.get("recent_list") or []
        if _rc:
            _head = " / ".join(f"{o['date']} {o['name'] or '이름미상'}" for o in _rc[:3])
            summary += f"\n  ▸ 최근 순: {_head} → {_LINK_LESSON}"

    if suc_missing is None:
        summary += " · 등록·명단 대조 미측정(조회 실패)"
    elif suc_missing["total"]:
        _head = " / ".join(f"{o['name']}({o['date'][:10]})" for o in suc_missing["oldest"])
        summary += (f" · ⚠️ 등록됐는데 회원 명단에 없음 {suc_missing['total']}명"
                    f" — 오래된 순: {_head} → {_LINK}")

    return make_payload(
        title="문의 라이프사이클 일일 액션",
        summary_line=summary,
        metrics=metrics,
        honesty_tag="부분",
        link=_LINK,
    )


if __name__ == "__main__":
    print(json.dumps(collect(), ensure_ascii=False, indent=2))
