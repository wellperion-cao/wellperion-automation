#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""auto_log_adhoc_to_queue.py — CLI ad-hoc 작업 커밋 → G1(_queue.json) 입항완료 자동기록.

약속 L13(고치면 바로 올린다)·"ad-hoc 작업도 G1에 기록" 메모리를 코드로 박제한다.
CLI 세션에서 굵직한 작업을 끝내고 커밋하면, 사람이 따로 _queue 에 '입항 완료 배'를
손으로 적지 않아도(자동 안 됨) 이 스크립트가 post-commit 훅에서 발화해 자동 등록한다.

호출 경로:
  .git/hooks/post-commit → (이 스크립트) → post_commit_push.py
  (auto_log 가 chore(queue) 커밋을 1개 만들 수 있고, 그 커밋의 post-commit 이
   다시 이 스크립트를 부르지만 — chore(queue) 는 SKIP 규칙 2.b 에 걸려 base case 로
   기록하지 않으므로 재귀 없음.)

설계 원칙 (fail-open · 절대 커밋을 되돌리지 않음):
  - 어떤 예외/락실패/판정불가든 조용히 통과 → 항상 exit 0.
  - SSOT(_queue.json) 손상 금지: 기존 항목은 절대 수정·삭제·순서변경하지 않고
    배열 끝에 append 만 한다. 멱등(adhoc_commit 중복이면 skip).
  - GitLock 임계구역 안에서만 _queue 커밋(동시 세션 직렬화). 락 못 잡으면 보류.
  - 미러('3. 웰페리온 가이드/status/_queue.json')는 pre-commit 의 sync_queue_mirror.py 가
    자동 처리 → 여기서 직접 건드리지 않는다.

직접 실행도 가능: python scripts/auto_log_adhoc_to_queue.py [sha]
  (인자 없으면 HEAD. 백필 시 과거 sha 를 넘긴다.)
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

QUEUE_REL = "status/_queue.json"

# clevel ↔ 닉네임 매핑 (CLAUDE.md §1).
NICK = {
    "ceo": "웰리",
    "cfo": "시뽀",
    "chro": "시로",
    "cmo": "시모",
    "coo": "시우",
    "cpo": "시포",
    "cto": "시토",
}
# 닉네임 → clevel (귀속 ① 닉네임 토큰 검색용).
NICK_TO_ROLE = {v: k for k, v in NICK.items()}
ROLES = tuple(NICK.keys())

# SKIP 2.c — 큐/자동발행 전용 파일 집합(실작업 파일이 하나도 없으면 skip, 재귀방지).
AUTO_ONLY_PATHS = {
    "status/_queue.json",
    "3. 웰페리온 가이드/status/_queue.json",
    "status/erp_status.json",
    "status/_ceo_log.jsonl",
    "scripts/.review_notified.json",
}


def _run(args, cwd=None):
    """git 등 서브프로세스 1회. (rc, stdout) bytes 반환. 예외는 (1, b'')."""
    try:
        p = subprocess.run(
            args, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        return p.returncode, p.stdout
    except Exception:
        return 1, b""


def _repo_root() -> str:
    rc, out = _run(["git", "rev-parse", "--show-toplevel"])
    if rc == 0 and out.strip():
        return out.decode("utf-8", "replace").strip()
    env = os.environ.get("WELLPERION_REPO")
    if env:
        return os.path.abspath(env)
    return os.getcwd()


def _commit_meta(root: str, ref: str):
    """대상 커밋 메타 취득. 실패 시 None(→ fail-open skip)."""
    # %H sha · %h short · %P parents · %cI committer date · %s subject · %b body
    rc, out = _run(
        ["git", "show", "-s", "--format=%H%x1f%h%x1f%P%x1f%cI%x1f%s%x1f%b", ref],
        cwd=root,
    )
    if rc != 0 or not out.strip():
        return None
    txt = out.decode("utf-8", "replace").rstrip("\n")
    parts = txt.split("\x1f")
    if len(parts) < 6:
        return None
    full, short, parents, cdate_iso, subject, body = parts[:6]
    parent_count = len([p for p in parents.split() if p])
    date = (cdate_iso or "")[:10]  # YYYY-MM-DD
    # 변경 파일 목록.
    rc2, out2 = _run(
        ["git", "show", "--name-only", "--format=", ref], cwd=root
    )
    files = []
    if rc2 == 0:
        files = [
            ln.strip()
            for ln in out2.decode("utf-8", "replace").splitlines()
            if ln.strip()
        ]
    return {
        "full": full.strip(),
        "short": short.strip(),
        "parent_count": parent_count,
        "date": date,
        "subject": subject.strip(),
        "body": body.strip(),
        "files": files,
    }


def _strip_conventional_prefix(subject: str) -> str:
    """conventional commit prefix(type(scope): / type: ) 제거한 본문 반환."""
    s = subject
    if ":" in s:
        head, rest = s.split(":", 1)
        head = head.strip()
        # head 가 'type' 또는 'type(scope)' 모양이면 prefix 로 간주.
        core = head
        if "(" in core and core.endswith(")"):
            core = core.split("(", 1)[0]
        if core and all(c.isalpha() for c in core) and len(core) <= 12:
            return rest.strip()
    return s.strip()


def _attribute_clevel(root: str, subject: str, body: str) -> str:
    """clevel 귀속 — 커밋 내용 우선(공유 저장소라 세션마커 신뢰 못 함).

    ① 닉네임 토큰(subject+body) ② 역할 토큰(scope/제목, 대소문자무시)
    ③ 기본 'ceo'(웰리=전사 디스패처).

    ※ 세션 마커(.omc/state/active_clevel) 폴백은 폐지(2026-06-18). 저장소가
      멀티세션 공유라 한 마커가 타 C-Level 커밋을 오귀속함(예: feat(헌법)
      전사 작업이 coo로 찍힘). 귀속은 반드시 커밋 자체(닉네임·역할 토큰)에서만
      뽑고, 토큰 없으면 전사 소유자 ceo(웰리)로 둔다. → C-Level은 본인 커밋에
      [닉네임] 또는 (scope) 태그를 달아야 정확히 귀속된다.
    """
    text = f"{subject}\n{body}"
    # ① 닉네임 토큰.
    for nick, role in NICK_TO_ROLE.items():
        if nick in text:
            return role
    # ② 역할 토큰 (예: feat(S2-COO) / feat(S2/cto) / "COO" 단어).
    low = text.lower()
    for role in ROLES:
        # 경계 문자(영숫자 아님)로 둘러싸인 role 토큰만 인정 — 오탐 방지.
        idx = 0
        while True:
            pos = low.find(role, idx)
            if pos < 0:
                break
            before = low[pos - 1] if pos > 0 else ""
            after = low[pos + len(role)] if pos + len(role) < len(low) else ""
            if not before.isalnum() and not after.isalnum():
                return role
            idx = pos + 1
    # ③ 기본 — 전사 소유자 ceo(웰리). 세션마커 폴백 폐지(멀티세션 오귀속 방지).
    return "ceo"


def _should_skip(meta: dict, queue: list) -> bool:
    """SKIP 판정 — True 면 기록하지 않는다."""
    # a. merge 커밋.
    if meta["parent_count"] >= 2:
        return True
    subject = meta["subject"]
    low = subject.lower()
    # b. 제목 패턴.
    if low.startswith("chore(erp)") or low.startswith("chore(queue)"):
        return True
    for kw in ("auto-log", "시스템 현황 자동 발행", "erp_status", "changelog"):
        if kw.lower() in low:
            return True
    # c. 변경파일이 전부 자동발행/큐 전용 집합에만 속함(=실작업 파일 0).
    files = meta["files"]
    if files:
        real = [f for f in files if f not in AUTO_ONLY_PATHS]
        # home changelog 류도 자동발행으로 간주(파일명에 changelog 포함).
        real = [f for f in real if "changelog" not in f.lower()]
        if not real:
            return True
    # d. 이미 로깅됨.
    full = meta["full"]
    for item in queue:
        if isinstance(item, dict) and item.get("adhoc_commit") == full:
            return True
    return False


def _build_item(meta: dict, clevel: str) -> dict:
    nick = NICK.get(clevel, clevel)
    sha7 = meta["short"]
    date = meta["date"]
    clean_subject = _strip_conventional_prefix(meta["subject"])
    title = f"[{nick}] {clean_subject}"
    body = meta["body"].strip()
    if body:
        first_para = body.split("\n\n", 1)[0].strip()
        base = first_para[:300]
    else:
        base = meta["subject"]
    artifact = f"{base} (CLI ad-hoc · 커밋 {sha7})"
    return {
        "task_id": f"{clevel.upper()}-{date}-ADHOC-{sha7}",
        "clevel": clevel,
        "title": title,
        "status": "DONE",
        "terminal": True,
        "priority": "NORMAL",
        "enqueued_at": date,
        "processed_at": date,
        "artifact": artifact,
        "next": "🌀 표류 — 다음 미정 (필요 시 GM·웰리/담당 C-Level 지정)",
        "adhoc_commit": meta["full"],
    }


def _load_queue(path: str):
    """_queue.json 읽기. (data, crlf) 반환. 실패 시 (None, ...)."""
    try:
        raw = open(path, "rb").read()
    except Exception:
        return None, True
    # BOM 제거(안전).
    if raw[:3] == b"\xef\xbb\xbf":
        raw = raw[3:]
    crlf = b"\r\n" in raw
    try:
        data = json.loads(raw.decode("utf-8"))
    except Exception:
        return None, crlf
    if not isinstance(data, list):
        return None, crlf
    return data, crlf


def _write_queue(path: str, data: list, crlf: bool) -> bool:
    """_queue.json 쓰기 — 기존 들여쓰기(indent=2)·줄끝(CRLF)·BOM없음 유지."""
    try:
        s = json.dumps(data, ensure_ascii=False, indent=2)
        if crlf:
            s = s.replace("\r\n", "\n").replace("\n", "\r\n")
        with open(path, "wb") as f:
            f.write(s.encode("utf-8"))  # BOM 없이.
        return True
    except Exception:
        return False


def _commit_queue(root: str, sha7: str, clevel: str) -> None:
    """GitLock 임계구역 안에서 _queue.json add+commit. push 는 안 함(체인이 처리).

    락 못 잡으면(within-parent-lock 등) fail-open: 기록을 디스크에 남겼지만
    이번 커밋은 보류 → 다음 기회. 절대 hang/abort 금지.
    """
    try:
        from git_lock import GitLock, _log  # type: ignore
        import git_lock as _gl  # type: ignore
    except Exception:
        return  # git_lock 직독 실패 = fail-open.

    msg = f"chore(queue): auto-log 입항완료 배 — {sha7} ({clevel})"
    lock = GitLock("auto-log-adhoc", root)
    prev = _gl.ACQUIRE_TIMEOUT
    try:
        _gl.ACQUIRE_TIMEOUT = 2  # 짧게: 비면 즉시, 잡혀 있으면 빠르게 포기.
        try:
            with lock:
                rc, _ = _run(["git", "add", QUEUE_REL], cwd=root)
                if rc != 0:
                    _log("AUTO_LOG add 실패; 보류", root)
                    return
                p = subprocess.run(
                    ["git", "commit", "-m", msg],
                    cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                )
                if p.returncode != 0:
                    out = (p.stdout + p.stderr).decode("utf-8", "replace").lower()
                    if "nothing to commit" in out or "nothing added" in out:
                        _log("AUTO_LOG nothing-to-commit", root)
                    else:
                        _log(f"AUTO_LOG commit 실패 rc={p.returncode}", root)
                    return
                _log(f"AUTO_LOG ok {sha7} ({clevel})", root)
        except _gl.GitLockTimeout:
            # 부모 커밋 임계구역 안 — 보류(다음 기회). 디스크 변경은 working tree 에
            # 남아 다음 커밋 때 함께 올라가거나, 다시 호출될 때 멱등 처리됨.
            _log("AUTO_LOG within-parent-lock; 보류(다음 기회)", root)
            return
    except Exception as e:
        try:
            _log(f"AUTO_LOG skip(err) {e}", root)
        except Exception:
            pass
        return
    finally:
        _gl.ACQUIRE_TIMEOUT = prev


def main() -> int:
    try:
        root = _repo_root()
        ref = sys.argv[1] if len(sys.argv) > 1 else "HEAD"

        meta = _commit_meta(root, ref)
        if meta is None:
            return 0  # 메타 취득 실패 → fail-open.

        queue_path = os.path.join(root, QUEUE_REL)
        queue, crlf = _load_queue(queue_path)
        if queue is None:
            return 0  # 큐 못 읽음 → fail-open(손상 방지: 아무것도 안 함).

        if _should_skip(meta, queue):
            return 0

        clevel = _attribute_clevel(root, meta["subject"], meta["body"])
        item = _build_item(meta, clevel)

        queue.append(item)
        if not _write_queue(queue_path, queue, crlf):
            return 0  # 쓰기 실패 → fail-open.

        _commit_queue(root, meta["short"], clevel)
        return 0
    except Exception:
        # 무엇이 됐든 커밋을 되돌리지 않는다.
        return 0


if __name__ == "__main__":
    sys.exit(main())
