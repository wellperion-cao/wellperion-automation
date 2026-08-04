# -*- coding: utf-8 -*-
"""safe_commit._precheck_violations — chro/cfo 보호 삭제 판정 단위 테스트.

배경: 2026-08-04 실사고 — COO(배10390)·CPO(배198) 무관 업무 커밋이
chro/hub/photos 지원자 사진 삭제를 같이 담았다(status/welly_auto_runner_log.jsonl
live_run 이벤트로 확정: commit 8c9205a8f/425cbb58a, 18223f4d2/31841eec1).
그 커밋들은 이 경로 밖(coo/notice, cpo/member, status/... 등)도 대량으로 같이
바꿨는데, chro 파일이 caller 의 rel_paths 안에 "잘못 포함"돼 기존 "무관 경로
혼입" 판정을 피해 가는 경우까지 잡으려면(caller 가 chro/ 를 자기 rel_paths 에
직접 넣는 실수) 도메인 순수성 판정이 따로 필요하다 — 이 테스트가 그 경로다.
(caller 가 chro/ 를 rel_paths 밖에 두는 정상적인 스윕은 기존 "무관 경로 혼입"
판정이 이미 잡는다 — tests/test_precommit_phantom_delete_guard.py 쪽 재현 참고.)

git 은 tmp_path 격리 — 실제 저장소를 절대 건드리지 않는다.
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import safe_commit as SC  # noqa: E402

_CHRO_PHOTO = SC.PROTECTED_DELETE_PREFIXES[0] + "hub/photos/r125.jpg"
_UNRELATED = "coo/check/파트너팀 체계.html"


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


def test_mixed_domain_delete_blocked_even_when_caller_lists_both_paths(tmp_path):
    """실사고 재현: caller 가 chro 사진 + 무관 파일을 자기 rel_paths 에 함께 넣고
    사진을 실제 삭제한 채 커밋을 시도 — 기존 '무관 경로 혼입' 판정은 두 경로 다
    caller 가 지정했으므로 통과시킨다. 새 도메인 순수성 판정이 이걸 잡아야 한다."""
    _init_repo(tmp_path)
    _commit_file(tmp_path, _CHRO_PHOTO, content="photo-bytes\n")
    _commit_file(tmp_path, _UNRELATED, content="점검 결과\n")
    os.remove(tmp_path / _CHRO_PHOTO)
    (tmp_path / _UNRELATED).write_text("갱신된 점검 결과\n", encoding="utf-8")

    res = SC.safe_commit(
        [_CHRO_PHOTO, _UNRELATED], "chore(coo): 무관 업무 + chro 사진 삭제 혼입",
        holder="test_sweep_repro", repo_root=str(tmp_path), push=False,
    )
    assert res["ok"] is False
    assert res["committed"] is False
    assert any("보호된 삭제 차단" in v for v in res["foreign"])
    assert any("r125.jpg" in v for v in res["foreign"])
    # HEAD 가 그대로다 — 나쁜 커밋이 만들어지지 않았다.
    head_files = subprocess.run(
        ["git", "-C", str(tmp_path), "-c", "core.quotepath=false",
         "ls-tree", "-r", "--name-only", "HEAD"],
        capture_output=True, text=True, encoding="utf-8",
    ).stdout
    assert _CHRO_PHOTO.replace("\\", "/") in head_files


def test_pure_domain_delete_still_allowed(tmp_path):
    """커밋 전체가 chro/ 안에서만 이뤄지면(도메인 전용 호출) 실제 삭제도 통과한다
    — 인사 담당(나우열M)의 정상 업무까지 막지 않는지 확인."""
    _init_repo(tmp_path)
    _commit_file(tmp_path, _CHRO_PHOTO, content="photo-bytes\n")
    os.remove(tmp_path / _CHRO_PHOTO)

    res = SC.safe_commit(
        [_CHRO_PHOTO], "chore(chro): 지원자 사진 정리",
        holder="test_chro_owner", repo_root=str(tmp_path), push=False,
    )
    assert res["ok"] is True
    assert res["committed"] is True
    assert res["foreign"] == []


# ── 일반 혼입 삭제 판정 (2026-08-04 GM 근본분석 — 판정 축 교체) ──────────────
# 원격(다른 PC·remote 세션)이 추가한 파일은 배245 무접촉 통합이 작업트리에
# 실체화하지 않아 이 PC 에선 삭제로 보인다. 오늘 실제 피해는 chro/cfo 밖에서도
# 났다(tests/·_assets/profile/·coo/notice/·.deploy-procurement/ — 커밋 425cbb58a).
# 아래는 그 부류 전체를 막는 새 판정의 재현이다.

def test_general_sweep_delete_blocked_via_directory_path(tmp_path):
    """①실사고 재현: 무관 업무 커밋(디렉터리 지정)이 남의 삭제를 쓸어담음 → 차단."""
    _init_repo(tmp_path)
    _commit_file(tmp_path, "tests/test_foo.py", content="assert True\n")
    _commit_file(tmp_path, "coo/check/점검.html", content="점검\n")
    os.remove(tmp_path / "tests/test_foo.py")  # 원격 추가분이 로컬에 없던 상황 재현
    (tmp_path / "coo/check/점검.html").write_text("갱신\n", encoding="utf-8")

    res = SC.safe_commit(
        ["tests", "coo/check/점검.html"], "chore(coo): 무관 업무 — tests 삭제 혼입",
        holder="test_general_sweep", repo_root=str(tmp_path), push=False,
    )
    assert res["ok"] is False and res["committed"] is False
    assert any("혼입 삭제 차단" in v for v in res["foreign"])
    assert any("tests/test_foo.py" in v for v in res["foreign"])


def test_other_victim_paths_blocked_same_way(tmp_path):
    """③오늘 피해 본 다른 경로(_assets/·coo/notice/)도 같은 방식으로 차단."""
    _init_repo(tmp_path)
    victims = ["3. 웰페리온 가이드/_assets/profile/profilewall.js",
               "3. 웰페리온 가이드/coo/notice/게시물_프로필월.html"]
    for v in victims:
        _commit_file(tmp_path, v, content="원격 추가분\n")
    _commit_file(tmp_path, "status/erp_status.json", content="{}\n")
    for v in victims:
        os.remove(tmp_path / v)
    (tmp_path / "status/erp_status.json").write_text('{"v":2}\n', encoding="utf-8")

    res = SC.safe_commit(
        ["3. 웰페리온 가이드", "status/erp_status.json"], "chore: 무관 업무 커밋",
        holder="test_victims", repo_root=str(tmp_path), push=False,
    )
    assert res["ok"] is False and res["committed"] is False
    assert any("profilewall.js" in v for v in res["foreign"])
    assert any("게시물_프로필월.html" in v for v in res["foreign"])


def test_intended_delete_passes_when_file_listed_exactly(tmp_path):
    """②의도된 삭제: 삭제할 파일을 경로에 직접 나열하면 다른 변경과 섞여도 통과."""
    _init_repo(tmp_path)
    _commit_file(tmp_path, "scripts/old_tool.py", content="낡음\n")
    _commit_file(tmp_path, "scripts/new_tool.py", content="v1\n")
    os.remove(tmp_path / "scripts/old_tool.py")
    (tmp_path / "scripts/new_tool.py").write_text("v2\n", encoding="utf-8")

    res = SC.safe_commit(
        ["scripts/old_tool.py", "scripts/new_tool.py"], "refactor: old_tool 제거·new_tool 갱신",
        holder="test_intended", repo_root=str(tmp_path), push=False,
    )
    assert res["ok"] is True and res["committed"] is True
    assert res["foreign"] == []


def test_plain_commit_without_deletion_passes(tmp_path):
    """④삭제 없는 평범한 커밋 → 통과(오탐 0)."""
    _init_repo(tmp_path)
    _commit_file(tmp_path, "docs/a.md", content="v1\n")
    (tmp_path / "docs/a.md").write_text("v2\n", encoding="utf-8")

    res = SC.safe_commit(
        ["docs/a.md"], "docs: 갱신",
        holder="test_plain", repo_root=str(tmp_path), push=False,
    )
    assert res["ok"] is True and res["committed"] is True
    assert res["foreign"] == []
