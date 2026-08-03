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
import sys
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
    """Bot API sendMessage 관문(scripts/tg_outbound_log.send) 경유. chat_id=None → False."""
    if chat_id is None:
        return False
    token = _read_token()
    if not token:
        return False

    sys.path.insert(0, str(_ENV_FILE.resolve().parent.parent / "scripts"))  # noqa: PLC0415
    from tg_outbound_log import send as _tg_send  # noqa: PLC0415 — 발송 시점에만 import

    return _tg_send(token, chat_id, text, source="notify.telegram_send.send", timeout=_TIMEOUT)
