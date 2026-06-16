#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""post_commit_push.py — 커밋 직후 origin 자동 push (INC-006 차단조치).

.git/hooks/post-commit 에서 호출된다. git_lock 임계구역 안에서
origin/master..HEAD 가 1개 이상이면 `git push origin HEAD:master` 한다.

설계 원칙 (fail-open · 절대 커밋을 되돌리지 않음):
  - 안 올라간 커밋 0개   → push skip (불필요 push 방지)
  - push 타임아웃(30s)   → 행(hang) 방지
  - push 실패            → logs/git_lock.log 로깅 + 텔레그램 1줄 경고.
                           exit 0 유지(커밋은 이미 성공).
  - 재귀 없음            → push 는 새 커밋을 만들지 않음.

직접 실행도 가능: python scripts/post_commit_push.py
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    from git_lock import GitLock, _log, _repo_root  # type: ignore
except Exception:
    # git_lock 직독 실패 = fail-open. 커밋은 이미 성공했으므로 조용히 통과.
    sys.exit(0)

PUSH_TIMEOUT = int(os.environ.get("POST_COMMIT_PUSH_TIMEOUT", 30))
REMOTE = "origin"
BRANCH = "master"


def _unpushed_count(root: str) -> int:
    """origin/master..HEAD 커밋 수. 원격 ref 없으면 -1(=알 수 없음→push 시도)."""
    try:
        r = subprocess.run(
            ["git", "rev-list", f"{REMOTE}/{BRANCH}..HEAD", "--count"],
            cwd=root,
            capture_output=True,
            text=True,
        )
        if r.returncode != 0:
            return -1
        return int(r.stdout.strip() or "0")
    except Exception:
        return -1


def _telegram_warn(root: str, text: str) -> None:
    """telegram_bot/.env 직독해 1줄 경고. 실패해도 무해(완전 무시)."""
    try:
        env_path = Path(root) / "telegram_bot" / ".env"
        if not env_path.exists():
            return
        token = chat_id = None
        for line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if line.startswith("TELEGRAM_BOT_TOKEN="):
                token = line.split("=", 1)[1].strip().strip('"').strip("'")
            elif line.startswith("TELEGRAM_CHAT_ID="):
                chat_id = line.split("=", 1)[1].strip().strip('"').strip("'")
        if not token or not chat_id:
            return
        import urllib.parse
        import urllib.request

        data = urllib.parse.urlencode(
            {"chat_id": chat_id, "text": text}
        ).encode("utf-8")
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage", data=data
        )
        urllib.request.urlopen(req, timeout=10).read()
    except Exception:
        pass


def _do_push(root: str) -> None:
    """실제 push 1회 + 결과 로깅/경고. lock 안/밖 어디서 불려도 동일."""
    try:
        r = subprocess.run(
            ["git", "push", REMOTE, f"HEAD:{BRANCH}"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=PUSH_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        _log("POST_COMMIT_PUSH timeout", root)
        _telegram_warn(
            root,
            "⚠️ 자동 push 타임아웃(30s) — origin 미동기화. 수동 `git push` 필요.",
        )
        return

    if r.returncode == 0:
        _log("POST_COMMIT_PUSH ok", root)
    else:
        err = (r.stderr or r.stdout).strip()[:200]
        _log(f"POST_COMMIT_PUSH fail rc={r.returncode} {err}", root)
        _telegram_warn(
            root,
            "⚠️ 자동 push 실패 — origin 미동기화(커밋은 로컬 보존). "
            f"수동 `git push` 필요.\n{err}",
        )


def main() -> int:
    root = _repo_root()

    n = _unpushed_count(root)
    if n == 0:
        # 이미 동기화됨 — push 불필요(무한/불필요 push 방지).
        return 0

    # 【재진입 안전】 자동 커밋 경로(ig_review_publish_watcher·bot 등)는 GitLock
    # 임계구역 *안에서* commit 하고, post-commit 훅은 그 commit 도중에 발화한다.
    # 같은 (재진입 불가) lock 을 다시 잡으려 하면 ACQUIRE_TIMEOUT(90s) 행 후 실패.
    # → 짧은 타임아웃으로 시도하고, 이미 잡혀 있으면(=부모가 이미 직렬화함) lock
    #    없이 바로 push 한다. push 는 새 커밋을 안 만들어 재귀 없음. 서버측 push 는
    #    원자적이라 경합 시 non-fast-forward 거부 → 다음 커밋에서 재시도(fail-open).
    lock = GitLock("post-commit-push", root)
    import git_lock as _gl

    prev_timeout = _gl.ACQUIRE_TIMEOUT
    try:
        _gl.ACQUIRE_TIMEOUT = 2  # 짧게: 비어 있으면 즉시 획득, 잡혀 있으면 빠르게 포기
        try:
            with lock:
                _do_push(root)
                return 0
        except _gl.GitLockTimeout:
            # 부모 커밋 임계구역 안 — 이미 직렬화됨. lock 없이 직접 push.
            _log("POST_COMMIT_PUSH within-parent-lock; push without lock", root)
            _do_push(root)
            return 0
    except Exception as e:
        # 그 외 예외 — 커밋은 이미 성공. 조용히 fail-open + 로깅.
        try:
            _log(f"POST_COMMIT_PUSH skip(err) {e}", root)
        except Exception:
            pass
        return 0
    finally:
        _gl.ACQUIRE_TIMEOUT = prev_timeout


if __name__ == "__main__":
    sys.exit(main())
