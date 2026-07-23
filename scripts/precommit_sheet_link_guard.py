# -*- coding: utf-8 -*-
"""
precommit_sheet_link_guard.py — 커밋 전 알림 문구 내 원본 시트(DB) 링크 차단 가드

배경 (2026-07-23 GM 지적 · AI CTO):
  신규 강습 문의 텔레그램 알림이 강습 시트(구글 스프레드시트) 원본 링크를
  실무진 방에 그대로 뿌리고 있었다. 원본 시트 링크가 알림에 노출되면
  ①누구나 그 링크로 직접 시트를 열어 수정·삭제할 수 있고
  ②고객 개인정보가 시트 전체째로 노출된다.
  알림에는 ERP 화면(대시보드) 링크만 나가야 한다 — 원본 DB 링크 금지.

동작:
  staged 된 *.py·*.js 파일의 diff에서 **추가된 줄**(`git diff --cached -U0`
  의 `+` 줄)만 검사한다. 기존에 이미 있던 줄은 건드리지 않는다 — 안 그러면
  대시보드 API가 화면에 내려주는 정당한 sheetUrl 같은 기존 용례까지 무더기로
  잡혀 가드가 무시당한다.

  추가된 줄에 `docs.google.com/spreadsheets` 가 있고, 그 줄(또는 파일 안에서
  앞뒤 3줄)에 알림 신호(sendMessage·_notifyTelegram·send_telegram·telegram(·
  sendPhoto·caption·chat_id·chatId·text=·'text'·"text")가 있으면 "알림 문구에
  원본 시트 링크"로 판정 → 커밋 차단(exit 1).
  알림 신호가 없으면(대시보드 응답 조립·주석·상수 정의 등) 통과.

안전 규칙 (fail-open):
  - .py/.js 가 아니면                        → 검사 제외
  - `scripts/_archive` 류 경로               → 검사 제외
    (그 외 _archive·node_modules·.deploy-* 는 검사 대상에 **포함** — .deploy-*
     아래 실제 알림 스크립트가 있어 여기서 빼면 가드 의미가 없다)
  - 가드 자신·자기 테스트                    → 검사 제외(SELF_EXEMPT_PATHS)
    (설명·픽스처 안에 이 URL 패턴을 예시로 담을 수밖에 없기 때문)
  - 줄 끝에 `sheet-link-ok:<사유>` 주석(# 또는 //)  → 통과시키고 그 사실을
    stdout 에 1줄 남김(조용한 예외 금지)
  - git 명령 실패·diff 파싱 실패              → 경고만 출력하고 통과(exit 0)
  - 가드 자체가 에러나면                      → 통과(exit 0)
  - 우회: env SKIP_SHEET_LINK_GUARD=1 → 경고 후 통과
          또는 git commit --no-verify

  ※ exit 1 = 차단(알림 문구 내 원본 시트 링크 감지). exit 0 = 통과(정상/에러/우회).
"""

import os
import re
import subprocess
import sys

# ── 검사 대상 확장자·제외 경로 ─────────────────────────────────────────────
WATCH_SUFFIXES = (".py", ".js")

# _archive·node_modules·.deploy-* 는 이 가드에서 검사 대상에 **포함**한다
# (.deploy-check/ 등에 실제 알림 코드가 있다). scripts/_archive 류만 제외.
EXCLUDE_SUBSTRINGS = ("scripts/_archive",)

# 가드 자신·자기 테스트는 검사 대상에서 제외 — 설명·픽스처에 이 URL 패턴을
# 예시로 담아야 하기 때문(erp_anchor_guard 와 동일 규약).
SELF_EXEMPT_PATHS = (
    "scripts/precommit_sheet_link_guard.py",
    "tests/test_precommit_sheet_link_guard.py",
)

SHEET_LINK_RE = re.compile(r"docs\.google\.com/spreadsheets")

NOTIFY_SIGNAL_RE = re.compile(
    r"sendMessage|_notifyTelegram|send_telegram|telegram\(|sendPhoto"
    r"|caption|chat_id|chatId|text=|'text'|\"text\""
)

EXEMPT_COMMENT_RE = re.compile(r"(?:#|//)\s*sheet-link-ok:(.*)$")

HUNK_HEADER_RE = re.compile(rb"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")

SKIP_ENV = "SKIP_SHEET_LINK_GUARD"


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


def staged_blob(path_bytes):
    """staged(인덱스) blob 바이트. 없으면 None."""
    rc, out = run(["git", "cat-file", "-p", b":" + path_bytes])
    if rc != 0:
        return None
    return out


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
    """-U0 unified diff → [(새 파일 줄번호, 내용str), ...] 추가(+)줄만."""
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


def context_window(full_lines, lineno, span=3):
    """full_lines(1-indexed 대응 리스트)에서 lineno 앞뒤 span줄 텍스트."""
    start = max(1, lineno - span)
    end = min(len(full_lines), lineno + span)
    return "\n".join(full_lines[start - 1:end])


def scan_file(disp, path_bytes):
    """(violations, exemptions) — 이 파일에서 발견된 위반·명시적 예외 목록."""
    diff = staged_diff(path_bytes)
    if not diff:
        return [], []
    added = [
        (lineno, content) for lineno, content in parse_added_lines(diff)
        if SHEET_LINK_RE.search(content)
    ]
    if not added:
        return [], []

    blob = staged_blob(path_bytes)
    full_lines = blob.decode("utf-8", "replace").splitlines() if blob else []

    violations = []
    exemptions = []
    for lineno, content in added:
        m = EXEMPT_COMMENT_RE.search(content)
        if m:
            exemptions.append((disp, lineno, m.group(1).strip()))
            continue
        window = context_window(full_lines, lineno) if full_lines else content
        if NOTIFY_SIGNAL_RE.search(window):
            violations.append((disp, lineno, content.strip()))
    return violations, exemptions


def main():
    if os.environ.get(SKIP_ENV) == "1":
        sys.stderr.write(
            "[sheet-link-guard][WARN] %s=1 — 가드 우회(통과)\n" % SKIP_ENV
        )
        return 0

    files = staged_files()
    if files is None:
        sys.stderr.write("[sheet-link-guard][WARN] git diff 실패 — 통과(fail-open)\n")
        return 0

    all_violations = []
    all_exemptions = []
    for path_bytes in files:
        try:
            disp = path_bytes.decode("utf-8", "replace")
            norm = disp.replace("\\", "/")
            if not norm.lower().endswith(WATCH_SUFFIXES):
                continue
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
            "[sheet-link-guard] 허용됨(sheet-link-ok): %s:%d — 사유: %s\n"
            % (disp, lineno, reason or "(사유 미기재)")
        )

    if all_violations:
        sys.stderr.write(
            "\n"
            "============================================================\n"
            "[sheet-link-guard] 커밋 차단 — 알림 문구에 원본 시트(DB) 링크\n"
            "------------------------------------------------------------\n"
        )
        for disp, lineno, content in all_violations:
            sys.stderr.write(
                "  - %s:%d\n"
                "      %s\n"
                % (disp, lineno, content)
            )
        sys.stderr.write(
            "------------------------------------------------------------\n"
            "  원본 스프레드시트 링크를 알림에 그대로 보내면 누구나 직접\n"
            "  수정·삭제할 수 있고 개인정보가 통째로 노출됩니다.\n"
            "  대안: ERP 화면(대시보드) 링크로 교체하세요.\n"
            "  정말 의도적이면 줄 끝에 주석 추가:  # sheet-link-ok:<사유>\n"
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
            "[sheet-link-guard][WARN] 가드 내부 오류 — 통과(fail-open): %r\n" % (exc,)
        )
        sys.exit(0)
