# -*- coding: utf-8 -*-
"""queue_archive_sweep.py — _queue.json 비대화 방지 아카이브 스윕 (2026-06-24 시토).

배경:
  status/_queue.json 이 DONE/완료/폐기 '입항' 배가 누적되며 비대해진다(372KB).
  G1 '오늘의 항로' 렌더(wellperion_guide(main).html · gm1FetchSsot)는 이 파일을
  fetch 해 active(PENDING/IN_PROGRESS) + terminal(DONE/완료/폐기) 둘 다 처리한다.
  terminal 은 '오늘 입항(🏁)' / '지난 입항(🗄️)' / '검색(폐기)' 표시에만 쓰인다.

해결(G1 손상 0 원칙):
  - active_keep = PENDING/IN_PROGRESS + terminal 중 오늘(KST) 입항분(processed_at[:10]==오늘).
    → G1 '오늘 입항' 칸 보존.
  - to_archive = 나머지 지난 terminal(processed_at 없는 terminal 포함 — G1 에선 이미 '지난').
    → status/_queue_archive.json 에 task_id dedup 병합(append). G1 은 archive 도 함께 fetch.
  - _queue.json 은 active_keep 만 남겨 다시 쓴다 → active 큐 ~30KB.

원칙:
  - 멱등: 옮길 게 0건이면 두 파일 모두 안 건드리고 no-op 종료(무한 트리거 방지).
  - fail-open: 모든 예외 → stderr 경고 + exit 0. 절대 파일 손상 금지(쓰기 전 검증 후에만 덮어쓰기).
  - 무손실: total(전) == active(후) + archive(후, 신규분). task_id 손실 0.
  - 포맷: json.dump(ensure_ascii=False, indent=2) + 끝 개행 1줄 (merge 드라이버 출력과 바이트 호환).
  - 커밋 금지: 두 파일 쓰기 + git add 까지만(커밋·푸시는 watcher/post_commit_push 흐름이 처리).
    GitLock 임계구역 안에서 파일 쓰기(post_commit_push 동일 패턴).

종료코드: 항상 0 (fail-open).
"""
import json
import os
import subprocess
import sys
from datetime import datetime

# git_lock 직독 (post_commit_push.py 동일 패턴). 실패=fail-open.
try:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from git_lock import GitLock, _repo_root  # type: ignore
except Exception:
    GitLock = None
    _repo_root = None

QUEUE_REL   = "status/_queue.json"
ARCHIVE_REL = "status/_queue_archive.json"

TERMINAL_STATUSES = ("DONE", "완료", "폐기")


def _root():
    if _repo_root is not None:
        try:
            return _repo_root()
        except Exception:
            pass
    return os.getcwd()


def _rank(item):
    """더 '최종' 상태일수록 높은 점수 — git_merge_queue._rank 와 동일."""
    if not isinstance(item, dict):
        return 0
    if item.get("terminal") is True:
        return 3
    st = str(item.get("status") or "")
    if st in ("DONE", "폐기"):
        return 2
    return 1


def _is_terminal(item):
    return isinstance(item, dict) and str(item.get("status") or "") in TERMINAL_STATUSES


def _processed_day(item):
    return str(item.get("processed_at") or "")[:10] if isinstance(item, dict) else ""


def _dump_atomic(path, data):
    """포맷 동일(ensure_ascii=False · indent=2 · 끝 개행 1줄). 임시파일 검증 후 교체."""
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    # 쓰기 검증 — 파싱 성공 + 리스트 확인 후에만 본 파일 덮어쓰기
    with open(tmp, encoding="utf-8") as f:
        chk = json.load(f)
    if not isinstance(chk, list):
        raise ValueError("검증 실패: 결과가 list 아님")
    os.replace(tmp, path)


def _git_add(root, rels):
    try:
        subprocess.run(["git", "add", "--"] + list(rels),
                       cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except Exception:
        pass


def _sweep():
    root = _root()
    qpath = os.path.join(root, *QUEUE_REL.split("/"))
    apath = os.path.join(root, *ARCHIVE_REL.split("/"))

    with open(qpath, encoding="utf-8") as f:
        queue = json.load(f)
    if not isinstance(queue, list):
        raise ValueError("_queue.json 이 list 아님")

    today = datetime.now().strftime("%Y-%m-%d")

    active_keep = []
    to_archive = []
    for it in queue:
        if not _is_terminal(it):
            active_keep.append(it)            # PENDING / IN_PROGRESS / 기타
            continue
        if _processed_day(it) == today:
            active_keep.append(it)            # 오늘 입항 — G1 '오늘' 칸 보존
        else:
            to_archive.append(it)             # 지난 terminal (processed_at 없는 것 포함)

    if not to_archive:
        sys.stderr.write("[queue-sweep] no-op (옮길 지난 입항 0건)\n")
        return

    # 기존 archive 로드 (없으면 [])
    archive = []
    if os.path.exists(apath):
        try:
            with open(apath, encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, list):
                archive = loaded
        except Exception:
            archive = []

    # task_id dedup 병합 — git_merge_queue 규칙(terminal/DONE/폐기 우선). 신규는 뒤에 append.
    merged = []
    seen = {}  # task_id → merged 인덱스
    for it in archive:
        k = it.get("task_id") if isinstance(it, dict) else None
        if k is None:
            merged.append(it)
            continue
        seen[k] = len(merged)
        merged.append(it)
    for it in to_archive:
        k = it.get("task_id") if isinstance(it, dict) else None
        if k is None:
            merged.append(it)
            continue
        if k in seen:
            cur = merged[seen[k]]
            if _rank(it) > _rank(cur):
                merged[seen[k]] = it
        else:
            seen[k] = len(merged)
            merged.append(it)

    # 쓰기 — archive 먼저(데이터 보존 우선), 그다음 active 축소
    _dump_atomic(apath, merged)
    _dump_atomic(qpath, active_keep)

    _git_add(root, [QUEUE_REL, ARCHIVE_REL])
    sys.stderr.write(
        "[queue-sweep] %d 척 아카이브 이동 (active=%d, archive=%d) — git add 완료\n"
        % (len(to_archive), len(active_keep), len(merged))
    )


def main():
    root = _root()
    # GitLock 임계구역 안에서 파일 쓰기 (post_commit_push 동일 패턴). lock 미가용=직접 실행(fail-open).
    if GitLock is not None:
        try:
            import git_lock as _gl  # type: ignore
            lock = GitLock("queue-archive-sweep", root)
            try:
                _gl.ACQUIRE_TIMEOUT = 60
            except Exception:
                pass
            try:
                with lock:
                    _sweep()
                return 0
            except _gl.GitLockTimeout:
                sys.stderr.write("[queue-sweep][WARN] lock busy — 다음 주기 재시도\n")
                return 0
        except Exception:
            pass
    _sweep()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        sys.stderr.write("[queue-sweep][WARN] 내부 오류 — 통과(fail-open): %r\n" % (exc,))
        sys.exit(0)
