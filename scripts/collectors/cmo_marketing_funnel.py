# -*- coding: utf-8 -*-
"""
cmo_marketing_funnel.py — 모듈 cmo-marketing-funnel 수집기(공유 SSOT 정합).
─────────────────────────────────────────────────────────────────────────────
등록부(module_registry.json)의 모듈 id `cmo-marketing-funnel` → id 규약으로
이 모듈명(collectors.cmo_marketing_funnel)이 해소된다.

1차 소스 = 모듈의 **선언된 data_source(status/kpi_values.json)** 직독.
  kpi_values.json 은 kpi_collector.py 가 일 2회 자동 집계하는 roles.cmo 블록
  (채널별_클릭수·총_클릭수·채널별_클릭문의전환)을 담는다 → 실측치는 '측정',
  measurable=false 채널(네이버/당근/카카오 — 추적밖유입우세)은 있는 그대로
  노출하고 전체 꼬리표는 '부분'(일부 채널 미측정) — 거짓 %로 채우지 않는다.

정직 꼬리표: 실측+일부 미측정 혼재 = 부분 / roles.cmo 없음 = 미측정.
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

_LINK = "https://wellperion-cao.github.io/wellperion-automation/cmo/funnel/%EB%A7%88%EC%BC%80%ED%8C%85%ED%98%84%ED%99%A9%EB%8C%80%EC%8B%9C%EB%B3%B4%EB%93%9C.html"
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
    """표준 payload 반환. roles.cmo 실측치 그대로(미측정 채널은 '추적밖유입우세' 명시)."""
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

    total_clicks = cmo.get("총_클릭수")
    by_channel_clicks = cmo.get("채널별_클릭수") or {}
    by_channel_conv = cmo.get("채널별_클릭문의전환") or {}

    metrics = [{"label": "총 클릭수", "value": total_clicks if total_clicks is not None else "미측정"}]
    for ch, v in by_channel_clicks.items():
        metrics.append({"label": f"클릭·{ch}", "value": v})

    measured_bits = []
    unmeasured_bits = []
    for ch, conv in by_channel_conv.items():
        if not isinstance(conv, dict):
            continue
        if conv.get("measurable"):
            rate = conv.get("클릭_문의_전환율")
            metrics.append({"label": f"클릭→문의 전환율·{ch}", "value": f"{rate}%"})
            measured_bits.append(f"{ch} {rate}%")
        else:
            상태 = conv.get("상태") or "추적밖유입우세"
            metrics.append({"label": f"클릭→문의 전환율·{ch}", "value": f"{상태}(측정불가)"})
            unmeasured_bits.append(f"{ch}={상태}")

    summary_parts = [f"총 클릭 {total_clicks if total_clicks is not None else '미측정'}"]
    if measured_bits:
        summary_parts.append("클릭→문의 전환 " + ", ".join(measured_bits) + "(실측)")
    if unmeasured_bits:
        summary_parts.append(", ".join(unmeasured_bits) + " — 노출 미측정")
    summary = " · ".join(summary_parts)

    return make_payload(
        title="마케팅 퍼널·채널 성과",
        summary_line=summary,
        metrics=metrics,
        honesty_tag="부분",
        link=_LINK,
    )


if __name__ == "__main__":
    print(json.dumps(collect(), ensure_ascii=False, indent=2))
