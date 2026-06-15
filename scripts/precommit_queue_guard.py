#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
precommit_queue_guard.py — 커밋 전 status 배열 JSON 급감(스테일 덮어쓰기) 차단 가드

배경 (2026-06-15 AI CTO):
  cmo 세션이 스테일 33척 _queue 기반으로 커밋(ecfa0f0f)해 최신 59척을 덮어써
  26척이 유실된 사고 재발 방지. truncation 가드(html/js)와 같은 원리로,
  배열형 status JSON(_queue.json·review_queue.json)의 항목 수가 HEAD 대비
  급감하면 커밋을 차단한다. 모든 커밋 경로(clevel.bat·에이전트·세션)에서
  .git/hooks/pre-commit 이 호출.

동작:
  staged 된 감시 대상 JSON(파일명 매칭)에 대해, HEAD 의 top-level 배열 길이 대비
  staged 길이가 급감(8개 이상 AND 15% 이상 감소)하면 커밋 중단(exit 1).

안전 규칙 (fail-open):
  - 신규 파일(HEAD에 없음)            → 통과
  - 전체 삭제(staged 에서 제거됨)      → 통과(의도적)
  - JSON 파싱 실패 / top-level 비배열  → 통과(이 가드 범위 아님)
  - HEAD 배열이 작음(MIN_HEAD 미만)    → 통과(노이즈 방지)
  - 가드 자체 오류                     → 통과(exit 0)
  - 의도적 대량 축소(아카이브 등) 우회 → git commit --no-verify

  ※ exit 1 = 차단(급감 감지). exit 0 = 통과(정상/에러 fail-open).
"""

import json
import subprocess
import sys

# ── 임계값 (둘 다 충족해야 차단) ──────────────────────────────────────────
SHRINK_COUNT = 8         # 8개 이상 감소
SHRINK_RATIO = 0.15      # AND 15% 이상 감소
MIN_HEAD_ITEMS = 12      # HEAD 배열이 이보다 작으면 판정 스킵(노이즈)
# 파일명(basename) 매칭 — 한글 경로 안전.
WATCH_BASENAMES = ("_queue.json", "review_queue.json")


def run(args):
    proc = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return proc.returncode, proc.stdout


def staged_paths():
    """staged 파일 경로(bytes) 목록 — 이름변경은 새 경로만. -z 로 한글 안전."""
    rc, out = run([
        "git", "diff", "--cached", "--name-status", "-z", "--diff-filter=ACMRT",
    ])
    if rc != 0:
        return []
    tokens = out.split(b"\x00")
    paths = []
    i = 0
    while i < len(tokens):
        status = tokens[i].decode("utf-8", "replace") if tokens[i] else ""
        if not status:
            i += 1
            continue
        if status[0] == "R":
            if i + 2 < len(tokens):
                paths.append(tokens[i + 2])
            i += 3
        else:
            if i + 1 < len(tokens):
                paths.append(tokens[i + 1])
            i += 2
    return paths


def blob(ref_prefix, path_bytes):
    rc, out = run(["git", "cat-file", "-p", ref_prefix + path_bytes])
    if rc != 0:
        return None
    return out


def array_len(blob_bytes):
    """JSON top-level 배열 길이. 배열 아니면 None(가드 범위 밖)."""
    if not blob_bytes:
        return None
    data = json.loads(blob_bytes.decode("utf-8", "replace"))
    if isinstance(data, list):
        return len(data)
    return None


def main():
    violations = []
    for path_bytes in staged_paths():
        try:
            disp = path_bytes.decode("utf-8", "replace")
            base = disp.replace("\\", "/").rsplit("/", 1)[-1]
            if base not in WATCH_BASENAMES:
                continue

            head = blob(b"HEAD:", path_bytes)
            if head is None:
                continue  # 신규 파일 → 통과
            new = blob(b":", path_bytes)
            if new is None:
                continue  # 전체 삭제 → 통과

            head_n = array_len(head)
            new_n = array_len(new)
            if head_n is None or new_n is None:
                continue  # 비배열/파싱불가 → 통과
            if head_n < MIN_HEAD_ITEMS:
                continue

            dropped = head_n - new_n
            if dropped <= 0:
                continue
            ratio = dropped / head_n
            if dropped >= SHRINK_COUNT and ratio >= SHRINK_RATIO:
                violations.append((disp, head_n, new_n, dropped, ratio))
        except Exception:
            continue  # 개별 파일 실패 → 그 파일만 건너뜀(fail-open)

    if violations:
        sys.stderr.write(
            "\n"
            "============================================================\n"
            "[queue-guard] 커밋 차단 — status 배열 급감(스테일 덮어쓰기 의심)\n"
            "------------------------------------------------------------\n"
        )
        for disp, hn, nn, dr, ratio in violations:
            sys.stderr.write(
                "  - %s\n"
                "      %d개 → %d개  (%d개 / %.0f%% 감소)\n"
                % (disp, hn, nn, dr, ratio * 100)
            )
        sys.stderr.write(
            "------------------------------------------------------------\n"
            "  옛 사본으로 최신 항목을 덮어쓴 것일 수 있습니다(2026-06-15 _queue 26척 유실 사고).\n"
            "  먼저 git pull --rebase 로 최신을 합쳤는지 확인하세요.\n"
            "  의도적 대량 축소(아카이브 등)라면 우회:  git commit --no-verify\n"
            "============================================================\n"
        )
        return 1
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        sys.stderr.write(
            "[queue-guard][WARN] 가드 내부 오류 — 통과(fail-open): %r\n" % (exc,)
        )
        sys.exit(0)
