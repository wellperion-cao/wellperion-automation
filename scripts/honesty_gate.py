#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""정직 게이트 — 카톡·텔레그램 등 GM 발신 채널의 비실측 수치 표기 단일 모듈 (scripts/honesty_gate.py)

GM 2026-07-24 지시 2단계: "요즘 데이터가 정확하지 않아서 카톡 방에 막 공지하기가 좀 그렇네."
1단계(status/monthly_ops_plan.json 의 objective.honesty.level 4종 딱지)는 끝났다.
2단계 = 그 딱지를 실제 "발신"(카톡·텔레그램) 지점에서 강제 적용하는 게이트.

★게이트는 이 한 곳에만 둔다(약속 L01 — 흩어서 만들면 그게 새 구멍이 된다). 발신 지점은
반드시 이 모듈을 import 해서 쓴다. 여기 없는 판정 로직을 발신 스크립트에 새로 만들지 말 것.

── honesty.level 4종 (status/monthly_ops_plan.json 의 objective.honesty.level 과 동일 정의.
   scripts/monthly_ops_sync.py:honesty_from_verdict() 가 이 4종을 매긴다) ──
  · measured   (✅ 실측)    — 라이브 소스(metric_live 등)에서 실제 값을 읽어옴. 숫자를 그대로 믿을 수 있다.
  · observed   (👀 상태만)  — 상태(진행중 N건 등)는 기계가 실제로 관찰했지만, 그 상태를 %/진척률로
                               환산한 숫자는 사람이 넣은 값이다. "상태 자체"는 사실이라 그대로 내보내되,
                               환산 숫자(progress %)는 검증되지 않았다는 점만 유의.
  · manual     (📝 사람값)  — 연결된 실측 소스가 없어 사람이 손으로 써넣은 값(진척률 등).
  · unmeasured (🔧 측정실패) — 실측 소스는 있는데 조회 실패·연결 대상 없음(verdict 미연동).

── 발신 정책 (엄수) ──
  1) 기본(policy="stamp") = "막지 않고 정직하게 표기"가 원칙. 비실측(manual/unmeasured) 수치는
     [미측정] 딱지를 붙여 그대로 내보낸다. 완전 숨김은 그 자체로 또 다른 거짓말(빈칸=문제없음 오독).
  2) 강한 차단(policy="measured_only") = 호출측이 명시적으로 요청할 때만. 비실측 '숫자'가 하나라도
     있으면 발신 자체를 보류(hold)한다. 실무진 다수가 보는 방(카톡 등) 같은 민감 채널에서 사용.
  3) 상태(state)·건수(count)는 게이트 대상이 아니다 — 기계가 실제로 센 사실이므로 그대로 내보낸다
     (예: "진행중 3건·완료 2건"). 게이트가 막는 건 검증 안 된 진척률·달성% 같은 '숫자'뿐이다.
     observed 는 그래서 stamp 없이 통과(딱지는 manual/unmeasured 에만).
"""
from __future__ import annotations

# level → (배지, 딱지 부착 여부) — 이 표 하나가 전체 판정의 단일 소스(추가 level 생기면 여기만 수정).
_LEVEL_TABLE = {
    "measured": {"badge": "✅", "stamped": False},
    "observed": {"badge": "👀", "stamped": False},  # 상태는 사실 → 통과(딱지 없음)
    "manual": {"badge": "📝", "stamped": True},
    "unmeasured": {"badge": "🔧", "stamped": True},
}
_UNKNOWN_BADGE = "❓"  # honesty.level 이 4종에 없거나 비어있을 때 — 안전 기본값(비실측 취급)
_STAMP = "[미측정]"

# summary_line 표기 라벨(GM 지정 포맷 — 배지·라벨 사이 공백 없음, "🔎 이 보고: ..." 한 줄용)
_SUMMARY_LABEL = {
    "measured": "실측",
    "observed": "상태만",
    "manual": "사람값",
    "unmeasured": "측정실패",
}
_SUMMARY_ORDER = ["measured", "observed", "manual", "unmeasured"]


def verdict(level: str) -> dict:
    """한 항목(objective 등)의 honesty.level 하나를 판정.

    반환 {"broadcast": True/False, "badge": "✅"/"👀"/"📝"/"🔧", "stamp": "" or "[미측정]"}
      - measured → broadcast True, stamp ""(그대로 나감)
      - observed → broadcast True, badge 👀, stamp ""(상태는 사실이므로 통과)
      - manual/unmeasured → broadcast True(기본 정책), stamp "[미측정]"(숫자에 딱지 붙여 내보냄)
      - level 이 4종에 없거나 빈 값 → 안전 기본값으로 비실측 취급(딱지 부착, 배지 ❓)
    """
    entry = _LEVEL_TABLE.get(level)
    if entry is None:
        return {"broadcast": True, "badge": _UNKNOWN_BADGE, "stamp": _STAMP}
    return {
        "broadcast": True,
        "badge": entry["badge"],
        "stamp": _STAMP if entry["stamped"] else "",
    }


def _extract_level(item: dict) -> str:
    """item 이 {"level": ...} 단순형이든 objective 원본({"honesty": {"level": ...}, ...})이든
    둘 다 받아 level 문자열을 뽑아낸다(호출측이 원본 객체를 그대로 넘겨도 되게 하는 편의)."""
    if not isinstance(item, dict):
        return ""
    if "level" in item:
        return str(item.get("level") or "")
    honesty = item.get("honesty")
    if isinstance(honesty, dict):
        return str(honesty.get("level") or "")
    return ""


def summary_line(items: list[dict]) -> str:
    """메시지 전체를 스캔해 비실측 항목 요약 한 줄 생성(발신 카드 하단에 붙임).

    items = [{"level": "measured"}, ...] 또는 objective 원본 리스트(honesty 하위 포함) 모두 허용.
    예: "🔎 이 보고: ✅실측 1 · 👀상태만 12 · 📝사람값 9 · 🔧측정실패 0 — [미측정] 표기값은 검토 필요"
    """
    counts = {k: 0 for k in _SUMMARY_ORDER}
    unknown = 0
    for it in items or []:
        lv = _extract_level(it)
        if lv in counts:
            counts[lv] += 1
        else:
            unknown += 1
    parts = [f"{_LEVEL_TABLE[k]['badge']}{_SUMMARY_LABEL[k]} {counts[k]}" for k in _SUMMARY_ORDER]
    if unknown:
        parts.append(f"{_UNKNOWN_BADGE}미분류 {unknown}")
    return f"🔎 이 보고: {' · '.join(parts)} — {_STAMP} 표기값은 검토 필요"


def should_hold(items: list[dict], policy: str = "stamp") -> tuple[bool, str]:
    """강한 차단이 필요할 때(옵션)의 판정. 기본(stamp)은 절대 막지 않는다(발신 정책 1).

    policy="stamp"(기본) → (False, "") : 막지 않음 — 각 항목은 verdict() 딱지로 내보냄.
    policy="measured_only" → 비실측(manual/unmeasured, 검증 안 된 '숫자')이 하나라도 있으면
      (True, "사유") : 발신 보류. observed(상태 사실)는 차단 사유에서 제외(발신 정책 3).
    """
    if policy != "measured_only":
        return False, ""
    bad = [it for it in (items or []) if _extract_level(it) in ("manual", "unmeasured")]
    if not bad:
        return False, ""
    return True, f"비실측(사람값/측정실패) 수치 {len(bad)}건 포함 — measured_only 정책으로 발신 보류"
