# -*- coding: utf-8 -*-
"""git_merge_queue.py — _queue.json 전용 git 머지 드라이버 (2026-06-19 시토).

여러 세션(PC·모바일·봇)이 각자 다른 '배'를 _queue.json 에 추가하면 JSON 배열이
rebase/merge 때 텍스트 충돌 → 자동 push 가 충돌로 멈췄다(경고 스팸의 근본 원인).
이 드라이버는 두 버전을 task_id 합집합으로 안전 병합해 충돌을 없앤다.

규칙(데이터 무손실 원칙):
  - 두 쪽의 모든 task_id 를 보존(union) — 어느 배도 잃지 않는다.
  - 같은 task_id 가 양쪽에 있으면 '더 진행된' 버전을 채택(terminal/DONE/폐기 > 그 외),
    동급이면 ours(현재 브랜치) 유지.
  - 순서: ours 순서 우선 + theirs 에만 있는 신규 배는 뒤에 덧붙임(G1 이 날짜로 재정렬하므로 무해).
  - 파싱 실패·배열 아님 → exit 1 (git 이 정상 충돌 표시 — 절대 손상시키지 않음).

git 호출: python scripts/git_merge_queue.py %O %A %B   (%A 에 결과 기록, exit 0=성공)
"""
import json
import sys


def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _rank(item):
    """더 '최종' 상태일수록 높은 점수 — 충돌 시 완료/폐기본이 미완본을 이긴다."""
    if not isinstance(item, dict):
        return 0
    if item.get("terminal") is True:
        return 3
    st = str(item.get("status") or "")
    if st in ("DONE", "폐기"):
        return 2
    return 1


def main():
    if len(sys.argv) < 4:
        return 1
    base_p, ours_p, theirs_p = sys.argv[1], sys.argv[2], sys.argv[3]
    try:
        ours = _load(ours_p)
        theirs = _load(theirs_p)
    except Exception:
        return 1  # 파싱 실패 → git 정상 충돌로 폴백
    if not isinstance(ours, list) or not isinstance(theirs, list):
        return 1

    merged = []
    seen = {}  # task_id → merged 인덱스
    for item in ours:
        k = item.get("task_id") if isinstance(item, dict) else None
        if k is None:
            merged.append(item)
            continue
        seen[k] = len(merged)
        merged.append(item)
    for item in theirs:
        k = item.get("task_id") if isinstance(item, dict) else None
        if k is None:
            merged.append(item)
            continue
        if k in seen:
            cur = merged[seen[k]]
            if _rank(item) > _rank(cur):
                merged[seen[k]] = item  # 더 진행된 버전 채택
        else:
            merged.append(item)  # theirs 에만 있는 신규 배 보존

    try:
        with open(ours_p, "w", encoding="utf-8") as f:
            json.dump(merged, f, ensure_ascii=False, indent=2)
            f.write("\n")
    except Exception:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
