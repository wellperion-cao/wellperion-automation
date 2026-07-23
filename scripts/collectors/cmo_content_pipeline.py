# -*- coding: utf-8 -*-
"""
cmo_content_pipeline.py — 모듈 cmo-content-pipeline 수집기(공유 SSOT 정합).
─────────────────────────────────────────────────────────────────────────────
등록부(module_registry.json)의 모듈 id `cmo-content-pipeline` → id 규약으로
이 모듈명(collectors.cmo_content_pipeline)이 해소된다.

1차 소스 = 모듈의 **선언된 data_source**
  ("3. 웰페리온 가이드/cmo/review/review_queue.json") 직독.
  review_queue.json 은 M1 콘텐츠 제작·검수·발행 큐(각 항목 status 필드)를 담는다
  → 실측 status 값을 그대로 집계(가정 금지) → '측정' 꼬리표.

정직 꼬리표: review_queue.json 실측 = 측정 / 로드 실패·빈 큐 = 미측정.
"""
from __future__ import annotations

import json
import os
import sys
from collections import Counter

_SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # scripts/
_PROJECT_ROOT = os.path.dirname(_SCRIPTS_DIR)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from collectors.base import make_payload  # noqa: E402

_LINK = "https://wellperion-cao.github.io/wellperion-automation/wellperion_guide(main).html#M1"
_DEFAULT_REF = "3. 웰페리온 가이드/cmo/review/review_queue.json"


def _load_json(path):
    """review_queue.json 로드(인코딩 관용 — utf-8/cp949/utf-8-sig 순 시도)."""
    for enc in ("utf-8", "cp949", "utf-8-sig"):
        try:
            with open(path, "r", encoding=enc) as f:
                return json.load(f)
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        except Exception:
            return None
    return None


def _resolve_ref(module):
    """모듈의 선언된 data_source.ref → 절대경로(없으면 기본 review_queue.json)."""
    ref = None
    if isinstance(module, dict):
        ds = module.get("data_source") or {}
        ref = ds.get("ref")
    ref = ref or _DEFAULT_REF
    return ref if os.path.isabs(ref) else os.path.join(_PROJECT_ROOT, ref)


def collect(module=None) -> dict:
    """표준 payload 반환. review_queue.json 실제 status 값별 건수 집계(가정 금지)."""
    records = _load_json(_resolve_ref(module))
    if not isinstance(records, list) or not records:
        return make_payload(
            title="콘텐츠 제작·검수·발행",
            summary_line="review_queue.json 로드 실패 또는 빈 큐",
            metrics=[],
            honesty_tag="미측정",
            link=_LINK,
        )

    counts = Counter(str(rec.get("status", "") or "미분류").strip() for rec in records)
    total = len(records)

    # 등록부(module_registry.json)에 노출된 대표 상태(있으면 우선순으로), 나머지는 등장순.
    priority = ["제작", "검수대기", "발행완료", "폐기"]
    ordered_statuses = [s for s in priority if s in counts]
    ordered_statuses += [s for s in counts if s not in ordered_statuses]

    metrics = [{"label": "전체", "value": total}]
    metrics += [{"label": s, "value": counts[s]} for s in ordered_statuses]

    summary = f"전체 {total}건 · " + " · ".join(
        f"{s} {counts[s]}" for s in ordered_statuses
    )

    return make_payload(
        title="콘텐츠 제작·검수·발행",
        summary_line=summary,
        metrics=metrics,
        honesty_tag="측정",
        link=_LINK,
    )


if __name__ == "__main__":
    print(json.dumps(collect(), ensure_ascii=False, indent=2))
