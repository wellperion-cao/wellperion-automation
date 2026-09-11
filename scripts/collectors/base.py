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


def _erp(text):
    """업무 화면 링크를 ERP 새 주소로 바꾼다(옛 주소로 열리는 것 차단 · 배 2529).

    정본은 tg_outbound_log.to_erp_links 하나다 — 카톡·텔레그램 본문이 이미 그 함수를 지난다.
    수집기 payload 의 link·summary_line 은 그 관문을 안 지나 옛 주소가 status/heartbeats/*.json
    에 그대로 적혔고, 화면이 그 값을 읽어 옛 화면으로 열었다(GM 지적 2026-09-11).
    이미지·PDF 주소는 그 함수가 안 건드린다 — 회원·외부가 여는 링크는 그대로 간다.
    """
    try:
        from tg_outbound_log import to_erp_links
    except Exception:
        try:
            import sys
            from pathlib import Path
            sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
            from tg_outbound_log import to_erp_links
        except Exception:
            return str(text or "")   # 못 불러오면 종전 값 그대로 — 수집을 막지 않는다
    return to_erp_links(text)


def make_payload(title, summary_line, metrics=None, honesty_tag="측정", link=""):
    """표준 payload를 조립한다(누락 필드 방어)."""
    return {
        "title": str(title),
        "summary_line": _erp(summary_line),
        "metrics": list(metrics) if metrics else [],
        "honesty_tag": honesty_tag if honesty_tag in HONESTY_TAGS else "미측정",
        "link": _erp(link or ""),
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


def demo():
    """배 2529 확인 — 업무 화면 링크는 ERP 새 주소로, 이미지는 옛 주소 그대로."""
    old = "https://wellperion-cao.github.io/wellperion-automation/"
    p = make_payload(
        "제목",
        f"자세히 {old}coo/check/전사_일정.html 보세요",
        link=old + "cpo/member/membership.html?manage=lesson",
    )
    assert p["link"] == "https://erp.wellperion.com/cpo/member/membership.html?manage=lesson", p["link"]
    assert "erp.wellperion.com/coo/check/전사_일정.html" in p["summary_line"], p["summary_line"]

    q = make_payload("제목", "시안", link=old + "reports/현수막.png")
    assert q["link"] == old + "reports/현수막.png", q["link"]   # 이미지는 로그인 벽 뒤로 넣지 않는다

    assert validate_payload(p) == []
    print("[selfcheck] make_payload 링크 치환 OK")


if __name__ == "__main__":
    demo()
