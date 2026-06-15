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
            capture_output=True, text=True, check=True
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

    with GitLock(holder, root):
        # git add
        run_git(["add"] + list(paths), cwd=work_dir)

        # git commit (nothing to commit이면 통과)
        result = subprocess.run(
            ["git", "commit", "-m", message],
            cwd=work_dir,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            out = (result.stdout + result.stderr).lower()
            if "nothing to commit" in out or "nothing added to commit" in out:
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
                text=True,
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
