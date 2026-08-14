# -*- coding: utf-8 -*-
"""무인 러너 자식 인덱스 격리 자체점검 (배296).

지키는 것: 러너가 띄우는 자식 세션은 **공용 인덱스를 절대 못 건드린다.** 자식에게 HEAD 로
새로 뜬 임시 인덱스를 쥐여 주므로, 남이 이미 `git add` 해 둔 파일이 자식 커밋에 딸려
들어갈 통로가 없다(2026-08-03 인사 허브 사진 2장 삭제 사고).

읽기 전용이다 — 커밋도 스테이징도 하지 않는다.
실행: C:/Python314/python.exe scripts/test_runner_index_guard.py
"""
from __future__ import annotations

import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import welly_auto_runner as w  # noqa: E402

ROOT = w._PROJECT_ROOT


def _staged(env=None) -> list[str]:
    out = subprocess.run(["git", "diff", "--cached", "--name-only"], cwd=ROOT,
                         capture_output=True, text=True, encoding="utf-8", env=env)
    return [ln for ln in out.stdout.splitlines() if ln.strip()]


def test_isolated_index_hides_foreign_staging():
    """공용 인덱스에 남의 스테이징이 있든 없든, 임시 인덱스에는 0건이어야 한다."""
    idx = os.path.join(ROOT, ".git", f"index-guardtest-{os.getpid()}")
    env = {**os.environ, "GIT_INDEX_FILE": idx}
    try:
        subprocess.run(["git", "read-tree", "HEAD"], cwd=ROOT, capture_output=True,
                       timeout=30, env=env, check=True)
        live = _staged()
        tmp = _staged(env)
        assert tmp == [], f"임시 인덱스에 스테이징이 보인다(격리 실패): {tmp}"
        print(f"  ok  격리 — 공용 인덱스 스테이징 {len(live)}건 · 임시 인덱스 0건")
    finally:
        if os.path.exists(idx):
            os.remove(idx)


def test_live_index_untouched():
    """임시 인덱스를 쓰고 나서도 공용 인덱스는 그대로여야 한다(부작용 0)."""
    before = _staged()
    test_isolated_index_hides_foreign_staging()
    after = _staged()
    assert before == after, f"공용 인덱스가 바뀌었다: {before} -> {after}"
    print("  ok  공용 인덱스 무변경")


def test_guard_is_wired():
    """가드가 코드에 실제로 박혀 있는지 — 주석만 남고 배선이 빠지는 것을 막는다."""
    src = open(os.path.join(ROOT, "scripts", "welly_auto_runner.py"), encoding="utf-8").read()
    assert 'child_env["GIT_INDEX_FILE"] = child_index' in src, "자식 env 에 GIT_INDEX_FILE 배선 없음"
    assert 'child_index_setup_failed' in src, "임시 인덱스 준비 실패 시 중단 경로 없음"
    print("  ok  배선 확인(자식 env + 실패 시 중단)")


if __name__ == "__main__":
    print("무인 러너 자식 인덱스 격리 자체점검")
    test_guard_is_wired()
    test_live_index_untouched()
    print("전부 통과")
