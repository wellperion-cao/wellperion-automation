#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""review_queue_recover.py — 사라진 검수큐 항목을 git 이력에서 되찾는 **조회** 도구.

가드(precommit_queue_guard.py)는 앞으로의 유실을 막지만, 이미 커밋된 과거 유실은
되돌리지 못한다(2026-07-21 AI하루 10편 — 다음날 재작업했다). 이 도구는 git 이력을
훑어 "예전엔 있었는데 지금 없는" 항목을 찾아 원본 JSON 을 그대로 보여준다.

**읽기 전용이다. 어떤 파일도 쓰지 않는다.** 복구는 사람이 내용을 확인한 뒤 직접 한다
(작업트리를 바꾸는 git 명령을 쓰지 않는 것이 원칙 — 동시 세션·자동화가 함께 돈다).

사용:
  python scripts/review_queue_recover.py --missing              # 사라진 항목 목록
  python scripts/review_queue_recover.py --missing --limit 500  # 더 깊이 훑기
  python scripts/review_queue_recover.py --id CMO-2026-07-21-AIDAY01-아침항로
                                                                # 그 항목 원본 JSON 출력
  python scripts/review_queue_recover.py --missing --file status/_queue.json
                                                                # _queue.json 도 동일 조회

종료코드: 0 = 정상(사라진 항목 유무와 무관) / 2 = 인자·경로 오류
"""
from __future__ import annotations

import argparse
import io
import json
import subprocess
import sys

DEFAULT_FILE = "3. 웰페리온 가이드/cmo/review/review_queue.json"
ID_KEYS = ("id", "task_id", "ship_no")

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
except Exception:
    pass


def _git(args: list[str]) -> tuple[int, bytes]:
    p = subprocess.run(["git"] + args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return p.returncode, p.stdout


def _item_id(item) -> str | None:
    if not isinstance(item, dict):
        return None
    for k in ID_KEYS:
        v = item.get(k)
        if v not in (None, ""):
            return str(v)
    return None


def _load_at(rev: str, path: str):
    """rev 시점의 파일을 배열로. 없거나 파싱 불가면 None."""
    rc, out = _git(["cat-file", "-p", f"{rev}:{path}"])
    if rc != 0 or not out:
        return None
    try:
        data = json.loads(out.decode("utf-8", "replace"))
    except Exception:
        return None
    return data if isinstance(data, list) else None


def _commits(path: str, limit: int) -> list[tuple[str, str, str]]:
    """(hash, 날짜, 제목) — 그 파일을 건드린 최근 커밋 순."""
    rc, out = _git([
        "log", f"-n{limit}", "--format=%H\x1f%ad\x1f%s", "--date=format:%Y-%m-%d %H:%M",
        "--", path,
    ])
    if rc != 0:
        return []
    rows = []
    for line in out.decode("utf-8", "replace").splitlines():
        parts = line.split("\x1f")
        if len(parts) == 3:
            rows.append((parts[0], parts[1], parts[2]))
    return rows


def cmd_missing(path: str, limit: int) -> int:
    current = _load_at("HEAD", path)
    if current is None:
        print(f"[ERROR] HEAD 에서 배열로 읽지 못함: {path}", file=sys.stderr)
        return 2
    now_ids = {i for i in (_item_id(x) for x in current) if i}

    commits = _commits(path, limit)
    print(f"현재(HEAD) {len(current)}건 · 이력 {len(commits)}커밋 훑는 중 — {path}\n")

    # id → (마지막으로 존재한 커밋, 날짜, 제목, 항목)
    lost: dict[str, tuple[str, str, str, dict]] = {}
    for h, date, subj in commits:            # 최신 → 과거 순
        items = _load_at(h, path)
        if items is None:
            continue
        for it in items:
            iid = _item_id(it)
            if iid and iid not in now_ids and iid not in lost:
                lost[iid] = (h, date, subj, it)

    if not lost:
        print("사라진 항목 없음 — 이력의 모든 항목이 현재 큐에 살아있습니다.")
        return 0

    print(f"⚠️ 현재 큐에서 사라진 항목 {len(lost)}건 (마지막으로 존재하던 커밋 기준)\n")
    for iid, (h, date, subj, it) in sorted(lost.items(), key=lambda kv: kv[1][1], reverse=True):
        status = str(it.get("status") or "?")
        title = str(it.get("title") or "")[:52]
        print(f"  - {iid}")
        print(f"      [{status}] {title}")
        print(f"      마지막 존재: {h[:9]} {date} — {subj[:60]}")
    print(
        "\n원본 JSON 보기:  python scripts/review_queue_recover.py --id <위 ID>"
        "\n※ 이 도구는 읽기 전용입니다. 되살리기는 내용을 확인한 뒤 사람이 직접 하세요."
    )
    return 0


def cmd_show(path: str, limit: int, wanted: str) -> int:
    for h, date, subj in _commits(path, limit):
        items = _load_at(h, path)
        if items is None:
            continue
        for it in items:
            if _item_id(it) == wanted:
                print(f"# {wanted}")
                print(f"# 출처 커밋: {h} ({date}) — {subj}")
                print(json.dumps(it, ensure_ascii=False, indent=2))
                return 0
    print(f"[INFO] 최근 {limit}커밋 이력에서 id={wanted} 를 찾지 못했습니다."
          f" --limit 을 늘려 보세요.", file=sys.stderr)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="검수큐(review_queue.json)에서 사라진 항목을 git 이력에서 조회 (읽기 전용)")
    ap.add_argument("--file", default=DEFAULT_FILE, help="대상 파일(repo 상대경로)")
    ap.add_argument("--limit", type=int, default=300, help="훑을 커밋 수 (기본 300)")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--missing", action="store_true", help="사라진 항목 목록")
    g.add_argument("--id", help="해당 항목의 원본 JSON 출력")
    a = ap.parse_args()

    if a.missing:
        return cmd_missing(a.file, a.limit)
    return cmd_show(a.file, a.limit, a.id)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(0)
