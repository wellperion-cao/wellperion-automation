"""
test_weekly_page_hygiene.py — 주간 페이지 위생 자동화 pytest.
검증 대상: scripts/weekly_page_hygiene.py
claude 헤드리스 호출(run_audit_claude)은 전부 monkeypatch로 대체 — 실제 API 호출 0회.
파일 쓰기·git commit이 필요한 테스트는 tmp_path로 _PROJECT_ROOT를 리다이렉트하고
_git_commit_file을 스텁으로 대체해 실제 리포를 건드리지 않는다.
"""

import json
import os
import subprocess
import sys

import pytest

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_TESTS_DIR)
_SCRIPTS_DIR = os.path.join(_PROJECT_ROOT, "scripts")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

import weekly_page_hygiene as wph  # noqa: E402


# ── load_targets: config 실측(읽기전용 — 실제 리포 대상 존재 확인) ──
def test_load_targets_coo_returns_13_pages():
    targets = wph.load_targets("coo")
    assert len(targets) == 13


@pytest.mark.parametrize("clevel,expected_count", [
    ("coo", 13),  # 2026-07-16 e1a2f73: "강습팀 업장관리" 페이지 삭제로 14 -> 13
    ("cpo", 3),
    ("cmo", 7),
    ("cto", 2),
    ("cfo", 3),
    ("chro", 12),
    ("shared", 6),  # 공용 3 + 리다이렉트 스텁 3
])
def test_load_targets_per_clevel_counts(clevel, expected_count):
    assert len(wph.load_targets(clevel)) == expected_count


def test_load_targets_all_clevels_sum_to_46_total():
    # 2026-07-14: 감사한 전사 47페이지를 config가 커버했으나, 2026-07-16 e1a2f73
    # 커밋에서 "강습팀 업장관리" 페이지가 삭제되며 46으로 줄었다(대상 목록 갱신).
    assert len(wph.load_targets(None)) == 46


def test_load_targets_all_paths_exist_on_disk():
    # 전체 47페이지(신규 CPO/CMO/CTO/CFO/CHRO/shared 포함) 실존 확인.
    for t in wph.load_targets(None):
        abs_path = os.path.join(_PROJECT_ROOT, t["path"])
        assert os.path.exists(abs_path), f"대상 파일 없음: {t['path']}"


def test_load_targets_none_clevel_returns_all():
    assert wph.load_targets(None) == wph.PAGE_TARGETS


# ── _extract_json ──
def test_extract_json_plain():
    assert wph._extract_json('{"candidates": []}') == {"candidates": []}


def test_extract_json_with_code_fence():
    text = '```json\n{"candidates": [{"category": "A"}]}\n```'
    parsed = wph._extract_json(text)
    assert parsed["candidates"][0]["category"] == "A"


def test_extract_json_with_prose_wrapper():
    text = 'Here is the analysis:\n{"candidates": []}\nDone.'
    assert wph._extract_json(text) == {"candidates": []}


def test_extract_json_invalid_returns_none():
    assert wph._extract_json("not json at all") is None
    assert wph._extract_json("") is None


# ── check_parse_integrity ──
def test_parse_integrity_balanced_ok():
    html = "<div><style>.a{}</style><script>var x=1;</script></div>"
    result = wph.check_parse_integrity(html)
    assert result["ok"] is True
    assert result["issues"] == []


def test_parse_integrity_unbalanced_script_detected():
    html = "<div><script>var x=1;</div>"  # </script> 누락
    result = wph.check_parse_integrity(html)
    assert result["ok"] is False
    assert any("script" in issue for issue in result["issues"])


def test_parse_integrity_unbalanced_div_detected():
    html = "<div><div>내용</div>"  # 닫는 div 하나 부족
    result = wph.check_parse_integrity(html)
    assert result["ok"] is False
    assert any("div" in issue for issue in result["issues"])


# ── verify_zero_consumers: 실제 git grep(격리된 tmp git repo) ──
@pytest.fixture
def tmp_git_repo(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "test"], cwd=tmp_path, check=True)
    return tmp_path


def test_verify_zero_consumers_true_when_only_declaration(tmp_git_repo):
    page = tmp_git_repo / "page.html"
    page.write_text(".dead-class{color:red}", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_git_repo, check=True)
    result = wph.verify_zero_consumers("dead-class", "page.html", repo_root=str(tmp_git_repo))
    assert result["zero"] is True


def test_verify_zero_consumers_false_when_used_elsewhere(tmp_git_repo):
    (tmp_git_repo / "page.html").write_text(".used-class{color:red}", encoding="utf-8")
    (tmp_git_repo / "other.html").write_text('<div class="used-class">x</div>', encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_git_repo, check=True)
    result = wph.verify_zero_consumers("used-class", "page.html", repo_root=str(tmp_git_repo))
    assert result["zero"] is False
    assert result["match_count"] == 2


def test_verify_zero_consumers_false_when_used_twice_same_file(tmp_git_repo):
    # 선언 + 같은 파일 내 재사용(2건) = 소비자 존재로 보수적 판정
    (tmp_git_repo / "page.html").write_text(
        ".reused-class{color:red}\n<div class=\"reused-class\">x</div>", encoding="utf-8"
    )
    subprocess.run(["git", "add", "."], cwd=tmp_git_repo, check=True)
    result = wph.verify_zero_consumers("reused-class", "page.html", repo_root=str(tmp_git_repo))
    assert result["zero"] is False


def test_verify_zero_consumers_empty_symbol_blocked(tmp_git_repo):
    result = wph.verify_zero_consumers("", "page.html", repo_root=str(tmp_git_repo))
    assert result["zero"] is False


# ── apply_category_a: 3중 게이트 ──
def test_apply_category_a_succeeds_with_clean_gate(tmp_git_repo, monkeypatch):
    content = ".dead-class{color:red}\n<div>본문</div>"
    (tmp_git_repo / "page.html").write_text(content, encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_git_repo, check=True)

    monkeypatch.setattr(wph, "_PROJECT_ROOT", str(tmp_git_repo))
    candidate = {"symbol": "dead-class", "snippet": ".dead-class{color:red}\n"}
    result = wph.apply_category_a(content, candidate, "page.html")
    assert result["applied"] is True
    assert "dead-class" not in result["content"]


def test_apply_category_a_skips_when_symbol_has_consumer(tmp_git_repo, monkeypatch):
    content = ".used-class{color:red}\n<div class=\"used-class\">본문</div>"
    (tmp_git_repo / "page.html").write_text(content, encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_git_repo, check=True)

    monkeypatch.setattr(wph, "_PROJECT_ROOT", str(tmp_git_repo))
    candidate = {"symbol": "used-class", "snippet": ".used-class{color:red}\n"}
    result = wph.apply_category_a(content, candidate, "page.html")
    assert result["applied"] is False
    assert "소비자" in result["reason"]
    assert result["content"] == content  # 원본 무변경


def test_apply_category_a_skips_when_snippet_missing():
    candidate = {"symbol": "dead-class", "snippet": ""}
    result = wph.apply_category_a("irrelevant", candidate, "page.html")
    assert result["applied"] is False
    assert "snippet" in result["reason"]


def test_apply_category_a_skips_when_snippet_not_unique(tmp_git_repo, monkeypatch):
    # symbol("only-once")은 grep-0 게이트를 통과(파일 내 1건뿐)하지만, snippet("DUP_MARKER\n")은
    # 파일 내 2회 등장해 고유성 게이트에서 걸려야 한다(두 게이트를 독립적으로 검증).
    content = ".only-once{color:red}\nDUP_MARKER\nDUP_MARKER\n"
    (tmp_git_repo / "page.html").write_text(content, encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_git_repo, check=True)

    monkeypatch.setattr(wph, "_PROJECT_ROOT", str(tmp_git_repo))
    candidate = {"symbol": "only-once", "snippet": "DUP_MARKER\n"}
    result = wph.apply_category_a(content, candidate, "page.html")
    assert result["applied"] is False
    assert "고유" in result["reason"]


def test_apply_category_a_rolls_back_on_parse_integrity_failure(tmp_git_repo, monkeypatch):
    content = "<script>function deadFnOk(){}</script><script>var x=1;</script>"
    (tmp_git_repo / "page.html").write_text(content, encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_git_repo, check=True)

    monkeypatch.setattr(wph, "_PROJECT_ROOT", str(tmp_git_repo))
    # snippet이 열고 닫는 태그까지 통째로 제거하는 정상 케이스(대조군) — 균형 유지되어 성공해야 함
    candidate = {"symbol": "deadFnOk", "snippet": "<script>function deadFnOk(){}</script>"}
    result = wph.apply_category_a(content, candidate, "page.html")
    assert result["applied"] is True

    # 진짜 불균형 유발 케이스: snippet이 </script>는 남기고 여는 태그+본문만 삭제
    # (symbol은 page.html의 다른 심볼과 충돌하지 않는 고유명 사용 — grep-0/고유성 게이트는 통과시키고
    # 오직 무결성 게이트만 걸리도록 격리)
    content2 = "<script>function deadFnBad(){}</script>"
    (tmp_git_repo / "page2.html").write_text(content2, encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_git_repo, check=True)
    candidate2 = {"symbol": "deadFnBad", "snippet": "<script>function deadFnBad(){}"}
    result2 = wph.apply_category_a(content2, candidate2, "page2.html")
    assert result2["applied"] is False
    assert "무결성" in result2["reason"]


# ── run_pipeline: apply gate 기본 OFF + force_dry_run 오버라이드 ──
def _fake_audit_factory(candidates):
    def _fake(prompt, timeout=240, model="claude-sonnet-4-6"):
        return {"ok": True, "candidates": candidates, "raw": "", "error": None}
    return _fake


@pytest.fixture
def isolated_pipeline(tmp_path, monkeypatch):
    """run_pipeline이 실제 리포를 건드리지 않도록 _PROJECT_ROOT를 tmp_path로 격리."""
    (tmp_path / "status").mkdir()
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "test"], cwd=tmp_path, check=True)
    monkeypatch.setattr(wph, "_PROJECT_ROOT", str(tmp_path))
    commit_calls = []
    monkeypatch.setattr(wph, "_git_commit_file", lambda path, msg, **kw: commit_calls.append((path, msg)) or "fakehash")
    return tmp_path, commit_calls


def test_run_pipeline_default_gate_off_never_applies(isolated_pipeline, monkeypatch):
    tmp_path, commit_calls = isolated_pipeline
    (tmp_path / "page.html").write_text(".dead-class{color:red}\n<div>본문</div>", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)

    candidates = [{
        "category": "A", "kind": "css-class", "symbol": "dead-class",
        "snippet": ".dead-class{color:red}\n", "location": "L1", "reason": "미사용",
        "preserve_check": "실데이터 아님",
    }]
    monkeypatch.setattr(wph, "run_audit_claude", _fake_audit_factory(candidates))
    monkeypatch.delenv(wph.APPLY_ENV_VAR, raising=False)

    result = wph.run_pipeline(
        clevel=None, targets=[{"clevel": "coo", "label": "테스트", "path": "page.html"}],
        notify=False, log_path=str(tmp_path / "log.jsonl"),
    )

    assert result["apply_gate"] is False
    assert result["apply_total"] == 0
    assert result["proposal_total"] == 1
    assert commit_calls == []
    assert (tmp_path / "page.html").read_text(encoding="utf-8") == ".dead-class{color:red}\n<div>본문</div>"
    # dry 미리보기: grep-0 게이트가 통과 가능함을 보여주되 적용은 안 함
    proposed = result["per_target_results"][0]["proposed"][0]
    assert proposed["would_auto_apply"] is True


def test_run_pipeline_force_dry_run_overrides_live_gate(isolated_pipeline, monkeypatch):
    tmp_path, commit_calls = isolated_pipeline
    (tmp_path / "page.html").write_text(".dead-class{color:red}\n<div>본문</div>", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)

    candidates = [{
        "category": "A", "kind": "css-class", "symbol": "dead-class",
        "snippet": ".dead-class{color:red}\n", "location": "L1", "reason": "미사용",
        "preserve_check": "실데이터 아님",
    }]
    monkeypatch.setattr(wph, "run_audit_claude", _fake_audit_factory(candidates))

    result = wph.run_pipeline(
        clevel=None, apply=True, force_dry_run=True,
        targets=[{"clevel": "coo", "label": "테스트", "path": "page.html"}],
        notify=False, log_path=str(tmp_path / "log.jsonl"),
    )

    assert result["apply_total"] == 0
    assert commit_calls == []


def test_run_pipeline_live_apply_writes_and_commits(isolated_pipeline, monkeypatch):
    tmp_path, commit_calls = isolated_pipeline
    (tmp_path / "page.html").write_text(".dead-class{color:red}\n<div>본문</div>", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)

    candidates = [{
        "category": "A", "kind": "css-class", "symbol": "dead-class",
        "snippet": ".dead-class{color:red}\n", "location": "L1", "reason": "미사용",
        "preserve_check": "실데이터 아님",
    }]
    monkeypatch.setattr(wph, "run_audit_claude", _fake_audit_factory(candidates))

    result = wph.run_pipeline(
        clevel=None, apply=True, force_dry_run=False,
        targets=[{"clevel": "coo", "label": "테스트", "path": "page.html"}],
        notify=False, log_path=str(tmp_path / "log.jsonl"),
    )

    assert result["apply_total"] == 1
    assert len(commit_calls) == 1
    new_content = (tmp_path / "page.html").read_text(encoding="utf-8")
    assert "dead-class" not in new_content


def test_run_pipeline_live_apply_skips_candidate_with_real_consumer(isolated_pipeline, monkeypatch):
    tmp_path, commit_calls = isolated_pipeline
    content = ".used-class{color:red}\n<div class=\"used-class\">본문</div>"
    (tmp_path / "page.html").write_text(content, encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)

    candidates = [{
        "category": "A", "kind": "css-class", "symbol": "used-class",
        "snippet": ".used-class{color:red}\n", "location": "L1", "reason": "미사용(오판)",
        "preserve_check": "실데이터 아님(오판)",
    }]
    monkeypatch.setattr(wph, "run_audit_claude", _fake_audit_factory(candidates))

    result = wph.run_pipeline(
        clevel=None, apply=True, force_dry_run=False,
        targets=[{"clevel": "coo", "label": "테스트", "path": "page.html"}],
        notify=False, log_path=str(tmp_path / "log.jsonl"),
    )

    # grep-0 게이트가 실제 소비자(같은 파일 내 재사용)를 잡아 자동적용 스킵 -> 제안으로 강등
    assert result["apply_total"] == 0
    assert result["proposal_total"] == 1
    assert commit_calls == []
    assert (tmp_path / "page.html").read_text(encoding="utf-8") == content


def test_run_pipeline_bcd_categories_never_auto_applied(isolated_pipeline, monkeypatch):
    tmp_path, commit_calls = isolated_pipeline
    (tmp_path / "page.html").write_text("<div>중복 설명 블록</div>", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)

    candidates = [
        {"category": "B", "kind": "duplicate-text", "location": "L1", "reason": "중복"},
        {"category": "C", "kind": "stale-notice", "location": "L2", "reason": "낡음"},
        {"category": "D", "kind": "verbose-block", "location": "L3", "reason": "장황"},
    ]
    monkeypatch.setattr(wph, "run_audit_claude", _fake_audit_factory(candidates))

    result = wph.run_pipeline(
        clevel=None, apply=True, force_dry_run=False,
        targets=[{"clevel": "coo", "label": "테스트", "path": "page.html"}],
        notify=False, log_path=str(tmp_path / "log.jsonl"),
    )

    assert result["apply_total"] == 0
    assert result["proposal_total"] == 3
    assert commit_calls == []


def test_run_pipeline_shared_file_targets_process_sequentially(isolated_pipeline, monkeypatch):
    """메인가이드 O1~O4처럼 같은 물리 파일을 가리키는 target들은 앞선 target의 적용이
    다음 target 감사에 반영되고, 파일당 커밋은 1회만 발생해야 한다."""
    tmp_path, commit_calls = isolated_pipeline
    content = ".dead-o1{color:red}\n.dead-o2{color:blue}\n<div>본문</div>"
    (tmp_path / "shared.html").write_text(content, encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)

    call_count = {"n": 0}

    def _fake_audit(prompt, timeout=240, model="claude-sonnet-4-6"):
        call_count["n"] += 1
        if call_count["n"] == 1:
            cand = {"category": "A", "kind": "css-class", "symbol": "dead-o1",
                     "snippet": ".dead-o1{color:red}\n", "location": "L1", "reason": "미사용"}
        else:
            # 두 번째 호출 시점엔 이미 dead-o1이 제거된 content를 봐야 한다
            assert "dead-o1" not in prompt
            cand = {"category": "A", "kind": "css-class", "symbol": "dead-o2",
                     "snippet": ".dead-o2{color:blue}\n", "location": "L2", "reason": "미사용"}
        return {"ok": True, "candidates": [cand], "raw": "", "error": None}

    monkeypatch.setattr(wph, "run_audit_claude", _fake_audit)

    targets = [
        {"clevel": "coo", "label": "O1", "path": "shared.html", "anchor": "O1"},
        {"clevel": "coo", "label": "O2", "path": "shared.html", "anchor": "O2"},
    ]
    result = wph.run_pipeline(
        clevel=None, apply=True, force_dry_run=False, targets=targets,
        notify=False, log_path=str(tmp_path / "log.jsonl"),
    )

    assert result["apply_total"] == 2
    assert len(commit_calls) == 1  # 파일당 1커밋
    final = (tmp_path / "shared.html").read_text(encoding="utf-8")
    assert "dead-o1" not in final and "dead-o2" not in final


def test_run_pipeline_audit_error_recorded_not_crashing(isolated_pipeline, monkeypatch):
    tmp_path, commit_calls = isolated_pipeline
    (tmp_path / "page.html").write_text("<div>본문</div>", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)

    def _fail(prompt, timeout=240, model="claude-sonnet-4-6"):
        return {"ok": False, "candidates": [], "raw": "garbage", "error": "JSON 파싱 실패"}

    monkeypatch.setattr(wph, "run_audit_claude", _fail)

    result = wph.run_pipeline(
        clevel=None, targets=[{"clevel": "coo", "label": "테스트", "path": "page.html"}],
        notify=False, log_path=str(tmp_path / "log.jsonl"),
    )
    assert result["error_total"] == 1
    assert commit_calls == []


# ── build_telegram_summary / write_proposal_file ──
def test_build_telegram_summary_reports_gate_mode():
    text_off = wph.build_telegram_summary(0, 3, 0, "/x/status/page_hygiene_proposal_20260101.md", False)
    assert "제안모드" in text_off
    text_on = wph.build_telegram_summary(2, 1, 2, "/x/status/page_hygiene_proposal_20260101.md", True)
    assert "라이브" in text_on


def test_write_proposal_file_creates_categorized_markdown(tmp_path):
    per_target_results = [{
        "target": {"label": "테스트페이지", "path": "page.html"},
        "audit_ok": True, "error": None,
        "applied": [{"kind": "css-class", "symbol": "dead", "reason": "미사용", "gate_reason": "소비자 0건"}],
        "proposed": [{"category": "B", "kind": "duplicate-text", "location": "L1", "reason": "중복",
                       "gate_reason": "", "would_auto_apply": False}],
    }]
    path = wph.write_proposal_file(per_target_results, "coo", date_str="20260101", out_dir=str(tmp_path))
    assert os.path.exists(path)
    text = open(path, encoding="utf-8").read()
    assert "테스트페이지" in text
    assert "자동 적용됨" in text
    assert "중복 설명 병합" in text
