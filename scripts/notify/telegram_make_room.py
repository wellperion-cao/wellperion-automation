# -*- coding: utf-8 -*-
"""telegram_make_room.py — GM 계정으로 「GM지시」 슈퍼그룹 신설 + 봇 초대·관리자 승격 (배 12769).

GM 지시 파이프라인(status/briefs/CEO-2026-09-18-GM지시-자동화-파이프라인.md §1)의 텔레그램 입구 방을
만든다. 세션·설정은 telegram_user_send.py 와 같은 곳(telegram_bot/.env · telegram_bot/gm_user.session)을
그대로 쓴다(약속 L21 — 세션 관문 하나).

사용:
  --dry-run   세션·봇 확인만(방 안 만듦)
  (인자 없음) status/telegram_rooms.json 에 「GM지시」 키가 이미 있으면 그대로 통과(멱등).
              없으면 슈퍼그룹 신설 → 봇 초대·관리자 승격 → chat_id 를 그 키에 등록.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts" / "notify"))
import telegram_user_send as tus  # _load_env·_SESSION_NAME 재사용 — 새 세션 관문을 안 만든다

ROOMS_PATH = ROOT / "status" / "telegram_rooms.json"
ROOM_KEY = "GM지시"
BOT_USERNAME = "namuki_report_bot"  # CLAUDE.md 0. 업무보고 봇


def _load_rooms() -> dict:
    return json.loads(ROOMS_PATH.read_text(encoding="utf-8"))


def _save_room_id(chat_id: int) -> None:
    rooms = _load_rooms()
    rooms[ROOM_KEY] = chat_id
    ROOMS_PATH.write_text(json.dumps(rooms, ensure_ascii=False, indent=2), encoding="utf-8")


async def _dry_run_async(api_id, api_hash) -> None:
    from telethon import TelegramClient
    client = TelegramClient(tus._SESSION_NAME, api_id, api_hash)
    await client.connect()
    try:
        if not await client.is_user_authorized():
            print("[미인증] GM 세션 만료 — telegram_user_send.py --setup 먼저 실행")
            sys.exit(3)
        me = await client.get_me()
        bot_entity = await client.get_entity(BOT_USERNAME)
        print(f"[OK] GM 세션: {(me.first_name or '')} (id={me.id}) · 봇 확인: @{BOT_USERNAME} (id={bot_entity.id})")
        print(f"[OK] 방 안 만듦(dry-run) — 실행하면 「{ROOM_KEY}」 슈퍼그룹을 새로 만든다")
    finally:
        await client.disconnect()


async def _create_async(api_id, api_hash) -> int:
    from telethon import TelegramClient
    from telethon.tl.functions.channels import CreateChannelRequest, InviteToChannelRequest, EditAdminRequest
    from telethon.tl.types import ChatAdminRights

    client = TelegramClient(tus._SESSION_NAME, api_id, api_hash)
    await client.connect()
    try:
        if not await client.is_user_authorized():
            raise RuntimeError("세션 만료/미인증 — telegram_user_send.py --setup 먼저 실행")
        result = await client(CreateChannelRequest(
            title=ROOM_KEY, about="GM 날메모 입구 · 이 방의 모든 글 = 지시", megagroup=True))
        channel = result.chats[0]
        bot_entity = await client.get_entity(BOT_USERNAME)
        await client(InviteToChannelRequest(channel, [bot_entity]))
        rights = ChatAdminRights(
            post_messages=True, add_admins=False, invite_users=False, change_info=False,
            ban_users=False, delete_messages=True, pin_messages=True, edit_messages=False,
            other=True,
        )
        await client(EditAdminRequest(channel, bot_entity, rights, "AI 웰리 봇"))
        return int(f"-100{channel.id}")  # 봇 API 규격 supergroup chat_id
    finally:
        await client.disconnect()


def main() -> None:
    ap = argparse.ArgumentParser(description="GM지시방 신설(멱등) — GM 계정 Telethon 세션")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    cfg = tus._load_env()
    missing = [k for k in tus.REQUIRED if not cfg.get(k)]
    if missing:
        print(f"[설정 필요] telegram_bot/.env 에 {', '.join(missing)} 값을 넣어주세요.")
        sys.exit(2)
    if not tus._session_exists():
        print("[미인증] 세션 없음 — 먼저 telegram_user_send.py --setup 실행")
        sys.exit(3)

    if args.dry_run:
        asyncio.run(_dry_run_async(int(cfg["TG_USER_API_ID"]), cfg["TG_USER_API_HASH"]))
        return

    rooms = _load_rooms()
    if rooms.get(ROOM_KEY):
        print(f"[스킵] 이미 등록됨 — {ROOM_KEY} = {rooms[ROOM_KEY]}")
        return

    chat_id = asyncio.run(_create_async(int(cfg["TG_USER_API_ID"]), cfg["TG_USER_API_HASH"]))
    _save_room_id(chat_id)
    print(f"[OK] 「{ROOM_KEY}」 방 신설 + 봇 초대·관리자 승격 완료 — chat_id={chat_id} (status/telegram_rooms.json 등록)")


if __name__ == "__main__":
    main()
