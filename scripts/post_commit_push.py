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


def _push_once(root: str) -> tuple[int, str]:
    """git push 1회. (returncode, stderr) 반환. 타임아웃은 rc=124."""
    try:
        r = subprocess.run(
            ["git", "push", REMOTE, f"HEAD:{BRANCH}"],
            cwd=root,
            capture_output=True,
            text=True, encoding="utf-8", errors="replace",
            timeout=PUSH_TIMEOUT,
        )
        return r.returncode, (r.stderr or r.stdout).strip()
    except subprocess.TimeoutExpired:
        return 124, "timeout"


def _is_nonff(err: str) -> bool:
    """원격이 앞서서 거부된(경합) 케이스인지."""
    low = (err or "").lower()
    return any(
        k in low
        for k in ("fast-forward", "fetch first", "non-fast", "rejected", "stale info")
    )


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


def _reconcile(root: str) -> bool:
    """원격이 앞섰을 때 fetch 후 로컬 커밋을 origin 위로 통합.
    ★언제나 merge 로만 통합한다(rebase 경로는 배147에서 껐다 — 아래 _ALLOW_REBASE 주석 참고).
    성공 True / 실패 False. 어떤 경우에도 half-state 안 남김(abort + 고아 강제정리).
    (호출자가 git_lock 임계구역 보유 상태에서만 호출 — 동시 로컬 git 없음 보장.)

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
            return False
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
                return True
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
        # merge — 워킹트리 reset 없이 통합(잠긴 바이너리와 무관)
        mg = subprocess.run(
            ["git", "merge", "--no-edit", f"{REMOTE}/{BRANCH}"],
            cwd=root, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=PUSH_TIMEOUT,
            env={**os.environ, "GIT_EDITOR": "true"},
        )
        if mg.returncode == 0:
            _log("POST_COMMIT_PUSH ok(after merge fallback)", root)
            return True
        # merge 도 실패(진짜 내용 충돌·원격이 잠긴 파일 건드림 등) → 원상복구
        subprocess.run(
            ["git", "merge", "--abort"],
            cwd=root, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=20,
        )
        _clear_orphan_rebase(root)
        _log("POST_COMMIT_PUSH merge 폴백도 실패; aborted (fall back to warn)", root)
        return False
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
        return False
    except Exception as e:
        try:
            _clear_orphan_rebase(root)
            _log(f"POST_COMMIT_PUSH reconcile err {e}", root)
        except Exception:
            pass
        return False


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
            if not _reconcile(root):
                break  # reconcile 자체 실패(진짜 충돌·타임아웃) → 경고 경로로
            rc2, err2 = _push_once(root)
            if rc2 == 0:
                _log(f"POST_COMMIT_PUSH ok(after reconcile, try {attempt})", root)
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
)


def _blocking_machine_outputs(root: str) -> list:
    """통합을 막고 있는 기계 산출물 경로 — '로컬에서 바뀌었고 origin 도 바꾼' 것만."""
    def _paths(args):
        r = subprocess.run(["git"] + args, cwd=root, capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=30)
        return {p for p in (r.stdout or "").split("\0") if p} if r.returncode == 0 else set()

    local = _paths(["diff", "--name-only", "-z", "HEAD"])          # 인덱스·작업트리 통틀어 HEAD 와 다른 것
    # ★두 점(트리 직접 비교)이어야 한다. 세 점(HEAD...origin)은 '합류점 이후 원격이 바꾼 것'만 주는데,
    #   merge 가 거부하는 조건은 그게 아니라 **지금 HEAD 와 원격 트리가 다른 파일**이다.
    #   실측 2026-07-27: 세 점으로는 차단 파일이 0건으로 보였는데 두 점으로는 잡혔고,
    #   실제 merge 는 바로 그 파일을 이유로 거부했다("local changes would be overwritten").
    upstream = _paths(["diff", "--name-only", "-z", "HEAD", f"{REMOTE}/{BRANCH}"])
    return [p for p in _MACHINE_OUTPUTS if p in local and p in upstream]


def _commit_machine_outputs(root: str) -> bool:
    """막고 있는 기계 산출물을 safe_commit 으로 커밋. 하나도 없으면 False(무해한 no-op)."""
    paths = _blocking_machine_outputs(root)
    if not paths:
        return False
    msg = ("chore(auto): 통합을 막던 자동 산출물 커밋 — non-ff 해소 (배147)\n\n"
           "3분·5분 주기 산출물이 커밋되지 않은 채 남아 git merge 가 거부되어 push 가 정체됨.\n"
           "산출물 자체는 원래 커밋되는 자동 발행물이라 정상 관문으로 커밋해 통합 창을 연다.")
    try:
        r = subprocess.run(
            [sys.executable, os.path.join(root, "scripts", "safe_commit.py"), "-m", msg, "--"] + paths,
            cwd=root, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=120,
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


def _alert_should_send(root: str, reason: str) -> bool:
    """같은 사유가 조용한 시간 안에 또 오면 보내지 않는다. 사유가 바뀌면 즉시 보낸다.
    상태 파일을 못 읽고 못 써도 **보내는 쪽**으로 판단한다 — 경보를 잃는 것보다 낫다."""
    import hashlib
    import time
    key = hashlib.sha256(reason.encode("utf-8", "replace")).hexdigest()[:16]
    path = os.path.join(root, *_ALERT_STATE.split("/"))
    now = time.time()
    try:
        with open(path, encoding="utf-8") as f:
            st = json.load(f)
        if st.get("key") == key and (now - float(st.get("at", 0))) < _ALERT_QUIET_SEC:
            _log(f"POST_COMMIT_PUSH 경보 억제(같은 사유 {int(now - float(st['at']))}s 전 발신)", root)
            return False
    except Exception:
        pass
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"key": key, "at": now, "reason": reason[:200]}, f, ensure_ascii=False)
    except Exception:
        pass
    return True


def _sweep(root: str) -> int:
    """푸시 스위퍼 — 밀린 커밋을 안전하게 드레인(5분 주기 스케줄러용).
    부모 lock 밖에서 독립 실행되므로 GitLock 을 정상 타임아웃으로 획득해 fetch+rebase+push
    한다. 부모 lock 안에서 rebase 없이 실패한 커밋들을 여기서 확실히 올린다.
    진짜 실패(충돌·인증 등)만 경고한다(allow_reconcile=True · alert=True)."""
    if _unpushed_count(root) == 0:
        return 0  # 밀린 것 없음
    # ★락을 잡기 **전에** 통합 방해물을 치운다 — safe_commit 이 자기 락을 잡으므로
    #   락 안에서 부르면 서로 기다리다 멈춘다(GitLock 은 재진입 불가).
    _commit_machine_outputs(root)
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
