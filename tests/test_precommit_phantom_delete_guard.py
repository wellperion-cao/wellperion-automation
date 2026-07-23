# -*- coding: utf-8 -*-
"""precommit_phantom_delete_guard 단위 테스트 — 유령 삭제(작업트리엔 있는데
삭제로 staged) 커밋 차단.

배경: 2026-07-23 하루 두 번 터진 사고(배9961) — ①커밋 b7d4f3817 임시 인덱스
read-tree 실패를 삼켜 빈 인덱스로 커밋 → 3,156개 파일이 삭제로 기록(INC-029).
②같은 날 저녁 시포가 공용 인덱스에 옛 스냅샷이 물린 걸 발견 — 그대로
커밋됐으면 그날 만든 가드 7개가 삭제될 뻔했다. 재발 방지 가드.
git·파일시스템은 tmp_path 격리 — 실제 저장소 상태에 의존하지 않음.
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import precommit_phantom_delete_guard as G  # noqa: E402


def _git(args, cwd):
    subprocess.run(["git"] + args, cwd=cwd, check=True,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def _init_repo(tmp_path):
    _git(["init", "-q"], tmp_path)
    _git(["config", "user.email", "test@test.com"], tmp_path)
    _git(["config", "user.name", "Test"], tmp_path)
    (tmp_path / "README.md").write_text("init\n", encoding="utf-8")
    _git(["add", "."], tmp_path)
    _git(["commit", "-q", "-m", "init"], tmp_path)


def _commit_file(tmp_path, rel_path, content="content\n"):
    full = tmp_path / rel_path
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(content, encoding="utf-8")
    _git(["add", rel_path], tmp_path)
    _git(["commit", "-q", "-m", "add %s" % rel_path], tmp_path)


def _stage_delete_from_index_only(tmp_path, rel_path):
    """작업트리 파일은 남겨둔 채 인덱스에서만 삭제로 staged (유령 삭제 재현)."""
    _git(["rm", "--cached", rel_path], tmp_path)


def _stage_real_delete(tmp_path, rel_path):
    """작업트리에서도 실제로 지우고 삭제로 staged (진짜 삭제)."""
    _git(["rm", rel_path], tmp_path)


# ── ①디스크엔 있는데 삭제로 staged → 차단 ──────────────────────────────────
def test_phantom_delete_blocks(tmp_path, monkeypatch, capsys):
    _init_repo(tmp_path)
    _commit_file(tmp_path, "docs/keep.md")
    _stage_delete_from_index_only(tmp_path, "docs/keep.md")
    monkeypatch.chdir(tmp_path)
    rc = G.main()
    assert rc == 1
    err = capsys.readouterr().err
    assert "keep.md" in err


# ── ②진짜 삭제(디스크에도 없음) → 통과 ─────────────────────────────────────
def test_real_delete_passes(tmp_path, monkeypatch, capsys):
    _init_repo(tmp_path)
    _commit_file(tmp_path, "docs/gone.md")
    _stage_real_delete(tmp_path, "docs/gone.md")
    monkeypatch.chdir(tmp_path)
    rc = G.main()
    assert rc == 0


# ── ③삭제 staged 0건 → 통과 ────────────────────────────────────────────────
def test_no_deletions_passes_quietly(tmp_path, monkeypatch, capsys):
    _init_repo(tmp_path)
    _commit_file(tmp_path, "docs/untouched.md")
    monkeypatch.chdir(tmp_path)
    rc = G.main()
    assert rc == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    assert captured.out == ""


# ── ④위반 21건 → 20건 + '외 1건' 으로 줄어드는지 ────────────────────────────
def test_many_violations_truncated(tmp_path, monkeypatch, capsys):
    _init_repo(tmp_path)
    rels = ["docs/f%02d.md" % i for i in range(21)]
    for rel in rels:
        _commit_file(tmp_path, rel)
    for rel in rels:
        _stage_delete_from_index_only(tmp_path, rel)
    monkeypatch.chdir(tmp_path)
    rc = G.main()
    assert rc == 1
    err = capsys.readouterr().err
    assert "외 1건" in err
    # 20개까지만 개별 나열됐는지(마지막 1개는 목록에 없고 카운트에만 반영)
    listed = sum(1 for rel in rels if rel in err)
    assert listed == 20


# ── ⑤env 우회 스위치 동작 ────────────────────────────────────────────────────
def test_env_bypass_switch(tmp_path, monkeypatch, capsys):
    _init_repo(tmp_path)
    _commit_file(tmp_path, "docs/keep.md")
    _stage_delete_from_index_only(tmp_path, "docs/keep.md")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SKIP_PHANTOM_DELETE_GUARD", "1")
    rc = G.main()
    assert rc == 0


# ── ⑥한글·공백 포함 경로도 정확히 잡히는지 ──────────────────────────────────
def test_korean_and_space_path_detected(tmp_path, monkeypatch, capsys):
    _init_repo(tmp_path)
    rel = "상태 보고/점검 일지.md"
    _commit_file(tmp_path, rel)
    _stage_delete_from_index_only(tmp_path, rel)
    monkeypatch.chdir(tmp_path)
    rc = G.main()
    assert rc == 1
    err = capsys.readouterr().err
    assert "점검 일지.md" in err
