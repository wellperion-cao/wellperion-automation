#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""어느 자리에 어느 모델을 쓸지 한 줄로 답한다 (GM 지시 2026-09-09).

왜: 세션 모델이 Start-AI 배치 8개에 각각 박혀 있었다. GM 이 /model 로 바꿔도
    배치가 명령줄로 덮어써서 다음 창은 옛 모델로 떴다(2026-09-09 실측). 값을 8곳에
    두는 대신 표 한 곳(ssot/model_routing.json)에 두고 배치가 읽어 가게 한다
    (약속 L01 — 한 곳만 본다).

쓰는 법:
    python scripts/model_for.py session [역할]  → 세션 모델 이름 한 줄(역할별 값이 있으면 그것)
    python scripts/model_for.py subagent 집계해줘   → 그 일에 맞는 등급 한 줄

값을 못 읽으면 안전한 기본값을 낸다 — 부팅이 모델 이름을 못 받아 멈추면 안 된다.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

TABLE = Path(__file__).resolve().parent.parent / "ssot" / "model_routing.json"
SESSION_FALLBACK = "opus"


def _table() -> dict:
    try:
        with open(TABLE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def session_model(role: str = "") -> str:
    """역할이 표의 「역할별」에 있으면 그 모델, 없으면 현재값.

    GM 지시 2026-09-15: 웰리(ceo)·시토(cto)는 항상 Fable 5.1 로 뜬다. 나머지 역할은
    종전대로 현재값(GM 이 /model 로 고르는 값 하나)을 따른다."""
    sess = _table().get("세션") or {}
    by_role = sess.get("역할별") or {}
    v = str(by_role.get((role or "").lower().strip()) or "").strip()
    if v:
        return v
    v = str(sess.get("현재값") or "").strip()
    return v or SESSION_FALLBACK


def subagent_tier(text: str) -> str:
    """일의 성격으로 등급을 고른다. 애매하면 싼 쪽(sonnet)."""
    sub = _table().get("서브에이전트") or {}
    text = str(text or "")
    for tier in ("opus", "sonnet", "haiku"):
        words = (sub.get(tier) or {}).get("낱말") or []
        if any(w in text for w in words):
            return tier
    return "sonnet"


def main(argv: list[str]) -> int:
    what = (argv[1] if len(argv) > 1 else "session").lower()
    if what == "subagent":
        print(subagent_tier(" ".join(argv[2:])))
    else:
        print(session_model(argv[2] if len(argv) > 2 else ""))
    return 0


def _selfcheck() -> None:
    assert session_model(), "세션 모델이 비었다"
    assert session_model("ceo") == "claude-fable-5-1", "웰리 세션은 Fable 5.1 이어야 한다(GM 2026-09-15)"
    assert session_model("cto") == "claude-fable-5-1", "시토 세션은 Fable 5.1 이어야 한다(GM 2026-09-15)"
    assert session_model("cmo") == session_model(), "역할별 값이 없는 역할은 현재값을 따라야 한다"
    assert subagent_tier("로그를 조회해줘") == "haiku"
    assert subagent_tier("이 파일을 수정해줘") == "sonnet"
    assert subagent_tier("장애 원인을 진단해줘") == "opus"
    assert subagent_tier("") == "sonnet", "애매하면 싼 쪽이어야 한다"
    print(f"model_for selfcheck OK — 세션 {session_model()}")


if __name__ == "__main__":
    if "--selfcheck" in sys.argv:
        _selfcheck()
    else:
        try:
            sys.exit(main(sys.argv))
        except Exception:
            print(SESSION_FALLBACK)
            sys.exit(0)
