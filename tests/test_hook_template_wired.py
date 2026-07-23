# -*- coding: utf-8 -*-
"""커밋 가드가 훅 템플릿에 실제로 배선됐는지 고정 (2026-07-23 시토).

왜 필요한가:
  `scripts/install_hooks.sh` 는 **`scripts/pre-commit.hook`(추적본)을 `.git/hooks/pre-commit`
  으로 복사**한다. 즉 추적본이 진짜 설치 원본이다. 그런데 가드를 새로 만들 때 `.git/hooks`
  (추적 안 됨)에만 배선하고 추적본을 안 고치는 일이 반복됐다 — 2026-07-23 실측 시점에
  추적본은 라이브보다 27줄 뒤처져 있었고, **가드 4개(erp_anchor·sheet_link·assign_ship_numbers·
  sync_queue_mirror)가 빠져 있었다.** 그 상태로 누가 install_hooks.sh 를 돌렸다면 가드들이
  조용히 사라졌을 것이다(문서·기억으로는 못 막는다 — 헌법 불변원리 2).

이 테스트가 하는 일:
  `scripts/precommit_*.py` 가 하나 늘어나면, 추적본에 배선하기 전까지 **여기서 깨진다.**
  새 가드를 만들고 배선을 잊는 경로 자체를 없앤다.
"""
from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "scripts" / "pre-commit.hook"
SCRIPTS = ROOT / "scripts"


def guard_scripts() -> list[str]:
    return sorted(p.name for p in SCRIPTS.glob("precommit_*.py"))


def test_template_exists_and_is_shell():
    assert TEMPLATE.exists(), "훅 템플릿이 없다 — install_hooks.sh 가 복사할 원본"
    head = TEMPLATE.read_text(encoding="utf-8", errors="replace").splitlines()[:1]
    assert head and head[0].startswith("#!"), "훅 템플릿에 셔뱅이 없다"


@pytest.mark.parametrize("guard", guard_scripts())
def test_every_guard_is_wired_into_template(guard: str):
    """scripts/precommit_*.py 는 전부 추적본 훅에 배선돼 있어야 한다."""
    src = TEMPLATE.read_text(encoding="utf-8", errors="replace")
    assert guard in src, (
        f"{guard} 가 scripts/pre-commit.hook 에 배선돼 있지 않다. "
        ".git/hooks 에만 넣으면 install_hooks.sh 재설치 때 사라진다 — 추적본에도 넣어라."
    )


def test_installer_copies_the_tracked_template():
    """설치 스크립트가 추적본을 원본으로 쓴다는 전제 자체를 고정."""
    installer = (SCRIPTS / "install_hooks.sh").read_text(encoding="utf-8", errors="replace")
    assert "pre-commit.hook" in installer, "install_hooks.sh 가 추적본을 복사하지 않는다 — 전제가 깨졌다"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
