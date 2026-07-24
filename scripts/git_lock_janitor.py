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
  index.lock       : ①주인 판정 ②파일 나이 > --min-age(기본 300초)
                     ③배타적 열기 성공(아무도 점유 안 함)
  next-index-*.lock: 파일명의 PID 가 **죽어 있을 것**(살아있으면 건너뜀)
  공통             : 지우기 전 격리 폴더로 **백업**(되돌릴 유일한 근거)

주인 판정 (2026-07-24 시토 보강 — 실측 재발로 드러난 구멍)
  처음엔 "살아있는 git 프로세스가 하나라도 있으면 보존"으로 근사했다. 이 저장소는
  워처·예약러너가 짧은 git 명령을 쉴 새 없이 돌려서, 그 근사가 **동전던지기**가 된다.
  실측(2026-07-24 09:04, 연속 3회 조회): 살아있는 git PID 가 [1504,1572] → [23800] → [] 로
  매번 달랐다. 그 사이 index.lock 은 **84분째** 남아 주인 PID 3288 은 이미 죽어 있었고,
  청소기는 우연히 빈 순간에 걸려야만 치울 수 있었다. 그래서 84분을 버텼다.

  본질 = "git 프로세스가 살아있다" ≠ "이 잠금의 주인이 살아있다".
  보강 = index.lock 과 **같은 순간(±OWNER_WINDOW 초)** 에 생긴 `next-index-<PID>.lock` 을
  주인으로 귀속시킨다. 우리 커밋 경로는 전부 임시 인덱스를 쓰므로 짝이 남는다.
    · 주인 PID 살아있음 → 나이·프로세스 수와 무관하게 **무조건 보존**(더 엄격해진다)
    · 주인 PID 죽음     → 무관한 git 프로세스가 떠 있어도 스테일로 판정
    · 주인 못 찾음      → 종전대로 보수적 판단(살아있는 git 프로세스 있으면 보존)

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
OWNER_WINDOW = 5  # 초 — index.lock 과 이만큼 안에 생긴 next-index-<PID>.lock 을 같은 주인으로 본다


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


def debris_pid(path: Path) -> int | None:
    try:
        return int(path.stem.rsplit("-", 1)[1])
    except (ValueError, IndexError):
        return None


def attribute_owner(index_lock: Path, debris: list[Path]) -> tuple[str, int | None]:
    """index.lock 의 주인을 임시 인덱스 잔해로 귀속. ('alive'|'dead'|'unknown', pid)."""
    try:
        il_mtime = index_lock.stat().st_mtime
    except OSError:
        return "unknown", None
    # 시간창 안 후보를 **전부** 본다. 하나라도 살아있으면 살아있는 쪽이 이긴다 —
    # 첫 짝만 보고 끊으면 파일명 정렬 운에 따라 산 주인을 놓치고 잠금을 지울 수 있다.
    candidates = []
    for f in debris:
        pid = debris_pid(f)
        if pid is None:
            continue
        try:
            f_mtime = f.stat().st_mtime
        except OSError:
            continue  # 다른 세션이 그 사이 치웠다 — 귀속 근거로 못 쓴다
        if abs(f_mtime - il_mtime) <= OWNER_WINDOW:
            candidates.append(pid)
    if not candidates:
        return "unknown", None
    for pid in candidates:
        if pid_alive(pid):
            return "alive", pid
    return "dead", candidates[0]


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
        owner, owner_pid = attribute_owner(il, found["debris"])
        reasons = []
        if owner == "alive":
            # 주인이 살아있으면 다른 조건과 무관하게 보존 — 종전보다 엄격하다.
            reasons.append(f"주인 PID {owner_pid} 가 살아있음 — 진짜 작업 중")
        elif owner == "dead":
            print(f"index.lock: 주인 PID {owner_pid} 종료 확인(임시 인덱스 잔해로 귀속)")
        elif live:
            reasons.append(f"주인 불명 + 살아있는 git 프로세스 {len(live)}개 — 진짜 작업 중일 수 있음")
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
