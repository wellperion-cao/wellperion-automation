#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
session_register.py — 지금 살아있는 C-Level 세션 등록부 (배1005 ③ · GM 지시 2026-09-05).

왜 있나
  사람이 창을 열어 둔 C-Level 세션은 부팅할 때만 큐를 본다. 낮에 넘긴 배는 모른다.
  반대로 무인 러너(welly_auto_runner)는 그 역할 세션이 살아 있어도 새 claude 를 띄워
  같은 배를 중복으로 집는다(2026-09-05 10:30 회차 2척 충돌).
  두 문제 모두 "그 역할 세션이 지금 살아 있나"를 아무도 몰라서 생긴다. 그 한 가지 사실만
  파일 하나로 남긴다 — 판정 지점은 여기 하나뿐이다(약속 L01).

무엇을 남기나
  status/sessions/{role}.json — 그 세션만 아는 자기 이름(SendMessage 주소)과 마지막 생존 시각.
  세션 이름은 그 세션 자신만 알 수 있으므로("This session is welperion-automation-4f [a08477]")
  부팅한 세션이 직접 --role/--session 으로 적는다.

쓰는 법
  python scripts/session_register.py --role ceo --session "welperion-automation-4f" --ref a08477
  python scripts/session_register.py --heartbeat --role ceo
  python scripts/session_register.py --alive ceo      # JSON 한 줄
  python scripts/session_register.py --list
  python scripts/session_register.py --selfcheck

파일 잠금 없음 — 역할당 파일 1개이고 쓰는 이는 그 역할 세션 하나뿐이다.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime

_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_SCRIPTS_DIR)
SESSIONS_DIR = os.path.join(_PROJECT_ROOT, "status", "sessions")

# 살아있음 판정 창. 부팅 뒤 한참 조용한 세션도 사람이 창을 열어 둔 동안은 살아 있다고 본다.
# 짧게 잡으면 러너가 그 세션 옆에서 같은 배를 또 집는다(원래 문제로 되돌아감).
ALIVE_MINUTES = 90


def path_for(role: str) -> str:
    return os.path.join(SESSIONS_DIR, f"{role.lower()}.json")


def _now() -> datetime:
    return datetime.now().astimezone()


def _roles() -> dict:
    """역할·닉네임 정본 = queue_dispatch.ROLES (복제 금지 · 지연 import 로 순환 회피)."""
    from queue_dispatch import ROLES  # noqa: PLC0415
    return ROLES


def load(role: str) -> dict | None:
    path = path_for(role)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _save(role: str, data: dict) -> None:
    os.makedirs(SESSIONS_DIR, exist_ok=True)
    with open(path_for(role), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def register(role: str, session: str, ref: str = "") -> dict:
    """세션 이름·ref 를 적고 등록·생존 시각을 지금으로 맞춘다. 다른 칸(nick·note)은 보존."""
    data = load(role) or {}
    now = _now().isoformat(timespec="seconds")
    data.update({
        "role": role.lower(), "session": session, "ref": ref,
        "registered_at": now, "heartbeat_at": now,
    })
    data.setdefault("nick", _roles().get(role.lower(), ""))
    _save(role, data)
    return data


def heartbeat(role: str) -> dict | None:
    """생존 시각만 갱신. 등록된 적 없으면 None(등록이 먼저다)."""
    data = load(role)
    if data is None:
        return None
    data["heartbeat_at"] = _now().isoformat(timespec="seconds")
    _save(role, data)
    return data


def alive(role: str, minutes: int = ALIVE_MINUTES) -> dict:
    """
    살아있음 판정 — heartbeat_at 이 minutes 이내면 alive.
    반환: {"role", "alive", "session", "age_min"}. 파일 없음·깨짐·시각 파싱 실패는 전부
    alive=False(fail-closed 아님 — '모르면 없는 것'으로 보고 러너가 평소대로 돈다).
    """
    out = {"role": role.lower(), "alive": False, "session": None, "age_min": None}
    data = load(role)
    if not data:
        return out
    out["session"] = data.get("session")
    try:
        stamp = datetime.fromisoformat(str(data.get("heartbeat_at") or "").replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return out
    if stamp.tzinfo is None:
        stamp = stamp.astimezone()
    age = (_now() - stamp).total_seconds() / 60.0
    out["age_min"] = round(age, 1)
    out["alive"] = age <= minutes
    return out


def print_list() -> None:
    print(f"## 살아있는 C-Level 세션 (기준 {ALIVE_MINUTES}분)\n")
    print("| 역할 | 닉 | 세션 | 마지막 생존 | 판정 |")
    print("|---|---|---|---|---|")
    for role, nick in _roles().items():
        st = alive(role)
        age = "—" if st["age_min"] is None else f"{st['age_min']:.0f}분 전"
        print(f"| {role.upper()} | {nick} | {st['session'] or '—'} | {age} | "
              f"{'🟢 살아있음' if st['alive'] else '⚪ 없음'} |")


def _selfcheck() -> int:
    """가짜 역할 하나로 등록→판정→만료를 확인하고 흔적을 지운다(실제 역할 파일 무손상)."""
    role = "_selftest"
    path = path_for(role)
    try:
        assert alive(role)["alive"] is False, "등록 전인데 alive"
        register(role, "welperion-automation-selftest", "abc123")
        st = alive(role)
        assert st["alive"] is True, f"방금 등록했는데 alive 아님: {st}"
        assert st["session"] == "welperion-automation-selftest", st
        assert st["age_min"] is not None and st["age_min"] < 1, st
        assert heartbeat(role) is not None, "heartbeat 실패"
        assert alive(role, minutes=0)["alive"] is False, "창 0분인데 alive"
        data = load(role)
        data["heartbeat_at"] = "깨진값"
        _save(role, data)
        assert alive(role)["alive"] is False, "시각 파싱 실패인데 alive"
    finally:
        if os.path.exists(path):
            os.remove(path)
    print("session_register selfcheck OK")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="살아있는 C-Level 세션 등록·판정")
    ap.add_argument("--role", help="역할(ceo/cto/cmo/cpo/coo/cbo/chro/cfo)")
    ap.add_argument("--session", help="이 세션의 이름 — SendMessage 주소")
    ap.add_argument("--ref", default="", help="세션 참조 해시(선택)")
    ap.add_argument("--heartbeat", action="store_true", help="생존 시각만 갱신")
    ap.add_argument("--alive", metavar="ROLE", help="살아있음 판정 JSON 한 줄")
    ap.add_argument("--list", action="store_true", help="전 역할 표")
    ap.add_argument("--selfcheck", action="store_true", help="자체 점검")
    args = ap.parse_args()

    if args.selfcheck:
        return _selfcheck()
    if args.alive:
        print(json.dumps(alive(args.alive), ensure_ascii=False))
        return 0
    if args.list:
        print_list()
        return 0
    if args.heartbeat:
        if not args.role:
            print("! --heartbeat 에는 --role 이 필요합니다.")
            return 2
        data = heartbeat(args.role)
        if data is None:
            print(f"! {args.role} 은 등록된 적이 없습니다 — --session 으로 먼저 등록하세요.")
            return 2
        print(f"생존 갱신: {data['role']} · {data.get('session')} · {data['heartbeat_at']}")
        return 0
    if args.role and args.session:
        data = register(args.role, args.session, args.ref)
        print(f"등록: {data['role']} · {data['session']} · {data['registered_at']}")
        print(f"  기록 {path_for(args.role)}")
        return 0

    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
