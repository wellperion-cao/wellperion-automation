# -*- coding: utf-8 -*-
"""검수큐(review_queue.json) 상태값 단일 출처 — 약속 L01 '한 곳만 본다'.

왜 별도 파일인가(2026-07-24 · 배9598 A3):
    종결 상태값은 원래 ig_review_publish_watcher.py 가 소유했고, 발행 디제스트
    (publish_digest.py)도 같은 집합을 봐야 한다. 그런데 watcher 가 publish_digest 를
    import 하므로(ig_review_publish_watcher.py:59) 반대 방향 import 는 순환이 되어
    조용히 폴백 복사본으로 떨어졌다 — 헌법 불변원리 1이 경고하는 '복사본이 조용히
    이기는' 바로 그 형태. 그래서 양쪽이 함께 import 할 수 있는 잎(leaf) 모듈로 내렸다.
    이 파일은 어떤 모듈도 import 하지 않는다(순환 불가).

※ 종결 상태값을 새로 만들면 여기에만 추가한다. 다른 곳에 같은 집합을 다시 적지 않는다.
"""

from __future__ import annotations

# 종결(더 이상 발행·요약 대상이 아님) 상태값.
#   실측 사용값은 '폐기'(review_queue.json 라이브 1건·아카이브 2건).
#   '취소'는 ssot/decision_contracts.json decision_events 에 선언된 동급 종결어.
TERMINAL_STATES: frozenset[str] = frozenset({"폐기", "취소"})


def is_terminal_status(status: str | None) -> bool:
    """상태값 하나가 종결인가(공백·None 안전)."""
    return (status or "").strip() in TERMINAL_STATES
