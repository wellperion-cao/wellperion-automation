#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""이 PC(info@·lessons@ 등 다른 계정 PC)의 클로드 사용량을 서버로 올린다.
GM PC 의 token_usage.py 가 이 값을 읽어(read_push_key·fetch_remote) AI 토큰 현황 화면에 합산한다.
GM 지시 2026-09-14. token_usage.py 의 parse_file·cost_for_bucket 을 그대로 재사용한다(중복 계산 금지).

열쇠 = %USERPROFILE%\\.claude\\token_push.key 한 줄(없으면 환경변수 ERP_TOKEN_PUSH_KEY).
예약작업(Wellperion-Token-Push, ops/home_pc_setup.ps1 §7)이 매일 이 스크립트를 돌린다.
"""
import argparse
import json
import socket
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta

import token_usage as tu

PUSH_URL = "https://erp.wellperion.com/api/token_usage/push"


def build_summary():
    """최근 30일(token_usage.KEEP_DAYS) 사용량을 이 계정 하나로 집계 — 세션ID 목록 없이 숫자만."""
    cutoff = (datetime.now(tu.KST) - timedelta(days=tu.KEEP_DAYS - 1)).strftime("%Y-%m-%d")
    totals = {"input": 0, "cache_creation": 0, "cache_read": 0, "output": 0}
    cost_usd = 0.0
    sessions = set()
    where_acc = {}  # 닉네임 또는 project 이름 -> {sessions:set, output, cost_usd}
    files = sorted(tu.PROJECTS_DIR.rglob("*.jsonl")) if tu.PROJECTS_DIR.exists() else []
    for path in files:
        parsed = tu.parse_file(path)
        where_label = tu.ROLE_NICK.get(parsed.get("role"), parsed.get("project", "unknown"))
        session_id = path.stem
        for day, models in parsed.get("days", {}).items():
            if day < cutoff:
                continue
            for model, b in models.items():
                krw, _, _ = tu.cost_for_bucket(model, b)
                usd = krw / tu.USD_KRW
                totals["input"] += b["input"]
                totals["cache_creation"] += b["cache_creation"]
                totals["cache_read"] += b["cache_read"]
                totals["output"] += b["output"]
                cost_usd += usd
                sessions.add(session_id)
                w = where_acc.setdefault(where_label, {"sessions": set(), "output": 0, "cost_usd": 0.0})
                w["sessions"].add(session_id)
                w["output"] += b["output"]
                w["cost_usd"] += usd
    where = sorted(
        ({"project": k, "sessions": len(v["sessions"]), "output": v["output"], "cost_usd": round(v["cost_usd"], 2)}
         for k, v in where_acc.items()),
        key=lambda x: x["cost_usd"], reverse=True,
    )[:8]
    return {
        "account": tu.current_account(),
        "host": socket.gethostname(),
        "generated_at": datetime.now(tu.KST).isoformat(),
        "input": totals["input"], "cache_creation": totals["cache_creation"],
        "cache_read": totals["cache_read"], "output": totals["output"],
        "cost_usd": round(cost_usd, 2), "sessions": len(sessions), "where": where,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="전송 없이 페이로드 크기·세션 수만 출력")
    args = ap.parse_args()

    payload = build_summary()
    assert payload["sessions"] >= 0 and payload["cost_usd"] >= 0, "집계값 음수"
    assert all(w["cost_usd"] >= 0 and w["sessions"] >= 0 for w in payload["where"]), "where 집계 음수"
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    if args.dry_run:
        print("dry-run: bytes=%d sessions=%d where=%d account=%s host=%s" %
              (len(body), payload["sessions"], len(payload["where"]), payload["account"], payload["host"]))
        return 0

    key = tu.read_push_key()
    if not key:
        sys.stderr.write("열쇠 없음 - %s 또는 환경변수 ERP_TOKEN_PUSH_KEY\n" % tu.TOKEN_PUSH_KEY_FILE)
        return 1

    req = urllib.request.Request(
        PUSH_URL, data=body,
        headers={"Content-Type": "application/json; charset=utf-8", "X-Token-Push-Key": key},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            r.read()
    except Exception as e:  # noqa: BLE001 — 실패 사유를 그대로 한 줄에
        sys.stderr.write("전송 실패: %s: %s\n" % (type(e).__name__, e))
        return 1

    print("전송 완료 account=%s host=%s sessions=%d" % (payload["account"], payload["host"], payload["sessions"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
