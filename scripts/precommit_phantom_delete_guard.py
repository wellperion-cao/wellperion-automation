# -*- coding: utf-8 -*-
"""
precommit_phantom_delete_guard.py — 커밋 전 "유령 삭제"(작업트리엔 멀쩡한 파일이
삭제로 staged) 차단 가드

배경 (2026-07-23 하루 두 번 터진 사고 · 배9961):
  ①커밋 b7d4f3817: 임시 인덱스 절차에서 read-tree 가 실패했는데 오류를 삼켜
    **빈 인덱스**로 커밋됐다 → HEAD 트리에 파일 2개만 남고 3,156개가 삭제로
    기록됨(INC-029, 복구 d591c95f8).
  ②같은 날 저녁 시포 발견: 공용 인덱스에 옛 스냅샷이 물려 있어, 그대로
    커밋됐다면 그날 만든 봇 토큰 재발방지 가드 등 7개 파일이 삭제될 뻔했다.

  두 사고의 공통 지문: 삭제로 staged 된 파일이 **작업트리(디스크)에는
  멀쩡히 존재**한다. 진짜 삭제라면 디스크에도 없다. 이 한 가지만 보면 둘 다
  잡힌다 — 스테일 인덱스·빈 인덱스·잘못된 read-tree 등 원인이 무엇이든
  결과(디스크엔 있는데 삭제로 staged)는 항상 같다.

동작:
  `git diff --cached --name-only --diff-filter=D -z` 로 삭제로 staged 된
  경로를 모두 얻는다(-z 로 한글·공백 경로 안전). 각 경로가 작업트리에
  실제로 존재하면(파일이든 디렉터리 심볼릭이든) 유령 삭제로 판정 →
  커밋 차단(exit 1). 작업트리에도 없으면(진짜 삭제) 통과.

안전 규칙 (fail-open):
  - 삭제로 staged 된 파일이 0건                → 통과
  - git 명령 실패·파싱 실패                    → 경고만 출력하고 통과(exit 0)
  - 가드 자체가 에러나면                      → 통과(exit 0)
  - 우회: env SKIP_PHANTOM_DELETE_GUARD=1 → 경고 후 통과
          또는 git commit --no-verify

  ※ exit 1 = 차단(유령 삭제 감지). exit 0 = 통과(정상/진짜 삭제/에러/우회).
"""

import os
import subprocess
import sys

SKIP_ENV = "SKIP_PHANTOM_DELETE_GUARD"
MAX_LISTED = 20


def run(args):
    """git 명령 실행 → (returncode, stdout_bytes)."""
    proc = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return proc.returncode, proc.stdout


def staged_deletions():
    """
    삭제로 staged 된 경로(bytes) 목록. -z 로 한글/공백 경로 안전.
    git 실패 시 None(fail-open 신호).
    """
    rc, out = run([
        "git", "diff", "--cached", "--name-only", "-z", "--diff-filter=D",
    ])
    if rc != 0:
        return None
    tokens = [t for t in out.split(b"\x00") if t]
    return tokens


def main():
    if os.environ.get(SKIP_ENV) == "1":
        sys.stderr.write(
            "[phantom-delete-guard][WARN] %s=1 — 가드 우회(통과)\n" % SKIP_ENV
        )
        return 0

    deleted = staged_deletions()
    if deleted is None:
        sys.stderr.write("[phantom-delete-guard][WARN] git diff 실패 — 통과(fail-open)\n")
        return 0

    if not deleted:
        return 0

    violations = []
    for path_bytes in deleted:
        try:
            disp = path_bytes.decode("utf-8", "replace")
            if os.path.exists(disp):
                violations.append(disp)
        except Exception:
            # 개별 경로 처리 실패 → 그 경로만 건너뜀(fail-open).
            continue

    if violations:
        sys.stderr.write(
            "\n"
            "============================================================\n"
            "[phantom-delete-guard] 커밋 차단 — 유령 삭제 감지"
            "(작업트리엔 있는데 삭제로 staged)\n"
            "------------------------------------------------------------\n"
        )
        shown = violations[:MAX_LISTED]
        for path in shown:
            sys.stderr.write("  - %s\n" % path)
        remainder = len(violations) - len(shown)
        if remainder > 0:
            sys.stderr.write("  ... 외 %d건\n" % remainder)
        sys.stderr.write(
            "------------------------------------------------------------\n"
            "  위 파일들은 디스크에 멀쩡히 있는데 이번 커밋에는 '삭제'로\n"
            "  올라가 있습니다. 진짜 삭제라면 디스크에도 없어야 합니다.\n"
            "  원인 후보: 공용 인덱스에 옛 스냅샷이 물렸거나, 임시 인덱스\n"
            "  절차(read-tree 등)가 실패해 빈/스테일 인덱스로 커밋되는 중.\n"
            "  해법: git reset (mixed, --hard 금지) 으로 인덱스를 HEAD 와\n"
            "  맞춘 뒤 필요한 경로만 다시 add 해서 재커밋하세요.\n"
            "  정말 의도한 삭제면 우회:  git commit --no-verify\n"
            "  또는 env %s=1\n"
            "============================================================\n"
            % SKIP_ENV
        )
        return 1

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        sys.stderr.write(
            "[phantom-delete-guard][WARN] 가드 내부 오류 — 통과(fail-open): %r\n" % (exc,)
        )
        sys.exit(0)
