# -*- coding: utf-8 -*-
"""스태시에 갇힌 append-only 로그(.jsonl) 회수 (INC-034 · 2026-07-24 시토).

무엇을 하나
  `git pull/rebase --autostash` 의 되돌리기가 실패해 스태시에 갇힌 **덧붙이기 전용 로그(.jsonl)** 의
  줄을 꺼내, 현재 파일에 **없는 줄만** 덧붙인다.

왜 안전한가 (이 도구가 절대 하지 않는 것)
  - `.json`·`.md` 같은 **상태 파일은 손대지 않는다.** 그건 옛 사본이 최신을 덮을 수 있다.
    `.jsonl` 은 덧붙이기 전용이라 합집합이 곧 정답이고, 줄을 지우지 않으므로 되돌릴 게 없다.
  - 스태시를 **pop 하지 않는다**(pop 은 파일 하나만 충돌해도 통째로 실패하고, 공용 작업트리에
    충돌 표시를 남긴다 — 다른 세션이 그걸 그대로 커밋할 위험). 내용만 읽어 온다.
  - 기존 줄을 지우거나 바꾸지 않는다. **추가만 한다.**
  - 순서는 기록 시각으로 정렬해 되돌린다(원래 append 순서 복원).

사용:
  python scripts/recover_stashed_logs.py            # 무엇이 회수될지 미리보기
  python scripts/recover_stashed_logs.py --apply    # 실제 회수
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 기록 시각으로 쓰이는 키 후보(파일마다 이름이 다르다) — 정렬용.
TS_KEYS = ("logged_at", "observed_at", "ts", "timestamp", "at", "time", "date", "생성시각")


def git(*args: str) -> subprocess.CompletedProcess:
    # ★encoding 을 반드시 지정한다. 안 주면 윈도우 기본 cp949 로 디코딩하다
    #   한글이 든 git 출력에서 UnicodeDecodeError 로 죽는다(배10015 와 같은 함정).
    return subprocess.run(["git", *args], cwd=str(ROOT), capture_output=True,
                          text=True, encoding="utf-8", errors="replace", timeout=120)


def stash_refs() -> list[str]:
    r = git("stash", "list", "--format=%gd")
    if r.returncode != 0:
        return []
    return [x.strip() for x in (r.stdout or "").splitlines() if x.strip()]


def stash_jsonl_paths(ref: str) -> list[str]:
    r = git("stash", "show", "--name-only", ref)
    if r.returncode != 0:
        return []
    return [p.strip() for p in (r.stdout or "").splitlines() if p.strip().endswith(".jsonl")]


def blob_lines(ref: str, path: str) -> list[str]:
    r = git("show", f"{ref}:{path}")
    if r.returncode != 0:
        return []
    return [l for l in (r.stdout or "").splitlines() if l.strip()]


def sort_key(line: str) -> str:
    try:
        obj = json.loads(line)
    except Exception:
        return ""
    for k in TS_KEYS:
        v = obj.get(k)
        if isinstance(v, str) and v:
            return v
    return ""


def main() -> int:
    ap = argparse.ArgumentParser(description="스태시에 갇힌 .jsonl 로그 회수(추가만)")
    ap.add_argument("--apply", action="store_true", help="실제로 파일에 덧붙인다(기본은 미리보기)")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    refs = stash_refs()
    if not refs:
        print("스태시 없음 — 회수할 것 없음")
        return 0
    print(f"스태시 {len(refs)}개 검사")

    # path -> 회수 후보 줄(중복 제거, 스태시 여러 개에 같은 줄이 있을 수 있다)
    found: dict[str, set[str]] = {}
    for ref in refs:
        for path in stash_jsonl_paths(ref):
            for line in blob_lines(ref, path):
                found.setdefault(path, set()).add(line)

    if not found:
        print("스태시 안에 .jsonl 없음")
        return 0

    total_new = 0
    for path in sorted(found):
        target = ROOT / path
        cur = []
        if target.exists():
            cur = [l for l in target.read_text(encoding="utf-8").splitlines() if l.strip()]
        curset = set(cur)
        new = [l for l in found[path] if l not in curset]
        if not new:
            print(f"  = {path}: 회수할 줄 없음(현재 {len(cur)}줄)")
            continue
        new.sort(key=sort_key)
        total_new += len(new)
        print(f"  + {path}: 현재 {len(cur)}줄 → 회수 {len(new)}줄")
        for l in new[:2]:
            print(f"      예) {l[:110]}")
        if args.apply:
            if not target.exists():
                print(f"      건너뜀 — 원본 파일이 없다(새로 만들지 않는다)")
                continue
            with open(target, "a", encoding="utf-8") as f:
                for l in new:
                    f.write(l + "\n")

    print(f"\n합계 회수 대상 {total_new}줄 — {'회수 완료' if args.apply else '미리보기(--apply 로 실행)'}")
    if not args.apply:
        print("※ .json·.md 상태 파일은 대상이 아니다(옛 사본이 최신을 덮을 수 있어 의도적으로 제외).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
