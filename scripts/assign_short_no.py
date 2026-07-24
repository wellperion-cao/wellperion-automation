"""
assign_short_no.py
표시용 짧은 번호(short_no) 배정 — 2026-07-24 시토, 배10012 2단계.

배경: ship_no가 5자리(예 10012)까지 길어져 GM이 부르기 불편해졌다. 하지만 실제
ship_no를 재부여하는 안(1안)은 위험하다고 판정됐다(status/briefs/시토_배번호재부여_
조사_20260724.md 참조) — hangro_review.py 결정원장·northstar_log.jsonl 조인이
ship_no를 키로 영속 저장하고, 아카이브에 이미 저번호 중복이 236개 있다.

채택안(2안): ship_no는 절대 안 건드리고, 화면 표시 전용 새 필드 `short_no`를
열린 배(PENDING/IN_PROGRESS)에만 추가로 부여한다. 내부 조인·키·저장은 전부
기존 ship_no 그대로 유지 — short_no는 render 단계에서만 읽힌다.

배정 규칙(설명 가능해야 함 — 무작위 금지):
  담당(clevel)을 CLEVEL_ORDER(ceo→cfo→chro→cmo→coo→cpo→cto) 순으로 묶고,
  그 안에서는 기존 ship_no 오름차순 정렬 후 1부터 순서대로 배정한다.

재사용 금지: 배가 닫혀도 이미 배정된 short_no 필드는 지우지 않는다(그대로 보존
— queue_archive_sweep.py는 항목을 통째로 옮기기만 하므로 별도 조치 불요). 신규
배정 시 다음 번호(next_short_no)는 큐 안의 모든 항목(열림+닫힘 무관, 필드가
남아있으면 전부) + 아카이브까지의 max+1이라 — 가장 높은 번호를 가진 배가
방금 닫혔어도 그 번호를 재사용하지 않는다.

멱등: 이미 short_no가 있는 배는 절대 건드리지 않는다.
"""
from __future__ import annotations

import json
import os
import sys

_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

ARCHIVE_PATH = os.path.normpath(
    os.path.join(_SCRIPTS_DIR, "..", "status", "_queue_archive.json")
)

# 약속 SSOT(CLAUDE.md §1)에 나온 7 C-Level 표 순서 그대로 — 새로 정하지 않고 기존 정본 재사용.
CLEVEL_ORDER = ["ceo", "cfo", "chro", "cmo", "coo", "cpo", "cto"]
OPEN_STATUSES = ("PENDING", "IN_PROGRESS")


def _archive_max_short_no() -> int:
    """아카이브에 이미 short_no가 있으면(향후 배가 닫히며 이 필드를 달고 넘어간
    경우) 그 max도 반영 — 재사용 방지 이중 안전."""
    try:
        with open(ARCHIVE_PATH, "r", encoding="utf-8") as f:
            arc = json.load(f)
    except Exception:
        return 0
    m = 0
    for t in arc:
        if isinstance(t, dict) and t.get("short_no") is not None:
            try:
                m = max(m, int(t["short_no"]))
            except (TypeError, ValueError):
                pass
    return m


def next_short_no(queue: list) -> int:
    """다음에 배정할 short_no.

    '현재 열린 배 최대값+1'과 결과가 보통 같지만, 큐 안의 항목은 상태(open/closed)
    무관하게 전부 스캔한다 — 가장 높은 short_no를 가진 배가 방금 닫혔어도(필드는
    안 지워지므로) 그 번호를 다시 내주지 않는다. 아카이브 max도 함께 본다.
    """
    m = _archive_max_short_no()
    for t in queue:
        if isinstance(t, dict) and t.get("short_no") is not None:
            try:
                m = max(m, int(t["short_no"]))
            except (TypeError, ValueError):
                pass
    return m + 1


def _sort_key(t: dict):
    cl = str(t.get("clevel", "")).lower()
    idx = CLEVEL_ORDER.index(cl) if cl in CLEVEL_ORDER else len(CLEVEL_ORDER)
    try:
        sn = int(t.get("ship_no") or 0)
    except (TypeError, ValueError):
        sn = 0
    return (idx, sn)


def backfill(queue: list) -> list[tuple[int, str]]:
    """열린 배 중 short_no 없는 항목에만 배정(멱등 — 있는 건 절대 안 건드림).
    반환: [(short_no, task_id), ...] 신규 배정분만."""
    targets = [
        t for t in queue
        if isinstance(t, dict)
        and t.get("status") in OPEN_STATUSES
        and t.get("short_no") is None
    ]
    targets.sort(key=_sort_key)

    next_no = next_short_no(queue)
    assigned: list[tuple[int, str]] = []
    for t in targets:
        t["short_no"] = next_no
        assigned.append((next_no, t.get("task_id", "")))
        next_no += 1
    return assigned


def main() -> int:
    from queue_lock import mutate_queue  # noqa: E402  (같은 scripts/ 폴더)

    result: dict = {}

    def mutator(queue):
        result["assigned"] = backfill(queue)
        return queue

    mutate_queue(mutator, holder="assign-short-no")

    assigned = result.get("assigned", [])
    if assigned:
        print(f"[assign_short_no] 신규 배정 {len(assigned)}건:")
        for no, tid in assigned:
            print(f"  short_no={no}  {tid}")
    else:
        print("[assign_short_no] 배정할 항목 없음(멱등 확인)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
