#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""precommit_skip_open_office.py — 커밋 직전, GM이 '열어둬서 잠긴' 작업문서를
스테이징에서 빼(unstage) 이번 커밋에서 건너뛴다. 파일을 닫으면 다음 커밋 주기에
정상 백업된다. (2026-06-22 웰리 · 잠긴 바이너리 자동push 사고 근본차단)

배경:
  이 폴더는 '로봇 자동백업(git)' + 'GM 라이브 편집(PowerPoint·PDF 등)' 을 겸한다.
  GM이 .pptx 를 열면 OS가 파일을 잠근다 → 로봇이 rebase/reset 중 그 파일을
  지우려다 'Invalid argument' 로 죽고, 자동push 가 5분마다 반복 실패·알림.
  열린 파일을 애초에 커밋·스테이징에서 빼면 충돌 자체가 안 생긴다.
  관련 기억: reference_autopush_fails_on_locked_binary.

동작:
  - staged 파일 중 '잠긴(다른 프로세스가 연)' 작업문서를 git restore --staged 로 제외.
  - 대상 확장자(작업문서)만: 코드·텍스트는 건드리지 않아 실수로 변경이 누락되지 않게.
  - 잠금 판정: ① 오피스 사이드카(~$name) 존재  ② 자기참조 rename 실패(Windows 잠금).
  - exit 0 항상(커밋 절대 안 막음). 어떤 오류든 fail-open(아무것도 안 함).
"""
from __future__ import annotations

import os
import subprocess
import sys

# 잠겨 있으면 '이번엔 건너뛸' 작업문서 확장자(소문자). 코드/텍스트는 제외(실수 누락 방지).
DOC_EXTS = {
    ".pptx", ".ppt", ".docx", ".doc", ".xlsx", ".xls", ".xlsm",
    ".pdf", ".hwp", ".hwpx", ".key", ".numbers", ".pages",
    ".psd", ".ai", ".indd", ".zip",
}


def _staged_files(root: str) -> list[str]:
    r = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "-z"],
        cwd=root, capture_output=True, text=True, timeout=20,
    )
    if r.returncode != 0:
        return []
    return [p for p in (r.stdout or "").split("\0") if p]


def _is_locked(abspath: str) -> bool:
    """다른 프로세스가 파일을 열어 잠갔는지(Windows 기준). 안전: 판단 불가 시 False."""
    try:
        if not os.path.isfile(abspath):
            return False  # 삭제 스테이징 등 — 잠금 아님
        d, n = os.path.split(abspath)
        # ① 오피스 사이드카 락(~$파일명) — Word/Excel/PowerPoint 가 열면 생성
        if n and os.path.exists(os.path.join(d, "~$" + n)):
            return True
        # ② 자기참조 rename — 열려 잠긴 파일은 Windows 에서 실패(PermissionError)
        os.rename(abspath, abspath)
        return False
    except OSError:
        return True
    except Exception:
        return False


def main() -> int:
    try:
        root = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=10,
        ).stdout.strip()
        if not root:
            return 0
        skipped = []
        for rel in _staged_files(root):
            ext = os.path.splitext(rel)[1].lower()
            if ext not in DOC_EXTS:
                continue
            if _is_locked(os.path.join(root, rel)):
                u = subprocess.run(
                    ["git", "restore", "--staged", "--", rel],
                    cwd=root, capture_output=True, text=True, timeout=20,
                )
                if u.returncode != 0:
                    # restore 미지원 환경 폴백
                    subprocess.run(
                        ["git", "reset", "-q", "HEAD", "--", rel],
                        cwd=root, capture_output=True, text=True, timeout=20,
                    )
                skipped.append(rel)
        if skipped:
            print("[skip-open-office] 열려서 잠긴 파일은 이번 커밋에서 건너뜀(닫으면 다음에 백업):")
            for s in skipped:
                print(f"  · {os.path.basename(s)}")
    except Exception:
        # fail-open: 가드 버그로 커밋이 막히면 안 된다.
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
