#!/usr/bin/env python3
"""발행완료 → GM 텔레그램 링크 자동 알림 (2026-06-26)

CLI:
  --folder "<folder 경로 일부>"  특정 콘텐츠 1건 (folder 부분일치, 발행 직후 호출용)
  --today                       published_at 가 오늘(KST)인 발행완료 건 롤업
  --since YYYY-MM-DD            해당 날짜 이후 발행완료 건 묶음 전송
  --dry-run                     전송 없이 메시지 stdout 출력 (검증용)

그룹 키 = folder 필드(없으면 id). 콘텐츠별 1회 메시지.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(r"C:\Users\jjky0\welperion-automation")
QUEUE = ROOT / "3. 웰페리온 가이드" / "cmo" / "review" / "review_queue.json"
ENV_FILE = ROOT / "telegram_bot" / ".env"

KST = timezone(timedelta(hours=9))


# ---------------------------------------------------------------------------
# .env 로더 (python-dotenv 불필요, KEY=VALUE / # 주석)
# ---------------------------------------------------------------------------
def _load_env(key: str) -> str:
    val = os.environ.get(key, "").strip()
    if val:
        return val
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            if k.strip() == key:
                return v.strip().strip('"').strip("'")
    return ""


# ---------------------------------------------------------------------------
# 날짜 파싱 (datetime / date 혼재 → 앞 10자)
# ---------------------------------------------------------------------------
def _date_str(published_at: str) -> str:
    """'2026-06-26T07:53:14+09:00' 또는 '2026-06-26' → '2026-06-26'"""
    return str(published_at).strip()[:10] if published_at else ""


def _today_kst() -> str:
    return datetime.now(tz=KST).strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# 필터링
# ---------------------------------------------------------------------------
def _filter(items: list[dict], folder: str | None, today: bool, since: str | None) -> list[dict]:
    today_str = _today_kst() if today else ""
    result = []
    for it in items:
        if it.get("status") != "발행완료":
            continue
        if folder is not None:
            if folder not in (it.get("folder") or ""):
                continue
        elif today:
            if _date_str(it.get("published_at", "")) != today_str:
                continue
        elif since is not None:
            d = _date_str(it.get("published_at", ""))
            if not d or d < since:
                continue
        result.append(it)
    return result


# ---------------------------------------------------------------------------
# 그룹화 (folder 기준, 없으면 id)
# ---------------------------------------------------------------------------
def _group(items: list[dict]) -> dict[str, list[dict]]:
    groups: dict[str, list[dict]] = {}
    for it in items:
        key = (it.get("folder") or it.get("id") or "unknown").strip()
        groups.setdefault(key, []).append(it)
    return groups


# ---------------------------------------------------------------------------
# 메시지 포맷
# ---------------------------------------------------------------------------
def _representative_title(group: list[dict]) -> str:
    """그룹 대표 제목: ' — ' 앞 공통 부분 or 첫 항목 전체 제목."""
    titles = [it.get("title", "") for it in group if it.get("title")]
    if not titles:
        return group[0].get("id", "(제목 없음)") if group else "(제목 없음)"
    bases = [t.split(" — ")[0].strip() for t in titles]
    uniq = list(dict.fromkeys(b for b in bases if b))
    return uniq[0] if len(uniq) == 1 else titles[0]


def _format_message(group: list[dict]) -> str:
    title = _representative_title(group)
    lines = [f"📲 발행 링크 모음", f"📌 {title}"]
    for it in group:
        ch = it.get("channel") or "채널 미지정"
        url = (it.get("post_url") or "").strip()
        if url:
            lines.append(f"• {ch}: {url}")
        else:
            lines.append(f"• {ch}: 발행완료 ✅ (URL 미회수)")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 5채널 요약 메시지 (📢 형식 — 채널별 이모지)
# ---------------------------------------------------------------------------
_CHANNEL_EMOJI: dict[str, str] = {
    "인스타그램": "📷",
    "카카오": "💬",
    "당근": "🥕",
    "블로그": "📝",
    "카페": "📝",
}

# 채널 출력 순서 고정: IG → 카카오 → 당근 → 블로그 → 카페
_CHANNEL_ORDER = ["인스타그램", "카카오", "당근", "블로그", "카페"]


def _channel_emoji(channel: str) -> str:
    for key, emoji in _CHANNEL_EMOJI.items():
        if key in channel:
            return emoji
    return "📄"


def _format_summary_message(group: list[dict]) -> str:
    """📢 5채널 발행 완료 요약 형식 (review_queue post_url 자동 수집)."""
    title = _representative_title(group)
    n = len(group)
    lines = [f"📢 {title} — {n}채널 발행 완료", ""]
    ordered = sorted(
        group,
        key=lambda it: next(
            (i for i, k in enumerate(_CHANNEL_ORDER) if k in (it.get("channel") or "")),
            len(_CHANNEL_ORDER),
        ),
    )
    for it in ordered:
        ch = it.get("channel") or "채널 미지정"
        url = (it.get("post_url") or "").strip()
        em = _channel_emoji(ch)
        if url:
            lines.append(f"{em} {ch}  {url}")
        else:
            lines.append(f"{em} {ch}  (URL 미회수)")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 텔레그램 전송
# ---------------------------------------------------------------------------
def _send(token: str, chat_id: str, text: str) -> bool:
    try:
        data = urllib.parse.urlencode({
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": "true",
        }).encode("utf-8")
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=data,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except Exception as exc:
        print(f"[WARN] 텔레그램 전송 실패: {exc}", file=sys.stderr)
        return False


# ---------------------------------------------------------------------------
# 실행 엔트리
# ---------------------------------------------------------------------------
def run(folder: str | None, today: bool, since: str | None, dry_run: bool, summary: bool = False) -> int:
    try:
        items: list[dict] = json.loads(QUEUE.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"[ERROR] 큐 읽기 실패: {exc}", file=sys.stderr)
        return 1

    filtered = _filter(items, folder, today, since)
    if not filtered:
        print("[INFO] 해당 조건의 발행완료 항목 없음.")
        return 0

    groups = _group(filtered)

    token = chat_id = ""
    if not dry_run:
        token = _load_env("TELEGRAM_BOT_TOKEN")
        chat_id = _load_env("TELEGRAM_CHAT_ID")
        if not token or not chat_id:
            print("[ERROR] TELEGRAM_BOT_TOKEN 또는 TELEGRAM_CHAT_ID 미설정", file=sys.stderr)
            return 2

    sent = 0
    for key, group in groups.items():
        msg = _format_summary_message(group) if summary else _format_message(group)
        if dry_run:
            print(msg)
            print("-" * 40)
        else:
            ok = _send(token, chat_id, msg)
            print(f"[INFO] 전송 {'완료' if ok else '실패'}: {key}")
        sent += 1

    mode = "dry-run 출력" if dry_run else "전송"
    print(f"[INFO] 총 {mode} {sent}건")
    return 0


def main() -> None:
    p = argparse.ArgumentParser(description="발행완료 → GM 텔레그램 링크 자동 알림")
    p.add_argument("--folder", metavar="FOLDER", help="folder 부분일치 — 특정 콘텐츠 1건")
    p.add_argument("--today", action="store_true", help="오늘(KST) 발행완료 건 롤업")
    p.add_argument("--since", metavar="YYYY-MM-DD", help="해당 날짜 이후 발행완료 건")
    p.add_argument("--dry-run", action="store_true", help="전송 없이 stdout 출력")
    p.add_argument("--summary", action="store_true",
                   help="📢 5채널 요약 형식 전송 (채널별 이모지+URL, review_queue post_url 자동 수집)")
    args = p.parse_args()

    if not args.folder and not args.today and not args.since:
        p.print_help()
        sys.exit(1)

    sys.exit(run(
        folder=args.folder,
        today=args.today,
        since=args.since,
        dry_run=args.dry_run,
        summary=args.summary,
    ))


if __name__ == "__main__":
    main()
