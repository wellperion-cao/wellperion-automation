#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sync_queue_mirror.py — _queue.json 발행루트 미러 단방향 동기화 (2026-06-17)

배경:
  G1 '오늘의 항로' 렌더(wellperion_guide(main).html)는 살아있는 항로를
  `/wellperion-automation/status/_queue.json` 절대경로로 fetch 한다.
  그러나 GitHub Pages 발행 루트 = 레포의 `3. 웰페리온 가이드/` 폴더라서,
  레포루트 `status/_queue.json` 은 발행트리에 없어 라이브에서 항상 404 →
  G1 큐 전용 항로(PENDING+IN_PROGRESS) 20여 척이 전부 증발했다.

해결:
  발행루트(`3. 웰페리온 가이드/status/_queue.json`)에 원본의 사본(미러)을
  두어 라이브 200 으로 도달하게 한다. 이 스크립트는 그 미러를 원본과
  자동 동기화한다.

원칙(중요):
  - 단방향: 원본(status/_queue.json) → 미러(3. 웰페리온 가이드/status/_queue.json).
    절대 역방향(미러→원본) 금지. 미러는 복사본일 뿐, 원본으로 취급 금지.
  - 멱등: 내용이 같으면 아무 것도 하지 않음(무한 트리거 방지).
  - SSOT 무변경: 원본 데이터는 절대 건드리지 않는다(읽기만).

pre-commit 훅에서 호출되며, 미러가 갱신되면 git add 까지 수행한다.

★사고 대응(2026-07-20, 배1307 실행 중 발견 · 커밋 504b6c4f 원인)★
  이전 버전은 원본을 항상 "작업트리(디스크) 그대로" 읽었다. 공유 워크트리에서는 커밋과
  무관한 다른 세션이 status/_queue.json을 중간 편집 상태로 남겨둔 순간에 아무 커밋이나
  하나 지나가면, 그 훅이 스테일 디스크 상태를 그대로 미러에 복사해 git add 해버린다 —
  커미터가 _queue.json을 전혀 건드릴 의도가 없어도 남의 미완성 편집이 함께 커밋된다
  (실제로 8편 취소 커밋 95941ff0 때 92→30건으로 줄어든 스테일 사본이 이렇게 섞여
  들어갔다가 504b6c4f로 수동 복구됨).
  수정: require_staged=True(pre-commit 훅 전용, --pre-commit 플래그)일 때는 원본 경로가
  "이번 커밋에 실제로 staged"된 경우에만(`git diff --cached --name-only`) 동기화하고,
  디스크가 아닌 인덱스(staged blob, `git show :path`)에서 읽는다 — 그래야 동시에 떠 있는
  무관한 미완성 편집을 절대 못 줍는다. require_staged=False(기본값 — erp_status_publisher·
  gm_aide_scan 등 커밋과 무관한 명시적 드리프트 자가치유 호출)는 기존처럼 디스크를 그대로
  읽는다(그 호출들은 "지금 디스크 상태를 미러에 즉시 반영"이 의도된 동작이라 바꾸지 않음).

종료코드: 항상 0 (실패해도 커밋을 막지 않음 — fail-open).
"""

import os
import subprocess
import sys

SYNC_PAIRS = [
    ("status/_queue.json",               "3. 웰페리온 가이드/status/_queue.json"),
    ("status/_queue_archive.json",       "3. 웰페리온 가이드/status/_queue_archive.json"),
    ("status/learning_proposals.json",   "3. 웰페리온 가이드/status/learning_proposals.json"),
    # 항해 지도 (2026-07-06): 항해지도.html 이 발행루트 절대경로로 직독.
    ("status/voyage_map.json",           "3. 웰페리온 가이드/status/voyage_map.json"),
]

# 하위 호환: 기존 단일 변수 참조 코드를 위해 유지
ROOT_REL   = SYNC_PAIRS[0][0]
MIRROR_REL = SYNC_PAIRS[0][1]


def repo_root():
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        if out.returncode == 0:
            return out.stdout.decode("utf-8", "replace").strip()
    except Exception:
        pass
    return os.getcwd()


def read_bytes(path):
    try:
        with open(path, "rb") as f:
            return f.read()
    except Exception:
        return None


def is_staged(root, rel_path):
    """rel_path 가 "이번 커밋"(인덱스)에 실제로 staged 됐는지(HEAD 대비 변경 있음)."""
    try:
        out = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--", rel_path],
            cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        return bool(out.stdout.decode("utf-8", "replace").strip())
    except Exception:
        return False


def read_staged_bytes(root, rel_path):
    """인덱스(staged blob) 내용을 읽는다 — 동시에 떠 있는 작업트리 변경과 무관."""
    try:
        out = subprocess.run(
            ["git", "show", ":%s" % rel_path],
            cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        if out.returncode != 0:
            return None
        return out.stdout
    except Exception:
        return None


def sync_one(root, src_rel, dst_rel, require_staged=False):
    """
    원본 → 미러 단방향 동기화 (멱등). 갱신 시 git add 수행. 실패=통과(fail-open).
    require_staged=True면 원본이 "이번 커밋에 실제로 staged"된 경우에만 동기화하고
    인덱스(staged blob)에서 읽는다(pre-commit 훅 전용 — 무관한 작업트리 상태 혼입 방지).
    """
    dst = os.path.join(root, *dst_rel.split("/"))

    if require_staged:
        if not is_staged(root, src_rel):
            return  # 이번 커밋이 원본을 안 건드림 → 동기화 skip(무관 상태 혼입 방지)
        src_bytes = read_staged_bytes(root, src_rel)
    else:
        src = os.path.join(root, src_rel)
        src_bytes = read_bytes(src)
    if src_bytes is None:
        return  # 원본 없음 → 건너뜀

    dst_bytes = read_bytes(dst)
    if dst_bytes == src_bytes:
        return  # 이미 동일 → 멱등 no-op

    try:
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with open(dst, "wb") as f:
            f.write(src_bytes)
    except Exception as exc:
        sys.stderr.write(
            "[queue-mirror][WARN] 미러 쓰기 실패(%s) — 통과(fail-open): %r\n" % (dst_rel, exc)
        )
        return

    try:
        # cwd=root 명시(2026-07-20 배1307 실행 중 발견) — 이게 없으면 이 스크립트가 repo
        # root 밖의 다른 프로세스 cwd에서 호출될 때 git add 가 엉뚱한 워킹트리에 걸린다
        # (파일 읽기/쓰기는 root 기준인데 git 명령만 ambient cwd 기준이 되는 불일치).
        subprocess.run(["git", "add", "--", dst_rel], cwd=root,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except Exception:
        pass

    sys.stderr.write("[queue-mirror] 미러 동기화 → %s (git add 완료)\n" % dst_rel)


def main(require_staged=False):
    root = repo_root()
    for src_rel, dst_rel in SYNC_PAIRS:
        sync_one(root, src_rel, dst_rel, require_staged=require_staged)
    return 0


if __name__ == "__main__":
    # --pre-commit: pre-commit 훅 전용 호출 표시 — staged 된 원본만, 인덱스에서 읽는다
    # (무관한 작업트리 상태 혼입 방지). 플래그 없으면 기존 동작(디스크 직독, 드리프트
    # 자가치유 호출 — erp_status_publisher.py·gm_aide_scan.py) 그대로 유지.
    require_staged = "--pre-commit" in sys.argv
    try:
        sys.exit(main(require_staged=require_staged))
    except Exception as exc:
        sys.stderr.write(
            "[queue-mirror][WARN] 동기화 내부 오류 — 통과(fail-open): %r\n" % (exc,)
        )
        sys.exit(0)
