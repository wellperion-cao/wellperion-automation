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

── chro/cfo 보호 삭제 판정 (2026-08-04 시토 · 인사 지원자 사진 반복삭제 사고) ──
  배경: COO·CPO 도메인 커밋(welly_auto_runner 디스패치, 배 425cbb58a·31841eec1)이
  chro/hub/photos 지원자 사진 삭제를 자기 업무와 전혀 무관하게 쓸어담았다(runner
  자체 로그 status/welly_auto_runner_log.jsonl live_run 이벤트로 확정 — 공유 라이브
  인덱스로 맨손 git commit 했을 때 다른 세션이 남긴 미커밋 삭제까지 같이 실렸다).
  두 사고 모두 파일이 디스크에도 실제로 없어(진짜 삭제) 위 유령 삭제 판정을
  피해 간다 — "디스크 존재 여부"가 아니라 "이 삭제가 커밋의 나머지 변경과 같은
  도메인이냐"로 갈라야 잡힌다.

  판정: 이번 커밋이 chro/·cfo/ 경로를 하나라도 삭제(D)로 담고 있는데, 같은 커밋에
  chro/·cfo/ 밖의 경로도 섞여 있으면 차단한다. 커밋 전체가 chro/·cfo/ 안에서만
  이뤄지면(=그 도메인 전용 도구·세션) 통과 — 인사·재무 담당(나우열M)의 정상
  삭제까지 막지 않는다.
  우회: env SKIP_PHANTOM_DELETE_GUARD=1 또는 git commit --no-verify(위와 동일 스위치
  재사용 — 새 환경변수 안 만듦).
"""

import os
import subprocess
import sys

SKIP_ENV = "SKIP_PHANTOM_DELETE_GUARD"
MAX_LISTED = 20

PROTECTED_DELETE_PREFIXES = (
    "3. 웰페리온 가이드/chro/",
    "3. 웰페리온 가이드/cfo/",
)


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


def staged_all():
    """스테이징된 전체 경로(상태 무관, bytes) 목록. git 실패 시 None(fail-open 신호)."""
    rc, out = run(["git", "diff", "--cached", "--name-only", "-z"])
    if rc != 0:
        return None
    return [t for t in out.split(b"\x00") if t]


def _is_protected(path: str) -> bool:
    return any(path.startswith(p) for p in PROTECTED_DELETE_PREFIXES)


def _decode(path_bytes):
    try:
        return path_bytes.decode("utf-8", "replace")
    except Exception:
        return None


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

    # ── chro/cfo 보호 삭제 판정 ──
    protected_deletes = [d for p in deleted if (d := _decode(p)) and _is_protected(d)]
    if protected_deletes:
        all_staged = staged_all()
        if all_staged is not None:
            all_paths = [d for p in all_staged if (d := _decode(p))]
            mixed_domain = any(not _is_protected(p) for p in all_paths)
            if mixed_domain:
                sys.stderr.write(
                    "\n"
                    "============================================================\n"
                    "[phantom-delete-guard] 커밋 차단 — chro/cfo 보호 삭제 혼입\n"
                    "------------------------------------------------------------\n"
                )
                for path in protected_deletes[:MAX_LISTED]:
                    sys.stderr.write("  - %s\n" % path)
                sys.stderr.write(
                    "------------------------------------------------------------\n"
                    "  이 커밋은 chro/cfo(인사·재무) 파일 삭제와 그 밖의 무관한 변경을\n"
                    "  함께 담고 있습니다. chro/cfo 경로 삭제는 그 도메인 전용 커밋\n"
                    "  (chro/cfo 안에서만 이뤄지는 커밋)에서만 허용됩니다 — 다른 업무\n"
                    "  커밋이 공유 인덱스를 통해 지원자 사진 등을 쓸어담는 사고를\n"
                    "  막기 위함(2026-08-04 재발).\n"
                    "  해법: chro/cfo 경로를 이번 커밋에서 빼고(git reset -- <경로>)\n"
                    "  나머지만 커밋하세요. 정말 의도한 삭제면 우회:\n"
                    "  git commit --no-verify 또는 env %s=1\n"
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
