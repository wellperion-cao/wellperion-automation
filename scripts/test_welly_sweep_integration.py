#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
test_welly_sweep_integration.py — welly_sweep dry-run 1회 통합 테스트

검증:
  - 심은 중복/ship_no 충돌 픽스처를 감지한다(detect_*).
  - run_sweep(dry-run) 부작용 0: status/_queue.json 무변경.
  - 요약 카운트 + 자율로그 jsonl 산출.
  - 표류 집합이 hangro_board._classify(...)["drift"] 단일출처에서 옴.

stdlib only. 직접 실행:
  python scripts/test_welly_sweep_integration.py
"""
import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

import welly_sweep as ws  # noqa: E402

_fail = 0
_pass = 0


def check(cond, msg):
    global _fail, _pass
    if cond:
        _pass += 1
    else:
        _fail += 1
        print(f"  [FAIL] {msg}")


def test_detect_dedup_and_ship():
    raw = [
        {"task_id": "A-1", "clevel": "coo", "title": "작업 가", "status": "PENDING", "ship_no": 1},
        {"task_id": "A-1", "clevel": "coo", "title": "작업 가 중복", "status": "PENDING", "ship_no": 2},  # task_id 중복
        {"task_id": "B-1", "clevel": "cmo", "title": "동일 제목", "status": "IN_PROGRESS", "ship_no": 5},
        {"task_id": "B-2", "clevel": "cmo", "title": "동일 제목", "status": "PENDING", "ship_no": 5},  # title 중복 + ship_no 충돌
        {"task_id": "C-1", "clevel": "cto", "title": "고유", "status": "PENDING", "ship_no": 9},
        {"task_id": "D-1", "clevel": "coo", "title": "완료건", "status": "DONE", "ship_no": 1},  # 비활성 제외
    ]
    dup, ship = ws.detect_dedup_and_ship_conflicts(raw)
    check("A-1" in dup, "task_id 중복 A-1 감지")
    check("B-2" in dup, "title 중복 B-2 감지")
    check("B-1" in ship and "B-2" in ship, "cmo ship_no=5 충돌 B-1·B-2 감지")
    check("C-1" not in dup and "C-1" not in ship, "고유 C-1 오탐 없음")


def test_dry_run_no_side_effects():
    qpath = ws.QUEUE_PATH
    before = qpath.read_bytes() if qpath.exists() else b""
    summary = ws.run_sweep(execute=False)
    after = qpath.read_bytes() if qpath.exists() else b""
    check(before == after, "dry-run 후 _queue.json 바이트 무변경(부작용 0)")
    check(summary["dry_run"] is True, "summary.dry_run True")
    check("counts" in summary and "AUTO_EXEC" in summary["counts"], "counts 구조 존재")
    check(isinstance(summary["drift_count"], int), "drift_count 정수")
    # 자율로그 산출 확인
    from datetime import datetime, timezone, timedelta
    day = (datetime.now(timezone.utc) + timedelta(hours=9)).strftime("%Y-%m-%d")
    log = ws.LOG_DIR / f"{day}.jsonl"
    check(log.exists(), f"자율로그 jsonl 생성됨: {log}")


def test_drift_single_source():
    """표류 집합이 build_board와 동일 입력 _classify(...)['drift']와 동일."""
    from hangro_board import fetch_gas_items, fetch_queue_items, _classify
    try:
        gas = fetch_gas_items()
    except Exception:
        gas = []
    secs = _classify(gas + fetch_queue_items())
    board_drift = {str(it.get("id", "")) for it in secs.get("drift", [])}
    sweep_drift = ws.fetch_drift_ids()
    check(board_drift == sweep_drift,
          f"표류 단일출처 일치: board={board_drift} sweep={sweep_drift}")


def main():
    for fn in [test_detect_dedup_and_ship, test_dry_run_no_side_effects,
               test_drift_single_source]:
        print(f"[RUN] {fn.__name__}")
        fn()
    print(f"\n결과: {_pass} passed, {_fail} failed")
    sys.exit(1 if _fail else 0)


if __name__ == "__main__":
    main()
