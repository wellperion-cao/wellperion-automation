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

종료코드: 항상 0 (실패해도 커밋을 막지 않음 — fail-open).
"""

import os
import subprocess
import sys

SYNC_PAIRS = [
    ("status/_queue.json",               "3. 웰페리온 가이드/status/_queue.json"),
    ("status/_queue_archive.json",       "3. 웰페리온 가이드/status/_queue_archive.json"),
    ("status/learning_proposals.json",   "3. 웰페리온 가이드/status/learning_proposals.json"),
    # 북극성 추천기 2단계 (CTO 2026-06-29): northstar_today.html 이 발행루트 상대경로로 직독.
    ("status/northstar_pending.json",    "3. 웰페리온 가이드/status/northstar_pending.json"),
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


def sync_one(root, src_rel, dst_rel):
    """원본 → 미러 단방향 동기화 (멱등). 갱신 시 git add 수행. 실패=통과(fail-open)."""
    src = os.path.join(root, src_rel)
    dst = os.path.join(root, *dst_rel.split("/"))

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
        subprocess.run(["git", "add", "--", dst_rel],
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except Exception:
        pass

    sys.stderr.write("[queue-mirror] 미러 동기화 → %s (git add 완료)\n" % dst_rel)


def main():
    root = repo_root()
    for src_rel, dst_rel in SYNC_PAIRS:
        sync_one(root, src_rel, dst_rel)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        sys.stderr.write(
            "[queue-mirror][WARN] 동기화 내부 오류 — 통과(fail-open): %r\n" % (exc,)
        )
        sys.exit(0)
