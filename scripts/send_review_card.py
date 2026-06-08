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
import hashlib
import json
import os
import sys
import time
from pathlib import Path

import urllib.parse
import urllib.request

try:  # 발신 공용 로깅(best-effort) — 임포트 실패해도 발신 무영향
    from tg_outbound_log import log_outbound
except Exception:
    def log_outbound(*a, **k):
        pass

ROOT = Path(r"C:\Users\jjky0\welperion-automation")
QUEUE = ROOT / "3. 웰페리온 가이드" / "cmo" / "review" / "review_queue.json"
M5_URL = "https://wellperion-cao.github.io/wellperion-automation/wellperion_guide(main).html#M5"

TELEGRAM_TOKEN_ENV_KEY = "TELEGRAM_BOT_TOKEN"
TELEGRAM_CHAT_ID = "8254867551"  # @namuki_report_bot (GM)
# 건별 마지막 카드 상태 저장 — 같은 건 재발송 시 이전 카드 자동 삭제(카드 1개만 유지)
# 값 스키마: {item_id: {"msg_id": int, "sig": str(caption해시), "ts": float}}
#   (구버전 평면 int 도 _load_msgids 에서 신스키마로 흡수 — 하위호환)
CARD_MSGID_STORE = ROOT / "scripts" / ".review_card_msgids.json"
# 동시 호출(11초 내 2회 발송 같은 사고) 직렬화용 파일 락 + 콘텐츠당 1회 재발송 차단 창(초)
CARD_LOCK = ROOT / "scripts" / ".review_card.lock"
DEDUP_WINDOW_SEC = 90  # 같은 콘텐츠·동일 내용 카드의 재발송을 막는 시간 창
# 그룹 id 매핑 저장소 — callback_data 64바이트 한계 우회용 (hash→[id,...])
CARD_GROUPS_STORE = ROOT / "scripts" / ".review_card_groups.json"


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


def _caption_sig(item: dict) -> str:
    """콘텐츠 동일성 판정용 서명. id + title + folder 로 안정 해시(내용 바뀌면 갱신).
    교체·폐기 후 새 내용으로 다시 올리면 sig 가 달라져 새 카드 1장이 정상 발송된다."""
    base = "|".join([
        str(item.get("id", "")),
        str(item.get("title", "")),
        str(item.get("folder", "")),
    ])
    return hashlib.sha1(base.encode("utf-8")).hexdigest()[:16]


def _load_msgids() -> dict:
    """저장소 로드 + 신스키마({msg_id,sig,ts}) 정규화(구버전 평면 int 흡수)."""
    raw = {}
    try:
        if CARD_MSGID_STORE.exists():
            raw = json.loads(CARD_MSGID_STORE.read_text(encoding="utf-8"))
    except Exception:
        raw = {}
    out: dict = {}
    if isinstance(raw, dict):
        for k, v in raw.items():
            if isinstance(v, dict):
                out[k] = v
            else:  # 구버전: 값이 message_id(int) 단일
                out[k] = {"msg_id": v, "sig": "", "ts": 0}
    return out


def _acquire_lock(timeout: float = 25.0) -> bool:
    """카드 발송 직렬화 락 획득(동시 2회 발송 사고 방지). 획득 실패해도 발송은 진행(best-effort)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            fd = os.open(str(CARD_LOCK), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode("ascii"))
            os.close(fd)
            return True
        except FileExistsError:
            # 스테일 락(60초 초과) 회수
            try:
                if time.time() - CARD_LOCK.stat().st_mtime > 60:
                    CARD_LOCK.unlink(missing_ok=True)
                    continue
            except Exception:
                pass
            time.sleep(0.3)
        except Exception:
            return False
    return False


def _release_lock() -> None:
    try:
        CARD_LOCK.unlink(missing_ok=True)
    except Exception:
        pass


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
            log_outbound(caption, chat_id=TELEGRAM_CHAT_ID, source="send_review_card._send_text_card", ok=bool(mid), kind="sendMessage")
            return mid
    except Exception:
        log_outbound(caption, chat_id=TELEGRAM_CHAT_ID, source="send_review_card._send_text_card", ok=False, kind="sendMessage")
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
            log_outbound(caption, chat_id=TELEGRAM_CHAT_ID, source="send_review_card._send_photo_card", ok=bool(mid), kind="sendPhoto")
            return mid
    except Exception:
        log_outbound(caption, chat_id=TELEGRAM_CHAT_ID, source="send_review_card._send_photo_card", ok=False, kind="sendPhoto")
        print("[WARN] 검수카드(이미지) 발송 실패 — 텍스트 폴백 시도")
        return None


def send_card(item: dict, force: bool = False,
              group_ids: list | None = None) -> bool:
    """검수 카드 1건 발송 — montage 미리보기 이미지 + [승인]/[반려] 버튼.

    group_ids: 복수 id 일괄 승인용. 지정 시 버튼 callback_data가
               pub:<id1,id2,...>:approve 형태로 생성된다. 카드 대표 item(미리보기·제목)은
               item 인자를 사용. 중복 가드 키는 item.id 기준.

    콘텐츠당 1회 보장: 동시 호출은 파일 락으로 직렬화하고, 같은 콘텐츠(동일 내용 sig)의
    카드가 DEDUP_WINDOW_SEC 내 이미 나가 있으면 재발송을 스킵한다(11초 내 2회 발송 사고 차단).
    내용이 바뀐 교체본은 sig 가 달라져 새 카드 1장만 발송(이전 카드는 삭제). force=True 면 가드 무시.
    이미지 없으면 텍스트 폴백. (토큰 stdout 노출 금지)"""
    token = _token()
    if not token:
        print("[WARN] 텔레그램 토큰 미설정 — 발송 생략")
        return False
    item_id = item.get("id", "")
    title = item.get("title", item_id)
    channel = item.get("channel", "")
    folder = item.get("folder", "")
    sig = _caption_sig(item)

    locked = _acquire_lock()
    try:
        # 콘텐츠당 1회 가드: 동일 sig 카드가 최근(창 이내) 이미 발송됐으면 재발송 스킵
        if not force:
            store0 = _load_msgids()
            prev = store0.get(item_id) or {}
            if (
                prev.get("msg_id")
                and prev.get("sig") == sig
                and (time.time() - float(prev.get("ts") or 0)) < DEDUP_WINDOW_SEC
            ):
                print(
                    f"[INFO] 콘텐츠당 1회 가드 - 동일 카드 최근 발송됨(스킵): {item_id} "
                    f"msg_id={prev.get('msg_id')}"
                )
                return True
        return _do_send_card(token, item, item_id, title, channel, folder, sig,
                             group_ids=group_ids)
    finally:
        if locked:
            _release_lock()


def _write_group(group_ids: list) -> str:
    """group_ids 를 .review_card_groups.json 에 저장하고 10자 sha1 해시키를 반환.
    callback_data 64바이트 한계 우회용 — bot.py 가 이 파일로 해시→id목록 역조회."""
    key = hashlib.sha1(",".join(group_ids).encode("utf-8")).hexdigest()[:10]
    try:
        store: dict = {}
        if CARD_GROUPS_STORE.exists():
            try:
                store = json.loads(CARD_GROUPS_STORE.read_text(encoding="utf-8"))
            except Exception:
                store = {}
        store[key] = group_ids
        CARD_GROUPS_STORE.write_text(
            json.dumps(store, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass
    return key


def _do_send_card(token, item, item_id, title, channel, folder, sig,
                  group_ids: list | None = None) -> bool:
    """group_ids 가 있으면 카드 1장으로 복수 id 일괄 승인 버튼을 생성한다.
    callback_data 64바이트 한계 → 해시키 방식: pub:grp:<hash>:approve"""

    if group_ids:
        grp_hash = _write_group(group_ids)
        cb_approve = f"pub:grp:{grp_hash}:approve"
        cb_reject  = f"pub:grp:{grp_hash}:reject"
        ch_label = f"{len(group_ids)}개 채널 일괄"
    else:
        cb_approve = f"pub:{item_id}:approve"
        cb_reject  = f"pub:{item_id}:reject"
        ch_label = channel

    caption = (
        f"🔎 <b>콘텐츠 검수 요청</b>\n"
        f"<b>{title}</b>\n"
        f"채널: {ch_label}\n"
        f"폴더: {folder}\n\n"
        f"슬라이드 미리보기 ↑ · <a href=\"{M5_URL}\">M5에서 전체 보기</a>\n"
        f"확인 후 아래에서 바로 발행 승인하세요."
    )
    keyboard = {
        "inline_keyboard": [[
            {"text": "✅ 승인 (즉시 발행)", "callback_data": cb_approve},
            {"text": "❌ 반려", "callback_data": cb_reject},
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

    # 같은 건의 이전 카드 자동 삭제 후 새 상태 저장 (카드 1개만 유지)
    store = _load_msgids()
    prev_id = (store.get(item_id) or {}).get("msg_id")
    if prev_id and prev_id != new_id:
        if _delete_message(token, prev_id):
            print(f"[INFO] 이전 카드 자동 삭제: {item_id} msg_id={prev_id}")
    store[item_id] = {"msg_id": new_id, "sig": sig, "ts": time.time()}
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
    p.add_argument("--id", help="발송할 큐 항목 id (카드 대표 항목 — 미리보기·제목 기준)")
    p.add_argument("--group-ids", help=(
        "콤마 구분 복수 id: 카드 1장으로 일괄 승인 버튼 생성. "
        "--id 는 대표 항목(미리보기·제목)으로만 사용. "
        "예: --id A --group-ids A,B,C,D"))
    p.add_argument("--all-pending", action="store_true",
                   help="status='검수대기' 전체 카드 발송")
    p.add_argument("--force", action="store_true",
                   help="콘텐츠당 1회 가드 무시하고 강제 재발송(이전 카드는 교체)")
    args = p.parse_args()

    items = load_queue()
    if args.id:
        target = next((it for it in items if it.get("id") == args.id), None)
        if not target:
            print(f"[ERROR] id 미발견: {args.id}")
            sys.exit(1)
        group_ids = [x.strip() for x in args.group_ids.split(",") if x.strip()] \
            if args.group_ids else None
        sys.exit(0 if send_card(target, force=args.force, group_ids=group_ids) else 1)
    elif args.all_pending:
        pending = [it for it in items if it.get("status") == "검수대기"]
        if not pending:
            print("[INFO] 검수대기 항목 없음.")
            return
        sent = sum(1 for it in pending if send_card(it, force=args.force))
        print(f"[INFO] 검수대기 {len(pending)}건 중 {sent}건 발송.")
    else:
        p.print_help()


if __name__ == "__main__":
    main()
