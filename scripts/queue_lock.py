"""
queue_lock.py — status/_queue.json 동시 read-modify-write 직렬화 (P2)

배경(2026-07-10 사고): 6개 프로세스(bot·ceo_watcher·auto_log_adhoc·assign_ship·
queue_archive·gm_aide_scan)가 _queue.json에 각자 read-modify-write 하는데 파일
레벨 락이 없어, 06:44 북극성 승인 배(ship 835)가 후속 프로세스에 덮어써져 유실됨.
→ OS 관리 바이트범위 잠금(msvcrt)으로 크로스프로세스 락을 걸어, 모든 writer가
load→modify→save 임계구역을 이 락으로 감싼다(각 writer 배선은 각 파일 참조).

설계 핵심:
  1) 임계구역 = load부터 save까지 전체 (쓰기만 감싸면 둘 다 stale 읽어 여전히 유실).
  2) 락 = msvcrt 바이트범위 잠금(Windows) — OS가 프로세스 죽음 시 자동 해제한다.
     고아 락·stale 추정·PID 생존검사가 아예 필요 없다(락파일+휴리스틱 방식의 오탈취·
     교착 문제를 원천 제거). 비Windows는 fcntl.flock 폴백.
  3) 쓰기는 tmp+os.replace 원자적 — 락 안 잡는 reader도 반쪽 파일을 절대 안 본다.
  4) 킬스위치: 환경변수 QUEUE_LOCK_DISABLED=1 → 락 no-op(즉시 역롤백).

Windows · 순수 stdlib(추가 의존성 없음).
"""

import datetime
import json
import os
import sys
import time
from contextlib import contextmanager

try:  # Windows 기본
    import msvcrt
    _WINLOCK = True
except ImportError:  # pragma: no cover - 비Windows 폴백
    import fcntl
    _WINLOCK = False

# git_lock.py(P1·검증됨)의 repo_root 해석 재사용.
# import 실패해도 self-contained fallback로 동작(교차 트리 경로 차이 방어).
try:
    from git_lock import _repo_root  # type: ignore
except Exception:  # pragma: no cover - 경로 폴백
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from git_lock import _repo_root  # type: ignore
    except Exception:
        import subprocess

        def _repo_root(repo_root=None):
            if repo_root:
                return os.path.abspath(repo_root)
            env = os.environ.get("WELLPERION_REPO")
            if env:
                return os.path.abspath(env)
            try:
                r = subprocess.run(
                    ["git", "rev-parse", "--show-toplevel"],
                    capture_output=True, text=True,
                    encoding="utf-8", errors="replace", check=True,
                )
                return r.stdout.strip()
            except Exception:
                return os.getcwd()


# ── 상수 (환경변수 override) ────────────────────────────────────────────────
# OS 자동해제 락이라 stale 임계값이 필요 없다. ACQUIRE_TIMEOUT은 홀더가 비정상적으로
# 오래 잡을 때(무한루프 등) 대기자가 영원히 멈추지 않게 하는 안전 상한일 뿐.
ACQUIRE_TIMEOUT = int(os.environ.get("QUEUE_LOCK_ACQUIRE_TIMEOUT", 60))
POLL = 0.05


class QueueLockTimeout(Exception):
    pass


# 기본 락 이름 = status/_queue.json 전용. 다른 배열 JSON(review_queue.json 등)은
# lock_name 을 달리 줘서 서로 막지 않게 한다(파일별 독립 임계구역).
DEFAULT_LOCK_NAME = "queue.lock"


def _lock_file(root, lock_name=DEFAULT_LOCK_NAME):
    parent = os.path.join(root, ".locks")
    os.makedirs(parent, exist_ok=True)
    return os.path.join(parent, lock_name)


def _log(msg, root):
    """logs/queue_lock.log에 1줄 append. 실패해도 절대 크래시 금지."""
    try:
        d = os.path.join(root, "logs")
        os.makedirs(d, exist_ok=True)
        ts = datetime.datetime.now().isoformat(timespec="seconds")
        with open(os.path.join(d, "queue_lock.log"), "a", encoding="utf-8") as f:
            f.write(f"{ts} pid={os.getpid()} {msg}\n")
    except Exception:
        pass


class QueueLock:
    """msvcrt 바이트범위 잠금 기반 크로스-프로세스 락(_queue.json 전용).

    영속 락 파일의 byte 0 을 배타 잠금한다. OS가 관리하는 잠금이라 홀더 프로세스가
    죽거나 핸들이 닫히면 자동 해제 → 고아 락·stale 추정·PID 생존검사가 불필요하다.
    (앞선 락파일+삭제+stale 휴리스틱 방식의 오탈취·delete-pending 교착을 제거.)

    with QueueLock(holder, repo_root): <load→modify→save>
    QUEUE_LOCK_DISABLED=1 이면 no-op(역롤백)."""

    def __init__(self, holder="?", repo_root=None, lock_name=DEFAULT_LOCK_NAME):
        self.holder = holder
        self.lock_name = lock_name
        self._root = _repo_root(repo_root)
        self._lockfile = _lock_file(self._root, lock_name)
        self._disabled = os.environ.get("QUEUE_LOCK_DISABLED") == "1"
        self._fd = None

    def _try_lock(self):
        """비차단 배타 잠금 1회 시도. 성공 True, 다른 홀더 보유 중이면 False."""
        try:
            if _WINLOCK:
                os.lseek(self._fd, 0, os.SEEK_SET)
                msvcrt.locking(self._fd, msvcrt.LK_NBLCK, 1)
            else:
                fcntl.flock(self._fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except OSError:
            return False

    def __enter__(self):
        if self._disabled:
            return self
        # 락 파일은 영속(삭제하지 않음) → delete-pending race 없음. locking은 쓰기권한 필요.
        self._fd = os.open(self._lockfile, os.O_CREAT | os.O_RDWR)
        waited = 0.0
        while True:
            if self._try_lock():
                _log(f"ACQUIRED lock={self.lock_name} holder={self.holder}", self._root)
                return self
            if waited >= ACQUIRE_TIMEOUT:
                os.close(self._fd)
                self._fd = None
                _log(
                    f"TIMEOUT lock={self.lock_name} holder={self.holder} "
                    f"waited={waited:.1f}s",
                    self._root,
                )
                raise QueueLockTimeout(
                    f"{self.lock_name} 획득 실패: {ACQUIRE_TIMEOUT}s 초과 "
                    f"(holder={self.holder})"
                )
            time.sleep(POLL)
            waited += POLL

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._disabled:
            return False
        if self._fd is not None:
            try:
                if _WINLOCK:
                    os.lseek(self._fd, 0, os.SEEK_SET)
                    msvcrt.locking(self._fd, msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(self._fd, fcntl.LOCK_UN)
            except OSError:
                pass
            try:
                os.close(self._fd)  # 핸들 닫힘 = OS 잠금 확실 해제
            finally:
                self._fd = None
            _log(f"RELEASED lock={self.lock_name} holder={self.holder}", self._root)
        return False  # 예외 전파


@contextmanager
def queue_lock(holder="?", repo_root=None, lock_name=DEFAULT_LOCK_NAME):
    """with queue_lock('holder'): <load→modify→save> 편의 래퍼."""
    with QueueLock(holder, repo_root, lock_name):
        yield


# ── 항로 파일 I/O (원자적) ──────────────────────────────────────────────────
def queue_path(repo_root=None):
    return os.path.join(_repo_root(repo_root), "status", "_queue.json")


def load_queue(repo_root=None):
    """_queue.json 전체 로드. 없거나 실패 시 빈 리스트."""
    p = queue_path(repo_root)
    if not os.path.exists(p):
        return []
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def save_queue_atomic(items, repo_root=None):
    """tmp+os.replace 원자적 쓰기 — 락 없는 reader도 반쪽 파일을 안 본다.
    윈도우: 대상 파일을 AV·인덱서가 순간 잡으면 os.replace가 WinError 5로 실패 →
    짧은 backoff 재시도(표준 우회). 실패 시 tmp 청소."""
    p = queue_path(repo_root)
    tmp = f"{p}.tmp.{os.getpid()}"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
    last_err = None
    for _ in range(25):  # 최대 ~0.5s 재시도
        try:
            os.replace(tmp, p)
            return
        except PermissionError as e:  # WinError 5 — 대상 순간 잠금
            last_err = e
            time.sleep(0.02)
    try:
        os.remove(tmp)
    except OSError:
        pass
    raise last_err


def mutate_queue(mutator, holder="?", repo_root=None):
    """락 임계구역에서 load→mutator(items)→원자적 save.
    mutator(items): 새 리스트 반환 또는 items in-place 수정 후 None 반환."""
    with QueueLock(holder, repo_root):
        items = load_queue(repo_root)
        result = mutator(items)
        new_items = result if result is not None else items
        save_queue_atomic(new_items, repo_root)
        return new_items
