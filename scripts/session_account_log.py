#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""세션 시작 시 로그인 계정을 한 줄 남긴다 (배1147 · GM 승인 2026-09-09).

왜: 대화 기록(jsonl)에는 모델·날짜·토큰(message.usage)이 남지만 **어느 계정으로 쓴
    것인지가 없다**. GM 은 cao / info 두 계정을 한도 때문에 오가므로, 토큰 사용량을
    계정별로 못 가르면 어느 쪽 한도가 닳는지 알 수 없다. 지금 로그인된 계정은
    ~/.claude.json 의 oauthAccount.emailAddress 에만 있고 세션이 바뀌면 덮인다.
    그래서 세션이 시작되는 그 순간에 (세션id ↔ 계정) 짝을 한 줄 적어 둔다.

무엇을: status/token_usage_accounts.jsonl 에 append 전용으로 한 줄.
    {"ts", "session_id", "account", "model", "cwd", "source"}

원칙:
  - **append 만 한다.** 같은 파일을 웰리 쪽 집계(scripts/token_usage.py)도 읽으므로
    통째 쓰기·정렬·중복 제거를 여기서 하지 않는다.
  - 같은 session_id 가 이미 있으면 덮지도 다시 적지도 않는다(세션 하나 = 한 줄).
  - **부팅을 막지 않는다.** 어떤 예외가 나도 조용히 exit 0 한다. 훅은 세션 시작
    경로라 여기서 죽으면 GM 창이 안 뜬다.
  - 기록은 계정 주소 하나뿐이다. 대화 내용·토큰 값은 여기서 만지지 않는다.

한계: 이 짝은 **오늘 이후분만** 생긴다. 지난 기록(8/9~9/9)은 계정 필드가 없어
    소급해서 가를 수 없다.

호출: SessionStart 훅이 stdin 으로 주는 JSON 을 그대로 받는다.
    C:/Python314/python.exe scripts/session_account_log.py
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "status" / "token_usage_accounts.jsonl"
CLAUDE_JSON = Path.home() / ".claude.json"
KST = timezone(timedelta(hours=9))


def _current_account() -> str:
    """지금 로그인된 계정 주소. 못 읽으면 빈 문자열."""
    try:
        with open(CLAUDE_JSON, encoding="utf-8") as f:
            d = json.load(f)
        return str((d.get("oauthAccount") or {}).get("emailAddress") or "")
    except Exception:
        return ""


def _already_logged(session_id: str) -> bool:
    """같은 세션이 이미 적혔나. 파일이 없거나 못 읽으면 False(=적는다)."""
    if not session_id or not OUT.is_file():
        return False
    try:
        with open(OUT, encoding="utf-8", errors="replace") as f:
            for line in f:
                if session_id in line:
                    return True
    except Exception:
        return False
    return False


def main() -> int:
    try:
        raw = sys.stdin.read() if not sys.stdin.isatty() else ""
    except Exception:
        raw = ""
    try:
        payload = json.loads(raw) if raw.strip().startswith("{") else {}
    except Exception:
        payload = {}

    session_id = str(payload.get("session_id") or "")
    if _already_logged(session_id):
        return 0

    row = {
        "ts": datetime.now(KST).isoformat(timespec="seconds"),
        "session_id": session_id,
        "account": _current_account(),
        "model": str(payload.get("model") or ""),
        "cwd": str(payload.get("cwd") or os.getcwd()),
        "source": str(payload.get("source") or ""),
    }
    try:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        with open(OUT, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception:
        pass
    return 0


def _selfcheck() -> None:
    """계정 읽기와 중복 판정이 도는지만 본다(파일은 건드리지 않는다)."""
    acc = _current_account()
    assert isinstance(acc, str), "계정 읽기가 문자열이 아니다"
    assert _already_logged("") is False, "빈 session_id 는 중복으로 보면 안 된다"
    print(f"자체검사 통과 — 현재 계정 {acc or '(못 읽음)'} · 기록 파일 {OUT}")


if __name__ == "__main__":
    if "--selfcheck" in sys.argv:
        _selfcheck()
    else:
        try:
            sys.exit(main())
        except Exception:
            sys.exit(0)  # 부팅을 막지 않는다
