"""
test_git_lock.py — git_lock.py 동시성 자기테스트
격리된 tempfile git repo에서만 실행 — 라이브 repo 무오염.
3프로세스 × 50커밋 = 150커밋 무손실 실증.
"""

import json
import multiprocessing
import os
import shutil
import subprocess
import sys
import tempfile

# Windows cp949 콘솔에서 비-ASCII(em-dash 등) print 크래시 방지 → stdout/err utf-8 고정
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

# scripts/ 디렉터리를 sys.path에 추가 (임포트 보장)
_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)


# ── 워커 함수 (별도 프로세스) ─────────────────────────────────────────────
def _worker(temp_repo, worker_id, iters, result_queue):
    """
    각 iter: status_{worker_id}.json 읽어 count+1 쓰고 git_commit_push.
    push=False (원격 없음), pull_autostash=False.
    성공/실패 카운트를 result_queue에 push.
    """
    # 자식 프로세스에서 sys.path 재설정
    if _SCRIPTS_DIR not in sys.path:
        sys.path.insert(0, _SCRIPTS_DIR)

    import git_lock as gl

    json_path = os.path.join(temp_repo, f"status_{worker_id}.json")
    errors = []

    for i in range(iters):
        # 읽기 (없으면 count=0 초기화)
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            count = data.get("count", 0)
        except (FileNotFoundError, json.JSONDecodeError):
            count = 0

        # +1 쓰기
        new_count = count + 1
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump({"count": new_count}, f)

        # git lock으로 커밋
        try:
            gl.git_commit_push(
                paths=[json_path],
                message=f"w{worker_id} #{i}",
                holder=f"w{worker_id}",
                repo_root=temp_repo,
                pull_autostash=False,
                push=False,
                cwd=temp_repo,
            )
        except Exception as e:
            errors.append(f"iter={i} {e}")

    result_queue.put({"worker_id": worker_id, "errors": errors})


# ── 메인 ──────────────────────────────────────────────────────────────────
def main():
    NUM_WORKERS = 3
    ITERS = 50
    TOTAL_COMMITS = NUM_WORKERS * ITERS

    print(f"[test_git_lock] 격리 temp repo 생성 중...")
    temp_repo = tempfile.mkdtemp(prefix="welperion_gitlock_test_")

    try:
        # 임시 git repo 초기화
        def rg(args):
            r = subprocess.run(
                ["git"] + args, cwd=temp_repo,
                capture_output=True, text=True
            )
            if r.returncode != 0:
                raise RuntimeError(f"git {args}: {r.stderr.strip()}")
            return r

        rg(["init"])
        rg(["config", "user.email", "test@wellperion.com"])
        rg(["config", "user.name", "TestRunner"])
        # 초기 빈 커밋 (1번)
        init_file = os.path.join(temp_repo, ".gitkeep")
        with open(init_file, "w") as f:
            f.write("")
        rg(["add", ".gitkeep"])
        rg(["commit", "-m", "init"])

        print(f"[test_git_lock] 워커 {NUM_WORKERS}개 × {ITERS}회 동시 시작...")

        result_queue = multiprocessing.Queue()
        workers = []
        for wid in range(NUM_WORKERS):
            p = multiprocessing.Process(
                target=_worker,
                args=(temp_repo, wid, ITERS, result_queue),
                daemon=False,
            )
            workers.append(p)

        for p in workers:
            p.start()
        for p in workers:
            p.join()

        # ── 검증 ──────────────────────────────────────────────────────────
        fail_reasons = []

        # 워커 에러 수집
        worker_errors = []
        while not result_queue.empty():
            res = result_queue.get()
            if res["errors"]:
                worker_errors.extend(res["errors"])

        # 1. 커밋 수 검증
        r = subprocess.run(
            ["git", "-C", temp_repo, "rev-list", "--count", "HEAD"],
            capture_output=True, text=True
        )
        actual_commits = int(r.stdout.strip())
        expected_commits = 1 + TOTAL_COMMITS  # 초기 커밋 1 + 워커 커밋
        if actual_commits != expected_commits:
            fail_reasons.append(
                f"커밋수 불일치: expected={expected_commits} actual={actual_commits}"
            )

        # 2. 각 status_{id}.json count == ITERS (손실 0)
        for wid in range(NUM_WORKERS):
            json_path = os.path.join(temp_repo, f"status_{wid}.json")
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                count = data.get("count", -1)
                if count != ITERS:
                    fail_reasons.append(
                        f"status_{wid}.json count={count} expected={ITERS}"
                    )
            except Exception as e:
                fail_reasons.append(f"status_{wid}.json 읽기 실패: {e}")

        # 3. 모든 json json.load PASS (위 루프에서 이미 검사됨)

        # 4. 워커 stderr / 에러에 index.lock / fatal 포함 여부
        index_lock_errors = [e for e in worker_errors if "index.lock" in e or "fatal" in e.lower()]
        if index_lock_errors:
            fail_reasons.append(f"index.lock/fatal 에러 발생: {index_lock_errors}")

        if worker_errors:
            fail_reasons.append(f"워커 에러 {len(worker_errors)}건: {worker_errors[:5]}")

        # 5. git_lock.log에 STEAL/TIMEOUT 비정상 건수
        log_path = os.path.join(temp_repo, "logs", "git_lock.log")
        steal_count = 0
        timeout_count = 0
        acquired_count = 0
        released_count = 0
        if os.path.exists(log_path):
            with open(log_path, "r", encoding="utf-8") as f:
                for line in f:
                    if "STEAL" in line:
                        steal_count += 1
                    if "TIMEOUT" in line:
                        timeout_count += 1
                    if "ACQUIRED" in line:
                        acquired_count += 1
                    if "RELEASED" in line:
                        released_count += 1

        if timeout_count > 0:
            fail_reasons.append(f"TIMEOUT {timeout_count}건 (비정상)")

        # ── 결과 출력 ──────────────────────────────────────────────────────
        print()
        print("=" * 60)
        print(f"  커밋 수:    {actual_commits} (expected {expected_commits})")
        print(f"  ACQUIRED:  {acquired_count}건")
        print(f"  RELEASED:  {released_count}건")
        print(f"  STEAL:     {steal_count}건 (경쟁 회수, 정상 가능)")
        print(f"  TIMEOUT:   {timeout_count}건")
        print(f"  워커에러:  {len(worker_errors)}건")
        for wid in range(NUM_WORKERS):
            json_path = os.path.join(temp_repo, f"status_{wid}.json")
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                print(f"  w{wid} count: {data.get('count')}")
            except Exception:
                print(f"  w{wid} count: 읽기실패")
        print("=" * 60)

        if fail_reasons:
            print("FAIL")
            for r in fail_reasons:
                print(f"  ✗ {r}")
            sys.exit(1)
        else:
            print("PASS — 동시 3프로세스 × 50커밋 무손실 직렬화 실증 완료")
            sys.exit(0)

    finally:
        shutil.rmtree(temp_repo, ignore_errors=True)
        print(f"[test_git_lock] temp repo 정리 완료")


if __name__ == "__main__":
    # Windows spawn 안전: freeze_support 필수
    multiprocessing.freeze_support()
    main()
