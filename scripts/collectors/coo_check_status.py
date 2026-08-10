# -*- coding: utf-8 -*-
"""
coo_check_status.py — 모듈 coo-check-status 수집기(공유 SSOT 정합).
─────────────────────────────────────────────────────────────────────────────
등록부(module_registry.json)의 모듈 id `coo-check-status` → id 규약으로
이 모듈명(collectors.coo_check_status)이 해소된다.

[2026-07-22 GM 지시 — 방4(자동화현황방) collector_missing 정리] 새 로직을 만들지
않는다 — scripts/coo_registry.py 의 기존 fetch_check_status() 를 그대로 재사용한다.
이 함수는 이미 08시 통합보고(coo_report_line.build_coo_daily_lines →
ceo_morning_pipeline.py)에서 쓰이는 실측 로직이다. module_reporter 경로로도 흘려
등록부에 이미 선언된 bot_id="자동화현황방"(방4)에 실제로 닿게 한다(기존엔 collector
가 없어 매일 스킵됐다).

정직 꼬리표: fetch_check_status() 는 항상 tag="measured"(실측) → '측정'.
조회 자체가 예외를 던지면(GAS 응답 실패 등) '미측정'.

[2026-08-10 GM 지시 — 보고 문구 개선] summary_line을 cpo_member_rollup.py와 동일한
"■ 소제목" 다줄 형식으로 재조립(집계 로직·판정 기준은 그대로 coo_registry.fetch_check_status()
재사용 — 새 수집 로직 금지). 영문 키(facility_pct 등) 노출 제거, 분모·분자 병기, 이상 항목
상위 3개를 이름으로 노출. metrics는 비움(모듈 리포터의 "· label: value" 나열이 다줄 요약과
안 맞음 — cpo_member_rollup.py와 동일 근거).

지원 0%는 "수집 끊김"이 아니다 — fetch_check_status()가 예외를 던지면 이 파일의 except
분기가 별도로 "조회 실패"(미측정)를 반환하므로, tag="측정"으로 0%가 나온다는 것 자체가
GAS 응답이 정상 도착했고 그 안의 done/total 값이 진짜 0이라는 뜻이다(2026-08-10 실측
확인 — support today_live는 이른 아침 시간대엔 실제로 0%였다가 낮 동안 점검이 쌓이며
오른다. GAS는 302 리다이렉트 응답이라 curl -L 없이 조회하면 빈 응답으로 착각하기 쉬우니
직접 조회 시 -L을 꼭 붙일 것 — urllib.request는 기본으로 302를 따라가 정상 동작한다).
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
import coo_registry  # noqa: E402 — fetch_check_status() 재사용(중복 복사 금지)

_LINK = "https://wellperion-cao.github.io/wellperion-automation/wellperion_guide(main).html#O1"

_DEPT_LABEL = {"facility": "시설", "support": "지원"}


def _dept_line(dept_key: str, d: dict) -> str:
    """분모·분자 병기. total=0(대상 없음)과 pct 산출 불가를 서로 다른 문구로 정직 표기."""
    label = _DEPT_LABEL.get(dept_key, dept_key)
    if not d:
        return f"{label} 측정 안 됨"
    total = d.get("total") or 0
    done = d.get("done") or 0
    pct = d.get("pct")
    if total == 0:
        return f"{label} 0%(0/0건 — 수집 정상·오늘 대상 없음)"
    if pct is None:
        return f"{label} 산출 불가({done}/{total}건)"
    return f"{label} {pct}%({done}/{total}건)"


def _translate_reason(r: str) -> str:
    """reasons 항목의 영문 dept 접두("facility: …")를 사람 말 라벨로 치환."""
    for en, ko in _DEPT_LABEL.items():
        if r.startswith(en + ":") or r.startswith(en + " "):
            return ko + r[len(en):]
    return r


def collect(module=None) -> dict:
    """표준 payload 반환. coo_registry.fetch_check_status() 실측 그대로 감싼다.
    summary_line은 ■ 소제목 다줄 형식(cpo_member_rollup.py 패턴 재사용)."""
    try:
        st = coo_registry.fetch_check_status()
    except Exception as e:
        return make_payload(
            title="점검 현황",
            summary_line=f"조회 실패({type(e).__name__})",
            metrics=[],
            honesty_tag="미측정",
            link=_LINK,
        )

    depts = st.get("depts") or {}
    line1 = "■ 이번 주 점검 — " + " · ".join(
        _dept_line(k, depts.get(k)) for k in _DEPT_LABEL
    )

    reasons = [_translate_reason(r) for r in (st.get("reasons") or [])]
    if reasons:
        shown = reasons[:3]
        tail = f" 외 {len(reasons) - 3}건" if len(reasons) > 3 else ""
        line2 = "■ 이상·미완 — " + " · ".join(shown) + tail
    else:
        line2 = "■ 이상·미완 — 없음"

    summary = "\n".join([line1, line2])

    return make_payload(
        title="점검 현황",
        summary_line=summary,
        metrics=[],
        honesty_tag="측정",
        link=_LINK,
    )


def _selftest():
    """분기 검증(그물 없는 assert) — 네트워크 없이 _dept_line/_translate_reason만 확인."""
    assert _dept_line("facility", {"total": 0, "done": 0, "pct": None}) == \
        "시설 0%(0/0건 — 수집 정상·오늘 대상 없음)"
    assert _dept_line("facility", {"total": 10, "done": 5, "pct": 50}) == "시설 50%(5/10건)"
    assert _dept_line("facility", {"total": 10, "done": 5, "pct": None}) == "시설 산출 불가(5/10건)"
    assert _dept_line("support", None) == "지원 측정 안 됨"
    assert _translate_reason("facility: 창문 파손") == "시설: 창문 파손"


if __name__ == "__main__":
    _selftest()
    print(json.dumps(collect(), ensure_ascii=False, indent=2))
