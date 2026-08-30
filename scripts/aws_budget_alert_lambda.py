"""
AWS Budgets → SNS → Lambda → Telegram 예산 알람 핸들러

배포 대상: AWS Lambda (Python 3.12)
트리거: SNS Topic wellperion-budget-alert
환경변수:
  TG_BOT_TOKEN  — 텔레그램 봇 토큰 (telegram_bot/.env 와 동일 값)
  TG_CHAT_ID    — GM 업무보고방 Chat ID (기본값: 8254867551)
"""
from __future__ import annotations

import json
import os
import urllib.request

TG_API = "https://api.telegram.org/bot{token}/sendMessage"
CHAT_ID = os.environ.get("TG_CHAT_ID", "8254867551")


def _send(token: str, text: str) -> None:
    payload = json.dumps({"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}).encode()
    req = urllib.request.Request(
        TG_API.format(token=token),
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        if resp.status != 200:
            raise RuntimeError(f"Telegram API {resp.status}")


def lambda_handler(event: dict, context) -> dict:
    token = os.environ["TG_BOT_TOKEN"]

    for record in event.get("Records", []):
        raw = record.get("Sns", {}).get("Message", "{}")
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            msg = {"detail": raw}

        budget_name = msg.get("budgetName", "웰페리온 AWS 예산")
        actual = msg.get("actualSpend", {})
        limit = msg.get("budgetLimit", {})
        amount = actual.get("amount", "?")
        currency = actual.get("unit", "USD")
        cap = limit.get("amount", "?")

        text = (
            f"⚠️ <b>AWS 예산 초과 알람</b>\n"
            f"예산명: {budget_name}\n"
            f"실제 지출: {amount} {currency}\n"
            f"임계값: {cap} {currency}\n"
            f"→ AWS Console 확인 필요"
        )
        _send(token, text)

    return {"statusCode": 200}
