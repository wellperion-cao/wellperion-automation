# -*- coding: utf-8 -*-
"""
telegram_send.py — 범용 텔레그램 발송 leaf (부작용 없는 안전 import).
─────────────────────────────────────────────────────────────────────────────
module_reporter 등 보고 인프라가 쓰는 단일 발송기.

leaf 원칙:
  - import-time 부작용 0: 토큰은 send() 호출 시에만 .env에서 직독.
  - 봇 토큰 단일출처 = telegram_bot/.env 의 TELEGRAM_BOT_TOKEN(환경변수 우선).
  - chat_id 가 None 이면 즉시 False 반환(방 미지정 → 발송 스킵).

반환: send(chat_id, text) -> bool  (성공 True / 실패·스킵 False)
"""
from __future__ import annotations

import os
from pathlib import Path

_ENV_FILE = Path(__file__).resolve().parent.parent.parent / "telegram_bot" / ".env"
_TIMEOUT = 15


def _read_token() -> str:
    """telegram_bot/.env 에서 TELEGRAM_BOT_TOKEN 직독. 환경변수 우선."""
    if os.environ.get("TELEGRAM_BOT_TOKEN"):
        return os.environ["TELEGRAM_BOT_TOKEN"].strip()
    if not _ENV_FILE.exists():
        return ""
    for line in _ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        if k.strip() == "TELEGRAM_BOT_TOKEN":
            return v.strip()
    return ""


def send(chat_id, text: str) -> bool:
    """Bot API sendMessage 1회 POST(실패 시 1회 재시도). chat_id=None → False."""
    if chat_id is None:
        return False
    token = _read_token()
    if not token:
        return False

    import requests  # noqa: PLC0415 — 발송 시점에만 import(테스트·dry-run 무접촉)

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    for attempt in range(2):
        try:
            resp = requests.post(url, json=payload, timeout=_TIMEOUT)
            if resp.status_code == 200 and resp.json().get("ok"):
                return True
            print(f"[telegram_send] 실패 attempt={attempt + 1} "
                  f"status={resp.status_code} body={resp.text[:160]}")
        except Exception as e:
            print(f"[telegram_send] 요청 예외 attempt={attempt + 1}: {e}")
    return False
