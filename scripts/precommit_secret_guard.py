# -*- coding: utf-8 -*-
r"""
precommit_secret_guard.py — 커밋 전 비밀값(봇 토큰·API 키 등) 평문 커밋 차단 가드

배경 (2026-07-23 시모 발견 · AI CTO 재발방지 · 배9952):
  @namuki_report_bot 텔레그램 봇 토큰이 2026-06-24부터 공개 저장소에 평문으로
  들어가 한 달 넘게 아무도 몰랐다. 사람이 조심하는 것으로는 못 막는다는 게
  증명됐다(GM 지시로 재발급 진행 중). 본 가드는 같은 종류의 비밀값이
  **다시 들어가는 것을 원천 차단**한다.

동작:
  staged 된 텍스트 파일 전부(확장자 무관)의 diff에서 **추가된 줄**만
  (`git diff --cached -U0` 의 `+` 줄) 검사한다. 기존에 이미 있던 줄은
  건드리지 않는다 — 이력에 이미 있는 것은 별도 조치 대상이며, 여기서
  무더기로 잡으면 가드가 무시당한다.

  다음 고신뢰 패턴만 차단 대상(오탐 방지 — "긴 영숫자면 무조건 차단" 같은
  규칙은 넣지 않는다):
    - 텔레그램 봇 토큰   \b\d{8,12}:[A-Za-z0-9_-]{30,}\b
    - Google API 키      \bAIza[0-9A-Za-z_\-]{35}\b
    - AWS 액세스 키      \bAKIA[0-9A-Z]{16}\b
    - Slack 토큰         \bxox[baprs]-[A-Za-z0-9-]{10,}\b
    - 개인키 헤더        -----BEGIN [A-Z ]*PRIVATE KEY-----

  위반 시 파일:줄 · 어떤 종류의 비밀값인지만 출력하고, 값 자체는 절대
  출력하지 않는다(앞 4자만 + "…" 로 마스킹).

안전 규칙 (fail-open):
  - 바이너리 파일                            → 검사 제외(diff 가 hunk 를 안 만들어 자연히 스킵)
  - scripts/_archive · node_modules 경로       → 검사 제외
  - 가드 자신·자기 테스트                    → 검사 제외(SELF_EXEMPT_PATHS)
    (패턴 정의·픽스처 안에 이 형태를 예시로 담을 수밖에 없기 때문)
  - 줄 끝에 `secret-ok:<사유>` 주석(# 또는 //) → 통과시키고 그 사실을
    stdout 에 1줄 남김(조용한 예외 금지)
  - git 명령 실패·diff 파싱 실패              → 경고만 출력하고 통과(exit 0)
  - 가드 자체가 에러나면                      → 통과(exit 0)
  - 우회: env SKIP_SECRET_GUARD=1 → 경고 후 통과
          또는 git commit --no-verify

  ※ exit 1 = 차단(비밀값 감지). exit 0 = 통과(정상/에러/우회).
"""

import os
import re
import subprocess
import sys

# _archive·node_modules 는 검사 제외.
EXCLUDE_SUBSTRINGS = ("scripts/_archive", "node_modules")

# 가드 자신·자기 테스트는 검사 대상에서 제외 — 패턴 설명·픽스처 안에 이 형태를
# 예시로 담아야 하기 때문(erp_anchor_guard·sheet_link_guard 와 동일 규약).
SELF_EXEMPT_PATHS = (
    "scripts/precommit_secret_guard.py",
    "tests/test_precommit_secret_guard.py",
)

# (사람이 읽을 이름, 패턴) — 고신뢰 패턴만. 순서대로 검사.
SECRET_PATTERNS = (
    ("텔레그램 봇 토큰", re.compile(r"\b\d{8,12}:[A-Za-z0-9_-]{30,}\b")),
    ("Google API 키", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")),
    ("AWS 액세스 키", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("Slack 토큰", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    ("개인키(PRIVATE KEY) 헤더", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
)

EXEMPT_COMMENT_RE = re.compile(r"(?:#|//)\s*secret-ok:(.*)$")

HUNK_HEADER_RE = re.compile(rb"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")

SKIP_ENV = "SKIP_SECRET_GUARD"


def run(args):
    """git 명령 실행 → (returncode, stdout_bytes)."""
    proc = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return proc.returncode, proc.stdout


def staged_files():
    """
    staged 파일 경로(bytes) 목록 — ACM(추가·복사·수정)만. -z 로 한글/공백 경로 안전.
    """
    rc, out = run([
        "git", "diff", "--cached", "--name-status", "-z", "--diff-filter=ACM",
    ])
    if rc != 0:
        return None
    tokens = out.split(b"\x00")
    paths = []
    i = 0
    while i < len(tokens):
        status = tokens[i].decode("utf-8", "replace") if tokens[i] else ""
        if not status:
            i += 1
            continue
        if i + 1 < len(tokens):
            paths.append(tokens[i + 1])
        i += 2
    return paths


def staged_diff(path_bytes):
    """staged 된 파일의 HEAD 대비 diff(-U0, 컨텍스트 없음) 바이트. 실패 시 None."""
    rc, out = run(["git", "diff", "--cached", "-U0", "--", path_bytes])
    if rc != 0:
        return None
    return out


def is_excluded(norm):
    if norm in SELF_EXEMPT_PATHS:
        return True
    return any(sub in norm for sub in EXCLUDE_SUBSTRINGS)


def parse_added_lines(diff_bytes):
    """-U0 unified diff → [(새 파일 줄번호, 내용str), ...] 추가(+)줄만.

    바이너리 파일 diff("Binary files a/... differ")는 @@ hunk 헤더가 없어
    자연히 빈 목록을 반환한다 — 별도 바이너리 판별이 필요 없다.
    """
    added = []
    new_lineno = None
    for line in diff_bytes.split(b"\n"):
        m = HUNK_HEADER_RE.match(line)
        if m:
            new_lineno = int(m.group(1))
            continue
        if new_lineno is None:
            continue
        if line.startswith(b"+++") or line.startswith(b"---"):
            continue
        if line.startswith(b"+"):
            added.append((new_lineno, line[1:].decode("utf-8", "replace")))
            new_lineno += 1
        elif line.startswith(b"-"):
            continue  # 삭제된 줄 — 새 파일 줄번호 소비 안 함
        # 그 외("\ No newline at end of file" 등)는 -U0 에서 무시
    return added


def mask(value):
    """값 원문을 절대 출력하지 않기 위한 마스킹 — 앞 4자만 + '…'."""
    return (value[:4] + "…") if value else "…"


def scan_file(disp, path_bytes):
    """(violations, exemptions) — 이 파일에서 발견된 위반·명시적 예외 목록.

    violations: (disp, lineno, 비밀값 종류, 마스킹된 값)
    exemptions: (disp, lineno, 사유)
    """
    diff = staged_diff(path_bytes)
    if not diff:
        return [], []

    violations = []
    exemptions = []
    for lineno, content in parse_added_lines(diff):
        m = EXEMPT_COMMENT_RE.search(content)
        if m:
            # 이 줄에 실제로 비밀값 패턴이 있을 때만 "허용됨" 로그를 남긴다
            # (무관한 줄 끝에 우연히 같은 주석이 붙어도 조용히 통과 — 노이즈 방지).
            if any(pat.search(content) for _name, pat in SECRET_PATTERNS):
                exemptions.append((disp, lineno, m.group(1).strip()))
            continue
        for name, pattern in SECRET_PATTERNS:
            found = pattern.search(content)
            if found:
                violations.append((disp, lineno, name, mask(found.group(0))))
                break  # 줄당 1건만 보고(같은 줄에 여러 패턴이 겹쳐도 충분)
    return violations, exemptions


def main():
    if os.environ.get(SKIP_ENV) == "1":
        sys.stderr.write(
            "[secret-guard][WARN] %s=1 — 가드 우회(통과)\n" % SKIP_ENV
        )
        return 0

    files = staged_files()
    if files is None:
        sys.stderr.write("[secret-guard][WARN] git diff 실패 — 통과(fail-open)\n")
        return 0

    all_violations = []
    all_exemptions = []
    for path_bytes in files:
        try:
            disp = path_bytes.decode("utf-8", "replace")
            norm = disp.replace("\\", "/")
            if is_excluded(norm):
                continue
            violations, exemptions = scan_file(disp, path_bytes)
            all_violations.extend(violations)
            all_exemptions.extend(exemptions)
        except Exception:
            # 개별 파일 처리 실패 → 그 파일만 건너뜀(fail-open).
            continue

    for disp, lineno, reason in all_exemptions:
        sys.stdout.write(
            "[secret-guard] 허용됨(secret-ok): %s:%d — 사유: %s\n"
            % (disp, lineno, reason or "(사유 미기재)")
        )

    if all_violations:
        sys.stderr.write(
            "\n"
            "============================================================\n"
            "[secret-guard] 커밋 차단 — 비밀값(자격증명) 평문 커밋 감지\n"
            "------------------------------------------------------------\n"
        )
        for disp, lineno, name, masked in all_violations:
            sys.stderr.write(
                "  - %s:%d\n"
                "      종류: %s (값: %s — 마스킹됨)\n"
                % (disp, lineno, name, masked)
            )
        sys.stderr.write(
            "------------------------------------------------------------\n"
            "  비밀값이 공개 저장소에 평문으로 들어가면 유출로 이어집니다\n"
            "  (2026-07-23 텔레그램 봇 토큰 한 달간 노출 사고 재발 방지 · 배9952).\n"
            "  대안: 값을 .env·시크릿 저장소로 옮기고 커밋에는 참조만 남기세요.\n"
            "  정말 의도적이면(예: 테스트 픽스처) 줄 끝에 주석 추가:\n"
            "    # secret-ok:<사유>\n"
            "  또는 우회:  git commit --no-verify   /   env %s=1\n"
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
            "[secret-guard][WARN] 가드 내부 오류 — 통과(fail-open): %r\n" % (exc,)
        )
        sys.exit(0)
