#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
scripts/welly_sweep_classifier.py — 자율 웰리 스윕 순수 분류 엔진 (2026-06-26)

부작용 0 · 순수 함수. unit 테스트 타깃.

계획: .omc/plans/autonomous-welly-loop.md §4 (first-match-wins 판정 파이프라인)
명세: .omc/specs/deep-interview-autonomous-welly-loop.md

입력:
  - item: fetch_queue_items() 정규화 dict (source·owner·terminal·next·status·title·_raw_summary 보유)
            + 기계적 분류용 보조키(_dup·_ship_conflict, welly_sweep이 원시 _queue.json에서 계산해 주입)
  - drift_ids: hangro_board._classify(fetch_gas_items()+fetch_queue_items())["drift"]에서 산출한 id 집합
            (부분 술어 재구현 금지 — §0.1 원칙4)

출력:
  - Verdict(verdict, reason, evidence)
      verdict ∈ {AUTO_EXEC, GM_GATE, GM_INTERVIEW, HOLD}

판정 파이프라인(순서 고정 · 먼저 매칭이 이김):
  0) 결재영역 키워드 게이트(하드 차단·최우선) → GM_GATE
  1) 빈/모호 next → GM_INTERVIEW (빈 next 채움은 자율 안 함)
  2) 비가역·외부영향 키워드 → HOLD
  3) 기계적(dedup·ship_no 충돌) → AUTO_EXEC
  4) 그 외 → GM_INTERVIEW (안전측 기본)
"""
from __future__ import annotations

from dataclasses import dataclass, field

# ── 결재영역 5종 게이트 키워드 (계획 §4 step0 · 영구 자율 금지) ──────────────
#   결제·보안 발효·공식값·전략·콘텐츠 발행. first-match-wins 최우선 하드 차단.
GATE_KEYWORDS: tuple[str, ...] = (
    # 결제
    "결제", "페이", "정산", "환불", "결재",
    # 보안 발효
    "보안", "차단", "발효", "jwt", "token_enforce",
    # 공식값
    "공식값", "공식 링크", "공식링크", "대표 전화", "대표전화",
    # 콘텐츠 발행
    "발행", "publish", "게시", "업로드", "라이브",
    # 전략 / C-Level 자기영역
    "전략", "북극성", "8차원",
)

# ── 비가역·외부영향 키워드 (계획 §4 step2 · 자율 금지·HOLD) ───────────────────
IRREVERSIBLE_KEYWORDS: tuple[str, ...] = (
    "삭제", "delete", "drop", "외부", "발송", "전송",
    "라이브 반영", "배포", "deploy",
)

# ── 빈/모호 next 토큰 (계획 §4 step1 · GM_INTERVIEW) ─────────────────────────
AMBIGUOUS_NEXT_TOKENS: tuple[str, ...] = (
    "미정", "?", "검토 필요", "검토필요", "tbd", "확인 필요", "확인필요",
)

VERDICT_AUTO_EXEC = "AUTO_EXEC"
VERDICT_GM_GATE = "GM_GATE"
VERDICT_GM_INTERVIEW = "GM_INTERVIEW"
VERDICT_HOLD = "HOLD"


@dataclass
class Verdict:
    verdict: str
    reason: str
    evidence: dict = field(default_factory=dict)


def _scan_keywords(text: str, keywords: tuple[str, ...]) -> str | None:
    """text(소문자화 매칭)에서 첫 적중 키워드 반환. 없으면 None."""
    if not text:
        return None
    low = text.lower()
    for kw in keywords:
        if kw.lower() in low:
            return kw
    return None


def _gate_text(item: dict) -> str:
    """게이트/비가역 키워드 스캔 대상 본문 = title + note(_raw_summary) + next."""
    parts = [
        str(item.get("title", "") or ""),
        str(item.get("_raw_summary", "") or item.get("note", "") or ""),
        str(item.get("next", "") or ""),
    ]
    return " ".join(parts)


def classify(item: dict, drift_ids: set[str] | None = None) -> Verdict:
    """미션 1건 → Verdict. 순수 함수(부작용 0).

    item 보조키(welly_sweep이 원시 _queue.json에서 계산·주입):
      - _dup: bool          # 완전중복(같은 task_id/정규화 title) 후보
      - _ship_conflict: bool # 같은 clevel 내 ship_no 충돌
    drift_ids: 표류 id 집합(hangro_board._classify 산출). 분류엔 직접 안 쓰나 evidence로 기록.
    """
    drift_ids = drift_ids or set()
    iid = str(item.get("id", "") or "")
    scan_text = _gate_text(item)

    # 0) 결재영역 키워드 게이트 — 최우선 하드 차단.
    hit = _scan_keywords(scan_text, GATE_KEYWORDS)
    if hit:
        return Verdict(
            VERDICT_GM_GATE,
            f"결재영역 키워드 적중('{hit}') — 영구 자율 금지",
            {"id": iid, "keyword": hit},
        )

    # 1) 빈/모호 next → GM_INTERVIEW (빈 next 채움은 자율 안 함 · first-match-wins).
    nxt = str(item.get("next", "") or "").strip()
    if not nxt:
        return Verdict(
            VERDICT_GM_INTERVIEW,
            "next(다음작업) 비어있음 — 근거 지어내기 금지, GM/담당 C레벨 위임",
            {"id": iid, "next": ""},
        )
    amb = _scan_keywords(nxt, AMBIGUOUS_NEXT_TOKENS)
    if amb:
        return Verdict(
            VERDICT_GM_INTERVIEW,
            f"next 모호('{amb}') — GM 질의",
            {"id": iid, "next": nxt, "token": amb},
        )

    # 2) 비가역·외부영향 → HOLD (게이트 아님 확인 후).
    irr = _scan_keywords(scan_text, IRREVERSIBLE_KEYWORDS)
    if irr:
        return Verdict(
            VERDICT_HOLD,
            f"비가역·외부영향 키워드('{irr}') — GM 통보 후 대기",
            {"id": iid, "keyword": irr},
        )

    # 3) 기계적 작업(ON-A 자율 2종) → AUTO_EXEC.
    if item.get("_dup"):
        return Verdict(
            VERDICT_AUTO_EXEC,
            "완전중복 항목 — 기계적 dedup 후보",
            {"id": iid, "kind": "dedup", "drift": iid in drift_ids},
        )
    if item.get("_ship_conflict"):
        return Verdict(
            VERDICT_AUTO_EXEC,
            "같은 clevel 내 ship_no 충돌 — 기계적 정정 후보",
            {"id": iid, "kind": "ship_no", "ship_no": item.get("ship_no"),
             "drift": iid in drift_ids},
        )

    # 4) 그 외 → GM_INTERVIEW (안전측 기본).
    return Verdict(
        VERDICT_GM_INTERVIEW,
        "기계적 자율집합(dedup·ship_no) 아님 — 안전측 GM 질의 기본",
        {"id": iid, "drift": iid in drift_ids},
    )
