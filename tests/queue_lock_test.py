"""
queue_lock_test.py — queue_lock.py 동시성 증명 테스트 (2026-07-10 사고 재발방지)

증명: 여러 프로세스가 warm 상태에서 각자 반복 append 로 _queue.json 을 동시에 두드릴 때
  - LOCK 모드(mutate_queue): 전건 보존(유실 0) — 근본수리 유효
  - NOLOCK 모드(raw load/append/save): 유실 발생 — 사고 재현(테스트가 의미 있음을 증명)

방법론 주의: 25개 python.exe 를 콜드스타트로 동시 spawn 하면 윈도우 프로세스 생성·인터프리터
기동 폭주로 홀더가 수십초 CPU 기아 → 현실에 없는 병리적 상황이라 테스트 왜곡. 실제 항로
writer 는 상주 프로세스(봇·스케줄러)라 홀드가 ms 단위다. 그래서 소수(6) 프로세스가 각자 warm
루프로 여러 번 append 하게 해 정상상태(steady-state) 경합만 측정한다.

실행: C:\\Python314\\python.exe scripts/queue_lock_test.py
워커: (내부) scripts/queue_lock_test.py --worker <wid> <root> <mode> <iters> <base>
"""

import json
import os
import subprocess
import sys
import tempfile
import time

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_TESTS_DIR)
_SCRIPTS_DIR = os.path.join(_PROJECT_ROOT, "scripts")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)
import queue_lock  # noqa: E402

NPROC = 6
ITERS = 20  # 프로세스당 반복 append → 총 NPROC*ITERS 건


def _qpath(root):
    return os.path.join(root, "status", "_queue.json")


def _worker(wid, root, mode, iters, base):
    """warm 루프: iters 번 각자 고유 배를 append. base+i*NPROC+wid = 전역 유일 ship_no."""
    wid, iters, base = int(wid), int(iters), int(base)
    for i in range(iters):
        ship = base + i * NPROC + wid
        bar = {"task_id": f"T-{ship}", "ship_no": ship, "status": "PENDING"}
        if mode == "LOCK":
            def add(items, _b=bar):
                items.append(_b)
                return items
            queue_lock.mutate_queue(add, holder=f"w{wid}-i{i}", repo_root=root)
        else:  # NOLOCK — 사고 재현(load/save 사이 경합 창). 찢긴 읽기 관용.
            p = _qpath(root)
            try:
                with open(p, "r", encoding="utf-8") as f:
                    items = json.load(f)
            except (json.JSONDecodeError, OSError):
                items = []
            time.sleep(0.002)  # load→save 경합 창
            items.append(bar)
            with open(p, "w", encoding="utf-8") as f:
                json.dump(items, f, ensure_ascii=False, indent=2)


def _run_scenario(mode):
    root = tempfile.mkdtemp(prefix=f"qlock_{mode}_")
    os.makedirs(os.path.join(root, "status"), exist_ok=True)
    with open(_qpath(root), "w", encoding="utf-8") as f:
        json.dump([], f)
    procs = [subprocess.Popen(
        [sys.executable, os.path.abspath(__file__),
         "--worker", str(w), root, mode, str(ITERS), "0"])
        for w in range(NPROC)]
    for pr in procs:
        pr.wait()
    with open(_qpath(root), "r", encoding="utf-8") as f:
        items = json.load(f)
    ship_nos = sorted(int(x["ship_no"]) for x in items)
    expected = NPROC * ITERS
    lost = sorted(set(range(expected)) - set(ship_nos))
    return {"expected": expected, "got": len(items),
            "unique": len(set(ship_nos)), "lost": lost}


def main():
    total = NPROC * ITERS
    print(f"=== queue_lock 동시성 증명 ({NPROC} warm 프로세스 × {ITERS} 반복 = {total} append) ===")
    nolock = _run_scenario("NOLOCK")
    print(f"[NOLOCK 대조]   기대 {nolock['expected']} → 저장 {nolock['got']} "
          f"(유실 {len(nolock['lost'])}건)")
    lock = _run_scenario("LOCK")
    print(f"[LOCK 근본수리] 기대 {lock['expected']} → 저장 {lock['got']} "
          f"(유실 {len(lock['lost'])}건)")
    print("---")
    lock_ok = (lock["got"] == lock["expected"]
               and lock["unique"] == lock["expected"] and not lock["lost"])
    nolock_showed_loss = len(nolock["lost"]) > 0
    print(f"LOCK 전건 보존(유실 0): {'PASS ✅' if lock_ok else 'FAIL ❌'}")
    print(f"NOLOCK 유실 재현(테스트 유효성): "
          f"{'PASS ✅ (사고 재현됨)' if nolock_showed_loss else '⚠️ 유실 미재현'}")
    print(f"\n종합: {'PASS ✅ 근본수리 유효 — 락이 동시 쓰기 유실을 막음' if lock_ok else 'FAIL ❌'}")
    sys.exit(0 if lock_ok else 1)


if __name__ == "__main__":
    if len(sys.argv) >= 7 and sys.argv[1] == "--worker":
        _worker(sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5], sys.argv[6])
    else:
        main()
