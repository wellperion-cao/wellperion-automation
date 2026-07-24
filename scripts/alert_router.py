# -*- coding: utf-8 -*-
"""알림이 어느 방으로 갈지 정하는 **단일 지점** (2026-07-24 시토 · GM 지시).

GM 2026-07-24: "실패건들이 업무보고방에 들어오는 건 아닌 것 같은데, 버그나 검수·검사
확인하는 내용들은 자동화현황 방으로."

가르는 기준 딱 하나:
  **GM 이 손으로 할 일이 있나?**
    있다  → GM 업무보고방 (kind="gm_action")
            예) 구글 재로그인, 봇 토큰 재발급, 결정·승인 요청
    없다  → 확인방(자동화현황방) (kind="tech_check")
            예) 헬스체크 경보, 자동 push 실패, 연동 다리 끊김, 검수·점검 결과

왜 한 곳에 모으나 (약속 L01 한 곳만 본다)
  이 저장소는 텔레그램 발신 지점이 수십 곳이고, 각자 chat_id 를 따로 들고 있었다.
  그래서 "이건 어느 방으로 가야 하나"를 고칠 때 빠뜨리는 곳이 생긴다.
  방 번호는 status/telegram_rooms.json 이 원천이고, **분류 판단은 여기 한 곳**이다.

★주의: 실패라고 다 확인방이 아니다. 'GM 이 재로그인해야 복구되는 실패'는 GM 방이 맞다.
  확인방으로 옮기면 GM 이 못 보고 다음 날 보고가 또 펑크난다(2026-07-24 매출보고 실사례).
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ROOMS = ROOT / "status" / "telegram_rooms.json"

GM_ACTION = "gm_action"
TECH_CHECK = "tech_check"

_FALLBACK = {"GM_DM": 8254867551, "자동화현황방": -5498808140}


def _rooms() -> dict:
    try:
        return json.loads(ROOMS.read_text(encoding="utf-8"))
    except Exception:
        return dict(_FALLBACK)


def route(kind: str) -> int:
    """분류 → chat_id. 모르는 분류는 GM 방으로(놓치는 것보다 시끄러운 게 낫다)."""
    r = _rooms()
    if kind == TECH_CHECK:
        v = r.get("자동화현황방") or _FALLBACK["자동화현황방"]
    else:
        v = r.get("GM_DM") or _FALLBACK["GM_DM"]
    return int(v)


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    print("gm_action  →", route(GM_ACTION), "(GM 업무보고방)")
    print("tech_check →", route(TECH_CHECK), "(확인방·자동화현황방)")
