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


def _loss_not_stamped(today: str) -> list:
    """종료일이 이틀 넘게 지났는데 LOSS일자가 아직 빈칸인 종료회원 목록.

    왜 이틀이냐: 자동 도장은 '잔여일이 음수'가 된 뒤에 찍는다. 종료 당일은 잔여일 0
    (만료일까지 유효)이라 대상이 아니고, 그 다음 날 밤 23시에 종료일+1 로 찍힌다.
    그래서 하루 비어 있는 것은 정상이고, 이틀이 넘게 비어 있으면 도장이 안 돈 것이다.

    2026-09-11: 위 _loss_stamped_before_report 는 '너무 일찍 찍힌 것'만 센다 —
    화면·사람 경유 쓰기만 이력에 남기 때문이다. 밤 도장이 아예 멈추면 이력에 아무
    기록도 안 남아 그 감시기는 영원히 0건을 낸다. 안 찍힌 쪽은 여기서 센다.

    원천 = status/member_ended_snapshot.json (cpo_inquiry_snapshot.py 가 3분마다 갱신).
    """
    from datetime import datetime as _dt, timedelta as _td   # noqa: PLC0415
    snap = os.path.join(_PROJECT_ROOT, "status", "member_ended_snapshot.json")
    try:
        with open(snap, encoding="utf-8") as fh:
            rows = (json.load(fh) or {}).get("rows") or []
    except Exception:
        return []
    try:
        cutoff = (_dt.strptime(today, "%Y-%m-%d") - _td(days=2)).strftime("%Y-%m-%d")
    except Exception:
        return []

    def _cell(row, want):
        for k, v in row.items():
            if want in str(k).replace(" ", "").replace(chr(10), ""):
                return str(v or "").strip()
        return ""

    hits = []
    for r in rows:
        if not isinstance(r, dict) or not _cell(r, "회원명"):
            continue
        end = _cell(r, "종료일자").replace(".", "-")
        if not end or _cell(r, "LOSS일자"):
            continue
        if end <= cutoff:
            hits.append({"회원": _cell(r, "회원명"), "종료일자": end})
    return hits


def _loss_stamped_before_report(today: str) -> list:
    """오늘 09:30 보고 전에 LOSS일자가 찍힌 기록을 돌려준다(없으면 빈 목록).

    GM 확정(2026-09-02 · 2026-09-10 재확인): LOSS일자는 **밤 23시에만** 찍는다.
    09:30 에 회장님·부서장 방으로 매출보고가 나가는데 그 전에 찍히면 보고에 실린
    회원수와 시트 회원수가 갈린다. 기록하는 자리는 앱스스크립트 밤 도장 한 곳뿐이고,
    그 도장은 회원 변경 이력을 남기지 않는다 — 그래서 **이력에 걸리는 LOSS일자 기록은
    전부 화면·사람 경유 쓰기**이고, 그중 09:30 이전 것이 규칙 위반이다.

    2026-09-10 실사고: 멤버십 「종료」 탭이 열릴 때마다 빈 LOSS일자를 스스로 채워
    저장하고 있었다(09:12 강창구 건). 그 저장 경로는 없앴지만, 다른 경로로 같은 일이
    다시 생기는 것을 사람이 눈으로 잡을 수는 없다 — 그래서 매일 여기서 센다.
    """
    data = cpo_report._gas_get("member_log_list")
    if not data or not isinstance(data.get("data"), list):
        return []
    from datetime import datetime as _dt, timedelta as _td   # noqa: PLC0415
    hits = []
    for r in data["data"]:
        if "LOSS" not in str(r.get("field") or ""):
            continue
        try:   # 이력의 at 은 UTC — 한국 시각으로 옮겨 본다
            kst = _dt.strptime(str(r.get("at"))[:19], "%Y-%m-%dT%H:%M:%S") + _td(hours=9)
        except Exception:
            continue
        if kst.strftime("%Y-%m-%d") != today or (kst.hour, kst.minute) >= (9, 30):
            continue
        hits.append({"시각": kst.strftime("%H:%M"), "회원": r.get("member"),
                     "계정": r.get("staff"), "화면": r.get("screen")})
    return hits


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

    # 보고(09:30) 전에 LOSS일자가 찍혔는지 — 찍혔으면 그날 보고 회원수가 시트와 갈린다.
    loss_early = _loss_stamped_before_report(today)
    # 반대쪽 — 밤 23시 도장이 멈춰 아예 안 찍힌 것(이력에 안 남아 위 감시기는 못 본다).
    loss_missing = _loss_not_stamped(today)

    metrics = [
        {"label": "보고 전(09:30) LOSS일자 기재", "value": len(loss_early)},
        {"label": "LOSS일자 안 찍힘(종료 이틀 지남)", "value": len(loss_missing)},
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
    summary = ""
    if loss_missing:
        who_m = " · ".join(f"{h['회원']}(종료 {h['종료일자']})" for h in loss_missing[:3])
        summary += (
            f"🚨 LOSS일자 안 찍힘 {len(loss_missing)}건 — {who_m}"
            + (" 외" if len(loss_missing) > 3 else "")
            + " · 밤 23시 자동 도장이 멈춘 것으로 본다 · "
        )
    if loss_early:
        who = " · ".join(
            f"{h['시각']} {h['회원']}({h['계정']})" for h in loss_early[:3]
        )
        summary += (
            f"🚨 보고 전 LOSS일자 기재 {len(loss_early)}건 — {who}"
            + (" 외" if len(loss_early) > 3 else "")
            + " · 로스일자는 밤 23시에만 찍는다(GM 확정) · "
        )
    summary += (
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
