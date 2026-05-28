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
from bidirectional_handler import (
    classify_message as _bidir_classify,
    push_to_inbox as _bidir_push_inbox,
)

BASE = Path(__file__).parent
STATE_FILE = BASE / "state.json"
ENV_FILE = BASE / ".env"
LOG_FILE = BASE / "bot.log"

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

# inbox_watcher가 사용하는 환경변수를 os.environ에 동기화 (옵션 c 통합, 2026-05-23)
for _k in ("TELEGRAM_BOT_TOKEN", "NOTION_API_KEY", "INBOX_DB_ID"):
    if _k in ENV and not os.environ.get(_k):
        os.environ[_k] = ENV[_k]

# 인박스 DB 적재 (옵션 c 통합, 2026-05-23)
try:
    from inbox_watcher import push_to_notion_inbox as _push_inbox
except Exception:
    _push_inbox = None
TOKEN = ENV.get("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise RuntimeError(".env 에 TELEGRAM_BOT_TOKEN 미정의")

# ── Notion 문구 DB 연동 상수 ─────────────────────────────────────────────────
NOTION_TOKEN = ENV.get("NOTION_TOKEN", "")
NOTION_QUOTE_DB_ID = ENV.get("NOTION_QUOTE_DB_ID", "b8e60ed9-53ab-472b-ab8b-fc6c91d138e6")
NOTION_HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}

# ── 결재 회신 라우터 상수 ─────────────────────────────────────────────────────
# Start 기획DB / 운영 아카이브DB / 업무자동화DB
PLANNING_DB_ID   = ENV.get("NOTION_PLANNING_DB_ID",   "3430407d-a948-8156-afde-e663227cb7a1")
ARCHIVE_DB_ID    = ENV.get("NOTION_ARCHIVE_DB_ID",    "3430407d-a948-819d-8769-f739221cf4c8")
AUTOMATION_DB_ID = ENV.get("NOTION_AUTOMATION_DB_ID", "aac275a4-fd54-4d97-8971-4f7050de4f6e")

# 결재 키워드 → (상태값, 승인결과값)
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


# ── 문구 DB 명령어 (v1.1) ─────────────────────────────────────────────────────

def _notion_add_quote(time_slot: str, content: str) -> dict | None:
    """Notion 문구 DB에 새 항목 추가. 성공 시 page dict 반환."""
    if not NOTION_TOKEN:
        return None
    payload = {
        "parent": {"database_id": NOTION_QUOTE_DB_ID},
        "properties": {
            "문구": {"title": [{"type": "text", "text": {"content": content}}]},
            "시간대": {"select": {"name": time_slot}},
            "활성": {"checkbox": True},
        },
    }
    try:
        resp = requests.post(
            "https://api.notion.com/v1/pages",
            headers=NOTION_HEADERS,
            json=payload,
            timeout=15,
        )
        if resp.status_code == 200:
            return resp.json()
        return None
    except Exception:
        return None


def _notion_deactivate_quote(page_id: str) -> bool:
    """문구 페이지 활성=False 처리."""
    if not NOTION_TOKEN:
        return False
    try:
        resp = requests.patch(
            f"https://api.notion.com/v1/pages/{page_id}",
            headers=NOTION_HEADERS,
            json={"properties": {"활성": {"checkbox": False}}},
            timeout=15,
        )
        return resp.status_code == 200
    except Exception:
        return False


def _notion_list_quotes(time_slot: str) -> list[dict]:
    """해당 시간대 활성 문구 목록 반환."""
    if not NOTION_TOKEN:
        return []
    try:
        payload = {
            "filter": {
                "and": [
                    {"property": "시간대", "select": {"equals": time_slot}},
                    {"property": "활성", "checkbox": {"equals": True}},
                ]
            },
            "page_size": 20,
        }
        resp = requests.post(
            f"https://api.notion.com/v1/databases/{NOTION_QUOTE_DB_ID}/query",
            headers=NOTION_HEADERS,
            json=payload,
            timeout=15,
        )
        if resp.status_code == 200:
            return resp.json().get("results", [])
        return []
    except Exception:
        return []


async def cmd_quote_add(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    /문구추가 06 "내용" 또는 /문구추가 18 내용
    """
    if not await authorized(update):
        return
    raw = update.message.text or ""
    # 명령어 부분 제거
    body = re.sub(r"^/문구추가\s*", "", raw).strip()
    # 시간대 파싱: 06 또는 18
    m = re.match(r"^(06|18)\s+(.+)$", body, re.DOTALL)
    if not m:
        await update.message.reply_text(
            "사용법: `/문구추가 06 내용` 또는 `/문구추가 18 내용`\n"
            "시간대는 06 또는 18만 허용됩니다.",
            parse_mode="Markdown",
        )
        return
    slot_raw, content = m.group(1), m.group(2).strip().strip('"').strip("'")
    time_slot = f"{slot_raw}시"

    if not NOTION_TOKEN:
        await update.message.reply_text("NOTION_TOKEN 미설정 — .env 확인 필요")
        return

    result = _notion_add_quote(time_slot, content)
    if result:
        page_id = result.get("id", "")
        await update.message.reply_text(
            f"문구 등록 완료\n"
            f"시간대: {time_slot}\n"
            f"내용: {content}\n"
            f"페이지 ID: `{page_id}`",
            parse_mode="Markdown",
        )
    else:
        await update.message.reply_text("문구 등록 실패 — Notion API 오류. 로그 확인 필요.")


async def cmd_quote_delete(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    /문구삭제 PAGE_ID
    """
    if not await authorized(update):
        return
    raw = update.message.text or ""
    body = re.sub(r"^/문구삭제\s*", "", raw).strip()
    if not body:
        await update.message.reply_text(
            "사용법: `/문구삭제 PAGE_ID`\n"
            "PAGE_ID는 /문구목록 에서 확인하세요.",
            parse_mode="Markdown",
        )
        return
    page_id = body
    if not NOTION_TOKEN:
        await update.message.reply_text("NOTION_TOKEN 미설정 — .env 확인 필요")
        return

    ok = _notion_deactivate_quote(page_id)
    if ok:
        await update.message.reply_text(f"문구 비활성화 완료\nID: `{page_id}`", parse_mode="Markdown")
    else:
        await update.message.reply_text("비활성화 실패 — PAGE_ID 확인 또는 Notion API 오류.")


async def cmd_quote_list(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    /문구목록 06 또는 /문구목록 18
    """
    if not await authorized(update):
        return
    raw = update.message.text or ""
    body = re.sub(r"^/문구목록\s*", "", raw).strip()
    if body not in ("06", "18"):
        await update.message.reply_text(
            "사용법: `/문구목록 06` 또는 `/문구목록 18`",
            parse_mode="Markdown",
        )
        return
    time_slot = f"{body}시"
    if not NOTION_TOKEN:
        await update.message.reply_text("NOTION_TOKEN 미설정 — .env 확인 필요")
        return

    items = _notion_list_quotes(time_slot)
    if not items:
        await update.message.reply_text(f"{time_slot} 활성 문구가 없습니다.")
        return

    lines = [f"[{time_slot} 활성 문구 — {len(items)}건]"]
    for i, item in enumerate(items, 1):
        pid = item.get("id", "")
        props = item.get("properties", {})
        title_list = props.get("문구", {}).get("title", [])
        text = title_list[0].get("plain_text", "(제목없음)") if title_list else "(제목없음)"
        lines.append(f"{i}. {text}\n   ID: `{pid}`")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# ── 결재 회신 라우터 헬퍼 ─────────────────────────────────────────────────────

def _notion_query_approval_candidates(db_id: str) -> list[dict]:
    """해당 DB에서 상태='승인 요청' 레코드를 최신순 최대 10건 조회."""
    if not NOTION_TOKEN:
        return []
    try:
        payload = {
            "filter": {"property": "상태", "select": {"equals": "승인 요청"}},
            "sorts": [{"timestamp": "last_edited_time", "direction": "descending"}],
            "page_size": 10,
        }
        resp = requests.post(
            f"https://api.notion.com/v1/databases/{db_id}/query",
            headers=NOTION_HEADERS,
            json=payload,
            timeout=15,
        )
        if resp.status_code == 200:
            return resp.json().get("results", [])
    except Exception:
        pass
    return []


def _page_title(page: dict) -> str:
    """Notion 페이지에서 title 속성 텍스트 추출."""
    props = page.get("properties", {})
    for key in ("제목", "이름", "Name", "title"):
        field = props.get(key, {})
        title_list = field.get("title", [])
        if title_list:
            return "".join(t.get("plain_text", "") for t in title_list)
    return "(제목 없음)"


def _match_identifier(identifier: str, pages: list[dict]) -> list[dict]:
    """식별자 문자열로 후보 페이지 필터링. page_id prefix 또는 제목 포함 매칭."""
    identifier = identifier.strip().lower().replace("-", "")
    matched = []
    for p in pages:
        pid = p.get("id", "").replace("-", "").lower()
        title = _page_title(p).lower()
        if identifier in pid or identifier in title.replace(" ", "").replace("-", ""):
            matched.append(p)
    return matched


def _patch_approval(page_id: str, status_value: str, approval_result: str, comment: str) -> bool:
    """Notion 페이지 상태·승인결과·반려코멘트 patch."""
    if not NOTION_TOKEN:
        return False
    props: dict = {
        "상태": {"select": {"name": status_value}},
        "AI CEO 결재": {"select": {"name": approval_result}},
    }
    if comment:
        props["반려 및 조건 코멘트"] = {
            "rich_text": [{"type": "text", "text": {"content": comment[:2000]}}]
        }
    try:
        resp = requests.patch(
            f"https://api.notion.com/v1/pages/{page_id}",
            headers=NOTION_HEADERS,
            json={"properties": props},
            timeout=15,
        )
        return resp.status_code == 200
    except Exception:
        return False


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

    # 3개 DB 후보 수집
    all_candidates: list[dict] = []
    for db_id in (PLANNING_DB_ID, ARCHIVE_DB_ID, AUTOMATION_DB_ID):
        all_candidates.extend(_notion_query_approval_candidates(db_id))

    if not all_candidates:
        await update.message.reply_text(
            "[AI CEO 자동 중계] 현재 '승인 요청' 상태 레코드가 없습니다. Notion DB를 확인해주세요."
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

    # 단일 매칭 — patch 실행
    target = matched[0]
    page_id = target["id"]
    title = _page_title(target)
    ok = _patch_approval(page_id, status_value, approval_result, comment)
    if ok:
        await update.message.reply_text(
            f"[AI CEO 자동 중계] 결재 patch 완료 — {title}\n"
            f"결재: {approval_result} / 상태: {status_value}"
            + (f"\n코멘트: {comment}" if comment else "")
        )
    else:
        await update.message.reply_text(
            f"[AI CEO 자동 중계] Notion patch 실패 — '{title}' (ID: {page_id})\n"
            "NOTION_TOKEN 또는 페이지 권한을 확인해주세요."
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

    # 인박스 적재 (simple_ack 제외)
    if bidir_category != "simple_ack":
        notion_key = ENV.get("NOTION_API_KEY", "")
        inbox_id = ENV.get("INBOX_DB_ID", "")
        _bidir_push_inbox(prompt, bidir_category, notion_key, inbox_id)

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
    # 결재 콜백 (sign:* prefix) — 2026-05-28 신설
    app.add_handler(CallbackQueryHandler(cmd_approval_callback, pattern=r"^sign:"))
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
