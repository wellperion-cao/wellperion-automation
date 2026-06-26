#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
test_welly_sweep_classifier.py — 분류 엔진 unit 테스트 (게이트 우회 0 전수)

stdlib only (pytest 불요). 직접 실행:
  python scripts/test_welly_sweep_classifier.py
"""
import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

import welly_sweep_classifier as wsc  # noqa: E402

_fail = 0
_pass = 0


def check(cond, msg):
    global _fail, _pass
    if cond:
        _pass += 1
    else:
        _fail += 1
        print(f"  [FAIL] {msg}")


def item(**kw):
    base = {"id": "T-1", "title": "", "next": "다음 단계 설명", "_dup": False,
            "_ship_conflict": False, "_raw_summary": "근거 메모"}
    base.update(kw)
    return base


def test_gate_keywords_never_auto_exec():
    """결재영역 5종 키워드 → 항상 GM_GATE (게이트 우회 0)."""
    cases = [
        "결제 정산 처리", "환불 요청 검토", "보안 차단 발효", "JWT 토큰 적용",
        "TOKEN_ENFORCE 켜기", "공식값 업데이트", "공식 링크 교체", "대표 전화 변경",
        "블로그 발행", "인스타 publish", "카페 게시", "이미지 업로드", "라이브 반영",
        "전략 수립", "북극성 재정의", "8차원 확장",
    ]
    for title in cases:
        # 게이트 키워드가 있으면, 심지어 기계적 dedup 후보여도 절대 AUTO_EXEC 아님.
        v = wsc.classify(item(title=title, _dup=True, _ship_conflict=True), set())
        check(v.verdict == wsc.VERDICT_GM_GATE,
              f"게이트 키워드 '{title}' → {v.verdict} (GM_GATE 기대)")
        check(v.verdict != wsc.VERDICT_AUTO_EXEC,
              f"게이트 키워드 '{title}' 가 AUTO_EXEC 로 샘! (게이트 우회)")


def test_empty_next_goes_interview():
    """빈/모호 next → GM_INTERVIEW. dedup 후보여도 AUTO_EXEC 아님(first-match-wins)."""
    for nxt in ["", "   ", "미정", "?", "검토 필요", "TBD"]:
        v = wsc.classify(item(next=nxt, _dup=True), set())
        check(v.verdict == wsc.VERDICT_GM_INTERVIEW,
              f"빈/모호 next '{nxt}' → {v.verdict} (GM_INTERVIEW 기대)")
        check(v.verdict != wsc.VERDICT_AUTO_EXEC,
              f"빈 next '{nxt}' 가 AUTO_EXEC 로 샘!")


def test_irreversible_goes_hold():
    """비가역·외부영향 키워드(게이트 아님) → HOLD."""
    for kw in ["항목 삭제 정리", "외부 전송 작업", "drop 처리", "배포 deploy"]:
        v = wsc.classify(item(title=kw), set())
        check(v.verdict == wsc.VERDICT_HOLD,
              f"비가역 '{kw}' → {v.verdict} (HOLD 기대)")


def test_mechanical_goes_auto_exec():
    """기계적 건(dedup·ship_no) — 게이트/모호/비가역 아님 → AUTO_EXEC."""
    v1 = wsc.classify(item(title="중복 배 정리", _dup=True), set())
    check(v1.verdict == wsc.VERDICT_AUTO_EXEC, f"dedup → {v1.verdict} (AUTO_EXEC 기대)")
    v2 = wsc.classify(item(title="배번호 정합", _ship_conflict=True, ship_no=14), set())
    check(v2.verdict == wsc.VERDICT_AUTO_EXEC, f"ship_no → {v2.verdict} (AUTO_EXEC 기대)")


def test_boundary_gate_beats_irreversible():
    """경계: 게이트+비가역 동시 → 게이트 우선(GM_GATE)."""
    v = wsc.classify(item(title="발행 콘텐츠 삭제"), set())
    check(v.verdict == wsc.VERDICT_GM_GATE,
          f"게이트+비가역 → {v.verdict} (GM_GATE 우선 기대)")


def test_default_interview():
    """기계적 아님 + 정상 next → 안전측 GM_INTERVIEW."""
    v = wsc.classify(item(title="평범한 내부 정리 작업"), set())
    check(v.verdict == wsc.VERDICT_GM_INTERVIEW,
          f"기본 → {v.verdict} (GM_INTERVIEW 기대)")


def main():
    for fn in [test_gate_keywords_never_auto_exec, test_empty_next_goes_interview,
               test_irreversible_goes_hold, test_mechanical_goes_auto_exec,
               test_boundary_gate_beats_irreversible, test_default_interview]:
        print(f"[RUN] {fn.__name__}")
        fn()
    print(f"\n결과: {_pass} passed, {_fail} failed")
    sys.exit(1 if _fail else 0)


if __name__ == "__main__":
    main()
