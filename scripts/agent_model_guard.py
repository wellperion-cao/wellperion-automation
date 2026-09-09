#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""서브에이전트 위임에 값비싼 모델을 잘못 지정하면 막는다 (GM 지시 2026-09-09).

왜: 자리가 아니라 일이 모델을 골라야 한다. 2026-09-05 실측 — 서브에이전트 13회 중
    7회를 opus 로 띄웠는데 전부 루틴(patch·집계·송부)이었다. 규칙은 CLAUDE.md 에
    적혀 있었지만 지켜지지 않았다. 문서로 두면 안 지켜지는 항목은 코드로 옮긴다
    (약속 L02). 새 관문을 만들지 않고 이미 Agent 를 거르는 PreToolUse 자리에 붙인다
    (약속 L21).

무엇을: 위임 지시문에 루틴 낱말이 뚜렷한데 model 이 opus·fable 이면 차단하고,
    무엇을 대신 쓰라는지 stderr 로 돌려준다. 판정표 정본 = ssot/model_routing.json.

안 막는 것:
  - model 을 안 넘긴 위임(기본 모델로 간다 — 이미 싼 쪽이다)
  - 판단 낱말이 함께 있는 위임(설계·검토·진단·원인 등)
  - 지시문에 「모델판단필요」 가 있는 위임(사람이 뜻을 밝힌 것)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TABLE = ROOT / "ssot" / "model_routing.json"
HEAVY = ("opus", "fable")
ESCAPE = "모델판단필요"


def _words(table: dict, tier: str) -> list[str]:
    return list(((table.get("서브에이전트") or {}).get(tier) or {}).get("낱말") or [])


def _load() -> dict:
    try:
        with open(TABLE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def verdict(prompt: str, model: str, table: dict) -> str | None:
    """막아야 하면 사유 문자열, 아니면 None."""
    model = (model or "").strip().lower()
    if not model or not any(h in model for h in HEAVY):
        return None
    text = str(prompt or "")
    if ESCAPE in text:
        return None
    routine = [w for w in _words(table, "haiku") + _words(table, "sonnet") if w in text]
    if not routine:
        return None
    if [w for w in _words(table, "opus") if w in text]:
        return None  # 판단 낱말이 섞여 있으면 사람 몫으로 둔다
    return (
        f"루틴 위임에 '{model}' 을 지정했다. 걸린 낱말: {', '.join(routine[:5])}.\n"
        "일이 모델을 고른다 — 읽기·조회·송부는 haiku, 코드 수정·집계·저장·콘텐츠 가공은 sonnet 이다.\n"
        f"정본 표 = ssot/model_routing.json. 정말 판단이 필요한 일이면 지시문에 '{ESCAPE}' 를 적어라."
    )


def main() -> int:
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip().startswith("{") else {}
    except Exception:
        return 0
    if payload.get("tool_name") not in ("Agent", "Task"):
        return 0
    args = payload.get("tool_input") or {}
    why = verdict(args.get("prompt", ""), args.get("model", ""), _load())
    if not why:
        return 0
    print(f"[모델 라우팅 가드] {why}", file=sys.stderr)
    return 2  # 2 = 차단하고 stderr 를 모델에게 돌려준다


def _selfcheck() -> None:
    t = _load()
    assert t, "ssot/model_routing.json 을 못 읽었다"
    assert verdict("이 파일들을 집계해서 표로 정리해줘", "opus", t), "루틴+opus 는 막아야 한다"
    assert verdict("커밋하고 배포해줘", "fable", t), "루틴+fable 은 막아야 한다"
    assert verdict("이 파일들을 집계해줘", "sonnet", t) is None, "sonnet 은 막지 않는다"
    assert verdict("이 파일들을 집계해줘", "", t) is None, "모델 미지정은 막지 않는다"
    assert verdict("장애 원인을 진단하고 설계를 검토해줘", "opus", t) is None, "판단 위임은 막지 않는다"
    assert verdict("집계해줘 모델판단필요", "opus", t) is None, "탈출구가 안 먹는다"
    print("agent_model_guard selfcheck OK")


if __name__ == "__main__":
    if "--selfcheck" in sys.argv:
        _selfcheck()
    else:
        try:
            sys.exit(main())
        except Exception:
            sys.exit(0)  # 가드가 죽어서 위임을 막으면 안 된다
