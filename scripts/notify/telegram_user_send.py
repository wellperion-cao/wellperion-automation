# -*- coding: utf-8 -*-
"""telegram_user_send.py — GM 본인 텔레그램 계정으로 직접 발송(Telethon, User API).

봇(telegram_send.py)과 다르다: 봇은 "봇이 보냄"으로 찍히고, 이건 GM 본인 이름으로 나간다.
GM 결재(2026-09-05): 업무관리 그룹(-5492623600)에 GM 계정으로 글을 남기는 용도.

설정 = telegram_bot/.env 의 TG_USER_API_ID · TG_USER_API_HASH · TG_USER_PHONE (my.telegram.org 발급).
세션 = telegram_bot/gm_user.session (.gitignore *.session 로 이미 제외).

사용:
  --setup                          최초 1회, GM 본인 터미널에서 대화형 로그인
  --whoami                         세션 확인
  --send --chat <id> --text "..."  발송(텍스트는 stdin 도 가능) · --dry-run 미리보기

파이썬에서: from scripts.notify.telegram_user_send import send_as_gm
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
_ENV_FILE = ROOT / "telegram_bot" / ".env"
_SESSION_NAME = str(ROOT / "telegram_bot" / "gm_user")  # telethon 이 .session 을 붙인다
_SESSION_FILE = ROOT / "telegram_bot" / "gm_user.session"
REQUIRED = ("TG_USER_API_ID", "TG_USER_API_HASH", "TG_USER_PHONE")
SOURCE = "telegram_user_send"
_DAILY_CAP = 30
_AI_SIGNS = ("[AI 웰리]", "AI 시토", "AI 시모", "AI 시우", "AI 시포", "AI 시뽀", "AI 시로", "AI 시보", "AI CEO")

sys.path.insert(0, str(ROOT / "scripts"))
from tg_outbound_log import log_outbound  # noqa: E402 — 기존 발신 로그 관문 재사용


def _parse_env_file(path: Path) -> dict:
    cfg = {}
    if not path.exists():
        return cfg
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        cfg[k.strip()] = v.strip()
    return cfg


def _load_env() -> dict:
    cfg = _parse_env_file(_ENV_FILE)
    for k in REQUIRED:
        if os.environ.get(k):
            cfg[k] = os.environ[k]
    return cfg


def _session_exists() -> bool:
    return _SESSION_FILE.exists()


def _check_ai_signature(text: str) -> None:
    """제거하지 않는다 — GM 계정 발신문에 AI 서명이 섞였다는 사실만 알린다(호출부 책임)."""
    for s in _AI_SIGNS:
        if s in text:
            print(f"[경고] 본문에 AI 서명({s!r})이 있음 — GM 계정 발신인데 그대로 보냄", file=sys.stderr)
            return


def _today_sent_count() -> int:
    log_path = ROOT / "logs" / f"telegram_sent-{datetime.date.today():%Y-%m-%d}.log"
    if not log_path.exists():
        return 0
    n = 0
    for line in log_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        try:
            rec = json.loads(line)
        except Exception:
            continue
        if rec.get("source") == SOURCE and rec.get("ok") is True:
            n += 1
    return n


def _prepare(text: str):
    """설정·세션 점검. 문제 있으면 (None, exit_code), 없으면 (cfg, 0)."""
    cfg = _load_env()
    missing = [k for k in REQUIRED if not cfg.get(k)]
    if missing:
        print(f"[설정 필요] telegram_bot/.env 에 {', '.join(missing)} 값을 넣어주세요.")
        print("my.telegram.org 에서 App 생성 → api_id/api_hash 발급, 전화번호는 국가코드 포함(예: +8210...)")
        return None, 2
    if not _session_exists():
        print("[미인증] 세션 없음 — 먼저 --setup 실행 "
              "(! C:/Python314/python.exe scripts/notify/telegram_user_send.py --setup)")
        return None, 3
    _check_ai_signature(text)
    return cfg, 0


async def _setup_async(api_id, api_hash, phone, code=None, password=None):
    """`!` 셸은 stdin 이 null 이라 input() 이 EOF 로 죽는다(2026-09-05 실측) —
    코드·2단계 비밀번호를 인자로 받는다. 코드 없이 부르면 텔레그램이 코드를 보내고 종료(exit 5)."""
    from telethon import TelegramClient
    client = TelegramClient(_SESSION_NAME, api_id, api_hash)
    if code is None:
        await client.connect()
        if await client.is_user_authorized():
            me = await client.get_me(); print(f"[OK] 이미 로그인됨: {(me.first_name or '')} (id={me.id})"); await client.disconnect(); return
        await client.send_code_request(phone)
        await client.disconnect()
        print("[코드 발송] 텔레그램 앱에 온 숫자 코드를 받아 다시: --setup --code 12345  (2단계 비밀번호 있으면 --password 도)")
        sys.exit(5)
    await client.start(phone=phone, code_callback=lambda: str(code), password=password)
    me = await client.get_me()
    print(f"[OK] 로그인 완료: {(me.first_name or '')} {(me.last_name or '')} (id={me.id})".strip())
    await client.disconnect()


async def _whoami_async(api_id, api_hash):
    from telethon import TelegramClient
    client = TelegramClient(_SESSION_NAME, api_id, api_hash)
    await client.connect()
    try:
        if not await client.is_user_authorized():
            print("[미인증] 세션 만료 — --setup 다시 실행")
            return
        me = await client.get_me()
        print(f"[OK] {(me.first_name or '')} {(me.last_name or '')} (id={me.id})".strip())
    finally:
        await client.disconnect()


def _room_id(chat_id):
    """--chat 에 방 이름(status/telegram_rooms.json 키 · 예 '업무관리-나우열M')이 오면 숫자 id 로 푼다.
    2026-09-06 실사고: 이름을 그대로 넘겨 int() 에서 죽고 헬스체크가 '발송 실패 1건'으로 잡았다. 숫자면 그대로."""
    s = str(chat_id).strip()
    if s.lstrip("-").isdigit():
        return int(s)
    rooms = json.loads((ROOT / "status" / "telegram_rooms.json").read_text(encoding="utf-8"))
    if s in rooms and rooms[s]:
        return int(rooms[s])
    raise ValueError("알 수 없는 방 이름: %s (status/telegram_rooms.json 키 또는 숫자 chat_id)" % s)


async def _resolve_and_send(client, chat_id, text):
    chat_id = _room_id(chat_id)
    try:
        entity = await client.get_entity(int(chat_id))
    except (ValueError, TypeError):
        await client.get_dialogs()  # raw id 캐시 미스 — 대화목록 동기화 후 재시도
        entity = await client.get_entity(int(chat_id))
    await client.send_message(entity, text)


async def _send_async(api_id, api_hash, chat_id, text):
    from telethon import TelegramClient
    client = TelegramClient(_SESSION_NAME, api_id, api_hash)
    await client.connect()
    try:
        if not await client.is_user_authorized():
            raise RuntimeError("세션 만료/미인증 — --setup 다시 실행 필요")
        await _resolve_and_send(client, chat_id, text)
    finally:
        await client.disconnect()


def _try_send(cfg, chat_id, text) -> bool:
    try:
        asyncio.run(asyncio.wait_for(
            _send_async(int(cfg["TG_USER_API_ID"]), cfg["TG_USER_API_HASH"], chat_id, text),
            timeout=30))
        return True
    except Exception as ex:
        print(f"[실패] {ex}")
        return False


def send_as_gm(chat_id, text: str) -> bool:
    """다른 파이썬 코드에서 호출. 성공 True."""
    cfg, code = _prepare(text)
    if cfg is None:
        return False
    if _today_sent_count() >= _DAILY_CAP:
        print(f"[상한] 오늘 {_DAILY_CAP}통 발송 완료 — 더 못 보냄")
        return False
    ok = _try_send(cfg, chat_id, text)
    log_outbound(text, chat_id=chat_id, source=SOURCE, ok=ok, kind="sendMessage")
    return ok


WORK_ROOM_CHAT_ID = -5492623600  # 텔레그램 「업무관리」 그룹(GM·나우열M·봇 · GM 확정 2026-09-05)


def render_chro_task(name: str, owner: str, start: str, end: str, content: str) -> str:
    """업무지시 규격(GM 확정 2026-09-05) — 첫 줄 「CHRO야」 고정. 나우열M 쪽 CHRO(AI)가 이 첫마디로
    업무지시를 인식해 업무 SSOT 에 바로 등록한다. 줄 순서·라벨은 바꾸지 않는다."""
    vals = {"업무명": name, "담당자": owner, "시작일": start, "종료일": end, "내용": content}
    empty = [k for k, v in vals.items() if not str(v or "").strip()]
    if empty:
        raise ValueError(f"업무지시 빈 값: {', '.join(empty)}")
    return "CHRO야\n" + "\n".join(f"{k} : {str(v).strip()}" for k, v in vals.items())


def send_chro_task(name, owner, start, end, content, chat_id=WORK_ROOM_CHAT_ID) -> bool:
    return send_as_gm(chat_id, render_chro_task(name, owner, start, end, content))


def _selfcheck():
    import tempfile
    t = render_chro_task("테스트", "나우열M", "2026-09-08", "2026-09-12", "내용")
    assert t.splitlines()[0] == "CHRO야" and t.splitlines()[1] == "업무명 : 테스트", t
    try:
        render_chro_task("", "x", "y", "z", "w"); raise AssertionError("빈 값 통과")
    except ValueError:
        pass
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d) / ".env"
        tmp.write_text("TG_USER_API_ID=123\nTG_USER_API_HASH=abc\nTG_USER_PHONE=+821012345678\n", encoding="utf-8")
        cfg = _parse_env_file(tmp)
        assert cfg == {"TG_USER_API_ID": "123", "TG_USER_API_HASH": "abc", "TG_USER_PHONE": "+821012345678"}, cfg
    _check_ai_signature("[AI 웰리] 테스트")  # 예외 없이 경고만
    _check_ai_signature("평범한 GM 메시지")
    print("[selfcheck] OK")


def main():
    ap = argparse.ArgumentParser(description="GM 텔레그램 계정으로 직접 발송(Telethon)")
    ap.add_argument("--setup", action="store_true")
    ap.add_argument("--code", type=str, help="--setup 2단계: 텔레그램 앱에 온 숫자 코드")
    ap.add_argument("--password", type=str, help="2단계 인증 비밀번호(있을 때만)")
    ap.add_argument("--whoami", action="store_true")
    ap.add_argument("--send", action="store_true")
    ap.add_argument("--chat", type=str)
    ap.add_argument("--text", type=str)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--selfcheck", action="store_true")
    ap.add_argument("--chro-task", action="store_true", help="업무지시 규격(CHRO야/업무명/담당자/시작일/종료일/내용)으로 발송 · 기본 chat=업무관리")
    ap.add_argument("--name"); ap.add_argument("--owner"); ap.add_argument("--start"); ap.add_argument("--end"); ap.add_argument("--content")
    args = ap.parse_args()

    if args.chro_task:
        try:
            text = render_chro_task(args.name, args.owner, args.start, args.end, args.content)
        except ValueError as ex:
            print(f"[오류] {ex}"); sys.exit(2)
        chat = args.chat or str(WORK_ROOM_CHAT_ID)
        cfg, code = _prepare(text)
        if cfg is None:
            print(text); sys.exit(code)
        if args.dry_run:
            print(f"[dry-run] chat={chat}\n{text}"); return
        if _today_sent_count() >= _DAILY_CAP:
            print(f"[상한] 오늘 {_DAILY_CAP}통 발송 완료"); sys.exit(4)
        ok = _try_send(cfg, chat, text)
        log_outbound(text, chat_id=chat, source=SOURCE, ok=ok, kind="sendMessage")
        sys.exit(0 if ok else 1)

    if args.selfcheck:
        _selfcheck()
        return

    if args.setup:
        cfg = _load_env()
        missing = [k for k in REQUIRED if not cfg.get(k)]
        if missing:
            print(f"[설정 필요] telegram_bot/.env 에 {', '.join(missing)} 값을 넣어주세요.")
            print("my.telegram.org 에서 App 생성 → api_id/api_hash 발급, 전화번호는 국가코드 포함(예: +8210...)")
            sys.exit(2)
        asyncio.run(_setup_async(int(cfg["TG_USER_API_ID"]), cfg["TG_USER_API_HASH"], cfg["TG_USER_PHONE"], code=args.code, password=args.password))
        return

    if args.whoami:
        cfg, code = _prepare("")
        if cfg is None:
            sys.exit(code)
        asyncio.run(_whoami_async(int(cfg["TG_USER_API_ID"]), cfg["TG_USER_API_HASH"]))
        return

    if args.send:
        if not args.chat:
            print("[오류] --chat 필요")
            sys.exit(1)
        text = args.text if args.text is not None else sys.stdin.read()
        cfg, code = _prepare(text)
        if cfg is None:
            sys.exit(code)
        if args.dry_run:
            print(f"[dry-run] 발송 안 함 — chat={args.chat} text={text[:80]!r}")
            return
        if _today_sent_count() >= _DAILY_CAP:
            print(f"[상한] 오늘 {_DAILY_CAP}통 발송 완료 — 더 못 보냄")
            sys.exit(4)
        ok = _try_send(cfg, args.chat, text)
        log_outbound(text, chat_id=args.chat, source=SOURCE, ok=ok, kind="sendMessage")
        sys.exit(0 if ok else 1)

    ap.print_help()


if __name__ == "__main__":
    main()
