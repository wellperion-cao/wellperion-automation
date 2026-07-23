# -*- coding: utf-8 -*-
"""git 죽은 잠금 청소기 (배9889 · 2026-07-23 시토).

무엇을 하나
  `.git/index.lock` 과 `.git/next-index-<PID>.lock` 중 **주인이 확실히 죽은 것만** 치운다.
  살아있는 git 작업이 쓰는 잠금은 **절대 건드리지 않는다** — 오판하면 인덱스가 깨진다.

왜 필요한가 (실측 근거)
  - 죽은 `index.lock` 이 남으면 그 뒤 **전 C-Level의 커밋이 전부 실패**한다
    ("Another git process seems to be running"). 자동화들이 재시도로 넘겨서
    '느리다'로만 보였고 결함으로 인지되지 않았다(시우 발견, 2026-07-23).
  - `next-index-<PID>.lock` 은 `git commit -- <경로>` 가 쓰는 임시 인덱스다.
    우리 자동 커밋 6곳이 전부 그 형태라, 그 프로세스가 중간에 죽으면 잔해가 남는다.
    2026-07-23 실측 23개(07-20부터 누적) — git 프로세스가 반복 강제종료된다는 신호.

안전 규칙 (이 순서로 전부 통과해야만 지운다)
  index.lock       : ①살아있는 git 프로세스 0개 ②파일 나이 > --min-age(기본 300초)
                     ③배타적 열기 성공(아무도 점유 안 함)
  next-index-*.lock: 파일명의 PID 가 **죽어 있을 것**(살아있으면 건너뜀)
  공통             : 지우기 전 격리 폴더로 **백업**(되돌릴 유일한 근거)

기본은 조회만 한다. 실제로 지우려면 --apply 를 명시해야 한다.

사용:
  python scripts/git_lock_janitor.py              # 진단만
  python scripts/git_lock_janitor.py --apply      # 안전 조건 통과분만 정리
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GIT_DIR = ROOT / ".git"
QUARANTINE = ROOT / ".git" / "lock-quarantine"
DEFAULT_MIN_AGE = 300  # 초


def live_git_pids() -> list[int]:
    """살아있는 git.exe PID 목록. 조회 실패 시 None 이 아니라 '알 수 없음'을 뜻하는 예외."""
    out = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "(Get-Process -Name git -ErrorAction SilentlyContinue).Id -join ','"],
        capture_output=True, text=True, timeout=60,
    )
    if out.returncode != 0:
        raise RuntimeError(f"git 프로세스 조회 실패(rc={out.returncode})")
    raw = (out.stdout or "").strip()
    return [int(x) for x in raw.split(",") if x.strip().isdigit()]


def pid_alive(pid: int) -> bool:
    out = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         f"if (Get-Process -Id {pid} -ErrorAction SilentlyContinue) {{ 'Y' }} else {{ 'N' }}"],
        capture_output=True, text=True, timeout=60,
    )
    return (out.stdout or "").strip() == "Y"


def exclusively_openable(path: Path) -> bool:
    """아무도 점유하지 않는지 확인 — 윈도우에서 열려 있으면 여기서 실패한다."""
    try:
        with open(path, "r+b"):
            return True
    except OSError:
        return False


def backup(path: Path) -> Path:
    QUARANTINE.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = QUARANTINE / f"{path.name}.{stamp}"
    shutil.copy2(path, dest)
    return dest


def scan() -> dict:
    index_lock = GIT_DIR / "index.lock"
    debris = sorted(GIT_DIR.glob("next-index-*.lock"))
    return {"index_lock": index_lock if index_lock.exists() else None, "debris": debris}


def main() -> int:
    p = argparse.ArgumentParser(description="git 죽은 잠금 청소기 (기본=진단만)")
    p.add_argument("--apply", action="store_true", help="안전 조건 통과분을 실제로 정리")
    p.add_argument("--min-age", type=int, default=DEFAULT_MIN_AGE,
                   help=f"index.lock 을 죽었다고 보기까지의 최소 경과 초(기본 {DEFAULT_MIN_AGE})")
    args = p.parse_args()

    try:
        live = live_git_pids()
    except Exception as exc:
        print(f"[중단] {exc} — 안전 확인 불가라 아무것도 건드리지 않습니다.")
        return 1

    found = scan()
    print(f"살아있는 git 프로세스: {len(live)}개 {live if live else ''}")

    # ── index.lock ────────────────────────────────────────────────────────
    il = found["index_lock"]
    if il is None:
        print("index.lock: 없음")
    else:
        age = time.time() - il.stat().st_mtime
        reasons = []
        if live:
            reasons.append(f"살아있는 git 프로세스 {len(live)}개 — 진짜 작업 중일 수 있음")
        if age < args.min_age:
            reasons.append(f"생긴 지 {int(age)}초(기준 {args.min_age}초 미만)")
        if not exclusively_openable(il):
            reasons.append("파일을 누군가 점유 중")
        if reasons:
            print(f"index.lock: 보존 — {' / '.join(reasons)}")
        elif not args.apply:
            print(f"index.lock: 스테일로 판정({int(age)}초 경과) — --apply 시 정리")
        else:
            b = backup(il)
            il.unlink()
            print(f"index.lock: 정리 완료(백업 {b.name})")

    # ── next-index-<PID>.lock ─────────────────────────────────────────────
    debris = found["debris"]
    if not debris:
        print("next-index 잔해: 없음")
        return 0

    dead, alive_kept = [], []
    for f in debris:
        try:
            pid = int(f.stem.rsplit("-", 1)[1])
        except (ValueError, IndexError):
            alive_kept.append((f, "PID 파싱 불가"))
            continue
        if pid_alive(pid):
            alive_kept.append((f, f"PID {pid} 살아있음"))
        else:
            dead.append(f)

    print(f"next-index 잔해: 총 {len(debris)}개 · 주인 죽음 {len(dead)} · 보존 {len(alive_kept)}")
    for f, why in alive_kept:
        print(f"  보존 {f.name} — {why}")

    if not args.apply:
        print(f"  (--apply 시 {len(dead)}개 정리)")
        return 0

    removed = 0
    for f in dead:
        if not exclusively_openable(f):
            print(f"  건너뜀 {f.name} — 점유 중")
            continue
        backup(f)
        f.unlink()
        removed += 1
    print(f"  정리 완료 {removed}개 (백업 → .git/lock-quarantine/)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
