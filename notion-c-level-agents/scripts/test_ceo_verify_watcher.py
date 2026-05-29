# -*- coding: utf-8 -*-
"""ceo_verify_watcher self-test (네트워크·git·텔레그램 없이 stub 검증)

실행:
    python test_ceo_verify_watcher.py
    python ceo_verify_watcher.py --selftest

검증 항목:
  1. commit-subject 정규식 — [DONE][CTO][인프라] 파싱 + non-DONE 무시
  2. DUAL 신호 — [DONE] commit이나 status≠DONE → MISMATCH, 미처리
  3. 멱등성 — 동일 (task_id, commit) 두 번 처리 시 두 번째 스킵
  4. L1 dedup — 동일 task_id가 다른 commit으로 APPROVED → 충돌 flag
  5. 판정 매트릭스 — (L1 pass+fit True)=APPROVED, (L1 fail)=REJECTED,
     (fit False)=REJECTED, (fit None)=AI_PENDING
  6. artifact_url HTTP 비-200 → L1 fail → REJECTED
  7. MISMATCH 후 해소 — 패스 1: 커서 정지; 패스 2: status DONE → APPROVED
  8. 크래시-전-텔레그램 멱등성 — ledger 기록 후 telegram 미발송 → 재처리 스킵
  9. amend/rebase 차단 — task_id REJECTED 후 다른 SHA → terminal_decided 차단
"""

import io
import sys
import tempfile
from pathlib import Path

if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import ceo_verify_watcher as w

# Save originals that test_mismatch_then_resolve needs to restore after stubbing run_once internals
_orig_git_fetch = w.git_fetch
_orig_git_cursor_valid = w.git_cursor_valid
_orig_git_new_commits = w.git_new_commits

_PASS = 0
_FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global _PASS, _FAIL
    if cond:
        _PASS += 1
        print(f"  [PASS] {name}")
    else:
        _FAIL += 1
        print(f"  [FAIL] {name} — {detail}")


class _StubTelegram:
    def __init__(self):
        self.sent = []

    def send(self, msg):
        self.sent.append(msg)
        return {"ok": True}


def _make_repo(tmp: Path, clevel_json: dict, clevel: str = "cto") -> Path:
    """임시 repo 디렉터리 + status/<clevel>.json 작성."""
    (tmp / "status").mkdir(parents=True, exist_ok=True)
    import json
    (tmp / "status" / f"{clevel}.json").write_text(
        json.dumps(clevel_json, ensure_ascii=False), encoding="utf-8")
    return tmp


def _patch_git(monkey_repo: Path, commit_exists: bool = True):
    """git/HTTP/AI 함수를 stub으로 교체. (원복용 dict 반환)"""
    saved = {
        "git_object_type": w.git_object_type,
        "git_show_stat": w.git_show_stat,
        "http_ok": w.http_ok,
        "ai_layer_verify": w.ai_layer_verify,
    }
    w.git_object_type = lambda repo, sha: "commit" if commit_exists else "missing"
    w.git_show_stat = lambda repo, sha: "stub stat"
    w.http_ok = lambda url, timeout=10: (True, "200")
    return saved


def _restore(saved: dict):
    for k, v in saved.items():
        setattr(w, k, v)


# ── 테스트 ────────────────────────────────────────────────────────────────────

def test_regex():
    print("[1] commit-subject 정규식")
    r = w.parse_done_tag("infra hotfix [DONE][CTO][인프라] 가동")
    check("DONE 태그 파싱", r == ("cto", "인프라"), str(r))
    check("non-DONE 무시", w.parse_done_tag("일반 커밋 메시지") is None)
    check("WIP 무시", w.parse_done_tag("[WIP][CTO][인프라]") is None)
    r2 = w.parse_done_tag("[DONE][cmo][CMO-001]")
    check("소문자 정규화", r2 == ("cmo", "CMO-001"), str(r2))


def test_dual_signal():
    print("[2] DUAL 신호 — status≠DONE → MISMATCH")
    with tempfile.TemporaryDirectory() as td:
        repo = _make_repo(Path(td), {"agent": "cto", "task_id": "인프라",
                                     "status": "IN_PROGRESS", "title": "T"})
        saved = _patch_git(repo)
        tg = _StubTelegram()
        ledger = []
        try:
            res = w.process_commit(repo, "a" * 40, "[DONE][CTO][인프라] x",
                                   "GM", ledger, tg, no_ai=True, dry_run=False)
        finally:
            _restore(saved)
        check("MISMATCH 판정", res["verdict"] == w.MISMATCH, str(res))
        check("ledger 미기록", len(ledger) == 0, str(ledger))
        check("MISMATCH 텔레그램 경고", any("MISMATCH" in m for m in tg.sent))


def test_idempotency():
    print("[3] 멱등성 — 동일 (task_id, commit) 재처리 스킵")
    with tempfile.TemporaryDirectory() as td:
        repo = _make_repo(Path(td), {"agent": "cto", "task_id": "인프라",
                                     "status": "DONE", "title": "T",
                                     "artifact_url": None})
        saved = _patch_git(repo)
        w.ai_layer_verify = lambda ctx, no_ai=False: {"fit": True, "reason": "ok",
                                                      "principle_check": "ok"}
        tg = _StubTelegram()
        ledger = []
        try:
            r1 = w.process_commit(repo, "b" * 40, "[DONE][CTO][인프라] x",
                                  "GM", ledger, tg, no_ai=False, dry_run=False)
            r2 = w.process_commit(repo, "b" * 40, "[DONE][CTO][인프라] x",
                                  "GM", ledger, tg, no_ai=False, dry_run=False)
        finally:
            _restore(saved)
        check("1차 APPROVED", r1["verdict"] == w.APPROVED, str(r1))
        check("2차 스킵", r2.get("skipped") == "already_processed", str(r2))
        check("ledger 1건만", len(ledger) == 1, str(len(ledger)))


def test_l1_dedup():
    print("[4] L1 dedup — 동일 task_id 다른 commit APPROVED → 충돌")
    with tempfile.TemporaryDirectory() as td:
        repo = _make_repo(Path(td), {"agent": "cto", "task_id": "인프라",
                                     "status": "DONE", "title": "T",
                                     "artifact_url": None})
        # 이미 다른 commit으로 APPROVED 된 ledger
        ledger = [{"task_id": "인프라", "clevel": "CTO", "commit": "c" * 40,
                   "verdict": w.APPROVED, "processed_at": "t"}]
        l1 = w.layer1_verify(repo, "d" * 40, "cto", "인프라", None, ledger)
        # commit 객체 stub 없이 layer1 직접 호출 → git_object_type 실제 호출 회피 위해 패치
        saved = _patch_git(repo)
        try:
            l1 = w.layer1_verify(repo, "d" * 40, "cto", "인프라", None, ledger)
        finally:
            _restore(saved)
        check("L1 실패(충돌)", l1["passed"] is False, str(l1))
        check("충돌 사유 포함", any("SSOT 충돌" in r for r in l1["reasons"]), str(l1["reasons"]))


def test_decision_matrix():
    print("[5] 판정 매트릭스")

    def run(status_done=True, commit_exists=True, fit=True, no_ai=False):
        with tempfile.TemporaryDirectory() as td:
            repo = _make_repo(Path(td), {
                "agent": "cto", "task_id": "T1",
                "status": "DONE" if status_done else "IN_PROGRESS",
                "title": "T", "artifact_url": None})
            saved = _patch_git(repo, commit_exists=commit_exists)
            w.ai_layer_verify = lambda ctx, no_ai=False, _f=fit: {
                "fit": _f, "reason": "r", "principle_check": "p"}
            tg = _StubTelegram()
            ledger = []
            try:
                res = w.process_commit(repo, "e" * 40, "[DONE][CTO][T1] x",
                                       "GM", ledger, tg, no_ai=no_ai, dry_run=False)
            finally:
                _restore(saved)
            return res, tg

    res, tg = run(fit=True)
    check("L1 pass + fit True = APPROVED", res["verdict"] == w.APPROVED, str(res))
    check("APPROVED 텔레그램 ✅", any("검증 통과" in m for m in tg.sent))

    res, _ = run(commit_exists=False, fit=True)
    check("L1 fail = REJECTED", res["verdict"] == w.REJECTED, str(res))

    res, _ = run(fit=False)
    check("fit False = REJECTED", res["verdict"] == w.REJECTED, str(res))

    res, tg = run(fit=None)
    check("fit None = AI_PENDING", res["verdict"] == w.AI_PENDING, str(res))
    check("AI_PENDING 텔레그램 ⏳", any("보류" in m for m in tg.sent))


def test_artifact_fail_rejected():
    """[6] artifact_url HTTP 비-200 → L1 fail → REJECTED"""
    print("[6] artifact_url 비-200 → REJECTED")
    with tempfile.TemporaryDirectory() as td:
        repo = _make_repo(Path(td), {
            "agent": "cto", "task_id": "인프라",
            "status": "DONE", "title": "T",
            "artifact_url": "https://example.com/artifact",
        })
        saved = _patch_git(repo)
        # Override http_ok to return non-200
        w.http_ok = lambda url, timeout=10: (False, "HTTP 404")
        w.ai_layer_verify = lambda ctx, no_ai=False: {"fit": True, "reason": "ok",
                                                      "principle_check": "ok"}
        tg = _StubTelegram()
        ledger = []
        try:
            res = w.process_commit(repo, "f" * 40, "[DONE][CTO][인프라] x",
                                   "GM", ledger, tg, no_ai=False, dry_run=False)
        finally:
            _restore(saved)
        check("artifact 실패 → REJECTED", res["verdict"] == w.REJECTED, str(res))
        check("L1 실패 사유 포함", any("artifact" in r for r in res["l1"]["reasons"]),
              str(res["l1"]["reasons"]))
        check("REJECTED 텔레그램 ❌", any("반려" in m for m in tg.sent))


def test_mismatch_then_resolve():
    """[7] MISMATCH 후 해소 — pass 1: 커서 정지; pass 2: status DONE → APPROVED"""
    print("[7] MISMATCH 후 해소 — pass 1 커서 정지, pass 2 APPROVED")
    import json as _json

    SHA_DONE = "d" * 40
    SHA_PREV = "0" * 40  # cursor before the DONE commit
    SHA_NORM = "1" * 40  # a normal commit before the DONE one (to confirm it advances)

    with tempfile.TemporaryDirectory() as td:
        repo = Path(td)

        # --- Pass 1: status = IN_PROGRESS (MISMATCH) ---
        _make_repo(repo, {"agent": "cto", "task_id": "인프라",
                          "status": "IN_PROGRESS", "title": "T",
                          "artifact_url": None})

        # Write cursor manually
        w.write_cursor(repo, SHA_PREV)

        saved = _patch_git(repo)
        w.ai_layer_verify = lambda ctx, no_ai=False: {"fit": True, "reason": "ok",
                                                      "principle_check": "ok"}

        # Stub git_fetch to succeed, git_head to return SHA_DONE,
        # git_new_commits to return one DONE commit
        w.git_fetch = lambda repo: True
        w.git_cursor_valid = lambda repo, sha: True
        w.git_new_commits = lambda repo, cursor: [(SHA_DONE, "[DONE][CTO][인프라] hotfix", "GM")]

        tg = _StubTelegram()
        try:
            counts = w.run_once(repo, tg, no_ai=True, dry_run=False)
        finally:
            _restore(saved)
            # restore run_once stubs
            w.git_fetch = _orig_git_fetch
            w.git_cursor_valid = _orig_git_cursor_valid
            w.git_new_commits = _orig_git_new_commits

        cursor_after_pass1 = w.read_cursor(repo)
        ledger_after_pass1 = w.read_ledger(repo)

        check("pass 1 mismatch 카운트=1", counts["mismatch"] == 1, str(counts))
        check("pass 1 커서 정지 (SHA_PREV 유지)", cursor_after_pass1 == SHA_PREV,
              f"cursor={cursor_after_pass1}")
        check("pass 1 ledger 비어있음", len(ledger_after_pass1) == 0, str(ledger_after_pass1))

        # --- Pass 2: flip status to DONE ---
        (repo / "status" / "cto.json").write_text(
            _json.dumps({"agent": "cto", "task_id": "인프라",
                         "status": "DONE", "title": "T", "artifact_url": None}),
            encoding="utf-8")

        saved2 = _patch_git(repo)
        w.ai_layer_verify = lambda ctx, no_ai=False: {"fit": True, "reason": "ok",
                                                      "principle_check": "ok"}
        w.git_fetch = lambda repo: True
        w.git_cursor_valid = lambda repo, sha: True
        w.git_new_commits = lambda repo, cursor: [(SHA_DONE, "[DONE][CTO][인프라] hotfix", "GM")]

        tg2 = _StubTelegram()
        try:
            counts2 = w.run_once(repo, tg2, no_ai=True, dry_run=False)
        finally:
            _restore(saved2)
            w.git_fetch = _orig_git_fetch
            w.git_cursor_valid = _orig_git_cursor_valid
            w.git_new_commits = _orig_git_new_commits

        cursor_after_pass2 = w.read_cursor(repo)
        ledger_after_pass2 = w.read_ledger(repo)

        check("pass 2 APPROVED 카운트=1", counts2["approved"] == 1, str(counts2))
        check("pass 2 커서 전진 (SHA_DONE)", cursor_after_pass2 == SHA_DONE,
              f"cursor={cursor_after_pass2}")
        check("pass 2 ledger 1건 APPROVED",
              len(ledger_after_pass2) == 1 and ledger_after_pass2[0]["verdict"] == w.APPROVED,
              str(ledger_after_pass2))


def test_crash_before_telegram_idempotency():
    """[8] ledger 기록 후 telegram 미발송 시뮬 → 재처리 패스에서 already_processed 스킵"""
    print("[8] crash-before-telegram 멱등성")
    with tempfile.TemporaryDirectory() as td:
        repo = _make_repo(Path(td), {"agent": "cto", "task_id": "인프라",
                                     "status": "DONE", "title": "T",
                                     "artifact_url": None})
        saved = _patch_git(repo)
        w.ai_layer_verify = lambda ctx, no_ai=False: {"fit": True, "reason": "ok",
                                                      "principle_check": "ok"}
        SHA = "a1b2c3" + "d" * 34

        # Simulate: ledger already has the record (written before telegram crash)
        ledger = [{
            "task_id": "인프라", "clevel": "CTO", "commit": SHA,
            "verdict": w.APPROVED, "processed_at": "2026-01-01T00:00:00+00:00",
        }]
        w.write_ledger(repo, ledger)

        tg = _StubTelegram()
        try:
            # Re-run process_commit with same SHA — should skip
            res = w.process_commit(repo, SHA, "[DONE][CTO][인프라] x",
                                   "GM", ledger, tg, no_ai=True, dry_run=False)
        finally:
            _restore(saved)

        check("재처리 스킵 (already_processed)", res.get("skipped") == "already_processed",
              str(res))
        check("텔레그램 발송 없음 (중복 ping 없음)", len(tg.sent) == 0, str(tg.sent))


def test_amend_rebase_blocked():
    """[9] task_id REJECTED under commit A → new commit B (same task_id) → terminal_decided 차단"""
    print("[9] amend/rebase 차단 — REJECTED 후 다른 SHA → terminal_decided")
    with tempfile.TemporaryDirectory() as td:
        repo = _make_repo(Path(td), {"agent": "cto", "task_id": "인프라",
                                     "status": "DONE", "title": "T",
                                     "artifact_url": None})
        saved = _patch_git(repo)
        w.ai_layer_verify = lambda ctx, no_ai=False: {"fit": True, "reason": "ok",
                                                      "principle_check": "ok"}

        SHA_A = "a" * 40
        SHA_B = "b" * 40

        # Pre-populate ledger: SHA_A was REJECTED
        ledger = [{
            "task_id": "인프라", "clevel": "CTO", "commit": SHA_A,
            "verdict": w.REJECTED, "processed_at": "2026-01-01T00:00:00+00:00",
        }]

        tg = _StubTelegram()
        try:
            res = w.process_commit(repo, SHA_B, "[DONE][CTO][인프라] amended",
                                   "GM", ledger, tg, no_ai=False, dry_run=False)
        finally:
            _restore(saved)

        check("amend 차단 = terminal_decided", res.get("skipped") == "terminal_decided", str(res))
        check("재처리 APPROVED 아님", res.get("verdict") != w.APPROVED, str(res))
        check("GM 텔레그램 차단 알림", any("재시도 차단" in m for m in tg.sent), str(tg.sent))
        check("ledger 변화 없음 (1건 유지)", len(ledger) == 1, str(ledger))


def run_selftest() -> bool:
    print("=" * 60)
    print("ceo_verify_watcher self-test")
    print("=" * 60)
    test_regex()
    test_dual_signal()
    test_idempotency()
    test_l1_dedup()
    test_decision_matrix()
    test_artifact_fail_rejected()
    test_crash_before_telegram_idempotency()
    test_amend_rebase_blocked()
    test_mismatch_then_resolve()
    print("=" * 60)
    print(f"결과: {_PASS} passed, {_FAIL} failed")
    print("=" * 60)
    return _FAIL == 0


if __name__ == "__main__":
    sys.exit(0 if run_selftest() else 1)
