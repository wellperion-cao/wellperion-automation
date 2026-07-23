# -*- coding: utf-8 -*-
"""precommit_sheet_link_guard 단위 테스트 — 알림 문구 내 원본 시트 링크 커밋 차단.

배경: GM 지적(2026-07-23) — 신규 강습 문의 텔레그램 알림이 강습 시트(구글
스프레드시트) 원본 링크를 그대로 노출해, 실무진 방 누구나 시트를 직접
수정·삭제하거나 개인정보 전체를 볼 수 있는 상태였다. 재발 방지 가드.
git·파일시스템은 tmp_path 격리 — 실제 저장소 상태에 의존하지 않음.
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import precommit_sheet_link_guard as G  # noqa: E402

SHEET_URL = "https://docs.google.com/spreadsheets/d/abc123/edit"


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


def _stage_file(tmp_path, rel_path, content):
    full = tmp_path / rel_path
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(content, encoding="utf-8")
    _git(["add", rel_path], tmp_path)


# ── ①알림 문맥의 시트 링크 추가 → 차단 ───────────────────────────────────────
def test_notify_context_sheet_link_blocks(tmp_path, monkeypatch, capsys):
    _init_repo(tmp_path)
    content = (
        "def notify_new_inquiry(row):\n"
        "    text = '신규 강습 문의 접수\\n' + '%s'\n"
        "    send_telegram(chat_id, text)\n"
    ) % SHEET_URL
    _stage_file(tmp_path, "scripts/lesson_alert.py", content)
    monkeypatch.chdir(tmp_path)
    rc = G.main()
    assert rc == 1
    err = capsys.readouterr().err
    assert "lesson_alert.py" in err
    assert "docs.google.com" in err


# ── ②대시보드 응답 조립(알림 신호 없음) → 통과 ────────────────────────────────
def test_dashboard_response_no_notify_signal_passes(tmp_path, monkeypatch, capsys):
    _init_repo(tmp_path)
    content = (
        "def build_dashboard_payload():\n"
        "    return {'sheetUrl': '%s'}\n"
    ) % SHEET_URL
    _stage_file(tmp_path, "scripts/dashboard_api.py", content)
    monkeypatch.chdir(tmp_path)
    rc = G.main()
    assert rc == 0


# ── ③기존 줄에 이미 있던 링크(추가된 줄 아님) → 통과 ─────────────────────────
def test_preexisting_line_not_flagged(tmp_path, monkeypatch, capsys):
    _init_repo(tmp_path)
    content = (
        "def notify_new_inquiry(row):\n"
        "    text = '신규 강습 문의 접수\\n' + '%s'\n"
        "    send_telegram(chat_id, text)\n"
    ) % SHEET_URL
    _stage_file(tmp_path, "scripts/lesson_alert.py", content)
    _git(["commit", "-q", "-m", "add alert (already has link)"], tmp_path)

    # 기존 줄은 그대로 두고 무관한 줄만 새로 추가한다.
    full = tmp_path / "scripts/lesson_alert.py"
    full.write_text(content + "    return True\n", encoding="utf-8")
    _git(["add", "scripts/lesson_alert.py"], tmp_path)
    monkeypatch.chdir(tmp_path)
    rc = G.main()
    assert rc == 0


# ── ④sheet-link-ok 예외 주석 → 통과 + stdout 로그 ────────────────────────────
def test_exempt_comment_passes_and_logs(tmp_path, monkeypatch, capsys):
    _init_repo(tmp_path)
    content = (
        "def notify_new_inquiry(row):\n"
        "    text = '신규 강습 문의 접수\\n' + '%s'  # sheet-link-ok: 임시 승인(GM)\n"
        "    send_telegram(chat_id, text)\n"
    ) % SHEET_URL
    _stage_file(tmp_path, "scripts/lesson_alert.py", content)
    monkeypatch.chdir(tmp_path)
    rc = G.main()
    assert rc == 0
    out = capsys.readouterr().out
    assert "sheet-link-ok" in out
    assert "lesson_alert.py" in out


# ── ⑤env 우회 스위치 동작 ────────────────────────────────────────────────────
def test_env_bypass_switch(tmp_path, monkeypatch, capsys):
    _init_repo(tmp_path)
    content = (
        "def notify_new_inquiry(row):\n"
        "    text = '신규 강습 문의 접수\\n' + '%s'\n"
        "    send_telegram(chat_id, text)\n"
    ) % SHEET_URL
    _stage_file(tmp_path, "scripts/lesson_alert.py", content)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SKIP_SHEET_LINK_GUARD", "1")
    rc = G.main()
    assert rc == 0


# ── ⑥가드 자신·자기 테스트 파일 → 통과 ───────────────────────────────────────
def test_guard_self_and_its_test_are_exempt(tmp_path, monkeypatch, capsys):
    _init_repo(tmp_path)
    content = (
        "# 예시 alert 코드 — send_telegram(chat_id, '%s')\n"
    ) % SHEET_URL
    for rel in (
        "scripts/precommit_sheet_link_guard.py",
        "tests/test_precommit_sheet_link_guard.py",
    ):
        _stage_file(tmp_path, rel, content)
    monkeypatch.chdir(tmp_path)
    assert G.main() == 0


# ── 보너스: scripts/_archive 류 경로 제외 ────────────────────────────────────
def test_scripts_archive_excluded(tmp_path, monkeypatch, capsys):
    _init_repo(tmp_path)
    content = (
        "def notify_new_inquiry(row):\n"
        "    send_telegram(chat_id, '%s')\n"
    ) % SHEET_URL
    _stage_file(tmp_path, "scripts/_archive/old_alert.py", content)
    monkeypatch.chdir(tmp_path)
    rc = G.main()
    assert rc == 0


# ── 보너스: .deploy-* 경로는 검사 대상에 포함(제외하면 안 됨) ────────────────
def test_deploy_path_is_included_not_excluded(tmp_path, monkeypatch, capsys):
    _init_repo(tmp_path)
    content = (
        "function notifyCheck(row) {\n"
        "  sendMessage(chatId, '%s');\n"
        "}\n"
    ) % SHEET_URL
    _stage_file(tmp_path, ".deploy-check/alert.js", content)
    monkeypatch.chdir(tmp_path)
    rc = G.main()
    assert rc == 1


# ── 보너스: 참조 없는 커밋은 조용히 통과 ─────────────────────────────────────
def test_no_reference_passes_quietly(tmp_path, monkeypatch, capsys):
    _init_repo(tmp_path)
    _stage_file(tmp_path, "scripts/notify.py", "print('hello')\n")
    monkeypatch.chdir(tmp_path)
    rc = G.main()
    assert rc == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    assert captured.out == ""
