"""콘텐츠 검수 카드 발송기 (2026-06-03, IG 폴링 감시기 폐기 대체).

검수대기 콘텐츠를 GM 텔레그램으로 [✅승인][❌반려] 인라인 버튼 카드로 발송한다.
GM이 [✅승인] 탭 → bot.py 의 cmd_publish_callback(pub:<id>:approve) 가 받아
그 순간 발행 엔진(ig_review_publish_watcher.py --once)을 1회 호출한다(폴링 없음).

CMO 가 콘텐츠를 review_queue.json 에 status='검수대기' 로 적재한 직후 이 스크립트를
호출하면 된다.

실행:
  특정 id 카드:        python scripts\\send_review_card.py --id CMO-2026-06-03-XXX
  검수대기 전체 카드:   python scripts\\send_review_card.py --all-pending
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import urllib.parse
import urllib.request

ROOT = Path(r"C:\Users\jjky0\welperion-automation")
QUEUE = ROOT / "3. 웰페리온 가이드" / "cmo" / "review" / "review_queue.json"
M5_URL = "https://wellperion-cao.github.io/wellperion-automation/wellperion_guide(main).html#M5"

TELEGRAM_TOKEN_ENV_KEY = "TELEGRAM_BOT_TOKEN"
TELEGRAM_CHAT_ID = "8254867551"  # @namuki_report_bot (GM)


def _token() -> str:
    tok = os.environ.get(TELEGRAM_TOKEN_ENV_KEY, "").strip()
    if not tok:
        # .env 폴백 (봇과 동일 SSOT)
        env = ROOT / "telegram_bot" / ".env"
        if env.exists():
            for line in env.read_text(encoding="utf-8").splitlines():
                if line.startswith(f"{TELEGRAM_TOKEN_ENV_KEY}="):
                    tok = line.split("=", 1)[1].strip()
                    break
    return tok


def send_card(item: dict) -> bool:
    """검수 카드 1건 발송. 성공 여부 반환. (토큰 stdout 노출 금지)"""
    token = _token()
    if not token:
        print("[WARN] 텔레그램 토큰 미설정 — 발송 생략")
        return False
    item_id = item.get("id", "")
    title = item.get("title", item_id)
    channel = item.get("channel", "")
    folder = item.get("folder", "")

    text = (
        f"🔎 <b>콘텐츠 검수 요청</b>\n"
        f"<b>{title}</b>\n"
        f"채널: {channel}\n"
        f"폴더: {folder}\n\n"
        f"미리보기 → <a href=\"{M5_URL}\">가이드허브 M5</a>\n"
        f"확인 후 아래에서 바로 발행 승인하세요."
    )
    keyboard = {
        "inline_keyboard": [[
            {"text": "✅ 승인 (즉시 발행)", "callback_data": f"pub:{item_id}:approve"},
            {"text": "❌ 반려", "callback_data": f"pub:{item_id}:reject"},
        ]]
    }
    data = urllib.parse.urlencode({
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": "true",
        "reply_markup": json.dumps(keyboard, ensure_ascii=False),
    }).encode("utf-8")
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage", data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            ok = resp.status == 200
            print(f"[INFO] 카드 발송 {'성공' if ok else '실패'}: {item_id}")
            return ok
    except Exception:
        print("[WARN] 카드 발송 실패 (토큰 trace 노출 방지로 상세 미출력)")
        return False


def load_queue() -> list:
    if not QUEUE.exists():
        return []
    try:
        data = json.loads(QUEUE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception as e:
        print(f"[ERROR] 큐 파싱 실패: {e}")
        return []


def main() -> None:
    p = argparse.ArgumentParser(description="콘텐츠 검수 카드 발송기")
    p.add_argument("--id", help="발송할 큐 항목 id")
    p.add_argument("--all-pending", action="store_true",
                   help="status='검수대기' 전체 카드 발송")
    args = p.parse_args()

    items = load_queue()
    if args.id:
        target = next((it for it in items if it.get("id") == args.id), None)
        if not target:
            print(f"[ERROR] id 미발견: {args.id}")
            sys.exit(1)
        sys.exit(0 if send_card(target) else 1)
    elif args.all_pending:
        pending = [it for it in items if it.get("status") == "검수대기"]
        if not pending:
            print("[INFO] 검수대기 항목 없음.")
            return
        sent = sum(1 for it in pending if send_card(it))
        print(f"[INFO] 검수대기 {len(pending)}건 중 {sent}건 발송.")
    else:
        p.print_help()


if __name__ == "__main__":
    main()
