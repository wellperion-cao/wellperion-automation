#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
precommit_truncation_guard.py — 커밋 전 truncation(대량 라인 유실) 차단 가드

배경 (2026-06-13 AI CTO):
  운영부 체계.html 이 stale 사본으로 덮어써져 3394→1908 줄(약 1486줄 유실)이
  검증 없이 커밋된 사고 재발 방지. 모든 커밋 경로(clevel.bat 자동커밋 + 에이전트
  직접 git commit)를 .git/hooks/pre-commit 에서 본 스크립트를 호출해 보호한다.

동작:
  staged 된 *.html · *.js 파일에 대해, HEAD 버전 대비 라인수가
  급감(30% 이상 AND 200줄 이상 감소)하면 커밋을 중단(exit 1)하고
  어느 파일이 몇 줄 → 몇 줄인지 한글로 경고한다.

안전 규칙 (fail-open):
  - 신규 파일(HEAD에 없음)          → 통과
  - 전체 삭제(staged 에서 제거됨)    → 통과 (의도적 삭제)
  - HEAD 가 200줄 미만인 작은 파일   → 통과 (소형 파일 비율 노이즈 방지)
  - 가드 자체가 에러나면             → 통과(exit 0). 가드 버그로 전 커밋이
                                       막히면 안 됨.
  - 의도적 대량삭제 우회             → git commit --no-verify

  ※ exit 1 = 차단(truncation 감지). exit 0 = 통과(정상/에러 fail-open).
"""

import subprocess
import sys

# ── 임계값 (둘 다 충족해야 차단) ──────────────────────────────────────────
SHRINK_RATIO = 0.30      # 30% 이상 감소
SHRINK_LINES = 200       # AND 200줄 이상 감소
MIN_HEAD_LINES = 200     # HEAD 가 이보다 작으면 비율 판정 스킵(소형파일 노이즈)
WATCH_SUFFIXES = (".html", ".js")


def run(args):
    """git 명령 실행 → (returncode, stdout_bytes)."""
    proc = subprocess.run(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return proc.returncode, proc.stdout


def count_lines(blob_bytes):
    """blob 바이트의 라인 수. 빈 내용=0."""
    if not blob_bytes:
        return 0
    # 마지막 줄에 개행이 없어도 1줄로 카운트되도록 splitlines 사용.
    return len(blob_bytes.splitlines())


def staged_files():
    """
    staged 파일 목록을 (status, path) 로 반환.
    -z 로 NUL 구분 → 한글/공백 경로 안전. 이름변경(R)은 새 경로만.
    """
    rc, out = run([
        "git", "diff", "--cached", "--name-status", "-z",
        "--diff-filter=ACMRT",
    ])
    if rc != 0:
        return []
    tokens = out.split(b"\x00")
    files = []
    i = 0
    while i < len(tokens):
        status = tokens[i].decode("utf-8", "replace") if tokens[i] else ""
        if not status:
            i += 1
            continue
        code = status[0]
        if code == "R":
            # R<score>\told\tnew  → -z 에서는 status, old, new 가 분리 토큰
            # tokens[i]=Rxxx, tokens[i+1]=old, tokens[i+2]=new
            if i + 2 < len(tokens):
                path = tokens[i + 2]
                files.append((code, path))
            i += 3
        else:
            if i + 1 < len(tokens):
                path = tokens[i + 1]
                files.append((code, path))
            i += 2
    return files


def head_blob(path_bytes):
    """HEAD:<path> blob 바이트. 없으면 None."""
    # path 를 그대로 인자로 전달하기 위해 bytes 경로 사용.
    rc, out = run(["git", "cat-file", "-p", b"HEAD:" + path_bytes])
    if rc != 0:
        return None
    return out


def staged_blob(path_bytes):
    """staged(인덱스) blob 바이트. 없으면 None."""
    rc, out = run(["git", "cat-file", "-p", b":" + path_bytes])
    if rc != 0:
        return None
    return out


def main():
    files = staged_files()
    violations = []

    for code, path_bytes in files:
        try:
            disp = path_bytes.decode("utf-8", "replace")
            low = disp.lower()
            if not low.endswith(WATCH_SUFFIXES):
                continue

            # 신규 파일(HEAD에 없음) → 통과
            head = head_blob(path_bytes)
            if head is None:
                continue

            new = staged_blob(path_bytes)
            # 전체 삭제(인덱스에 없음) → 통과(의도적)
            if new is None:
                continue

            head_lines = count_lines(head)
            new_lines = count_lines(new)

            # 소형 파일 → 비율 노이즈 방지, 스킵
            if head_lines < MIN_HEAD_LINES:
                continue

            dropped = head_lines - new_lines
            if dropped <= 0:
                continue  # 증가/동일 → OK

            ratio = dropped / head_lines
            if ratio >= SHRINK_RATIO and dropped >= SHRINK_LINES:
                violations.append((disp, head_lines, new_lines, dropped, ratio))
        except Exception:
            # 개별 파일 처리 실패 → 그 파일만 건너뜀(fail-open).
            continue

    if violations:
        sys.stderr.write(
            "\n"
            "============================================================\n"
            "[truncation-guard] 커밋 차단 — 대량 라인 유실 감지\n"
            "------------------------------------------------------------\n"
        )
        for disp, hl, nl, dr, ratio in violations:
            sys.stderr.write(
                "  - %s\n"
                "      %d줄 → %d줄  (%d줄 / %.0f%% 감소)\n"
                % (disp, hl, nl, dr, ratio * 100)
            )
        sys.stderr.write(
            "------------------------------------------------------------\n"
            "  stale 사본 덮어쓰기로 인한 유실일 수 있습니다. 확인하세요.\n"
            "  의도적 대량 삭제라면 우회:  git commit --no-verify\n"
            "============================================================\n"
        )
        return 1

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        # 가드 자체 오류 → fail-open(커밋 통과). 진단 메시지만 출력.
        sys.stderr.write(
            "[truncation-guard][WARN] 가드 내부 오류 — 통과(fail-open): %r\n" % (exc,)
        )
        sys.exit(0)
