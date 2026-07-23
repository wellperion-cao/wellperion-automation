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
#   3) commit-tree 직전 HEAD 재검증 — 트리 읽은 뒤 HEAD 가 움직였으면 폐기하고 재시도.
#   4) `git update-ref HEAD <new> <old>` CAS 로 원자 갱신 — 경쟁 커밋이 끼어들면
#      update-ref 자체가 실패하고 재시도(락만으로는 못 막는 틈을 git 이 막아준다).
#   5) 커밋 후 실제로 내 경로가 커밋에 들어갔는지 + 무관 경로 혼입이 없는지 검증.
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
        ["git", "-C", str(root), *args],
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
              "changed": [], "foreign": [], "index_synced": [], "reason": ""}
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

                head_tree = _git_out(["rev-parse", "HEAD^{tree}"], root)
                if tree == head_tree:
                    result["ok"] = True
                    result["reason"] = "변경 없음(nothing to commit)"
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

                # ⑤ 사후 검증 — 내 경로가 실제로 들어갔는가 + 무관 경로 혼입 0인가
                changed = [ln for ln in _git_out(
                    ["diff-tree", "--no-commit-id", "--name-only", "-r", new_sha], root
                ).splitlines() if ln.strip()]
                result["changed"] = changed
                foreign = [c for c in changed
                           if not any(c == rp or c.startswith(rp + "/") for rp in rel_paths)]
                result["foreign"] = foreign
                if not changed:
                    result["reason"] = "커밋에 변경 파일 0건(검증 실패)"
                elif foreign:
                    result["reason"] = f"무관 경로 혼입 {len(foreign)}건(검증 실패)"
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

    if result["committed"] and push:
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
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
