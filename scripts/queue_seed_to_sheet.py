#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
scripts/queue_seed_to_sheet.py — _queue.json AI 배를 구글시트에 1회 시드 insert (S2 전용)

안전 원칙
    - task_id 기준 dedup: 시트에 이미 같은 task_id 임베드가 있으면 SKIP (idempotent).
    - 기본값 --dry-run: 실제 insert 없이 "추가 예정 N건 / SKIP N건" 만 출력.
    - --execute 플래그를 명시해야 실제 GAS todo_add 호출.
    - 1건씩 순차 insert (batch 금지) — 어제 사고 재발 방지.
    - insert 전후 시트 AI행 count assert — 기대값과 다르면 즉시 중단.

CLI 예
    python scripts/queue_seed_to_sheet.py              # dry-run (기본)
    python scripts/queue_seed_to_sheet.py --execute    # 실제 insert
    python scripts/queue_seed_to_sheet.py --execute --limit 1  # 1건만 (S1 검증용)
"""
from __future__ import annotations

import argparse
import io
import json
import sys
import time
import urllib.request
import urllib.parse
from pathlib import Path

# ── 콘솔 인코딩(Windows cp949 한글 깨짐 방지) ──────────────────────────────
try:
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
except Exception:
    pass

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parent
QUEUE_PATH = _REPO / "status" / "_queue.json"

GAS_URL = (
    "https://script.google.com/macros/s/"
    "AKfycbxDwFkrxK1YIaEoSNcuw2MiHiZQ-7o5N6311ytksSyeEd86ZFOhLknOWqQgNArQvZ-7/exec"
)

AI_CATEGORY = "[7]AI배(C레벨)"

_EMBED_RE = __import__("re").compile(r"===AI_QUEUE===\s*(.+?)\s*===END===", __import__("re").DOTALL)

# status 정방향 매핑 (_queue → 시트 한글)
_STATUS_TO_SHEET = {
    "IN_PROGRESS": "진행중",
    "PENDING": "대기",
    "DONE": "완료",
    "ON_HOLD": "보류",
    "폐기": "폐기",
}


def _gas_get(action: str) -> dict:
    req = urllib.request.Request(GAS_URL + f"?action={action}")
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())


def _gas_post(payload: dict) -> dict:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        GAS_URL,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())


def _fetch_ai_task_ids() -> set[str]:
    """시트에서 현재 AI행의 task_id 집합 반환 (dedup 판정용)."""
    data = _gas_get("todo_list")
    rows = list(data.get("data", []))
    ids: set[str] = set()
    for row in rows:
        cat = str(row.get("카테고리", "") or "").strip()
        if cat != AI_CATEGORY:
            continue
        content = str(row.get("내용", "") or "")
        m = _EMBED_RE.search(content)
        if m:
            try:
                obj = json.loads(m.group(1))
                tid = obj.get("task_id", "")
                if tid:
                    ids.add(tid)
            except Exception:
                pass
        # id 컬럼 폴백
        tid_col = str(row.get("id", "") or "").strip()
        if tid_col:
            ids.add(tid_col)
    return ids


def _count_ai_rows() -> int:
    data = _gas_get("todo_list")
    rows = list(data.get("data", []))
    return sum(1 for r in rows if str(r.get("카테고리", "") or "").strip() == AI_CATEGORY)


def _build_embed(item: dict) -> str:
    """_queue 항목 → 내용 셀 임베드 블록 생성."""
    # title·status 는 시트 전용 컬럼으로 빠짐 — 임베드엔 나머지 전부
    embed = {k: v for k, v in item.items() if k not in ("title", "status")}
    return "===AI_QUEUE===\n" + json.dumps(embed, ensure_ascii=False) + "\n===END==="


def _todo_add_payload(item: dict) -> dict:
    """GAS todo_add 에 보낼 payload 구성."""
    return {
        "action": "todo_add",
        "업무명": item.get("title", ""),
        "카테고리": AI_CATEGORY,
        "담당자": item.get("clevel", ""),
        "상태": _STATUS_TO_SHEET.get(item.get("status", ""), item.get("status", "")),
        "내용": _build_embed(item),
        "난이도": {"HIGH": "상", "NORMAL": "중", "P0": "P0"}.get(
            item.get("priority", "NORMAL"), "중"
        ),
        "종료일": item.get("deadline", ""),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="_queue.json AI 배 → 시트 1회 시드 insert (dedup 가드)")
    ap.add_argument("--execute", action="store_true",
                    help="실제 insert 실행. 미지정 시 dry-run.")
    ap.add_argument("--limit", type=int, default=0,
                    help="insert 최대 건수 (0=전체). S1 검증용: --limit 1")
    args = ap.parse_args(argv)

    items = json.loads(QUEUE_PATH.read_text(encoding="utf-8"))

    print(f"[INFO] _queue.json 로드: {len(items)}건")

    # 시트 현황 조회
    print("[INFO] 시트 AI행 현황 조회 중...")
    existing_ids = _fetch_ai_task_ids()
    before_count = len(existing_ids)
    print(f"[INFO] 시트 기존 AI행: {before_count}건 (task_id {sorted(existing_ids)[:3]}{'...' if len(existing_ids)>3 else ''})")

    # 추가 대상 선별
    to_add = [it for it in items if it.get("task_id", "") not in existing_ids]
    skip = [it for it in items if it.get("task_id", "") in existing_ids]

    print(f"[INFO] 추가 예정: {len(to_add)}건 / SKIP(이미 있음): {len(skip)}건")

    if args.limit and len(to_add) > args.limit:
        to_add = to_add[: args.limit]
        print(f"[INFO] --limit {args.limit} 적용 → {len(to_add)}건만 처리")

    if not to_add:
        print("[DONE] 추가할 항목 없음 (모두 이미 존재).")
        return 0

    if not args.execute:
        print("\n[DRY-RUN] 실제 insert 없음. --execute 로 재실행하면 아래 항목 추가됨:")
        for it in to_add:
            print(f"  - {it.get('task_id')} [{it.get('clevel')}] {it.get('status')} :: {str(it.get('title',''))[:40]}")
        return 0

    # 실제 insert — 1건씩 순차
    inserted = 0
    for it in to_add:
        tid = it.get("task_id", "?")
        print(f"[INSERT] {tid} ...", end=" ", flush=True)
        try:
            payload = _todo_add_payload(it)
            result = _gas_post(payload)
            if result.get("ok") or result.get("status") == "ok":
                print("OK")
                inserted += 1
            else:
                print(f"FAIL — {result}")
                print(f"[ABORT] insert 실패. 이후 건 중단. 현재까지 {inserted}건 추가됨.")
                return 1
        except Exception as e:
            print(f"ERROR — {e}")
            print(f"[ABORT] 현재까지 {inserted}건 추가됨.")
            return 1
        time.sleep(0.5)  # GAS rate limit 방지

    # insert 후 count assert
    print(f"\n[INFO] insert 완료 {inserted}건. 시트 AI행 count 재확인 중...")
    after_count = _count_ai_rows()
    expected = before_count + inserted
    if after_count == expected:
        print(f"[ASSERT] PASS — 시트 AI행 {after_count}건 (기대값 {expected})")
    else:
        print(f"[ASSERT] FAIL — 시트 AI행 {after_count}건 (기대값 {expected}) — 수동 확인 필요")
        return 1

    print(f"[DONE] S2 시드 insert 완료. 다음: queue_sync_from_sheet.py --diff 로 미러 검증.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
