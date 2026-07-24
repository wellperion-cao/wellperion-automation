# -*- coding: utf-8 -*-
"""git_lock_janitor 주인 귀속 판정 검증 (배9889 · 2026-07-24 시토).

왜 이 테스트가 있나
  청소기는 처음에 "살아있는 git 프로세스가 하나라도 있으면 보존"으로 근사했다.
  이 저장소는 워처·예약러너가 짧은 git 명령을 쉴 새 없이 돌려서 그 근사가 동전던지기가 되고,
  실제로 죽은 index.lock 이 84분을 버텼다(2026-07-24 09:04 실측).
  귀속 판정은 그 구멍을 막는 장치다 — 되돌아가지 않게 여기서 고정한다.

  ★가장 중요한 케이스 = "죽은 짝과 산 짝이 같은 시간창에 있으면 **산 쪽이 이긴다**".
  이게 깨지면 살아있는 작업의 잠금을 지워 인덱스를 깨뜨린다.
"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import git_lock_janitor as J  # noqa: E402

ALIVE = os.getpid()   # 지금 이 프로세스 = 확실히 살아있다
DEAD = 999999         # 존재하지 않는 PID


def _fixture():
    tmp = Path(tempfile.mkdtemp())
    il = tmp / "index.lock"
    il.write_bytes(b"x")
    return tmp, il, il.stat().st_mtime


def _debris(tmp, base, pid, offset):
    f = tmp / ("next-index-%d.lock" % pid)
    f.write_bytes(b"y")
    os.utime(f, (base + offset, base + offset))
    return f


def _run(cases):
    fails = 0
    for name, make, want in cases:
        tmp, il, base = _fixture()
        got = J.attribute_owner(il, make(tmp, base))[0]
        ok = got == want
        fails += 0 if ok else 1
        print("%s %-40s 기대=%-8s 실제=%s" % ("PASS" if ok else "FAIL", name, want, got))
    return fails


CASES = [
    ("주인 살아있음 → 보존",
     lambda t, b: [_debris(t, b, ALIVE, 1)], "alive"),
    ("주인 죽음 → 스테일",
     lambda t, b: [_debris(t, b, DEAD, 2)], "dead"),
    ("★죽은짝+산짝 공존 → 산 쪽이 이긴다",
     lambda t, b: [_debris(t, b, DEAD, 1), _debris(t, b, ALIVE, 2)], "alive"),
    ("★산짝이 파일명 정렬상 뒤여도 산 쪽이 이긴다",
     lambda t, b: [_debris(t, b, 11111, 1), _debris(t, b, ALIVE, 2)]
     if ALIVE > 11111 else [_debris(t, b, ALIVE, 1), _debris(t, b, 99999999, 2)], "alive"),
    ("짝이 시간창 밖 → 주인 불명(보수적 판단으로 넘김)",
     lambda t, b: [_debris(t, b, DEAD, 600)], "unknown"),
    ("잔해 없음 → 주인 불명",
     lambda t, b: [], "unknown"),
    ("짝이 스캔 중 사라짐 → 주인 불명(예외 아님)",
     lambda t, b: [t / "next-index-4242.lock"], "unknown"),
]


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    n = _run(CASES)
    print("\n결과: %s" % ("전부 통과" if n == 0 else "%d건 실패" % n))
    sys.exit(1 if n else 0)
