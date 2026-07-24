# scripts/safe_commit.py
# 전 C-Level 공용 "스테일 트리 차단" 안전 커밋터 (2026-07-23, CMO 신설 · 배9820).
#
# 계기: 공용 작업트리 레이스 — 커밋 준비 시점에 읽은 트리를 나중 parent 위에 커밋해
#   ①남의 미커밋 변경분을 내 커밋이 쓸어담거나(이력 귀속 어긋남, 2026-07-23 하루 4회 관측)
#   ②그 사이 들어온 파일이 '삭제'로 기록되는(2026-07-21 AI하루 10편 190파일 삭제) 사고.
#   상세 실측 = status/briefs/시모_커밋스테일트리_제기_20260723.md.
#
# 차단 원리(2026-07-23 커밋 8244b4acb 에서 혼입 0건 실증된 절차를 그대로 함수화):
#   1) 라이브 인덱스에 손대지 않는다 — GIT_INDEX_FILE 로 임시 인덱스를 쓰고,
#      그 임시 인덱스는 라이브 index 복사가 아니라 `read-tree HEAD` 로 시작한다
#      (라이브 index 를 cp 하면 남의 staged 파일이 전부 딸려온다 — 기억 박제 2건).
#   2) 지정 경로만 stage → write-tree.
#   2-b) ★선검증(2026-07-24, 배10009) — commit-tree/update-ref *이전*, 트리 대 트리
#      비교로 무관 경로 혼입·유령 삭제(디스크엔 있는데 삭제로 staged)를 판정한다.
#      걸리면 커밋 자체를 만들지 않고 그 자리에서 중단한다. (구 결함: 이 판정이
#      update-ref *이후*에 돌아 탐지는 해도 이미 만들어진 나쁜 커밋이 그대로 origin
#      까지 push 됐다 — scripts/precommit_phantom_delete_guard.py 의 디스크 존재
#      판정 방식을 재사용해 앞당김. safe_commit 은 commit-tree/update-ref 라 git
#      훅이 안 걸려 그 가드가 원래 이 경로에선 발화하지 않는다.)
#   3) commit-tree 직전 HEAD 재검증 — 트리 읽은 뒤 HEAD 가 움직였으면 폐기하고 재시도.
#   4) `git update-ref HEAD <new> <old>` CAS 로 원자 갱신 — 경쟁 커밋이 끼어들면
#      update-ref 자체가 실패하고 재시도(락만으로는 못 막는 틈을 git 이 막아준다).
#   5) 커밋 후 사후 재확인(방어적) — 선검증과 같은 트리라 정상 상황엔 항상 통과.
#      push 게이트는 committed 가 아니라 ok 를 본다(혼입 감지 시 push 도 막힘).
#
# 직렬화 락은 기존 scripts/git_lock.py 의 GitLock 을 그대로 재사용한다(중복 구현 금지).
# push 도 기존 scripts/post_commit_push.py 를 그대로 호출한다 — update-ref 는 post-commit
#   훅을 발화시키지 않으므로(훅은 `git commit` 경로 전용) 명시 호출이 필요하다.
#
# ★작업트리를 바꾸는 git 명령(reset·checkout --·rebase)은 이 모듈에서 절대 쓰지 않는다.
#
# API:
#   from safe_commit import safe_commit
#   res = safe_commit(paths, message, holder="ig_publish_verify")
#   res = {"ok":bool, "committed":bool, "sha":str, "attempts":int,
#          "changed":[경로...], "foreign":[혼입경로...], "reason":str}
#
# CLI(자체 검증·수동 커밋용):
#   python scripts/safe_commit.py -m "메시지" --no-push -- <경로1> <경로2>
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(r"C:\Users\jjky0\welperion-automation")

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from git_lock import GitLock  # noqa: E402  (같은 scripts/ 폴더 — 락 로직 재사용)

_MAX_RETRIES = 5          # HEAD 경합 재시도 상한(경쟁 커밋이 계속 끼어들면 실패 보고)
_RETRY_WAIT_SEC = 0.4
_INDEX_LOCK_WAIT_SEC = 0.5
_INDEX_LOCK_RETRIES = 6   # index.lock 은 지우지 않는다 — 대기 후 재시도만 한다


def _git(args: list[str], root: Path, env: dict | None = None,
         check: bool = False) -> subprocess.CompletedProcess:
    run_env = dict(os.environ)
    if env:
        run_env.update(env)
    return subprocess.run(
        # core.quotepath=false — git 기본값은 한글 등 비ASCII 경로를 "\355\201..." 로 인용해
        # 출력한다. 그러면 ⑤ 사후검증의 경로 비교가 전부 어긋나 정상 커밋도 '혼입'으로 오판하고,
        # _sync_live_index 의 ls-tree/ls-files 대조도 깨진다(=임시 인덱스 후처리 무력화 →
        # 2026-07-21 삭제 사고 경로 재개통). 한글 폴더가 표준인 저장소라 전 호출에 고정한다.
        # (2026-07-23 격리 재현으로 실측 — instagram/.../큐레이션_추천.md 가 혼입으로 오판됨)
        ["git", "-C", str(root), "-c", "core.quotepath=false", *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        env=run_env, check=check,
    )


def _git_out(args: list[str], root: Path, env: dict | None = None) -> str:
    r = _git(args, root, env)
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} 실패(rc={r.returncode}): {r.stderr.strip()}")
    return r.stdout.strip()


def _rel(path, root: Path) -> str:
    """저장소 상대 posix 경로로 정규화(절대·상대 입력 모두 허용)."""
    p = Path(str(path))
    if not p.is_absolute():
        p = root / p
    try:
        return p.resolve().relative_to(root.resolve()).as_posix()
    except Exception:
        return Path(str(path)).as_posix()


def _tree_entries(rev: str, rel_paths: list[str], root: Path) -> dict[str, tuple[str, str]]:
    """ls-tree 로 지정 경로의 (mode, blob) 맵. rev 가 없으면 빈 맵."""
    out = _git(["ls-tree", "-r", rev, "--", *rel_paths], root)
    entries: dict[str, tuple[str, str]] = {}
    if out.returncode != 0:
        return entries
    for line in out.stdout.splitlines():
        if "\t" not in line:
            continue
        meta, path = line.split("\t", 1)
        parts = meta.split()
        if len(parts) >= 3:
            entries[path.strip()] = (parts[0], parts[2])
    return entries


def _index_entries(rel_paths: list[str], root: Path) -> dict[str, tuple[str, str]]:
    """라이브 인덱스의 (mode, blob) 맵(stage 0 만)."""
    out = _git(["ls-files", "-s", "--", *rel_paths], root)
    entries: dict[str, tuple[str, str]] = {}
    if out.returncode != 0:
        return entries
    for line in out.stdout.splitlines():
        if "\t" not in line:
            continue
        meta, path = line.split("\t", 1)
        parts = meta.split()
        if len(parts) >= 3 and parts[2] == "0":
            entries[path.strip()] = (parts[0], parts[1])
    return entries


def _tree_diff_status(tree_a: str, tree_b: str, root: Path) -> list[tuple[str, str]]:
    """두 트리 객체를 직접 비교(커밋 없이도 가능) — [(status, path), ...].

    diff-tree 는 커밋 없이 트리-트리 비교를 지원하므로 commit-tree/update-ref
    *이전*에도 검증할 수 있다(배10009 선검증의 핵심 — rename/copy 감지(-M/-C)는
    안 켜므로 status 는 항상 단일 문자 + 경로 1개 쌍으로만 나온다).
    """
    out = _git(["diff-tree", "--no-commit-id", "--name-status", "-r", "-z",
                tree_a, tree_b], root)
    if out.returncode != 0:
        raise RuntimeError(f"git diff-tree 실패(rc={out.returncode}): {out.stderr.strip()}")
    tokens = [t for t in out.stdout.split("\x00") if t]
    pairs: list[tuple[str, str]] = []
    for i in range(0, len(tokens) - 1, 2):
        pairs.append((tokens[i][:1], tokens[i + 1]))
    return pairs


# ── 훅가드 이식(2026-07-24 · 웰리 가드모듈 병합지도 §2 사각지대 봉합) ──────────
# safe_commit 은 commit-tree/update-ref 라 git 훅(.git/hooks/pre-commit)이
# 전혀 안 걸린다(위 _precheck_violations 주석 참조) — 그 훅 안 가드 10개가
# 전부 이 경로에서 미발화한다는 게 조사로 확인됐다(status/briefs/
# 웰리_가드모듈_병합지도_20260724.md §2). 그중 위험도 최상위 3개(비밀값·
# 대량유실·공식값)만 1단계로 이식한다 — 로직은 복제하지 않고 기존 가드
# 스크립트를 그대로 서브프로세스로 호출한다(L01, 단일 지점 재사용).
# 나머지 7개(queue·incident·erp_anchor·sheet_link·chatid_drift·
# reception_drift·phantom_delete)는 이번엔 이식하지 않는다 — phantom_delete
# 는 이미 위 _precheck_violations 가 대체 판정 중이고, 나머지는 오탐 위험
# 검증 전엔 동시 커밋 중인 다른 세션 전부를 막을 수 있어 2단계로 미룬다.
_HOOK_GUARDS = (
    ("secret", "precommit_secret_guard.py"),
    ("truncation", "precommit_truncation_guard.py"),
    ("enforcement", "precommit_enforcement_guard.py"),
)


def _run_hook_guards(root: Path, index_path: Path) -> list[str]:
    """이식된 훅가드 3종을 임시 인덱스 기준으로 실행 — 위반 메시지 목록(비면 통과).

    각 가드는 내부적으로 `git diff --cached`/`git cat-file -p :path` 로 스테이징
    상태를 읽는다 — 둘 다 GIT_INDEX_FILE 환경변수를 그대로 존중하므로, 이 임시
    인덱스를 가리키게 하면 safe_commit 이 stage 한 내용만 정확히 본다(라이브
    인덱스는 안 건드림). cwd=root 로 실행해 각 가드의 내부 git 호출이 이 저장소를
    보게 한다.

    ★enforcement 가드의 GM 승인 우회([GM-approved])는 `.git/COMMIT_EDITMSG` 를
      읽는데(ssot/enforcement.py:_commit_message) safe_commit 경로엔 그 파일이
      "이번" 커밋 메시지를 담고 있지 않다(옛 커밋의 메시지이거나 비어있음) —
      알려진 한계. 단 enforcement_mode.json 기본값이 warn/off(둘 다 절대
      비차단)라 지금은 실질 위험 없음. mode=block 전환 시엔 이 한계부터 반드시
      보완할 것(§2 참고, 이 함수를 다시 고치지 말고 ssot/enforcement.py 쪽에
      commit_message 인자를 받는 진입점을 추가하는 방향).
    """
    run_env = dict(os.environ)
    run_env["GIT_INDEX_FILE"] = str(index_path)
    run_env["PYTHONUTF8"] = "1"
    violations: list[str] = []
    for label, fname in _HOOK_GUARDS:
        script = _SCRIPTS_DIR / fname
        if not script.exists():
            continue  # 가드 파일 없음 = fail-open(기존 훅 규약과 동일)
        try:
            r = subprocess.run(
                [sys.executable, str(script)],
                cwd=str(root), env=run_env,
                capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=30,
            )
        except Exception as exc:
            # 가드 실행 자체 실패 = fail-open(기존 훅 규약과 동일 — 가드 버그로
            # 전 커밋이 막히면 안 됨).
            print(f"[WARN] {label} 가드 실행 실패(fail-open): {type(exc).__name__}: {exc}")
            continue
        if r.returncode == 1:
            msg = (r.stderr or r.stdout or "").strip()
            violations.append(f"[{label}] {msg[:500]}")
    return violations


def _precheck_violations(head_tree: str, tree: str, rel_paths: list[str], root: Path) -> list[str]:
    """commit-tree/update-ref *이전* 선검증(배10009) — 무관 경로 혼입 + 유령 삭제 판정.

    ★기존 결함: 이 판정이 update-ref 이후에 돌아 탐지는 해도 이미 만들어진
      나쁜 커밋을 origin 까지 그대로 push 해버렸다(감지는 정확, 차단 실패).
      이 함수를 write-tree 직후·commit-tree 이전에 호출해 문제가 있으면
      커밋 자체를 만들지 않고 중단하도록 바로잡는다.
    ★판정 로직은 새로 짜지 않고 scripts/precommit_phantom_delete_guard.py 의
      "삭제로 표시됐는데 디스크엔 실존" 판정 방식을 그대로 재사용한다 — 그
      가드는 git 훅(pre-commit)에서만 발화하는데 safe_commit 은 commit-tree
      /update-ref 라 훅이 아예 안 걸린다(가드 사각지대).
    - 무관 경로 혼입: rel_paths 밖의 경로가 조금이라도 바뀌면 위반(추가·수정·
      삭제 무관 — safe_commit 계약상 지정 경로 밖은 절대 손대면 안 됨).
    - 유령 삭제: rel_paths 안이라도 삭제(D)로 표시됐는데 작업트리(디스크)에
      파일이 실존하면 위반. 디스크에도 없으면 의도된 정당한 삭제 — 통과.
    """
    violations: list[str] = []
    for status, path in _tree_diff_status(head_tree, tree, root):
        in_scope = any(path == rp or path.startswith(rp + "/") for rp in rel_paths)
        if not in_scope:
            violations.append(f"무관 경로 혼입: {status} {path}")
            continue
        if status == "D" and (root / path).exists():
            violations.append(f"유령 삭제(디스크엔 실존): {path}")
    return violations


def _sync_live_index(rel_paths: list[str], root: Path, old_head: str, new_sha: str) -> list[str]:
    """커밋 후 라이브 인덱스의 '옛 HEAD 기준' 항목만 새 커밋 기준으로 동기화한다.

    ★왜 필요한가(격리 테스트로 실측, 2026-07-23): 임시 인덱스로 커밋하면 라이브 인덱스는
      옛 HEAD 스냅샷 그대로 남는다 → 내가 새로 추가한 파일이 라이브 인덱스에선 '삭제(D)'로
      보이고, 그 상태에서 다른 세션이 커밋하면 내 파일이 '삭제'로 기록된다(2026-07-21
      AI하루 190파일 삭제 사고의 물리 경로). 기억 박제 2건("임시인덱스 뒤 인덱스 정리 필수")의
      코드 이행.

    ★안전장치: 라이브 인덱스 항목이 옛 HEAD 와 같은 경우(=다른 세션이 자기 것을 stage 해두지
      않은 경우)에만 동기화한다. 다르면 남의 staged 내용이므로 손대지 않는다.
      작업트리는 건드리지 않는다(update-index = 인덱스 전용 · reset/checkout 미사용).
    """
    old_map = _tree_entries(old_head, rel_paths, root)
    new_map = _tree_entries(new_sha, rel_paths, root)
    live_map = _index_entries(rel_paths, root)
    add_lines: list[str] = []
    remove_paths: list[str] = []
    for path in set(old_map) | set(new_map) | set(live_map):
        live = live_map.get(path)
        old = old_map.get(path)
        new = new_map.get(path)
        if live == new:
            continue
        if live != old:
            continue  # 다른 세션이 stage 해둔 자기 내용 — 절대 덮지 않는다
        if new:
            add_lines.append(f"{new[0]} {new[1]}\t{path}")
        else:
            remove_paths.append(path)
    synced = [ln.split("\t", 1)[1] for ln in add_lines] + remove_paths
    try:
        if add_lines:
            # stdin 은 반드시 bytes — text=True 로 주면 Windows 에서 "\n"→"\r\n" 로 번역돼
            # 경로 끝에 CR 이 붙고 update-index 가 조용히 실패한다(2026-07-23 격리 테스트로 실측).
            payload = ("\n".join(add_lines) + "\n").encode("utf-8")
            r = subprocess.run(
                ["git", "-C", str(root), "update-index", "--add", "--index-info"],
                input=payload, capture_output=True, timeout=60,
            )
            if r.returncode != 0:
                print(f"[WARN] 라이브 인덱스 동기화 실패(best-effort): "
                      f"{r.stderr.decode('utf-8', 'replace').strip()}")
        if remove_paths:
            _git(["update-index", "--force-remove", "--", *remove_paths], root)
    except Exception as exc:  # best-effort — 커밋은 이미 성공했다
        print(f"[WARN] 라이브 인덱스 동기화 실패(best-effort): {type(exc).__name__}: {exc}")
    return synced


def _stage_with_retry(rel_paths: list[str], root: Path, env: dict) -> None:
    """지정 경로만 임시 인덱스에 stage. index.lock 경합은 지우지 말고 대기 후 재시도."""
    last_err = ""
    for attempt in range(_INDEX_LOCK_RETRIES):
        r = _git(["add", "--", *rel_paths], root, env)
        if r.returncode == 0:
            return
        last_err = (r.stderr or r.stdout).strip()
        if "index.lock" not in last_err.lower():
            raise RuntimeError(f"git add 실패: {last_err}")
        time.sleep(_INDEX_LOCK_WAIT_SEC)
    raise RuntimeError(f"git add 실패(index.lock 대기 초과): {last_err}")


def safe_commit(
    paths,
    message: str,
    holder: str = "safe_commit",
    repo_root=None,
    push: bool = True,
    max_retries: int = _MAX_RETRIES,
) -> dict:
    """지정 경로만 담아 HEAD 재검증 + update-ref CAS 로 원자 커밋한다.

    paths: 커밋할 경로 목록(절대·상대 모두 허용). 이 목록 밖 파일은 절대 커밋되지 않는다.
    push:  True 면 커밋 성공 후 기존 post_commit_push.py 호출(update-ref 는 post-commit
           훅을 발화시키지 않으므로 명시 호출). 실패해도 커밋은 유지(fail-open).
    반환:  {"ok","committed","sha","attempts","changed","foreign","reason"}
           - committed=False, ok=True → 변경 없음(무해 통과)
           - foreign 이 비어있지 않으면 혼입 발생 → ok=False (보고용)
    """
    root = Path(repo_root) if repo_root else ROOT
    rel_paths = [_rel(p, root) for p in paths if str(p).strip()]
    result = {"ok": False, "committed": False, "sha": "", "attempts": 0,
              "changed": [], "foreign": [], "hook_violations": [], "index_synced": [], "reason": ""}
    if not rel_paths:
        result["ok"] = True
        result["reason"] = "대상 경로 없음"
        return result

    index_path = root / ".git" / f"safe_commit_index_{os.getpid()}"
    env = {"GIT_INDEX_FILE": str(index_path)}

    try:
        with GitLock(holder=holder, repo_root=str(root)):
            for attempt in range(1, max_retries + 1):
                result["attempts"] = attempt
                # ① 임시 인덱스를 HEAD 트리로 시작(라이브 index 복사 금지)
                index_path.unlink(missing_ok=True)
                head = _git_out(["rev-parse", "HEAD"], root)
                _git_out(["read-tree", "HEAD"], root, env)

                # ② 지정 경로만 stage
                _stage_with_retry(rel_paths, root, env)
                tree = _git_out(["write-tree"], root, env)

                head_tree = _git_out(["rev-parse", f"{head}^{{tree}}"], root)
                if tree == head_tree:
                    result["ok"] = True
                    result["reason"] = "변경 없음(nothing to commit)"
                    return result

                # ②-b 선검증(배10009) — commit-tree/update-ref *이전* 트리-트리 비교로
                # 무관 경로 혼입·유령 삭제를 판정한다. 걸리면 커밋 자체를 만들지 않고
                # 즉시 중단(재시도 안 함 — HEAD 레이스가 아니라 스테이징 내용 자체의
                # 문제라 재시도해도 그대로 재현된다).
                violations = _precheck_violations(head_tree, tree, rel_paths, root)
                if violations:
                    result["foreign"] = violations
                    result["reason"] = (
                        f"선검증 실패(커밋 생성 안 함) — {violations[0]}"
                        + (f" 외 {len(violations) - 1}건" if len(violations) > 1 else "")
                    )
                    return result

                # ②-c 훅가드 이식(2026-07-24) — secret·truncation·enforcement.
                # 같은 임시 인덱스를 GIT_INDEX_FILE 로 넘겨 스테이징 내용만 정확히
                # 검사한다. 걸리면 ②-b 와 동일하게 커밋 자체를 만들지 않고 중단.
                hook_violations = _run_hook_guards(root, index_path)
                if hook_violations:
                    result["hook_violations"] = hook_violations
                    result["reason"] = (
                        f"훅가드 위반(커밋 생성 안 함) — {hook_violations[0]}"
                        + (f" 외 {len(hook_violations) - 1}건" if len(hook_violations) > 1 else "")
                    )
                    return result

                # ③ commit-tree 직전 HEAD 재검증 — 움직였으면 통째로 재시도(스테일 트리 차단)
                head_now = _git_out(["rev-parse", "HEAD"], root)
                if head_now != head:
                    time.sleep(_RETRY_WAIT_SEC)
                    continue

                new_sha = _git_out(["commit-tree", tree, "-p", head, "-m", message], root)

                # ④ CAS — 경쟁 커밋이 끼어들었으면 update-ref 가 실패한다(원자 갱신)
                upd = _git(["update-ref", "HEAD", new_sha, head], root)
                if upd.returncode != 0:
                    time.sleep(_RETRY_WAIT_SEC)
                    continue

                result["sha"] = new_sha
                result["committed"] = True

                # ④-b 라이브 인덱스 동기화(임시 인덱스 커밋의 필수 후처리 — 위 주석 참조)
                result["index_synced"] = _sync_live_index(rel_paths, root, head, new_sha)

                # ⑤ 사후 재확인(방어적 — 선검증②-b 와 같은 트리라 정상 상황에선 항상 통과.
                # commit-tree/update-ref 가 그 사이 트리를 바꿀 수는 없으니 여기서 다시
                # 걸리는 건 이례적이지만, 걸리면 여전히 ok=False 로 push 를 막는다)
                changed = [ln for ln in _git_out(
                    ["diff-tree", "--no-commit-id", "--name-only", "-r", new_sha], root
                ).splitlines() if ln.strip()]
                result["changed"] = changed
                foreign = [c for c in changed
                           if not any(c == rp or c.startswith(rp + "/") for rp in rel_paths)]
                if not changed:
                    result["foreign"] = foreign
                    result["reason"] = "커밋에 변경 파일 0건(검증 실패)"
                elif foreign:
                    result["foreign"] = foreign
                    result["reason"] = f"무관 경로 혼입 {len(foreign)}건(사후 재확인 — 이례적)"
                else:
                    result["ok"] = True
                    result["reason"] = f"커밋 완료 {len(changed)}건"
                break
            else:
                result["reason"] = f"HEAD 경합 {max_retries}회 재시도 초과(커밋 안 함)"
    except Exception as exc:
        result["reason"] = f"{type(exc).__name__}: {exc}"
    finally:
        try:
            index_path.unlink(missing_ok=True)
        except Exception:
            pass

    # ★배10009: committed 만 보면 혼입이 감지돼(ok=False) 이미 만들어진 나쁜 커밋이
    # 그대로 push 될 수 있었다 — 검증 통과 여부(ok)를 게이트로 쓴다.
    if result["ok"] and push:
        try:
            subprocess.run(
                [sys.executable, str(_SCRIPTS_DIR / "post_commit_push.py")],
                cwd=str(root), capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=120,
            )
        except Exception as exc:  # push 실패는 커밋을 되돌리지 않는다(fail-open)
            print(f"[WARN] push 실패(커밋은 유지 — 다음 워처가 올림): {type(exc).__name__}: {exc}")
    return result


def main() -> int:
    import argparse

    p = argparse.ArgumentParser(description="스테일 트리 차단 안전 커밋(HEAD 재검증 + update-ref CAS)")
    p.add_argument("-m", "--message", required=True, help="커밋 메시지")
    p.add_argument("--holder", default="safe_commit_cli", help="락 holder 이름")
    p.add_argument("--no-push", action="store_true", help="커밋만 하고 push 하지 않음")
    p.add_argument("paths", nargs="+", help="커밋할 경로(이 목록 밖은 절대 안 담김)")
    args = p.parse_args()

    res = safe_commit(args.paths, args.message, holder=args.holder, push=not args.no_push)
    print(f"[{'OK' if res['ok'] else 'FAIL'}] {res['reason']} "
          f"(시도 {res['attempts']}회 · sha={res['sha'][:9] or '-'})")
    for c in res["changed"]:
        print(f"  + {c}")
    for f in res["foreign"]:
        print(f"  ! 혼입 {f}")
    for h in res["hook_violations"]:
        print(f"  ! 훅가드 {h}")
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
