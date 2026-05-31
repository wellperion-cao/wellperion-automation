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
import json
import logging
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

import requests

from telegram import Update, constants
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

BASE = Path(__file__).parent
STATE_FILE = BASE / "state.json"
ENV_FILE = BASE / ".env"
LOG_FILE = BASE / "bot.log"

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
    """_queue.json 저장."""
    try:
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
    ok = _patch_approval(task_id, status_value, approval_result, comment)
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


async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await authorized(update):
        return

    prompt = update.message.text
    if not prompt:
        return

    _inbox_log("in", "GM", prompt)

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


def main():
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
    # 문구 DB 명령어 (v1.1) — 영문 커맨드로 등록 (telegram 라이브러리 ASCII 전용 제약)
    app.add_handler(CommandHandler("quote_add", cmd_quote_add))
    app.add_handler(CommandHandler("quote_delete", cmd_quote_delete))
    app.add_handler(CommandHandler("quote_list", cmd_quote_list))
    # 결재 콜백 등록은 옵션 A(2026-05-28)로 비활성 — 결재 처리는 결재 SSOT 페이지에서 단일 진행.
    # cmd_approval_callback 함수는 보존 (텔레그램 인라인 ✅/❌ 패턴 복원 시 재등록).
    # app.add_handler(CallbackQueryHandler(cmd_approval_callback, pattern=r"^sign:"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(error_handler)

    log.info(
        f"Bot starting. cwd={WORKDIR} state={STATE_FILE} log={LOG_FILE} "
        f"claude_bin={CLAUDE_BIN}"
    )
    # drop_pending_updates=False: 봇 재시작 전 미수신 메시지도 처리
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=False)


if __name__ == "__main__":
    main()
