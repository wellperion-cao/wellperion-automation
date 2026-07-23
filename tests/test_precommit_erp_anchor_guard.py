# -*- coding: utf-8 -*-
"""precommit_erp_anchor_guard 단위 테스트 — 죽은 ERP 문서 앵커 참조 커밋 차단.

배경: 2026-07-03 M5→M1 리넘버 때 하드코딩 앵커 주소가 안 바뀌어 20일간 GM께
존재하지 않는 문서를 안내한 사고(가이드의 M_LEGACY 조용한 리다이렉트로 은폐)
재발 방지 가드. git·파일시스템은 tmp_path 격리 — 실제 저장소 상태에 의존하지 않음.
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import precommit_erp_anchor_guard as G  # noqa: E402

GUIDE_REL = "3. 웰페리온 가이드/wellperion_guide(main).html"

GUIDE_HTML = """<!doctype html>
<html><body>
<a data-id="S2">AI C-Level 운영 가이드</a>
<a data-id="M1">콘텐츠 제작 · 검수·발행</a>
<article class="doc" id="S2">...</article>
<article class="doc" id="M1">...</article>
<script>
  // 구 M번호 → 새 M번호 폴백. M2/M4/M5 는 id/data-id 속성이 아니라 JS 객체
  // 키일 뿐 — 정본 앵커 집합에 들어가면 안 됨(이번 사고의 원인).
  const M_LEGACY = { M2: 'M1', M4: 'M2', M5: 'M1' };
</script>
</body></html>
"""


def _git(args, cwd):
    subprocess.run(["git"] + args, cwd=cwd, check=True,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def _init_repo(tmp_path, with_guide=True):
    _git(["init", "-q"], tmp_path)
    _git(["config", "user.email", "test@test.com"], tmp_path)
    _git(["config", "user.name", "Test"], tmp_path)
    if with_guide:
        guide_dir = tmp_path / "3. 웰페리온 가이드"
        guide_dir.mkdir(parents=True, exist_ok=True)
        (guide_dir / "wellperion_guide(main).html").write_text(GUIDE_HTML, encoding="utf-8")
        _git(["add", "."], tmp_path)
        _git(["commit", "-q", "-m", "init"], tmp_path)


def _stage_file(tmp_path, rel_path, content):
    full = tmp_path / rel_path
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(content, encoding="utf-8")
    _git(["add", rel_path], tmp_path)


# ── ①존재 앵커 통과 ──────────────────────────────────────────────────────────
def test_existing_anchor_passes(tmp_path, monkeypatch, capsys):
    _init_repo(tmp_path)
    _stage_file(
        tmp_path, "scripts/notify.py",
        "URL = 'wellperion_guide(main).html#S2'\n",
    )
    monkeypatch.chdir(tmp_path)
    rc = G.main()
    assert rc == 0


# ── ②죽은 앵커 차단(exit 1) ──────────────────────────────────────────────────
def test_dead_anchor_blocks(tmp_path, monkeypatch, capsys):
    _init_repo(tmp_path)
    _stage_file(
        tmp_path, "scripts/notify.py",
        "URL = 'wellperion_guide(main).html#M5'\n",
    )
    monkeypatch.chdir(tmp_path)
    rc = G.main()
    assert rc == 1
    err = capsys.readouterr().err
    assert "M5" in err
    assert "notify.py" in err


# ── ③가이드 파일 부재 시 fail-open ───────────────────────────────────────────
def test_missing_guide_fails_open(tmp_path, monkeypatch, capsys):
    _init_repo(tmp_path, with_guide=False)
    _stage_file(
        tmp_path, "scripts/notify.py",
        "URL = 'wellperion_guide(main).html#M5'\n",
    )
    monkeypatch.chdir(tmp_path)
    rc = G.main()
    assert rc == 0
    err = capsys.readouterr().err
    assert "erp-anchor-guard" in err


# ── ④env 우회 스위치 동작 ────────────────────────────────────────────────────
def test_env_bypass_switch(tmp_path, monkeypatch, capsys):
    _init_repo(tmp_path)
    _stage_file(
        tmp_path, "scripts/notify.py",
        "URL = 'wellperion_guide(main).html#M5'\n",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SKIP_ERP_ANCHOR_GUARD", "1")
    rc = G.main()
    assert rc == 0


# ── ⑤제외 경로(_archive 등) 무시 ─────────────────────────────────────────────
def test_excluded_path_ignored(tmp_path, monkeypatch, capsys):
    _init_repo(tmp_path)
    _stage_file(
        tmp_path, "scripts/_archive/legacy_notify.py",
        "URL = 'wellperion_guide(main).html#M5'\n",
    )
    monkeypatch.chdir(tmp_path)
    rc = G.main()
    assert rc == 0


# ── 보너스: 가이드 파일 자신은 검사 대상에서 제외 ────────────────────────────
def test_guide_file_self_reference_excluded(tmp_path, monkeypatch, capsys):
    _init_repo(tmp_path)
    # 가이드 자신 안에 죽은 앵커 문자열(M_LEGACY 주석 등)이 있어도 자기 참조는 스킵.
    guide_path = GUIDE_REL
    full = tmp_path / guide_path
    full.write_text(GUIDE_HTML + "\n<!-- wellperion_guide(main).html#M5 -->\n", encoding="utf-8")
    _git(["add", guide_path], tmp_path)
    monkeypatch.chdir(tmp_path)
    rc = G.main()
    assert rc == 0


# ── 보너스: 참조 없는 커밋은 가이드조차 안 읽고 통과 ─────────────────────────
def test_no_reference_no_guide_read_needed(tmp_path, monkeypatch, capsys):
    _init_repo(tmp_path, with_guide=False)
    _stage_file(tmp_path, "scripts/notify.py", "print('hello')\n")
    monkeypatch.chdir(tmp_path)
    rc = G.main()
    assert rc == 0
    assert capsys.readouterr().err == ""


# ── 가드 자신·자기 테스트는 검사 제외 (실제 발생한 자기차단 사고 재발 방지) ──
# 2026-07-23: 가드가 설명문에 예시로 담은 죽은 앵커(#M5) 때문에 자기 커밋을 차단했다.
def test_guard_self_and_its_test_are_exempt(tmp_path, monkeypatch, capsys):
    _init_repo(tmp_path)
    for rel in (
        "scripts/precommit_erp_anchor_guard.py",
        "tests/test_precommit_erp_anchor_guard.py",
    ):
        _stage_file(
            tmp_path, rel,
            "예시 = 'wellperion_guide(main).html#M5'  # 설명·픽스처용 죽은 앵커\n",
        )
    monkeypatch.chdir(tmp_path)
    assert G.main() == 0
