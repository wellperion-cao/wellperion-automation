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

import json
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

# ── 실패 사유 로깅용 마스킹·절단 (2026-07-30 GM 승인 · CTO) ──────────────────────
#  왜: fetch/merge/push 실패의 진짜 stderr 를 로그에 남기지 않아 non-ff 가 며칠씩
#  막혀도 원인을 알 수 없었다(2026-07-30 실측·GM 지적). 이제 남기되, git 원격 URL에
#  자격증명이 박혀 있을 수 있어(https://user:token@host) 로그에 쓰기 전 반드시 마스킹한다.
import re as _re_mask


def _mask_secrets(s: str) -> str:
    """git stderr 등에 섞일 수 있는 자격증명을 로그에 쓰기 전 가린다."""
    try:
        s = _re_mask.sub(r'://[^/\s@]+@', '://***@', s)
        s = _re_mask.sub(r'(x-access-token|token)[:=][A-Za-z0-9_\-]+', r'\1:***', s, flags=_re_mask.IGNORECASE)
        s = _re_mask.sub(r'\b(ghp|gho|ghu|ghs|ghr|github_pat)_[A-Za-z0-9_]{10,}\b', r'\1_***', s)
        return s
    except Exception:
        return s


def _tail(s: str, n: int = 500) -> str:
    """로그용 — 마스킹 후 뒤에서 n자만(긴 stderr 도배 방지). 실패해도 빈 문자열."""
    try:
        s = _mask_secrets(s or "")
        return s[-n:] if len(s) > n else s
    except Exception:
        return ""


def _unpushed_count(root: str) -> int:
    """origin/master..HEAD 커밋 수. 원격 ref 없으면 -1(=알 수 없음→push 시도)."""
    try:
        r = subprocess.run(
            ["git", "rev-list", f"{REMOTE}/{BRANCH}..HEAD", "--count"],
            cwd=root,
            capture_output=True,
            text=True, encoding="utf-8", errors="replace",
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
        # ★2026-07-24 GM 지시: 자동 push 실패 같은 기계 알림은 **확인방(자동화현황방)** 으로.
        #   GM 이 손으로 할 일이 아니다(워처가 스스로 재시도해 대개 몇 분 안에 풀린다).
        #   분류 판단은 scripts/alert_router.py 한 곳에서만 한다(약속 L01).
        try:
            sys.path.insert(0, str(Path(root) / "scripts"))
            from alert_router import TECH_CHECK, route
            chat_id = route(TECH_CHECK)
        except Exception:
            pass  # 라우터를 못 읽으면 기존 대상 유지 — 알림 자체를 잃지 않는다
        from tg_outbound_log import send as _tg_send
        _tg_send(token, chat_id, text, source="post_commit_push._telegram_warn", timeout=10)
    except Exception:
        pass


def _push_once(root: str) -> tuple[int, str]:
    """git push 1회. (returncode, stderr) 반환. 타임아웃은 rc=124.
    반환 문자열은 로그에 그대로 쓰일 수 있으므로 마스킹·절단(_tail) 처리해서 준다."""
    try:
        r = subprocess.run(
            ["git", "push", REMOTE, f"HEAD:{BRANCH}"],
            cwd=root,
            capture_output=True,
            text=True, encoding="utf-8", errors="replace",
            timeout=PUSH_TIMEOUT,
        )
        return r.returncode, _tail((r.stderr or r.stdout).strip())
    except subprocess.TimeoutExpired:
        return 124, "timeout"


def _is_nonff(err: str) -> bool:
    """원격이 앞서서 거부된(경합) 케이스인지."""
    low = (err or "").lower()
    return any(
        k in low
        for k in ("fast-forward", "fetch first", "non-fast", "rejected", "stale info")
    )


def _rev_parse(root: str, ref: str) -> str:
    """ref 의 커밋 해시(40자). 실패하면 빈 문자열 — 호출자가 그때는 통합을 시도하지 않는다."""
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--verify", f"{ref}^{{commit}}"],
            cwd=root, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=20,
        )
        s = (r.stdout or "").strip()
        return s if r.returncode == 0 and len(s) == 40 else ""
    except Exception:
        return ""


def _clear_orphan_rebase(root: str) -> None:
    """rebase --abort 가 못 치운 고아 rebase 상태(.git/rebase-merge|rebase-apply)를
    강제 제거. 잠긴 바이너리(PowerPoint 등 열린 파일)로 autostash reset --hard 가
    'Invalid argument' 로 죽으면 제어파일 없는 고아 디렉터리만 남아 이후 모든 git 이
    'currently rebasing' 으로 막힌다 → 직접 삭제로 끊는다. HEAD 는 안 옮겨진 상태라 안전.
    참고 기억: reference_autopush_fails_on_locked_binary."""
    import shutil
    try:
        gd = subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            cwd=root, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=10,
        )
        gitdir = (gd.stdout or "").strip() or ".git"
        if not os.path.isabs(gitdir):
            gitdir = os.path.join(root, gitdir)
        for name in ("rebase-merge", "rebase-apply"):
            d = os.path.join(gitdir, name)
            if os.path.isdir(d):
                shutil.rmtree(d, ignore_errors=True)
                _log(f"POST_COMMIT_PUSH cleared orphan {name}", root)
    except Exception:
        pass


def _is_dirty(root: str) -> bool:
    """워킹트리/스테이징에 미커밋 변경이 있나(=GM이 파일 열어 편집 중일 수 있음).
    판단 불가 시 안전하게 True(=merge 경로 선택, 열린 파일 보호)."""
    try:
        r = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=root, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=20,
        )
        if r.returncode != 0:
            return True
        return bool((r.stdout or "").strip())
    except Exception:
        return True


def _stash_count(root: str) -> int:
    """스태시 개수. 확인 불가면 -1(비교를 무의미하게 만들어 오탐을 막는다)."""
    try:
        r = subprocess.run(["git", "stash", "list"], cwd=root,
                           capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=20)
        if r.returncode != 0:
            return -1
        return len([x for x in (r.stdout or "").splitlines() if x.strip()])
    except Exception:
        return -1


def _clear_stale_index_entries(root: str) -> list:
    """공용 인덱스에 남은 **증명 가능한 찌꺼기 스테이징**만 골라 HEAD 기준으로 되돌린다.

    ★배245 근본원인(2026-07-31 실측). 이 저장소는 여러 세션이 같은 작업트리를 쓰고,
    일부 스크립트는 `git add` 만 하고 커밋하지 않는다(설계상 '커밋은 워처가'). 그렇게 남은
    인덱스 항목은 **옛 blob 을 가리킨 채 영구히 남아** 이후 모든 merge 를 거부시킨다
    ("local changes would be overwritten by merge") — 통합 창이 영영 안 열린다.
    실측 피해: origin/master 8시간 정지, 미푸시 919건, 그중 588건이 그 정체 때문에
    찍힌 '기계 산출물 선커밋' 자동 커밋. safe_commit.py 는 원인이 아니다(임시 인덱스를
    `read-tree HEAD` 로 시작해 라이브 인덱스를 안 건드린다) — 맨손 `git add` 가 원인이다.

    ★안전 조건(이것 하나로 유실 가능성이 0이다): **작업트리 내용이 HEAD 와 같은 경로만**
    되돌린다. 그런 경로의 인덱스 항목은 정의상 아무도 원하지 않는 옛 blob 이고, HEAD 가
    이미 작업트리와 같으므로 되돌려도 잃을 내용이 없다.
    작업트리가 HEAD 와 다르면(=진짜 진행 중인 작업) **손대지 않는다** — 기존처럼 보류한다.

    쓰는 명령은 경로 한정 `git reset -- <경로>` 뿐이다. 이건 인덱스만 HEAD 로 맞추고
    **작업트리는 건드리지 않는다**(`reset --hard`·`checkout --` 와 다르다 — 공용 작업트리
    금지선 안쪽). 호출자가 GitLock 을 쥔 구간에서만 부른다.
    """
    def _paths(args):
        r = subprocess.run(["git"] + args, cwd=root, capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=30)
        return [p for p in (r.stdout or "").split("\0") if p] if r.returncode == 0 else []

    try:
        staged = _paths(["diff", "--cached", "--name-only", "-z"])
        if not staged:
            return []
        stale = []
        for p in staged:
            # HEAD ↔ 작업트리 비교. 차이가 없으면(rc=0) 인덱스 항목만 옛것 = 순수 찌꺼기.
            r = subprocess.run(
                ["git", "diff", "--quiet", "HEAD", "--", p],
                cwd=root, capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=30,
            )
            if r.returncode == 0:
                stale.append(p)
        if not stale:
            return []
        r = subprocess.run(
            ["git", "reset", "-q", "--"] + stale,
            cwd=root, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=60,
        )
        if r.returncode != 0:
            _log(f"POST_COMMIT_PUSH 찌꺼기 스테이징 해제 실패 — {_tail(r.stderr or r.stdout)}", root)
            return []
        _log(f"POST_COMMIT_PUSH 찌꺼기 스테이징 해제 {len(stale)}건(작업트리=HEAD 인 것만): "
             f"{', '.join(stale[:5])}", root)
        return stale
    except Exception as e:
        _log(f"POST_COMMIT_PUSH 찌꺼기 스테이징 해제 예외 {e}", root)
        return []


def _sync_index_to_new_head(root: str, old_head: str, new_sha: str) -> list:
    """무접촉 통합 직후 라이브 인덱스를 새 HEAD 로 동기화 (2026-08-04 GM 지시 — 인덱스 동결 근본수리).

    왜: 아래 통합은 update-ref 로 HEAD 만 옮기고 라이브 인덱스는 옛 트리 그대로 남긴다.
    그 순간부터 이 클론의 인덱스는 '동결' — 원격이 넣은 파일이 인덱스엔 없어 삭제로
    보이고, 원격이 고친 파일은 옛 blob 이라 되돌림으로 보인다. 이후 맨손 커밋이 그
    옛것을 그대로 커밋한다(2026-08-04 지원자 사진 반복삭제 사고의 뿌리 — 나우열M PC 가
    push 한 chro 사진이 이 PC 에선 영구히 '삭제된 것처럼' 보였다).

    로직은 safe_commit._sync_live_index 재사용(약속 L01 — 복제 금지). 그 함수의 안전
    조건이 여기 요구와 정확히 같다: **라이브 인덱스 항목이 옛 HEAD 와 같은 경로만**
    새 HEAD 로 바꾼다(다른 세션이 stage 해 둔 자기 내용은 절대 안 덮음). 인덱스 전용
    update-index 만 쓰고 작업트리는 무접촉. index.lock 은 지우지 않고 대기·재시도
    (그 함수에 내장 — 0.5s × 40회). 실패해도 통합 자체는 유효(best-effort — 남은
    동결분은 커밋 관문의 동결 인덱스 게이트가 거부한다)."""
    try:
        from safe_commit import _sync_live_index
        r = subprocess.run(
            ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", "-z",
             old_head, new_sha],
            cwd=root, capture_output=True, timeout=60,
        )
        if r.returncode != 0:
            return []
        paths = [p.decode("utf-8", "replace") for p in r.stdout.split(b"\x00") if p]
        synced: list = []
        for i in range(0, len(paths), 100):  # Windows 명령줄 길이 한도 방어(한글 경로)
            synced += _sync_live_index(paths[i:i + 100], Path(root), old_head, new_sha)
        return synced
    except Exception as e:
        _log(f"POST_COMMIT_PUSH 인덱스 동기화 실패(best-effort) {e}", root)
        return []


def _fill_missing_from_index(root: str, old_head: str, new_sha: str) -> list:
    """(다) 원격 추가분 실체화 (2026-08-04 GM 지시) — **디스크에 없는 경로만** 채운다.

    왜: 무접촉 통합은 checkout 을 안 하므로 원격(나우열M PC·remote 세션)이 추가한
    파일이 이 PC 디스크에 영원히 안 내려온다(실측: chro/hub/photos 가 r99 에서 정지).
    디스크에 없는 파일은 **덮어쓸 로컬 변경 자체가 없다** — 잃을 것이 0 인 경로만 쓴다.

    안전 조건(코드로 강제):
      ①os.path.exists 로 걸러 **로컬에 파일이 있는 경로는 후보에서 제외**(수정 중일 수 있음)
      ②인덱스에 실존하는 경로만(ls-files 대조 — 삭제·동기화 실패분 자동 제외)
      ③쓰기는 `git checkout-index`(-f 없음) — 이 명령은 기존 파일을 **절대 덮지 않는다**
        (①의 이중 안전벨트). checkout --·restore 계열은 쓰지 않는다.
    채운 수를 로그에 남긴다(조용히 하지 않음). 실패=best-effort(다음 통합이 재시도)."""
    try:
        r = subprocess.run(
            ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", "-z",
             old_head, new_sha],
            cwd=root, capture_output=True, timeout=60,
        )
        if r.returncode != 0:
            return []
        paths = [p.decode("utf-8", "replace") for p in r.stdout.split(b"\x00") if p]
        cand = [p for p in paths if p and not os.path.exists(os.path.join(root, p))]
        if not cand:
            return []
        filled: list = []
        for i in range(0, len(cand), 100):  # Windows 명령줄 길이 한도 방어(한글 경로)
            chunk = cand[i:i + 100]
            ls = subprocess.run(
                ["git", "-c", "core.quotepath=false", "ls-files", "-z", "--", *chunk],
                cwd=root, capture_output=True, timeout=60,
            )
            if ls.returncode != 0:
                continue
            in_index = [p.decode("utf-8", "replace") for p in ls.stdout.split(b"\x00") if p]
            if not in_index:
                continue
            payload = b"\x00".join(p.encode("utf-8") for p in in_index) + b"\x00"
            co = subprocess.run(
                ["git", "checkout-index", "-z", "--stdin"],
                cwd=root, input=payload, capture_output=True, timeout=120,
            )
            if co.returncode == 0:
                filled += in_index
        if filled:
            _log(f"POST_COMMIT_PUSH 원격 추가분 실체화 {len(filled)}건(디스크에 없던 것만): "
                 f"{', '.join(filled[:5])}", root)
        return filled
    except Exception as e:
        _log(f"POST_COMMIT_PUSH 실체화 실패(best-effort) {e}", root)
        return []


def _detect_stale_worktree_copies(root: str, old_head: str, new_sha: str) -> list:
    """무접촉 통합 직후 '뒤진 작업본' 감지 (2026-08-10 GM 지시 · 예방 대책).

    왜: 위 통합은 작업트리를 절대 안 건드린다. 그래서 원격이 고친 파일이 이 PC
    디스크엔 옛 내용 그대로 남고, git status 엔 조용히 " M"(unstaged)으로만 뜬다.
    그 상태로 커밋하면 방금 들어온 개선을 지운다(2026-08-08 사고 cd2e79cae — 인사
    화면 47줄 삭제). 여기서는 **감지·경고만** 한다 — 작업트리를 자동으로 덮으면
    지금 편집 중인 남의 파일을 잃을 위험이 있어(설계가 일부러 피한 부분) 이번
    범위가 아니다.

    판정: 통합으로 내용이 바뀐 경로(diff-tree old_head..new_sha) 중 디스크에
    실재하면서 새 HEAD 내용과 다른 것. 줄바꿈만 다른 건 제외(\\r\\n 정규화 후
    비교) — 안 하면 디스크 CRLF 파일이 통째로 오탐된다(실측)."""
    try:
        r = subprocess.run(
            ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", "-z",
             old_head, new_sha],
            cwd=root, capture_output=True, timeout=60,
        )
        if r.returncode != 0:
            return []
        paths = [p.decode("utf-8", "replace") for p in r.stdout.split(b"\x00") if p]
        stale: list = []
        # ponytail: 경로마다 git show 1회 — 통합이 수백 파일 규모로 흔해지면
        # git cat-file --batch 로 묶어 왕복 줄이기.
        for p in paths:
            fp = os.path.join(root, p)
            if not os.path.isfile(fp):
                continue
            try:
                with open(fp, "rb") as fh:
                    disk = fh.read()
            except OSError:
                continue
            show = subprocess.run(
                ["git", "show", f"{new_sha}:{p}"],
                cwd=root, capture_output=True, timeout=30,
            )
            if show.returncode != 0:
                continue
            if disk.replace(b"\r\n", b"\n") != show.stdout.replace(b"\r\n", b"\n"):
                stale.append(p)
        return stale
    except Exception as e:
        _log(f"POST_COMMIT_PUSH 뒤진 작업본 감지 실패(best-effort) {e}", root)
        return []


def _reconcile(root: str) -> tuple[bool, str]:
    """원격이 앞섰을 때 fetch 후 로컬 커밋을 origin 위로 통합.
    ★언제나 merge 로만 통합한다(rebase 경로는 배147에서 껐다 — 아래 _ALLOW_REBASE 주석 참고).
    반환 = (성공 여부, 실패 사유 — 성공 시 빈 문자열). 어떤 경우에도 half-state 안 남김
    (abort + 고아 강제정리).
    (호출자가 git_lock 임계구역 보유 상태에서만 호출 — 동시 로컬 git 없음 보장.)

    ★2026-07-30(GM 지시): 예전엔 bool 만 반환해 실패해도 진짜 사유(git stderr)가 로그에
    안 남았다(non-ff 가 며칠 막혀도 원인불명). 이제 각 실패 지점에서 사유 문자열을 함께
    반환한다 — 호출자가 최종 로그에 "그 시도의 실제 사유"를 쓸 수 있게(첫 push 거부
    메시지 재사용 금지). 문자열은 _tail() 로 이미 마스킹·절단돼 있다.

    merge 폴백 사유: 열린 앱이 추적 바이너리(예: 작업 중 .pptx)를 잠그면 rebase 가
    시작 시 워킹트리를 reset --hard 하다 잠긴 파일 unlink 실패로 죽는다. 원격이 그
    파일을 안 건드리는 한 merge 는 워킹트리를 안 건드려 통과한다(INC: locked-binary).
    """
    try:
        f = subprocess.run(
            ["git", "fetch", REMOTE, BRANCH],
            cwd=root, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=PUSH_TIMEOUT,
        )
        if f.returncode != 0:
            reason = _tail("fetch 실패: " + (f.stderr or f.stdout or "").strip())
            _log(f"POST_COMMIT_PUSH {reason}", root)
            return False, reason
        # 워킹트리가 더러우면(=GM이 파일을 열어 편집 중) rebase 는 시작 시 워킹트리를
        # reset 하다 잠긴 파일에서 죽는다 → 처음부터 merge 로 간다(열린 파일 안 건드림).
        # 깨끗하면 rebase 로 선형 히스토리 유지, 실패해도 아래 merge 폴백.
        # ★2026-07-27 (배147) — rebase 경로를 **완전히 끈다.** 기본은 merge 하나뿐이다.
        #   왜: rebase 는 성공하든 중단(--abort)하든 **작업트리를 통째로 되감는다.** 이 저장소는
        #   3분·5분 주기 자동화가 쉴 새 없이 파일을 쓰므로, '깨끗한지 확인'과 'rebase 시작' 사이
        #   몇 초 안에 새 결과물이 쓰이고, 그 파일은 되감기에 휩쓸려 **조용히 옛 내용으로 돌아간다.**
        #   실측 2026-07-27: kpi_values.json 이 05:58·07:52 정상 갱신 성공 로그를 남겼는데도 내용은
        #   07-23 자로 되돌아가 있었다(95시간 정체로 오탐 경보까지 발생). 실패가 아니라 덮어쓰기였다.
        #   같은 계열 전력: INC-034(autostash 가 미커밋 변경을 스태시에 가둠·자율 기록 소실),
        #   INC-029(스테일 트리). 매번 '조건을 좁히는' 식으로 막았지만 되감기 자체가 남아 재발했다.
        #   merge 는 작업트리를 되감지 않는다 — 통합할 수 없으면 **거부**할 뿐 조용히 잃지 않는다.
        #   대가는 선형 히스토리 포기(머지 커밋 생김). 기록이 예뻐지는 것보다 결과물을 안 잃는 게 먼저다.
        #   되돌리려면 아래 REBASE 상수를 True 로.
        _ALLOW_REBASE = False
        if _ALLOW_REBASE and not _is_dirty(root):
            # ★--autostash 를 쓰지 않는다 (2026-07-24 시토 · INC-034).
            #   왜: 이 저장소는 자동화 6곳 이상이 쉴 새 없이 파일을 쓴다. _is_dirty() 확인과
            #   rebase 사이 2초 안에도 트리가 더러워진다(실측 race). 그때 --autostash 가 붙어 있으면
            #   git 이 미커밋 변경을 스태시했다가 rebase 뒤 되돌리는데, **파일 하나라도 충돌하면
            #   되돌리기가 통째로 실패**한다. 그런데 `git rebase --autostash` 는 그 경우에도
            #   **exit 0** 을 낸다 → 여기서 True 를 반환하고 "ok" 로 보고된다. 미커밋 변경은
            #   스태시에 갇힌 채 작업트리는 옛 내용으로 돌아가고, 아무도 모른다.
            #   실측 피해: 스태시 32개 적체(2026-05-28~), GM보좌 스캔 기록 07-20~24 전량 소실
            #   → 자율현황 페이지가 '포착 0건'(거짓)으로 표시.
            #   고침: --autostash 제거. 트리가 더러우면 rebase 가 **시작 전에 거부**하고(파일 무접촉)
            #   아래 merge 폴백으로 내려간다. merge 는 작업트리를 건드리지 않아 유실이 0이다.
            #   (.gitattributes 의 *.jsonl merge=union 은 그대로 유효 — merge 경로에서 동작한다.)
            before = _stash_count(root)
            rb = subprocess.run(
                ["git", "rebase", f"{REMOTE}/{BRANCH}"],
                cwd=root, capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=PUSH_TIMEOUT,
            )
            if rb.returncode == 0:
                # 방어 2겹: 그래도 스태시가 늘었다면 미커밋 변경이 갇힌 것이다. 조용히 넘기지 않는다.
                after = _stash_count(root)
                if before >= 0 and after >= 0 and after > before:
                    _log(f"POST_COMMIT_PUSH ★경고 스태시 증가 {before}->{after} — "
                         f"미커밋 변경이 갇혔을 수 있음(git stash list 확인 필요)", root)
                return True, ""
            # rebase 실패 → 원상복구(커밋·작업트리 보존) + 고아 상태 강제정리
            subprocess.run(
                ["git", "rebase", "--abort"],
                cwd=root, capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=20,
            )
            _clear_orphan_rebase(root)
            _log("POST_COMMIT_PUSH rebase 실패; merge 폴백 시도", root)
        else:
            _log("POST_COMMIT_PUSH merge 로 통합(작업트리 되감기 없음 — 배147)", root)
        # ★2026-07-30(GM 승인 · B안, 시토 안전조정) — merge 직전에 아직도 더러우면(화이트리스트
        # 밖 파일이 섞였거나 미러가 그새 재경합) 무리하게 merge 하지 않는다. 사유만 남기고 다음
        # 주기(다음 커밋 훅 또는 5분 스위퍼)로 넘긴다 — 사람이 편집 중인 파일을 이 경로가 절대
        # 커밋하지 않기 위한 안전판. ★기계 산출물 선커밋(_commit_machine_outputs) 자체는 여기(락
        # 보유 구간) 안에서 부르지 않는다 — safe_commit.py 가 같은 GitLock 파일을 다시 잡으려 하고
        # (재진입 불가) 자기 자신이 든 락을 기다리며 최대 90초씩 자가교착된다(실측 확인 후 조정).
        # 그래서 선커밋은 main()/스위퍼에서 **락을 잡기 전**에 이미 끝내고, 여기서는 그 결과만
        # git diff 로 읽기만 한다(락 불필요).
        # ★2026-07-31(시토 · 배245) — 판정 기준을 "더러운 파일이 하나라도 있나"에서
        #   "**merge 가 실제로 건드릴 파일**이 더러운가"로 좁힌다.
        #   왜: 이 저장소는 3분·5분 자동화가 20건 넘는 산출물을 상시 더럽게 유지한다
        #   (실측 2026-07-31: 상시 23건). 예전 기준은 그중 단 하나만 더러워도 merge 를
        #   건너뛰었는데, 그 23건 중 원격도 건드리는 건 5건뿐이었다. 즉 merge 는
        #   **한 번도 시도되지 않았고** non-fast-forward 가 영구 지속됐다 — 그러는 동안
        #   커밋 훅·스위퍼는 매 주기 '기계 산출물 선커밋'만 반복해 새 커밋을 찍었다
        #   (실측: 미푸시 900건 중 588건이 그 자동 커밋 · 라이브 화면 8시간 정지).
        #   git merge 가 거부하는 조건은 "더러움" 자체가 아니라 **merge 가 덮어써야 할
        #   파일이 더러움**이다. 그래서 _blocking_machine_outputs 와 **같은 두 점 기준**
        #   (HEAD vs origin — 이유는 그 함수 주석 참고)으로 교집합만 본다.
        #   교집합에 남은 게 있으면 그대로 보류한다(사람이 편집 중인 파일 보호 — 원래 목적 유지).
        # 통합을 막는 것이 '아무도 원하지 않는 옛 스테이징 찌꺼기'뿐이면 먼저 치운다(배245).
        # 진짜 진행 중인 작업은 건드리지 않는다 — 아래 판정에 그대로 남아 보류된다.
        _clear_stale_index_entries(root)
        still_dirty = _merge_blocking_paths(root)
        if still_dirty:
            # ★2026-07-31 시토(GM "AI진행현황방에 계속 알림 뜨는데 좋은 내용이 아니다") —
            #   '비기계 파일이 겹치면 보류' 가드를 **뺐다.**
            #   왜: 이 가드는 `git merge` 가 작업트리를 덮어쓸 때를 막으려던 것이다. 그런데
            #   아래 통합은 merge-tree/commit-tree/update-ref 로 **작업트리를 아예 안 만진다.**
            #   덮어쓸 일이 없으니 막을 이유도 없는데, 남은 가드가 미커밋 파일 하나만 있으면
            #   전체 push 를 세웠다.
            #   실측 2026-07-31: 종합접수처 화면 파일이 스테이지에 옛 blob 으로 남아 **74분간
            #   모든 push 를 막았고**, 그동안 30분마다 같은 경보가 확인방에 반복 발신됐다.
            #   막힌 것은 한 파일인데 대가는 저장소 전체 정지였다.
            #   ▸미커밋 변경은 통합 뒤에도 **미커밋 그대로 남는다**(내용 무손실). 사람이 편집
            #     중인 파일을 이 경로가 커밋하는 일은 여전히 없다 — 커밋 대상은 기계 산출물뿐.
            #   ▸진짜 내용 충돌이면 merge-tree 가 0 아닌 코드로 거부하고 그때 보류한다(그 방어는 유지).
            _log(
                "POST_COMMIT_PUSH 겹침 " + str(len(still_dirty)) +
                "건(비기계 " + str(sum(1 for p in still_dirty if not _is_machine_output(p))) +
                "건) — 작업트리 무접촉 통합이라 그대로 진행", root,
            )
            # ★2026-07-31(시토 · 배245·배242 근본) — 겹치는 게 **기계 산출물뿐**이면 보류하지
            #   않는다. 여기서 보류하면 영원히 안 열리기 때문이다: 선커밋이 성공해도 3분·5분
            #   자동화가 몇 초 안에 같은 파일을 다시 써서(실측: 선커밋 ok 직후 같은 3건이 다시
            #   더러워짐) merge 직전 재확인에서 매번 다시 걸린다. 경쟁을 이길 수 없는 구조다.
            _log(
                "POST_COMMIT_PUSH 겹침 " + str(len(still_dirty)) +
                "건 전부 기계 산출물 — 작업트리 무접촉 통합으로 진행(배245)", root,
            )
        # ★통합은 작업트리를 아예 건드리지 않고 한다 (2026-07-31 · 배245 근본 수리).
        #   `git merge` 는 작업트리·인덱스를 만지므로, 더러운 파일이 대상에 하나라도 있으면
        #   거부한다("local changes would be overwritten"). 이 저장소는 자동화가 쉴 새 없이
        #   써서 그 조건을 **피할 수 없다** — 배242 note 가 요구한 "임시 인덱스로 병합 트리를
        #   만들어 update-ref" 경로가 이것이다.
        #   ▸merge-tree --write-tree: 작업트리·인덱스·HEAD 어느 것도 안 건드리고 병합 트리만
        #     계산한다(충돌이면 0 아닌 종료코드 — 그때는 자동 해결하지 않고 보류한다).
        #   ▸commit-tree + update-ref: 커밋을 만들고 브랜치만 옮긴다. 미커밋 변경은 그대로
        #     미커밋으로 남는다(유실 0 · 되감기 0 — rebase 를 끈 이유와 같은 안전선).
        #   ▸update-ref 는 **직전에 읽은 HEAD 를 old-value 로 넘겨** 원자적으로 바꾼다. 그
        #     사이 다른 세션이 커밋했으면 실패하고 다음 주기로 넘어간다(남의 커밋 유실 방지).
        head = _rev_parse(root, "HEAD")
        theirs = _rev_parse(root, f"{REMOTE}/{BRANCH}")
        if head and theirs:
            mt = subprocess.run(
                ["git", "merge-tree", "--write-tree", head, theirs],
                cwd=root, capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=PUSH_TIMEOUT,
            )
            tree = (mt.stdout or "").strip().splitlines()
            if mt.returncode == 0 and tree and len(tree[0].strip()) == 40:
                ct = subprocess.run(
                    ["git", "commit-tree", tree[0].strip(), "-p", head, "-p", theirs,
                     "-m", f"Merge {REMOTE}/{BRANCH} — 작업트리 무접촉 통합 (배245)"],
                    cwd=root, capture_output=True, text=True,
                    encoding="utf-8", errors="replace", timeout=PUSH_TIMEOUT,
                )
                new = (ct.stdout or "").strip()
                if ct.returncode == 0 and len(new) == 40:
                    ur = subprocess.run(
                        ["git", "update-ref", f"refs/heads/{BRANCH}", new, head],
                        cwd=root, capture_output=True, text=True,
                        encoding="utf-8", errors="replace", timeout=30,
                    )
                    if ur.returncode == 0:
                        # ★인덱스 동결 방지(2026-08-04 GM 지시) — HEAD 만 전진시키고 끝내면
                        #   라이브 인덱스가 옛 트리에 동결돼 이후 맨손 커밋이 원격 추가분을
                        #   삭제로·원격 수정분을 되돌림으로 쓸어담는다. 통합 직후 바로 맞춘다.
                        synced = _sync_index_to_new_head(root, head, new)
                        # (다) 원격 추가분 실체화 — 인덱스 동기화 뒤에 호출(인덱스 기준으로 쓰므로).
                        filled = _fill_missing_from_index(root, head, new)
                        # (라) 뒤진 작업본 감지 — 실체화 뒤에 호출(디스크 최신 상태 기준으로 비교).
                        stale = _detect_stale_worktree_copies(root, head, new)
                        if stale:
                            warn = (
                                f"⚠️ 이 PC 파일 {len(stale)}개가 방금 들어온 최신본보다 뒤져 "
                                f"있습니다 — 그대로 커밋하면 남의 작업을 지웁니다: "
                                + ", ".join(stale[:10])
                                + (f" 외 {len(stale) - 10}건" if len(stale) > 10 else "")
                            )
                            print(warn, file=sys.stderr)
                            _log(f"POST_COMMIT_PUSH {warn}", root)
                        _log("POST_COMMIT_PUSH ok(작업트리 무접촉 통합 — 배245"
                             + (f" · 인덱스 동기화 {len(synced)}건" if synced else "")
                             + (f" · 실체화 {len(filled)}건" if filled else "")
                             + (f" · ★뒤진 작업본 {len(stale)}건" if stale else "")
                             + ")", root)
                        return True, ""
                    reason = _tail("update-ref 실패(그새 HEAD 이동): "
                                   + (ur.stderr or ur.stdout or "").strip())
                    _log(f"POST_COMMIT_PUSH {reason}", root)
                    return False, reason
            else:
                # 진짜 내용 충돌 — 자동 해결하지 않는다. 아래 일반 merge 로 내려가 사유를 남긴다.
                _log("POST_COMMIT_PUSH merge-tree 충돌/불가 — 일반 merge 로 사유 확인", root)
        # 폴백: merge — 워킹트리 reset 없이 통합(잠긴 바이너리와 무관)
        mg = subprocess.run(
            ["git", "merge", "--no-edit", f"{REMOTE}/{BRANCH}"],
            cwd=root, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=PUSH_TIMEOUT,
            env={**os.environ, "GIT_EDITOR": "true"},
        )
        if mg.returncode == 0:
            _log("POST_COMMIT_PUSH ok(after merge fallback)", root)
            return True, ""
        # merge 도 실패(진짜 내용 충돌·원격이 잠긴 파일 건드림·워킹트리 더러움 등) → 원상복구
        # ★실제 git stderr 를 남긴다(2026-07-30 GM 지시) — 예전엔 정적 문구만 남아 사유를
        # 알 수 없었다. mg.stderr 가 비면 stdout 으로 폴백(merge 는 충돌 요약을 stdout 에
        # 쓰는 경우가 있다).
        merge_reason = _tail("merge 실패: " + (mg.stderr or mg.stdout or "").strip())
        subprocess.run(
            ["git", "merge", "--abort"],
            cwd=root, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=20,
        )
        _clear_orphan_rebase(root)
        _log(f"POST_COMMIT_PUSH merge 폴백도 실패; aborted — {merge_reason}", root)
        return False, merge_reason
    except subprocess.TimeoutExpired:
        try:
            subprocess.run(["git", "rebase", "--abort"], cwd=root,
                           capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=15)
            subprocess.run(["git", "merge", "--abort"], cwd=root,
                           capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=15)
        except Exception:
            pass
        _clear_orphan_rebase(root)
        _log("POST_COMMIT_PUSH reconcile timeout; aborted", root)
        return False, "reconcile timeout"
    except Exception as e:
        reason = f"reconcile err {e}"
        try:
            _clear_orphan_rebase(root)
            _log(f"POST_COMMIT_PUSH {reason}", root)
        except Exception:
            pass
        return False, reason


def _do_push(root: str, allow_reconcile: bool = True, alert: bool = False) -> None:
    """push 1회 + 결과 로깅. 경합(non-ff) 거부 시 (lock 보유 경로에 한해) fetch+rebase 후 1회 재시도.

    alert=False(기본·매 커밋 훅 경로): 실패해도 텔레그램 경고를 보내지 않고 로그만 남긴다.
      커밋마다의 push 실패는 다세션 동시쓰기에서 정상적으로 발생하고 곧 self-heal/스위퍼가
      드레인하므로, GM 에게 알리면 false 알람 스팸이 된다(INC-008).
    alert=True(스위퍼 전용): 5분 주기 스위퍼가 안전하게 rebase·재시도하고도 끝내 실패한
      '진짜 막힘'만 경고한다."""
    rc, err = _push_once(root)
    if rc == 0:
        _log("POST_COMMIT_PUSH ok", root)
        _push_succeeded(root)
        return
    if rc == 124:
        _log("POST_COMMIT_PUSH timeout", root)
        if alert and _alert_should_send(root, "timeout"):
            _telegram_warn(
                root,
                "⚠️ 자동 push 타임아웃 — 스위퍼 재시도도 실패. 수동 `git push` 필요.",
            )
        return

    # 원격이 앞섬(경합) → fetch+rebase 후 재시도. ★근본해결(2026-06-24): 1회가 아니라
    # 백오프+지터 루프. 'cannot lock ref(원격 동시push)'는 재fetch+rebase 하면 풀리는
    # 일시 경합 — 동시 커밋이 몰리면 한 창에서 또 밀려 1회 재시도가 실패하던 문제를,
    # 최대 PUSH_RETRIES회 재시도+지터 백오프로 desync 해 사실상 항상 수렴시킨다.
    if allow_reconcile and _is_nonff(err):
        import time
        import random
        retries = int(os.environ.get("POST_COMMIT_PUSH_RETRIES", 5))
        for attempt in range(1, retries + 1):
            _log(f"POST_COMMIT_PUSH non-ff; reconcile+재시도 {attempt}/{retries}", root)
            reconciled, reconcile_reason = _reconcile(root)
            if not reconciled:
                # ★2026-07-30(GM 지시): 예전엔 여기서 err 를 안 바꿔 최종 로그가 맨 처음
                # push 거부 메시지("[rejected] non-fast-forward")를 그대로 재사용했다 —
                # 실제로 막은 건 fetch/merge 실패인데 그 사유가 안 보였다. reconcile 사유로 갱신한다.
                err = reconcile_reason or err
                break  # reconcile 자체 실패(진짜 충돌·타임아웃) → 경고 경로로
            rc2, err2 = _push_once(root)
            if rc2 == 0:
                _log(f"POST_COMMIT_PUSH ok(after reconcile, try {attempt})", root)
                _push_succeeded(root)
                return
            err = err2 or err
            if rc2 == 124 or not _is_nonff(err):
                break  # 타임아웃·비경합 실패(인증 등) → 재시도 무의미
            # 지터 백오프: 동시 push 들이 같은 순간 재시도해 또 충돌하는 걸 흩는다.
            time.sleep(min(3.0, 0.4 * attempt) + random.uniform(0, 0.4))

    err = (err or "").strip()[:200]
    _log(f"POST_COMMIT_PUSH fail {err}", root)
    # 같은 사유가 5분마다 GM 화면에 도배되지 않게 억제한다(배147 — 실제로 그렇게 됐다).
    # 사유가 바뀌면 바로 알린다. 억제해도 로그에는 매번 남으므로 흔적은 안 잃는다.
    if alert and _alert_should_send(root, err):
        _telegram_warn(
            root,
            "⚠️ 자동 push 가 스위퍼 재시도에도 실패 — origin 미동기화(커밋 로컬 보존). "
            f"수동 `git push` 필요.\n{err}",
        )


# ── 통합을 막는 '기계 산출물' 만 골라 먼저 커밋한다 (배147 · 2026-07-27) ──────────
#  왜: git merge 는 **로컬에서 고쳐진 파일을 원격도 고쳤을 때** 'local changes would be
#  overwritten' 으로 거부한다. 이 저장소에서 그 조건에 걸리는 건 거의 항상 3분·5분 주기
#  자동 산출물(문의 스냅샷·큐 미러 등)이다. 게다가 일부 스크립트는 git add 까지만 하고
#  커밋하지 않아(설계상 '커밋은 워처가') 공용 인덱스에 찌꺼기로 남는다 →
#  통합 창이 영영 안 열리고 non-fast-forward 가 **영구 지속**된다.
#  실측 2026-07-27: 미푸시 14건·26분 정체, 5분마다 같은 경보 반복, 라이브 Pages 가 최신 커밋 미수신.
#  고침: 통합 직전, **아래 목록에 정확히 해당하는 기계 산출물만** 정상 관문(safe_commit)으로
#  커밋해 길을 튼다. 소스코드·문서는 절대 손대지 않는다(남의 미완성 작업을 커밋해 버리는 사고 방지).
_MACHINE_OUTPUTS = (
    "status/inquiry_snapshot_lesson.json",
    "status/inquiry_snapshot_member.json",
    "3. 웰페리온 가이드/status/_queue.json",   # 큐 미러 — sync_queue_mirror 가 add 만 하고 커밋 안 함
    "3. 웰페리온 가이드/status/_queue_archive.json",
    # 아래 3개는 2026-07-27 실측에서 실제로 통합을 막고 있던 것들 — 전부 기계가 쓰는 산출물이다.
    #   status/_queue.json 은 사람이 아니라 도구(queue_dispatch·clevel_post_action·러너)가 쓰고
    #   쓰기는 queue_lock 으로 직렬화된다. worklog·home_kpi 스냅샷도 마찬가지.
    #   ※소스코드·문서·brief 는 여기 넣지 않는다 — 남의 미완성 작업을 커밋해 버리기 때문이다.
    "status/_queue.json",
    "status/worklog.jsonl",
    "status/home_kpi_snapshot.json",
    # ── 2026-07-30(GM 승인 · CTO 실측) 추가 — 새 로깅(위 _reconcile 수정)으로 잡은 실제
    #   차단 파일이 "3. 웰페리온 가이드/status/_queue.json"(이미 위에 있었는데도 막혔다 — 몇 초
    #   간격으로 다시 더러워지는 경합. _sweep() 의 재시도 루프가 이걸 흡수한다)이었던 것을 계기로,
    #   상시 더러운 나머지 기계 산출물도 전수 확인해 추가했다. 전부 grep 으로 쓰기 스크립트를
    #   실측 확인(사람이 손으로 고치는 파일 아님) — 판정 근거는 각 줄 주석.
    "logs/.tg_last_send",                        # scripts/tg_outbound_log.py
    "status/cmo_reaction_scorecard.json",         # scripts/reaction_scorecard.py 등
    "status/erp_status.json",                     # scripts/erp_status_publisher.py
    "status/incident_health.md",                  # ssot/incident_regression_monitor.py
    "status/kakao_dedup_ledger.json",             # scripts/kakao_report_sender.py
    "status/kakao_last_send.json",                # scripts/kakao_auto_daily_report.py 등
    "status/kpi_values.json",                     # scripts/build_voyage_map.py 등
    # ★2026-08-10 시토(배488) — 자율현황 🥁 쿵짝표가 읽는 파일이다. emit 은 3분마다
    #   돌고 있었는데(cpo_inquiry_snapshot.bat) 커밋이 안 붙어 HEAD 는 08-08 것에 멈춰
    #   있었다 — 화면은 멀쩡히 뜨고 어떤 경보도 안 울린다(voyage_map 과 같은 부류).
    #   전용 커밋을 3분마다 만들지 않고 여기 태운다: 커밋이 일어날 때 같이 올라간다(약속 L21).
    "status/kungjjak_today.json",                 # scripts/kungjjak_board.py --emit
    # ★2026-08-13 시토(배518) — 자율현황 학습제안 배지가 읽는 파일. ai_learning_proposer.py
    #   가 쓰기만 하고 자체 커밋이 없어(scripts/ai_learning_proposer.py 에 safe_commit 호출
    #   없음 실측 확인) kungjjak_today.json 과 같은 부류로 GM 화면이 뒤처졌다. 같은 관문에 흡수.
    "status/learning_proposals.json",             # scripts/ai_learning_proposer.py
    "status/module_silence_snapshot.json",        # scripts/module_silence_detector.py
    "status/northstar_reach.json",                # scripts/northstar_reach.py
    # ★2026-08-03 시토 — 자율현황 「북극성별 보기」가 raw.githubusercontent 로 읽는 파일이다.
    #   매일 만들어도 커밋이 안 되면 GM 화면은 그대로 옛날 것이다(9일 묵었던 실제 원인의 절반).
    "status/voyage_map.json",                     # scripts/build_voyage_map.py
    "status/parking_revenue.json",                # scripts/parking_revenue_crawler.py
    "status/publish_audit_state.json",            # scripts/publish_status_audit.py 등
    "status/weekly_bundle_pending_stream3_daily.json",
    "status/welly_auto_runner_ping_state.json",   # scripts/welly_auto_runner.py
    "status/welly_auto_runner_state.json",        # scripts/welly_auto_runner.py
    "telegram_bot/bot_heartbeat.txt",             # scripts/telegram_health_check.py 등
    # status/{role}.json 7종 — wellperion-agents/scripts/clevel_post_action.py 가 쓰는
    # C-Level 보조(메타) 상태(CLAUDE.md §5 · "완료건 부활 금지, 큐가 정본"). 사람이 직접 고치지 않는다.
    "status/ceo.json",
    "status/cfo.json",
    "status/chro.json",
    "status/cmo.json",
    "status/coo.json",
    "status/cpo.json",
    "status/cto.json",
)

# status/heartbeats/*.json — 전 C-Level 모듈 하트비트(각 collector 가 자기 것만 씀).
# 개별 나열 대신 디렉터리 전체를 기계 산출물로 취급한다 — 새 하트비트가 추가돼도(각 모듈이
# 자기 id 로 파일 하나씩 늘 뿐) 그때마다 이 목록을 또 고치지 않아도 되게(2026-07-30).
_MACHINE_OUTPUT_DIRS = (
    "status/heartbeats/",
    # ★2026-08-04 시토 — C-Level 브리프·아침 항로 근거. 예약작업이 만들기만 하고 아무도
    #   커밋하지 않아 GM 화면까지 못 갔다(실측: 브리프 9건 07-30~08-03 · 항로 5일치 전부
    #   미커밋. 생산자 3종에 커밋 코드가 아예 없었고, 5분 스위퍼는 '커밋된 것을 push' 만
    #   하므로 이 부류는 어느 관문에도 안 걸렸다). 폴더 단위로 잡아 새 브리프가 생겨도
    #   목록을 다시 고치지 않게 한다(위 heartbeats 와 같은 이유).
    "status/briefs/",
    "status/morning_plans/",
)


def _is_machine_output(p: str) -> bool:
    if p in _MACHINE_OUTPUTS:
        return True
    return any(p.startswith(d) for d in _MACHINE_OUTPUT_DIRS)


def _merge_blocking_paths(root: str) -> list:
    """통합을 막고 있는 경로 전부 — '로컬에서 바뀌었고(더러움) origin 도 바꾼' 것만.

    이것이 git merge 가 실제로 거부하는 조건이다("local changes would be overwritten
    by merge"). 단순히 '작업트리가 더러운가'가 아니다 — 이 저장소는 자동화 때문에
    항상 더럽기 때문에 그 기준으로는 merge 가 영원히 안 열린다(배245).
    """
    def _paths(args):
        r = subprocess.run(["git"] + args, cwd=root, capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=30)
        return {p for p in (r.stdout or "").split("\0") if p} if r.returncode == 0 else set()

    # git 이 실제로 거부하는 조건은 **두 가지**다(2026-07-31 격리 재현으로 확정 · 배245).
    #
    #  ⓐ 스테이징된 경로는 **원격이 그 파일을 건드렸든 말든 전부** 막는다.
    #     merge(ort)는 인덱스가 HEAD 와 일치할 것을 요구하기 때문이다. 격리 재현: 원격이
    #     손대지도 않은 f.txt 를 인덱스에만 스테이징해 두자 merge 가 f.txt 를 대며 거부했다.
    #     ★예전 판정이 이걸 놓친 두 겹의 이유 — `git diff HEAD` 는 HEAD↔**작업트리** 비교라
    #     인덱스에만 남은 옛 blob 을 아예 못 보고, 설령 봤어도 아래 upstream 과 교집합을
    #     내면 '원격이 안 건드린 파일'이라 걸러져 버린다. 실제로 판정이 "차단 0건"이라고
    #     답한 그 순간 merge 는 4건을 대며 거부했다(gm_profile_builder.py·gm_profile.md·
    #     gm_observation_ledger.jsonl·큐 미러 — 전부 인덱스에만 남은 찌꺼기).
    #
    #  ⓑ 작업트리만 더러운 경로는 **merge 가 그 파일을 덮어써야 할 때만** 막는다.
    #     이 저장소는 자동화 때문에 상시 20건 넘게 더러우므로(실측 23건), 여기서 교집합을
    #     안 내면 merge 창이 영영 안 열린다 — 그게 배245 정체의 절반이었다.
    #     교집합 상대는 두 점(HEAD↔origin 트리 직접 비교)이다. 세 점(HEAD...origin)은
    #     '합류점 이후 원격이 바꾼 것'만 주는데 merge 가 보는 건 **지금 두 트리의 차이**다
    #     (실측 2026-07-27: 세 점 0건 → 두 점에서 잡힘 → 실제 merge 도 그 파일로 거부).
    staged = _paths(["diff", "--cached", "--name-only", "-z"])         # HEAD ↔ 인덱스
    worktree = _paths(["diff", "--name-only", "-z", "HEAD"])           # HEAD ↔ 작업트리
    upstream = _paths(["diff", "--name-only", "-z", "HEAD", f"{REMOTE}/{BRANCH}"])
    return sorted(staged | (worktree & upstream))


def _blocking_machine_outputs(root: str) -> list:
    """통합을 막고 있는 것 중 **기계 산출물만** — 선커밋으로 길을 틀 수 있는 것들."""
    return [p for p in _merge_blocking_paths(root) if _is_machine_output(p)]


def _commit_machine_outputs(root: str, lock_timeout: int | None = None) -> bool:
    """막고 있는 기계 산출물을 safe_commit 으로 커밋. 하나도 없으면 False(무해한 no-op).

    lock_timeout: safe_commit.py 서브프로세스가 GitLock 을 기다릴 최대 초.
    None 이면 safe_commit 기본값(90s) 그대로. ★2026-07-30(GM 승인 · B안) —
    post-commit 훅 경로에서 부를 때는 짧게(2s) 준다: 이 훅은 "commit 을 만든 부모
    프로세스가 아직 같은 GitLock 을 쥔 채" 발화하는 경우가 흔하다(자동 커밋 경로 —
    safe_commit_cli 가 `git commit` 을 자기 lock 안에서 실행 → 그 commit 이 이 훅을
    동기 호출). 그 상황에서 90초씩 기다리면 매 커밋마다 스톨이 생긴다 — main() 이
    "post-commit-push" lock 을 2초로 시도하는 것과 같은 이유·같은 값이다. 짧게 실패해도
    무해(fail-open) — 다음 커밋 훅이나 5분 스위퍼가 다시 시도한다."""
    paths = _blocking_machine_outputs(root)
    if not paths:
        return False
    # ★2026-07-31(시토 · 배242 3번) — 효과 없는 반복을 멈춘다.
    #   왜: 2026-07-31 이 선커밋이 85초마다 돌며 'non-ff 해소' 커밋을 **589건**까지 찍었는데
    #   push 는 한 번도 성공하지 않았다. 길을 트는 커밋이 길을 안 트면 그건 더 이상 해결이
    #   아니라 증식이다. 연속 _PRECOMMIT_MAX_STREAK 회를 넘기면 커밋을 그만 찍고 알린다.
    #   카운터는 push 성공(_push_succeeded) 한 곳에서만 0 으로 돌아간다.
    st = _alert_state_read(root)
    streak = int(st.get("precommit_streak") or 0)
    if streak >= _PRECOMMIT_MAX_STREAK:
        if streak == _PRECOMMIT_MAX_STREAK:  # 넘어서는 순간 딱 한 번만 알린다(설계상)
            _log(f"PUSH_SWEEPER 선커밋 중단 — {streak}회 연속 찍고도 push 실패(배242)", root)
            # ★2026-08-01(시토 · 배265) — '무엇이 막고 있는지'를 경고에 같이 보낸다.
            #   왜: 2026-08-01 경보를 받고도 원인(종합접수처 파일 merge 충돌)을 찾는 데
            #   따로 실측이 필요했다. 막은 이유는 이미 이 상태파일에 적혀 있었는데
            #   경고 문구에만 없었다 — 새 수집기 없이 있는 값을 한 줄 더 보낸다(약속 L21).
            why = str(st.get("reason") or "").strip()
            # ★2026-08-15 GM 지시(중복 알림 정리) — "streak==20을 막 넘는 순간에만"이 설계였지만,
            #   이 저장소는 여러 프로세스가 동시에 push 를 재시도해 streak 가 성공→리셋→재적재를
            #   반복하며 짧은 시간에 몇 번씩 다시 20을 넘긴다(실측 8/10 5통·8/11 6통, 20~30분
            #   안·문구 동일). 이미 이 파일에 있는 같은 사유 60분 억제(_alert_should_send — 아래
            #   push 실패 경보와 같은 장치)를 그대로 재사용한다(새 억제 장치 안 만듦).
            if _alert_should_send(root, f"streak_max::{why}"):
                _telegram_warn(
                    root,
                    f"⚠️ 자동 push 가 {streak}회 연속 막혀 '통합 여는 커밋'을 중단했습니다.\n"
                    + (f"막은 이유: {why[:180]}\n" if why else "")
                    + "커밋은 로컬에 안전히 남아 있습니다 — 원인 확인이 필요합니다.",
                )
        st["precommit_streak"] = streak + 1
        _alert_state_write(root, st)
        return False
    st["precommit_streak"] = streak + 1
    _alert_state_write(root, st)
    msg = ("chore(auto): 통합을 막던 자동 산출물 커밋 — non-ff 해소 (배147)\n\n"
           "3분·5분 주기 산출물이 커밋되지 않은 채 남아 git merge 가 거부되어 push 가 정체됨.\n"
           "산출물 자체는 원래 커밋되는 자동 발행물이라 정상 관문으로 커밋해 통합 창을 연다.")
    try:
        env = os.environ.copy()
        if lock_timeout is not None:
            env["GIT_LOCK_ACQUIRE_TIMEOUT"] = str(lock_timeout)
        r = subprocess.run(
            [sys.executable, os.path.join(root, "scripts", "safe_commit.py"), "-m", msg, "--"] + paths,
            cwd=root, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=120, env=env,
        )
        ok = (r.returncode == 0)
        _log(f"PUSH_SWEEPER 기계산출물 선커밋 {'ok' if ok else 'fail'} ({len(paths)}건: {', '.join(paths)})", root)
        return ok
    except Exception as e:
        _log(f"PUSH_SWEEPER 기계산출물 선커밋 예외 {e}", root)
        return False


# ── 같은 사유 경보 도배 방지 (배147 · GM 이 5분마다 같은 문구를 받았다) ──────────────
_ALERT_STATE = "tmp/push_alert_state.json"
_ALERT_QUIET_SEC = 3600      # 같은 사유는 1시간에 1번만
_ALERT_STUCK_MAX_SEC = 1800  # 단 정체가 30분을 넘기면 같은 사유라도 반드시 알린다(배242)
_PRECOMMIT_MAX_STREAK = 20   # 선커밋을 20회 연속 찍고도 push 가 안 되면 멈추고 알린다(배242)


def _alert_state_read(root: str) -> dict:
    try:
        with open(os.path.join(root, *_ALERT_STATE.split("/")), encoding="utf-8") as f:
            st = json.load(f)
        return st if isinstance(st, dict) else {}
    except Exception:
        return {}


def _alert_state_write(root: str, st: dict) -> None:
    path = os.path.join(root, *_ALERT_STATE.split("/"))
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(st, f, ensure_ascii=False)
    except Exception:
        pass


def _push_succeeded(root: str) -> None:
    """push 가 실제로 성공했을 때만 부른다 — 정체 시계와 선커밋 연속 카운터를 0으로 되돌린다.
    이 두 값이 리셋되는 자리는 여기 하나뿐이다(정체 판정의 단일 기준점).

    ★2026-07-31 시토(GM "계속 들어오는 것 같은데?") — 풀렸으면 **풀렸다고 알린다.**
      그동안 확인방에는 '막혔다'만 가고 회복은 침묵이었다. 그래서 마지막 경보 뒤에 조용히
      해결돼도 GM 화면에는 나쁜 소식만 쌓인 채 남아, 이미 끝난 일이 계속 진행 중처럼 보였다
      (실측: 16:11~16:26 경보 3통 → 16:28 해소, 그런데 해소를 아무도 말해 주지 않았다).
      알림을 늘리는 게 아니라 **이미 보낸 경보를 닫아 주는 짝**이다 — 경보를 실제로 보낸
      적이 있을 때만(1통 나갔으면 1통 닫는다), 그리고 딱 한 번만 보낸다.
    """
    st = _alert_state_read(root)
    was_alerted = bool(st.get("key")) and bool(st.get("stuck_since"))
    if st.get("stuck_since") or st.get("precommit_streak"):
        import time
        stuck_min = int((time.time() - float(st.get("stuck_since") or 0)) / 60) if st.get("stuck_since") else 0
        st.pop("stuck_since", None)
        st.pop("precommit_streak", None)
        st.pop("forced_at", None)
        _alert_state_write(root, st)
        if was_alerted:
            _log(f"POST_COMMIT_PUSH 회복 — 정체 {stuck_min}분 만에 해소, 확인방에 닫힘 1통", root)
            _telegram_warn(
                root,
                f"✅ 자동 push 정상화 — 밀려 있던 것이 모두 올라갔습니다(정체 {stuck_min}분).\n"
                "앞서 보낸 push 실패 알림은 해소된 건입니다.",
            )


def _alert_should_send(root: str, reason: str) -> bool:
    """같은 사유가 조용한 시간 안에 또 오면 보내지 않는다. 사유가 바뀌면 즉시 보낸다.
    상태 파일을 못 읽고 못 써도 **보내는 쪽**으로 판단한다 — 경보를 잃는 것보다 낫다.

    ★2026-07-31(시토 · 배242 2번) — 억제에 **지속시간 상한**을 뒀다.
      왜: 2026-07-30~31 밤사이 같은 사유로 계속 억제되는 동안 라이브 화면이 **8시간+**
      멈춰 있었는데 아무에게도 알려지지 않았다. 억제는 도배를 막으려는 것이지 침묵하려는
      것이 아니다. 그래서 '같은 사유라도 정체가 _ALERT_STUCK_MAX_SEC 을 넘기면 반드시
      보낸다'를 얹는다(그 뒤로도 같은 간격으로만 — 도배 방지는 유지).

    ★2026-08-04(시토 · 텔레그램·카톡 전수점검) — read→write 임계구역에 락이 없어
      동시에 실행된 두 post_commit_push 프로세스가 같은 밀리초에 같은 상태를 읽고
      둘 다 '억제 안 걸림'으로 판단해 같은 경보를 2번 보냈다(실사고: 2026-08-04
      12:02:53·12:02:54 1초 간격 중복). 새 락 코드를 만들지 않고 이미 있는
      queue_lock(P2, msvcrt 크로스프로세스 락)을 다른 lock_name으로 재사용해
      임계구역(읽기~쓰기 전체)을 감싼다. 락을 못 잡아도(타임아웃) 기존 철학대로
      경보를 잃지 않는 쪽(락 없이 진행)으로 폴백한다."""
    import hashlib
    import time
    try:
        import queue_lock  # noqa: E402  (같은 scripts/ 폴더 · P2 크로스프로세스 락 재사용)
        _lock_cm = queue_lock.queue_lock(holder="post_commit_push", repo_root=root, lock_name="push_alert.lock")
    except Exception:
        from contextlib import nullcontext
        _lock_cm = nullcontext()
    try:
        with _lock_cm:
            return _alert_should_send_locked(root, reason)
    except Exception:
        # 락 타임아웃 등 — 경보를 잃는 것보다 락 없이 진행하는 쪽을 택한다(기존 철학과 동일).
        return _alert_should_send_locked(root, reason)


def _alert_should_send_locked(root: str, reason: str) -> bool:
    """_alert_should_send의 실제 판정 로직(락으로 감싸진 임계구역)."""
    import hashlib
    import time
    key = hashlib.sha256(reason.encode("utf-8", "replace")).hexdigest()[:16]
    now = time.time()
    st = _alert_state_read(root)

    # 정체 시계는 '연속 실패의 시작'을 기록한다 — 사유가 바뀌어도 이어진다(같은 정체이므로).
    stuck_since = float(st.get("stuck_since") or 0) or now
    stuck_for = now - stuck_since

    quiet = (st.get("key") == key and (now - float(st.get("at") or 0)) < _ALERT_QUIET_SEC)
    if quiet:
        forced_at = float(st.get("forced_at") or 0)
        if stuck_for >= _ALERT_STUCK_MAX_SEC and (now - forced_at) >= _ALERT_STUCK_MAX_SEC:
            _log(f"POST_COMMIT_PUSH 억제 해제 — 정체 {int(stuck_for / 60)}분 지속(상한 초과)", root)
            st.update({"key": key, "at": now, "forced_at": now,
                       "stuck_since": stuck_since, "reason": reason[:200]})
            _alert_state_write(root, st)
            return True
        _log(f"POST_COMMIT_PUSH 경보 억제(같은 사유 {int(now - float(st['at']))}s 전 발신 · "
             f"정체 {int(stuck_for / 60)}분)", root)
        st["stuck_since"] = stuck_since
        _alert_state_write(root, st)
        return False

    st.update({"key": key, "at": now, "stuck_since": stuck_since, "reason": reason[:200]})
    _alert_state_write(root, st)
    return True


_STALE_OUTPUT_SEC = 7200  # 2시간. 이만큼 미커밋으로 묵은 자동 산출물은 스스로 올린다.


def _commit_stale_machine_outputs(root: str) -> None:
    """★2026-07-31 시토 — **아무도 커밋하지 않는 자동 산출물**을 올린다.

    왜: 지금까지 자동 산출물은 '통합을 막을 때'만 커밋됐다(_commit_machine_outputs 는
    local ∩ upstream 만 본다). 그런데 원격이 건드리지 않는 파일은 영원히 그 교집합에
    들어가지 않는다 → 로컬에서만 매일 갱신되고 **한 번도 올라가지 않는다.**
    실측 2026-07-31: status/module_silence_snapshot.json 이 07-29 이후 이틀째 미커밋이라
    자율현황 라이브가 '카톡 매출보고 239시간 멈춤' 이라는 **거짓 빨간불**을 띄우고 있었다
    (같은 페이지의 예약작업 칸은 같은 시각 '정상'이라 서로 모순됐다). 파일은 멀쩡히
    갱신되고 있었고, 못 간 것은 저장소까지였다 — 자가점검이 말하는 '작업트리 고립'.

    안전: 대상은 이미 손으로 골라 둔 _MACHINE_OUTPUTS 목록뿐이다(사람이 편집하는 파일
    아님이 확인된 것들). 방금 쓰인 것은 건드리지 않고 _STALE_OUTPUT_SEC 이상 묵은 것만
    올린다 — 쓰는 중인 파일을 중간 상태로 커밋하지 않기 위해서다.
    """
    import time
    try:
        # HEAD 와 다른 추적 파일 전부(작업트리+인덱스). _merge_blocking_paths 는 '원격도 바꾼 것'
        # 교집합이라 여기 쓸 수 없다 — 여기서 찾는 건 정반대로 **아무도 안 건드려서 남은 것**이다.
        r = subprocess.run(
            ["git", "diff", "--name-only", "-z", "HEAD"],
            cwd=root, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=30,
        )
        if r.returncode != 0:
            return
        dirty = [p for p in (r.stdout or "").split("\0") if p]
        # ★2026-08-04 시토 — 아직 한 번도 커밋된 적 없는 산출물(미추적)도 대상에 넣는다.
        #   `git diff HEAD` 는 **추적 중인 파일의 변경**만 준다 — 새로 생긴 브리프처럼
        #   태어나서 한 번도 올라간 적 없는 파일은 여기 안 잡혀 영원히 로컬에만 남았다.
        #   (--exclude-standard = .gitignore 존중. 아래 _is_machine_output 허용목록으로
        #    한 번 더 좁히므로 목록 밖 파일은 여전히 손대지 않는다.)
        r2 = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard", "-z"],
            cwd=root, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=30,
        )
        if r2.returncode == 0:
            dirty += [p for p in (r2.stdout or "").split("\0") if p]
    except Exception:
        return
    now = time.time()
    stale = []
    for p in dirty:
        if not _is_machine_output(p):
            continue
        try:
            if now - os.path.getmtime(os.path.join(root, p)) >= _STALE_OUTPUT_SEC:
                stale.append(p)
        except Exception:
            continue
    if not stale:
        return
    msg = ("chore(auto): 자동 산출물 적재 — 저장소까지 못 가던 것 올림\n\n"
           "원격이 건드리지 않는 산출물은 '통합을 막는' 경우에만 커밋되던 구조라, 로컬에서만\n"
           "갱신되고 며칠씩 안 올라갔다. 그동안 라이브 화면은 옛 값을 사실처럼 보여준다.\n"
           f"{_STALE_OUTPUT_SEC // 3600}시간 이상 묵은 자동 산출물만 올린다.")
    try:
        r = subprocess.run(
            [sys.executable, os.path.join(root, "scripts", "safe_commit.py"), "-m", msg, "--"] + stale,
            cwd=root, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=120,
        )
        _log(f"PUSH_SWEEPER 묵은 산출물 적재 {'ok' if r.returncode == 0 else 'fail'} "
             f"({len(stale)}건: {', '.join(stale[:6])})", root)
    except Exception as e:
        _log(f"PUSH_SWEEPER 묵은 산출물 적재 예외 {e}", root)


def _detect_disk_reverted_to_history(root: str) -> list:
    """디스크가 이 PC 자신의 HEAD(이미 커밋한 기록)보다도 옛것인 파일을 찾는다.
    origin 과 무관 — 위 _check_remote_drift 의 사각지대를 메운다(배10978 · 2026-08-29).

    왜 origin 대조만으로는 못 잡나: 실측(coo/todo/업무 현황 SSOT.html) — HEAD 3876줄 =
    origin 3876줄인데 디스크는 3600줄이었다. head == theirs 라 위 함수는 아예 안 돈다.
    즉 원인은 'pull 안 함'이 아니라 이 PC 자신의 워킹트리가 자기 HEAD 를 못 따라간 것 —
    ① 파일 하나만 격리 커밋하는 임시 인덱스(R8) 프로토콜은 HEAD 만 전진시키고 워킹트리는
    안 건드린다 ② Start-AI-Morning.bat 의 git pull --rebase --autostash 가 오래 묵어
    이미 뒤에 다른 커밋으로 갱신된 dirty diff 를 그대로 되돌려 쓴다(실측: 이 커밋의
    autostash 가 2026-08-05 시점 blob 을 2026-08-18 에 그대로 재현 — 08-12·08-14·08-17
    세 번의 정식 갱신을 무효화). 어느 쪽이든 원격 fetch 로는 안 잡힌다.

    판정: 현재 dirty(HEAD 대비 수정)한 추적 파일마다 디스크 blob 해시가 그 경로의
    **과거(최신 아닌) 커밋 blob** 과 일치하면 '옛 버전이 되돌아온 것'으로 본다 — 새로
    쓰고 있는 WIP 편집이 과거 커밋과 바이트 단위로 우연히 일치할 확률은 사실상 0이다."""
    # ponytail: 경로 상한 150 — dirty 가 그 이상이면 이례적 상태라 이미 다른 경고가
    # 돈다. Windows 는 프로세스 기동 자체가 느려 파일당 1회씩 왕복하면 76개도 수십초가
    # 걸린다 — git cat-file --batch-check 로 커밋 대조를 한 프로세스에 묶는다.
    _MAX_PATHS = 150
    try:
        diff = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            cwd=root, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=30,
        )
        if diff.returncode != 0:
            return []
        paths = [x for x in diff.stdout.splitlines() if x.strip()][:_MAX_PATHS]
        paths = [p for p in paths if os.path.isfile(os.path.join(root, p))]
        if not paths:
            return []

        # 디스크 blob 해시 — 경로 전부 한 프로세스로(stdin-paths)
        ho = subprocess.run(
            ["git", "hash-object", "--stdin-paths"],
            cwd=root, input="\n".join(paths), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=30,
        )
        if ho.returncode != 0:
            return []
        disk_hash = dict(zip(paths, [h.strip() for h in ho.stdout.splitlines()]))

        reverted: list = []
        for p in paths:
            blob = disk_hash.get(p)
            if not blob:
                continue
            hist = subprocess.run(
                ["git", "log", "-60", "--format=%H", "HEAD", "--", p],
                cwd=root, capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=20,
            )
            commits = [c for c in hist.stdout.splitlines() if c.strip()]
            if len(commits) < 2:
                continue  # 과거 버전 자체가 없으면(신규 파일) 대조 대상 아님
            # commits[0]=현재 HEAD 판(이미 다르므로 제외) — 그 이전 커밋들만 배치 대조
            batch_in = "\n".join(f"{c}:{p}" for c in commits[1:])
            bc = subprocess.run(
                ["git", "cat-file", "--batch-check=%(objectname)"],
                cwd=root, input=batch_in, capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=20,
            )
            if bc.returncode == 0 and blob in bc.stdout.split():
                reverted.append(p)
        return reverted
    except Exception as e:
        _log(f"POST_COMMIT_PUSH HEAD 대비 옛버전 감지 실패(best-effort) {e}", root)
        return []


def _check_remote_drift(root: str) -> None:
    """★2026-08-13(시토 · 배591) — 로컬 커밋 시도가 0건이어도 origin 이 이 PC 를
    앞서 있는지 표면화한다(경고만·덮어쓰지 않음). ★2026-08-29(배10978) — 이 PC 자신의
    HEAD 보다도 디스크가 옛것인 경우(원격과 무관)도 함께 본다. 둘은 원인이 다르므로
    경고 문구를 갈라 적는다 — 하나로 뭉치면 'pull 하면 된다'로 오해한다(GM 지적).

    왜: 통합·뒤진작업본감지(_detect_stale_worktree_copies)는 지금까지 _reconcile()
    안에서만, 즉 **이 PC 가 로컬 커밋을 push 하려다 non-ff 로 막혔을 때만** 돌았다.
    이 PC 가 그 파일들을 아예 건드리지 않으면(도메인가드가 막거나 다른 세션만 고치는
    파일) fetch 자체가 안 돌아 영원히 못 알아챈다 — 실측(배591·2026-08-13): GM 승인
    기능 3건이 origin·HEAD 에는 이미 있는데 이 PC 디스크만 구버전으로 남아 있었다.
    ▸fetch 는 하되 checkout·merge·reset 은 절대 안 한다 — 감지·경고까지가 안전선
    (팀장 지시: 다른 세션이 편집 중인 파일을 덮어쓸 위험 때문에 일부러 자동화 범위
    밖에 둔다). 로직은 _detect_stale_worktree_copies 재사용(약속 L01 — 복제 금지)."""
    try:
        f = subprocess.run(
            ["git", "fetch", REMOTE, BRANCH],
            cwd=root, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=PUSH_TIMEOUT,
        )
        head = _rev_parse(root, "HEAD")

        # ① origin 이 이 PC(HEAD)를 앞서는 경우 — 진짜 'pull 필요'
        if f.returncode == 0 and head:
            theirs = _rev_parse(root, f"{REMOTE}/{BRANCH}")
            if theirs and head != theirs:
                stale = _detect_stale_worktree_copies(root, head, theirs)
                if stale:
                    warn = (
                        f"⚠️ [원격 지연] 이 PC 디스크 파일 {len(stale)}개가 origin 최신본보다 "
                        "뒤져 있습니다(origin 에 이미 들어온 변경을 이 PC 가 아직 못 받음 — "
                        "pull 로 해소됨) — 그대로 커밋하면 남의 작업을 지웁니다: "
                        + ", ".join(stale[:10])
                        + (f" 외 {len(stale) - 10}건" if len(stale) > 10 else "")
                    )
                    _log(f"PUSH_SWEEPER {warn}", root)
                    if _alert_should_send(root, warn):
                        _telegram_warn(root, warn)

        # ② 이 PC 자신의 HEAD 보다도 디스크가 옛것인 경우 — origin 무관, pull 로 안 풀림
        if head:
            reverted = _detect_disk_reverted_to_history(root)
            if reverted:
                warn2 = (
                    f"⚠️ [자체 표류] 이 PC 디스크 파일 {len(reverted)}개가 origin 이 아니라 "
                    "이 PC 자신의 HEAD(이미 커밋된 기록)보다도 옛 버전입니다 — pull 을 해도 "
                    "안 풀립니다(임시인덱스 격리커밋 또는 부팅 시 git pull --rebase --autostash "
                    "가 원인으로 추정). 그대로 커밋하면 이미 커밋된 내용을 되돌립니다. "
                    "★단 반대 경우도 있습니다 — 무관한 커밋이 이 파일을 쓸어담아 저장소 쪽이 "
                    "옛것이 된 경우에는 디스크가 옳습니다(실측 2026-08-31 접수_점수제_설계.md). "
                    "어느 쪽이 옳은지는 해당 파일의 최근 커밋 내용을 열어 판단하세요: "
                    + ", ".join(reverted[:10])
                    + (f" 외 {len(reverted) - 10}건" if len(reverted) > 10 else "")
                )
                _log(f"PUSH_SWEEPER {warn2}", root)
                if _alert_should_send(root, warn2):
                    _telegram_warn(root, warn2)
    except Exception as e:
        _log(f"PUSH_SWEEPER 원격 표류 감지 실패(best-effort) {e}", root)


def _sweep(root: str) -> int:
    """푸시 스위퍼 — 밀린 커밋을 안전하게 드레인(5분 주기 스케줄러용).
    부모 lock 밖에서 독립 실행되므로 GitLock 을 정상 타임아웃으로 획득해 fetch+rebase+push
    한다. 부모 lock 안에서 rebase 없이 실패한 커밋들을 여기서 확실히 올린다.
    진짜 실패(충돌·인증 등)만 경고한다(allow_reconcile=True · alert=True)."""
    # 밀린 커밋이 0이어도 여기는 먼저 본다 — '올릴 커밋이 없다'와 '올려야 할 산출물이
    # 커밋조차 안 됐다'는 다른 상태이고, 후자가 라이브를 옛 값으로 굳힌다.
    _commit_stale_machine_outputs(root)
    if _unpushed_count(root) == 0:
        _check_remote_drift(root)  # 배591 — 로컬 커밋이 없을 때만 fetch 조차 안 돌던 사각지대
        return 0  # 밀린 것 없음
    # ★락을 잡기 **전에** 통합 방해물을 치운다 — safe_commit 이 자기 락을 잡으므로
    #   락 안에서 부르면 서로 기다리다 멈춘다(GitLock 은 재진입 불가).
    #   그리고 **한 번으로는 부족하다**: 치운 직후 다시 더러워지는 경합이 실재한다
    #   (큐 미러는 몇 분마다 다시 쓰인다 — 실측 2026-07-27, 적체 33건까지 늘었다).
    #   그래서 '치우고 → 밀어보고 → 남았으면 다시 치우고' 를 몇 번 반복한다.
    #   각 회차는 그 순간 막고 있는 산출물만 커밋하므로 반복해도 부작용이 없다(멱등).
    #   ★2026-08-13(시토 · 배445) — 순서를 뒤집었다: **먼저 밀어보고, 안 되면 치운다.**
    #   왜: 배245 로 통합이 작업트리를 안 만지게 된 뒤로는 더러운 산출물이 push 를 막지 않는다.
    #   그런데 이 루프가 매 회차 선커밋을 먼저 불러, 필요하지도 않은 커밋을 하루 280건 찍었다
    #   (5분 주기 × 최대 3회차). 이제 선커밋은 **push 가 실제로 실패했을 때만** 도는 폴백이다.
    #   정상인 날에는 0건, 진짜 막힌 날에는 예전과 똑같이 3회차까지 시도한다(회복력 동일).
    for _round in range(1, 4):
        rc = _sweep_once(root)
        if _unpushed_count(root) == 0:
            return rc
        _log(f"PUSH_SWEEPER 재시도 {_round}/3 — 밀린 커밋 {_unpushed_count(root)}건 남음 "
             f"→ 막고 있는 산출물 선커밋 시도", root)
        _commit_machine_outputs(root)
    return 0


def _sweep_once(root: str) -> int:
    """한 회차 — 락을 잡고 통합·push 를 1회 시도한다."""
    import git_lock as _gl
    lock = GitLock("push-sweeper", root)
    prev = _gl.ACQUIRE_TIMEOUT
    try:
        _gl.ACQUIRE_TIMEOUT = 60  # 스위퍼는 lock 을 기다린다(진행 중 git 작업 양보)
        try:
            with lock:
                if _unpushed_count(root) == 0:
                    return 0  # lock 대기 중 다른 경로가 올림
                _log("PUSH_SWEEPER drain 시작", root)
                _do_push(root, allow_reconcile=True, alert=True)
                return 0
        except _gl.GitLockTimeout:
            _log("PUSH_SWEEPER lock busy; 다음 주기 재시도", root)
            return 0
    finally:
        _gl.ACQUIRE_TIMEOUT = prev


def main() -> int:
    root = _repo_root()

    if "--sweep" in sys.argv:
        try:
            return _sweep(root)
        except Exception as e:
            # ★스위퍼가 예외로 죽으면 여기서 exit 0 이 되어 스케줄러는 '성공'으로 본다.
            #   그 사이 밀린 커밋은 계속 쌓이는데 아무도 모른다(배10015 실측: cp949
            #   디코딩 크래시가 이 자리에서 통째로 삼켜져 드레인이 조용히 멎었다).
            #   → 밀린 커밋이 실제로 있을 때만 확인방에 1줄 알린다(없으면 무해하므로 침묵).
            try:
                _log(f"PUSH_SWEEPER skip(err) {e}", root)
                if _unpushed_count(root) != 0:
                    _telegram_warn(
                        root,
                        "⚠️ 자동 push 스위퍼가 오류로 중단 — 밀린 커밋이 남아 있습니다.\n"
                        f"{type(e).__name__}: {str(e)[:200]}",
                    )
            except Exception:
                pass
            return 0

    n = _unpushed_count(root)
    if n == 0:
        # 이미 동기화됨 — push 불필요(무한/불필요 push 방지).
        return 0

    # ★2026-08-13(시토 · 배445) — 여기서 선커밋을 **부르지 않는다.**
    #   원래 이유(2026-07-30): 미러가 더러운 채로 merge 에 들어가 실패했다.
    #   그 원인은 그 다음날 배245 가 구조로 없앴다 — 통합이 merge-tree/commit-tree/update-ref
    #   로 **작업트리를 아예 안 만지므로** 더러운 파일이 통합을 막지 못한다(위 _do_push 주석
    #   500~521행이 그 판정을 그대로 적고 "겹침 전부 기계 산출물 — 그대로 진행"으로 지난다).
    #   그런데 이 호출만 남아, 통합에 필요하지도 않은 커밋을 **매 커밋마다** 찍었다.
    #   실측(2026-08-13 · 최근 24시간): 총 커밋 841건 중 이 문구가 280건. GM 지적
    #   "코드 자동화도 chore 는 의미가 없고"의 실체다. 커밋 기록뿐 아니라 배 note 까지
    #   덮어 무엇을 언제 왜 고쳤는지 못 읽게 만들었다(배464 note 에 13줄).
    #   ▸없애는 것이 아니라 **진짜 필요할 때만** 남긴다: push 가 실제로 막히면 5분 스위퍼가
    #     '밀어보고 → 안 되면 선커밋 → 다시 밀어보기' 순서로 부른다(_sweep_pending).
    #   ▸산출물을 저장소에 올리는 일 자체는 _commit_stale_machine_outputs 가 이미 맡고 있다
    #     (2시간 신선도 가드 · 하루 17건). 그쪽이 정상 경로다.

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
            # 단 rebase 는 부모 시퀀스(진행 중 HEAD)를 흔들 수 있어 금지(allow_reconcile=False).
            _log("POST_COMMIT_PUSH within-parent-lock; push without lock(no rebase)", root)
            _do_push(root, allow_reconcile=False)
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
