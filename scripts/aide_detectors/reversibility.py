# -*- coding: utf-8 -*-
"""가역성 라우터 (US-002).

route(gap): (revert_ok ∧ ¬external ∧ ¬data_loss) → 'auto', 아니면/불명(None) → 'propose'.
보수 폴백 — 3부울 중 하나라도 True 아님/False 아님/누락이면 제안으로.
"""
from __future__ import annotations


def route(gap: dict) -> str:
    """정확히 revert_ok=True · external=False · data_loss=False 일 때만 'auto'.
    그 외(누락·None·불명 포함)는 보수적으로 'propose'."""
    if (gap.get("revert_ok") is True
            and gap.get("external") is False
            and gap.get("data_loss") is False):
        return "auto"
    return "propose"


def split_lanes(gaps: list) -> tuple:
    """배237(b) 반반 구성 라우팅 (GM 결정 2026-07-08):
      - kind=='resumable' & route=='auto' → 재개가능 auto 레인(태그+nudge+의존해소, 게이트 뒤 라이브).
      - kind=='stalled'                    → surface-only(자율 write 0·제안 배도 안 만듦, 보드 정보 표시만).
      - 그 외(불명·비가역 resumable)        → propose(제안 배 폴백).
    반환: (resumable_auto, stall_surface, propose). 정체는 auto·propose 어디에도 안 들어감(하드 분리)."""
    resumable_auto, stall_surface, propose = [], [], []
    for g in gaps:
        if g.get("kind") == "stalled":
            stall_surface.append(g)          # surface-only — 개별 배 mutation 절대 금지
        elif g.get("kind") == "resumable" and route(g) == "auto":
            resumable_auto.append(g)
        else:
            propose.append(g)
    return resumable_auto, stall_surface, propose
