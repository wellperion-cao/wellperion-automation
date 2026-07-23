# -*- coding: utf-8 -*-
"""
cmo_marketing_funnel.py — 모듈 cmo-marketing-funnel 수집기(공유 SSOT 정합).
─────────────────────────────────────────────────────────────────────────────
등록부(module_registry.json)의 모듈 id `cmo-marketing-funnel` → id 규약으로
이 모듈명(collectors.cmo_marketing_funnel)이 해소된다.

1차 소스 = 모듈의 **선언된 data_source(status/kpi_values.json)** 직독.
  kpi_values.json 은 kpi_collector.py 가 일 2회 자동 집계하는 roles.cmo 블록
  (채널별_문의전환)을 담는다 → funnel_conversion(byChannel) 실측치를 채널별로
  노출한다(2026-07-15 클릭 지수 제거·GM 결정 — 클릭 관련 필드는 더 이상 수집하지 않음).

정직 꼬리표: 채널별 문의·전환율 실측 = 측정 / roles.cmo 또는 채널별_문의전환 없음 = 미측정.
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

# 2026-07-09 웰리 확정: 마케팅 대시보드 = M1 페이지(#m1-dash)로 통합.
# 구 cmo/funnel/마케팅현황대시보드.html 링크(URL 인코딩)는 사이트 라우팅상
# 404 — 정본 M1 앵커로 교체 (2026-07-20 수리).
_LINK = "https://wellperion-cao.github.io/wellperion-automation/wellperion_guide(main).html#m1-dash"
_DEFAULT_REF = "status/kpi_values.json"


def _load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _resolve_ref(module):
    """모듈의 선언된 data_source.ref → 절대경로(없으면 기본 kpi_values.json)."""
    ref = None
    if isinstance(module, dict):
        ds = module.get("data_source") or {}
        ref = ds.get("ref")
    ref = ref or _DEFAULT_REF
    return ref if os.path.isabs(ref) else os.path.join(_PROJECT_ROOT, ref)


def collect(module=None) -> dict:
    """표준 payload 반환. roles.cmo 채널별_문의전환 실측치 그대로(funnel_conversion byChannel)."""
    data = _load_json(_resolve_ref(module))
    cmo = (data or {}).get("roles", {}).get("cmo") if isinstance(data, dict) else None
    if not isinstance(cmo, dict):
        return make_payload(
            title="마케팅 퍼널·채널 성과",
            summary_line="kpi_values.json roles.cmo 없음",
            metrics=[],
            honesty_tag="미측정",
            link=_LINK,
        )

    by_channel_conv = cmo.get("채널별_문의전환") or {}
    if not by_channel_conv:
        return make_payload(
            title="마케팅 퍼널·채널 성과",
            summary_line="roles.cmo.채널별_문의전환 없음",
            metrics=[],
            honesty_tag="미측정",
            link=_LINK,
        )

    metrics = []
    summary_bits = []
    for ch, conv in by_channel_conv.items():
        if not isinstance(conv, dict):
            continue
        inq = conv.get("문의")
        rate = conv.get("문의_가입_전환율")
        rate_s = f"{rate}%" if rate is not None else "미측정"
        metrics.append({"label": f"문의·{ch}", "value": inq if inq is not None else "미측정"})
        metrics.append({"label": f"문의→가입 전환율·{ch}", "value": rate_s})
        summary_bits.append(f"{ch} 문의{inq if inq is not None else '미측정'}·전환{rate_s}")

    summary = "채널별 문의→가입: " + ", ".join(summary_bits) if summary_bits else "미측정"

    return make_payload(
        title="마케팅 퍼널·채널 성과",
        summary_line=summary,
        metrics=metrics,
        honesty_tag="측정",
        link=_LINK,
    )


if __name__ == "__main__":
    print(json.dumps(collect(), ensure_ascii=False, indent=2))
