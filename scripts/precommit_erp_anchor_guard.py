# -*- coding: utf-8 -*-
"""
precommit_erp_anchor_guard.py — 커밋 전 죽은 ERP 문서 앵커 참조 차단 가드

배경 (2026-07-23 AI CTO):
  2026-07-03 마케팅 문서 리넘버(M5→M1) 때 텔레그램 알림 스크립트 3곳의
  하드코딩 주소 `wellperion_guide(main).html#M5` 가 같이 안 바뀌어, 20일간
  GM께 존재하지 않는 문서(M5)를 안내했다. 가이드 HTML의 레거시 리다이렉트
  (M_LEGACY)가 조용히 받아줘서 아무도 몰랐다. 문자열 수리는 커밋 d889f28e로
  끝났고, 본 가드는 같은 일이 다시는 커밋되지 못하게 막는다.

동작:
  staged 된 *.py·*.js·*.md 파일에서 `wellperion_guide(main).html#<ID>` 형태의
  ERP 문서 앵커 참조를 찾는다. `3. 웰페리온 가이드/wellperion_guide(main).html`
  안의 id="..."·data-id="..."·data-doc="..." 값 전체를 정본 앵커 집합으로 삼아,
  참조된 ID 가 그 집합에 없으면(레거시 M_LEGACY 구주소 포함) 커밋을 차단(exit 1)
  하고 파일:줄·잘못된 ID·현존 앵커 후보를 한글로 출력한다.

안전 규칙 (fail-open):
  - .py/.js/.md 가 아니거나 _archive·node_modules·.deploy-·instagram/ 경로  → 검사 제외
  - 가이드 HTML 파일 자신이 staged 여도 그 파일은 검사 대상에서 제외(자기 참조 오탐 방지)
  - 참조가 하나도 없으면                    → 가이드 파일을 읽지 않고 통과
  - 가이드 HTML 이 없거나·읽기 실패          → 경고만 출력하고 통과(exit 0)
  - git 명령 실패                          → 경고만 출력하고 통과(exit 0)
  - 가드 자체가 에러나면                    → 통과(exit 0). 가드 버그로 전 커밋이
                                              막히면 안 됨.
  - 우회: env SKIP_ERP_ANCHOR_GUARD=1 → 경고 후 통과
          또는 git commit --no-verify

  ※ exit 1 = 차단(죽은 앵커 감지). exit 0 = 통과(정상/에러/우회 fail-open).
"""

import os
import re
import subprocess
import sys

# ── 검사 대상 확장자·제외 경로 ─────────────────────────────────────────────
WATCH_SUFFIXES = (".py", ".js", ".md")
EXCLUDE_SUBSTRINGS = ("_archive", "node_modules", ".deploy-", "instagram/")

# 가드 자신·자기 테스트는 검사 대상에서 제외한다(source 자기허용 규약 — divergence_scan 과 동일).
# 이유: 이 파일들은 "무엇이 잘못된 주소인가"를 설명·시험하려고 죽은 앵커(#M5)를 본문에
# 예시·픽스처로 담을 수밖에 없다. 제외하지 않으면 가드가 자기 자신을 차단한다(실제 발생).
SELF_EXEMPT_PATHS = (
    "scripts/precommit_erp_anchor_guard.py",
    "tests/test_precommit_erp_anchor_guard.py",
)

GUIDE_REL_PATH = "3. 웰페리온 가이드/wellperion_guide(main).html"

ANCHOR_REF_RE = re.compile(r"wellperion_guide\(main\)\.html#([A-Za-z0-9_]+)")
ANCHOR_DEF_RE = re.compile(r'(?:id|data-id|data-doc)="([A-Za-z0-9_]+)"')

SKIP_ENV = "SKIP_ERP_ANCHOR_GUARD"


def run(args):
    """git 명령 실행 → (returncode, stdout_bytes)."""
    proc = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return proc.returncode, proc.stdout


def repo_root():
    rc, out = run(["git", "rev-parse", "--show-toplevel"])
    if rc != 0:
        return None
    return out.decode("utf-8", "replace").strip()


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


def is_excluded(disp_norm):
    if disp_norm in SELF_EXEMPT_PATHS:
        return True
    return any(sub in disp_norm for sub in EXCLUDE_SUBSTRINGS)


def collect_refs(files):
    """staged 대상 파일에서 (파일경로, 줄번호, ID) 참조 목록 수집."""
    refs = []
    guide_norm = GUIDE_REL_PATH.replace("\\", "/")
    for path_bytes in files:
        try:
            disp = path_bytes.decode("utf-8", "replace")
            norm = disp.replace("\\", "/")
            low = norm.lower()
            if not low.endswith(WATCH_SUFFIXES):
                continue
            if is_excluded(norm):
                continue
            # 가이드 HTML 자신은 검사 대상에서 제외(자기 참조 오탐 방지).
            if norm == guide_norm:
                continue

            blob = staged_blob(path_bytes)
            if blob is None:
                continue

            text = blob.decode("utf-8", "replace")
            for lineno, line in enumerate(text.splitlines(), start=1):
                for m in ANCHOR_REF_RE.finditer(line):
                    refs.append((disp, lineno, m.group(1)))
        except Exception:
            # 개별 파일 처리 실패 → 그 파일만 건너뜀(fail-open).
            continue
    return refs


def canonical_anchors(root):
    """가이드 HTML에서 id=·data-id=·data-doc= 값 전체 집합. 실패 시 None."""
    guide_abs = os.path.join(root, *GUIDE_REL_PATH.split("/"))
    with open(guide_abs, "r", encoding="utf-8", errors="replace") as f:
        text = f.read()
    return set(ANCHOR_DEF_RE.findall(text))


def main():
    if os.environ.get(SKIP_ENV) == "1":
        sys.stderr.write(
            "[erp-anchor-guard][WARN] %s=1 — 가드 우회(통과)\n" % SKIP_ENV
        )
        return 0

    files = staged_files()
    if files is None:
        sys.stderr.write("[erp-anchor-guard][WARN] git diff 실패 — 통과(fail-open)\n")
        return 0

    refs = collect_refs(files)
    if not refs:
        return 0  # 참조가 없으면 가이드 파일을 읽을 필요도 없음.

    root = repo_root()
    if root is None:
        sys.stderr.write("[erp-anchor-guard][WARN] git root 를 찾을 수 없음 — 통과(fail-open)\n")
        return 0

    try:
        anchors = canonical_anchors(root)
    except Exception as exc:
        sys.stderr.write(
            "[erp-anchor-guard][WARN] 가이드 HTML 읽기 실패 — 통과(fail-open): %r\n" % (exc,)
        )
        return 0

    violations = [(disp, lineno, aid) for disp, lineno, aid in refs if aid not in anchors]

    if violations:
        candidates = ", ".join(sorted(anchors)[:30])
        sys.stderr.write(
            "\n"
            "============================================================\n"
            "[erp-anchor-guard] 커밋 차단 — 존재하지 않는 ERP 문서 앵커 참조\n"
            "------------------------------------------------------------\n"
        )
        for disp, lineno, aid in violations:
            sys.stderr.write(
                "  - %s:%d\n"
                "      #%s → 가이드에 없는 앵커(레거시 구주소 포함)\n"
                % (disp, lineno, aid)
            )
        sys.stderr.write(
            "------------------------------------------------------------\n"
            "  현존 앵커 후보: %s%s\n"
            "  2026-07-03 M5→M1 리넘버 때 하드코딩 주소가 안 바뀌어 20일간\n"
            "  존재하지 않는 문서를 안내한 사고(M5) 재발 방지용입니다.\n"
            "  의도적(신설 예정 등)이라면 우회:  git commit --no-verify\n"
            "  또는 env %s=1\n"
            "============================================================\n"
            % (candidates, " ..." if len(anchors) > 30 else "", SKIP_ENV)
        )
        return 1

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        sys.stderr.write(
            "[erp-anchor-guard][WARN] 가드 내부 오류 — 통과(fail-open): %r\n" % (exc,)
        )
        sys.exit(0)
