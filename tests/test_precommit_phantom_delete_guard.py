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


# ── ⑦~⑨ chro/cfo 보호 삭제(2026-08-04 · 인사 지원자 사진 반복삭제 사고 재현) ──
# 실사고: COO·CPO 무관 업무 커밋이 chro/hub/photos 지원자 사진 삭제를 같이
# 담았다(배 425cbb58a·31841eec1, status/welly_auto_runner_log.jsonl live_run 로
# 확정). 사진이 디스크에도 실제로 없어(진짜 삭제) 위 ①~⑥ 유령 삭제 판정을
# 피해 간다 — 아래는 그 정확한 재현.
_CHRO_PHOTO = G.PROTECTED_DELETE_PREFIXES[0] + "hub/photos/r125.jpg"


def test_protected_delete_mixed_domain_blocks(tmp_path, monkeypatch, capsys):
    """무관 업무 파일 + chro 사진을 같은 커밋에 실제 삭제로 staged → 차단(실사고 재현)."""
    _init_repo(tmp_path)
    _commit_file(tmp_path, _CHRO_PHOTO, content="photo-bytes\n")
    _commit_file(tmp_path, "coo/check/파트너팀 체계.html", content="점검 결과\n")
    _stage_real_delete(tmp_path, _CHRO_PHOTO)
    (tmp_path / "coo/check/파트너팀 체계.html").write_text("갱신된 점검 결과\n", encoding="utf-8")
    _git(["add", "coo/check/파트너팀 체계.html"], tmp_path)
    monkeypatch.chdir(tmp_path)
    rc = G.main()
    assert rc == 1
    err = capsys.readouterr().err
    assert "r125.jpg" in err
    assert "chro/cfo" in err


def test_protected_delete_pure_domain_passes(tmp_path, monkeypatch, capsys):
    """커밋 전체가 chro/ 안에서만 이뤄지면(도메인 전용 도구) 실제 삭제도 통과."""
    _init_repo(tmp_path)
    _commit_file(tmp_path, _CHRO_PHOTO, content="photo-bytes\n")
    _stage_real_delete(tmp_path, _CHRO_PHOTO)
    monkeypatch.chdir(tmp_path)
    rc = G.main()
    assert rc == 0


def test_protected_delete_without_any_deletion_passes(tmp_path, monkeypatch, capsys):
    """chro 경로를 건드리지만 삭제가 없으면(추가·수정만) 무관 경로와 섞여도 통과."""
    _init_repo(tmp_path)
    _commit_file(tmp_path, "coo/check/파트너팀 체계.html")
    (tmp_path / _CHRO_PHOTO).parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / _CHRO_PHOTO).write_text("new-photo\n", encoding="utf-8")
    _git(["add", "coo/check/파트너팀 체계.html", _CHRO_PHOTO], tmp_path)
    monkeypatch.chdir(tmp_path)
    rc = G.main()
    assert rc == 0


# ── 일반 혼입 삭제 판정(2026-08-04 GM 근본분석) — 훅 경로(맨손 git commit) ──
def test_mixed_delete_any_domain_blocks(tmp_path, monkeypatch, capsys):
    """chro/cfo 밖 경로라도, 진짜 삭제가 비삭제 변경과 섞이면 차단(오늘 실사고 부류)."""
    _init_repo(tmp_path)
    _commit_file(tmp_path, "tests/test_foo.py")
    _commit_file(tmp_path, "status/erp_status.json")
    _stage_real_delete(tmp_path, "tests/test_foo.py")
    (tmp_path / "status/erp_status.json").write_text("{}\n", encoding="utf-8")
    _git(["add", "status/erp_status.json"], tmp_path)
    monkeypatch.chdir(tmp_path)
    rc = G.main()
    assert rc == 1
    err = capsys.readouterr().err
    assert "혼입 삭제" in err
    assert "test_foo.py" in err


def test_delete_only_commit_passes(tmp_path, monkeypatch, capsys):
    """삭제만 담은 커밋(전부 D) = 명시적 의도 → 통과."""
    _init_repo(tmp_path)
    _commit_file(tmp_path, "docs/old1.md")
    _commit_file(tmp_path, "docs/old2.md")
    _stage_real_delete(tmp_path, "docs/old1.md")
    _stage_real_delete(tmp_path, "docs/old2.md")
    monkeypatch.chdir(tmp_path)
    rc = G.main()
    assert rc == 0


def test_foreign_delete_violations_unit():
    """판정 함수 단위 계약: 혼합=위반 / 삭제전용=통과 / 명시나열=통과 / 보호도메인전용=통과."""
    assert G.foreign_delete_violations([], ["a.py"]) == []
    assert G.foreign_delete_violations(["gone.py"], ["gone.py"]) == []           # 삭제 전용
    assert G.foreign_delete_violations(["gone.py"], ["gone.py", "kept.py"]) == ["gone.py"]  # 혼합
    assert G.foreign_delete_violations(["gone.py"], ["gone.py", "kept.py"],
                                        explicit_paths=["gone.py"]) == []        # 명시 나열
    pre = G.PROTECTED_DELETE_PREFIXES[0]
    assert G.foreign_delete_violations([pre + "x.jpg"], [pre + "x.jpg", pre + "y.html"]) == []  # 보호 도메인 전용


# ── 동결(스테일) 인덱스 — 게이트(나) + 통합 직후 동기화(가) (2026-08-04 GM 지시 ②) ──
# post_commit_push 무접촉 통합이 HEAD 만 전진시키고 라이브 인덱스를 안 맞춰,
# 인덱스가 옛 트리에 동결 → 이후 커밋이 남의 최신 변경을 옛것으로 되돌리거나
# 원격 추가분을 삭제로 쓸어담았다(2026-08-04 실사고). 가=원인 제거, 나=안전망.

def test_stale_index_entry_blocks_with_guidance(tmp_path, monkeypatch, capsys):
    """①스테이징 blob 이 HEAD 와도 작업트리와도 다르면(동결 인덱스) 차단 + 해법 안내."""
    _init_repo(tmp_path)
    _commit_file(tmp_path, "docs/f.md", content="v1\n")
    (tmp_path / "docs/f.md").write_text("v2\n", encoding="utf-8")
    _git(["add", "docs/f.md"], tmp_path)
    (tmp_path / "docs/f.md").write_text("v3\n", encoding="utf-8")  # index=v2·HEAD=v1·디스크=v3
    monkeypatch.chdir(tmp_path)
    rc = G.main()
    assert rc == 1
    err = capsys.readouterr().err
    assert "동결" in err and "git reset" in err  # 차단 + 푸는 법 안내


def test_normal_staged_commit_passes_stale_gate(tmp_path, monkeypatch, capsys):
    """③평범한 스테이징(스테이징=디스크) → 통과(오탐 0)."""
    _init_repo(tmp_path)
    _commit_file(tmp_path, "docs/g.md", content="v1\n")
    (tmp_path / "docs/g.md").write_text("v2\n", encoding="utf-8")
    _git(["add", "docs/g.md"], tmp_path)
    monkeypatch.chdir(tmp_path)
    assert G.main() == 0


def test_reconcile_syncs_index_to_new_head(tmp_path):
    """②무접촉 통합 직후 인덱스=새 HEAD(동결 0) ③원격 추가분 디스크 실체화
    ④로컬에서 수정 중인 파일은 절대 안 덮임(가장 중요한 안전 조건)."""
    import post_commit_push as P

    bare = tmp_path / "origin.git"
    _git(["init", "-q", "--bare", "-b", "master", str(bare)], tmp_path)
    local = tmp_path / "local"
    local.mkdir()
    _git(["init", "-q", "-b", "master"], local)
    _git(["config", "user.email", "t@t.t"], local)
    _git(["config", "user.name", "T"], local)
    (local / "README.md").write_text("init\n", encoding="utf-8")
    (local / "shared.md").write_text("v1\n", encoding="utf-8")
    _git(["add", "README.md", "shared.md"], local)
    _git(["commit", "-q", "-m", "init"], local)
    _git(["remote", "add", "origin", str(bare)], local)
    _git(["push", "-q", "origin", "master"], local)

    # 나우열M PC 역할 — 별도 클론이 파일 추가 + shared.md 수정 후 push
    other = tmp_path / "other"
    _git(["clone", "-q", str(bare), str(other)], tmp_path)
    _git(["config", "user.email", "n@t.t"], other)
    _git(["config", "user.name", "N"], other)
    _commit_file(other, "photos/r999.jpg", content="remote-added\n")
    (other / "shared.md").write_text("v2-remote\n", encoding="utf-8")
    _git(["add", "shared.md"], other)
    _git(["commit", "-q", "-m", "shared v2"], other)
    _git(["push", "-q", "origin", "master"], other)

    _commit_file(local, "local.md", content="local work\n")  # 로컬도 앞섬 → non-ff
    # 로컬에서 shared.md 를 수정 중(미커밋) — 통합·실체화가 절대 덮으면 안 됨
    (local / "shared.md").write_text("local-uncommitted\n", encoding="utf-8")

    ok, reason = P._reconcile(str(local))
    assert ok, reason
    # ② 인덱스 ↔ 새 HEAD 차이 0건 (동결 없음)
    r = subprocess.run(["git", "-C", str(local), "diff", "--cached", "--name-only"],
                       capture_output=True, text=True, encoding="utf-8")
    assert r.stdout.strip() == "", r.stdout
    # ③ 원격 추가분: HEAD·인덱스에 들어왔고 **디스크에도 실체화**됐다(다)
    ls = subprocess.run(["git", "-C", str(local), "ls-files", "--", "photos/r999.jpg"],
                        capture_output=True, text=True, encoding="utf-8")
    assert ls.stdout.strip() != ""
    assert (local / "photos/r999.jpg").exists()
    assert (local / "photos/r999.jpg").read_text(encoding="utf-8") == "remote-added\n"
    # ④ 로컬에 존재하며 수정 중이던 파일은 그대로 — 원격 v2 로 덮이지 않았다
    assert (local / "shared.md").read_text(encoding="utf-8") == "local-uncommitted\n"
