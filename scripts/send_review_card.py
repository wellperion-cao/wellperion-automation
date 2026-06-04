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
# 건별 마지막 카드 message_id 저장 — 같은 건 재발송 시 이전 카드 자동 삭제(카드 1개만 유지)
CARD_MSGID_STORE = ROOT / "scripts" / ".review_card_msgids.json"


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


def _preview_photo(item: dict) -> Path | None:
    """검수카드에 첨부할 montage 미리보기 로컬 경로.
    preview(배포루트 상대 cmo/review/...) 우선, 없으면 폴더 output/_검수_미리보기_*.png."""
    guide_root = ROOT / "3. 웰페리온 가이드"
    prev = item.get("preview") or ""
    if prev:
        p = guide_root / prev
        if p.exists():
            return p
    folder = item.get("folder") or ""
    if folder:
        out = ROOT / folder / "output"
        if out.exists():
            cands = sorted(out.glob("_검수_미리보기_*.png"))
            if cands:
                return cands[0]
    return None


def _load_msgids() -> dict:
    try:
        if CARD_MSGID_STORE.exists():
            return json.loads(CARD_MSGID_STORE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _save_msgids(d: dict) -> None:
    try:
        CARD_MSGID_STORE.write_text(
            json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def _extract_msg_id(resp) -> int | None:
    """텔레그램 API 응답 본문에서 result.message_id 추출."""
    try:
        payload = json.loads(resp.read().decode("utf-8"))
        if payload.get("ok"):
            return payload.get("result", {}).get("message_id")
    except Exception:
        pass
    return None


def _delete_message(token: str, msg_id: int) -> bool:
    """봇이 보낸 이전 카드 삭제(48시간 내 가능). 실패는 무시(이미 지웠거나 만료)."""
    data = urllib.parse.urlencode(
        {"chat_id": TELEGRAM_CHAT_ID, "message_id": msg_id}).encode("utf-8")
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/deleteMessage", data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except Exception:
        return False


def _send_text_card(token: str, caption: str, keyboard: dict, item_id: str) -> int | None:
    """이미지 없을 때 텍스트 카드 폴백. message_id 반환(실패 None)."""
    data = urllib.parse.urlencode({
        "chat_id": TELEGRAM_CHAT_ID, "text": caption, "parse_mode": "HTML",
        "disable_web_page_preview": "true",
        "reply_markup": json.dumps(keyboard, ensure_ascii=False),
    }).encode("utf-8")
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage", data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            mid = _extract_msg_id(resp)
            print(f"[INFO] 카드(텍스트 폴백) 발송 {'성공' if mid else '실패'}: {item_id}")
            return mid
    except Exception:
        print("[WARN] 카드 발송 실패 (토큰 trace 노출 방지로 상세 미출력)")
        return None


def _send_photo_card(token: str, caption: str, keyboard: dict,
                     photo: Path, item_id: str) -> int | None:
    """sendPhoto multipart (montage 이미지 + caption + 인라인 버튼). message_id 반환(실패 None)."""
    boundary = "----WellperionCard" + os.urandom(12).hex()
    pre = []
    for name, value in (("chat_id", TELEGRAM_CHAT_ID), ("caption", caption),
                        ("parse_mode", "HTML"),
                        ("reply_markup", json.dumps(keyboard, ensure_ascii=False))):
        pre.append(
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n"
            .encode("utf-8"))
    head = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"photo\"; "
            f"filename=\"{photo.name}\"\r\nContent-Type: image/png\r\n\r\n").encode("utf-8")
    body = b"".join(pre) + head + photo.read_bytes() + f"\r\n--{boundary}--\r\n".encode("utf-8")
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendPhoto", data=body, method="POST")
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            mid = _extract_msg_id(resp)
            print(f"[INFO] 검수카드(이미지) 발송 {'성공' if mid else '실패'}: {item_id}")
            return mid
    except Exception:
        print("[WARN] 검수카드(이미지) 발송 실패 — 텍스트 폴백 시도")
        return None


def send_card(item: dict) -> bool:
    """검수 카드 1건 발송 — montage 미리보기 이미지 + [승인]/[반려] 버튼.
    같은 건 재발송 시 이전 카드를 자동 삭제(카드 1개만 유지). 이미지 없으면 텍스트 폴백. (토큰 stdout 노출 금지)"""
    token = _token()
    if not token:
        print("[WARN] 텔레그램 토큰 미설정 — 발송 생략")
        return False
    item_id = item.get("id", "")
    title = item.get("title", item_id)
    channel = item.get("channel", "")
    folder = item.get("folder", "")

    caption = (
        f"🔎 <b>콘텐츠 검수 요청</b>\n"
        f"<b>{title}</b>\n"
        f"채널: {channel}\n"
        f"폴더: {folder}\n\n"
        f"슬라이드 미리보기 ↑ · <a href=\"{M5_URL}\">M5에서 전체 보기</a>\n"
        f"확인 후 아래에서 바로 발행 승인하세요."
    )
    keyboard = {
        "inline_keyboard": [[
            {"text": "✅ 승인 (즉시 발행)", "callback_data": f"pub:{item_id}:approve"},
            {"text": "❌ 반려", "callback_data": f"pub:{item_id}:reject"},
        ]]
    }

    photo = _preview_photo(item)
    if photo is None:
        print(f"[INFO] 미리보기 이미지 없음 — 텍스트 카드 폴백: {item_id}")
        new_id = _send_text_card(token, caption, keyboard, item_id)
    else:
        new_id = _send_photo_card(token, caption, keyboard, photo, item_id)
        if new_id is None:  # 이미지 발송 실패 → 텍스트 폴백
            new_id = _send_text_card(token, caption, keyboard, item_id)

    if new_id is None:
        return False

    # 같은 건의 이전 카드 자동 삭제 후 새 message_id 저장 (카드 1개만 유지)
    store = _load_msgids()
    prev_id = store.get(item_id)
    if prev_id and prev_id != new_id:
        if _delete_message(token, prev_id):
            print(f"[INFO] 이전 카드 자동 삭제: {item_id} msg_id={prev_id}")
    store[item_id] = new_id
    _save_msgids(store)
    return True


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
