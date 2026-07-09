# -*- coding: utf-8 -*-
"""
base.py — 수집기(collector) 표준 payload 규격 + 검증 헬퍼.
─────────────────────────────────────────────────────────────────────────────
모든 모듈 수집기는 `collect() -> dict` 하나만 노출한다. 반환은 아래 표준 payload:

  {
    "title":        str,          # 보고 제목 (예: "자율현황 자동화 건강")
    "summary_line": str,          # 한 줄 요약 (예: "가동 10/10 · 실패 0")
    "metrics":      list[dict],   # [{"label": str, "value": str|int|float}, ...]
    "honesty_tag":  str,          # 측정 | 부분 | 미측정 | 표본부족
    "link":         str,          # 프론트/대시보드 링크 (없으면 "")
  }

정직 꼬리표(honesty_tag) 표준(스펙 §정직 가드):
  - 측정: 실측치 신뢰. / 부분: 일부만 측정. / 미측정: 데이터 없음.
  - 표본부족: 표본이 통계적으로 부족 → % 대신 원수치.
"""
from __future__ import annotations

REQUIRED_KEYS = ("title", "summary_line", "metrics", "honesty_tag", "link")
HONESTY_TAGS = ("측정", "부분", "미측정", "표본부족")


def make_payload(title, summary_line, metrics=None, honesty_tag="측정", link=""):
    """표준 payload를 조립한다(누락 필드 방어)."""
    return {
        "title": str(title),
        "summary_line": str(summary_line),
        "metrics": list(metrics) if metrics else [],
        "honesty_tag": honesty_tag if honesty_tag in HONESTY_TAGS else "미측정",
        "link": str(link or ""),
    }


def validate_payload(payload) -> list:
    """표준 payload를 검증해 위반 사유 문자열 목록 반환. 빈 리스트=통과."""
    violations = []
    if not isinstance(payload, dict):
        return [f"payload가 dict 아님: {type(payload).__name__}"]

    for key in REQUIRED_KEYS:
        if key not in payload:
            violations.append(f"필수 키 누락: {key}")

    if "title" in payload and not isinstance(payload["title"], str):
        violations.append("title이 str 아님")
    if "summary_line" in payload and not isinstance(payload["summary_line"], str):
        violations.append("summary_line이 str 아님")
    if "link" in payload and not isinstance(payload["link"], str):
        violations.append("link가 str 아님")

    if "metrics" in payload:
        if not isinstance(payload["metrics"], list):
            violations.append("metrics가 list 아님")
        else:
            for i, m in enumerate(payload["metrics"]):
                if not isinstance(m, dict) or "label" not in m or "value" not in m:
                    violations.append(f"metrics[{i}] label/value 규격 위반")

    if "honesty_tag" in payload and payload["honesty_tag"] not in HONESTY_TAGS:
        violations.append(
            f"honesty_tag 허용값 밖: {payload['honesty_tag']!r} (허용: {HONESTY_TAGS})"
        )

    return violations
