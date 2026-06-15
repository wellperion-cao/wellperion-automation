#!/usr/bin/env python3
"""발행검증 대기 체커 — INC-003 가드.

review_queue.json에서 status='발행검증대기' 항목을 나열한다.
웰리 IG↔M5 대조(발행완료 도장)가 아직 안 된 건을 가시화해
INC-003(발행됐는데 검증 조용히 방치) 재발을 막는다.

사용:
  python ssot/publish_verify_pending.py
"""
from __future__ import annotations

import json
import sys
import io
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

QUEUE_PATH = (
    Path(__file__).parent.parent
    / "3. 웰페리온 가이드"
    / "cmo"
    / "review"
    / "review_queue.json"
)

TARGET_STATUS = "발행검증대기"


def main() -> int:
    if not QUEUE_PATH.exists():
        print(f"[ERROR] 큐 파일 없음: {QUEUE_PATH}")
        return 1

    queue: list[dict] = json.loads(QUEUE_PATH.read_text(encoding="utf-8"))
    pending = [item for item in queue if item.get("status") == TARGET_STATUS]

    print("=" * 50)
    print(f"  발행검증 대기 체커 (INC-003 가드)")
    print("=" * 50)

    if not pending:
        print(f"\n✅ 발행검증 대기 없음 — 모든 발행 건 검증 완료.\n")
        return 0

    print(f"\n⚠️  발행검증 대기 {len(pending)}건 — 웰리 IG↔M5 대조 필요:\n")
    for item in pending:
        item_id = item.get("id", "-")
        title = item.get("title", "(제목 없음)")
        folder = item.get("folder", "")
        channel = item.get("channel", "")
        print(f"  [{item_id}] {title}")
        if channel:
            print(f"        채널: {channel}")
        if folder:
            print(f"        폴더: {folder}")
        print()

    print(f"→ 위 {len(pending)}건을 IG 실제 게시물과 M5 큐 대조 후 '발행완료'로 닫을 것.\n")
    return 1


if __name__ == "__main__":
    sys.exit(main())
