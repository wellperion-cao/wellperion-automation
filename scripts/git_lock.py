"""
git_lock.py — 동시 git 커밋 직렬화 lock (P1)
설계: docs/git_serialize_lock_design.md §3
Windows · 순수 stdlib (추가 의존성 없음)
"""

import ctypes
import datetime
import os
import shutil
import socket
import subprocess
import time

# ── 상수 (환경변수 override 가능) ──────────────────────────────────────────
ACQUIRE_TIMEOUT = int(os.environ.get("GIT_LOCK_ACQUIRE_TIMEOUT", 90))
STALE_SECONDS   = int(os.environ.get("GIT_LOCK_STALE", 300))
POLL            = 0.2


# ── 예외 ───────────────────────────────────────────────────────────────────
class GitLockTimeout(Exception):
    pass


# ── 내부 유틸 ──────────────────────────────────────────────────────────────
def _repo_root(repo_root=None):
    """repo_root 해석 우선순위: 인자 > env > git rev-parse > cwd"""
    if repo_root:
        return os.path.abspath(repo_root)
    env = os.environ.get("WELLPERION_REPO")
    if env:
        return os.path.abspath(env)
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", check=True
        )
        return result.stdout.strip()
    except Exception:
        return os.getcwd()


def _lock_dir(repo_root):
    locks_parent = os.path.join(repo_root, ".locks")
    os.makedirs(locks_parent, exist_ok=True)
    return os.path.join(locks_parent, "git.lock")


def _log(msg, repo_root):
    """logs/git_lock.log에 1줄 append. 실패해도 절대 크래시 금지."""
    try:
        logs_dir = os.path.join(repo_root, "logs")
        os.makedirs(logs_dir, exist_ok=True)
        log_path = os.path.join(logs_dir, "git_lock.log")
        ts = datetime.datetime.now().isoformat(timespec="seconds")
        line = f"{ts} pid={os.getpid()} {msg}\n"
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass


def _pid_alive(pid):
    """
    Windows: OpenProcess(SYNCHRONIZE=0x100000 | PROCESS_QUERY_LIMITED_INFORMATION=0x1000)
    핸들 0 이면 죽음(True 반환 == 살아있음이 False == steal 가능).
    핸들 얻으면 CloseHandle 후 살아있음 반환.
    예외 시 보수적으로 살아있다고 간주(False steal 방지).
    """
    try:
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = ctypes.windll.kernel32.OpenProcess(
            PROCESS_QUERY_LIMITED_INFORMATION, False, pid
        )
        if handle == 0:
            return False
        ctypes.windll.kernel32.CloseHandle(handle)
        return True
    except Exception:
        return True  # 보수적: 살아있다고 간주


# ── GitLock ────────────────────────────────────────────────────────────────
class GitLock:
    """
    디렉터리 atomic mkdir 기반 크로스-프로세스 git lock.
    with GitLock(holder, repo_root) as lock: ...
    """

    def __init__(self, holder="?", repo_root=None):
        self.holder = holder
        self._root = _repo_root(repo_root)
        self._lockdir = _lock_dir(self._root)
        self._holder_txt = os.path.join(self._lockdir, "holder.txt")

    def __enter__(self):
        waited = 0.0
        while True:
            try:
                os.mkdir(self._lockdir)
                # 획득 성공 — holder.txt 기록
                ts = datetime.datetime.now().isoformat(timespec="seconds")
                pid = os.getpid()
                host = socket.gethostname()
                with open(self._holder_txt, "w", encoding="utf-8") as f:
                    f.write(f"{pid}|{host}|{ts}|{self.holder}")
                _log(f"ACQUIRED holder={self.holder}", self._root)
                return self
            except FileExistsError:
                if self._is_stale():
                    self._steal()
                    continue  # 재시도
                if waited >= ACQUIRE_TIMEOUT:
                    _log(f"TIMEOUT holder={self.holder} waited={waited:.1f}s", self._root)
                    raise GitLockTimeout(
                        f"git lock 획득 실패: {ACQUIRE_TIMEOUT}s 초과 "
                        f"(holder={self.holder})"
                    )
                time.sleep(POLL)
                waited += POLL

    def __exit__(self, exc_type, exc_val, exc_tb):
        shutil.rmtree(self._lockdir, ignore_errors=True)
        _log(f"RELEASED holder={self.holder}", self._root)
        return False  # 예외 전파

    def _is_stale(self):
        """holder.txt 읽어 age>STALE 또는 PID 죽음 → True. 읽기 실패 → False."""
        try:
            with open(self._holder_txt, "r", encoding="utf-8") as f:
                content = f.read().strip()
            parts = content.split("|")
            if len(parts) < 3:
                return False
            pid_str, _host, ts_str = parts[0], parts[1], parts[2]
            # 타임스탬프 age 검사
            try:
                lock_ts = datetime.datetime.fromisoformat(ts_str)
                age = (datetime.datetime.now() - lock_ts).total_seconds()
                if age > STALE_SECONDS:
                    return True
            except ValueError:
                pass
            # PID 생존 검사
            try:
                pid = int(pid_str)
                if not _pid_alive(pid):
                    return True
            except ValueError:
                pass
            return False
        except Exception:
            return False  # 경합 중 읽기 실패 → False (conservative)

    def _steal(self):
        _log(f"STEAL by={self.holder}", self._root)
        shutil.rmtree(self._lockdir, ignore_errors=True)


# ── git 유틸 ───────────────────────────────────────────────────────────────
def run_git(args, cwd, check=True):
    """subprocess.run(['git', *args], cwd=cwd). check=True면 returncode≠0 시 RuntimeError."""
    result = subprocess.run(
        ["git"] + list(args),
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    if check and result.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} 실패 (rc={result.returncode}): {result.stderr.strip()}"
        )
    return result


def git_commit_push(
    paths,
    message,
    holder,
    repo_root=None,
    pull_autostash=True,
    push=True,
    cwd=None,
):
    """
    GitLock 임계구역 안에서 add→commit→(pull --rebase --autostash)→push 실행.
    paths: List[str] — git add 대상 경로 목록.
    nothing-to-commit은 무해 통과.
    원격 없음/pull 실패는 경고 로그 후 통과.
    """
    root = _repo_root(repo_root)
    work_dir = cwd or root
    paths = list(paths)

    with GitLock(holder, root):
        # git add
        run_git(["add"] + paths, cwd=work_dir)

        # git commit (nothing to commit이면 통과) — pathspec 강제(2026-07-20 시토·
        # 동시커밋 사고대응, P1 설계보완): GitLock 은 이 함수를 호출하는 프로세스끼리만
        # 직렬화하고, 사람이 터미널에서 치는 bare `git commit`이나 이 락을 안 쓰는 다른
        # 스크립트의 동시 `git add` 는 못 막는다. paths 로 커밋을 스코프하면, 그 사이
        # 인덱스에 다른 세션이 무관한 파일을 스테이징해뒀어도 이 커밋엔 안 실린다(그
        # 파일들은 staged 상태 그대로 남아 자기 커밋을 기다린다) — 락만으론 못 막는
        # "add~commit 사이 틈" 오염을 pathspec 이 구조적으로 차단.
        result = subprocess.run(
            ["git", "commit", "-m", message, "--"] + paths,
            cwd=work_dir,
            capture_output=True,
            text=True, encoding="utf-8", errors="replace",
        )
        if result.returncode != 0:
            out = (result.stdout + result.stderr).lower()
            # "no changes added to commit" 추가(2026-07-20 시토 발견·동시커밋 수리 중):
            # pathspec 유무와 무관하게 git 이 실제로 쓰는 무해 no-op 문구는 이것이다 —
            # 기존 "nothing to commit"/"nothing added to commit" 은 실제 git 출력과
            # 안 맞아 이 케이스에서 항상 RuntimeError 로 잘못 격상되고 있었다(latent bug,
            # pathspec 도입과 무관 — bare commit 에서도 동일하게 재현됨. 격리 테스트로 확인).
            if (
                "nothing to commit" in out
                or "nothing added to commit" in out
                or "no changes added to commit" in out
            ):
                _log(f"COMMIT nothing-to-commit holder={holder}", root)
            else:
                raise RuntimeError(
                    f"git commit 실패 (rc={result.returncode}): {result.stderr.strip()}"
                )

        # git pull --rebase --autostash
        if pull_autostash:
            pr = subprocess.run(
                ["git", "pull", "--rebase", "--autostash"],
                cwd=work_dir,
                capture_output=True,
                text=True, encoding="utf-8", errors="replace",
            )
            if pr.returncode != 0:
                _log(
                    f"PULL_WARN holder={holder} rc={pr.returncode} "
                    f"stderr={pr.stderr.strip()[:120]}",
                    root,
                )

        # git push
        if push:
            run_git(["push"], cwd=work_dir)


# ── 편의 함수 ──────────────────────────────────────────────────────────────
def git_lock(holder="?", repo_root=None):
    """GitLock(holder, repo_root) 편의 래퍼 — with git_lock(...) as lock: ..."""
    return GitLock(holder, repo_root)
