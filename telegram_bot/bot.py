"""
웰페리온 텔레그램 <-> Claude 역방향 통제 봇
대표님이 외부에서 스마트폰(Telegram)만으로 로컬 Claude Code 파이프라인 통제.

- 최초 /start 보낸 user 가 owner 로 자동 등록 (단독 화이트리스트)
- 지시 수신 -> Claude CLI `-p` (print mode) + `-r <session_id>` 로 문맥 유지 호출
- 최종 응답 + 중요 이벤트만 회신, 4000자 초과 시 .txt 첨부

문구 DB 명령어 (v1.1 추가):
- /문구추가 06 "내용" — 06시 시간대 문구 등록
- /문구추가 18 "내용" — 18시 시간대 문구 등록
- /문구삭제 PAGE_ID  — 해당 문구 페이지 비활성화(활성=False)
- /문구목록 06       — 06시 활성 문구 목록 조회
- /문구목록 18       — 18시 활성 문구 목록 조회
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import re
import shutil
import subprocess
import threading
import time
from contextlib import nullcontext
from pathlib import Path

import requests

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, constants
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from message_store import append_message as _inbox_log
from bidirectional_handler import classify_message as _bidir_classify

try:  # 저신호 무음 플래그(best-effort) — 임포트 실패해도 발신 무영향(False 폴백)
    from notify_prefs import muted
except Exception:
    def muted(kind: str) -> bool:
        return False

try:  # 발신 공용 로깅(best-effort) — 임포트 실패해도 발신 무영향
    _scr = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
    if _scr not in __import__("sys").path:
        __import__("sys").path.insert(0, _scr)
    from tg_outbound_log import log_outbound
except Exception:
    def log_outbound(*a, **k):
        pass

try:  # 동시커밋 직렬화 lock (P3, 2026-06-16) — scripts/ 경로는 위 블록에서 이미 삽입
    from git_lock import GitLock, pull_rebase_safe
except Exception:
    GitLock = None
    pull_rebase_safe = None

try:  # 크로스프로세스 _queue.json 락 (P2, 2026-07-10) — scripts/ 경로는 위 블록에서 이미 삽입
    import queue_lock
except Exception:
    queue_lock = None

try:  # GM 개인 하루 체크인(ck: 콜백, 2026-08-08 GM 승인 A안) — scripts/ 경로는 위 블록에서 이미 삽입
    import gm_checkin as _checkin
except Exception:
    _checkin = None

try:  # 발송요약 GM 검토 게이트(dig: 콜백, 2026-08-04) — scripts/ 경로는 위 블록에서 이미 삽입
    import publish_digest as _digest
except Exception:
    _digest = None


def _install_outbound_logging() -> None:
    """PTB 발신 메서드(send_message/send_photo/reply_text)에 best-effort 로깅 래핑.
    원본 동작·반환값·문구는 일절 변경하지 않는다(예외 무시). 1회만 설치."""
    try:
        from telegram import Bot, Message

        def _wrap(cls, name, kind):
            orig = getattr(cls, name, None)
            if orig is None or getattr(orig, "_wp_logged", False):
                return

            async def wrapper(self, *args, **kwargs):
                result = await orig(self, *args, **kwargs)
                try:
                    text = kwargs.get("text") or kwargs.get("caption")
                    if text is None and args:
                        text = args[0]
                    cid = kwargs.get("chat_id", None)
                    if cid is None:
                        cid = getattr(getattr(self, "chat", None), "id", None)
                    log_outbound(text, chat_id=cid, source="bot." + name, ok=True, kind=kind)
                except Exception:
                    pass
                return result

            wrapper._wp_logged = True
            setattr(cls, name, wrapper)

        _wrap(Bot, "send_message", "sendMessage")
        _wrap(Bot, "send_photo", "sendPhoto")
        _wrap(Message, "reply_text", "sendMessage")
        _wrap(Message, "reply_photo", "sendPhoto")
    except Exception:
        pass

BASE = Path(__file__).parent
STATE_FILE = BASE / "state.json"
ENV_FILE = BASE / ".env"
LOG_FILE = BASE / "bot.log"
# 폴링 생존 하트비트 (2026-07-03 CTO, 배102) — getMe 헬스체크는 API 도달성만
# 확인하고 실제 run_polling 수신 여부는 모른다. 5분마다 갱신되는 이 파일을
# 헬스체크가 감시해 20분+ 미갱신이면 "폴링 정지 의심"으로 경보한다.
HEARTBEAT_FILE = BASE / "bot_heartbeat.txt"

# ── SSOT 소스 경로 (노션 폐기 2026-05-29 → GitHub status/*) ───────────────────
REPO_ROOT = BASE.parent
STATUS_DIR = REPO_ROOT / "status"
QUOTES_FILE = STATUS_DIR / "quotes.json"
QUEUE_FILE = STATUS_DIR / "_queue.json"
CEO_LOG_FILE = STATUS_DIR / "_ceo_log.jsonl"

WORKDIR = Path.home() / "welperion-automation"  # Claude 실행 기준 디렉토리 (2026-05-23 fix: Desktop → 메인 repo)


def _find_claude() -> str:
    """Windows npm 글로벌 설치 경로를 포함하여 claude CLI 경로 탐색."""
    # Windows: .cmd 래퍼 우선
    for name in ("claude.cmd", "claude.exe", "claude"):
        found = shutil.which(name)
        if found:
            return found
    # Fallback: npm global prefix
    npm_paths = [
        Path.home() / "AppData" / "Roaming" / "npm" / "claude.cmd",
        Path.home() / "AppData" / "Roaming" / "npm" / "claude",
    ]
    for p in npm_paths:
        if p.exists():
            return str(p)
    return "claude"  # 마지막 기대


CLAUDE_BIN = _find_claude()


def load_env() -> dict:
    env = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env


ENV = load_env()

# [2026-05-31 CTO] 죽은 inbox_watcher env 동기화·import 제거 (inbox_watcher.py 부재,
#   CEO 인박스 DB 폐기 2026-05-29). 인박스 적재는 status/_ceo_log.jsonl append로 대체.

TOKEN = ENV.get("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise RuntimeError(".env 에 TELEGRAM_BOT_TOKEN 미정의")

# M1 웹 승인 → 발행 라이브 게이트 (2026-07-16 CMO, 배1170) — 기본 OFF.
# GM go 후 .env M1_AUTO_PUBLISH=1 + 봇 재시작으로 발효. cmd_m1_publish() 가 참조.
M1_AUTO_PUBLISH = ENV.get("M1_AUTO_PUBLISH", "0") == "1"

# ── 결재 키워드 → (상태값, 승인결과값) ────────────────────────────────────────
_APPROVAL_KEYWORD_MAP = {
    "승인":      ("승인완료", "승인"),
    "조건부 승인": ("승인완료", "조건부 승인"),
    "조건부승인":  ("승인완료", "조건부 승인"),
    "보류":      ("보류",    "보류"),
    "반려":      ("반려",    "반려"),
}

# 식별자 패턴: "5.4", "5.4-", "5.4-프로젝트명", 32자리 hex page_id
_ID_PATTERN = re.compile(
    r"([A-Fa-f0-9]{8}-[A-Fa-f0-9]{4}-[A-Fa-f0-9]{4}-[A-Fa-f0-9]{4}-[A-Fa-f0-9]{12}"  # UUID
    r"|[A-Fa-f0-9]{32}"                                                                   # UUID no-dash
    r"|\d{1,2}\.\d{1,2}[-\w가-힣]*)"                                                      # M.D or M.D-이름
)

from logging.handlers import RotatingFileHandler as _RFH

log = logging.getLogger("bot")
log.setLevel(logging.INFO)
_fh = _RFH(LOG_FILE, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8")
_fh.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
_sh = logging.StreamHandler()
_sh.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
log.addHandler(_fh)
log.addHandler(_sh)


def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"owner_id": None, "session_id": None}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )


async def authorized(update: Update) -> bool:
    """최초 접근자를 owner 로 자동 등록. 이후엔 owner 만 허용."""
    state = load_state()
    uid = update.effective_user.id
    uname = update.effective_user.username or "(no username)"
    update_id = getattr(update, "update_id", "?")
    chat_id = update.effective_chat.id if update.effective_chat else "?"

    log.info(f"메시지 수신: update_id={update_id} chat_id={chat_id} user_id={uid} @{uname}")

    if state["owner_id"] is None:
        state["owner_id"] = uid
        save_state(state)
        log.info(f"Owner 신규 등록: id={uid} @{uname}")
        await update.message.reply_text(
            f"✅ 대표님 등록 완료\nid: `{uid}`\n이제 이 대화로 지시사항을 보내주시면 "
            f"로컬 Claude 가 실행하여 회신합니다.\n\n"
            f"• /status - 현재 세션/owner 확인\n"
            f"• /new - 신규 Claude 세션 개시 (문맥 초기화)\n"
            f"• /stopbot - 봇 정상 종료",
            parse_mode="Markdown",
        )
        return True

    if uid != state["owner_id"]:
        log.warning(f"인증 실패 (Unauthorized): id={uid} @{uname} — owner={state['owner_id']}")
        return False

    log.info(f"인증 성공: user_id={uid} owner_id={state['owner_id']}")
    return True


async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await authorized(update):
        return
    await update.message.reply_text(
        "🤖 웰페리온 CEO 통제실 대기 중.\n지시사항을 입력해주세요."
    )


async def cmd_new(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await authorized(update):
        return
    state = load_state()
    old = state.get("session_id")
    state["session_id"] = None
    save_state(state)
    await update.message.reply_text(
        f"🆕 신규 세션 개시.\n이전 session_id: `{old}`", parse_mode="Markdown"
    )


async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await authorized(update):
        return
    state = load_state()
    await update.message.reply_text(
        f"📊 상태\n"
        f"owner_id: `{state.get('owner_id')}`\n"
        f"session_id: `{state.get('session_id') or '(신규)'}`\n"
        f"cwd: `{WORKDIR}`",
        parse_mode="Markdown",
    )


async def cmd_stop(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await authorized(update):
        return
    await update.message.reply_text("🛑 봇 종료합니다. watchdog 이 자동 재기동합니다.")
    log.info("Stop command received. Exiting.")
    os._exit(0)


# ── /복구 (/restart): 죽은 원격 Claude 세션 재기동 (2026-06-07 CTO) ────────────
# 봇·스케줄러는 Task Scheduler 로그온 트리거로 상시 생존 → 이 명령은 Claude 세션만
# 숨김 런처로 다시 띄운다. 이미 살아있으면 중복 기동하지 않음(원격 통제 안전).
_CLAUDE_RESTART_VBS = REPO_ROOT / "launchers" / "claude_session_hidden.vbs"


def _claude_session_alive() -> bool:
    """원격 Claude 세션(claude.exe --remote-control)이 가동 중인지 확인."""
    try:
        result = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq claude.exe", "/FO", "CSV"],
            capture_output=True, text=True, shell=True, timeout=15,
        )
        return "claude.exe" in result.stdout
    except Exception as e:
        log.warning(f"[복구] claude.exe 가동 확인 실패: {e}")
        return False


async def cmd_recover(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """/복구 또는 /restart — owner 전용. 깨진 원격 Claude 세션 재기동.

    숨김 런처(claude_session_hidden.vbs)로 정리된 Start-AI CEO.bat을 호출 →
    Claude 세션만 다시 뜸(봇·스케줄러는 영향 없음). 결과 1줄 회신.
    """
    if not await authorized(update):
        return

    if _claude_session_alive():
        await update.message.reply_text(
            "ℹ️ 원격 Claude 세션이 이미 가동 중입니다. 재기동 불필요."
        )
        return

    if not _CLAUDE_RESTART_VBS.exists():
        await update.message.reply_text(
            f"⚠️ 복구 런처를 찾을 수 없습니다: {_CLAUDE_RESTART_VBS.name}"
        )
        log.error(f"[복구] 런처 부재: {_CLAUDE_RESTART_VBS}")
        return

    try:
        # wscript 로 숨김 VBS 실행 → 검은 창 없이 Start-AI CEO.bat 재기동.
        subprocess.Popen(
            ["wscript.exe", str(_CLAUDE_RESTART_VBS)],
            cwd=str(REPO_ROOT),
        )
        log.info(f"[복구] 원격 Claude 세션 재기동 트리거: {_CLAUDE_RESTART_VBS}")
        await update.message.reply_text(
            "🔄 원격 Claude 세션을 재기동했습니다. 약 1~2분 후 부팅 보고가 도착합니다."
        )
    except Exception as e:
        log.error(f"[복구] 세션 재기동 실패: {e}")
        await update.message.reply_text(f"⚠️ 재기동 실패: {e}")


# ── 문구 명령어 (v2.0) — status/quotes.json SSOT (노션 문구 DB 폐기 2026-05-29) ──

def _load_quotes() -> dict:
    """quotes.json 로드. 실패 시 빈 슬롯 구조 반환."""
    if not QUOTES_FILE.exists():
        return {"06": [], "18": []}
    try:
        data = json.loads(QUOTES_FILE.read_text(encoding="utf-8"))
        data.setdefault("06", [])
        data.setdefault("18", [])
        return data
    except Exception as e:
        log.error(f"quotes.json 로드 실패: {e}")
        return {"06": [], "18": []}


def _save_quotes(data: dict) -> bool:
    """quotes.json 저장."""
    try:
        QUOTES_FILE.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return True
    except Exception as e:
        log.error(f"quotes.json 저장 실패: {e}")
        return False


def _quotes_add(slot: str, content: str) -> str | None:
    """슬롯('06'|'18')에 문구 추가. 성공 시 새 id 반환, 실패 시 None."""
    data = _load_quotes()
    items = data.setdefault(slot, [])
    # id 자동 증가: 슬롯 내 최대 접미 숫자 + 1
    max_n = 0
    for q in items:
        m = re.search(r"-(\d+)$", str(q.get("id", "")))
        if m:
            max_n = max(max_n, int(m.group(1)))
    new_id = f"{slot}-{max_n + 1}"
    items.append({"id": new_id, "text": content, "active": True})
    return new_id if _save_quotes(data) else None


def _quotes_deactivate(quote_id: str) -> bool:
    """문구 id 를 active=False 처리. 매칭 없으면 False."""
    data = _load_quotes()
    found = False
    for slot in ("06", "18"):
        for q in data.get(slot, []):
            if str(q.get("id")) == quote_id:
                q["active"] = False
                found = True
    if not found:
        return False
    return _save_quotes(data)


def _quotes_list(slot: str) -> list[dict]:
    """슬롯의 active=True 문구 목록 반환."""
    data = _load_quotes()
    return [q for q in data.get(slot, []) if q.get("active")]


async def cmd_quote_add(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    /문구추가 06 "내용" 또는 /문구추가 18 내용
    """
    if not await authorized(update):
        return
    raw = update.message.text or ""
    # 명령어 부분 제거 (영문/한글 커맨드 모두 허용)
    body = re.sub(r"^/(문구추가|quote_add)\s*", "", raw).strip()
    # 시간대 파싱: 06 또는 18
    m = re.match(r"^(06|18)\s+(.+)$", body, re.DOTALL)
    if not m:
        await update.message.reply_text(
            "사용법: `/문구추가 06 내용` 또는 `/문구추가 18 내용`\n"
            "시간대는 06 또는 18만 허용됩니다.",
            parse_mode="Markdown",
        )
        return
    slot, content = m.group(1), m.group(2).strip().strip('"').strip("'")

    new_id = _quotes_add(slot, content)
    if new_id:
        await update.message.reply_text(
            f"문구 등록 완료\n"
            f"시간대: {slot}시\n"
            f"내용: {content}\n"
            f"ID: `{new_id}`",
            parse_mode="Markdown",
        )
    else:
        await update.message.reply_text("문구 등록 실패 — quotes.json 쓰기 오류. 로그 확인 필요.")


async def cmd_quote_delete(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    /문구삭제 QUOTE_ID  (예: 06-2)
    """
    if not await authorized(update):
        return
    raw = update.message.text or ""
    body = re.sub(r"^/(문구삭제|quote_delete)\s*", "", raw).strip()
    if not body:
        await update.message.reply_text(
            "사용법: `/문구삭제 ID`\n"
            "ID는 /문구목록 에서 확인하세요 (예: 06-2).",
            parse_mode="Markdown",
        )
        return
    quote_id = body

    ok = _quotes_deactivate(quote_id)
    if ok:
        await update.message.reply_text(f"문구 비활성화 완료\nID: `{quote_id}`", parse_mode="Markdown")
    else:
        await update.message.reply_text("비활성화 실패 — ID 확인 또는 quotes.json 쓰기 오류.")


async def cmd_quote_list(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    /문구목록 06 또는 /문구목록 18
    """
    if not await authorized(update):
        return
    raw = update.message.text or ""
    body = re.sub(r"^/(문구목록|quote_list)\s*", "", raw).strip()
    if body not in ("06", "18"):
        await update.message.reply_text(
            "사용법: `/문구목록 06` 또는 `/문구목록 18`",
            parse_mode="Markdown",
        )
        return

    items = _quotes_list(body)
    if not items:
        await update.message.reply_text(f"{body}시 활성 문구가 없습니다.")
        return

    lines = [f"[{body}시 활성 문구 — {len(items)}건]"]
    for i, item in enumerate(items, 1):
        lines.append(f"{i}. {item.get('text', '(내용없음)')}\n   ID: `{item.get('id', '')}`")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# ── 결재 회신 라우터 헬퍼 (v2.0 — status/_queue.json SSOT, 노션 폐기 대체) ──────
# 결재 매핑: 승인/조건부승인 → DONE 가속(진행), 보류 → ON_HOLD, 반려 → REJECTED
_QUEUE_STATUS_MAP = {
    "승인완료": "APPROVED",
    "보류": "ON_HOLD",
    "반려": "REJECTED",
}


def _load_queue() -> list[dict]:
    """_queue.json 전체 로드. 실패 시 빈 리스트."""
    if not QUEUE_FILE.exists():
        return []
    try:
        return json.loads(QUEUE_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        log.error(f"_queue.json 로드 실패: {e}")
        return []


def _save_queue(items: list[dict]) -> bool:
    """_queue.json 저장 (원자적 tmp+replace — 락 없는 reader도 반쪽 파일 안 봄)."""
    try:
        if queue_lock:
            queue_lock.save_queue_atomic(items)
        else:
            QUEUE_FILE.write_text(
                json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        return True
    except Exception as e:
        log.error(f"_queue.json 저장 실패: {e}")
        return False


def _ceo_log_append(event: str, **fields) -> None:
    """status/_ceo_log.jsonl 에 이벤트 1줄 append (CEO 인박스 DB 폐기 대체)."""
    import datetime as _dt
    rec = {"event": event, **fields, "logged_at": _dt.datetime.now().isoformat()}
    try:
        with open(CEO_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception as e:
        log.error(f"_ceo_log.jsonl append 실패: {e}")


def _query_approval_candidates() -> list[dict]:
    """_queue.json 에서 결재 대기(status=PENDING) 항목을 최신 enqueue 순 반환."""
    items = [x for x in _load_queue() if str(x.get("status", "")).upper() == "PENDING"]
    items.sort(key=lambda x: str(x.get("enqueued_at", "")), reverse=True)
    return items


def _page_title(item: dict) -> str:
    """큐 항목에서 제목 텍스트 추출 (첫 줄만)."""
    title = str(item.get("title", "(제목 없음)"))
    return title.split("\n")[0].strip() or "(제목 없음)"


def _match_identifier(identifier: str, items: list[dict]) -> list[dict]:
    """식별자 문자열로 후보 필터링. task_id 또는 제목 포함 매칭."""
    ident = identifier.strip().lower().replace("-", "")
    matched = []
    for x in items:
        tid = str(x.get("task_id", "")).replace("-", "").lower()
        title = _page_title(x).lower().replace(" ", "").replace("-", "")
        if ident in tid or ident in title:
            matched.append(x)
    return matched


def _patch_approval(task_id: str, status_value: str, approval_result: str, comment: str) -> bool:
    """_queue.json 의 해당 task_id 항목에 결재 결과 반영 + _ceo_log 기록."""
    import datetime as _dt
    with (queue_lock.queue_lock("bot:approval") if queue_lock else nullcontext()):
        items = _load_queue()
        found = False
        for x in items:
            if str(x.get("task_id")) == task_id:
                x["status"] = _QUEUE_STATUS_MAP.get(status_value, status_value)
                x["approval"] = approval_result
                x["approved_at"] = _dt.datetime.now().isoformat()
                if comment:
                    x["approval_comment"] = comment[:2000]
                found = True
                break
        if not found:
            return False
        if not _save_queue(items):
            return False
    _ceo_log_append(
        "GM_APPROVAL",
        task_id=task_id,
        approval=approval_result,
        status=_QUEUE_STATUS_MAP.get(status_value, status_value),
        comment=comment[:500] if comment else "",
    )
    return True


def _detect_approval_intent(text: str) -> str | None:
    """텍스트 앞부분에서 결재 키워드 탐지. 매칭된 원본 키워드 반환, 없으면 None."""
    # 앞 10자 이내에서 탐지 (키워드 + 식별자 순서 가정)
    head = text.strip()
    for kw in sorted(_APPROVAL_KEYWORD_MAP.keys(), key=len, reverse=True):
        if head.startswith(kw):
            return kw
    return None


async def route_approval(update: Update, text: str) -> bool:
    """
    결재 회신 라우터.
    - 결재 키워드 감지 시 True 반환 (Claude CLI relay skip).
    - 결재 키워드 미감지 시 False 반환 (기존 흐름 유지).
    - 모호 케이스(다중 후보/식별자 없음)는 역질문 후 True 반환.
    """
    kw = _detect_approval_intent(text)
    if kw is None:
        return False

    status_value, approval_result = _APPROVAL_KEYWORD_MAP[kw]
    # 키워드 제거 후 나머지에서 식별자 추출
    remainder = text[len(kw):].strip()
    id_match = _ID_PATTERN.search(remainder)
    identifier = id_match.group(0) if id_match else None
    # 반려/조건부 승인 시 키워드+식별자 이후 텍스트를 코멘트로 사용
    comment = ""
    if id_match:
        comment = remainder[id_match.end():].strip()
    elif remainder:
        comment = remainder

    # 결재 대기 후보 수집 (status/_queue.json status=PENDING)
    all_candidates: list[dict] = _query_approval_candidates()

    if not all_candidates:
        await update.message.reply_text(
            "[AI CEO 자동 중계] 현재 결재 대기(PENDING) 항목이 없습니다. status/_queue.json을 확인해주세요."
        )
        return True

    # 식별자 있으면 필터
    if identifier:
        matched = _match_identifier(identifier, all_candidates)
    else:
        matched = all_candidates

    if len(matched) == 0:
        await update.message.reply_text(
            f"[AI CEO 자동 중계] 식별자 '{identifier}'에 해당하는 승인 요청 레코드를 찾지 못했습니다.\n"
            f"현재 승인 요청 건 목록:\n"
            + "\n".join(f"• {_page_title(p)}" for p in all_candidates[:5])
            + "\n\n어느 건을 결재하시겠습니까?"
        )
        return True

    if len(matched) > 1:
        lines = "\n".join(f"{i+1}. {_page_title(p)}" for i, p in enumerate(matched[:5]))
        await update.message.reply_text(
            f"[AI CEO 자동 중계] '{identifier}'에 해당하는 레코드가 {len(matched)}건입니다.\n"
            f"{lines}\n\n정확한 제목 또는 페이지 ID를 포함하여 재전송해 주세요."
        )
        return True

    # 단일 매칭 — patch 실행 (_queue.json 갱신 + _ceo_log 기록)
    target = matched[0]
    task_id = target.get("task_id", "")
    title = _page_title(target)
    ok = await asyncio.to_thread(_patch_approval, task_id, status_value, approval_result, comment)
    if ok:
        await update.message.reply_text(
            f"[AI CEO 자동 중계] 결재 반영 완료 — {title}\n"
            f"결재: {approval_result} / 상태: {_QUEUE_STATUS_MAP.get(status_value, status_value)}"
            + (f"\n코멘트: {comment}" if comment else "")
        )
    else:
        await update.message.reply_text(
            f"[AI CEO 자동 중계] _queue.json 반영 실패 — '{title}' (task_id: {task_id})\n"
            "status/_queue.json 쓰기 권한을 확인해주세요."
        )
    return True


# ── [DEPRECATED] 이전 분류 게이트 (v1.0 양방향 통신으로 대체, 2026-05-25) ────
# 아래 함수들은 현재 호출되지 않음. 향후 Claude CLI 직접 호출 복원 시 재활성화.
_HAIKU_MODEL = "claude-haiku-4-5-20251001"

# 정규식 1차 분류 — (패턴, 즉답 텍스트) 목록
_REGEX_GATE: list[tuple[re.Pattern, str]] = [
    (
        re.compile(r"^(안녕|hi|하이|반가워|좋은\s*(아침|점심|저녁))", re.IGNORECASE),
        "안녕하세요! 웰페리온 AI CEO입니다. 무엇을 도와드릴까요?",
    ),
    (
        re.compile(
            r"(지금|현재).*(몇\s*시|시간|날짜|요일)|오늘.*(날짜|요일)", re.IGNORECASE
        ),
        None,  # None → 동적 응답 (시간 즉답)
    ),
    (
        re.compile(r"^(응|네|예|ok|좋아|알겠|확인|yes|no)$", re.IGNORECASE),
        "확인했습니다.",
    ),
    (
        re.compile(r"(상태|status|살아|가동)\??$|^/(status|new|start)", re.IGNORECASE),
        "봇 정상 가동 중입니다.",
    ),
]


def _regex_classify(text: str) -> str | None:
    """정규식 1차 분류. 매칭 시 즉답 문자열 반환, 미매칭 시 None."""
    stripped = text.strip()
    for pattern, reply in _REGEX_GATE:
        if pattern.search(stripped):
            if reply is None:
                # 시간/날짜 동적 즉답
                import datetime as _dt
                now = _dt.datetime.now()
                weekdays = ["월", "화", "수", "목", "금", "토", "일"]
                return (
                    f"현재 {now.strftime('%Y-%m-%d')} ({weekdays[now.weekday()]}) "
                    f"{now.strftime('%H:%M')} 입니다."
                )
            return reply
    return None


async def _run_haiku_classify(text: str) -> str:
    """haiku로 simple/complex 분류. 실패 시 'complex' 반환 (안전 fallback)."""
    classify_prompt = (
        "다음 메시지를 [simple/complex] 중 하나로 분류하라. "
        "simple = 단순 질의·yes/no·짧은 확인. "
        "complex = 복잡한 의사결정·기획·실행 지시. "
        f"메시지: '{text}'. 답은 simple 또는 complex 한 단어만."
    )
    args = [
        CLAUDE_BIN,
        "-p",
        "--model", _HAIKU_MODEL,
        "--output-format", "text",
        "--permission-mode", "bypassPermissions",
        "--no-session-persistence",
    ]
    try:
        if CLAUDE_BIN.lower().endswith(".cmd") or os.name == "nt":
            shell_cmd = subprocess.list2cmdline(args)
            proc = await asyncio.create_subprocess_shell(
                shell_cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(WORKDIR),
            )
        else:
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(WORKDIR),
            )
        stdout, _ = await asyncio.wait_for(
            proc.communicate(input=classify_prompt.encode("utf-8")),
            timeout=30,
        )
        if proc.returncode != 0:
            log.warning(f"[분류게이트] haiku 분류 비정상 종료 exit={proc.returncode} → complex fallback")
            return "complex"
        result = stdout.decode("utf-8", "replace").strip().lower()
        if "simple" in result:
            return "simple"
        return "complex"
    except asyncio.TimeoutError:
        log.warning("[분류게이트] haiku 분류 timeout → complex fallback")
        return "complex"
    except Exception as e:
        log.warning(f"[분류게이트] haiku 분류 예외: {e} → complex fallback")
        return "complex"


async def _run_haiku_answer(prompt: str) -> tuple[str, str | None]:
    """haiku로 simple 메시지 본격 답신. returns (output_text, error)."""
    args = [
        CLAUDE_BIN,
        "-p",
        "--model", _HAIKU_MODEL,
        "--output-format", "json",
        "--permission-mode", "bypassPermissions",
        "--no-session-persistence",
    ]
    try:
        if CLAUDE_BIN.lower().endswith(".cmd") or os.name == "nt":
            shell_cmd = subprocess.list2cmdline(args)
            proc = await asyncio.create_subprocess_shell(
                shell_cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(WORKDIR),
            )
        else:
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(WORKDIR),
            )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(input=prompt.encode("utf-8")),
            timeout=60,
        )
        if proc.returncode != 0:
            err = stderr.decode("utf-8", "replace")[:500]
            return ("", f"haiku exit={proc.returncode}: {err}")
        raw = stdout.decode("utf-8", "replace")
        try:
            data = json.loads(raw)
            result = data.get("result") or data.get("response") or raw
        except Exception:
            result = raw
        return (result, None)
    except asyncio.TimeoutError:
        return ("", "haiku 답신 timeout")
    except Exception as e:
        return ("", f"haiku 답신 예외: {e}")


async def classify_message(text: str) -> tuple[str, str]:
    """
    1차(정규식) → 2차(haiku) 분류 게이트.
    returns (category, gate) where
      category: 'regex_instant' | 'simple' | 'complex'
      gate: 'regex' | 'haiku'
    """
    # 1차: 정규식
    instant = _regex_classify(text)
    if instant is not None:
        return ("regex_instant", "regex")
    # 2차: haiku
    haiku_result = await _run_haiku_classify(text)
    if haiku_result == "simple":
        return ("simple", "haiku")
    return ("complex", "haiku")


async def run_claude(prompt: str, session_id: str | None) -> tuple[str, str | None, str | None]:
    """Claude CLI `-p` 호출. returns (output_text, new_session_id, error)"""
    log.info(
        f"Spawn: {CLAUDE_BIN} {'(resume)' if session_id else '(new)'} prompt_len={len(prompt)}"
    )

    # stdin 으로 prompt 전달 (Windows .cmd 에서 인자 이스케이프 이슈 회피)
    args = [CLAUDE_BIN]
    if session_id:
        args += ["-r", session_id]
    args += [
        "-p",
        "--output-format",
        "json",
        "--permission-mode",
        "bypassPermissions",
    ]

    try:
        # Windows .cmd 는 create_subprocess_exec 에서 실행 불가 → shell 모드
        if CLAUDE_BIN.lower().endswith(".cmd") or os.name == "nt":
            # 쉘 문자열 구성 (prompt 는 stdin 전달이므로 인자 목록에 없음)
            shell_cmd = subprocess.list2cmdline(args)
            proc = await asyncio.create_subprocess_shell(
                shell_cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(WORKDIR),
            )
        else:
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(WORKDIR),
            )
        stdout, stderr = await proc.communicate(input=prompt.encode("utf-8"))
    except FileNotFoundError:
        return ("", None, f"claude CLI 를 찾을 수 없음 ({CLAUDE_BIN})")
    except Exception as e:
        return ("", None, f"subprocess 예외: {type(e).__name__}: {e}")

    if proc.returncode != 0:
        err = stderr.decode("utf-8", "replace")[:1500]
        log.error(f"Claude 비정상 종료: exit={proc.returncode} stderr={err[:300]}")
        return ("", None, f"exit={proc.returncode}\nstderr:\n{err}")

    raw = stdout.decode("utf-8", "replace")
    try:
        data = json.loads(raw)
    except Exception:
        # output-format=json 이 아닐 경우 대비
        log.warning(f"Claude 응답 JSON 파싱 실패 — 원문 반환 (len={len(raw)})")
        return (raw, None, None)

    result = data.get("result") or data.get("response") or ""
    sid = data.get("session_id")
    log.info(f"Claude 응답 수신: result_len={len(result)} session_id={sid}")
    return (result, sid, None)


IMPORTANT_PATTERNS = [
    "승인 필요",
    "승인 요청",
    "approval needed",
    "requires approval",
    "Stage 3",
    "오류 발생",
    "error:",
    "failed",
    "반려",
]


def is_important(text: str) -> bool:
    t = text.lower()
    return any(p.lower() in t for p in IMPORTANT_PATTERNS)


def _log_group_message(update: Update) -> None:
    """그룹 채팅 수신 원문을 _ceo_log.jsonl 에 GROUP_MSG 로 보존 (2026-07-29, 배10392).

    authorized() 게이트보다 먼저 호출 — 지금까지 owner(GM) 아닌 발신자는 authorized()가
    False 를 반환하는 즉시 handle_message 가 return 해 본문이 어디에도 안 남았다
    (실측: 2026-07-22 종합접수처방 user_id=8845322391 — 로그엔 메타뿐 본문 0건).
    이 함수는 순수 추가(additive)다 — 기존 흐름·회신·분류는 한 글자도 안 바꾸고,
    이 호출 다음 줄부터 원래 경로(authorized → 분류 → 자동회신)가 그대로 이어진다.
    소비자(읽어서 담당자에게 넘기는 쪽)는 다음 회차 과제 — 이번엔 적재만."""
    try:
        chat = update.effective_chat
        if not chat or chat.type not in ("group", "supergroup"):
            return
        msg = update.message
        text = msg.text if msg else None
        if not text:
            return
        user = update.effective_user
        state = load_state()
        is_owner = bool(user) and user.id == state.get("owner_id")
        _ceo_log_append(
            "GROUP_MSG",
            chat_id=chat.id,
            chat_title=getattr(chat, "title", None),
            sender_id=user.id if user else None,
            sender_name=(user.username or user.first_name) if user else None,
            is_owner=is_owner,
            text=text[:1000],
        )
    except Exception as e:
        log.error(f"GROUP_MSG 로깅 실패(비치명적 — 원 흐름은 계속 진행): {e}")


# ─── 사진창고 수신 (2026-08-10 CTO · 배492 · GM 선택 2026-08-08) ───
# GM 이 개인 대화에 사진·영상을 그냥 보내면 드라이브 「웰페리온 사진창고 · 00_들어온것」에 쌓인다.
# 저장은 콘텐츠 접수 GAS(action='photo_vault') 재사용 — 새 백엔드를 만들지 않는다(약속 L21).
# 그룹방은 제외한다: 실무진 방에 올라온 사진까지 창고로 빨려 들어가면 안 된다.
# 창고 규칙·분류 기준 정본 = instagram/_사진창고.md
_INTAKE_HTML = WORKDIR / "3. 웰페리온 가이드" / "cmo" / "intake" / "instructor_intake.html"
_TG_FILE_LIMIT_MB = 20  # 텔레그램 Bot API getFile 다운로드 상한


def _intake_gas_url() -> str:
    """GAS 배포 URL 정본 = instructor_intake.html 의 GAS_PROD (약속 L01 — 복사본을 두지 않는다)."""
    try:
        m = re.search(r'GAS_PROD\s*=\s*"([^"]+)"', _INTAKE_HTML.read_text(encoding="utf-8"))
        return m.group(1) if m else ""
    except Exception as exc:
        log.error(f"[photo_vault] 접수 GAS 주소 읽기 실패: {exc}")
        return ""


def _vault_filename(caption: str, ext: str) -> str:
    """받은 시각 + 캡션(있으면)으로 파일명. 캡션은 시모가 분류할 때 힌트로 쓴다."""
    slug = re.sub(r"[^0-9A-Za-z가-힣]+", "_", (caption or "").strip())[:40].strip("_")
    stamp = time.strftime("%Y%m%d_%H%M%S")
    return f"{stamp}_{slug}.{ext}" if slug else f"{stamp}.{ext}"


async def handle_media(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or msg.chat.type != constants.ChatType.PRIVATE:
        return
    if not await authorized(update):
        return

    if msg.photo:
        file_id, mime, ext = msg.photo[-1].file_id, "image/jpeg", "jpg"
    elif msg.video:
        file_id, mime, ext = msg.video.file_id, "video/mp4", "mp4"
    else:
        return

    gas_url = _intake_gas_url()
    if not gas_url:
        await msg.reply_text("⚠️ 사진창고 저장 실패 — 접수 주소를 찾지 못했습니다.")
        return

    try:
        tg_file = await ctx.bot.get_file(file_id)
        blob = bytes(await tg_file.download_as_bytearray())
    except Exception as exc:
        await msg.reply_text(
            f"⚠️ 사진창고 저장 실패 — 파일을 받지 못했습니다. "
            f"{_TG_FILE_LIMIT_MB}MB 를 넘으면 접수 화면으로 올려 주세요. ({exc})")
        return

    payload = {"action": "photo_vault", "photos": [{
        "b64": base64.b64encode(blob).decode("ascii"),
        "mime": mime,
        "fname": _vault_filename(msg.caption, ext),
    }]}
    try:
        resp = await asyncio.to_thread(
            requests.post, gas_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "text/plain;charset=utf-8"},
            timeout=300,
        )
        result = resp.json()
    except Exception as exc:
        await msg.reply_text(f"⚠️ 사진창고 저장 실패 — {exc}")
        return

    if result.get("ok"):
        log.info(f"[photo_vault] 저장 완료 {result.get('urls')}")
        await msg.reply_text("📸 사진창고에 넣었습니다 — 00_들어온것 (분류는 시모가 합니다)")
    else:
        await msg.reply_text(f"⚠️ 사진창고 저장 실패 — {result.get('err') or '알 수 없는 오류'}")


async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    _log_group_message(update)
    if not await authorized(update):
        return

    prompt = update.message.text
    if not prompt:
        return

    _inbox_log("in", "GM", prompt)

    # ── 한글 /복구 명령 선처리 (telegram CommandHandler 는 ASCII 만 허용) ───────
    # "/복구" 또는 "복구" 단독 입력 시 원격 Claude 세션 재기동으로 라우팅.
    if prompt.strip() in ("/복구", "복구", "/재기동", "재기동"):
        await cmd_recover(update, ctx)
        return
    # ────────────────────────────────────────────────────────────────────────

    # NOTE: 인박스 DB 적재는 양방향 분류 게이트에서 category별로 처리
    # (simple_ack 제외, directive/feedback만 적재)

    state = load_state()
    session_id = state.get("session_id")

    # ── 결재 회신 라우터 (양방향 분류보다 우선) ────────────────────────────────
    routed = await route_approval(update, prompt)
    if routed:
        _inbox_log("out", "CEO", f"[결재 자동 처리] {prompt[:100]}", msg_type="approval")
        return  # 결재 처리 완료 — 양방향 분류 skip
    # ────────────────────────────────────────────────────────────────────────

    # ── 네이버 URL 자동기록 분기 (GM 손게시 → review_queue.json, 2026-06-26) ─
    if await _handle_naver_url_record(update, ctx, prompt):
        return
    # ────────────────────────────────────────────────────────────────────────

    # ── 양방향 통신 분류 게이트 (v1.0, 2026-05-25) ─────────────────────────────
    # Claude API/CLI 호출 없이 순수 Python 키워드 분류
    bidir_category, bidir_reply = _bidir_classify(prompt)
    log.info(
        f"[양방향] 분류={bidir_category} 메시지길이={len(prompt)} "
        f"회신미리보기={bidir_reply[:50]}"
    )

    # 인박스 적재 (simple_ack 제외) — CEO 인박스 DB 폐기 → status/_ceo_log.jsonl append
    if bidir_category != "simple_ack":
        _ceo_log_append("GM_INBOX", category=bidir_category, text=prompt[:1000])

    # 자동 회신
    _inbox_log("out", "CEO", bidir_reply, msg_type=bidir_category)
    await update.message.reply_text(bidir_reply)
    # ── /end 양방향 통신 분류 게이트 ────────────────────────────────────────────


async def error_handler(update: object, ctx: ContextTypes.DEFAULT_TYPE):
    log.error(f"Exception in handler: {ctx.error}", exc_info=ctx.error)


# ─── 결재 시스템: SSOT 결재 CallbackQuery 처리 (2026-05-28 신설) ───
TODO_API_URL = ENV.get(
    "TODO_API_URL",
    "https://script.google.com/macros/s/AKfycbxDwFkrxK1YIaEoSNcuw2MiHiZQ-7o5N6311ytksSyeEd86ZFOhLknOWqQgNArQvZ-7/exec",
)


async def cmd_approval_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """결재방 인라인 버튼 (✅/❌) 클릭 처리.

    callback_data 형식: ``sign:<task_id>:<role>:<approve|reject>``
    Apps Script ``todo_sign`` action을 호출해 시트에 싸인을 누적하고,
    응답에 ``next`` 결재자가 있으면 Apps Script 측이 자동으로 다음 카드를 발송한다.
    """
    q = update.callback_query
    if not q or not q.data:
        return
    await q.answer()
    if not q.data.startswith("sign:"):
        return

    parts = q.data.split(":", 3)
    if len(parts) < 4:
        await q.answer("형식 오류", show_alert=False)
        return
    _, task_id, role, decision = parts
    user = update.effective_user
    signer = (user.first_name if user else "") or (user.username if user else "") or role

    log.info(f"[결재] role={role} decision={decision} task={task_id} signer={signer}")

    try:
        r = requests.get(
            TODO_API_URL,
            params={
                "action": "todo_sign",
                "id": task_id,
                "role": role,
                "decision": decision,
                "signer": signer,
            },
            timeout=15,
        )
        res = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        ok = bool(res.get("ok"))
    except Exception as exc:
        log.error(f"[결재] todo_sign 호출 실패: {exc}")
        try:
            await q.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass
        await ctx.bot.send_message(
            chat_id=q.message.chat_id,
            text=f"⚠️ <b>결재 처리 실패</b>\n사유: {exc}\n🆔 {task_id}",
            parse_mode="HTML",
        )
        return

    if not ok:
        err = res.get("error", "알 수 없는 오류")
        try:
            await q.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass
        await ctx.bot.send_message(
            chat_id=q.message.chat_id,
            text=f"⚠️ <b>결재 처리 실패</b>\n사유: {err}\n🆔 {task_id}",
            parse_mode="HTML",
        )
        return

    label = "✅ 승인" if decision == "approve" else "❌ 반려"
    try:
        original = q.message.text_html or q.message.text or ""
    except Exception:
        original = q.message.text or ""
    stamp = f"\n\n━━━━━━━━━━━━━━━━\n{label} — {signer} ({role})"
    try:
        await q.edit_message_text(
            text=original + stamp,
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
    except Exception:
        # 동일 텍스트·HTML 파싱 실패 fallback: 키보드만 제거
        try:
            await q.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass


# ─── 콘텐츠 검수 발행 콜백 (pub:) — 2026-06-03 IG 폴링 감시기 폐기 대체 ───
# sign:(업무 결재, 옵션A로 웹 단일)와 별개. 승인 상태 SSOT = review_queue.json.
# GM이 검수 카드 [✅승인] 탭 → 그 순간 발행 엔진 1회 호출(폴링 제거). 봇은 상시 상주.
REVIEW_QUEUE = WORKDIR / "3. 웰페리온 가이드" / "cmo" / "review" / "review_queue.json"
_VENV_PY = WORKDIR / ".venv" / "Scripts" / "python.exe"
_PUBLISH_ENGINE = WORKDIR / "scripts" / "ig_review_publish_watcher.py"


def _git_seq_locked(commit_msg: str) -> None:
    """승인 콜백 git 시퀀스 — GitLock 임계구역에서 add→commit→pull→push 원자 실행.
    동기·블로킹이므로 반드시 asyncio.to_thread로 호출(봇 이벤트 루프 비차단).
    P3(2026-06-16): 4개 분리 git 호출 사이로 IG 발행엔진(--once)이 끼어들던
    위험쌍#1을 단일 락으로 차단. 설계: docs/git_serialize_lock_design.md §3.
    pull 은 --autostash 대신 pull_rebase_safe 사용(2026-07-30·INC-034 잔존 제거) —
    봇은 상시가동 프로세스라 남의 미커밋 변경을 stash 에 가두는 사고 위험이 가장 컸다."""
    def _g(*args):
        try:
            subprocess.run(
                ["git", "-C", str(WORKDIR), *args],
                capture_output=True, text=True,
                encoding="utf-8", errors="replace",
            )
        except Exception as exc:
            log.error(f"[pub] git {args[:1]} 실패: {exc}")

    def _seq():
        _g("add", str(REVIEW_QUEUE))
        _g("commit", "-m", commit_msg)
        if pull_rebase_safe is not None:
            pull_rebase_safe(str(WORKDIR), str(WORKDIR), "bot:publish_callback")
        else:
            log.warning("[pub] pull_rebase_safe 미가용 — pull 건너뜀(--autostash 재도입 금지)")
        _g("push", "origin", "master")

    try:
        if GitLock is not None:
            with GitLock(holder="bot:publish_callback", repo_root=str(WORKDIR)):
                _seq()
        else:  # 모듈 임포트 실패 시 폴백 — 무락 순차(최소한 봇은 죽지 않음)
            log.warning("[pub] GitLock 미가용 — 무락 순차 커밋 폴백")
            _seq()
    except Exception as exc:  # 락 타임아웃 등 — 무방비 진행 금지, 다음 기회 재커밋
        log.error(f"[pub] git lock/seq 실패(커밋 건너뜀): {exc}")


# ─── 네이버 URL 자동기록 (GM 손게시 → review_queue.json, 2026-06-26) ───────────
# GM이 텔레그램으로 네이버 블로그·카페 URL을 보내면 review_queue.json 해당 항목에
# post_url 기록 후 커밋·푸시. 후보 복수 시 번호 선택 요청(절대 임의 기록 금지).
_NAVER_BLOG_RE = re.compile(r'https?://blog\.naver\.com/\S+')
_NAVER_CAFE_RE = re.compile(r'https?://cafe\.naver\.com/\S+')
_NOTIFY_LINKS_SCRIPT = WORKDIR / "scripts" / "notify_published_links.py"
_NAVER_PENDING_KEY = "naver_url_pending"


def _extract_naver_url(text: str):
    """텍스트에서 첫 번째 네이버 블로그/카페 URL과 채널명 추출.
    blog 우선. 둘 다 없으면 (None, None)."""
    m = _NAVER_BLOG_RE.search(text)
    if m:
        return m.group(0).rstrip(".,)>\"'"), "네이버 블로그"
    m = _NAVER_CAFE_RE.search(text)
    if m:
        return m.group(0).rstrip(".,)>\"'"), "네이버 카페 (동부이촌동)"
    return None, None


def _rq_candidates(items: list, channel: str) -> list:
    """채널 일치 AND (status=='임시저장완료' OR (status=='발행완료' AND post_url 없음))
    published_at/enqueued_at 최신순 정렬."""
    result = [
        it for it in items
        if it.get("channel") == channel
        and (
            it.get("status") == "임시저장완료"
            or (it.get("status") == "발행완료" and not it.get("post_url"))
        )
    ]
    result.sort(
        key=lambda it: it.get("published_at") or it.get("enqueued_at") or it.get("id", ""),
        reverse=True,
    )
    return result


def _rq_apply_url(it: dict, url: str) -> None:
    """review_queue 항목에 post_url·status 갱신 + note append."""
    import datetime
    it["post_url"] = url
    it["status"] = "발행완료"
    today = datetime.date.today().isoformat()
    old_note = (it.get("note") or "").rstrip()
    suffix = f"[GM 텔레그램 회신 {today}] URL 자동기록"
    it["note"] = (old_note + " / " + suffix) if old_note else suffix


# ── review_queue.json 쓰기 = 단일 관문 경유 (2026-07-23 · 07-21 AI하루 10편 소실 재발방지) ──
# 봇도 read→modify→write 를 직접 하다가 스테일 사본으로 덮어쓸 수 있었다. scripts/
# review_queue_util.py 의 락(review_queue.lock)을 경유해 모든 writer 와 직렬화한다.
# 아래 두 함수는 동기·블로킹 → 반드시 asyncio.to_thread 로 호출(봇 루프 비차단).
def _rq_util():
    # scripts/ 경로는 상단 임포트 블록에서 이미 sys.path 에 삽입돼 있다(git_lock·queue_lock 동일).
    import review_queue_util as _u
    return _u


def _rq_record_url_locked(item_id: str, url: str) -> tuple[str, dict | None]:
    """락 임계구역에서 load→검사→URL기록→save.

    반환 code: 'ok' | 'missing' | 'dup' | 'error:<메시지>'
    """
    u = _rq_util()
    box: dict = {}

    def _apply(items: list):
        t = next((it for it in items if it.get("id") == item_id), None)
        if t is None:
            box["r"] = ("missing", None)
            raise u.SkipSave
        if t.get("post_url"):
            box["r"] = ("dup", t)
            raise u.SkipSave
        _rq_apply_url(t, url)
        box["r"] = ("ok", t)
        return items

    try:
        u.mutate_review_queue(_apply, holder="bot:naver_url")
    except Exception as exc:
        # 저장 단계에서 터졌다면 'ok' 로 보고하면 안 된다(기록 안 된 걸 됐다고 말하는 꼴).
        return (f"error:{exc}", None)
    return box.get("r", ("error:판정 결과 없음", None))


def _rq_set_status_locked(item_ids: list, new_status: str) -> tuple:
    """락 임계구역에서 load→status 일괄 기록→save.

    반환: (targets, missing, cancelled, error|None). '폐기' 항목은 절대 안 건드림.
    """
    u = _rq_util()
    box: dict = {"targets": [], "missing": [], "cancelled": []}

    def _apply(items: list):
        for iid in item_ids:
            t = next((it for it in items if it.get("id") == iid), None)
            if t is None:
                box["missing"].append(iid)
            elif t.get("status") == "폐기":
                # 2026-07-20 8편 취소 사고 재발방지: 취소된 항목은 status 덮어쓰기·발행 금지.
                box["cancelled"].append(t)
            else:
                t["status"] = new_status
                if new_status == "승인":
                    t["publish_at"] = ""  # 카드 탭 승인 = 즉시 발행(publish_at 예약 무시)
                box["targets"].append(t)
        if not box["targets"]:
            raise u.SkipSave   # 바꿀 게 없으면 파일 무변경
        return items

    try:
        u.mutate_review_queue(_apply, holder="bot:review_decision")
    except Exception as exc:
        return ([], [], [], str(exc))
    return (box["targets"], box["missing"], box["cancelled"], None)


def _try_notify_links(item: dict) -> None:
    """notify_published_links.py --folder 비차단 호출(best-effort)."""
    folder = item.get("folder", "")
    if not folder or not _NOTIFY_LINKS_SCRIPT.exists():
        return
    try:
        subprocess.Popen(
            [str(_VENV_PY), "-u", str(_NOTIFY_LINKS_SCRIPT), "--folder", folder],
            cwd=str(WORKDIR),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=dict(os.environ, PYTHONIOENCODING="utf-8", TELEGRAM_BOT_TOKEN=(TOKEN or "")),
        )
    except Exception as exc:
        log.warning(f"[naver_url] notify_published_links 호출 실패(무시): {exc}")


async def _handle_naver_url_record(
    update: Update, ctx: ContextTypes.DEFAULT_TYPE, prompt: str
) -> bool:
    """GM이 보낸 네이버 URL을 review_queue.json에 자동 기록.

    흐름:
      1) pending 확인 — 이전 메시지에서 번호 선택 대기 중이면 숫자로 해소.
         숫자가 아닌 새 메시지면 pending 취소 후 URL 탐지로 계속.
      2) 네이버 URL 탐지(blog/cafe). 없으면 False 반환(기존 라우팅 통과).
      3) 후보 1건: 즉시 기록·커밋·회신.
         후보 다건: 번호 목록 제시 후 pending 저장. 임의 기록 금지.
         후보 0건: '대기 없음' 안내.

    처리 완료(handle_message가 return해야 하는 경우) True 반환.
    해당 없으면 False 반환.
    """
    # ── 1) pending 해소 ────────────────────────────────────────────────────
    pending = ctx.user_data.get(_NAVER_PENDING_KEY)
    if pending:
        stripped = prompt.strip()
        if stripped.isdigit():
            idx = int(stripped) - 1
            candidates = pending["candidates"]
            if 0 <= idx < len(candidates):
                chosen_id = candidates[idx]["id"]
                url = pending["url"]
                channel = pending["channel"]
                code, target = await asyncio.to_thread(
                    _rq_record_url_locked, chosen_id, url
                )
                if code.startswith("error:"):
                    await update.message.reply_text(f"⚠️ 큐 기록 실패: {code[6:]}")
                    ctx.user_data.pop(_NAVER_PENDING_KEY, None)
                    return True
                if code == "missing":
                    await update.message.reply_text(
                        f"⚠️ 큐에서 항목을 찾지 못했습니다 (id={chosen_id})."
                    )
                    ctx.user_data.pop(_NAVER_PENDING_KEY, None)
                    return True
                if code == "dup":
                    await update.message.reply_text(
                        f"⚠️ 이미 URL이 기록된 항목입니다: {target.get('title')}\n"
                        f"기존 URL: {target['post_url']}\n덮어쓰지 않습니다."
                    )
                    ctx.user_data.pop(_NAVER_PENDING_KEY, None)
                    return True
                commit_msg = (
                    f"auto(cmo): GM 텔레그램 URL 기록 — {target.get('title', '?')} [{channel}]"
                )
                await asyncio.to_thread(_git_seq_locked, commit_msg)
                ctx.user_data.pop(_NAVER_PENDING_KEY, None)
                await update.message.reply_text(
                    f"✅ {target.get('title', '?')} — {channel} URL 기록 완료"
                )
                _try_notify_links(target)
                return True
            else:
                await update.message.reply_text(
                    f"⚠️ 1~{len(candidates)} 번호만 유효합니다. 다시 입력해 주세요."
                )
                return True
        else:
            # 숫자가 아닌 새 메시지 → pending 취소 후 URL 탐지로 계속
            ctx.user_data.pop(_NAVER_PENDING_KEY, None)

    # ── 2) 네이버 URL 탐지 ──────────────────────────────────────────────────
    url, channel = _extract_naver_url(prompt)
    if url is None:
        return False

    try:
        items = json.loads(REVIEW_QUEUE.read_text(encoding="utf-8"))
    except Exception as exc:
        await update.message.reply_text(f"⚠️ 큐 로드 실패: {exc}")
        return True

    candidates = _rq_candidates(items, channel)

    # ── 3-A) 정확히 1건 ─────────────────────────────────────────────────────
    if len(candidates) == 1:
        code, target = await asyncio.to_thread(
            _rq_record_url_locked, candidates[0].get("id"), url
        )
        if code.startswith("error:"):
            await update.message.reply_text(f"⚠️ 큐 기록 실패: {code[6:]}")
            return True
        if code == "missing":
            await update.message.reply_text(
                f"⚠️ 큐에서 항목을 찾지 못했습니다 (id={candidates[0].get('id')})."
            )
            return True
        if code == "dup":
            await update.message.reply_text(
                f"⚠️ 이미 URL이 기록된 항목입니다: {target.get('title')}\n"
                f"기존 URL: {target['post_url']}\n덮어쓰지 않습니다."
            )
            return True
        commit_msg = (
            f"auto(cmo): GM 텔레그램 URL 기록 — {target.get('title', '?')} [{channel}]"
        )
        await asyncio.to_thread(_git_seq_locked, commit_msg)
        await update.message.reply_text(
            f"✅ {target.get('title', '?')} — {channel} URL 기록 완료"
        )
        _try_notify_links(target)
        return True

    # ── 3-B) 여러 건 — 반드시 GM 확인 후 기록 ────────────────────────────────
    if len(candidates) > 1:
        lines = [
            f"GM, {channel} 대기 중인 글이 {len(candidates)}건 있습니다. 몇 번에 기록할까요?"
        ]
        for i, it in enumerate(candidates, 1):
            lines.append(f"  {i}. [{it.get('status', '')}] {it.get('title', it.get('id'))}")
        lines.append("\n숫자만 보내주시면 기록합니다.")
        ctx.user_data[_NAVER_PENDING_KEY] = {
            "url": url,
            "channel": channel,
            "candidates": [
                {"id": it["id"], "title": it.get("title", it.get("id"))}
                for it in candidates
            ],
        }
        await update.message.reply_text("\n".join(lines))
        return True

    # ── 3-C) 0건 ────────────────────────────────────────────────────────────
    await update.message.reply_text(
        f"GM, 대기 중인 {channel} 글이 없습니다. 콘텐츠명을 함께 알려주시면 찾아 기록할게요."
    )
    return True


async def _launch_publish_engine(item_ids: list, *, source: str = "tg") -> None:
    """검수 승인 항목의 발행 엔진(ig_review_publish_watcher.py --once) 비차단 기동.

    cmd_publish_callback(텔레그램 카드 승인)·cmd_m1_publish(M1 웹 승인 신호) 공용 경로
    — 2026-07-16 두 승인 경로를 '같은 동작(승인→발행)'으로 통일(CMO 배1170).
    source: 로그 헤더에 남기는 트리거 출처("tg"=텔레그램 카드, "m1-web"=M1 웹 승인).
    구 cmd_publish_callback 인라인 subprocess 블록을 추출 — 외부 동작(로그 위치·
    subprocess 인자·환경변수)은 그대로 보존.
    """
    _pub_log = WORKDIR / "logs" / "ig_publish_engine.log"
    try:
        _pub_log.parent.mkdir(parents=True, exist_ok=True)
        _pub_out = open(_pub_log, "a", encoding="utf-8", buffering=1)
        _pub_out.write(
            f"\n===== {time.strftime('%Y-%m-%d %H:%M:%S')} "
            f"publish --once ids={item_ids} src={source} =====\n"
        )
        _pub_out.flush()
    except Exception:
        _pub_out = asyncio.subprocess.DEVNULL  # 로그 열기 실패 시 안전 폴백
    await asyncio.create_subprocess_exec(
        str(_VENV_PY), "-u", str(_PUBLISH_ENGINE), "--once",
        cwd=str(WORKDIR),
        stdout=_pub_out,
        stderr=asyncio.subprocess.STDOUT,
        env=dict(os.environ, PYTHONIOENCODING="utf-8",
                 TELEGRAM_BOT_TOKEN=(TOKEN or "")),
    )


async def cmd_publish_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """콘텐츠 검수 카드 [✅승인]/[❌반려] 클릭 처리.

    callback_data 형식:
      단일:  ``pub:<id>:<approve|reject>``
      복수:  ``pub:<id1,id2,...>:<approve|reject>``  (콤마 구분, 그룹 일괄 승인)

    승인 → review_queue.json status='승인' 기록·커밋·푸시 → 발행 엔진
           (ig_review_publish_watcher.py --once) 비차단 호출. 엔진이 채널 분기
           발행·자체 텔레그램 보고(IG 0% 시 수동발행대기 폴백). 폴링 감시기 폐기 대체.
    반려 → status='반려' 기록·커밋.
    복수 id: 각 항목 모두 status 갱신 후 발행 엔진 1회 호출 (4채널 그룹 승인 지원).
    """
    q = update.callback_query
    if not q or not q.data or not q.data.startswith("pub:"):
        return
    await q.answer()
    parts = q.data.split(":")
    if len(parts) < 3:
        await q.answer("형식 오류", show_alert=False)
        return

    # 그룹 해시 방식: pub:grp:<hash>:<decision> → .review_card_groups.json 역조회
    _GROUPS_STORE = WORKDIR / "scripts" / ".review_card_groups.json"
    if len(parts) >= 4 and parts[1] == "grp":
        grp_hash = parts[2]
        decision = parts[3]
        id_field = "grp:" + grp_hash
        try:
            grp_map = json.loads(_GROUPS_STORE.read_text(encoding="utf-8"))
            item_ids = grp_map.get(grp_hash) or []
        except Exception:
            item_ids = []
        if not item_ids:
            await ctx.bot.send_message(chat_id=q.message.chat_id,
                text=f"⚠️ 그룹 해시를 찾지 못함: {grp_hash}")
            return
    else:
        # 복수 id 지원: 콤마 구분 분리 (단일 id는 리스트 1개)
        id_field = parts[1]
        decision = parts[2]
        item_ids = [x.strip() for x in id_field.split(",") if x.strip()]

    new_status = "승인" if decision == "approve" else "반려"
    # 락 임계구역에서 load→status 기록→save 를 한 번에 (스테일 덮어쓰기 차단)
    targets, missing, cancelled, rq_err = await asyncio.to_thread(
        _rq_set_status_locked, item_ids, new_status
    )
    if rq_err:
        await ctx.bot.send_message(chat_id=q.message.chat_id,
            text=f"⚠️ 발행 큐 처리 실패: {rq_err}\n🆔 {id_field}")
        return

    if missing:
        await ctx.bot.send_message(chat_id=q.message.chat_id,
            text=f"⚠️ 큐에서 항목을 찾지 못함: {', '.join(missing)}")
        if not targets:
            return

    if cancelled:
        cancelled_titles = ", ".join(c.get("title", c.get("id", "")) for c in cancelled)
        await ctx.bot.send_message(chat_id=q.message.chat_id,
            text=f"🚫 취소된 건입니다 — 발행하지 않습니다: {cancelled_titles}")
        if not targets:
            return

    # 저장은 위 _rq_set_status_locked 안(락 임계구역)에서 이미 원자적으로 끝났다.

    # 대표 타이틀·채널 (복수면 첫 항목 + 건수 표시)
    first = targets[0] if targets else {}
    title = first.get("title", id_field)
    channel = first.get("channel", "")
    if len(targets) > 1:
        title_label = f"{title} 외 {len(targets)-1}건"
        channel_label = f"{len(targets)}개 채널"
    else:
        title_label = title
        channel_label = channel

    log.info(f"[pub] decision={decision} ids={item_ids} ch={channel_label}")

    commit_msg = f"auto(cmo): 검수 {new_status} — {title_label} [{channel_label}]"
    await asyncio.to_thread(_git_seq_locked, commit_msg)

    label = "✅ 승인" if decision == "approve" else "❌ 반려"
    try:
        await q.edit_message_text(
            text=(q.message.text or title_label) + f"\n\n━━━━━━━━\n{label} 처리됨",
            reply_markup=None)
    except Exception:
        try:
            await q.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass

    if decision == "approve":
        try:
            # 발행엔진 출력을 로그로 남긴다(구 DEVNULL → 진단 사각 제거).
            # 2026-07-08 재발방지: DEVNULL 로 버려 EP01 발행실패의 진짜 사유
            # ('post 섹션 없음')가 '게시 URL 미회수'로 둔갑, 원인추적이 오래 걸린 사고.
            # 2026-07-16: subprocess 기동 로직은 _launch_publish_engine()으로 추출
            # (cmd_m1_publish 와 공용) — 이 콜백의 외부 동작은 무변경.
            await _launch_publish_engine(item_ids, source="tg")
            try:
                skip_pending_ping = muted("pending_ping")
            except Exception:
                skip_pending_ping = False
            if not skip_pending_ping:
                await ctx.bot.send_message(chat_id=q.message.chat_id,
                    text=f"⏳ <b>{title_label}</b> 발행 처리 시작 — 결과는 발행 엔진이 곧 보고합니다.",
                    parse_mode="HTML")
        except Exception as exc:
            await ctx.bot.send_message(chat_id=q.message.chat_id,
                text=f"⚠️ 발행 엔진 기동 실패: {exc}\n수동 발행 필요: {title_label}")


async def cmd_digest_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """발송요약(디제스트) GM 검토 카드 [✅ 실무진 방 발송]/[⛔ 보류] 클릭 처리.

    callback_data 형식: ``dig:<h8>:<a|r>`` (h8 = folder 그룹키의 md5 앞 8자리 —
    scripts/publish_digest.py send_publish_digest() 가 GM 검토 카드 발신 시 원장
    ledger[f"{folder}:gm_review"] = {"h8":..,"folder":..,"hash":..} 로 기록).

    승인(a) → ledger[f"{folder}:gm_ok"]=True 기록 후 send_publish_digest() 재호출 —
              이제 gm_ok 가 있으므로 그 함수가 실무진 문의·컨택·등록 알림방으로 실제 발신한다.
    보류(r) → ledger[f"{folder}:gm_hold"]=True 만 기록(실무진 방 미발송). gm_review 키는
              그대로 남아있어 다음 사이클에 다시 묻지 않는다(의도된 동작).
    2026-08-04 GM 지시("실무진 방으로 보내기 전에 항상 업무보고방에 보내줘 검토할게") 구현.
    """
    q = update.callback_query
    if not q or not q.data or not q.data.startswith("dig:"):
        return
    await q.answer()
    parts = q.data.split(":")
    if len(parts) != 3 or _digest is None:
        await q.answer("형식 오류" if _digest is not None else "게이트 모듈 미가용", show_alert=False)
        return
    h8, decision = parts[1], parts[2]

    ledger = _digest._load_ledger(_digest.SENT_LEDGER)
    folder = None
    for k, v in ledger.items():
        if k.endswith(":gm_review") and isinstance(v, dict) and v.get("h8") == h8:
            folder = v.get("folder")
            break
    if not folder:
        await q.answer("식별자를 찾지 못했습니다", show_alert=True)
        return

    if decision == "a":
        ledger[f"{folder}:gm_ok"] = True
        _digest._save_ledger(_digest.SENT_LEDGER, ledger)
        try:
            all_review_items = _digest._load_review_queue()
            entries = _digest._group_all_entries(folder, all_review_items)
            await asyncio.to_thread(_digest.send_publish_digest, entries, False, None)
        except Exception as exc:
            log.error(f"[digest] 승인 후 실무진 방 발신 실패: {exc}")
        try:
            await q.edit_message_text(text=f"✅ 실무진 방 발송 완료 — {folder}", reply_markup=None)
        except Exception:
            try:
                await q.edit_message_reply_markup(reply_markup=None)
            except Exception:
                pass
    else:
        ledger[f"{folder}:gm_hold"] = True
        _digest._save_ledger(_digest.SENT_LEDGER, ledger)
        try:
            await q.edit_message_text(text=f"⛔ 보류 — 실무진 방 미발송 — {folder}", reply_markup=None)
        except Exception:
            try:
                await q.edit_message_reply_markup(reply_markup=None)
            except Exception:
                pass


# ─── M1 웹 승인 ↔ 텔레그램 승인 통일 (/m1pub) — 2026-07-16 CMO, 배1170 ───────────
# GM 확정 방식='봇 발행 재사용': M1(웹 검수 SSOT, wellperion_guide(main).html)에서
# [승인] 클릭 → GAS _reviewSetStatus() 가 review_queue.json status='승인' 커밋 후
# _signalM1Publish() 로 이 봇에 "/m1pub <id>" 신호 발송 → 여기서 텔레그램 카드
# 승인(cmd_publish_callback)과 동일한 _launch_publish_engine() 을 호출한다.
# 라이브 발효 게이트: M1_AUTO_PUBLISH env(.env, 기본 0=OFF). OFF 동안은 신호 수신만
# 하고 발행하지 않는다(GM go 후 1로 전환 + 봇 재시작 = 라이브 발효).
_GM_CHAT_ID = 8254867551  # GM 텔레그램 챗 id (ssot/canon_values.json telegram_chat_id 정본과 동일)

# GM 개인 방(「나의하루」) — 개인 체크인 버튼이 이 방에서도 먹어야 한다(GM 2026-08-08).
# .env 를 읽는다: 이 프로세스는 os.environ 에 .env 를 싣지 않으므로 파일에서 직접 뽑는다.
def _read_personal_chat_id() -> str:
    try:
        p = Path(__file__).resolve().parent / ".env"
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("TELEGRAM_PERSONAL_CHAT_ID="):
                return line.split("=", 1)[1].strip()
    except Exception:
        pass
    return ""


_ENV_PERSONAL_CHAT_ID = _read_personal_chat_id()


def _git_pull_locked() -> None:
    """GAS가 GitHub에 직접 커밋한 review_queue.json status='승인'을 로컬로 당긴다.
    _git_seq_locked 와 동일 GitLock 임계구역(파괴적 옵션 없음) — 동시 커밋으로 인한
    레포 손상 방지(reference_guidehub_concurrent_commit_corruption 교훈). 동기·블로킹
    이므로 asyncio.to_thread 로 호출.
    pull 은 --autostash 대신 pull_rebase_safe 사용(2026-07-30·INC-034 잔존 제거)."""
    def _seq():
        if pull_rebase_safe is not None:
            pull_rebase_safe(str(WORKDIR), str(WORKDIR), "bot:m1pub")
        else:
            log.warning("[m1pub] pull_rebase_safe 미가용 — pull 건너뜀(--autostash 재도입 금지)")

    try:
        if GitLock is not None:
            with GitLock(holder="bot:m1pub", repo_root=str(WORKDIR)):
                _seq()
        else:  # 모듈 임포트 실패 시 폴백 — 무락 순차(최소한 봇은 죽지 않음)
            log.warning("[m1pub] GitLock 미가용 — 무락 순차 pull 폴백")
            _seq()
    except Exception as exc:  # 락 타임아웃 등 — 무방비 진행 금지
        log.error(f"[m1pub] git lock/pull 실패: {exc}")


async def cmd_m1_publish(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """M1 웹 검수 SSOT [승인] 신호 수신 — ``/m1pub <검수id>``.

    GAS _signalM1Publish() 가 status='승인' 커밋 직후 이 명령을 GM 챗으로 보낸다.
    ①GM 챗 아니면 무시 ②id 없음=사용법 안내 ③pull 후 status≠승인=보류 안내
    ④게이트(M1_AUTO_PUBLISH) OFF=안내만·발행 안 함 ⑤ON+승인=발행 엔진 기동.
    """
    try:
        if not update.effective_chat or update.effective_chat.id != _GM_CHAT_ID:
            return  # GM 챗 아니면 조용히 무시(보안)

        args = ctx.args or []
        if not args:
            await update.message.reply_text("사용법: /m1pub <검수id>")
            return
        item_id = args[0].strip()

        # GAS가 GitHub에 커밋한 최신 status를 로컬로 반영 (동시커밋 위험 방지 — 직렬화 pull)
        await asyncio.to_thread(_git_pull_locked)

        try:
            items = json.loads(REVIEW_QUEUE.read_text(encoding="utf-8"))
        except Exception as exc:
            await update.message.reply_text(f"⚠️ 검수 큐 로드 실패: {exc}\n🆔 {item_id}")
            return

        target = next((it for it in items if it.get("id") == item_id), None)
        if target is None:
            await update.message.reply_text(f"⚠️ 검수 큐에서 항목을 찾지 못함: {item_id}")
            return

        status = target.get("status", "")
        title = target.get("title", item_id)
        if status != "승인":
            await update.message.reply_text(
                f"⏸️ {title} — status='{status}'(승인 아님) → 발행 보류 🆔 {item_id}")
            return

        if not M1_AUTO_PUBLISH:
            await update.message.reply_text(
                f"🔒 M1 승인 신호 수신 — {title} · 게이트 OFF라 발행 보류"
                f"(라이브=.env M1_AUTO_PUBLISH=1+봇 재시작)")
            return

        await _launch_publish_engine([item_id], source="m1-web")
        await update.message.reply_text(f"⏳ <b>{title}</b> 발행 처리 시작", parse_mode="HTML")
    except Exception as exc:
        try:
            await ctx.bot.send_message(chat_id=_GM_CHAT_ID, text=f"⚠️ /m1pub 처리 실패: {exc}")
        except Exception:
            log.error(f"[m1pub] 예외+안내 발송도 실패: {exc}")


# ─── 카톡 매출보고 원클릭 3방 전송 콜백 (kakao_send) — 2026-07-06 CTO, 배488(확장) ───
# 9시 매출보고 사진 아래 인라인버튼 "📤 카톡 3방 전송" 탭 → 그 메시지의 사진(file_id)+캡션을
# 로컬 월 폴더(archive_dir)에 수신일 기준 파일명으로 저장 후, 그 저장본을 그대로
# scripts/kakao_report_sender.py 로 카톡 방 3개(kakao_rooms.json) 실발송(중복 다운로드 없음).
# 방별 캡션 prefix(예: 회장님방 "회장님, ")는 sender가 kakao_rooms.json에서 읽어 조합한다.
# 이미지 재생성 없음·시트 접근 없음. GAS(매출보고_자동발송.js sendTelegramPhoto)가 버튼을 붙인다.
_KAKAO_SENDER = WORKDIR / "scripts" / "kakao_report_sender.py"
_KAKAO_ROOMS_CONFIG = WORKDIR / "scripts" / "kakao_rooms.json"
_KAKAO_DEFAULT_ARCHIVE_DIR = WORKDIR / "1. AI자료_아카이브" / "10_매출보고"
_KAKAO_STATUS_FILE = WORKDIR / "status" / "kakao_last_send.json"


def _kakao_archive_dir() -> Path:
    """kakao_rooms.json의 archive_dir 읽기(없으면 기본값). 저장소 밖 GM 개인 폴더 기본."""
    try:
        cfg = json.loads(_KAKAO_ROOMS_CONFIG.read_text(encoding="utf-8"))
        raw = cfg.get("archive_dir")
        if raw:
            return Path(raw).expanduser()
    except Exception:
        pass
    return _KAKAO_DEFAULT_ARCHIVE_DIR


# status/kakao_last_send.json 기록은 여기서 하지 않는다(2026-08-04 CTO) — 관문
# kakao_report_sender.py의 write_status()가 단일 기록 지점(--status-file 로 전달).
# 예전엔 이 콜백도 자체 write_kakao_status()로 같은 파일에 따로 썼는데(스키마도 kind
# 필드가 빠져 다른 두 곳과 어긋나 있었다), 사람이 kakao_report_sender.py를 직접 불러
# 재발송하면 이 콜백도 kakao_auto_daily_report.py도 안 거치므로 그 결과가 어디에도
# 안 남았다(09:34 3방 재발송 사고, 2026-08-04) — 관문 한 곳으로 옮겨 해결한다.


async def cmd_kakao_send_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """callback_data == "kakao_send" 처리 — 버튼 달린 메시지의 사진+캡션을 카톡 3방 전송.

    이미지는 그 텔레그램 메시지 그대로(file_id→getFile→다운로드) 로컬 월 폴더에 archive 저장
    (경로: <archive_dir>/YYYY-MM/웰페리온_일일보고_YYYYMMDD.png, 날짜=수신일 기준),
    그 저장본을 그대로 전송에 사용(중복 다운로드 없음). 캡션은 원본 그대로 전달 —
    방별 prefix 조합은 kakao_report_sender.py가 kakao_rooms.json 기준으로 수행한다.
    실행은 서브프로세스(kakao_report_sender.py, 옵션 없음=3방 실발송)로 위임하고
    결과 1줄만 회신한다. 카톡 UI 자동화 실패는 방별 사유와 함께 그대로 노출한다."""
    q = update.callback_query
    if not q or not q.data or q.data != "kakao_send":
        return
    await q.answer()

    msg = q.message
    photos = getattr(msg, "photo", None) if msg else None
    if not msg or not photos:
        await ctx.bot.send_message(
            chat_id=(msg.chat_id if msg else q.from_user.id),
            text="⚠️ 카톡 전송 실패: 이 메시지에서 사진을 찾지 못했습니다.")
        return

    caption = msg.caption or ""
    file_id = photos[-1].file_id  # 최대 해상도

    try:
        await q.edit_message_reply_markup(reply_markup=None)  # 중복 탭 방지 — 버튼 즉시 제거
    except Exception:
        pass

    await ctx.bot.send_message(chat_id=msg.chat_id, text="⏳ 카톡 3방 전송 처리 시작...")

    try:
        import datetime as _dt
        tg_file = await ctx.bot.get_file(file_id)
        today = _dt.datetime.now()  # 수신일 기준(보고 캡션 날짜 아님)
        month_dir = _kakao_archive_dir() / today.strftime("%Y-%m")
        month_dir.mkdir(parents=True, exist_ok=True)
        local_path = month_dir / f"웰페리온_일일보고_{today.strftime('%Y%m%d')}.png"
        await tg_file.download_to_drive(str(local_path))
    except Exception as exc:
        await ctx.bot.send_message(chat_id=msg.chat_id,
            text=f"⚠️ 카톡 전송 실패: 이미지 다운로드/archive 저장 오류 — {exc}")
        return

    out_text = ""
    try:
        proc = await asyncio.create_subprocess_exec(
            str(_VENV_PY), "-u", str(_KAKAO_SENDER),
            "--image", str(local_path), "--caption", caption,
            "--status-file", str(_KAKAO_STATUS_FILE), "--status-kind", "IMAGE_REPORT",
            # --sender 매출보고 — kakao_report_sender 사람 방 발신 가드(배 11070 ⑤) 통과용
            # (기본 3~4방에 사람 방 ★운영부가 섞여 있다). GM이 직접 버튼을 눌러 보내는
            # 것도 같은 매출보고 파이프라인의 수동 트리거일 뿐 내용은 동일하다.
            "--sender", "매출보고",
            cwd=str(WORKDIR),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env=dict(os.environ, PYTHONIOENCODING="utf-8"),
        )
        out, _ = await proc.communicate()
        out_text = (out or b"").decode("utf-8", errors="replace")
        log.info(f"[kakao_send] rc={proc.returncode} out_tail={out_text[-500:]}")
    except Exception as exc:
        await ctx.bot.send_message(chat_id=msg.chat_id,
            text=f"⚠️ 카톡 전송 실패: 실행 오류 — {exc}")
        return

    if proc.returncode == 0 and "DONE:" in out_text:
        # ★DONE 줄을 그대로 보여준다(정적 "완료" 문구로 뭉개지 않는다) — 일부 방이 가드에
        # 걸려 보류돼도(예: 웰리_승인_필요) "(미발신 N개: [...])"가 DONE 줄에 이미 담겨
        # 있다. 예전엔 여기서 고정 문구로 덮어써 부분 보류가 GM 눈에 안 보였다(배 11070 ⑤ 후속).
        done_line = next((ln for ln in out_text.strip().splitlines() if ln.startswith("DONE:")),
                         "DONE: 전송 완료")
        await ctx.bot.send_message(chat_id=msg.chat_id, text=f"✅ {done_line}")
    else:
        tail = out_text.strip().splitlines()[-1] if out_text.strip() else "알 수 없는 오류"
        await ctx.bot.send_message(chat_id=msg.chat_id, text=f"⚠️ 카톡 전송 실패: {tail}")


async def cmd_checkin_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """GM 개인 하루 체크인 버튼 — callback_data ck:t:{토막} / ck:m:{기분} / ck:save / ck:skip.

    2026-08-08 GM 승인(A안). G1 「오늘 체크인」이 11칸 손입력이라 이틀 만에 끊긴 것을,
    저녁에 봇이 묻고 버튼만 누르는 구조로 옮긴 것이다. 글자 입력이 없다.

    토막·기분은 누를 때마다 파일에 바로 쓰되 커밋은 안 한다(하루에 열 번 쌓이지 않게).
    커밋은 [💾 저장] 한 번에만. 판정·저장 로직은 scripts/gm_checkin.py 단일 출처.
    """
    q = update.callback_query
    if not q or not q.data:
        return
    if _checkin is None:
        await q.answer("체크인 모듈을 불러오지 못했습니다", show_alert=True)
        return
    # GM 본인 방 또는 개인 방(「나의하루」)에서만 — 개인 기록이다.
    # ★개인 방을 빠뜨리면 카드는 가는데 버튼이 안 먹는다(2026-08-08 실측 직전에 잡음).
    _allowed = {_GM_CHAT_ID}
    _personal = os.environ.get("TELEGRAM_PERSONAL_CHAT_ID") or _ENV_PERSONAL_CHAT_ID
    if _personal:
        try:
            _allowed.add(int(_personal))
        except ValueError:
            pass
    if q.message and q.message.chat_id not in _allowed:
        await q.answer()
        return

    data = q.data
    # ── 저녁 설문(한 번에 하나씩) — ck:q:{문항}:{답} ──────────────────────────
    #   같은 메시지를 문항마다 갈아 끼운다. 답은 누른 즉시 저장 — 중간에 그만두셔도
    #   답한 데까지가 그날 기록이다. 마지막 문항을 넘기면 마무리 화면 + 커밋.
    if data.startswith("ck:q:"):
        try:
            _, _, idx_s, code = data.split(":", 3)
            idx = int(idx_s)
            if code:                       # 빈 code = [🔧 다시 답하기] — 저장 없이 그 문항으로
                await asyncio.to_thread(_checkin.set_answer, idx, code)
                idx += 1
            step = _checkin.build_step(idx)
            if idx > len(_checkin.TOROKS):
                await asyncio.to_thread(_checkin.commit)
            markup = None
            if step.get("markup"):
                markup = InlineKeyboardMarkup([
                    [InlineKeyboardButton(b["text"], callback_data=b["callback_data"]) for b in row]
                    for row in step["markup"]["inline_keyboard"]])
            await q.edit_message_text(text=step["text"], reply_markup=markup)
            await q.answer()
        except Exception as exc:
            log.error(f"[checkin] 설문 처리 실패: {exc}")
            await q.answer("처리 실패 — 다시 눌러 주세요", show_alert=True)
        return

    # ── 시점별 체크(끼니·운동) — ck:s:{슬롯}:{축}:{O|X} ─────────────────────────
    #   저녁 설문(ck:q:)과 같은 갈아 끼우기 방식. 슬롯 안 항목을 다 답하면 요약으로 바뀌고
    #   그때 커밋한다(build_slot 이 markup 없이 돌려주는 게 곧 '다 답했다' 신호).
    if data.startswith("ck:s:"):
        try:
            _, _, slot_id, axis, code = data.split(":", 4)
            await asyncio.to_thread(_checkin.set_slot_answer, slot_id, axis, code)
            step = await asyncio.to_thread(_checkin.build_slot, slot_id)
            if not step.get("markup"):
                await asyncio.to_thread(_checkin.commit)
            markup = None
            if step.get("markup"):
                markup = InlineKeyboardMarkup([
                    [InlineKeyboardButton(b["text"], callback_data=b["callback_data"]) for b in row]
                    for row in step["markup"]["inline_keyboard"]])
            await q.edit_message_text(text=step["text"], reply_markup=markup)
            await q.answer()
        except Exception as exc:
            log.error(f"[checkin] 시점 카드 처리 실패: {exc}")
            await q.answer("처리 실패 — 다시 눌러 주세요", show_alert=True)
        return

    # ── 저녁 정리 카드(오늘 하신 일) — ck:r:{인덱스} ────────────────────────────
    #   GM 지시 2026-08-10 — 08:00 업무 브리핑의 짝(저녁판). 「아직 남은 것」 버튼을 누르면
    #   그 항목만 확인 표시로 바뀐다. 저장 로직은 gm_checkin.ack_recap_item 단일 출처.
    if data.startswith("ck:r:"):
        try:
            idx = int(data[5:])
            step = await asyncio.to_thread(_checkin.ack_recap_item, idx)
            markup = None
            if step.get("markup"):
                markup = InlineKeyboardMarkup([
                    [InlineKeyboardButton(b["text"], callback_data=b["callback_data"]) for b in row]
                    for row in step["markup"]["inline_keyboard"]])
            await q.edit_message_text(text=step["text"], reply_markup=markup)
            await q.answer("확인했습니다")
        except Exception as exc:
            log.error(f"[checkin] 저녁정리 확인 처리 실패: {exc}")
            await q.answer("처리 실패 — 다시 눌러 주세요", show_alert=True)
        return

    try:
        if data.startswith("ck:t:"):
            _checkin.toggle(data[5:])
            await q.answer()
        elif data.startswith("ck:m:"):
            _checkin.set_mood(data[5:])
            await q.answer()
        elif data == "ck:skip":
            await q.edit_message_text(text="오늘은 건너뜁니다. 내일 다시 여쭙겠습니다.",
                                      reply_markup=None)
            return
        elif data == "ck:save":
            line = _checkin.summary()
            ok = await asyncio.to_thread(_checkin.commit)
            tail = "" if ok else "\n(저장은 됐고 업로드만 다음 차례에 따라갑니다)"
            await q.edit_message_text(text=f"✅ 오늘 체크인 저장\n{line}{tail}", reply_markup=None)
            await q.answer()
            return
        else:
            await q.answer()
            return
    except Exception as exc:
        log.error(f"[checkin] 처리 실패: {exc}")
        await q.answer("처리 실패 — 잠시 후 다시 눌러 주세요", show_alert=True)
        return

    # 누른 결과가 버튼에 그대로 보이게 갱신(✅ 표시). 내용이 같으면 텔레그램이 거부하므로 무시한다.
    try:
        await q.edit_message_reply_markup(
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(b["text"], callback_data=b["callback_data"]) for b in row]
                for row in _checkin.build_markup()["inline_keyboard"]
            ]))
    except Exception:
        pass


# ── 중복 기동 방지 PID 락 (daily_scheduler.py와 동일 패턴, 2026-06-02) ──────────
_PID_FILE = BASE / "bot.pid"


def _check_pid_lock() -> None:
    """재기동 시 기존 bot.py 인스턴스를 kill 후 자신이 단일 주인으로 기동.
    (구 로직: 기존 있으면 자신 종료 → 재기동 시도 시 봇이 영영 안 뜨는 문제 수정)"""
    my_pid = os.getpid()
    if _PID_FILE.exists():
        try:
            old_pid = int(_PID_FILE.read_text().strip())
            if old_pid == my_pid:
                # 자기 자신 — 재진입 없음
                return
            # ★2026-08-01(시토 · 배265) — PID 재사용 오탐 차단.
            #   여기선 오탐이 더 위험하다: 재배정된 PID 를 '옛 봇'으로 보고
            #   taskkill /F 하면 **엉뚱한 시스템 프로세스를 죽인다**(같은 날
            #   daily_scheduler 쪽 PID 2824 가 실제로 svchost 였다).
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {old_pid}",
                 "/FI", "IMAGENAME eq python*", "/FO", "CSV"],
                capture_output=True, text=True, shell=True,
            )
            if str(old_pid) in result.stdout:
                # 기존 봇 프로세스 강제 종료 후 자신이 새 주인
                subprocess.run(
                    ["taskkill", "/F", "/PID", str(old_pid)],
                    capture_output=True, shell=True,
                )
                print(f"[bot] 기존 인스턴스(PID {old_pid}) kill 완료 — 1초 대기", flush=True)
                time.sleep(1)  # 소켓 해제 대기
        except SystemExit:
            raise
        except Exception:
            pass
    _PID_FILE.write_text(str(my_pid))


def _ensure_no_webhook() -> None:
    """시작 시 웹훅이 걸려 있으면 자동 삭제 — getUpdates Conflict 재발 방지."""
    try:
        info = requests.get(f"https://api.telegram.org/bot{TOKEN}/getWebhookInfo", timeout=10).json()
        if info.get("result", {}).get("url"):
            requests.get(f"https://api.telegram.org/bot{TOKEN}/deleteWebhook", timeout=10)
            log.info("[bot] 웹훅 자동 삭제 완료 (Conflict 방지)")
    except Exception as exc:
        log.warning(f"[bot] 웹훅 확인/삭제 실패(무시): {exc}")


_HB_APP = None            # 폴링 상태를 물어볼 Application (main 에서 채운다)
_hb_down_logged = False   # 같은 사유를 매 회차 로그에 도배하지 않기 위한 1회 표시


def _polling_alive() -> bool:
    """지금 '받는 쪽'이 실제로 돌고 있나.

    ★2026-08-08 배468 — 이걸 안 보던 것이 이 배의 뿌리다.
      그 전엔 하트비트를 무조건 5분마다 찍었다. 그런데 하트비트는 **별도 스레드**라
      폴링 루프가 죽어도 계속 찍힌다 — 발신(sendMessage)은 API 직접 호출이라 그대로 나가고,
      하트비트도 정상이니 어떤 감시기도 '승인 버튼이 안 닿는 상태'를 못 잡았다.
      실측(2026-08-08): 봇 기록이 10:10 Bad Gateway 이후 멈췄는데 하트비트는 12:01 에도 찍혔다.
      시모가 배398 시운전 중 손으로 확인해서야 드러났다.
    ▸이제 폴링이 멈추면 하트비트를 **안 찍는다.** 그러면 파일이 낡고, 이미 있는
      20분 신선도 점검(scripts/telegram_health_check.py _check_heartbeat)이 그대로 잡아낸다.
      새 파일·새 감시기·새 형식 없음 — 있던 점검이 진실을 보게 만드는 것이 전부다(약속 L21).
    ▸판단이 안 서면(앱을 아직 모르거나 속성이 없으면) 살아 있는 것으로 본다 —
      확신 없이 '죽었다'고 적으면 멀쩡한 봇에 경보가 울린다.
    """
    app = _HB_APP
    if app is None:
        return True
    up = getattr(app, "updater", None)
    if up is None:
        return True
    running = getattr(up, "running", None)
    return True if running is None else bool(running)


def _write_heartbeat() -> None:
    """폴링이 살아 있을 때만 생존 신호 기록. temp write + replace 로 원자적 기록."""
    global _hb_down_logged
    import datetime as _dt
    if not _polling_alive():
        if not _hb_down_logged:
            log.error("[bot] 받는 쪽(폴링)이 멈춰 하트비트를 찍지 않는다 — "
                      "13시 상태 점검이 '미갱신'으로 잡아낸다. 재기동 필요.")
            _hb_down_logged = True
        return
    _hb_down_logged = False
    try:
        tmp = HEARTBEAT_FILE.with_suffix(".tmp")
        tmp.write_text(_dt.datetime.now().isoformat(), encoding="utf-8")
        tmp.replace(HEARTBEAT_FILE)
    except Exception as exc:
        log.warning(f"[bot] 하트비트 기록 실패(무시): {exc}")


def _heartbeat_loop() -> None:
    """5분마다 하트비트 기록 — daemon 스레드 폴백(job_queue 미설치 환경용)."""
    while True:
        _write_heartbeat()
        time.sleep(300)


async def _heartbeat_job(context) -> None:
    """job_queue 콜백(설치돼 있을 때 우선 사용)."""
    _write_heartbeat()


def main():
    _check_pid_lock()  # 중복 봇 기동 차단 (자동기동 + 수동 배치 충돌 방지)
    _ensure_no_webhook()  # 웹훅 활성 시 자동 삭제 — getUpdates Conflict 재발 방지
    _install_outbound_logging()  # 발신 공용 로깅 래핑(best-effort, 발신 무영향)
    # Python 3.14 호환성: run_polling 내부의 get_event_loop 호출 대응
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())

    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("new", cmd_new))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("stopbot", cmd_stop))
    # /복구 (/restart) — 깨진 원격 Claude 세션 재기동 (2026-06-07 CTO).
    # 한글 /복구 는 telegram CommandHandler 가 ASCII 만 허용하므로 handle_message
    # 선처리로 라우팅(아래). /restart 영문 별칭만 CommandHandler 로 등록.
    app.add_handler(CommandHandler("restart", cmd_recover))
    # 문구 DB 명령어 (v1.1) — 영문 커맨드로 등록 (telegram 라이브러리 ASCII 전용 제약)
    app.add_handler(CommandHandler("quote_add", cmd_quote_add))
    app.add_handler(CommandHandler("quote_delete", cmd_quote_delete))
    app.add_handler(CommandHandler("quote_list", cmd_quote_list))
    # 결재 콜백 등록은 옵션 A(2026-05-28)로 비활성 — 결재 처리는 결재 SSOT 페이지에서 단일 진행.
    # cmd_approval_callback 함수는 보존 (텔레그램 인라인 ✅/❌ 패턴 복원 시 재등록).
    # app.add_handler(CallbackQueryHandler(cmd_approval_callback, pattern=r"^sign:"))
    # 콘텐츠 검수 발행 콜백 (pub:) — IG 폴링 감시기 폐기 대체 (2026-06-03). 결재(sign:)와 별개.
    app.add_handler(CallbackQueryHandler(cmd_publish_callback, pattern=r"^pub:"))
    # 발송요약 GM 검토 게이트 콜백 (dig:) — 실무진 방 발송 전 GM 승인/보류 (2026-08-04).
    app.add_handler(CallbackQueryHandler(cmd_digest_callback, pattern=r"^dig:"))
    # M1 웹 승인 신호 (/m1pub) — GAS _signalM1Publish() 가 보냄. 텔레그램 카드 승인과
    # 동일 발행 트리거로 수렴(2026-07-16 CMO, 배1170). 게이트=M1_AUTO_PUBLISH(기본 OFF).
    app.add_handler(CommandHandler("m1pub", cmd_m1_publish))
    # 카톡 매출보고 원클릭 3방 전송 콜백 (kakao_send) — 2026-07-06 CTO, 배488.
    # 코드만 등록 — 발효는 다음 봇 자동재기동 때(GM PC 재부팅 또는 아침 자동재기동).
    app.add_handler(CallbackQueryHandler(cmd_kakao_send_callback, pattern=r"^kakao_send$"))
    # GM 개인 하루 체크인 (ck:) — 2026-08-08 GM 승인 A안. 21:30 daily_scheduler 가 보낸
    # 카드의 토막·기분 버튼과 저장/건너뜀 처리. 저장은 gm_personal_routine.json 한 파일만 건드린다.
    app.add_handler(CallbackQueryHandler(cmd_checkin_callback, pattern=r"^ck:"))
    app.add_handler(MessageHandler(filters.PHOTO | filters.VIDEO, handle_media))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(error_handler)

    # ── 하트비트 기동 (2026-07-03 CTO, 배102) ─────────────────────────────────
    # job_queue(apscheduler+pytz) 설치돼 있으면 그걸 우선 사용, 없으면 daemon
    # 스레드로 폴백 — 현재 환경은 pytz 미설치라 스레드 경로를 탄다.
    global _HB_APP
    _HB_APP = app          # 하트비트가 '폴링이 실제로 도는지'를 물어볼 수 있게 (배468)
    if app.job_queue is not None:
        app.job_queue.run_repeating(_heartbeat_job, interval=300, first=5)
        log.info("[bot] 하트비트: job_queue 기반 (300s)")
    else:
        threading.Thread(target=_heartbeat_loop, daemon=True, name="heartbeat").start()
        log.info("[bot] 하트비트: daemon 스레드 기반 (job_queue 미설치, 300s)")

    log.info(
        f"Bot starting. cwd={WORKDIR} state={STATE_FILE} log={LOG_FILE} "
        f"claude_bin={CLAUDE_BIN}"
    )

    # ── 폴링 크래시 방어 감시 루프 (2026-07-03 CTO, INC·배102) ──────────────────
    # 오늘 10:11 telegram.error.NetworkError: Bad Gateway 로 run_polling() 프로세스
    # 전체가 죽어(PTB 21.6 내부 getUpdates 재시도 경로를 벗어난 예외로 추정) 수신
    # (GM 승인·콜백)이 4.5h 다운됐다(bot.log 10:11:13 이후 6h 무기록 확인).
    # run_polling()은 정상 종료 신호(SIGINT/SIGTERM)는 내부(__run)에서 흡수해
    # '정상 반환'하므로, 여기서는 "정상 반환=종료" · "예외 발생=일시 오류→재연결"
    # 로 구분해 지수 백오프(5s→최대 60s)로 재기동한다.
    # 싱글톤 pid락(_check_pid_lock)·웹훅가드(_ensure_no_webhook, 위에서 1회만 실행)·
    # error_handler·핸들러 등록·drop_pending_updates=False(다운 중 미수신 메시지도
    # 재기동 후 처리)는 전부 무변경.
    _backoff = 5
    while True:
        try:
            app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=False)
            break  # 정상 반환(정상 종료 신호) — 재기동하지 않고 프로세스 종료
        except (KeyboardInterrupt, SystemExit):
            # run_polling()이 보통 내부에서 흡수해 여기까지 안 오지만, 혹시 올라와도
            # 정상 종료 신호는 그대로 통과시켜 프로세스를 끝낸다(재기동 금지).
            raise
        except Exception as exc:
            log.error(
                f"[bot] run_polling 크래시(일시 네트워크 오류 추정) — "
                f"{_backoff}s 후 재연결: {exc}",
                exc_info=True,
            )
            time.sleep(_backoff)
            _backoff = min(_backoff * 2, 60)
            # run_polling()은 close_loop=True로 종료 시 이벤트 루프를 닫는다.
            # 재기동 전 새 루프를 설정하지 않으면 RuntimeError: Event loop is
            # closed 로 재기동 자체가 실패한다.
            asyncio.set_event_loop(asyncio.new_event_loop())


if __name__ == "__main__":
    main()
