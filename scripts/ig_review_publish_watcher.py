"""검수 승인 → 자동 발행 감시기 (멀티채널 v2, 2026-06-02)

흐름: 김남욱 페이지 검수 카드에서 GM이 [승인] → (역방향 중계가 큐에 status='승인' 기록)
      → 이 감시기가 채널별 분기 발행 → status 갱신 → 커밋/푸시 → 텔레그램 보고.

큐 파일(검수 카드와 공유): 3. 웰페리온 가이드/cmo/review/review_queue.json
  각 항목 필수: id, title, folder(콘텐츠 폴더 상대경로), status
  채널 분기용: channel (예: "인스타그램", "블로그", "카페", "카카오", "당근")
  status: 검수대기 → 승인 → 발행완료 / 발행실패 / 수동발행대기

실행:
  단발(Windows 예약작업 권장): python scripts\\ig_review_publish_watcher.py --once
  반복:                         python scripts\\ig_review_publish_watcher.py --interval 300
  발행 없이 로직만(테스트):      python scripts\\ig_review_publish_watcher.py --once --dry-run

채널 분기 정책:
  블로그 → naver_blog_upload_playwright.py --mode draft (임시저장, exit 0 = 완료)
  카페   → cafe_upload_playwright.py --mode draft (임시저장, exit 0 = 완료)
  ※ GM 정책(2026-06-05): 승인=임시저장까지만, 최종 게시는 GM 수동(시모 임시저장→GM 게시).
  카카오·당근 → 자동발행 안 함, 텔레그램 수동 업로드 알림 + status='수동발행대기'
  나머지(인스타 등) → instagram_upload_playwright.py --mode publish (기존 경로 유지)
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
BLOG_SCRIPT = ROOT / "scripts" / "naver_blog_upload_playwright.py"   # 블로그 발행 스크립트
CAFE_SCRIPT = ROOT / "scripts" / "cafe_upload_playwright.py"          # 카페 발행 스크립트
DANGGN_SCRIPT = ROOT / "scripts" / "danggn_upload_playwright.py"      # 당근 반자동(자동입력+임시저장)
PY = ROOT / ".venv" / "Scripts" / "python.exe"
NOTIFIED_FILE = ROOT / "scripts" / ".review_notified.json"  # 검수대기 알림 발송 이력
CARD_MSGID_STORE = ROOT / "scripts" / ".review_card_msgids.json"  # send_review_card 가 카드 보낸 id 저장

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


def load_notified() -> set:
    """이미 검수대기 알림을 발송한 id 집합 로드."""
    if not NOTIFIED_FILE.exists():
        return set()
    try:
        data = json.loads(NOTIFIED_FILE.read_text(encoding="utf-8"))
        return set(data) if isinstance(data, list) else set()
    except Exception:
        return set()


def save_notified(notified: set) -> None:
    """검수대기 알림 발송 이력 저장."""
    NOTIFIED_FILE.write_text(
        json.dumps(sorted(notified), ensure_ascii=False, indent=2), encoding="utf-8"
    )


def load_carded() -> set:
    """send_review_card 가 인라인 카드를 이미 보낸 id 집합. 카드=알림이므로 중복 텍스트 알림 억제."""
    if not CARD_MSGID_STORE.exists():
        return set()
    try:
        data = json.loads(CARD_MSGID_STORE.read_text(encoding="utf-8"))
        return set(data.keys()) if isinstance(data, dict) else set()
    except Exception:
        return set()


def notify_pending_review(items: list) -> None:
    """검수대기 항목 중 아직 알림 안 보낸 건만 텔레그램 발송 후 이력 기록.
    단, 이미 검수카드(인라인 버튼)를 보낸 id 는 건너뜀 — 중복 알림이 텔레그램을 복잡하게 만듦(GM 2026-06-05)."""
    notified = load_notified()
    carded = load_carded()
    newly_notified: list[str] = []
    for it in items:
        if it.get("status") != "검수대기":
            continue
        item_id = it.get("id", "")
        if not item_id or item_id in notified or item_id in carded:
            continue
        title = it.get("title", item_id)
        channel = it.get("channel", "")
        msg = (
            f"🔎 검수 대기 등록\n"
            f"{title} ({channel}) — 가이드허브 M5에서 미리보기·승인\n"
            f"https://wellperion-cao.github.io/wellperion-automation/wellperion_guide(main).html#M5"
        )
        telegram(msg)
        newly_notified.append(item_id)
        print(f"[INFO] 검수대기 알림 발송: {item_id}")
    if newly_notified:
        notified.update(newly_notified)
        save_notified(notified)


def git(*args: str, check: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(ROOT), *args],
                          capture_output=True, text=True,
                          encoding="utf-8", errors="replace", check=check)


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


def publish_item(it: dict) -> tuple[str | None, int]:
    """발행 서브프로세스 실행 → (게시 URL|None, exit code) 반환.
    it 에서 folder / location / mentions / account / collaborators 를 추출해 발행기에 CLI 인자로 전달."""
    folder: str = it.get("folder", "")
    location: str = it.get("location", "").strip()
    account: str = it.get("account", "").strip()

    raw_mentions = it.get("mentions", [])
    # mentions 는 리스트 또는 콤마 문자열 모두 허용
    if isinstance(raw_mentions, list):
        mentions_str = ",".join(m.strip() for m in raw_mentions if m.strip())
    else:
        mentions_str = str(raw_mentions).strip()

    raw_collaborators = it.get("collaborators", [])
    # collaborators 는 리스트 또는 콤마 문자열 모두 허용
    if isinstance(raw_collaborators, list):
        collab_str = ",".join(c.strip() for c in raw_collaborators if c.strip())
    else:
        collab_str = str(raw_collaborators).strip()

    cmd = [str(PY), str(PUBLISH_SCRIPT), "--mode", "publish", "--content-folder", folder]
    if account:
        cmd += ["--account", account]
    if location:
        cmd += ["--location", location]
    if mentions_str:
        cmd += ["--mentions", mentions_str]
    if collab_str:
        cmd += ["--collaborators", collab_str]

    # 입력 단일화 (2026-06-04) — 큐의 caption 을 임시파일로 발행기에 전달.
    # 콘텐츠 폴더에 큐레이션_추천.md 가 없어도 review_queue.caption 으로 발행 가능
    # → '큐레이션 누락' FileNotFoundError 즉사 재발방지(오늘 실패 원인 #1).
    # 폴더에 큐레이션_추천.md 가 있으면 발행기가 그쪽을 우선 사용(이 파일 무시).
    caption_text: str = it.get("caption", "") or ""
    caption_tmp: Path | None = None
    if caption_text.strip():
        try:
            import tempfile
            fd, tmp_name = tempfile.mkstemp(prefix="ig_caption_", suffix=".txt")
            os.close(fd)
            caption_tmp = Path(tmp_name)
            caption_tmp.write_text(caption_text, encoding="utf-8")
            cmd += ["--caption-file", str(caption_tmp)]
        except Exception as exc:
            print(f"[WARN] caption 임시파일 생성 실패(큐레이션 md 폴백 의존): {exc}")
            caption_tmp = None

    try:
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True,
                              encoding="utf-8", errors="replace", env=env, timeout=600)
    finally:
        if caption_tmp is not None:
            try:
                caption_tmp.unlink()
            except Exception:
                pass
    out = (proc.stdout or "") + (proc.stderr or "")
    print(out)
    m = POST_URL_RE.search(out)
    url = m.group(1).rstrip("/") + "/" if m else None
    return url, proc.returncode


def publish_blog(it: dict) -> tuple[bool, str | None]:
    """블로그 발행 서브프로세스 실행.
    exit code 0 이면 발행완료로 간주 (네이버 URL 회수 불안정 — feedback_blog_cafe_drafts_terminal).
    반환: (성공여부, url|None)
    """
    cmd = [
        str(PY), str(BLOG_SCRIPT),
        "--mode", "draft",
        "--title", it["title"],
        "--body-file", str(ROOT / it["body_file"]),
        "--image-dir", str(ROOT / it["image_dir"]),
        "--sticker-count", "0",  # 하이엔드 브랜드 — GIF 스티커 자동삽입 금지(본문 깨짐 방지, GM 2026-06-05)
        "--i-am-sure",
    ]
    # image_glob 필드가 있으면 추가
    if it.get("image_glob"):
        cmd += ["--image-glob", it["image_glob"]]
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", env=env, timeout=600)
    out = (proc.stdout or "") + (proc.stderr or "")
    print(out)
    m = POST_URL_RE.search(out)
    url = m.group(1).rstrip("/") + "/" if m else None
    # exit code 0 이면 URL 미회수여도 발행완료
    success = (proc.returncode == 0)
    return success, url


def publish_cafe(it: dict) -> tuple[bool, str | None]:
    """카페 발행 서브프로세스 실행.
    exit code 0 이면 발행완료로 간주 (URL 회수 불안정 동일 정책).
    반환: (성공여부, url|None)
    """
    cmd = [
        str(PY), str(CAFE_SCRIPT),
        "--mode", "draft",
        "--title", it["title"],
        "--body-file", str(ROOT / it["body_file"]),
        "--image-dir", str(ROOT / it["image_dir"]),
        "--sticker-count", "0",  # 하이엔드 브랜드 — GIF 스티커 자동삽입 금지(본문 깨짐 방지, GM 2026-06-05)
        "--i-am-sure",
    ]
    # menuid 필드가 있으면 추가
    if it.get("menuid"):
        cmd += ["--menuid", str(it["menuid"])]
    # image_glob 필드가 있으면 추가
    if it.get("image_glob"):
        cmd += ["--image-glob", it["image_glob"]]
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", env=env, timeout=600)
    out = (proc.stdout or "") + (proc.stderr or "")
    print(out)
    m = POST_URL_RE.search(out)
    url = m.group(1).rstrip("/") + "/" if m else None
    # exit code 0 이면 URL 미회수여도 발행완료
    success = (proc.returncode == 0)
    return success, url


def publish_danggn(it: dict) -> tuple[bool, str]:
    """당근 반자동 임시저장 (자동입력+임시저장). danggn_upload_playwright.py --mode draft.
    당근은 당일 QR 로그인 세션 필요 — 세션 만료(exit 5)면 (False, '세션만료')로 폴백.
    반환: (성공여부, 사유). 이미지 첨부는 GM 수동(반자동 — 2026-06-04 WJO 선례)."""
    folder = it.get("folder", "")
    cmd = [
        str(PY), str(DANGGN_SCRIPT),
        "--mode", "draft",
        "--content-dir", folder,
    ]
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    try:
        proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True,
                              encoding="utf-8", errors="replace", env=env, timeout=600)
    except Exception as exc:
        return False, f"실행예외:{exc}"
    print((proc.stdout or "") + (proc.stderr or ""))
    if proc.returncode == 0:
        return True, "ok"
    if proc.returncode == 5:
        return False, "세션만료"  # 당일 QR 로그인 필요
    return False, f"exit={proc.returncode}"


def dispatch_publish(it: dict, events: list) -> None:
    """채널 분기 발행 디스패처.

    ch(channel 필드) 기준:
      블로그 → publish_blog (exit 0 = 완료, URL 있으면 기록)
      카페   → publish_cafe (exit 0 = 완료, URL 있으면 기록)
      카카오·당근 → 자동발행 안 함, 텔레그램 수동 알림 + status='수동발행대기'
      나머지(인스타 등) → 기존 publish_item (URL 회수 필수)

    it 딕셔너리를 직접 변경(status, post_url, published_at, note).
    events 리스트에 결과 문자열 추가.
    """
    title = it.get("title", it.get("id", "?"))
    ch = it.get("channel", "")

    if "블로그" in ch:
        # 블로그 자동 임시저장 (GM 정책: 승인=임시저장, 최종 게시는 GM 수동)
        success, url = publish_blog(it)
        if success:
            it["status"] = "임시저장"
            if url:
                it["post_url"] = url
            it["published_at"] = datetime.now().isoformat(timespec="seconds")
            it.pop("note", None)
            events.append(f"✅ {title} 블로그 임시저장 완료 — GM 최종 게시 대기")
        else:
            it["status"] = "임시저장실패"
            it["note"] = "블로그 임시저장 스크립트 exit≠0"
            events.append(f"⚠️ {title} 블로그 임시저장 실패 — exit code 비정상")

    elif "카페" in ch:
        # 카페 자동 임시저장 (GM 정책: 승인=임시저장, 최종 게시는 GM 수동)
        success, url = publish_cafe(it)
        if success:
            it["status"] = "임시저장"
            if url:
                it["post_url"] = url
            it["published_at"] = datetime.now().isoformat(timespec="seconds")
            it.pop("note", None)
            events.append(f"✅ {title} 카페 임시저장 완료 — GM 최종 게시 대기")
        else:
            it["status"] = "임시저장실패"
            it["note"] = "카페 임시저장 스크립트 exit≠0"
            events.append(f"⚠️ {title} 카페 임시저장 실패 — exit code 비정상")

    elif "당근" in ch:
        # 당근 반자동 — 자동입력+임시저장(이미지는 GM 수동 첨부, 2026-06-04 WJO 선례).
        # 당일 QR 로그인 세션 필요 — 세션 만료 시 기존 수동 알림으로 안전 폴백.
        ok, reason = publish_danggn(it)
        folder = it.get("folder", "(폴더 미지정)")
        if ok:
            it["status"] = "임시저장"
            it["published_at"] = datetime.now().isoformat(timespec="seconds")
            it["note"] = "당근 글 자동입력+임시저장 완료 — GM 이미지 첨부 후 게시"
            events.append(f"✅ {title} 당근 임시저장 완료 — GM 이미지 첨부·게시 대기")
        else:
            it["status"] = "수동발행대기"
            it["note"] = f"당근 자동 임시저장 실패({reason}) — 수동 업로드 필요"
            telegram(
                f"📦 [당근채널] 승인됨 — 수동 업로드 필요({reason})\n"
                f"폴더: {folder}\n본문: {it.get('body_file','(본문파일 미지정)')}"
            )
            events.append(f"📦 {title}: 당근 수동 업로드 대기(GM) — {reason}")

    elif "카카오" in ch:
        # 카카오 채널 — 자동 입력 스크립트 미구현, 수동 업로드 알림만
        folder = it.get("folder", "(폴더 미지정)")
        body_file = it.get("body_file", "(본문파일 미지정)")
        telegram(
            f"📦 [카카오 채널] 승인됨 — 수동 업로드 필요\n"
            f"폴더: {folder}\n본문: {body_file}"
        )
        it["status"] = "수동발행대기"
        it.pop("note", None)
        events.append(f"📦 {title}: 카카오 수동 업로드 대기(GM)")

    else:
        # 기존 IG 경로 — publish_item 결과(URL, exit code) 기준으로 성공 판정
        url, rc = publish_item(it)
        if url:
            it["status"] = "발행완료"
            it["post_url"] = url
            it["published_at"] = datetime.now().isoformat(timespec="seconds")
            it.pop("note", None)
            events.append(f"✅ {title} 발행 완료 — {url}")
        elif rc == 9:
            # (FIX2) 확인필요 — 성공 토스트는 떴으나 그리드 신규 shortcode 윈도우 내 미확정.
            # 발행됐을 가능성 높음 → '발행실패' 단정·자동 재발행 금지(중복 방지). GM 수동 URL 확인.
            it["status"] = "확인필요"
            it["note"] = "발행됐을 가능성 높음(검증 캐시지연) — 게시물 직접 확인 후 발행완료/재승인 결정. 자동 재발행 안 함."
            events.append(f"🔎 {title}: 발행 확인필요 — URL 수동확인(중복발행 금지)")
        else:
            it["status"] = "발행실패"
            it["note"] = "게시 URL 미회수 — 수동 점검 필요"
            events.append(f"⚠️ {title} 발행 실패 — 게시 URL 미회수")


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
            ch_info = it.get("channel", "")
            location_info = it.get("location", "")
            mentions_info = it.get("mentions", [])
            events.append(
                f"🔎 [dry-run] 발행 대상: {title} (folder={folder}"
                + (f", channel={ch_info!r}" if ch_info else "")
                + (f", location={location_info!r}" if location_info else "")
                + (f", mentions={mentions_info}" if mentions_info else "")
                + ")"
            )
            continue
        # 채널 분기 디스패처 — IG/블로그/카페/카카오·당근 분기 처리
        dispatch_publish(it, events)
    return items, events


def run_once(dry_run: bool) -> int:
    if not dry_run:
        pull_latest()
    items = load_queue()
    # 검수대기 신규 항목 텔레그램 알림 (중복 방지 이력 기반)
    notify_pending_review(items)
    approved = [it for it in items if it.get("status") in APPROVED_STATES]
    if not approved:
        print("[INFO] 발행할 승인 건 없음.")
        return 0
    print(f"[INFO] 승인 건 {len(approved)}개 처리 시작 (dry_run={dry_run})")
    items, events = process_queue(items, dry_run)
    for e in events:
        print("  " + e)
    published = [e for e in events if e.startswith("✅")]
    manual = [e for e in events if e.startswith("📦")]
    if not dry_run and events:
        save_queue(items)
        git("add", str(QUEUE))
        git("commit", "-m", f"auto(cmo): 검수 승인 건 발행 {len(published)}건 / 수동대기 {len(manual)}건")
        git("pull", "--rebase", "--autostash", "origin", "master")
        git("push", "origin", "master")
        telegram("📲 멀티채널 발행 결과\n" + "\n".join(events))
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
