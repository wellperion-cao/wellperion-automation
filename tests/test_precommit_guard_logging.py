# -*- coding: utf-8 -*-
"""가드 판정 로그(PASS/WARN/BLOCK) 회귀 검사 — 배 가드판정로그구멍(2026-08-17 시토).

배경: secret·truncation·enforcement·queue·erp_anchor·sheet_link 6개 pre-commit
가드가 막았는지 통과시켰는지 아무 데도 안 남았다. scripts/precommit_
phantom_delete_guard.py 에 이미 있던 _log_block 자리를 log_guard_decision 으로
넓혀 6개 가드가 공유하게 했다(logs/phantom_delete_guard.jsonl, 새 로그파일 없음).

이 검사가 확인하는 것(딱 이 세 가지 — 판정 로직 자체는 각 가드의 기존 테스트가
이미 담당한다):
  ①PASS·BLOCK 두 경우 모두 로그 한 줄이 남는가
  ②로그 쓰기가 실패해도(디렉터리를 파일로 막아 os.makedirs 를 깨뜨림) 가드
    판정(return code)이 그대로인가
  ③기존 판정 결과(0/1)가 이번 변경으로 안 바뀌는가
"""
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import precommit_phantom_delete_guard as PDG  # noqa: E402
import precommit_secret_guard as SEC  # noqa: E402
import precommit_truncation_guard as TRUNC  # noqa: E402
import precommit_queue_guard as QUEUE  # noqa: E402
import precommit_erp_anchor_guard as ERP  # noqa: E402
import precommit_sheet_link_guard as SHEET  # noqa: E402

# precommit_enforcement_guard 는 import 시점에 sys.stdout/stderr 를
# TextIOWrapper 로 재바인딩한다(기존 동작, 안 건드림). 그 래퍼가 나중에 GC 되며
# 물려있는 원본 버퍼까지 닫아버려 pytest capture 가 깨진다 — import 전후로
# 원래 스트림을 되돌리고, 새로 생긴 래퍼는 detach() 로 버퍼 소유를 끊는다.
_orig_stdout, _orig_stderr = sys.stdout, sys.stderr
import precommit_enforcement_guard as ENF  # noqa: E402
_wrapped_stdout, _wrapped_stderr = sys.stdout, sys.stderr
sys.stdout, sys.stderr = _orig_stdout, _orig_stderr
for _w in (_wrapped_stdout, _wrapped_stderr):
    try:
        _w.detach()
    except Exception:
        pass

LOG_REL = "logs/phantom_delete_guard.jsonl"


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


def _stage_commit(tmp_path, rel_path, content):
    """이미 커밋된 파일 내용을 바꿔 stage(HEAD 대비 diff 유발용)."""
    (tmp_path / rel_path).write_text(content, encoding="utf-8")
    _git(["add", rel_path], tmp_path)


def _log_entries(tmp_path):
    p = tmp_path / LOG_REL
    if not p.exists():
        return []
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line]


def _last_for(tmp_path, guard):
    entries = [e for e in _log_entries(tmp_path) if e.get("guard") == guard]
    assert entries, "guard=%s 로그 없음" % guard
    return entries[-1]


# ── secret ──────────────────────────────────────────────────────────────────
def test_secret_guard_logs_pass_and_block(tmp_path, monkeypatch):
    _init_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    _stage_file(tmp_path, "a.py", "x = 1\n")
    rc = SEC.main()
    assert rc == 0
    assert _last_for(tmp_path, "secret")["decision"] == "PASS"

    _git(["commit", "-q", "-m", "clean"], tmp_path)
    _stage_file(tmp_path, "b.py", 'TOKEN = "78012345678:AAExxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"\n')
    rc = SEC.main()
    assert rc == 1
    assert _last_for(tmp_path, "secret")["decision"] == "BLOCK"


# ── sheet_link ──────────────────────────────────────────────────────────────
def test_sheet_link_guard_logs_pass_and_block(tmp_path, monkeypatch):
    _init_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    _stage_file(tmp_path, "a.py", "x = 1\n")
    rc = SHEET.main()
    assert rc == 0
    assert _last_for(tmp_path, "sheet_link")["decision"] == "PASS"

    _git(["commit", "-q", "-m", "clean"], tmp_path)
    _stage_file(
        tmp_path, "notify.py",
        'sendMessage(chat_id, "https://docs.google.com/spreadsheets/d/xxx")\n',
    )
    rc = SHEET.main()
    assert rc == 1
    assert _last_for(tmp_path, "sheet_link")["decision"] == "BLOCK"


# ── erp_anchor ──────────────────────────────────────────────────────────────
def test_erp_anchor_guard_logs_pass_and_block(tmp_path, monkeypatch):
    _init_repo(tmp_path)
    guide_rel = "3. 웰페리온 가이드/wellperion_guide(main).html"
    _stage_file(tmp_path, guide_rel, '<div id="M1">real</div>\n')
    _git(["commit", "-q", "-m", "guide"], tmp_path)
    monkeypatch.chdir(tmp_path)

    _stage_file(tmp_path, "notify.py", "x = 1\n")
    rc = ERP.main()
    assert rc == 0
    assert _last_for(tmp_path, "erp_anchor")["decision"] == "PASS"

    _git(["commit", "-q", "-m", "clean"], tmp_path)
    _stage_file(tmp_path, "notify2.py", 'url = "wellperion_guide(main).html#M5"\n')
    rc = ERP.main()
    assert rc == 1
    assert _last_for(tmp_path, "erp_anchor")["decision"] == "BLOCK"


# ── truncation ──────────────────────────────────────────────────────────────
def test_truncation_guard_logs_pass_and_block(tmp_path, monkeypatch):
    _init_repo(tmp_path)
    big = "".join("line %d\n" % i for i in range(300))
    _stage_file(tmp_path, "page.html", big)
    _git(["commit", "-q", "-m", "big"], tmp_path)
    monkeypatch.chdir(tmp_path)

    _stage_commit(tmp_path, "page.html", big + "extra\n")
    rc = TRUNC.main()
    assert rc == 0
    assert _last_for(tmp_path, "truncation")["decision"] == "PASS"

    _git(["commit", "-q", "-m", "clean"], tmp_path)
    small = "".join("line %d\n" % i for i in range(10))
    _stage_commit(tmp_path, "page.html", small)
    rc = TRUNC.main()
    assert rc == 1
    assert _last_for(tmp_path, "truncation")["decision"] == "BLOCK"


# ── queue ───────────────────────────────────────────────────────────────────
def test_queue_guard_logs_pass_and_block(tmp_path, monkeypatch):
    _init_repo(tmp_path)
    _stage_file(
        tmp_path, "status/_queue.json",
        json.dumps([{"id": "t1", "status": "PENDING"}], ensure_ascii=False),
    )
    _git(["commit", "-q", "-m", "queue"], tmp_path)
    monkeypatch.chdir(tmp_path)

    # PASS: 기존 활성 항목 유지 + 신규 추가(소멸 없음)
    _stage_commit(
        tmp_path, "status/_queue.json",
        json.dumps(
            [{"id": "t1", "status": "PENDING"}, {"id": "t2", "status": "PENDING"}],
            ensure_ascii=False,
        ),
    )
    rc = QUEUE.main()
    assert rc == 0
    assert _last_for(tmp_path, "queue")["decision"] == "PASS"

    _git(["commit", "-q", "-m", "clean"], tmp_path)
    # BLOCK: 활성(PENDING) 항목 t1 이 종결·아카이브 근거 없이 그냥 사라짐
    _stage_commit(
        tmp_path, "status/_queue.json",
        json.dumps([{"id": "t2", "status": "PENDING"}], ensure_ascii=False),
    )
    rc = QUEUE.main()
    assert rc == 1
    assert _last_for(tmp_path, "queue")["decision"] == "BLOCK"


# ── enforcement (E 모듈 자체 판정 로직은 monkeypatch 로 격리 — 여기선 배선만 검사) ──
def test_enforcement_guard_logs_pass_and_block(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    os.makedirs(tmp_path / "logs", exist_ok=True)

    from ssot import enforcement as E

    monkeypatch.setattr(E, "get_mode", lambda: E.ENFORCE_MODE_OFF)
    rc = ENF.main()
    assert rc == 0
    assert _last_for(tmp_path, "enforcement")["decision"] == "PASS"

    monkeypatch.setattr(E, "get_mode", lambda: E.ENFORCE_MODE_BLOCK)
    monkeypatch.setattr(E, "staged_files", lambda: ["ssot/canon_values.json"])
    monkeypatch.setattr(E, "check_canon_promise_change", lambda files=None: ["ssot/canon_values.json"])
    monkeypatch.setattr(E, "check_forbidden_path_change", lambda files=None: [])
    monkeypatch.setattr(E, "check_security_live_activation", lambda files=None: [])
    monkeypatch.setattr(E, "is_bypassed", lambda commit_message=None: False)
    monkeypatch.setattr(E, "log_event", lambda *a, **k: None)
    monkeypatch.setattr(E, "notify_warn", lambda *a, **k: None)
    rc = ENF.main()
    assert rc == 1
    assert _last_for(tmp_path, "enforcement")["decision"] == "BLOCK"


# ── 로그 쓰기 실패해도 가드 판정은 그대로(fail-soft) ─────────────────────────
def test_log_write_failure_does_not_change_verdict(tmp_path, monkeypatch):
    _init_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    _stage_file(tmp_path, "b.py", 'TOKEN = "78012345678:AAExxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"\n')

    # logs/ 자리에 파일을 만들어 os.makedirs(logs/) 가 깨지게 한다.
    (tmp_path / "logs").write_text("not a dir\n", encoding="utf-8")

    rc = SEC.main()  # 로그 기록은 실패하지만 판정(차단)은 그대로여야 한다.
    assert rc == 1


def test_log_guard_decision_swallows_errors(monkeypatch):
    """log_guard_decision 자체가 예외를 던지지 않는지(호출부 보호) 직접 확인."""
    monkeypatch.setattr(PDG.os, "makedirs", lambda *a, **k: (_ for _ in ()).throw(OSError("boom")))
    PDG.log_guard_decision("dummy", "PASS")  # 예외 없이 조용히 무시되어야 함
