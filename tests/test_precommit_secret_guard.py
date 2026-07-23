# -*- coding: utf-8 -*-
"""precommit_secret_guard 단위 테스트 — 비밀값(자격증명) 평문 커밋 차단.

배경: @namuki_report_bot 텔레그램 봇 토큰이 2026-06-24부터 공개 저장소에
평문으로 들어가 한 달 넘게 아무도 몰랐다(시모가 07-23 발견). 사람이 조심하는
것으로는 못 막는다는 게 증명됐다 — 재발 방지 가드. git·파일시스템은 tmp_path
격리 — 실제 저장소 상태에 의존하지 않음.
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import precommit_secret_guard as G  # noqa: E402

TELEGRAM_TOKEN = "7801234567:AAExxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
GOOGLE_API_KEY = "AIzaSyDaGmWKa4JsXZ-HjGw7ISLn_3namBGewQe"
AWS_ACCESS_KEY = "AKIAIOSFODNN7EXAMPLE"


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


# ── ①텔레그램 봇 토큰 추가 → 차단 ───────────────────────────────────────────
def test_telegram_bot_token_blocks(tmp_path, monkeypatch, capsys):
    _init_repo(tmp_path)
    content = 'BOT_TOKEN = "%s"\n' % TELEGRAM_TOKEN
    _stage_file(tmp_path, "telegram_bot/config.py", content)
    monkeypatch.chdir(tmp_path)
    rc = G.main()
    assert rc == 1
    err = capsys.readouterr().err
    assert "config.py" in err
    assert "텔레그램 봇 토큰" in err


# ── ②Google API 키 → 차단 ──────────────────────────────────────────────────
def test_google_api_key_blocks(tmp_path, monkeypatch, capsys):
    _init_repo(tmp_path)
    content = 'API_KEY = "%s"\n' % GOOGLE_API_KEY
    _stage_file(tmp_path, "scripts/gas_client.py", content)
    monkeypatch.chdir(tmp_path)
    rc = G.main()
    assert rc == 1
    err = capsys.readouterr().err
    assert "Google API 키" in err


# ── ②-2 AWS 액세스 키 → 차단 ────────────────────────────────────────────────
def test_aws_access_key_blocks(tmp_path, monkeypatch, capsys):
    _init_repo(tmp_path)
    content = 'AWS_KEY = "%s"\n' % AWS_ACCESS_KEY
    _stage_file(tmp_path, "scripts/s3_client.py", content)
    monkeypatch.chdir(tmp_path)
    rc = G.main()
    assert rc == 1
    err = capsys.readouterr().err
    assert "AWS 액세스 키" in err


# ── ③개인키 헤더 → 차단 ────────────────────────────────────────────────────
def test_private_key_header_blocks(tmp_path, monkeypatch, capsys):
    _init_repo(tmp_path)
    content = "-----BEGIN RSA PRIVATE KEY-----\nMIIExampleNotARealKey\n-----END RSA PRIVATE KEY-----\n"
    _stage_file(tmp_path, "scripts/deploy_key.pem", content)
    monkeypatch.chdir(tmp_path)
    rc = G.main()
    assert rc == 1
    err = capsys.readouterr().err
    assert "개인키" in err


# ── ④평범한 긴 문자열(커밋 해시·URL) → 통과(오탐 없음) ───────────────────────
def test_ordinary_long_strings_pass(tmp_path, monkeypatch, capsys):
    _init_repo(tmp_path)
    content = (
        "COMMIT_SHA = 'c7ac66849f1234567890abcdef1234567890abcd'\n"
        "URL = 'https://wellperion-cao.github.io/wellperion-automation/index.html'\n"
        "LONG_ID = '1A77oDR9EXAMPLESHEETID1234567890abcdefghijklmno'\n"
    )
    _stage_file(tmp_path, "scripts/constants.py", content)
    monkeypatch.chdir(tmp_path)
    rc = G.main()
    assert rc == 0
    captured = capsys.readouterr()
    assert captured.err == ""


# ── ⑤secret-ok 예외 주석 → 통과 + stdout 로그 ────────────────────────────────
def test_exempt_comment_passes_and_logs(tmp_path, monkeypatch, capsys):
    _init_repo(tmp_path)
    content = 'BOT_TOKEN = "%s"  # secret-ok: 테스트 픽스처 더미값\n' % TELEGRAM_TOKEN
    _stage_file(tmp_path, "tests/fixtures/dummy_token.py", content)
    monkeypatch.chdir(tmp_path)
    rc = G.main()
    assert rc == 0
    out = capsys.readouterr().out
    assert "secret-ok" in out
    assert "dummy_token.py" in out


# ── ⑥env 우회 스위치 동작 ────────────────────────────────────────────────────
def test_env_bypass_switch(tmp_path, monkeypatch, capsys):
    _init_repo(tmp_path)
    content = 'BOT_TOKEN = "%s"\n' % TELEGRAM_TOKEN
    _stage_file(tmp_path, "telegram_bot/config.py", content)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SKIP_SECRET_GUARD", "1")
    rc = G.main()
    assert rc == 0


# ── ⑦가드 자신·자기 테스트 파일 → 통과 ───────────────────────────────────────
def test_guard_self_and_its_test_are_exempt(tmp_path, monkeypatch, capsys):
    _init_repo(tmp_path)
    content = 'EXAMPLE = "%s"\n' % TELEGRAM_TOKEN
    for rel in (
        "scripts/precommit_secret_guard.py",
        "tests/test_precommit_secret_guard.py",
    ):
        _stage_file(tmp_path, rel, content)
    monkeypatch.chdir(tmp_path)
    assert G.main() == 0


# ── 보너스: 기존 줄(추가된 줄 아님)은 검사 대상에서 제외 ─────────────────────
def test_preexisting_line_not_flagged(tmp_path, monkeypatch, capsys):
    _init_repo(tmp_path)
    content = 'BOT_TOKEN = "%s"\n' % TELEGRAM_TOKEN
    _stage_file(tmp_path, "telegram_bot/config.py", content)
    _git(["commit", "-q", "-m", "add config (already has token)"], tmp_path)

    full = tmp_path / "telegram_bot/config.py"
    full.write_text(content + "OTHER = 1\n", encoding="utf-8")
    _git(["add", "telegram_bot/config.py"], tmp_path)
    monkeypatch.chdir(tmp_path)
    rc = G.main()
    assert rc == 0


# ── 보너스: scripts/_archive 경로 제외 ───────────────────────────────────────
def test_scripts_archive_excluded(tmp_path, monkeypatch, capsys):
    _init_repo(tmp_path)
    content = 'BOT_TOKEN = "%s"\n' % TELEGRAM_TOKEN
    _stage_file(tmp_path, "scripts/_archive/old_config.py", content)
    monkeypatch.chdir(tmp_path)
    rc = G.main()
    assert rc == 0


# ── ★출력에 비밀값 원문이 안 나오는지 검증 ───────────────────────────────────
def test_output_never_contains_raw_secret_value(tmp_path, monkeypatch, capsys):
    _init_repo(tmp_path)
    content = 'BOT_TOKEN = "%s"\nAPI_KEY = "%s"\n' % (TELEGRAM_TOKEN, GOOGLE_API_KEY)
    _stage_file(tmp_path, "telegram_bot/config.py", content)
    monkeypatch.chdir(tmp_path)
    rc = G.main()
    assert rc == 1
    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert TELEGRAM_TOKEN not in combined
    assert GOOGLE_API_KEY not in combined
    # 마스킹된 앞 4자만 남아야 한다
    assert TELEGRAM_TOKEN[:4] in combined
    assert GOOGLE_API_KEY[:4] in combined
