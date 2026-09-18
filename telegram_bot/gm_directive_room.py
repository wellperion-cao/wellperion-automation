# -*- coding: utf-8 -*-
"""gm_directive_room.py — GM지시방 수신 에이전트 (배 12769 · GM 지시 2026-09-18).

정본 = status/briefs/CEO-2026-09-18-GM지시-자동화-파이프라인.md §1·§4·§8.
work_room_agent.py(업무관리 방)와 같은 모양의 `handle_group_message(update, ctx)` — bot.py
handle_message() 안에서 1줄 호출된다. GM지시방(status/telegram_rooms.json 「GM지시」)에서
GM 본인 텍스트만 상대, 봇·다른 방은 무시.

흐름:
  「승인」(「승인 N」 허용) → 대기 중 정리본(§ _find_pending)을 게시 엔진(scripts/gm_directive_pipeline.py
  publish)으로 넘긴다. 엔진 없으면 승인 기록만 남기고 폴백 회신.
  그 밖 모든 텍스트 = 지시 날메모 → inbox 에 원문 저장 → 정리 엔진(organize)에 넘겨 정리본을
  회신(+「승인」 안내). 엔진 없으면 접수 폴백 회신(원문은 이미 보관).

3-트리거(💰🔒🚫) 낱말이 있으면 정리본 앞에 경고 줄 + pending.trigger=true(게시 시 --flag-trigger).

pending 원장 = status/_private/gm_directives/pending.json(.gitignore 대상 — 공개 저장소에 안 나감).
"""
from __future__ import annotations

import json
import logging
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import work_room_agent  # _is_owner·KST 재사용(약속 L21 — 같은 판정을 두 곳에 안 만든다)

REPO_ROOT = Path(__file__).resolve().parent.parent
ROOMS_PATH = REPO_ROOT / "status" / "telegram_rooms.json"
ROOM_KEY = "GM지시"
PIPELINE = REPO_ROOT / "scripts" / "gm_directive_pipeline.py"
PYTHON = "C:/Python314/python.exe"

log = logging.getLogger("gm_directive_room")

_APPROVE_RE = re.compile(r"^승인(?:\s+(\d+))?$")
_TRIGGER_WORDS = ("결제", "비용", "원", "만원", "계약", "보안", "비밀번호", "권한", "삭제", "금지", "계정")
_TRIGGER_HEADER = "⚠️ 💰🔒🚫 해당 가능 — 자동 게시 제외 · 승인 뒤에도 GM 재확인 대상으로 표시\n\n"
_APPROVE_HINT = "\n\n👉 이대로 게시하려면 「승인」 한 마디"
_CHUNK = 4000

# ponytail: 테스트가 격리 디렉터리로 바꿔치기하는 단일 지점 — 실제 실행은 REPO_ROOT 아래 고정 경로.
BASE_DIR = REPO_ROOT / "status" / "_private" / "gm_directives"


def _inbox_dir() -> Path:
    return BASE_DIR / "inbox"


def _organized_dir() -> Path:
    return BASE_DIR / "organized"


def _pending_path() -> Path:
    return BASE_DIR / "pending.json"


def _room_chat_id() -> "int | None":
    try:
        rooms = json.loads(ROOMS_PATH.read_text(encoding="utf-8"))
        v = rooms.get(ROOM_KEY)
        return int(v) if v else None
    except Exception:
        return None


def _has_trigger(text: str) -> bool:
    return any(w in (text or "") for w in _TRIGGER_WORDS)


def _iso_now() -> str:
    return datetime.now(work_room_agent.KST).strftime("%Y-%m-%dT%H:%M:%S+09:00")


def _load_pending() -> list:
    try:
        return json.loads(_pending_path().read_text(encoding="utf-8"))
    except Exception:
        return []


def _save_pending(items: list) -> None:
    p = _pending_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def _next_no(items: "list | None" = None) -> int:
    items = items if items is not None else _load_pending()
    return max((int(it.get("no", 0)) for it in items), default=0) + 1


def _already_processed(msgid: int) -> bool:
    return any(it.get("msgid") == msgid for it in _load_pending())


def _append_pending(entry: dict) -> None:
    items = _load_pending()
    items.append(entry)
    _save_pending(items)


def _update_pending(no: int, **kwargs) -> None:
    items = _load_pending()
    for it in items:
        if it.get("no") == no:
            it.update(kwargs)
    _save_pending(items)


def _find_pending(no: "int | None" = None) -> "dict | None":
    """no 지정 시 그 번호, 아니면 md 는 있고 아직 게시 안 된 것 중 가장 최근."""
    items = _load_pending()
    if no is not None:
        for it in items:
            if it.get("no") == no:
                return it
        return None
    for it in reversed(items):
        if it.get("md") and not it.get("published_at"):
            return it
    return None


def _organize(txt_path: Path) -> "tuple[str | None, str | None]":
    """(정리본 본문, None) 성공 / (None, 사유) 실패·엔진 없음."""
    if not PIPELINE.exists():
        return None, "정리 엔진 준비 중"
    md_path = _organized_dir() / (txt_path.stem + ".md")
    md_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        r = subprocess.run(
            [PYTHON, str(PIPELINE), "organize", "--in", str(txt_path), "--out", str(md_path)],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180)
        if r.returncode != 0:
            return None, f"엔진 오류: {(r.stderr or r.stdout or '').strip()[:200]}"
        if not md_path.exists():
            return None, "엔진이 출력 파일을 안 만듦"
        return md_path.read_text(encoding="utf-8"), None
    except Exception as exc:
        return None, f"엔진 호출 실패: {exc}"


def _publish(entry: dict) -> "tuple[bool, str | None]":
    if not PIPELINE.exists():
        return False, "게시 엔진 준비 중"
    args = [PYTHON, str(PIPELINE), "publish", "--md", entry["md"]]
    if entry.get("trigger"):
        args.append("--flag-trigger")
    try:
        r = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180)
        if r.returncode != 0:
            return False, f"엔진 오류: {(r.stderr or r.stdout or '').strip()[:200]}"
        return True, None
    except Exception as exc:
        return False, f"엔진 호출 실패: {exc}"


async def _reply(ctx, text: str) -> None:
    room = _room_chat_id()
    if room is None:
        return
    for i in range(0, len(text), _CHUNK):
        try:
            await ctx.bot.send_message(chat_id=room, text=text[i:i + _CHUNK])
        except Exception as exc:
            log.error(f"[gm_directive] 회신 실패: {exc}")


async def _handle_memo(text: str, msgid: int, ctx) -> None:
    import asyncio
    now = datetime.now(work_room_agent.KST)
    _inbox_dir().mkdir(parents=True, exist_ok=True)
    txt_path = _inbox_dir() / f"{now:%Y%m%d-%H%M%S}-{msgid}.txt"
    txt_path.write_text(text, encoding="utf-8")
    no = _next_no()
    trigger = _has_trigger(text)
    _append_pending({
        "no": no, "msgid": msgid, "memo": str(txt_path), "md": None,
        "received_at": _iso_now(), "approved_at": None, "published_at": None, "trigger": trigger,
    })
    md_text, err = await asyncio.to_thread(_organize, txt_path)
    if md_text is None:
        await _reply(ctx, f"접수했습니다(#{no}) — {err} · 원문 보관")
        return
    md_path = _organized_dir() / (txt_path.stem + ".md")
    _update_pending(no, md=str(md_path))
    header = _TRIGGER_HEADER if trigger else ""
    await _reply(ctx, header + md_text + _APPROVE_HINT)


async def _handle_approve(text: str, ctx) -> None:
    import asyncio
    m = _APPROVE_RE.match(text)
    no = int(m.group(1)) if m and m.group(1) else None
    entry = _find_pending(no)
    if not entry:
        await _reply(ctx, "승인할 정리본이 없습니다 — 먼저 날메모를 보내주세요")
        return
    if not entry.get("md"):
        await _reply(ctx, f"#{entry['no']} 아직 정리 전 — 정리 엔진 준비 중")
        return
    ok, err = await asyncio.to_thread(_publish, entry)
    now = _iso_now()
    if ok:
        _update_pending(entry["no"], approved_at=now, published_at=now)
        await _reply(ctx, f"✅ 게시 완료(#{entry['no']})")
    else:
        _update_pending(entry["no"], approved_at=now)
        await _reply(ctx, f"승인 기록했습니다(#{entry['no']}) — {err}")


async def handle_group_message(update, ctx) -> None:
    """bot.py handle_message() 안에서 1줄 호출. GM지시방·GM 본인 텍스트만 상대."""
    chat = update.effective_chat
    room = _room_chat_id()
    if room is None or not chat or chat.id != room:
        return
    msg = update.message
    text = msg.text if msg else None
    if not text:
        return
    user = update.effective_user
    if not user or user.is_bot or not work_room_agent._is_owner(user.id):
        return  # 이 방은 GM 본인 글만 지시로 본다 — 봇·다른 사람 글 무시
    msgid = msg.message_id
    if _already_processed(msgid):
        return
    text = text.strip()
    try:
        if _APPROVE_RE.match(text):
            await _handle_approve(text, ctx)
        else:
            await _handle_memo(text, msgid, ctx)
    except Exception as exc:
        log.error(f"[gm_directive] 처리 실패: {exc}")


def _selftest() -> None:
    """네트워크·실제 텔레그램 발신 없이 도는 자체점검 — bot 은 스텁."""
    import asyncio
    import tempfile

    class _FakeBot:
        def __init__(self):
            self.sent = []

        async def send_message(self, chat_id, text, **kw):
            self.sent.append((chat_id, text))

    class _FakeCtx:
        def __init__(self):
            self.bot = _FakeBot()

    class _Obj:
        def __init__(self, **kw):
            self.__dict__.update(kw)

    def _update(chat_id, text, message_id, user_id=1, is_bot=False):
        return _Obj(
            effective_chat=_Obj(id=chat_id),
            message=_Obj(text=text, message_id=message_id),
            effective_user=_Obj(id=user_id, is_bot=is_bot),
        )

    global BASE_DIR, PIPELINE
    orig_base, orig_room, orig_is_owner, orig_pipeline = BASE_DIR, _room_chat_id, work_room_agent._is_owner, PIPELINE
    TEST_ROOM = -999000111
    with tempfile.TemporaryDirectory() as d:
        BASE_DIR = Path(d)
        PIPELINE = Path(d) / "no_such_pipeline.py"  # 엔진 유무와 무관하게 항상 "엔진 없음" 경로를 잰다
        globals()["_room_chat_id"] = lambda: TEST_ROOM
        work_room_agent._is_owner = lambda uid: uid == 1
        try:
            # (a) 날메모 → 엔진 없음 폴백 회신 + inbox 파일 생성
            ctx = _FakeCtx()
            asyncio.run(handle_group_message(_update(TEST_ROOM, "시토 · 상담봇 로그 폴더 분리", 1001), ctx))
            assert len(ctx.bot.sent) == 1 and "정리 엔진 준비 중" in ctx.bot.sent[0][1], ctx.bot.sent
            assert list(_inbox_dir().glob("*.txt")), "inbox 파일 안 생김"
            print("[selftest] (a) 날메모 폴백 OK")

            # (b) 「승인」 → 게시 엔진 없음 폴백(정리본이 있다고 가정하고 pending 을 직접 채운다 —
            # organize 엔진이 없는 이 테스트 환경에서는 md 가 절대 안 생기므로, publish 경로만 따로 잰다)
            md_path = _organized_dir() / "test.md"
            md_path.parent.mkdir(parents=True, exist_ok=True)
            md_path.write_text("# 테스트 정리본", encoding="utf-8")
            _append_pending({"no": 99, "msgid": 1002, "memo": "", "md": str(md_path),
                             "received_at": _iso_now(), "approved_at": None, "published_at": None,
                             "trigger": False})
            ctx2 = _FakeCtx()
            asyncio.run(handle_group_message(_update(TEST_ROOM, "승인", 1003), ctx2))
            assert len(ctx2.bot.sent) == 1 and "게시 엔진 준비 중" in ctx2.bot.sent[0][1], ctx2.bot.sent
            entry = _find_pending(99)
            assert entry["approved_at"] is not None and entry["published_at"] is None, entry
            print("[selftest] (b) 승인→게시엔진없음 폴백 OK")

            # (c) 3-트리거 낱말 감지
            assert _has_trigger("이 건은 계약서 검토가 필요합니다") is True
            assert _has_trigger("오늘 점검 다녀왔습니다") is False
            print("[selftest] (c) 트리거 감지 OK")

            # (d) 다른 방 chat_id 는 무시(발신·저장 없음)
            ctx3 = _FakeCtx()
            before = len(_load_pending())
            asyncio.run(handle_group_message(_update(TEST_ROOM + 1, "아무 메모", 1004), ctx3))
            assert ctx3.bot.sent == [] and len(_load_pending()) == before, "다른 방인데 처리됨"
            print("[selftest] (d) 다른 방 무시 OK")

            # 봇 글·타인 글 무시
            ctx4 = _FakeCtx()
            asyncio.run(handle_group_message(_update(TEST_ROOM, "메모", 1005, user_id=1, is_bot=True), ctx4))
            asyncio.run(handle_group_message(_update(TEST_ROOM, "메모", 1006, user_id=2, is_bot=False), ctx4))
            assert ctx4.bot.sent == [], "봇·타인 글이 처리됨"
            print("[selftest] 봇·타인 글 무시 OK")
        finally:
            BASE_DIR = orig_base
            PIPELINE = orig_pipeline
            globals()["_room_chat_id"] = orig_room
            work_room_agent._is_owner = orig_is_owner
    print("[selftest] 전체 OK")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    _selftest()
