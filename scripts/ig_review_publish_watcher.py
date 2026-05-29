"""인스타 검수 승인 → 자동 발행 감시기 (Phase 2, 2026-05-29)

흐름: 김남욱 페이지 검수 카드에서 GM이 [승인] → (역방향 중계가 큐에 status='승인' 기록)
      → 이 감시기가 승인 건을 발행 → status='발행완료'(+게시 URL)로 갱신 → 커밋/푸시 → 텔레그램 보고.

큐 파일(검수 카드와 공유): 3. 웰페리온 가이드/cmo/review/review_queue.json
  각 항목 필수: id, title, folder(콘텐츠 폴더 상대경로), status
  status: 검수대기 → 승인 → 발행완료 / 발행실패

실행:
  단발(Windows 예약작업 권장): python scripts\\ig_review_publish_watcher.py --once
  반복:                         python scripts\\ig_review_publish_watcher.py --interval 300
  발행 없이 로직만(테스트):      python scripts\\ig_review_publish_watcher.py --once --dry-run

발행은 instagram_upload_playwright.py --mode publish 를 그대로 호출(검증된 경로 재사용).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(r"C:\Users\jjky0\welperion-automation")
QUEUE = ROOT / "3. 웰페리온 가이드" / "cmo" / "review" / "review_queue.json"
PUBLISH_SCRIPT = ROOT / "scripts" / "instagram_upload_playwright.py"
PY = ROOT / ".venv" / "Scripts" / "python.exe"

APPROVED_STATES = {"승인", "승인발행대기", "approved"}
POST_URL_RE = re.compile(r"post\s+[A-C]:\s*(https?://\S+)", re.IGNORECASE)

TELEGRAM_TOKEN_ENV_KEY = "TELEGRAM_BOT_TOKEN"
TELEGRAM_CHAT_ID = "8254867551"  # @namuki_report_bot


# ----------------------------------------------------------------------
def telegram(message: str) -> None:
    """텔레그램 1줄 보고 — 토큰 stdout 노출 금지 (메모리 feedback_no_token_in_stdout)."""
    token = os.environ.get(TELEGRAM_TOKEN_ENV_KEY, "").strip()
    if not token:
        print("[WARN] 텔레그램 토큰 미설정 — 보고 생략")
        return
    try:
        import urllib.parse
        import urllib.request
        data = urllib.parse.urlencode({
            "chat_id": TELEGRAM_CHAT_ID, "text": message,
            "disable_web_page_preview": "true",
        }).encode("utf-8")
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage", data=data, method="POST")
        with urllib.request.urlopen(req, timeout=10) as resp:
            print(f"[INFO] 텔레그램 보고 {'성공' if resp.status == 200 else '실패'}")
    except Exception:
        print("[WARN] 텔레그램 보고 실패 (토큰 trace 노출 방지로 상세 미출력)")


def git(*args: str, check: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(ROOT), *args],
                          capture_output=True, text=True, check=check)


def pull_latest() -> None:
    """승인 신호 동기화 — dirty tree여도 autostash로 안전 rebase (메모리 git 원샷 원칙)."""
    git("fetch", "origin", "master")
    r = git("pull", "--rebase", "--autostash", "origin", "master")
    print(f"[INFO] git pull: {(r.stdout + r.stderr).strip().splitlines()[-1:] or ['(no output)']}")


def load_queue() -> list:
    if not QUEUE.exists():
        return []
    try:
        data = json.loads(QUEUE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception as e:
        print(f"[ERROR] 큐 파싱 실패: {e}")
        return []


def save_queue(items: list) -> None:
    QUEUE.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def publish_folder(folder: str) -> str | None:
    """발행 서브프로세스 실행 → 게시 URL 반환(실패 시 None)."""
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    proc = subprocess.run(
        [str(PY), str(PUBLISH_SCRIPT), "--mode", "publish", "--content-folder", folder],
        cwd=str(ROOT), capture_output=True, text=True, env=env, timeout=600)
    out = (proc.stdout or "") + (proc.stderr or "")
    print(out)
    m = POST_URL_RE.search(out)
    return m.group(1).rstrip("/") + "/" if m else None


def process_queue(items: list, dry_run: bool) -> tuple[list, list]:
    """승인 건 처리. (변경된 items, 이벤트 로그) 반환. dry_run이면 발행 안 함."""
    events: list[str] = []
    for it in items:
        if it.get("status") not in APPROVED_STATES:
            continue
        title = it.get("title", it.get("id", "?"))
        folder = it.get("folder")
        if not folder:
            it["status"] = "발행실패"
            it["note"] = "folder 필드 없음 — 발행 대상 폴더 미지정"
            events.append(f"⛔ {title}: folder 미지정")
            continue
        if dry_run:
            events.append(f"🔎 [dry-run] 발행 대상: {title} (folder={folder})")
            continue
        url = publish_folder(folder)
        if url:
            it["status"] = "발행완료"
            it["post_url"] = url
            it["published_at"] = datetime.now().isoformat(timespec="seconds")
            it.pop("note", None)
            events.append(f"✅ {title} 발행 완료 — {url}")
        else:
            it["status"] = "발행실패"
            it["note"] = "게시 URL 미회수 — 수동 점검 필요"
            events.append(f"⚠️ {title} 발행 실패 — 게시 URL 미회수")
    return items, events


def run_once(dry_run: bool) -> int:
    if not dry_run:
        pull_latest()
    items = load_queue()
    approved = [it for it in items if it.get("status") in APPROVED_STATES]
    if not approved:
        print("[INFO] 발행할 승인 건 없음.")
        return 0
    print(f"[INFO] 승인 건 {len(approved)}개 처리 시작 (dry_run={dry_run})")
    items, events = process_queue(items, dry_run)
    for e in events:
        print("  " + e)
    published = [e for e in events if e.startswith("✅")]
    if not dry_run and events:
        save_queue(items)
        git("add", str(QUEUE))
        git("commit", "-m", f"auto(cmo): 검수 승인 건 자동 발행 {len(published)}건")
        git("pull", "--rebase", "--autostash", "origin", "master")
        git("push", "origin", "master")
        telegram("📲 인스타 자동 발행 결과\n" + "\n".join(events))
    return len(published)


def main() -> None:
    p = argparse.ArgumentParser(description="인스타 검수 승인 → 자동 발행 감시기")
    p.add_argument("--once", action="store_true", help="단발 실행 (예약작업 권장)")
    p.add_argument("--interval", type=int, default=300, help="반복 주기(초), --once 없을 때")
    p.add_argument("--dry-run", action="store_true", help="발행 없이 로직만")
    args = p.parse_args()

    if args.once:
        run_once(args.dry_run)
        return
    print(f"[INFO] 감시기 시작 — {args.interval}s 주기 (Ctrl+C 종료)")
    while True:
        try:
            run_once(args.dry_run)
        except Exception as e:
            print(f"[ERROR] 사이클 예외: {e}")
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
