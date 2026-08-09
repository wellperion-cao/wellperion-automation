#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_reception_wp_drift.py — 종합접수처 리포↔WP 드리프트 재발방지 가드

동작:
  staged 파일에 reception_block.html 이 포함되면 WP 라이브(page 8434) 반영
  리마인드를 경고 출력한다. 그 외에는 무출력.

배경(정본):
  WP 종합접수처(wellperion.com/ko/reception/, post_id 8434)는
  reception_block.html 의 폼 HTML 을 [vc_raw_html] base64 blob 인라인
  사본으로 저장 — 리포 파일을 고쳐도 WP 라이브엔 자동 반영 안 됨.
  GM 결정(2026-07-15·A안): 정본=리포 reception_block.html 단일.
    - 대량/구조 변경 → wordpress_admin_playwright.py --mode draft-reception --post-id 8434
    - 한 문자열 교체 → wordpress_admin_playwright.py --mode swap-reception-text
  memory: reference_wp_reception_inline_copy_drift

안전 원칙:
  경고 전용(warn-only) — exit 1 없음. 커밋 절대 막지 않음.
  모든 예외 → fail-open(exit 0).
"""

import subprocess
import sys
import io

try:
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "buffer"):
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
except Exception:
    pass

# 워드프레스에 사본이 인라인으로 박혀 있어, 리포만 고치면 라이브가 안 바뀌는 파일들.
# (경로 끝, 라이브 주소, 주입 명령) — 습득물 접수는 2026-08-10 추가(배315):
# 리포는 08-03 에 고쳐 뒀는데 라이브는 나흘간 옛 폼('등록 직원(선택)')으로 접수받고 있었다.
# 화면은 멀쩡히 떠서 아무도 못 알아챘다 — 종합접수처와 같은 부류라 같은 가드에 태운다(약속 L21).
_TARGETS = [
    ("coo/reception/reception_block.html",
     "http://wellperion.com/ko/reception/",
     "  대량변경=python scripts/wordpress_admin_playwright.py --mode draft-reception --post-id 8434\n"
     "  한 문자열=python scripts/wordpress_admin_playwright.py --mode swap-reception-text\n"),
    ("coo/reception/wp_lost_found_register_block.html",
     "http://wellperion.com/ko/lost-found-register/",
     "  주입=python scripts/wordpress_admin_playwright.py --mode draft-page --page lf-register --post-id 8464\n"),
]


def _staged_files() -> set:
    """staged 파일 레포 상대경로 집합(forward-slash). 실패 시 빈 집합."""
    try:
        proc = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "-z"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if proc.returncode != 0:
            return set()
        parts = proc.stdout.split(b"\x00")
        return {p.decode("utf-8", "replace") for p in parts if p}
    except Exception:
        return set()


def main() -> int:
    try:
        staged = _staged_files()
        if not staged:
            return 0

        paths = {s.replace("\\", "/") for s in staged}
        for suffix, live_url, how in _TARGETS:
            if not any(p.endswith(suffix) for p in paths):
                continue
            sys.stdout.write(
                f"\n⚠️ {suffix.rsplit('/', 1)[-1]} 변경 감지 — WP 라이브 반영 필요:\n"
                f"{how}"
                f"  저장 후 시크릿 크롬으로 {live_url} 실측 확인.\n\n"
            )
        return 0

    except Exception as exc:
        try:
            sys.stderr.write(f"[reception-wp-drift][WARN] 가드 내부 오류 — fail-open: {exc!r}\n")
        except Exception:
            pass
        return 0


if __name__ == "__main__":
    sys.exit(main())
