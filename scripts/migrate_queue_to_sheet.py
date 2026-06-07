#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
scripts/migrate_queue_to_sheet.py — _queue.json AI 배 → 구글시트 1회성 이관 (2단계)

목적:
    현재 status/_queue.json 의 AI 배(폐기 제외)를 GAS todo_add API 로 시트에 올린다.
    카테고리 '[7]AI배(C레벨)' + '내용' 셀에 ===AI_QUEUE=== 임베드로 부족 필드 보존.

안전:
    - task_id 기준 중복 방지: todo_list 먼저 조회 → 기존 임베드 task_id 집합과 비교.
    - --dry-run: 실제 add 없이 페이로드만 출력.
    - 기존 _queue.json 절대 수정 안 함.

사용:
    python scripts/migrate_queue_to_sheet.py --dry-run   # 미리보기
    python scripts/migrate_queue_to_sheet.py             # 실제 이관
"""
from __future__ import annotations

import argparse
import io
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

try:
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
except Exception:
    pass

_REPO = Path(__file__).resolve().parent.parent
QUEUE_PATH = _REPO / "status" / "_queue.json"

GAS_URL = (
    "https://script.google.com/macros/s/"
    "AKfycbxDwFkrxK1YIaEoSNcuw2MiHiZQ-7o5N6311ytksSyeEd86ZFOhLknOWqQgNArQvZ-7/exec"
)
AI_CATEGORY = "[7]AI배(C레벨)"

# _queue status → 시트 상태 (시트는 진행중/완료/보류 3종)
_STATUS_TO_SHEET = {
    "PENDING":     "대기",
    "IN_PROGRESS": "진행중",
    "DONE":        "완료",
    "ON_HOLD":     "보류",
    "폐기":        "완료",   # 폐기는 이관 대상 아님(아래서 필터)
}

# clevel → 담당자 표시명
_CLEVEL_DISPLAY = {
    "ceo": "AI CEO(웰리)", "cfo": "AI CFO(시뽀)", "chro": "AI CHRO(시로)",
    "cmo": "AI CMO(시모)", "coo": "AI COO(시우)", "cpo": "AI CPO(시포)",
    "cto": "AI CTO(시토)",
}

import re
_EMBED_RE = re.compile(r"===AI_QUEUE===\s*(.+?)\s*===END===", re.DOTALL)


def _existing_task_ids(dry_run: bool) -> set[str]:
    """시트에서 기존 AI배 행의 task_id 집합 반환(중복 방지용)."""
    if dry_run:
        return set()
    try:
        req = urllib.request.Request(GAS_URL + "?action=todo_list")
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.loads(r.read())
        rows = data.get("data", [])
        ids: set[str] = set()
        for row in rows:
            cat = str(row.get("카테고리", "")).strip()
            if "[7]" not in cat and "AI배" not in cat:
                continue
            content = str(row.get("내용", ""))
            m = _EMBED_RE.search(content)
            if m:
                try:
                    embed = json.loads(m.group(1))
                    tid = embed.get("task_id", "")
                    if tid:
                        ids.add(tid)
                except Exception:
                    pass
            # fallback: 업무명에서 task_id 추출 시도
            title = str(row.get("업무명", ""))
            # id 컬럼에 GAS 자동생성 ID가 있음 — 별도 추적 불필요(임베드 기준)
        return ids
    except Exception as e:
        print(f"[WARN] 시트 조회 실패(중복 체크 스킵): {e}", file=sys.stderr)
        return set()


def _build_embed(item: dict) -> str:
    """_queue 항목에서 ===AI_QUEUE=== 임베드 JSON 생성."""
    # 시트 컬럼으로 이미 표현되는 필드 제외: title(업무명), clevel(담당자), status(상태),
    # deadline(종료일), priority(난이도).
    # enqueued_at 은 시트 생성일(GAS 자동)과 다를 수 있어 임베드에 보존 → sync 시 원본값 복원.
    omit = {"title", "clevel", "status", "deadline", "priority"}
    embed: dict = {}
    for k, v in item.items():
        if k in omit:
            continue
        if v is None or (isinstance(v, str) and not v.strip()):
            continue
        embed[k] = v
    return (
        "===AI_QUEUE===\n"
        + json.dumps(embed, ensure_ascii=False)
        + "\n===END==="
    )


def _priority_to_difficulty(priority: str) -> str:
    p = str(priority or "").upper()
    if p == "P0":
        return "상"
    if p == "HIGH":
        return "상"
    return "중"  # NORMAL → 중


def _gas_add(payload: dict, dry_run: bool) -> tuple[bool, str]:
    """GAS todo_add POST. 성공 시 (True, id), 실패 시 (False, 오류)."""
    if dry_run:
        print(f"  [DRY-RUN] todo_add: {payload.get('title','')[:50]}")
        return True, "dry-run"

    body_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        GAS_URL,
        data=body_bytes,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            resp = json.loads(r.read())
        if resp.get("ok"):
            return True, str(resp.get("id", ""))
        return False, str(resp.get("error", "unknown"))
    except Exception as e:
        return False, str(e)


def load_queue_items() -> list[dict]:
    """_queue.json 에서 폐기 제외 전체 로드."""
    items = json.loads(QUEUE_PATH.read_text(encoding="utf-8"))
    return [x for x in items if "폐기" not in str(x.get("status", ""))]


def migrate(dry_run: bool = False) -> int:
    print(f"{'[DRY-RUN] ' if dry_run else ''}AI 배 시트 이관 시작")

    items = load_queue_items()
    print(f"  _queue 이관 대상: {len(items)}건")

    existing = _existing_task_ids(dry_run)
    if existing:
        print(f"  시트 기존 AI배 {len(existing)}건 (중복 스킵): {sorted(existing)}")

    ok_count = 0
    skip_count = 0
    fail_count = 0

    for item in items:
        tid = item.get("task_id", "")
        if tid in existing:
            print(f"  [SKIP] {tid} — 이미 시트에 있음")
            skip_count += 1
            continue

        note_from_item = item.get("note", "")
        embed_str = _build_embed(item)
        # 내용 = 사람용 note + 임베드 블록
        content = (note_from_item + "\n" if note_from_item else "") + embed_str

        status_sheet = _STATUS_TO_SHEET.get(str(item.get("status", "PENDING")), "대기")
        clevel = str(item.get("clevel", "ceo")).lower()
        owner = _CLEVEL_DISPLAY.get(clevel, f"AI {clevel.upper()}")
        deadline = str(item.get("deadline") or "")[:10]
        priority = str(item.get("priority", "NORMAL"))
        difficulty = _priority_to_difficulty(priority)

        payload = {
            "action": "todo_add",
            "title": str(item.get("title", "")),
            "category": AI_CATEGORY,
            "owner": owner,
            "status": status_sheet,
            "content": content,
            "difficulty": difficulty,
        }
        if deadline:
            payload["endDate"] = deadline

        ok, result = _gas_add(payload, dry_run)
        if ok:
            print(f"  [OK] {tid} → 시트 id={result}")
            ok_count += 1
        else:
            print(f"  [FAIL] {tid}: {result}", file=sys.stderr)
            fail_count += 1

        if not dry_run:
            time.sleep(0.5)  # GAS rate limit 방지

    print(f"\n결과: 추가={ok_count}, 스킵={skip_count}, 실패={fail_count}")
    return 0 if fail_count == 0 else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="_queue.json AI 배 → 구글시트 1회성 이관")
    ap.add_argument("--dry-run", action="store_true", help="실제 add 없이 페이로드만 출력")
    args = ap.parse_args(argv)
    return migrate(dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
