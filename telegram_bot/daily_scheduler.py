"""
웰페리온 일일 자동 보고 스케줄러 v2.0
-------------------------------
정규 스케줄 (10개): 06/07/09/12/15/18/21/22/23시 정각 텔레그램 자동 보고
테스트 모드: python daily_scheduler.py --test  →  1시간 주기 실행
※ 08시(오늘의 항로)는 ceo_morning_pipeline.py (별도 Task Scheduler) 담당 — 여기서 중복 발송 없음

슬롯 정본 = 웰페리온 ERP T2(업무자동화SSOT) 텔레그램탭 — 슬롯 변경 시 T2만 수정
※ 08시(오늘의 항로)는 ceo_morning_pipeline.py 별도 Task Scheduler 담당 — 여기서 중복 발송 없음

운영 원칙:
- 기존 워처 3종 (archive_result_watcher·planning_to_archive_watcher·permission_watcher) 유지
- 데이터 소스 조회 실패(quotes.json 부재·git log 실패 등) 시 Claude 연동 없이 자동화 실패 경보만 송신
- PC 정각 오프 후 복구 시 misfire_grace_time(600초) 내 catch-up 자동 실행
- 로그: scheduler.log (RotatingFileHandler, 7일 보존)

v1.2 헬스체크 업그레이드 (2026-04-20, 4.20-텔레그램 통신 장애 재발 방지):
- 15분 간격 봇 헬스체크: getMe API self-ping, 실패 시 로그 + telegram_failure.json 기록
- 전송 응답 검증: send_telegram 실패 시 consecutive_failures 카운트, 3회 연속 시 스케줄러 자동 재기동
- 로컬 fallback 알림: 텔레그램 실패 감지 시 Windows 데스크톱 알림 + 콘솔 출력
- state.json 확장: last_successful_send_timestamp, consecutive_failures 필드 추가
- .env mtime 감시: .env 변경 감지 시 환경 변수 자동 재로드

버전: v1.0 → v1.1 (2026-04-18 B안 승인, 6시간대 재설계)
       v1.1 → v1.2 (2026-04-20 헬스체크·재시도·fallback·자동 재로드 추가)
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import random
import subprocess
import sys
import time
from datetime import datetime, timedelta
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

# ── 중복 기동 방지 PID 락 (v1.3) ─────────────────────────────────────────────
_PID_FILE = Path(__file__).parent / "daily_scheduler.pid"


def _check_pid_lock() -> None:
    """이미 실행 중인 daily_scheduler.py 인스턴스가 있으면 즉시 종료."""
    if _PID_FILE.exists():
        try:
            old_pid = int(_PID_FILE.read_text().strip())
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {old_pid}", "/FO", "CSV"],
                capture_output=True, text=True, shell=True
            )
            if str(old_pid) in result.stdout:
                print(f"[daily_scheduler] 이미 실행 중 (PID {old_pid}). 중복 기동 차단 후 종료.", flush=True)
                sys.exit(0)
        except Exception:
            pass
    _PID_FILE.write_text(str(os.getpid()))


_check_pid_lock()

import requests
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

try:  # 발신 공용 로깅(best-effort) — 임포트 실패해도 발신 무영향
    import os as _os, sys as _sys
    _scr = _os.path.abspath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "scripts"))
    if _scr not in _sys.path:
        _sys.path.insert(0, _scr)
    from tg_outbound_log import log_outbound
except Exception:
    def log_outbound(*a, **k):
        pass

# 배 분류 공유 모듈 (scripts/ship_classify.py)
try:
    import os as _os2, sys as _sys2
    _scr2 = _os2.path.abspath(_os2.path.join(_os2.path.dirname(_os2.path.abspath(__file__)), "..", "scripts"))
    if _scr2 not in _sys2.path:
        _sys2.path.insert(0, _scr2)
    from ship_classify import classify_ship, has_clevel_id, render_ship_line
    _SHIP_CLASSIFY_OK = True
except Exception as _e_ship:
    _SHIP_CLASSIFY_OK = False
    def classify_ship(task, urgent_titles=None):  # type: ignore[misc]
        return {"icon": "🚢", "tier": "여객선", "urgent": False, "northstar": False}
    def has_clevel_id(title):  # type: ignore[misc]
        return False
    def render_ship_line(title, owner, ship, due=""):  # type: ignore[misc]
        owner_part = f" [{owner}]" if owner else ""
        return f"🚢 {title}{owner_part}"

# ── v1.2 헬스체크 상수 ────────────────────────────────────────────────────────
FAILURE_STATE_FILE = Path(__file__).parent / "telegram_failure.json"
_ENV_MTIME: float = 0.0          # .env 마지막 수정 시각 추적용

# ── 경로 상수 ────────────────────────────────────────────────────────────────
BASE = Path(__file__).parent
STATE_FILE = BASE / "state.json"
ENV_FILE = BASE / ".env"
LOG_FILE = BASE / "scheduler.log"

# ── SSOT 소스 경로 (노션 폐기 2026-05-29 → GitHub status/* + git log) ──────────
REPO_ROOT = BASE.parent
STATUS_DIR = REPO_ROOT / "status"
QUOTES_FILE = STATUS_DIR / "quotes.json"
QUEUE_FILE = STATUS_DIR / "_queue.json"
# 진행현황 집계 대상 C-Level status 파일
_CLEVEL_FILES = ["ceo", "cfo", "chro", "cmo", "coo", "cpo", "cto"]

# ── 로거 설정 (7일 RotatingFileHandler) ──────────────────────────────────────
logger = logging.getLogger("scheduler")
logger.setLevel(logging.INFO)

_fh = TimedRotatingFileHandler(
    LOG_FILE,
    when="midnight",
    interval=1,
    backupCount=7,
    encoding="utf-8",
)
_fh.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
_sh = logging.StreamHandler(sys.stdout)
_sh.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
logger.addHandler(_fh)
logger.addHandler(_sh)


# ── 환경 변수 로드 ─────────────────────────────────────────────────────────────
def load_env() -> dict[str, str]:
    env: dict[str, str] = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    for key in ("TELEGRAM_BOT_TOKEN", "OWNER_ID", "CHECKLIST_API_URL"):
        if key in os.environ:
            env[key] = os.environ[key]
    return env


ENV = load_env()
TELEGRAM_TOKEN = ENV.get("TELEGRAM_BOT_TOKEN", "")
if not TELEGRAM_TOKEN:
    logger.critical(".env 에 TELEGRAM_BOT_TOKEN 미정의 — 스케줄러 종료")
    sys.exit(1)

TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

# [2026-05-31 CTO] 노션 연동 상수 제거 — 일일보고 소스를 GitHub status/* + git log로
#   이관(노션 폐기 2026-05-29). 문구=status/quotes.json, 09시=git log, 15시=status/*.json.

# 12시 시설·지원·주차 현황용 (Google Sheets Apps Script 단일 소스)
CHECKLIST_API_URL = ENV.get("CHECKLIST_API_URL", "")

# 23시 마감 점검 차트 상세형용 — today_live(지원부 회차×성별) 지원 라이브 GAS.
# 기존 CHECKLIST_API_URL은 옛 배포라 today_live 불가 → 본 슬롯은 검증된 라이브 URL 사용.
# (env SUPPORT_CHECK_API_URL로 오버라이드 가능, 기본=검증된 라이브 exec URL.)
SUPPORT_CHECK_API_URL = ENV.get(
    "SUPPORT_CHECK_API_URL",
    "https://script.google.com/macros/s/AKfycbyXw4ZaA6hLK567GC7NY33Y8SvNPW6kNtrXFz2OsSdFVBmCnZP-2oD-RQiX0IpekBu1/exec",
)

# 9시 매출·지출 현황용 (CFO 시트 — GM이 시트 링크 제공 후 .env CFO_SHEET_URL에 등록)
CFO_SHEET_URL = ENV.get("CFO_SHEET_URL", "")

# 업무현황 SSOT API (G1 할일, 09·15시 공용)
SSOT_API_URL = "https://script.google.com/macros/s/AKfycbxDwFkrxK1YIaEoSNcuw2MiHiZQ-7o5N6311ytksSyeEd86ZFOhLknOWqQgNArQvZ-7/exec"


# ── state.json 읽기/쓰기 ─────────────────────────────────────────────────────
def read_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        logger.error(f"state.json 읽기 실패: {e}")
        return {}


def write_state(data: dict) -> None:
    try:
        STATE_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        logger.error(f"state.json 쓰기 실패: {e}")


# ── state.json 에서 owner_id 취득 (.env OWNER_ID fallback 포함) ───────────────
def get_owner_id() -> int | None:
    """
    우선순위:
      1) state.json 의 owner_id (정상 경로)
      2) .env 의 OWNER_ID (state.json 깨진 경우 fallback)
      3) None → 기존처럼 에러 로그 후 보고 생략
    """
    owner_id = read_state().get("owner_id")
    if owner_id:
        return int(owner_id)
    # fallback: .env OWNER_ID
    env_owner = load_env().get("OWNER_ID", "").strip()
    if env_owner:
        logger.warning(
            f"state.json owner_id 미등록 — .env OWNER_ID fallback 사용: {env_owner}"
        )
        return int(env_owner)
    return None


# ── v1.2: consecutive_failures 업데이트 ──────────────────────────────────────
def record_send_success() -> None:
    state = read_state()
    state["last_successful_send_timestamp"] = datetime.now().isoformat()
    state["consecutive_failures"] = 0
    write_state(state)


def record_send_failure() -> int:
    """실패 카운트를 1 증가시키고 현재 연속 실패 횟수를 반환."""
    state = read_state()
    count = state.get("consecutive_failures", 0) + 1
    state["consecutive_failures"] = count
    write_state(state)
    # telegram_failure.json 기록
    try:
        FAILURE_STATE_FILE.write_text(
            json.dumps({
                "timestamp": datetime.now().isoformat(),
                "consecutive_failures": count,
            }, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception:
        pass
    return count


# ── v1.2: 로컬 fallback 알림 (Windows 데스크톱 토스트) ───────────────────────
def local_fallback_alert(message: str) -> None:
    """텔레그램 전송 실패 시 Windows 데스크톱 알림 + 콘솔 출력."""
    logger.critical(f"[FALLBACK ALERT] {message}")
    try:
        ps_cmd = (
            f"Add-Type -AssemblyName System.Windows.Forms; "
            f"[System.Windows.Forms.MessageBox]::Show('{message}', "
            f"'웰페리온 CTO 경보', 0, 48)"
        )
        subprocess.Popen(
            ["powershell", "-NonInteractive", "-Command", ps_cmd],
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
        )
    except Exception as e:
        logger.warning(f"로컬 fallback 알림 실패: {e}")


# ── v1.2: .env mtime 감시 및 자동 재로드 ─────────────────────────────────────
def check_env_reload() -> None:
    global _ENV_MTIME, ENV, TELEGRAM_TOKEN, TELEGRAM_API
    try:
        current_mtime = ENV_FILE.stat().st_mtime
        if _ENV_MTIME == 0.0:
            _ENV_MTIME = current_mtime
            return
        if current_mtime != _ENV_MTIME:
            logger.warning(".env 파일 변경 감지 — 환경 변수 재로드")
            _ENV_MTIME = current_mtime
            ENV = load_env()
            TELEGRAM_TOKEN = ENV.get("TELEGRAM_BOT_TOKEN", "")
            TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
            logger.info(".env 재로드 완료")
    except Exception as e:
        logger.error(f".env mtime 감시 오류: {e}")


# ── v1.2: 봇 헬스체크 (15분 주기 self-ping) ──────────────────────────────────
def health_check_bot() -> None:
    """getMe API 호출로 봇 토큰 유효성 및 네트워크 확인."""
    check_env_reload()
    if not TELEGRAM_TOKEN:
        logger.error("[헬스체크] TELEGRAM_BOT_TOKEN 미설정")
        local_fallback_alert("헬스체크 실패: TELEGRAM_BOT_TOKEN 미설정")
        return
    try:
        resp = requests.get(f"{TELEGRAM_API}/getMe", timeout=10)
        if resp.status_code == 200 and resp.json().get("ok"):
            logger.info(f"[헬스체크] OK — bot={resp.json()['result'].get('username')}")
        else:
            msg = f"[헬스체크] getMe 실패 status={resp.status_code} body={resp.text[:200]}"
            logger.error(msg)
            local_fallback_alert(msg)
    except Exception as e:
        msg = f"[헬스체크] 네트워크 오류: {e}"
        logger.error(msg)
        local_fallback_alert(msg)


# ── MarkdownV2 escape 헬퍼 (Bot API 7.x 기준) ────────────────────────────────
_MD_V2_SPECIALS = r'_*[]()~`>#+-=|{}.!'


def escape_md_v2(text: str) -> str:
    """Telegram MarkdownV2 reserved chars escape (Bot API 7.x 기준)."""
    return ''.join('\\' + c if c in _MD_V2_SPECIALS else c for c in text)


# ── 텔레그램 메시지 송신 (v1.2: 응답 검증 + 지수 백오프 + 연속 실패 추적) ───
def send_telegram(chat_id: int, text: str) -> bool:
    """HTTP POST. 재시도 3회 지수 백오프. ok:true 검증. 연속 실패 시 fallback."""
    url = f"{TELEGRAM_API}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "MarkdownV2"}
    for attempt in range(1, 4):
        try:
            resp = requests.post(url, json=payload, timeout=15)
            if resp.status_code == 200:
                resp_json = resp.json()
                if resp_json.get("ok"):
                    logger.info(f"Telegram 송신 성공 chat_id={chat_id} message_id={resp_json.get('result', {}).get('message_id')}")
                    record_send_success()
                    log_outbound(text, chat_id=chat_id, source="daily_scheduler.send_telegram", ok=True, kind="sendMessage")
                    return True
                else:
                    logger.warning(f"Telegram ok=false attempt={attempt} body={resp.text[:200]}")
            elif resp.status_code == 400 and "parse entities" in resp.text:
                # MarkdownV2 파싱 오류 → 즉시 평문 fallback (같은 attempt 내 1회)
                plain_payload = {"chat_id": chat_id, "text": text}
                try:
                    plain_resp = requests.post(url, json=plain_payload, timeout=15)
                    if plain_resp.status_code == 200 and plain_resp.json().get("ok"):
                        logger.warning("MarkdownV2 escape 실패 → 평문 fallback 성공")
                        record_send_success()
                        log_outbound(text, chat_id=chat_id, source="daily_scheduler.send_telegram", ok=True, kind="sendMessage")
                        return True
                    else:
                        logger.warning(
                            f"평문 fallback 실패 attempt={attempt} status={plain_resp.status_code} body={plain_resp.text[:200]}"
                        )
                except Exception as fe:
                    logger.warning(f"평문 fallback 예외 attempt={attempt}: {fe}")
            else:
                logger.warning(
                    f"Telegram 송신 실패 attempt={attempt} status={resp.status_code} body={resp.text[:200]}"
                )
        except Exception as e:
            logger.warning(f"Telegram 요청 예외 attempt={attempt}: {e}")
        # 지수 백오프: 3s → 6s → 12s
        time.sleep(3 * (2 ** (attempt - 1)))
    # 3회 모두 실패
    count = record_send_failure()
    local_fallback_alert(f"텔레그램 전송 3회 실패 (연속 {count}회) — chat_id={chat_id}")
    if count >= 3:
        logger.critical(f"연속 실패 {count}회 — 스케줄러 자동 재기동 시도")
        _restart_scheduler()
    log_outbound(text, chat_id=chat_id, source="daily_scheduler.send_telegram", ok=False, kind="sendMessage")
    return False


def _restart_scheduler() -> None:
    """스케줄러 자체 재기동 (현재 프로세스를 교체 실행)."""
    try:
        python = sys.executable
        script = str(Path(__file__).resolve())
        logger.info(f"재기동: {python} {script}")
        subprocess.Popen([python, script])
        sys.exit(0)
    except Exception as e:
        logger.error(f"재기동 실패: {e}")


# ── 문구: status/quotes.json 에서 랜덤 1건 취득 (노션 문구 DB 폐기 대체) ──────
def fetch_random_quote(time_slot: str) -> str | None:
    """
    time_slot: "06시" | "18시"
    status/quotes.json 의 해당 시간대 + active=True 문구 중 랜덤 1건 반환.
    파일 없거나 문구 없으면 None 반환.
    """
    slot_key = time_slot.replace("시", "").strip()  # "06시" → "06"
    if not QUOTES_FILE.exists():
        logger.warning(f"quotes.json 없음: {QUOTES_FILE}")
        return None
    try:
        data = json.loads(QUOTES_FILE.read_text(encoding="utf-8"))
        items = data.get(slot_key, [])
        active = [q.get("text", "") for q in items if q.get("active") and q.get("text")]
        if not active:
            return None
        return random.choice(active)
    except Exception as e:
        logger.error(f"quotes.json 조회 예외: {e}")
        return None


# ── git log: 전날 커밋 집계 (09시용, 노션 DB 폐기 대체) ───────────────────────
def _git_log_between(since: str, until: str, max_lines: int = 40) -> list[str]:
    """git log --since/--until 로 커밋 제목 목록 반환. 실패 시 빈 리스트."""
    try:
        # bytes 모드 후 수동 디코드 — git stderr가 OS 로캘(cp949 등) 바이트를 섞어
        #   text=True 의 리더 스레드 디코드를 깨뜨리는 문제 회피 (Python 3.14).
        result = subprocess.run(
            [
                "git", "log",
                f"--since={since}", f"--until={until}",
                "--no-merges", "--pretty=format:%s",
            ],
            cwd=str(REPO_ROOT),
            capture_output=True,
            timeout=20,
        )
        if result.returncode != 0:
            logger.warning(f"git log 실패: {result.stderr.decode('utf-8', 'replace')[:200]}")
            return []
        stdout = result.stdout.decode("utf-8", "replace")
        lines = [ln.strip() for ln in stdout.splitlines() if ln.strip()]
        # auto(changelog) 자동 커밋은 노이즈 → 제외
        lines = [ln for ln in lines if not ln.startswith("auto(changelog)")]
        return lines[:max_lines]
    except Exception as e:
        logger.warning(f"git log 예외: {e}")
        return []


def fetch_yesterday_summary() -> str:
    """
    전날(어제) git 커밋을 집계. SSOT = GitHub (노션 결과물DB 폐기 2026-05-29).
    """
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    today = datetime.now().strftime("%Y-%m-%d")

    commits = _git_log_between(f"{yesterday} 00:00", f"{today} 00:00")
    total = len(commits)
    if total == 0:
        return f"• 전날({yesterday}) 커밋 없음"

    lines = [f"• 전날 커밋 {total}건 (auto 제외)"]
    for c in commits[:10]:
        lines.append(f"  - {c}")
    if total > 10:
        lines.append(f"  ... 외 {total - 10}건")
    return "\n".join(lines)


def _fetch_yesterday_done_todos() -> list[str]:
    """
    todo_list API에서 어제 완료된 항목 제목 리스트 반환.
    updatedAt == 어제 AND 상태 == 완료 기준.
    실패 시 빈 리스트.
    """
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    try:
        resp = requests.get(SSOT_API_URL, params={"action": "todo_list"}, timeout=15)
        if resp.status_code != 200:
            return []
        data = resp.json()
        if not data.get("ok"):
            return []
        items = data.get("data", [])
        done = []
        for x in items:
            st = str(x.get("상태", ""))
            updated = str(x.get("수정일", "") or x.get("updatedAt", ""))
            title = str(x.get("업무명", "")).strip()
            if st in _TODO_DONE_STATUSES and updated.startswith(yesterday) and title:
                done.append(title[:60])
        return done[:15]
    except Exception as e:
        logger.warning(f"_fetch_yesterday_done_todos 예외: {e}")
        return []


def _fetch_open_todo_cards_for_tomorrow() -> list[dict]:
    """
    미완료(진행중·보류·대기) 항목 중 내일 항로점 브릿지 대상.
    21시 '내일 항로점' 섹션용. 실패 시 빈 리스트.
    """
    try:
        resp = requests.get(SSOT_API_URL, params={"action": "todo_list"}, timeout=15)
        if resp.status_code != 200:
            return []
        data = resp.json()
        if not data.get("ok"):
            return []
        items = data.get("data", [])
        open_items = [
            x for x in items
            if str(x.get("상태", "")) not in _TODO_DONE_STATUSES
        ]
        cards = []
        for idx, x in enumerate(open_items[:12], 1):
            st = str(x.get("상태", ""))
            owner = str(x.get("담당자", "")).replace("GM", " GM").strip()
            due_date = _parse_kst_date(x.get("종료일", ""))
            due_str = due_date.strftime("%m/%d") if due_date else ""
            cards.append({
                "id_short": f"T-{idx:02d}",
                "업무명": str(x.get("업무명", "(제목없음)"))[:50],
                "담당자": owner,
                "상태": st,
                "due": due_str,
            })
        return cards
    except Exception as e:
        logger.warning(f"_fetch_open_todo_cards_for_tomorrow 예외: {e}")
        return []


# ── G1 할일 fetch (09·15시 공용, 업무현황 SSOT API) ──────────────────────────
_TODO_DONE_STATUSES = {"완료", "폐기", "DONE", "완료됨"}


def fetch_gm_todos(only_in_progress: bool = False) -> list[str] | None:
    """
    업무현황 SSOT API에서 GM(김남욱) 담당 미완료 항목 제목 리스트 반환.
    - 담당자 필드에 '김남욱' 포함 AND 상태가 완료·폐기·DONE 아님
    - only_in_progress=True 면 상태에 '진행' 포함 건만(보류·대기 제외) — 15시 진행 체크용
    - 실패 시 None 반환
    """
    try:
        resp = requests.get(
            SSOT_API_URL,
            params={"action": "todo_list"},
            timeout=15,
        )
        if resp.status_code != 200:
            logger.warning(f"fetch_gm_todos HTTP {resp.status_code}")
            return None
        data = resp.json()
        if not data.get("ok"):
            logger.warning(f"fetch_gm_todos ok=False: {data}")
            return None
        items = data.get("data", [])
        open_items = [
            x for x in items
            if "김남욱" in str(x.get("담당자", ""))
            and x.get("상태", "") not in _TODO_DONE_STATUSES
            and (not only_in_progress or "진행" in str(x.get("상태", "")))
        ]
        return [str(x.get("업무명", "(제목없음)"))[:60] for x in open_items[:15]]
    except Exception as e:
        logger.warning(f"fetch_gm_todos 예외: {e}")
        return None


# ── G1 할일 카드형 fetch (09·15시 카드 빌더용) ───────────────────────────────
def _parse_kst_date(iso_str: str):
    """ISO 8601 UTC 문자열(Z 포함)을 KST(+9) date로 변환. 실패 시 None."""
    from datetime import timezone, timedelta as _td
    if not iso_str:
        return None
    try:
        s = iso_str.rstrip("Z").replace("T", " ")
        dt_utc = datetime.fromisoformat(s).replace(tzinfo=timezone.utc)
        return (dt_utc + _td(hours=9)).date()
    except Exception:
        return None


def _extract_continuity_note(content: str) -> str:
    """
    내용 필드에서 연속성 비고를 추출한다.
    ① 날짜패턴(YYYY-MM-DD 또는 MM-DD) + 연속성 키워드 포함 줄 우선
    ② 없으면 ===PROGRESS_LOG=== 이하 첫 줄(타임스탬프 포함 줄)
    ③ 없으면 첫 줄 50자
    ④ 빈 내용이면 빈 문자열
    직렬화 마커(=== 포함 구분선) 제거.
    """
    import re
    if not content:
        return ""
    # 마커 라인 제거
    lines_raw = content.splitlines()
    lines = [l for l in lines_raw if not re.match(r"^=+[A-Z_]+=+$", l.strip())]

    _CONT_KW = re.compile(r"(흡수|통합|이어|후속|연장|계속|진척|완료|진행|전달|변경|확정)")
    _DATE_PAT = re.compile(r"\d{4}-\d{2}-\d{2}|\d{2}-\d{2}|\d{4}\.\d{1,2}\.\d{1,2}")

    # ① 날짜 + 키워드 줄 우선
    for line in lines:
        if _DATE_PAT.search(line) and _CONT_KW.search(line):
            return line.strip()[:80]

    # ② PROGRESS_LOG 블록 이후 내용 줄
    prog_idx = next(
        (i for i, l in enumerate(lines_raw) if "PROGRESS_LOG" in l), None
    )
    if prog_idx is not None:
        for line in lines_raw[prog_idx + 1:]:
            stripped = line.strip()
            if stripped and not re.match(r"^=+", stripped):
                return stripped[:80]

    # ③ 첫 줄 50자
    for line in lines:
        if line.strip():
            return line.strip()[:50]

    return ""


def fetch_gm_todo_cards(only_in_progress: bool = False) -> list[dict] | None:
    """
    업무현황 SSOT API에서 GM(김남욱) 담당 미완료 항목을 dict 리스트로 반환.
    각 항목: id_short, 업무명, 담당자, 상태, due(MM/DD), start(date), 비고
    실패 시 None 반환.
    """
    try:
        resp = requests.get(
            SSOT_API_URL,
            params={"action": "todo_list"},
            timeout=15,
        )
        if resp.status_code != 200:
            logger.warning(f"fetch_gm_todo_cards HTTP {resp.status_code}")
            return None
        data = resp.json()
        if not data.get("ok"):
            logger.warning(f"fetch_gm_todo_cards ok=False: {data}")
            return None
        items = data.get("data", [])
        open_items = [
            x for x in items
            if "김남욱" in str(x.get("담당자", ""))
            and x.get("상태", "") not in _TODO_DONE_STATUSES
            and (not only_in_progress or "진행" in str(x.get("상태", "")))
        ]
        cards = []
        for idx, x in enumerate(open_items, 1):
            raw_id = str(x.get("id", ""))
            # id가 TODO-숫자 형태면 T-NN 순번 사용, 아니면 원본
            id_short = f"T-{idx:02d}"

            due_date = _parse_kst_date(x.get("종료일", ""))
            due_str = due_date.strftime("%m/%d") if due_date else ""

            start_date = _parse_kst_date(x.get("시작일", ""))

            담당자_raw = str(x.get("담당자", ""))
            # '김남욱GM' → '김남욱 GM' 정리
            담당자 = 담당자_raw.replace("GM", " GM").strip()

            cards.append({
                "id_short": id_short,
                "raw_id": raw_id,
                "업무명": str(x.get("업무명", "(제목없음)"))[:50],
                "담당자": 담당자,
                "상태": str(x.get("상태", "")),
                "due": due_str,
                "due_date": due_date,
                "start_date": start_date,
                "비고": _extract_continuity_note(str(x.get("내용", ""))),
            })
        return cards
    except Exception as e:
        logger.warning(f"fetch_gm_todo_cards 예외: {e}")
        return None


def _classify_todo_cards(
    cards: list[dict],
) -> tuple[list[dict], list[dict]]:
    """
    카드 리스트를 오늘 / 내일 로 분류한다 (KST 기준).
    오늘: 시작일 <= 오늘 <= 종료일  OR  종료일이 오늘/과거  OR  날짜 파싱 실패
    내일: 시작일==내일 OR 종료일==내일  (오늘 목록과 중복 제외)
    """
    from datetime import date as _date
    today = _date.today()
    tomorrow = today + __import__("datetime").timedelta(days=1)

    today_cards: list[dict] = []
    tomorrow_cards: list[dict] = []

    for c in cards:
        start = c.get("start_date")
        due = c.get("due_date")

        # 오늘 분류
        is_today = False
        if start is None and due is None:
            is_today = True  # 날짜 없음 → 오늘 포함
        elif due is not None and due <= today:
            is_today = True  # 마감 오늘 이하 미완료(지연 포함)
        elif start is not None and start <= today and (due is None or due >= today):
            is_today = True  # 진행 구간이 오늘 포함

        # 내일 분류 (오늘과 별개)
        is_tomorrow = (
            (start is not None and start == tomorrow)
            or (due is not None and due == tomorrow)
        )

        if is_today:
            today_cards.append(c)
        if is_tomorrow and not is_today:
            tomorrow_cards.append(c)

    return today_cards, tomorrow_cards


def _render_card(c: dict, show_status: bool = True) -> str:
    """단일 카드를 들여쓰기 텍스트로 렌더링 (배 무게 이모지 포함)."""
    ship = classify_ship(c)
    title = c["업무명"]
    owner = c.get("담당자", "")
    due = c.get("due", "")
    headline = render_ship_line(title, owner, ship, due)
    lines = [headline]
    status_part = f" · {c['상태']}" if show_status and c.get("상태") else ""
    sub_parts = []
    if owner and not has_clevel_id(title):
        # owner는 이미 headline에 포함되었으므로 sub에는 상태만
        pass
    if show_status and c.get("상태"):
        sub_parts.append(c["상태"])
    if sub_parts:
        lines.append(f"   {' · '.join(sub_parts)}")
    if c.get("비고"):
        lines.append(f"   비고: {c['비고']}")
    return "\n".join(lines)


# ── status/*: C-Level별 현재 업무 진행현황 (15시용, 노션 DB 폐기 대체) ────────
# 미완료로 간주하는 상태값 (DONE/완료/폐기 외 전부 진행/대기로 집계)
_OPEN_STATUSES = {"PENDING", "IN_PROGRESS", "ON_HOLD", "진행중", "대기", "보류", "진행예정"}


def _load_queue_open() -> list[dict]:
    """_queue.json 에서 미완료 항목 반환 (DONE·완료·폐기·완료됨 제외).
    active_tasks 경로(아래)와 동일 기준으로 통일 — 큐 경로만 '폐기'를 흘려보내
    15시 진행현황에 죽은(폐기) 항목이 진행중으로 잡히던 버그 차단 (2026-06-11)."""
    if not QUEUE_FILE.exists():
        return []
    try:
        data = json.loads(QUEUE_FILE.read_text(encoding="utf-8"))
        return [x for x in data
                if str(x.get("status", "")).strip().upper() != "DONE"
                and str(x.get("status", "")).strip() not in ("완료", "폐기", "완료됨")]
    except Exception as e:
        logger.warning(f"_queue.json 읽기 실패: {e}")
        return []


def _fetch_current_progress_local() -> str:
    """
    [폴백 전용] status/_queue.json + 각 C-Level status JSON의 active_tasks 중
    미완료 항목을 C-Level별로 집계. gm_hangro 실패 시 사용.

    gm_hangro(서버 권위 경로)와 동일 기준으로 정합 (2026-06-12 시토):
    - GM 소유 항목 제외 (_owner_to_clevel — 9시는 C-Level 현황만)
    - 활성 상태를 '진행중·대기' 계열만 인정 (보류·ON_HOLD는 비활성으로 빼서 두 경로 일치)
    """
    # 두 경로 일치: 폐기·완료·DONE 외에 보류/ON_HOLD도 9시 활성에서 제외
    _ACTIVE_LOCAL = {"PENDING", "IN_PROGRESS", "진행중", "대기"}
    per_clevel: dict[str, list[str]] = {}

    _VALID_CLEVELS = {"CEO", "CFO", "CHRO", "CMO", "COO", "CPO", "CTO"}
    # 1) 대기 큐 (status != DONE, 폐기·보류 제외, GM 소유 제외)
    for item in _load_queue_open():
        status = str(item.get("status", "")).strip()
        if status and status.upper() not in {s.upper() for s in _ACTIVE_LOCAL}:
            continue
        # owner 우선 매핑(GM이면 None) → 없으면 clevel 필드. GM/미상은 제외.
        owner = str(item.get("owner", ""))
        clevel = _owner_to_clevel(owner) if owner else None
        if clevel is None:
            clevel = str(item.get("clevel", "")).upper()
        if clevel not in _VALID_CLEVELS:
            continue
        title = str(item.get("title", "(제목없음)")).split("\n")[0][:60]
        per_clevel.setdefault(clevel, []).append(f"[{status}] {title}")

    # 2) 각 C-Level active_tasks (status 진행중·대기만)
    for name in _CLEVEL_FILES:
        f = STATUS_DIR / f"{name}.json"
        if not f.exists():
            continue
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(f"{name}.json 읽기 실패: {e}")
            continue
        for t in d.get("active_tasks", []):
            st = str(t.get("status", ""))
            if st and st.upper() not in {s.upper() for s in _ACTIVE_LOCAL}:
                continue
            clevel = name.upper()
            title = str(t.get("title", "(제목없음)")).split("\n")[0][:60]
            per_clevel.setdefault(clevel, []).append(f"[{st or '진행'}] {title}")

    if not per_clevel:
        return "• 현재 진행중·대기 항목 없음"

    total = sum(len(v) for v in per_clevel.values())
    lines = [f"• 진행중·대기 총 {total}건"]
    for clevel in sorted(per_clevel):
        items = per_clevel[clevel]
        lines.append("")
        lines.append(f"[{clevel}] {len(items)}건")
        for it in items[:5]:
            lines.append(f"  - {it}")
        if len(items) > 5:
            lines.append(f"  ... 외 {len(items) - 5}건")
    return "\n".join(lines)


# gm_hangro owner → C-Level 레이블 매핑
_GM_HANGRO_OWNER_TO_CLEVEL: dict[str, str] = {
    "AI CEO": "CEO", "웰리": "CEO",
    "AI CMO": "CMO", "시모": "CMO",
    "AI CTO": "CTO", "시토": "CTO",
    "AI COO": "COO", "시우": "COO",
    "AI CFO": "CFO", "시뽀": "CFO",
    "AI CPO": "CPO", "시포": "CPO",
    "AI CHRO": "CHRO", "시로": "CHRO",
}

# GM 소유자 패턴 (C-Level 집계에서 제외)
_GM_OWNER_KEYWORDS = ("김남욱", "GM")


def _owner_to_clevel(owner: str) -> str | None:
    """owner 문자열 → C-Level 레이블. GM이거나 매핑 없으면 None."""
    # GM 제외
    for kw in _GM_OWNER_KEYWORDS:
        if kw in owner:
            return None
    # 정확 매핑 우선
    for key, label in _GM_HANGRO_OWNER_TO_CLEVEL.items():
        if key in owner:
            return label
    # 'AI XXX' 패턴 범용 추출
    import re
    m = re.search(r"AI\s+(CEO|CMO|CTO|COO|CFO|CPO|CHRO)", owner)
    if m:
        return m.group(1)
    return None


def _fetch_current_progress_hangro() -> str | None:
    """
    gm_hangro API에서 C-Level 활성 항목을 집계.
    성공 시 포맷된 문자열 반환, 실패/빈응답/타임아웃 시 None 반환.
    """
    try:
        resp = requests.get(
            SSOT_API_URL,
            params={"action": "gm_hangro"},
            timeout=15,
        )
        if resp.status_code != 200:
            logger.warning(f"gm_hangro HTTP {resp.status_code}")
            return None
        data = resp.json()
        if not data.get("ok"):
            logger.warning(f"gm_hangro ok=False: {str(data)[:200]}")
            return None

        items = data.get("data", [])
        if not items:
            return "• 현재 진행중·대기 항목 없음"

        # C-Level 소유 + 활성(진행중·대기) + 업무 or 결재 inflight 필터
        per_clevel: dict[str, list[str]] = {}
        for item in items:
            owner = str(item.get("owner", ""))
            status = str(item.get("status", ""))
            category = str(item.get("category", ""))
            appr_kind = str(item.get("_apprKind", ""))
            title = str(item.get("title", "(제목없음)")).split("\n")[0][:60]

            # 활성 상태만 (완료·보류·폐기 제외)
            if status not in ("진행중", "대기"):
                continue

            # 업무 카테고리 또는 결재 inflight만 포함
            if category == "결재" and appr_kind not in ("inflight", "gm"):
                continue

            clevel = _owner_to_clevel(owner)
            if clevel is None:
                continue

            per_clevel.setdefault(clevel, []).append(f"[{status}] {title}")

        if not per_clevel:
            return "• 현재 진행중·대기 항목 없음"

        total = sum(len(v) for v in per_clevel.values())
        lines = [f"• 진행중·대기 총 {total}건"]
        for clevel in sorted(per_clevel):
            clevel_items = per_clevel[clevel]
            lines.append("")
            lines.append(f"[{clevel}] {len(clevel_items)}건")
            for it in clevel_items[:5]:
                lines.append(f"  - {it}")
            if len(clevel_items) > 5:
                lines.append(f"  ... 외 {len(clevel_items) - 5}건")
        return "\n".join(lines)

    except Exception as e:
        logger.warning(f"gm_hangro 호출 예외: {e}")
        return None


def fetch_current_progress() -> str:
    """
    C-Level 진행현황 집계. gm_hangro API(서버 단일 엔진) 우선 사용.
    실패·빈응답·타임아웃 시 로컬 폴백(_fetch_current_progress_local) 자동 전환.
    """
    result = _fetch_current_progress_hangro()
    if result is not None:
        return result
    logger.warning("gm_hangro 실패 — 로컬 폴백(_queue+status/*.json) 사용")
    return _fetch_current_progress_local()


# ── Claude CLI: 오늘자 요약 생성 (21시 Lv1용) ───────────────────────────────
def _find_claude_bin() -> str:
    import shutil
    for name in ("claude.cmd", "claude.exe", "claude"):
        found = shutil.which(name)
        if found:
            return found
    from pathlib import Path as P
    for p in [
        P.home() / "AppData" / "Roaming" / "npm" / "claude.cmd",
        P.home() / "AppData" / "Roaming" / "npm" / "claude",
    ]:
        if p.exists():
            return str(p)
    return "claude"


def _fetch_today_changes_grouped() -> dict[str, list[str]]:
    """오늘자 git 커밋을 단일 그룹('커밋')으로 반환. SSOT = GitHub (노션 폐기)."""
    today = datetime.now().strftime("%Y-%m-%d")
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    commits = _git_log_between(f"{today} 00:00", f"{tomorrow} 00:00", max_lines=30)
    if not commits:
        return {}
    return {"커밋": commits}


def _fetch_one_line_summary(grouped: dict[str, list[str]]) -> str:
    """Claude CLI로 하루 인상 한 줄 요약. 실패 시 빈 문자열."""
    if not grouped:
        return ""
    flat = []
    for db_name, titles in grouped.items():
        for t in titles[:10]:
            flat.append(f"[{db_name}] {t}")
    if not flat:
        return ""
    today = datetime.now().strftime("%Y-%m-%d")
    prompt = (
        f"다음은 웰페리온 {today} 변경된 업무 목록입니다. "
        f"오늘 하루의 인상을 한국어 한 줄(최대 60자)로만 요약하세요. "
        f"불필요한 수식 없이 핵심 동향만.\n\n"
        + "\n".join(flat[:20])
    )
    claude_bin = _find_claude_bin()
    try:
        import subprocess as sp
        result = sp.run(
            [claude_bin, "-p", "--output-format", "text"],
            input=prompt.encode("utf-8"),
            capture_output=True,
            timeout=60,
        )
        if result.returncode == 0:
            output = result.stdout.decode("utf-8", "replace").strip()
            output = output.replace("\n", " ").strip()
            if output:
                return output[:120]
        logger.warning(f"Claude CLI 요약 실패: exit={result.returncode}")
    except Exception as e:
        logger.warning(f"Claude CLI 호출 예외: {e}")
    return ""


GUIDE_HUB_PATH = Path(__file__).parent.parent / "3. 웰페리온 가이드" / "wellperion_guide(main).html"


def _fetch_tomorrow_tasks_from_guidehub() -> tuple[str, list[str]]:
    """웰페리온 ERP HTML에서 내일 할 일 시드 목록을 반환한다.

    반환: (내일_날짜_문자열 'YYYY-MM-DD', 시드_제목_리스트)
    - status='진행중' + startDate == 내일 인 시드만 포함
    - 파일 없거나 파싱 실패 시 ('', []) 반환
    """
    import re

    tomorrow = (datetime.now() + timedelta(days=1)).date()
    tomorrow_str = tomorrow.strftime("%Y-%m-%d")

    if not GUIDE_HUB_PATH.exists():
        logger.warning(f"웰페리온 ERP 파일 없음: {GUIDE_HUB_PATH}")
        return tomorrow_str, []

    try:
        text = GUIDE_HUB_PATH.read_text(encoding="utf-8")
    except Exception as e:
        logger.warning(f"웰페리온 ERP 읽기 실패: {e}")
        return tomorrow_str, []

    # CEO_SEEDS 영역 추출
    start_marker = "/* ── CEO_SEED_START ── */"
    start_idx = text.find(start_marker)
    if start_idx == -1:
        logger.warning("CEO_SEED_START 마커 없음")
        return tomorrow_str, []

    # 영역 끝: ]; 로 종료되는 첫 라인
    seed_block = text[start_idx:]
    end_idx = seed_block.find("];")
    if end_idx != -1:
        seed_block = seed_block[: end_idx + 2]

    # 시드 객체에서 title·startDate·status 추출
    # 패턴: {id:'...',title:'...',...,startDate:'YYYY-MM-DD',...,status:'...',...}
    seed_pattern = re.compile(
        r"\{[^{}]*?id\s*:\s*'([^']+)'[^{}]*?title\s*:\s*'([^']*)'[^{}]*?startDate\s*:\s*'([^']*)'[^{}]*?status\s*:\s*'([^']*)'[^{}]*?\}",
        re.DOTALL,
    )

    titles: list[str] = []
    for m in seed_pattern.finditer(seed_block):
        seed_id, title, start_date, status = m.group(1), m.group(2), m.group(3), m.group(4)
        # 메타 시드 제외 (id에 'meta' 포함)
        if "meta" in seed_id:
            continue
        if status != "진행중":
            continue
        if start_date != tomorrow_str:
            continue
        titles.append(title)

    return tomorrow_str, titles


def fetch_daily_summary_lv1() -> str:
    """21시 1단계 요약: 한 줄 인상 + DB별 변동 항목 목록."""
    grouped = _fetch_today_changes_grouped()
    if not grouped:
        return "오늘 변경된 항목이 없습니다."

    total = sum(len(v) for v in grouped.values())
    one_line = _fetch_one_line_summary(grouped)

    lines: list[str] = []
    if one_line:
        lines.append("💬 한 줄 요약")
        lines.append(f"  {one_line}")
        lines.append("")
    lines.append(f"📊 오늘 변동 {total}건")

    db_icons = {"기획DB": "🗂️", "결과물DB": "📦"}
    for db_name, titles in grouped.items():
        icon = db_icons.get(db_name, "•")
        lines.append("")
        lines.append(f"{icon} {db_name} ({len(titles)}건)")
        for t in titles[:5]:
            lines.append(f"  • {t}")
        if len(titles) > 5:
            lines.append(f"  · 외 {len(titles) - 5}건")

    # 내일 할 일 (웰페리온 ERP SSOT)
    try:
        tomorrow_str, tomorrow_tasks = _fetch_tomorrow_tasks_from_guidehub()
        lines.append("")
        weekday_kor = _WEEKDAY_KOR[(datetime.now() + timedelta(days=1)).weekday()]
        if tomorrow_tasks:
            lines.append(f"🌅 내일 ({tomorrow_str} {weekday_kor}) 할 일 {len(tomorrow_tasks)}건")
            for i, title in enumerate(tomorrow_tasks[:8], 1):
                lines.append(f"  {i}. {title}")
            if len(tomorrow_tasks) > 8:
                lines.append(f"  · 외 {len(tomorrow_tasks) - 8}건")
        else:
            lines.append("🌅 내일의 항로")
            lines.append("  (등록된 시드 없음 — 웰페리온 ERP 등록 필요)")
    except Exception as e:
        logger.warning(f"내일 할 일 조회 실패: {e}")

    return "\n".join(lines)


# ── 시간대별 보고 실행 함수 ───────────────────────────────────────────────────

# 06시 매일 고정 운동 루틴 — 5종목 체크리스트 (v1.5, 대표님 지시)
DAILY_WORKOUT_ITEMS = [
    ("맨몸 스쿼트", "개"),
    ("푸시업", "개"),
    ("크로스 토터치", "개"),
    ("덤벨 (이두·삼두·어깨)", "세트"),
    ("찬물 샤워", "분"),
]
_WEEKDAY_KOR = ["월", "화", "수", "목", "금", "토", "일"]

# ── 통일 포맷 헬퍼 (2026-06-11 GM 지시) ────────────────────────────────────────
# 9슬롯(06/07/09/12/15/18/21/22/23) 출력 포맷을 단일 템플릿으로 통일.
#   · 공통 헤더:  [HH시 · {분류} · 한줄목적]  + 날짜줄 + 구분선
#   · 분류 라벨:  개인 / 회사 / 개인&회사  (GM 한눈 파악 핵심)
#   · 공통 구분선·푸터 단일화 (중복 제거)
# ※ 07s(직원 공유 카드)는 GM 확정대로 제외 — 손대지 않음.
# ※ 시간·내용 substance·로직은 불변. 시각 구조(헤더/구분/푸터)만 통일.
_DIVIDER = "━━━━━━━━━━━━━━━━"
_AUTO_FOOTER = "_본 메시지는 자동 발송입니다._"


def _unified_header(hour: str, category: str, purpose: str) -> str:
    """모든 슬롯 공통 헤더 — [HH시 · 분류 · 한줄목적] + 날짜줄 + 구분선.

    hour:     "06" 등 2자리 시
    category: "개인" | "회사" | "개인&회사"
    purpose:  한 줄 목적 (예: "하루 시작 · 운동 점검")
    """
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    weekday_kor = _WEEKDAY_KOR[now.weekday()]
    return (
        f"[{hour}시 · {category} · {purpose}]\n"
        f"📅 {date_str} ({weekday_kor})\n"
        f"{_DIVIDER}"
    )


def _build_06_body() -> str:
    """06시 — 하루 시작 아침당부·문구 + 매일 고정 운동 5종목 체크리스트 (v1.5)"""
    quote = fetch_random_quote("06시")
    if quote:
        quote_line = f'\n\n> "{quote}"\n'
    else:
        quote_line = "\n\n(추후 데이터 연결 필요 — 문구 DB 등록 후 활성화)\n"

    workout_lines = ["🏋️ 오늘 운동 점검"]
    for name, unit in DAILY_WORKOUT_ITEMS:
        workout_lines.append(f"  • {name}  ___{unit}  ☐")

    return (
        f"{_unified_header('06', '개인', '하루 시작 · 운동 점검')}\n"
        f"오늘도 좋은 하루 되십시오."
        f"{quote_line}\n"
        + "\n".join(workout_lines)
        + f"\n\n{_AUTO_FOOTER}"
    )


def _build_share_card_body() -> str:
    """07시 직원 공유용 카드 — 북극성+명언 복붙용 텍스트 (카카오톡 단톡방 반자동)"""
    now = datetime.now()
    today_str = now.strftime("%Y-%m-%d")
    weekday_kor = _WEEKDAY_KOR[now.weekday()]

    quote = fetch_random_quote("06시")
    quote_line = f'"{quote}"' if quote else '"오늘 하루도 한 걸음씩, 꾸준함이 곧 실력입니다."'

    # 복붙용 본문 — 헤더/서명 없이 깔끔하게
    share_text = (
        f"🌟 {today_str} ({weekday_kor}) 북극성\n"
        f"지속되지 않는 건강 문제를 해결한다\n\n"
        f"💬 오늘의 한 마디\n"
        f"{quote_line}"
    )

    return (
        f"📋 직원 공유용 (카톡 복붙)\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"{share_text}\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"↑ 위 텍스트를 직원 단톡방에 붙여넣기"
    )


def _build_07_body() -> str:
    """07시 — 어제 한 항로 정리 (git 완료 + todo_list 어제완료 머지) [개인&회사]"""
    now = datetime.now()
    yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%d")
    yesterday_wd = _WEEKDAY_KOR[(now - timedelta(days=1)).weekday()]
    today_str = now.strftime("%Y-%m-%d")
    weekday_kor = _WEEKDAY_KOR[now.weekday()]

    # ① git 커밋 (어제)
    commits = _git_log_between(f"{yesterday} 00:00", f"{today_str} 00:00")
    n_commits = len(commits)

    # ② todo_list 어제완료 항목
    done_todos = _fetch_yesterday_done_todos()
    n_todos = len(done_todos)

    total = n_commits + n_todos

    # 박스표: 완료 요약
    table_rows = [
        ("코드·자동화 커밋", str(n_commits)),
        ("업무 완료 항목",   str(n_todos)),
        ("합계",            str(total)),
    ]
    table_str = "\n".join(_count_table(table_rows))

    # 커밋 목록
    commit_lines = []
    for c in commits[:8]:
        commit_lines.append(f"  · {c}")
    if n_commits > 8:
        commit_lines.append(f"  ... 외 {n_commits - 8}건")

    # 업무 완료 목록 (배 이모지 적용 — ship_classify 기준대로 분류)
    todo_lines = []
    for t in done_todos[:5]:
        ship = classify_ship({"업무명": t})
        line = render_ship_line(t, "", ship)
        todo_lines.append(f"  ✅ {line}")
    if n_todos > 5:
        todo_lines.append(f"  ... 외 {n_todos - 5}건")

    commit_block = "\n".join(commit_lines) if commit_lines else "  (어제 커밋 없음)"
    todo_block = "\n".join(todo_lines) if todo_lines else "  (어제 완료 항목 없음)"

    return (
        f"{_unified_header('07', '개인&회사', '어제의 항로 결산')}\n"
        f"🏁 {yesterday} ({yesterday_wd}) 결산\n\n"
        f"   완료 요약\n"
        f"{table_str}\n\n"
        f"🚢 코드·자동화\n"
        f"{commit_block}\n\n"
        f"✅ 업무 완료\n"
        f"{todo_block}\n\n"
        f"{_DIVIDER}\n"
        f"📅 오늘 출항: {today_str} ({weekday_kor})\n"
        f"{_AUTO_FOOTER}"
    )


def _kr_amt(n) -> str:
    """한국식 금액 표기: 271488886 → '2억 7,148만'. ERP home krAmt와 동일 규칙."""
    try:
        n = round(float(n))
    except (TypeError, ValueError):
        return "—"
    sign = "-" if n < 0 else ""
    n = abs(n)
    eok = n // 100000000
    man = (n % 100000000) // 10000
    if eok > 0 and man > 0:
        return f"{sign}{eok}억 {man:,}만"
    if eok > 0:
        return f"{sign}{eok}억"
    if man > 0:
        return f"{sign}{man:,}만"
    return f"{sign}{n:,}원"


def _fetch_cfo_finance_block() -> str:
    """
    매출·지출 현황 조회 — ERP home과 동일 소스(SSOT API home_kpi) 사용.
    home(wellperion_guide)이 'action=home_kpi'의 sales/expense를 그대로 표시하므로
    9시 보고도 같은 엔드포인트를 fetch해 home과 수치를 일치시킨다 (2026-06-12 시토).
    CFO_SHEET_URL이 .env에 별도 등록돼 있으면 그것을 우선(override)한다.
    """
    src_url = CFO_SHEET_URL or SSOT_API_URL
    action = "summary" if CFO_SHEET_URL else "home_kpi"
    try:
        resp = requests.get(src_url, params={"action": action}, timeout=15)
        if resp.status_code != 200:
            return f"💰 매출·지출 현황\n  조회 실패 (HTTP {resp.status_code})"
        data = resp.json()
    except Exception as e:
        logger.warning(f"매출·지출(home_kpi) 조회 실패: {e}")
        return f"💰 매출·지출 현황\n  조회 오류: {str(e)[:80]}"

    if not data.get("ok"):
        return "💰 매출·지출 현황\n  소스 응답 ok=False (home_kpi 미연동 — 보완 중)"

    sales = data.get("sales") or {}
    expense = data.get("expense") or {}
    s_month, s_today = sales.get("month"), sales.get("today")
    e_month, e_today = expense.get("month"), expense.get("today")

    if s_month is None and e_month is None:
        # 구버전(CFO_SHEET_URL) raw 키 폴백
        s_month = data.get("revenue") or data.get("매출")
        e_month = data.get("expense") if isinstance(data.get("expense"), (int, float)) else None

    if s_month is None and e_month is None:
        return "💰 매출·지출 현황\n  데이터 없음 (home 소스 미연동 — 보완 중)"

    table_rows = [
        ("이달 매출", _kr_amt(s_month)),
        ("이달 지출", _kr_amt(e_month)),
    ]
    table_str = "\n".join(_count_table(table_rows))
    today_line = ""
    if s_today is not None or e_today is not None:
        today_line = f"\n  (오늘 매출 {_kr_amt(s_today)} · 지출 {_kr_amt(e_today)})"
    return f"💰 매출·지출 현황 (ERP home 동일 소스)\n{table_str}{today_line}"


def _build_09_body() -> str:
    """09시 — 업무·매출·지출 현황 [회사] (기존 오늘할일 → 08시 중복 폐기·대체)"""
    # ① 업무현황: C-Level별 진행 (_queue.json + status/*.json)
    progress = fetch_current_progress()

    # ② 매출·지출 (CFO 시트)
    finance_block = _fetch_cfo_finance_block()

    return (
        f"{_unified_header('09', '회사', '업무·매출·지출 현황')}\n"
        f"📋 C-Level 업무 진행현황\n"
        f"{progress}\n\n"
        f"{_DIVIDER}\n"
        f"{finance_block}\n\n"
        f"{_AUTO_FOOTER}"
    )


def _fetch_checklist_status_sheets(today: str) -> dict | None:
    """Google Sheets Apps Script API에서 오늘 점검 데이터 조회."""
    if not CHECKLIST_API_URL:
        return None
    try:
        resp = requests.get(
            f"{CHECKLIST_API_URL}?date={today}&zone=all", timeout=15
        )
        if resp.status_code == 200:
            return resp.json()
    except Exception as e:
        logger.warning(f"12시 Sheets API 조회 실패: {e}")
    return None


def _count_table(rows: list[tuple]) -> list[str]:
    """
    텔레그램 고정폭 카운트 표 (좌측 라벨 + 우측 값).
    한글/CJK 1자=2폭, ASCII 1폭으로 계산해 양쪽 칸 폭을 맞춘다.
    rows: [(label, value_str), ...]
    """
    def w(s: str) -> int:
        # CJK/한글 범위: U+1100 이상 또는 유니코드 동아시아 와이드 판정
        import unicodedata
        return sum(2 if unicodedata.east_asian_width(c) in ('W', 'F') else 1 for c in s)

    label_w = max((w(str(lbl)) for lbl, _ in rows), default=4)
    num_w = max((w(str(val)) for _, val in rows), default=1)
    bar = "─"
    top = f"┌─{bar * label_w}─┬─{bar * num_w}─┐"
    bot = f"└─{bar * label_w}─┴─{bar * num_w}─┘"
    out = [top]
    for lbl, val in rows:
        lpad = " " * (label_w - w(str(lbl)))
        rpad = " " * (num_w - w(str(val)))
        out.append(f"│ {lbl}{lpad} │ {rpad}{val} │")
    out.append(bot)
    return out


def _compile_checklist_dashboard(rows: list[dict]) -> tuple[list[tuple], str, list[str]]:
    """
    Google Sheets 행 데이터를 집계해
    (표_행_리스트, 주차_현황_문자열, 이슈_리스트) 반환.
    - 지원부 체크 = 지원_남성구역 + 지원_여성구역 합산
      (2026-06-12 지원부 공용구역 폐기 → 성별탭으로 라우팅. '공용구역' 시트는 sentinel/미존재.)
    - 시설부 체크 = 시설_남성구역 + 시설_여성구역 합산
      (단, 본 대시보드 API 호출은 dept=support 단일 → 시설부 행은 데이터 부재로 '-' 표기.)
    - 주차 현황  = E-6 주차장 단일 항목
    GAS doGet은 rows[].zone 에 실제 시트명을 그대로 넣음(예 '지원_남성구역').
    """
    # 실제 시트명(zone) → 집계 버킷. 지원부=지원_*, 시설부=시설_*.
    SUPPORT_ZONES = ("지원_남성구역", "지원_여성구역")
    FACILITY_ZONES = ("시설_남성구역", "시설_여성구역")
    support = {"total": 0, "done": 0}
    facility = {"total": 0, "done": 0}
    issues: list[str] = []
    parking_checked: bool | None = None

    for r in rows:
        zone = r.get("zone", "")
        checked = bool(r.get("checked", False))
        issue = r.get("issue", "")
        name = r.get("name", "")

        if zone in SUPPORT_ZONES:
            support["total"] += 1
            if checked:
                support["done"] += 1
        elif zone in FACILITY_ZONES:
            facility["total"] += 1
            if checked:
                facility["done"] += 1

        # 주차 항목 별도 추적 (E-6 주차장)
        if "주차" in name:
            parking_checked = checked

        if issue:
            issues.append(f"  - {name}: {issue}")

    def fmt_score(done: int, total: int) -> str:
        return f"{done}/{total}" if total > 0 else "-"

    parking_str = "정상" if parking_checked else ("미완료" if parking_checked is False else "-")

    table_rows = [
        ("지원부 체크", fmt_score(support["done"], support["total"])),
        ("시설부 체크", fmt_score(facility["done"], facility["total"])),
        ("주차 현황",   parking_str),
    ]
    return table_rows, parking_str, issues


def _build_checklist_block(slot_label: str) -> str:
    """
    12시/18시 공용 — 체크리스트 대시보드 박스표 블록 생성.
    slot_label: "12:00" | "18:00"
    """
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    weekday_kor = _WEEKDAY_KOR[now.weekday()]
    day_kor = ["월", "화", "수", "목", "금", "토", "일"][now.weekday()]

    sheets_data = _fetch_checklist_status_sheets(today)
    dashboard_url = "https://wellperion-cao.github.io/wellperion-automation/coo/check/%EC%A7%80%EC%9B%90%EB%B6%80%20%EC%B2%B4%EA%B3%84.html"

    if sheets_data and sheets_data.get("rows"):
        table_rows, parking_str, issues = _compile_checklist_dashboard(sheets_data["rows"])
        table_lines = _count_table(table_rows)
        table_str = "\n".join(table_lines)

        issue_block = ""
        if issues:
            issue_block = "\n\n[이슈 발생]\n" + "\n".join(issues[:5])
            if len(issues) > 5:
                issue_block += f"\n  ... 외 {len(issues) - 5}건"
    else:
        table_str = "(점검 데이터 없음 — 실무진 점검앱 미입력 또는 API 미연결)"
        issue_block = ""

    return (
        f"🛠 시설·지원 점검 현황 — {slot_label} ({day_kor})\n"
        f"   체크리스트 진행 상황\n"
        f"{table_str}"
        f"{issue_block}\n"
        f"🔗 대시보드: {dashboard_url}"
    )


def _build_12_body() -> str:
    """12시 — 시설·지원 체크리스트 대시보드 진행현황 박스표"""
    checklist_block = _build_checklist_block("12:00")

    return (
        f"{_unified_header('12', '회사', '오전 시설·지원·주차 현황')}\n"
        f"{checklist_block}\n\n"
        f"{_AUTO_FOOTER}"
    )


def _build_15_body() -> str:
    """15시 — GM 진행 중 오늘 카드형 + C-Level별 진행현황"""
    # 섹션1: GM 오늘 활성 + 진행중만 카드형
    cards = fetch_gm_todo_cards(only_in_progress=True)

    if cards is None:
        gm_section = "  (API 조회 실패 — 업무현황 연결 확인)"
        n_gm = 0
    else:
        today_cards, _ = _classify_todo_cards(cards)
        n_gm = len(today_cards)
        if today_cards:
            rendered = [_render_card(c) for c in today_cards[:10]]
            if n_gm > 10:
                rendered.append(f"  ...외 {n_gm - 10}건")
            gm_section = "\n\n".join(rendered)
        else:
            gm_section = "  진행 중 업무 없음"

    # 섹션2: C-Level 진행현황
    progress = fetch_current_progress()

    return (
        f"{_unified_header('15', '개인&회사', '오늘 항로 1차 정리 · 진행 체크')}\n"
        f"👤 GM 진행 중 ({n_gm}건)\n"
        f"{gm_section}\n\n"
        f"{_DIVIDER}\n"
        f"🏢 C-Level 진행현황\n"
        f"{progress}\n\n"
        f"{_AUTO_FOOTER}"
    )


def _build_18_body() -> str:
    """18시 — 퇴근 인사 + 체크리스트 최종 현황 + 오늘 성과"""
    now = datetime.now()
    today_str = now.strftime("%Y-%m-%d")
    weekday_kor = _WEEKDAY_KOR[now.weekday()]

    # 체크리스트 현황 (12시와 동일 소스, 18시 기준으로 재조회)
    checklist_block = _build_checklist_block("18:00")

    # 오늘 성과: 오늘자 git 커밋 집계
    today = now.strftime("%Y-%m-%d")
    tomorrow = (now + timedelta(days=1)).strftime("%Y-%m-%d")
    today_commits = _git_log_between(f"{today} 00:00", f"{tomorrow} 00:00", max_lines=10)
    if today_commits:
        commit_section = f"  커밋 {len(today_commits)}건\n" + "\n".join(f"  - {c}" for c in today_commits[:7])
        if len(today_commits) > 7:
            commit_section += f"\n  ... 외 {len(today_commits) - 7}건"
    else:
        commit_section = "  오늘 기록된 커밋 없음"

    # 명언
    quote = fetch_random_quote("18시")
    if quote:
        quote_line = f'\n> "{quote}"\n'
    else:
        quote_line = "\n"

    return (
        f"{_unified_header('18', '회사', '오후 시설·지원·주차 · 퇴근 루틴')}\n"
        f"🌙 오늘도 수고하셨습니다.\n\n"
        f"{checklist_block}\n\n"
        f"{_DIVIDER}\n"
        f"📊 오늘 성과\n"
        f"{commit_section}\n"
        f"{quote_line}"
        f"{_AUTO_FOOTER}"
    )


def _build_21_body() -> str:
    """21시 — 오늘 최종 정리 + 내일 항로점 브릿지 [개인&회사]"""
    now = datetime.now()
    today_str = now.strftime("%Y-%m-%d")
    weekday_kor = _WEEKDAY_KOR[now.weekday()]
    tmr_str = (now + timedelta(days=1)).strftime("%Y-%m-%d")
    tmr_wd = _WEEKDAY_KOR[(now + timedelta(days=1)).weekday()]

    # ① 오늘 git 커밋 (완료 성과)
    tomorrow = (now + timedelta(days=1)).strftime("%Y-%m-%d")
    today_commits = _git_log_between(f"{today_str} 00:00", f"{tomorrow} 00:00", max_lines=20)
    n_commits = len(today_commits)

    # ② 오늘 완료된 todo (updatedAt = 오늘 + 상태=완료)
    try:
        resp = requests.get(SSOT_API_URL, params={"action": "todo_list"}, timeout=15)
        done_today: list[str] = []
        if resp.status_code == 200:
            data = resp.json()
            if data.get("ok"):
                for x in data.get("data", []):
                    st = str(x.get("상태", ""))
                    updated = str(x.get("수정일", "") or x.get("updatedAt", ""))
                    title = str(x.get("업무명", "")).strip()
                    if st in _TODO_DONE_STATUSES and updated.startswith(today_str) and title:
                        done_today.append(title[:50])
    except Exception as e:
        logger.warning(f"21시 오늘완료 조회 실패: {e}")
        done_today = []

    # ③ 미완료 → 내일 항로점 (브릿지)
    open_cards = _fetch_open_todo_cards_for_tomorrow()

    # 박스표: 오늘 성과 요약
    table_rows = [
        ("코드·자동화", str(n_commits)),
        ("업무 완료",   str(len(done_today))),
        ("미완 이월",   str(len(open_cards))),
    ]
    table_str = "\n".join(_count_table(table_rows))

    # 오늘 커밋 목록
    commit_lines = [f"  · {c}" for c in today_commits[:7]]
    if n_commits > 7:
        commit_lines.append(f"  ... 외 {n_commits - 7}건")
    commit_block = "\n".join(commit_lines) if commit_lines else "  (오늘 커밋 없음)"

    # 업무 완료 목록
    done_lines = [f"  ✅ {t}" for t in done_today[:5]]
    if len(done_today) > 5:
        done_lines.append(f"  ... 외 {len(done_today) - 5}건")
    done_block = "\n".join(done_lines) if done_lines else "  (오늘 완료 항목 없음)"

    # 내일 항로점 (미완료 → 이월)
    bridge_lines = []
    for c in open_cards[:8]:
        ship = classify_ship(c)
        owner = c.get("담당자", "")
        due = c.get("due", "")
        line = render_ship_line(c["업무명"], owner, ship, due)
        st_part = f" [{c['상태']}]" if c.get("상태") else ""
        bridge_lines.append(f"  {line}{st_part}")
    if len(open_cards) > 8:
        bridge_lines.append(f"  ... 외 {len(open_cards) - 8}건")
    bridge_block = "\n".join(bridge_lines) if bridge_lines else "  (미완료 이월 항목 없음 — 오늘 항로 완주)"

    return (
        f"{_unified_header('21', '개인&회사', '오늘 항로 최종 정리 · 내일 항로 정립')}\n"
        f"   오늘의 성과\n"
        f"{table_str}\n\n"
        f"🚢 코드·자동화\n"
        f"{commit_block}\n\n"
        f"✅ 업무 완료\n"
        f"{done_block}\n\n"
        f"{_DIVIDER}\n"
        f"🔗 내일 항로점 ({tmr_str} {tmr_wd})\n"
        f"  (오늘 미완 → 내일 이월)\n"
        f"{bridge_block}\n\n"
        f"{_AUTO_FOOTER}"
    )


def _build_22_body() -> str:
    """22시 — 취침·전자기기off + 마무리(종료) 인사 통합 + 북극성 + 명언 [개인]

    [2026-06-08 GM 지시] 기존 22:00 취침안내 + 22:25 종료인사(별도 예약작업)가
    25분 내 중복 발송되던 것을 22:00 단일 메시지로 통합. 별도 22:25 종료인사
    예약작업(Wellperion-PC-Shutdown-Greeting-Live)은 제거.
    """
    quote = fetch_random_quote("22시")
    if quote:
        quote_line = f'\n> "{quote}"\n'
    else:
        quote_line = "\n> \"충분한 수면이 내일의 판단력을 만듭니다.\"\n"

    return (
        f"{_unified_header('22', '개인', '전자기기 OFF · 취침 · 북극성')}\n"
        f"오늘 하루도 고생 많으셨습니다, GM님.\n"
        f"📵 전자기기 off — 수면 루틴 시작\n\n"
        f"🌟 북극성\n"
        f"  GM만 보는 G1 오케스트레이션 +\n"
        f"  웰페리온 스포츠클럽 ERP 제품화\n"
        f"{quote_line}"
        f"{_AUTO_FOOTER}"
    )


# ── 23시 마감 점검 차트 상세형 헬퍼 (today_live 지원부 회차×성별) ──────────────
_SUPPORT_DASHBOARD_URL = (
    "https://wellperion-cao.github.io/wellperion-automation/coo/check/"
    "%EC%A7%80%EC%9B%90%EB%B6%80%20%EC%B2%B4%EA%B3%84.html"
)


def _cjk_w(s: str) -> int:
    """CJK/한글 1자=2폭, ASCII 1폭으로 표시폭 계산 (_count_table 방식 재사용)."""
    import unicodedata
    return sum(2 if unicodedata.east_asian_width(c) in ("W", "F") else 1 for c in s)


def _pad(s: str, width: int, align: str = "left") -> str:
    """표시폭 기준 패딩 (한글 폭 보정). align: left|right|center."""
    s = str(s)
    gap = max(0, width - _cjk_w(s))
    if align == "right":
        return " " * gap + s
    if align == "center":
        l = gap // 2
        return " " * l + s + " " * (gap - l)
    return s + " " * gap


def _fetch_support_today_live(today: str) -> dict | None:
    """지원부 라이브 점검 GAS에서 오늘자 회차×성별 데이터 조회 (today_live).

    today: "YYYY-MM-DD". ok=true면 응답 dict 반환, 아니면 None.
    """
    try:
        resp = requests.get(
            f"{SUPPORT_CHECK_API_URL}"
            f"?action=today_live&dept=support&date={today}&_pv={int(time.time())}",
            timeout=20,
            allow_redirects=True,
        )
        if resp.status_code == 200:
            data = resp.json()
            if data.get("ok"):
                return data
        logger.warning(
            f"23시 지원부 today_live 응답 비정상: status={resp.status_code}"
        )
    except Exception as e:
        logger.warning(f"23시 지원부 today_live 조회 실패: {e}")
    return None


def _fetch_dept_weekly(dept: str) -> dict | None:
    """시설/주차 weekly 조회 (오늘자 total/done). 실패 시 None."""
    try:
        resp = requests.get(
            f"{SUPPORT_CHECK_API_URL}?action=weekly&dept={dept}&_pv={int(time.time())}",
            timeout=20,
            allow_redirects=True,
        )
        if resp.status_code == 200:
            data = resp.json()
            if data.get("ok"):
                return data
    except Exception as e:
        logger.warning(f"23시 {dept} weekly 조회 실패: {e}")
    return None


def _build_support_check_chart(d: dict) -> str:
    """today_live dict → 지원부 회차×성별 고정폭 차트 (텔레그램 코드블록)."""
    now = datetime.now()
    md = now.strftime("%m-%d")
    weekday_kor = _WEEKDAY_KOR[now.weekday()]

    g = d.get("byGender", {})
    m = g.get("m", {})
    f = g.get("f", {})

    def pct(done: int, total: int) -> str:
        return f"{round(done / total * 100)}%" if total else "-"

    def cell(part: dict, key: str) -> str:
        # 회차별 done/total — key in {"am","pm","close"}
        return f"{part.get(key, 0)}/{part.get(key + 'Total', 0)}"

    rows = [
        ("오전", "am"),
        ("오후", "pm"),
        ("마감", "close"),
    ]

    # 열 폭 계산
    h_round, h_m, h_f, h_sum = "회차", "남", "여", "합계"
    m_cells = [cell(m, k) for _, k in rows]
    f_cells = [cell(f, k) for _, k in rows]
    sum_cells = [
        f"{d.get(k, 0)}/{d.get(k + 'Total', 0)} {pct(d.get(k, 0), d.get(k + 'Total', 0))}"
        for _, k in rows
    ]

    w_round = max(_cjk_w(h_round), *(_cjk_w(r[0]) for r in rows), _cjk_w("종일"))
    w_m = max(_cjk_w(h_m), *(_cjk_w(c) for c in m_cells))
    w_f = max(_cjk_w(h_f), *(_cjk_w(c) for c in f_cells))
    w_sum = max(_cjk_w(h_sum), *(_cjk_w(c) for c in sum_cells))

    lines = [
        f"{_pad(h_round, w_round)}  {_pad(h_m, w_m)}  {_pad(h_f, w_f)}  {_pad(h_sum, w_sum)}",
    ]
    for (label, _key), mc, fc, sc in zip(rows, m_cells, f_cells, sum_cells):
        lines.append(
            f"{_pad(label, w_round)}  {_pad(mc, w_m)}  {_pad(fc, w_f)}  {_pad(sc, w_sum)}"
        )

    total = d.get("total", 0)
    done = d.get("done", 0)
    sep_w = w_round + w_m + w_f + w_sum + 6
    lines.append("─" * max(8, sep_w))
    all_sum = f"{done}/{total} {pct(done, total)}"
    lines.append(
        f"{_pad('종일', w_round)}  {_pad('', w_m)}  {_pad('', w_f)}  {_pad(all_sum, w_sum)}"
    )

    chart = "\n".join(lines)
    return f"🛠 지원부 점검 — {md}({weekday_kor})\n```\n{chart}\n```"


def _build_support_weakspot(d: dict) -> str:
    """byGender 회차×성별 칸 중 분모>0이고 완료율 최저인 칸 = 자동 약점 한 줄."""
    g = d.get("byGender", {})
    gender_label = {"m": "남", "f": "여"}
    round_label = {"am": "오전", "pm": "오후", "close": "마감"}

    worst = None  # (pct, gender, rnd, done, total)
    for gk in ("m", "f"):
        part = g.get(gk, {})
        for rk in ("am", "pm", "close"):
            total = part.get(rk + "Total", 0)
            if total <= 0:
                continue
            done = part.get(rk, 0)
            p = round(done / total * 100)
            cand = (p, gender_label[gk], round_label[rk], done, total)
            if worst is None or p < worst[0]:
                worst = cand

    if worst is None:
        return "⚠️ 짚을 점: 진행 데이터 없음"
    p, gl, rl, done, total = worst
    if p >= 100:
        return "✅ 짚을 점 없음 — 전 회차 완료"
    return f"⚠️ 짚을 점: {gl} {rl} {done}/{total}({p}%) — 독려 필요"


def _dept_status_lines() -> str:
    """4부서 상태 줄 (지원=별도 차트, 나머지 3개)."""
    facility = _fetch_dept_weekly("facility")
    parking = _fetch_dept_weekly("parking")

    def dept_line(icon: str, name: str, data: dict | None) -> str:
        if data is None:
            return f"{icon} {name}: -"
        total = data.get("total", 0)
        if total == 0:
            return f"{icon} {name}: 미가동(자체점검 준비 중)"
        done = data.get("done", 0)
        pct = round(done / total * 100) if total else 0
        return f"{icon} {name}: {done}/{total}({pct}%)"

    return (
        f"{dept_line('🏗', '시설부', facility)}\n"
        f"{dept_line('🅿', '주차', parking)}\n"
        f"🏢 운영부: 점검 체계 없음(규정·매뉴얼 운영)"
    )


def _build_23_body() -> str:
    """23시 — 마감 점검 현황 차트 상세형 [회사]

    today_live(지원부 회차×성별) 성공 시 차트+약점+4부서 상태.
    실패 시 기존 _build_checklist_block('23:00')로 폴백(빈 메시지/크래시 금지).

    [2026-06-08 GM 지시] PC 종료 22:30→23:30 변경으로 23:00 발송 환경 확보 →
    23시 마감 점검 슬롯 복원(10슬롯 정본).
    [2026-06-18 시우] today_live 차트 상세형 업그레이드(라이브 GAS).
    """
    today = datetime.now().strftime("%Y-%m-%d")
    live = _fetch_support_today_live(today)

    if live is None:
        # 폴백 — 기존 12/18 공용 블록 재사용
        checklist_block = _build_checklist_block("23:00")
        return (
            f"{_unified_header('23', '회사', '마감 시설·지원·주차 현황')}\n"
            f"{checklist_block}\n\n"
            f"{_AUTO_FOOTER}"
        )

    chart = _build_support_check_chart(live)
    weakspot = _build_support_weakspot(live)
    dept_lines = _dept_status_lines()

    return (
        f"{_unified_header('23', '회사', '마감 점검 현황')}\n"
        f"{chart}\n"
        f"{weakspot}\n\n"
        f"{dept_lines}\n\n"
        f"🔗 대시보드: {_SUPPORT_DASHBOARD_URL}\n\n"
        f"{_AUTO_FOOTER}"
    )


# ── 지원부 점검 미완 자동 독려 (오후17시·마감22시·미완시만·하루1회) — 시우 2026-06-18 ──
# 점검 관리 방(점검 독려 대상). 핵심멤버방 3분류 분리(시우 102, 2026-06-24): 점검 알림 → '점검 관리' 방.
# .env TELEGRAM_CHECK_CHAT_ID 사용. 미설정 시 구 핵심멤버방(현 '종합 접수처')으로 폴백.
CHECK_NUDGE_CHAT_ID = int(ENV.get("TELEGRAM_CHECK_CHAT_ID") or -5065206276)


def _build_nudge_body(shift: str) -> str | None:
    """지원부 점검 회차(shift) 미완 시 독려 1줄 생성. shift ∈ {'pm','close'}.

    today_live(support) 조회 → 해당 회차만 done/total·성별 분리.
    조회 실패/None → None(발송 스킵). 완료(done>=total 또는 total==0) → None(침묵).
    미완이면 독려 문자열 반환(지어내기 금지 — 라이브 GAS 실값만).
    """
    if shift not in ("pm", "close"):
        return None
    today = datetime.now().strftime("%Y-%m-%d")
    live = _fetch_support_today_live(today)
    if live is None:
        return None  # 조회 실패 → 침묵

    total = live.get(shift + "Total", 0)
    done = live.get(shift, 0)
    if total == 0 or done >= total:
        return None  # 완료/분모없음 → 침묵

    g = live.get("byGender", {})
    m = g.get("m", {})
    f = g.get("f", {})
    mT, m_done = m.get(shift + "Total", 0), m.get(shift, 0)
    fT, f_done = f.get(shift + "Total", 0), f.get(shift, 0)

    if shift == "pm":
        label, action = "오후조", "마감 전 점검 부탁드립니다"
    else:
        label, action = "마감조", "마감 점검 부탁드립니다"

    return (
        f"⚠️ [{label}] 지원부 점검 미완 — "
        f"남 {m_done}/{mT} · 여 {f_done}/{fT} (합 {done}/{total}). {action}.\n"
        f"🔗 대시보드: {_SUPPORT_DASHBOARD_URL}"
    )


def run_nudge(shift: str) -> None:
    """독려 디스패치 — 핵심멤버방으로만 발송. 빌더 None이면 침묵(완료/조회실패).
    하루·shift당 1회(state.json nudge_sent[date] 마커로 dedup). 기존 슬롯 동작 불변."""
    today = datetime.now().strftime("%Y-%m-%d")
    label = f"[지원부 독려:{shift}]"

    # dedup — 같은 날·같은 shift 1회만
    state = read_state()
    sent_map = state.get("nudge_sent", {})
    sent_today = sent_map.get(today, [])
    if shift in sent_today:
        logger.info(f"{label} 오늘 이미 발송됨 — skip")
        return

    body = _build_nudge_body(shift)
    if body is None:
        logger.info(f"{label} 미완 아님/조회실패 — 침묵(발송 스킵)")
        return

    success = send_telegram(CHECK_NUDGE_CHAT_ID, body)
    if success:
        sent_today.append(shift)
        sent_map[today] = sent_today
        # 오래된 날짜 정리(최근 7일만 유지) — state 비대화 방지
        recent = sorted(sent_map.keys())[-7:]
        state["nudge_sent"] = {k: sent_map[k] for k in recent}
        write_state(state)
        logger.info(f"{label} 점검관리방 발송 완료 chat_id={CHECK_NUDGE_CHAT_ID}")
    else:
        logger.error(f"{label} 핵심멤버방 발송 실패 — dedup 미기록(다음 트리거 재시도)")


SLOT_BUILDERS = {
    "06": _build_06_body,
    "07s": _build_share_card_body,
    "07": _build_07_body,
    "09": _build_09_body,
    "12": _build_12_body,
    "15": _build_15_body,
    "18": _build_18_body,
    "21": _build_21_body,
    "22": _build_22_body,
    "23": _build_23_body,
}


# ── 핵심 보고 실행 함수 ───────────────────────────────────────────────────────
def run_report(slot: str, test_mode: bool = False) -> None:
    """
    slot: "06" | "07s" | "07" | "09" | "12" | "15" | "18" | "21" | "22" | "23"
    """
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    label = f"[{'TEST ' if test_mode else ''}{slot}시 보고]"
    logger.info(f"{label} 트리거 실행 시작 ({now_str})")

    owner_id = get_owner_id()
    if not owner_id:
        logger.error(f"{label} owner_id 미등록 — state.json 확인 필요. 보고 생략.")
        return

    try:
        builder = SLOT_BUILDERS.get(slot)
        if builder:
            body = builder()
        else:
            body = (
                f"[웰페리온] {slot}시 자동 보고\n"
                f"━━━━━━━━━━━━━━━━\n"
                f"(슬롯 미정의 — 스케줄 설정 확인 필요)\n\n"
                f"_본 메시지는 자동 발송입니다._"
            )
    except Exception as e:
        logger.error(f"{label} 보고 본문 생성 예외: {e}")
        body = (
            f"[웰페리온] {slot}시 자동화 실패\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"보고 생성 중 오류가 발생했습니다.\n"
            f"오류: {str(e)[:300]}\n\n"
            f"_본 메시지는 자동 발송입니다._"
        )

    if test_mode:
        body = f"[테스트 발송] {now_str}\n\n" + body

    success = send_telegram(owner_id, body)
    if success:
        logger.info(f"{label} 텔레그램 발송 완료 owner_id={owner_id}")
    else:
        logger.error(f"{label} 텔레그램 발송 실패 — 재시도 소진")
        logger.critical(f"{label} CRITICAL: 텔레그램 도달 불가 — 수동 확인 필요")


# ── 테스트 모드 슬롯 결정 ──────────────────────────────────────────────────────
def get_test_slot() -> str:
    """현재 시각 기준으로 가장 가까운 보고 슬롯 반환 (테스트 레이블용)."""
    h = datetime.now().hour
    if h < 7:
        return "06"
    elif h < 9:
        return "07"
    elif h < 12:
        return "09"
    elif h < 15:
        return "12"
    elif h < 18:
        return "15"
    elif h < 21:
        return "18"
    elif h < 22:
        return "21"
    elif h < 23:
        return "22"
    else:
        return "23"


# ── 수동 즉시 테스트 헬퍼 (--manual-test 옵션) ───────────────────────────────
def run_manual_test(slot: str) -> None:
    """특정 슬롯 즉시 1회 발송 (개발·검증용)."""
    logger.info(f"=== 수동 테스트 발송: {slot}시 슬롯 ===")
    run_report(slot, test_mode=True)
    logger.info("=== 수동 테스트 완료 ===")


def verify_publish_sweep() -> None:
    """IG 발행검증 자동 대조 스윕 (30분 주기) — INC-003 자동화.
    발행검증대기 IG 항목을 라이브 게시물 캡션과 대조해 일치하면 발행완료 도장(+커밋·푸시).
    별도 프로세스(playwright)로 실행해 스케줄러 블로킹 없음. 실패는 로그만(다음 스윕 재시도)."""
    script = REPO_ROOT / "scripts" / "ig_publish_verify.py"
    if not script.exists():
        return
    try:
        env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
        proc = subprocess.run(
            [sys.executable, str(script), "--commit"],
            cwd=str(REPO_ROOT), capture_output=True, text=True,
            encoding="utf-8", errors="replace", env=env, timeout=600,
        )
        tail = (proc.stdout or "").strip().splitlines()[-1:] or ["(출력없음)"]
        logger.info(f"verify_publish_sweep 완료: {tail[0]}")
    except Exception as exc:
        logger.warning(f"verify_publish_sweep 실패(무해, 다음 스윕 재시도): {exc}")


# ── 스케줄러 메인 ─────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="웰페리온 일일 자동 보고 스케줄러 v1.1")
    parser.add_argument(
        "--test",
        action="store_true",
        help="테스트 모드: 1시간 주기로 실행 (정규 6회 스케줄 대신)",
    )
    parser.add_argument(
        "--manual-test",
        metavar="SLOT",
        help="특정 슬롯 즉시 1회 발송 후 종료 (예: --manual-test 06)",
    )
    args = parser.parse_args()

    # 수동 즉시 테스트
    if args.manual_test:
        run_manual_test(args.manual_test)
        return

    scheduler = BlockingScheduler(timezone="Asia/Seoul")

    # [2026-05-31 CTO 제거] archive_result_watcher · planning_to_archive_watcher
    #   두 노션 추종 감지기는 노션 결과물DB·Start기획DB 폐기(2026-05-29)로 상시 0건·
    #   알림 0건 확정 → if False 사문(死文) 블록 삭제. 파일(archive_result_watcher.py·
    #   planning_to_archive_watcher.py)은 디스크 보존(가역적). 참조: docs/노션_웰페리온 ERP_리뉴얼_계획.md.

    # [2026-06-01 CTO 공식 폐지] auto_task_watcher(노션 업무자동화DB 폴링→Claude CLI
    #   자동실행)는 노션 업무자동화DB '[폐기]'(2026-06-01)로 방식 자체가 구식.
    #   소스도 소실(git 미추적)되어 import 항시 실패·매 부팅 ERROR 로그만 남기던
    #   사문 블록을 제거(GM 결재). 정기 실행 트리거는 Windows Task Scheduler가 담당,
    #   H-15분 사전 알림은 pre_task_notifier(status/schedule.json SSOT)가 유지.

    # ── 업무자동화 DB H-15분 사전 알림 Notifier (5분 주기) — CTO v1.0 ─────────
    try:
        from pre_task_notifier import check_and_notify as _pre_task_notify
        scheduler.add_job(
            _pre_task_notify,
            trigger=IntervalTrigger(minutes=5),
            id="pre_task_notifier",
            misfire_grace_time=600,
            coalesce=True,
            next_run_time=datetime.now(),
        )
        logger.info("pre_task_notifier 등록 완료 (5분 주기) — CTO v1.0")
    except ImportError as e:
        logger.error(f"pre_task_notifier 임포트 실패 — 알림기 미등록: {e}")

    # [2026-05-31 CTO 제거] permission_watcher(노션 통합 권한 감시)는 노션 미사용
    #   확정으로 감시 가치 0·알림 0건 → if False 사문 블록 삭제. permission_watcher.py는
    #   디스크 보존(가역적). 참조: docs/노션_웰페리온 ERP_리뉴얼_계획.md.

    # [2026-06-02 CTO 제거] status_change_watcher(C-Level 상태변경 1분주기 자동발송)는
    #   status_change_watcher.py가 미구현(git 이력·디스크 0)으로 매 부팅 ImportError만
    #   발생 → 기능 0의 사문 블록 제거. C-Level 상태 보고는 각 에이전트 직접 발송으로 대체.
    #   필요 시 status_change_watcher.py 작성 후 복원(가역적).

    # status_regression_guard 폐기 (2026-05-22 GM 지시)
    # 사유: 진행중→진행예정→진행중(자동복원) 무의미한 사이클 + GM 의도 덮어쓰기 위험.
    # 동시에 "진행예정" select 옵션 자체 폐기, 휴면 상태는 "보류" 단일로 통합.

    # ── v1.2: 봇 헬스체크 (15분 주기) ───────────────────────────────────────
    scheduler.add_job(
        health_check_bot,
        trigger=IntervalTrigger(minutes=15),
        id="bot_health_check",
        misfire_grace_time=120,
        coalesce=True,
        next_run_time=datetime.now(),
    )
    logger.info("bot_health_check 등록 완료 (15분 주기) — v1.2")

    # ── v1.2: .env mtime 감시 (5분 주기) ─────────────────────────────────────
    scheduler.add_job(
        check_env_reload,
        trigger=IntervalTrigger(minutes=5),
        id="env_reload_watcher",
        misfire_grace_time=60,
        coalesce=True,
    )
    logger.info("env_reload_watcher 등록 완료 (5분 주기) — v1.2")

    # ── IG 발행검증 자동 대조 스윕 (30분 주기) — INC-003 자동화 ───────────────────
    scheduler.add_job(
        verify_publish_sweep,
        trigger=IntervalTrigger(minutes=30),
        id="ig_publish_verify_sweep",
        misfire_grace_time=600,
        coalesce=True,
        next_run_time=datetime.now(),
    )
    logger.info("ig_publish_verify_sweep 등록 완료 (30분 주기) — 발행검증대기→발행완료 자동")

    # ── ERP 시스템 현황 발행 (30분 주기) — 서버 상태를 ERP가 읽게 push — CTO 2026-06-16 ──
    def _publish_erp_status():
        try:
            subprocess.run(
                [sys.executable, "scripts/erp_status_publisher.py", "--push"],
                cwd=str(BASE.parent), timeout=150,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            logger.info("erp_status_publisher 실행 완료 (시스템 현황 ERP 발행)")
        except Exception as e:
            logger.error(f"erp_status_publisher 실행 실패: {e}")

    scheduler.add_job(
        _publish_erp_status,
        trigger=IntervalTrigger(minutes=30),
        id="erp_status_publisher",
        misfire_grace_time=600,
        coalesce=True,
        next_run_time=datetime.now(),
    )
    logger.info("erp_status_publisher 등록 완료 (30분 주기) — 시스템 현황 ERP 발행")

    # ── KPI 자동집계 (매일 07:50·21:00 · 기동 시 1회) — S2 라이브 배지 갱신 — CTO 2026-06-23 ──
    def _collect_kpi():
        try:
            subprocess.run(
                [sys.executable, "scripts/kpi_collector.py"],
                cwd=str(BASE.parent), timeout=120,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            logger.info("kpi_collector 실행 완료 (kpi_values.json 갱신)")
        except Exception as e:
            logger.error(f"kpi_collector 실행 실패: {e}")

    scheduler.add_job(
        _collect_kpi,
        trigger=CronTrigger(hour=7, minute=50),
        id="kpi_collector_morning",
        misfire_grace_time=600,
        coalesce=True,
    )
    scheduler.add_job(
        _collect_kpi,
        trigger=CronTrigger(hour=21, minute=0),
        id="kpi_collector_evening",
        misfire_grace_time=600,
        coalesce=True,
        next_run_time=datetime.now(),
    )
    logger.info("kpi_collector 등록 완료 (07:50·21:00 일 2회) — S2 KPI 라이브 배지")

    # ── 주차 매출 일일 수집 (매일 07:00 + 기동 시 1회) — 08:00 보고 전 갱신 — CTO 2026-06-19 ──
    def _crawl_parking_revenue():
        try:
            subprocess.run(
                [sys.executable, "scripts/parking_revenue_crawler.py", "--push"],
                cwd=str(BASE.parent), timeout=150,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            logger.info("parking_revenue_crawler 실행 완료 (주차 매출 발행)")
        except Exception as e:
            logger.error(f"parking_revenue_crawler 실행 실패: {e}")

    scheduler.add_job(
        _crawl_parking_revenue,
        trigger=CronTrigger(hour=7, minute=0, timezone="Asia/Seoul"),
        id="parking_revenue_crawler",
        misfire_grace_time=3600,
        coalesce=True,
        next_run_time=datetime.now(),
    )
    logger.info("parking_revenue_crawler 등록 완료 (매일 07:00) — 주차 매출 ERP 발행")

    # ── 마케팅 대시보드 캐시 워밍 (15분 주기) — 무거운 집계를 미리 데워 사용자 항상 ~1.5초 — CTO 2026-06-19 ──
    # 콜드 컴퓨트(type_channel 23s·funnel_conversion 13s)를 백그라운드에서 nocache=1로 강제 재계산·재캐싱.
    # Claude/LLM 토큰 무관(구글 GAS 실행). TTL 30분 > 주기 15분이라 항상 따뜻하게 유지.
    _FUNNEL_EXEC = 'https://script.google.com/macros/s/AKfycbzdwSCCSSJ6JXLDoWuo7HG0JmBM2iy10TujFQ_O5JbTjnWaN7gOk-ddA4IAvsNfelg0xA/exec'

    def _warm_dashboard_cache():
        try:
            now = datetime.now()
            frm = now.strftime("%Y-%m") + "-01"
            to  = now.strftime("%Y-%m-%d")
            rng = f"&from={frm}&to={to}"
            qs = [
                "action=funnel_conversion",
                "action=type_channel_breakdown" + rng,
                "action=click_stats" + rng,
                "action=period_breakdown" + rng,
            ]
            for q in qs:
                try:
                    requests.get(f"{_FUNNEL_EXEC}?{q}&nocache=1", timeout=60)
                except Exception:
                    pass  # 개별 실패 무시 — 다음 주기 재시도
            logger.info("dashboard_cache_warm 실행 완료 (마케팅 대시보드 캐시 데움)")
        except Exception as e:
            logger.error(f"dashboard_cache_warm 실행 실패: {e}")

    scheduler.add_job(
        _warm_dashboard_cache,
        trigger=IntervalTrigger(minutes=15),
        id="dashboard_cache_warm",
        misfire_grace_time=600,
        coalesce=True,
        next_run_time=datetime.now(),
    )
    logger.info("dashboard_cache_warm 등록 완료 (15분 주기) — 마케팅 대시보드 캐시 워밍")

    # ── 푸시 스위퍼 (5분 주기) — 밀린 커밋 안전 드레인(fetch+rebase+push) — CTO 2026-06-19 ──
    # 부모 GitLock 안에서 rebase 못 하고 쌓인 커밋을 lock 밖에서 안전하게 올린다.
    # 자동 push 실패(non-ff 경합)의 근본 해결: 경합은 조용히 두고 스위퍼가 확실히 동기화.
    def _push_sweeper():
        try:
            subprocess.run(
                [sys.executable, "scripts/post_commit_push.py", "--sweep"],
                cwd=str(BASE.parent), timeout=120,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        except Exception as e:
            logger.error(f"push_sweeper 실행 실패: {e}")

    scheduler.add_job(
        _push_sweeper,
        trigger=IntervalTrigger(minutes=5),
        id="push_sweeper",
        misfire_grace_time=300,
        coalesce=True,
        next_run_time=datetime.now(),
    )
    logger.info("push_sweeper 등록 완료 (5분 주기) — 미푸시 커밋 안전 드레인")

    # ── 큐 아카이브 스윕 (6시간 주기) — _queue.json 비대화 방지 — CTO 2026-06-24 ──
    # 지난 입항(terminal)·폐기 배를 _queue_archive.json 으로 분리해 active 큐를 작게 유지.
    # 멱등·fail-open·커밋 없음(git add 까지). G1 은 archive 도 함께 fetch 하므로 표시 무손상.
    def _queue_archive_sweep():
        try:
            subprocess.run(
                [sys.executable, "scripts/queue_archive_sweep.py"],
                cwd=str(BASE.parent), timeout=120,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        except Exception as e:
            logger.error(f"queue_archive_sweep 실행 실패: {e}")

    scheduler.add_job(
        _queue_archive_sweep,
        trigger=IntervalTrigger(hours=6),
        id="queue_archive_sweep",
        misfire_grace_time=600,
        coalesce=True,
    )
    logger.info("queue_archive_sweep 등록 완료 (6시간 주기) — _queue.json 비대화 방지")

    if args.test:
        logger.info("=== 테스트 모드 시작: 1시간 주기 ===")
        scheduler.add_job(
            lambda: run_report(get_test_slot(), test_mode=True),
            trigger="interval",
            hours=1,
            id="test_hourly",
            misfire_grace_time=600,
            next_run_time=datetime.now(),
        )
    else:
        logger.info("=== 정규 스케줄 시작: 06/07/09/12/15/18/21/22/23시 (10슬롯) ===")
        # [2026-06-07 GM 확정] 10슬롯 개편 — 08시는 ceo_morning_pipeline(별도 Task Scheduler) 담당
        # [2026-06-08 GM] 23시 슬롯 복원 → 10슬롯. PC 종료 22:30→23:30 변경으로 23:00 발송 가능.
        #   동시에 22시는 취침안내+종료인사 통합(별도 22:25 종료인사 예약작업 제거).
        schedule_map = {
            "06": (6, 0),
            "07s": (7, 5),   # 직원 공유용 카드 — 07시 어제항로 직후 5분
            "07": (7, 0),
            "09": (9, 0),
            "12": (12, 0),
            "15": (15, 0),
            "18": (18, 0),
            "21": (21, 0),
            "22": (22, 0),
            "23": (23, 0),
        }
        for slot, (hour, minute) in schedule_map.items():
            scheduler.add_job(
                run_report,
                trigger=CronTrigger(hour=hour, minute=minute, timezone="Asia/Seoul"),
                args=[slot, False],
                id=f"report_{slot}",
                misfire_grace_time=600,
                coalesce=True,
            )
            logger.info(f"  등록: {slot}시 정각 (misfire_grace_time=600s)")

        # ── 지원부 점검 미완 자동 독려 (시우 2026-06-18) ─────────────────────
        #   nudge_pm=17:00(오후조)·nudge_close=22:00(마감조 — 23시 요약 전 1시간 여유).
        #   미완일 때만 핵심멤버방 발송·하루 회차당 1회. 빌더 None이면 침묵.
        nudge_map = {
            "nudge_pm": (17, 0, "pm"),
            "nudge_close": (22, 0, "close"),
        }
        for slot, (hour, minute, shift) in nudge_map.items():
            scheduler.add_job(
                run_nudge,
                trigger=CronTrigger(hour=hour, minute=minute, timezone="Asia/Seoul"),
                args=[shift],
                id=f"report_{slot}",
                misfire_grace_time=600,
                coalesce=True,
            )
            logger.info(f"  등록: {slot} {hour:02d}:{minute:02d} 지원부 점검 미완 독려")

    logger.info(f"스케줄러 기동 완료. PID={os.getpid()}")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("스케줄러 정상 종료 (KeyboardInterrupt)")
    finally:
        # 종료 시 PID 락 파일 제거 (v1.3 중복 방지)
        try:
            _PID_FILE.unlink(missing_ok=True)
            logger.info("PID 락 파일 제거 완료")
        except Exception:
            pass


if __name__ == "__main__":
    main()
