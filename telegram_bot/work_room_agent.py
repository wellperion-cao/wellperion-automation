"""work_room_agent.py — 업무관리 방(-5492623600, GM·나우열M·봇) 라이브 에이전트 (배1068, GM 지시 2026-09-05).

bot.py handle_message() 의 그룹 수신 지점(_log_group_message 바로 다음)에서
`await work_room_agent.handle_group_message(update, ctx)` 한 줄로 호출된다. 그 방(WORK_ROOM_CHAT_ID)
사람·CHRO 발화만 상대하고, 봇·GM 본인 발화는 건드리지 않는다(그룹 무응답 원칙 배1065 유지 — 이
에이전트는 자동응답 금지 원칙과 별개로, GM 계정(telegram_user_send)으로만 밖에 말한다).

분류 3종(classify):
  done            — 「반영했습니다」「완료」「등록했습니다」「처리했습니다」류 → 어느 배인지
                     scripts/send_ops_digest._reply_match 재사용으로 찾아 그 배 DONE(mutate_queue)
                     + GM 개인 봇방 1줄.
  question        — 물음표·「확인 부탁」류 → 정본(ssot/canon_values.json values[])에서 답 나오면
                     GM 계정으로 짧게 답, 안 나오면 GM 개인 봇방에 카드.
  register_confirm — 「등록했습니다 TODO-…」류(TODO 번호 포함) → /api/todo(todo_list) 대조 →
                     있으면 배 note 「SSOT 등록 확인」, 없으면 GM 개인 봇방 1줄.

발신(승인 카드): staff_to=나우열M · note 에 '업무관리 발송' 마커가 없는 열린 배 →
CHRO 규격(scripts/notify/telegram_user_send.render_chro_task) 렌더 → GM 개인 봇방에
인라인 [승인]/[보류] 카드(wrk: 콜백 — sign:·pub:·dig:·kakao_send·ck: 와 접두 안 겹침) →
[승인] 시 send_chro_task 로 GM 계정 발송 + 배 note 「업무관리 발송 HH:MM」. 카드 대기 상태는
status/work_room_pending.json 에 최소 저장(봇 재기동 생존).
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import requests
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

REPO_ROOT = Path(__file__).resolve().parent.parent
STATE_FILE = Path(__file__).resolve().parent / "state.json"
QUEUE_LOG = REPO_ROOT / "status" / "_ceo_log.jsonl"
CANON_PATH = REPO_ROOT / "ssot" / "canon_values.json"
PENDING_PATH = REPO_ROOT / "status" / "work_room_pending.json"

WORK_ROOM_CHAT_ID = -5492623600  # 텔레그램 「업무관리」 그룹(GM·나우열M·봇 · GM 확정 2026-09-05)
_GM_CHAT_ID = 8254867551  # GM 텔레그램 챗 id (bot.py _GM_CHAT_ID 와 동일 · ssot/canon_values.json 정본)
TODO_API_URL = (
    "https://script.google.com/macros/s/"
    "AKfycbxDwFkrxK1YIaEoSNcuw2MiHiZQ-7o5N6311ytksSyeEd86ZFOhLknOWqQgNArQvZ-7/exec"
)

log = logging.getLogger("work_room_agent")

_TODO_ID_RE = re.compile(r"TODO-\d+")
_DONE_WORDS = ("반영했습니다", "완료", "등록했습니다", "처리했습니다")
_QUESTION_HINTS = ("확인 부탁",)


def classify(text: str) -> str:
    """분류 우선순위: TODO 번호가 있으면 등록확인이 완료·회신보다 더 구체적인 신호다."""
    t = text or ""
    if _TODO_ID_RE.search(t):
        return "register_confirm"
    if any(w in t for w in _DONE_WORDS):
        return "done"
    if "?" in t or "？" in t or any(h in t for h in _QUESTION_HINTS):
        return "question"
    return "other"


def _is_owner(user_id) -> "bool":
    """bot.py 의 load_state() 와 같은 파일을 읽는다(순환 임포트 회피 위해 자체 구현)."""
    try:
        st = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        return user_id is not None and user_id == st.get("owner_id")
    except Exception:
        return False


_SOD_MODULE = None


def _sod():
    """scripts/send_ops_digest.py 지연 임포트 — _reply_match·NAWOOL_WHO 재사용(약속 L21 ·
    새 매칭 로직·새 상수를 여기 다시 만들지 않는다)."""
    global _SOD_MODULE
    if _SOD_MODULE is not None:
        return _SOD_MODULE
    try:
        scr = str(REPO_ROOT / "scripts")
        if scr not in sys.path:
            sys.path.insert(0, scr)
        import send_ops_digest as _mod
        _SOD_MODULE = _mod
    except Exception as exc:
        log.error(f"[work_room] send_ops_digest 임포트 실패: {exc}")
        _SOD_MODULE = False
    return _SOD_MODULE or None


def _queue_lock():
    try:
        scr = str(REPO_ROOT / "scripts")
        if scr not in sys.path:
            sys.path.insert(0, scr)
        import queue_lock
        return queue_lock
    except Exception as exc:
        log.error(f"[work_room] queue_lock 임포트 실패: {exc}")
        return None


def _open_nawool_ships() -> "list[dict]":
    """staff_to=나우열M · 상태 PENDING/IN_PROGRESS · 전달문 있는 열린 배들."""
    ql = _queue_lock()
    sod = _sod()
    if ql is None or sod is None:
        return []
    try:
        queue = ql.load_queue()
    except Exception as exc:
        log.error(f"[work_room] 큐 읽기 실패: {exc}")
        return []
    out = []
    for ship in queue:
        if not isinstance(ship, dict):
            continue
        if ship.get("status") not in ("PENDING", "IN_PROGRESS"):
            continue
        if str(ship.get("staff_to") or "").strip() != sod.NAWOOL_WHO:
            continue
        if not sod._has_staff_message(ship):
            continue
        out.append(ship)
    return out


def find_ship_for_reply(text: str, today: "str | None" = None) -> "dict | None":
    """이 방 회신 한 줄이 가리키는 배 하나(없으면 None). send_ops_digest._reply_match(희소
    키워드 2개+ 매치)를 그대로 재사용한다."""
    sod = _sod()
    if sod is None:
        return None
    today = today or date.today().isoformat()
    try:
        human_lines = sod._nawool_telegram_human_lines(today)
        rare_words = sod._reply_rare_words(human_lines)
    except Exception as exc:
        log.error(f"[work_room] 회신 코퍼스 계산 실패: {exc}")
        return None
    probe = [{"date": today, "time": "", "msg": text}]
    for ship in _open_nawool_ships():
        if sod._reply_match(sod._resolve_staff_message(ship), probe, rare_words):
            return ship
    return None


def _find_ship_by_registered_title(title: str) -> "dict | None":
    """SSOT 에 이미 등록된 「업무명」으로 배를 역추적(포함관계 대조 — 발송문 name=배 제목 그대로 썼으므로)."""
    if not title:
        return None
    sod = _sod()
    if sod is None:
        return None
    for ship in _open_nawool_ships():
        clean = sod._ROLE_TAG_RE.sub("", str(ship.get("title") or "")).strip()
        note = str(ship.get("note") or "")
        if clean and (clean in title or title in clean or title in note):
            return ship
    return None


def _append_ship_note(task_id: str, line: str) -> None:
    ql = _queue_lock()
    if ql is None or not task_id:
        return

    def _mutator(items):
        for it in items:
            if it.get("task_id") == task_id:
                prev = str(it.get("note") or "")
                it["note"] = (prev + ("\n" if prev else "") + line).strip()

    ql.mutate_queue(_mutator, holder="work_room_agent")


def _close_ship(task_id: str, reply_text: str, human_time: str) -> None:
    ql = _queue_lock()
    if ql is None or not task_id:
        return

    def _mutator(items):
        for it in items:
            if it.get("task_id") == task_id:
                prev = str(it.get("note") or "")
                line = f"[업무관리 회신 {human_time}] {reply_text[:40]}"
                it["note"] = (prev + ("\n" if prev else "") + line).strip()
                it["status"] = "DONE"
                it["processed_at"] = date.today().isoformat()

    ql.mutate_queue(_mutator, holder="work_room_agent-done")
    try:
        scr = str(REPO_ROOT / "scripts")
        if scr not in sys.path:
            sys.path.insert(0, scr)
        from worklog import log as _worklog_log
        _worklog_log("cto", "업무관리방", "나우열M 반영 확인", result="ok",
                     detail=reply_text[:80], ref=task_id)
    except Exception:
        pass


def _check_todo_registered(todo_id: str) -> "str | None":
    """/api/todo(todo_list) 에서 todo_id 행을 찾아 업무명을 돌려준다(없으면 None)."""
    try:
        r = requests.get(TODO_API_URL, params={"action": "todo_list"}, timeout=15)
        data = (r.json() or {}).get("data") or []
    except Exception as exc:
        log.error(f"[work_room] todo_list 조회 실패: {exc}")
        return None
    for row in data:
        if isinstance(row, dict) and row.get("id") == todo_id:
            return row.get("업무명")
    return None


def answer_from_canon(question: str) -> "str | None":
    """ssot/canon_values.json values[] 에서 질문에 라벨(「이름」, 끝 괄호주석 제거)이 그대로
    들어있으면 그 값으로 답한다. 새 사실 스키마를 만들지 않는다(약속 L21) — 정본 값 목록
    하나만 대조. ★낱말 하나만 겹치는 느슨한 매치는 쓰지 않는다("전화"·"번호"·"공식" 같은
    흔한 낱말이 엉뚱한 값을 골라 GM 계정으로 오답이 나가는 사고가 실측됐다) — 모르면
    답하지 않고 카드로 넘기는 쪽이 안전하다."""
    try:
        vals = json.loads(CANON_PATH.read_text(encoding="utf-8")).get("values") or []
    except Exception as exc:
        log.error(f"[work_room] canon_values 읽기 실패: {exc}")
        return None
    q = question or ""
    hits = []
    for v in vals:
        if not isinstance(v, dict):
            continue
        label = str(v.get("이름") or "").strip()
        value = v.get("value")
        if not label or value in (None, ""):
            continue
        core = re.sub(r"\s*\([^)]*\)\s*$", "", label).strip()  # "공식 포지셔닝 (국문)" → "공식 포지셔닝"
        if core and core in q:
            hits.append((core, label, value))
    if not hits:
        return None
    _core, label, value = max(hits, key=lambda x: len(x[0]))
    return f"{label} — {value}"


def _load_pending() -> dict:
    try:
        return json.loads(PENDING_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_pending(pending: dict) -> None:
    PENDING_PATH.write_text(json.dumps(pending, ensure_ascii=False, indent=2), encoding="utf-8")


def scan_new_instructions() -> "list[dict]":
    """staff_to=나우열M 인 열린 배 중, 아직 이 에이전트가 안 보낸(note 에 마커 없는) 것들."""
    out = []
    for ship in _open_nawool_ships():
        note = str(ship.get("note") or "")
        if "업무관리 발송" in note:
            continue
        out.append(ship)
    return out


def _render_card_text(name, owner, start, end, content) -> str:
    return (
        "📋 업무관리 방 발송 승인 요청\n"
        f"업무명 : {name}\n담당자 : {owner}\n시작일 : {start}\n종료일 : {end}\n내용 : {content}\n\n"
        "[승인]하면 GM 계정으로 위 규격 그대로 「업무관리」 방에 나갑니다."
    )


async def _scan_pending_cards(ctx) -> None:
    """staff_to=나우열M 신규 배 → GM 개인 봇방에 승인 카드 1장씩(중복 방지: pending·note 마커)."""
    sod = _sod()
    if sod is None:
        return
    try:
        ships = scan_new_instructions()
    except Exception as exc:
        log.error(f"[work_room] 신규 배 스캔 실패: {exc}")
        return
    if not ships:
        return
    pending = _load_pending()
    already = {v.get("task_id") for v in pending.values()}
    for ship in ships:
        task_id = ship.get("task_id")
        if task_id in already:
            continue
        name = sod._ROLE_TAG_RE.sub("", str(ship.get("title") or "")).strip()
        owner = sod.NAWOOL_WHO
        start = date.today().isoformat()
        end = str(ship.get("must_finish_on") or "").strip() or (date.today() + timedelta(days=7)).isoformat()
        content = sod._resolve_staff_message(ship).strip()
        if not name or not content:
            continue
        h8 = hashlib.md5(str(task_id).encode("utf-8")).hexdigest()[:8]
        pending[h8] = {"task_id": task_id, "name": name, "owner": owner, "start": start, "end": end, "content": content}
        _save_pending(pending)
        markup = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ 승인", callback_data=f"wrk:{h8}:a"),
            InlineKeyboardButton("⛔ 보류", callback_data=f"wrk:{h8}:h"),
        ]])
        try:
            await ctx.bot.send_message(
                chat_id=_GM_CHAT_ID,
                text=_render_card_text(name, owner, start, end, content),
                reply_markup=markup,
            )
        except Exception as exc:
            log.error(f"[work_room] 승인 카드 발송 실패: {exc}")


async def _escalate(ctx, text: str) -> None:
    try:
        await ctx.bot.send_message(chat_id=_GM_CHAT_ID, text=text)
    except Exception as exc:
        log.error(f"[work_room] GM 봇방 경보 실패: {exc}")


async def _handle_done(text: str, ctx) -> None:
    import asyncio
    ship = await asyncio.to_thread(find_ship_for_reply, text)
    if not ship:
        return
    now = datetime.now().strftime("%H:%M")
    task_id = ship.get("task_id")
    title = str(ship.get("title") or "")
    await asyncio.to_thread(_close_ship, task_id, text, now)
    await _escalate(ctx, f"✅ 나우열M 반영 — {title}")


async def _handle_register_confirm(text: str, ctx) -> None:
    import asyncio
    m = _TODO_ID_RE.search(text)
    if not m:
        return
    todo_id = m.group(0)
    title = await asyncio.to_thread(_check_todo_registered, todo_id)
    if not title:
        await _escalate(ctx, f"❓ 업무관리 등록 확인 실패 — {todo_id} 가 SSOT 에 없습니다: {text[:200]}")
        return
    ship = await asyncio.to_thread(_find_ship_by_registered_title, title)
    if ship:
        await asyncio.to_thread(_append_ship_note, ship.get("task_id"), f"SSOT 등록 확인 — {title} ({todo_id})")


async def _handle_question(text: str, ctx) -> None:
    import asyncio
    answer = await asyncio.to_thread(answer_from_canon, text)
    if answer:
        try:
            from notify.telegram_user_send import send_as_gm
        except Exception as exc:
            log.error(f"[work_room] telegram_user_send 임포트 실패: {exc}")
            await _escalate(ctx, f"❓ 업무관리 질문 — {text[:200]} → 답 필요(발신기 미가용)")
            return
        ok = await asyncio.to_thread(send_as_gm, WORK_ROOM_CHAT_ID, answer)
        if not ok:
            await _escalate(ctx, f"❓ 업무관리 질문 — {text[:200]} → 답 필요(발신 실패 — 상한·세션 확인)")
    else:
        await _escalate(ctx, f"❓ 업무관리 질문 — {text[:200]} → 답 필요")


async def handle_group_message(update, ctx) -> None:
    """bot.py handle_message() 의 그룹 수신 지점에서 1줄 호출. WORK_ROOM_CHAT_ID 방
    사람·CHRO 발화만 상대하고, 봇·GM 본인 발화·다른 방은 조용히 지나간다."""
    chat = update.effective_chat
    if not chat or chat.id != WORK_ROOM_CHAT_ID:
        return
    msg = update.message
    text = msg.text if msg else None
    if not text:
        return
    user = update.effective_user
    if user and (user.is_bot or _is_owner(user.id)):
        return  # GM 본인 지시 원문·봇 발화는 응대 대상이 아니다

    kind = classify(text)
    try:
        if kind == "register_confirm":
            await _handle_register_confirm(text, ctx)
        elif kind == "done":
            await _handle_done(text, ctx)
        elif kind == "question":
            await _handle_question(text, ctx)
    except Exception as exc:
        log.error(f"[work_room] 분류({kind}) 처리 실패: {exc}")

    try:
        await _scan_pending_cards(ctx)
    except Exception as exc:
        log.error(f"[work_room] 승인 카드 스캔 실패: {exc}")


async def handle_card_callback(update, ctx) -> None:
    """승인 카드 [✅ 승인]/[⛔ 보류] 클릭 처리. callback_data = ``wrk:<h8>:<a|h>``."""
    import asyncio
    q = update.callback_query
    if not q or not q.data or not q.data.startswith("wrk:"):
        return
    await q.answer()
    parts = q.data.split(":")
    if len(parts) != 3:
        return
    h8, decision = parts[1], parts[2]
    pending = _load_pending()
    item = pending.get(h8)
    if not item:
        try:
            await q.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass
        return

    if decision != "a":
        try:
            await q.edit_message_text(text=f"⛔ 보류 — {item['name']}", reply_markup=None)
        except Exception:
            pass
        pending.pop(h8, None)
        _save_pending(pending)
        return

    try:
        from notify.telegram_user_send import send_chro_task, _today_sent_count, _DAILY_CAP
    except Exception as exc:
        log.error(f"[work_room] telegram_user_send 임포트 실패: {exc}")
        try:
            await q.edit_message_text(text=f"⚠️ 발송 실패(발신기 미가용) — {item['name']}", reply_markup=None)
        except Exception:
            pass
        return

    if _today_sent_count() >= _DAILY_CAP:
        try:
            await q.edit_message_text(text=f"⚠️ 오늘 발신 상한({_DAILY_CAP}통) 초과 — {item['name']} · 내일 다시 승인", reply_markup=None)
        except Exception:
            pass
        return  # pending 유지 — 내일 재승인 가능

    ok = await asyncio.to_thread(
        send_chro_task, item["name"], item["owner"], item["start"], item["end"], item["content"]
    )
    if not ok:
        try:
            await q.edit_message_text(text=f"⚠️ 발송 실패(세션 만료 의심) — {item['name']}", reply_markup=None)
        except Exception:
            pass
        return  # pending 유지 — 재시도 가능

    now = datetime.now().strftime("%H:%M")
    await asyncio.to_thread(_append_ship_note, item["task_id"], f"[업무관리 발송 {now}]")
    try:
        await q.edit_message_text(text=f"✅ 발송 완료 — {item['name']}", reply_markup=None)
    except Exception:
        pass
    pending.pop(h8, None)
    _save_pending(pending)


def _selfcheck() -> None:
    """네트워크 없이 도는 classify() 최소 검증(6케이스) — python work_room_agent.py 로 실행."""
    assert classify("반영했습니다") == "done"
    assert classify("등록했습니다 TODO-20260905171415092") == "register_confirm"
    assert classify("이거 확인 부탁드립니다") == "question"
    assert classify("이 문구 맞나요?") == "question"
    assert classify("네 알겠습니다 진행할게요") == "other"
    assert classify("완료했습니다 TODO-999") == "register_confirm", "TODO 번호가 있으면 완료보다 등록확인 우선"
    print("[selfcheck] classify OK (6케이스)")


if __name__ == "__main__":
    _selfcheck()
