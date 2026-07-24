# -*- coding: utf-8 -*-
"""weekly_bundle_pending.py — 배10011 알림 묶기 공용 pending 파일 유틸.

문제: 같은 날 아침에 여러 독립 스크립트(각자 다른 Windows 예약작업)가 따로 발송하던 걸
한 통으로 묶으려면, "먼저 도는 것들"은 자기 텍스트만 적어두고 "가장 나중에 도는 것"이
전부 모아 한 번에 보내야 한다. 이 모듈이 그 적재/소비를 공용화한다(중복 구현 금지).

사용:
  weekly_bundle_pending.append(bundle_id, source, text)   # 먼저 도는 스크립트
  weekly_bundle_pending.consume(bundle_id)                # 가장 나중에 도는(=합쳐 보내는) 스크립트

같은 날 같은 source가 중복 append돼도 1건만 남는다(멱등 — 재실행 안전).
날짜가 바뀌면 그 전날 파일은 자동으로 무시된다(consume이 오늘자 아니면 빈 리스트 반환).
"""
from __future__ import annotations

import json
import os
from datetime import datetime

_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
_STATUS_DIR = os.path.normpath(os.path.join(_SCRIPTS_DIR, "..", "status"))


def _pending_path(bundle_id: str) -> str:
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in str(bundle_id))
    return os.path.join(_STATUS_DIR, f"weekly_bundle_pending_{safe}.json")


def _load(bundle_id: str, today: str) -> dict:
    path = _pending_path(bundle_id)
    if not os.path.exists(path):
        return {"date": today, "items": []}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return {"date": today, "items": []}
    if data.get("date") != today:
        return {"date": today, "items": []}  # 날짜 바뀜 — 이전 잔여는 버림(정직: 늦은 발송보다 미발송이 낫다)
    if not isinstance(data.get("items"), list):
        data["items"] = []
    return data


def append(bundle_id: str, source: str, text: str, *, now=None) -> None:
    """source(모듈/스크립트 식별자) 텍스트를 오늘자 번들에 적재. 같은 source 재호출 시 최신 텍스트로 덮어씀(멱등)."""
    now = now or datetime.now()
    today = now.strftime("%Y-%m-%d")
    data = _load(bundle_id, today)
    items = [it for it in data["items"] if it.get("source") != source]
    items.append({"source": source, "text": text, "ts": now.isoformat()})
    data["items"] = items
    try:
        with open(_pending_path(bundle_id), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as exc:
        print(f"[weekly_bundle_pending] {bundle_id} append 실패(무시): {exc}")


def peek(bundle_id: str, *, now=None) -> list[dict]:
    """소비하지 않고 오늘자 항목만 조회(디버그·검증용)."""
    now = now or datetime.now()
    today = now.strftime("%Y-%m-%d")
    return list(_load(bundle_id, today)["items"])


def consume(bundle_id: str, *, now=None) -> list[dict]:
    """오늘자 항목을 반환하고 파일을 비운다(재중복 방지). 반환: [{"source","text","ts"}, ...]."""
    now = now or datetime.now()
    today = now.strftime("%Y-%m-%d")
    data = _load(bundle_id, today)
    items = data["items"]
    try:
        with open(_pending_path(bundle_id), "w", encoding="utf-8") as f:
            json.dump({"date": today, "items": []}, f, ensure_ascii=False)
    except Exception as exc:
        print(f"[weekly_bundle_pending] {bundle_id} consume 정리 실패(무시): {exc}")
    return items
