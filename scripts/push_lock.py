# -*- coding: utf-8 -*-
"""push_lock.py — 🔒 자물쇠 라인 판정 모듈 (배1098 · 시토 · 2026-09-07 · GM 지시).

GM 원문(웰리 창 10:3x): 「AWS 최신버전 외에 수정 및 데이터 이관 관련해서는 자물쇠라인이
하나 있어야 · 커밋 푸시 관련 나한테 승인을 당분간 받는 모듈」. 설계 정본 =
status/briefs/CTO-2026-09-07-배1098-자물쇠라인-설계.md(§7 웰리 수정 반영본이 최종).

정본 파일 2개(접수처 잠금 status/reception_freeze.json 과 같은 모양):
  status/push_lock.json      — locked·paths(잠글 경로 glob)·allow_globs·html_glob·
                                html_origin_markers. GM 만 손으로 푼다(AI 가 스스로 안 품).
  status/push_approvals.json — 요청 행(id·sha·branch·paths·summary·requester·status·
                                decided_at·decided_by).

단일 판정 함수 judge()/judge_tree_diff() 를 세 곳이 공유한다(약속 L21 — 새 가드 복제 금지):
  ① scripts/safe_commit.py    — 잠금 경로가 섞인 커밋을 master 대신 lock/<id> 브랜치로.
  ② .git/hooks/pre-push       — 맨손 git push 가 잠금 경로를 실은 채 master 로 가는 것 차단.
  ③ scripts/post_commit_push.py --sweep — 승인된 요청만 lock/<id> → master cherry-pick.

시험: python scripts/push_lock.py --selftest
"""
from __future__ import annotations

import fnmatch
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCK_PATH = ROOT / "status" / "push_lock.json"
APPROVALS_PATH = ROOT / "status" / "push_approvals.json"

KST = timezone(timedelta(hours=9))
_DRY_ENV = "PUSH_LOCK_DRY"
_GM_CHAT_ID = 8254867551  # ssot/canon_values.json 정본과 동일(notify_gm_progress.py 등 재사용 관례)


# ── 잠금 파일 읽기/판정 ──────────────────────────────────────────────────────
def load_lock() -> dict:
    try:
        with open(LOCK_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def is_locked(d: dict | None = None) -> bool:
    d = d if d is not None else load_lock()
    return bool(d.get("locked"))


def _glob_match(path: str, pattern: str) -> bool:
    """ponytail: fnmatch 하나로 prefix·glob·"**" 전부 처리한다(별도 경로 파서 없음) —
    fnmatch 의 '*' 는 '/' 도 그대로 집어삼키므로 "server/**"·"server/*" 둘 다 동일하게
    "server/ 아래 전부"로 매치된다. 새 글롭 엔진을 안 만든다(약속 L21)."""
    q = path.replace("\\", "/")
    p = pattern.replace("\\", "/").replace("**", "*")
    return q == pattern.rstrip("/") or fnmatch.fnmatchcase(q, p) or (
        p.endswith("/") and q.startswith(p)
    )


def judge(changed_paths: list[str], root: Path | None = None, get_diff=None,
          lock: dict | None = None) -> list[str]:
    """changed_paths(이번 커밋/푸시로 바뀐 경로 전부, 상태 무관) 중 잠금에 걸리는 것만.

    get_diff: callable(path) -> 유니파이드 diff 텍스트(옵션). html_glob 예외 판정에만 쓴다
    — 화면 문구 수정까지 잠그면 실무진 화면이 멈추므로(설계 §2), 원천 전환 마커가 그 diff
    에 추가/삭제되는 커밋만 잠근다. get_diff 를 안 주면 확인 불가 = 안전하게 잠근다(fail-safe).
    """
    lock = lock if lock is not None else load_lock()
    if not is_locked(lock):
        return []
    lock_globs = lock.get("paths") or []
    allow_globs = lock.get("allow_globs") or []
    html_glob = lock.get("html_glob") or ""
    markers = lock.get("html_origin_markers") or []
    hits: list[str] = []
    for p in changed_paths:
        if any(_glob_match(p, g) for g in allow_globs):
            continue
        if html_glob and _glob_match(p, html_glob):
            if get_diff is None:
                hits.append(p)
                continue
            text = get_diff(p) or ""
            changed_lines = [ln for ln in text.splitlines()
                              if ln[:1] in "+-" and ln[:3] not in ("+++", "---")]
            if any(m in ln for ln in changed_lines for m in markers):
                hits.append(p)
            continue
        if any(_glob_match(p, g) for g in lock_globs):
            hits.append(p)
    return sorted(set(hits))


def judge_tree_diff(head_tree: str, tree: str, root: Path, lock: dict | None = None) -> list[str]:
    """safe_commit 용 편의 함수 — 트리 두 개(head_tree·tree)만 주면 변경 경로·html diff 를
    직접 계산해 judge() 를 부른다. head_tree==tree(빈 diff)면 즉시 빈 리스트."""
    if head_tree == tree:
        return []
    out = subprocess.run(
        ["git", "-C", str(root), "-c", "core.quotepath=false",
         "diff-tree", "--no-commit-id", "--name-only", "-r", head_tree, tree],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    paths = [p for p in out.stdout.splitlines() if p.strip()]

    def _get_diff(path: str) -> str:
        r = subprocess.run(
            ["git", "-C", str(root), "-c", "core.quotepath=false",
             "diff", "--unified=0", head_tree, tree, "--", path],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        return r.stdout

    return judge(paths, root=root, get_diff=_get_diff, lock=lock)


# ── 승인 요청 원장 ───────────────────────────────────────────────────────────
def load_approvals() -> dict:
    try:
        with open(APPROVALS_PATH, encoding="utf-8") as f:
            d = json.load(f)
        d.setdefault("requests", [])
        return d
    except Exception:
        return {"requests": []}


def save_approvals(d: dict) -> None:
    APPROVALS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(APPROVALS_PATH, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)


def _next_id(d: dict, now: datetime) -> str:
    today = now.strftime("%Y%m%d")
    n = sum(1 for r in d["requests"] if str(r.get("id", "")).startswith(f"PL-{today}-")) + 1
    return f"PL-{today}-{n:02d}"


def make_request(paths: list[str], sha: str, summary: str, requester: str,
                  root: Path | None = None, now: datetime | None = None) -> dict:
    """요청 행을 만들어 push_approvals.json 에 적고 그대로 반환한다.

    # ponytail: read-modify-write 에 파일락이 없다 — 잠금 경로가 섞인 커밋은 하루에 흔치
    # 않으므로 동시 요청 경합 위험은 낮게 잡았다. 부딪히면 queue_lock 을 재사용해 감쌀 것.
    """
    now = now or datetime.now(KST)
    d = load_approvals()
    req_id = _next_id(d, now)
    req = {
        "id": req_id, "sha": sha, "branch": f"lock/{req_id}",
        "paths": paths, "summary": summary, "requester": requester,
        "created_at": now.strftime("%Y-%m-%d %H:%M"),
        "status": "pending", "decided_at": "", "decided_by": "",
    }
    d["requests"].append(req)
    save_approvals(d)
    return req


def decide(req_id: str, status: str, decided_by: str, now: datetime | None = None) -> tuple[bool, dict | None]:
    """텔레그램 카드 콜백이 부른다 — status 만 approved/rejected 로 바꾼다(무거운 git 작업은
    scripts/post_commit_push.py --sweep 이 한다 · 약속 L21)."""
    now = now or datetime.now(KST)
    d = load_approvals()
    for r in d["requests"]:
        if r.get("id") == req_id and r.get("status") == "pending":
            r["status"] = status
            r["decided_at"] = now.strftime("%Y-%m-%d %H:%M")
            r["decided_by"] = decided_by
            save_approvals(d)
            return True, r
    return False, None


def pending_by_status(status: str) -> list[dict]:
    return [r for r in load_approvals()["requests"] if r.get("status") == status]


# ── GM 승인 카드 발송(telegram_bot/.env 직독 — bot.py 이벤트 루프 밖에서도 동작) ────────
def _bot_token() -> str:
    env_path = ROOT / "telegram_bot" / ".env"
    try:
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("TELEGRAM_BOT_TOKEN="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    except Exception:
        pass
    return ""


def send_approval_card(req: dict, dry_run: bool = False) -> bool:
    """GM 개인 봇방에 [승인]/[반려] 인라인 카드 1장. dry_run 이나 env PUSH_LOCK_DRY=1 이면
    발송 없이 로그만(배1098 자체 시험 요구사항 §7)."""
    if dry_run or os.environ.get(_DRY_ENV) == "1":
        print(f"[dry-run] 승인 카드 발송 생략 — {req['id']} ({req['branch']})")
        return True
    token = _bot_token()
    if not token:
        print(f"[WARN] TELEGRAM_BOT_TOKEN 없음 — 승인 카드 미발송 {req['id']}")
        return False
    paths = req.get("paths") or []
    extra_n = f" 외 {len(paths) - 1}건" if len(paths) > 1 else ""
    text = (
        f"🔒 커밋·푸시 승인 요청 {req['id']}\n"
        f"요청자 : {req.get('requester', '')}\n"
        f"경로 : {paths[0] if paths else ''}{extra_n}\n"
        f"요약 : {str(req.get('summary', ''))[:200]}\n\n"
        "[✅ 승인]하면 다음 스위퍼 주기(5분 내)에 master 로 올라갑니다. [⛔ 반려]하면 브랜치를 지웁니다."
    )
    markup = {
        "inline_keyboard": [[
            {"text": "✅ 승인", "callback_data": f"plk:{req['id']}:a"},
            {"text": "⛔ 반려", "callback_data": f"plk:{req['id']}:r"},
        ]]
    }
    try:
        sys.path.insert(0, str(ROOT / "scripts"))
        from tg_outbound_log import send as _tg_send
        return bool(_tg_send(
            token, _GM_CHAT_ID, text, source="push_lock.send_approval_card",
            extra={"reply_markup": json.dumps(markup)}, timeout=15,
        ))
    except Exception as exc:
        print(f"[WARN] 승인 카드 발송 실패: {type(exc).__name__}: {exc}")
        return False


# ── 자체 시험(§7 ③ judge 단위 assert) ────────────────────────────────────────
def _selftest() -> None:
    lock = {
        "locked": True,
        "paths": ["server/**", "scripts/sync_*.py", ".deploy-*/**", "ssot/**",
                  "status/origin_switch*.json"],
        "allow_globs": ["ssot/incidents.json"],
        "html_glob": "3. 웰페리온 가이드/**/*.html",
        "html_origin_markers": ["script.google.com/macros", "/api/", "apiFirst", "ERP_API_ON"],
    }
    assert judge(["server/erp_api/main.py"], lock=lock) == ["server/erp_api/main.py"]
    assert judge(["scripts/sync_members.py"], lock=lock) == ["scripts/sync_members.py"]
    assert judge([".deploy-todo/업무&결재 현황.js"], lock=lock) == [".deploy-todo/업무&결재 현황.js"]
    assert judge(["ssot/canon_values.json"], lock=lock) == ["ssot/canon_values.json"]
    # allow_globs 제외 확인
    assert judge(["ssot/incidents.json"], lock=lock) == []
    # 잠금 밖 경로는 통과
    assert judge(["status/worklog.jsonl"], lock=lock) == []
    # html: get_diff 없으면 안전하게 잠금
    html_path = "3. 웰페리온 가이드/public/ko/x.html"
    assert judge([html_path], lock=lock) == [html_path]
    # html: 마커 없는 diff → 통과
    assert judge([html_path], lock=lock, get_diff=lambda p: "+<p>문구만 수정</p>") == []
    # html: 마커가 추가되는 diff → 잠금
    assert judge([html_path], lock=lock,
                  get_diff=lambda p: "+fetch('/api/members')") == [html_path]
    # locked=False 면 전부 통과
    off = dict(lock, locked=False)
    assert judge(["server/erp_api/main.py"], lock=off) == []
    print("[selftest] push_lock.judge OK (9케이스)")


_PUSH_TARGET_REF = "refs/heads/master"
_ZERO_SHA = "0" * 40


def check_push(remote_ref: str, remote_sha: str, local_sha: str) -> int:
    """.git/hooks/pre-push 본체(scripts/pre-push.hook 이 호출) — 맨손 git push 가 잠금
    경로를 실은 채 master 로 가는 것만 막는다. lock/<id> 브랜치 자체의 push(승인 흐름의
    일부 — 스위퍼가 만든다)는 대상 밖이라 통과한다. 반환 0=통과 · 1=차단."""
    if remote_ref != _PUSH_TARGET_REF or remote_sha == _ZERO_SHA or not is_locked():
        return 0
    hits = judge_tree_diff(f"{remote_sha}^{{tree}}", f"{local_sha}^{{tree}}", ROOT)
    if not hits:
        return 0
    approvals = load_approvals()["requests"]
    covered = {p for r in approvals if r.get("status") in ("approved", "pushed")
               for p in (r.get("paths") or [])}
    uncovered = [h for h in hits if h not in covered]
    if not uncovered:
        return 0
    extra = f" 외 {len(uncovered) - 5}건" if len(uncovered) > 5 else ""
    print("[자물쇠 차단] GM 승인 없이 잠금 경로를 master 로 push 할 수 없습니다.", file=sys.stderr)
    print(f"  막힌 경로: {', '.join(uncovered[:5])}{extra}", file=sys.stderr)
    print("  scripts/safe_commit.py 로 커밋하면 lock/<id> 브랜치 + GM 승인 카드가 자동으로 나갑니다.",
          file=sys.stderr)
    return 1


def main() -> int:
    if "--selftest" in sys.argv:
        _selftest()
        return 0
    if "--check-push" in sys.argv:
        i = sys.argv.index("--check-push")
        remote_ref, remote_sha, local_sha = sys.argv[i + 1], sys.argv[i + 2], sys.argv[i + 3]
        return check_push(remote_ref, remote_sha, local_sha)
    print(json.dumps({"is_locked": is_locked(), "pending": len(pending_by_status("pending"))},
                      ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
