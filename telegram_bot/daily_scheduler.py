"""
웰페리온 일일 자동 보고 스케줄러 v1.2
-------------------------------
정규 스케줄 (6개): 06 / 09 / 12 / 15 / 18 / 21시 정각 텔레그램 자동 보고
테스트 모드: python daily_scheduler.py --test  →  1시간 주기 실행

스케줄 설계:
  06시 — 하루 시작 다짐·좋은 문구 (Notion 정기 보고 문구 DB, 06시 시간대)
  09시 — 전날 업무 전체 정리 (Notion 전 DB 어제자 변경 집계)
  12시 — 관심 분야 트렌드 정리 (Phase 2 플레이스홀더)
  15시 — 현재 업무 진행현황 C-Level별 (기획DB·결과물DB 필터링)
  18시 — 퇴근·가족·건강 좋은 문구 (Notion 정기 보고 문구 DB, 18시 시간대)
  21시 — 하루 핵심 요약 Lv1 MVP (Claude CLI + Notion 오늘자 변동 종합 요약)

운영 원칙:
- 기존 워처 3종 (archive_result_watcher·planning_to_archive_watcher·permission_watcher) 유지
- Notion API 호출 실패 시 Claude 연동 없이 자동화 실패 경보만 송신
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


# ── status/*: C-Level별 현재 업무 진행현황 (15시용, 노션 DB 폐기 대체) ────────
# 미완료로 간주하는 상태값 (DONE/완료/폐기 외 전부 진행/대기로 집계)
_OPEN_STATUSES = {"PENDING", "IN_PROGRESS", "ON_HOLD", "진행중", "대기", "보류", "진행예정"}


def _load_queue_open() -> list[dict]:
    """_queue.json 에서 미완료(status != DONE) 항목 반환."""
    if not QUEUE_FILE.exists():
        return []
    try:
        data = json.loads(QUEUE_FILE.read_text(encoding="utf-8"))
        return [x for x in data if str(x.get("status", "")).upper() != "DONE"]
    except Exception as e:
        logger.warning(f"_queue.json 읽기 실패: {e}")
        return []


def fetch_current_progress() -> str:
    """
    status/_queue.json (대기 큐) + 각 C-Level status JSON의 active_tasks 중
    미완료 항목을 C-Level별로 집계. SSOT = GitHub status/*.json.
    """
    # C-Level별 미완료 카운트 + 제목 수집
    per_clevel: dict[str, list[str]] = {}

    # 1) 대기 큐 (status != DONE)
    for item in _load_queue_open():
        clevel = str(item.get("clevel", "?")).upper()
        title = str(item.get("title", "(제목없음)")).split("\n")[0][:60]
        status = item.get("status", "")
        per_clevel.setdefault(clevel, []).append(f"[{status}] {title}")

    # 2) 각 C-Level active_tasks (status not in 완료군)
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
            if st.upper() == "DONE" or st in ("완료", "폐기"):
                continue
            if st and st.upper() not in {s.upper() for s in _OPEN_STATUSES}:
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
    """가이드허브 HTML에서 내일 할 일 시드 목록을 반환한다.

    반환: (내일_날짜_문자열 'YYYY-MM-DD', 시드_제목_리스트)
    - status='진행중' + startDate == 내일 인 시드만 포함
    - 파일 없거나 파싱 실패 시 ('', []) 반환
    """
    import re

    tomorrow = (datetime.now() + timedelta(days=1)).date()
    tomorrow_str = tomorrow.strftime("%Y-%m-%d")

    if not GUIDE_HUB_PATH.exists():
        logger.warning(f"가이드허브 파일 없음: {GUIDE_HUB_PATH}")
        return tomorrow_str, []

    try:
        text = GUIDE_HUB_PATH.read_text(encoding="utf-8")
    except Exception as e:
        logger.warning(f"가이드허브 읽기 실패: {e}")
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

    # 내일 할 일 (가이드허브 SSOT)
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
            lines.append("🌅 내일 할 일")
            lines.append("  (등록된 시드 없음 — 가이드허브 등록 필요)")
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


def _build_06_body() -> str:
    """06시 — 하루 시작 아침당부·문구 + 매일 고정 운동 5종목 체크리스트 (v1.5)"""
    quote = fetch_random_quote("06시")
    if quote:
        quote_line = f'\n\n> "{quote}"\n'
    else:
        quote_line = "\n\n(추후 데이터 연결 필요 — 문구 DB 등록 후 활성화)\n"

    now = datetime.now()
    weekday_kor = _WEEKDAY_KOR[now.weekday()]
    today_str = now.strftime("%Y-%m-%d")

    workout_lines = ["\n🏋️ 오늘 운동 점검"]
    for name, unit in DAILY_WORKOUT_ITEMS:
        workout_lines.append(f"  • {name}  ___{unit}  ☐")

    return (
        f"[웰페리온] 06시 하루 시작\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"{today_str} ({weekday_kor})\n"
        f"오늘도 좋은 하루 되십시오."
        f"{quote_line}"
        + "\n".join(workout_lines)
        + "\n\n_본 메시지는 자동 발송입니다._"
    )


def _build_09_body() -> str:
    """09시 — 전날 업무 전체 정리"""
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    summary = fetch_yesterday_summary()
    return (
        f"[웰페리온] 09시 전날 업무 정리\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"기준일: {yesterday}\n\n"
        f"{summary}\n\n"
        f"_본 메시지는 자동 발송입니다._"
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


def _compile_zone_summary(rows: list[dict]) -> str:
    """Google Sheets 행 데이터 → 구역별 완료율 + 이슈 + 주차."""
    zones: dict[str, dict] = {}
    issues: list[str] = []
    parking: list[str] = []

    for r in rows:
        zone = r.get("zone", "기타")
        checked = r.get("checked", False)
        issue = r.get("issue", "")
        name = r.get("name", "")

        if zone not in zones:
            zones[zone] = {"total": 0, "done": 0}
        zones[zone]["total"] += 1
        if checked:
            zones[zone]["done"] += 1
        if issue:
            issues.append(f"  - {name}: {issue}")
        if "주차" in name:
            mark = "V" if checked else "_"
            parking.append(f"  [{mark}] {name}")

    labels = {"남성구역": "남성구역", "여성구역": "여성구역", "공용구역": "공용구역"}
    lines: list[str] = []
    for z, c in zones.items():
        label = labels.get(z, z)
        rate = int(c["done"] / c["total"] * 100) if c["total"] > 0 else 0
        lines.append(f"  {label}: {rate}% ({c['done']}/{c['total']})")

    result = ["[시설·지원 점검 현황]"] + lines

    if parking:
        result += ["", "[주차 관리]"] + parking

    if issues:
        result += ["", "[이슈 발생]"] + issues[:5]
        if len(issues) > 5:
            result.append(f"  ... 외 {len(issues) - 5}건")

    return "\n".join(result)


def _build_12_body() -> str:
    """12시 — 시설·지원·주차 점검 현황 (Google Sheets 단일 소스, 노션 폐기)"""
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    weekday_kor = _WEEKDAY_KOR[now.weekday()]

    sections: list[str] = []

    sheets_data = _fetch_checklist_status_sheets(today)
    if sheets_data and sheets_data.get("rows"):
        sections.append(_compile_zone_summary(sheets_data["rows"]))

    if not sections:
        sections.append(
            "(점검 데이터 미연결)\n"
            "  .env CHECKLIST_API_URL 설정 후 활성화"
        )

    body = "\n\n".join(sections)

    return (
        f"[웰페리온] 12시 시설·지원·주차 현황\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"{today} ({weekday_kor}) 12:00 기준\n\n"
        f"{body}\n\n"
        f"_본 메시지는 자동 발송입니다._"
    )


def _build_15_body() -> str:
    """15시 — C-Level별 현재 업무 진행현황"""
    progress = fetch_current_progress()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    return (
        f"[웰페리온] 15시 업무 진행현황\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"기준: {now_str}\n\n"
        f"{progress}\n\n"
        f"_본 메시지는 자동 발송입니다._"
    )


def _build_18_body() -> str:
    """18시 — 퇴근당부·가족·건강 + 오늘 운동 부위 점검 안내 (v1.5)"""
    quote = fetch_random_quote("18시")
    if quote:
        quote_line = f'\n\n> "{quote}"\n'
    else:
        quote_line = "\n\n(추후 데이터 연결 필요 — 문구 DB 등록 후 활성화)\n"

    now = datetime.now()
    weekday_kor = _WEEKDAY_KOR[now.weekday()]
    today_str = now.strftime("%Y-%m-%d")

    return (
        f"[웰페리온] 18시 퇴근 인사\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"{today_str} ({weekday_kor})\n"
        f"오늘 하루도 수고 많으셨습니다."
        f"{quote_line}"
        f"\n🌙 오늘 운동 점검 — 매일 고정 5종목\n"
        f"  • 했다면 좋은 마무리, 못 했다면 내일은 챙겨보자.\n"
        f"  • 7일 중 5일이면 충분하다 — 꾸준함이 곧 루틴이다.\n"
        f"\n_본 메시지는 자동 발송입니다._"
    )


def _build_21_body() -> str:
    """21시 — 하루 핵심 요약 (가독성 개선판)"""
    now = datetime.now()
    today_str = now.strftime("%Y-%m-%d")
    weekday_kor = _WEEKDAY_KOR[now.weekday()]
    summary = fetch_daily_summary_lv1()
    return (
        f"🌙 [웰페리온] 21시 하루 마감\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"📅 {today_str} ({weekday_kor})\n\n"
        f"{summary}\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"_자동 발송 · 1단계 요약_"
    )


SLOT_BUILDERS = {
    "06": _build_06_body,
    "09": _build_09_body,
    "12": _build_12_body,
    "15": _build_15_body,
    "18": _build_18_body,
    "21": _build_21_body,
}


# ── 핵심 보고 실행 함수 ───────────────────────────────────────────────────────
def run_report(slot: str, test_mode: bool = False) -> None:
    """
    slot: "06" | "09" | "12" | "15" | "18" | "21"
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
    if h < 9:
        return "06"
    elif h < 12:
        return "09"
    elif h < 15:
        return "12"
    elif h < 18:
        return "15"
    elif h < 21:
        return "18"
    else:
        return "21"


# ── 수동 즉시 테스트 헬퍼 (--manual-test 옵션) ───────────────────────────────
def run_manual_test(slot: str) -> None:
    """특정 슬롯 즉시 1회 발송 (개발·검증용)."""
    logger.info(f"=== 수동 테스트 발송: {slot}시 슬롯 ===")
    run_report(slot, test_mode=True)
    logger.info("=== 수동 테스트 완료 ===")


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
    #   planning_to_archive_watcher.py)은 디스크 보존(가역적). 참조: docs/노션_가이드허브_리뉴얼_계획.md.

    # ── 업무자동화 DB 자동 실행 Watcher (5분 주기) — CTO v1.0 ───────────────
    try:
        from auto_task_watcher import check_and_run_auto_tasks as _auto_task_check
        scheduler.add_job(
            _auto_task_check,
            trigger=IntervalTrigger(minutes=5),
            id="auto_task_watcher",
            misfire_grace_time=600,
            coalesce=True,
            next_run_time=datetime.now(),
        )
        logger.info("auto_task_watcher 등록 완료 (5분 주기) — CTO v1.0")
    except ImportError as e:
        logger.error(f"auto_task_watcher 임포트 실패 — 감지기 미등록: {e}")

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
    #   디스크 보존(가역적). 참조: docs/노션_가이드허브_리뉴얼_계획.md.

    # ── C-Level 상태변경 텔레그램 자동발송 (1분 주기) — CTO v1.0 ─────────────
    try:
        from status_change_watcher import check_status_changes as _status_check
        scheduler.add_job(
            _status_check,
            trigger=IntervalTrigger(minutes=1),
            id="status_change_watcher",
            misfire_grace_time=120,
            coalesce=True,
            next_run_time=datetime.now(),
        )
        logger.info("status_change_watcher 등록 완료 (1분 주기) — CTO v1.0")
    except ImportError as e:
        logger.error(f"status_change_watcher 임포트 실패 — 감지기 미등록: {e}")

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
        logger.info("=== 정규 스케줄 시작: 06 / 09 / 12 / 15 / 18시 (21시 비활성) ===")
        # 정기 슬롯 스케줄
        # [2026-05-30 CTO 비활성] 21시 고정 마감 보고 슬롯 제거 — 세션종료(off)
        #   마감 루틴(ceo_evening_wrap.py, 5b58f9b)으로 단일화(GM 결정 "합쳐줘").
        #   06·09·12·15·18시 정기 보고는 그대로 유지. _build_21_body 함수·
        #   SLOT_BUILDERS["21"]는 보존(가역적 — '21' 키만 schedule_map에서 제외).
        #   --manual-test 21 수동 발송은 여전히 가능.
        schedule_map = {
            "06": (6, 0),
            "09": (9, 0),
            "12": (12, 0),
            "15": (15, 0),
            "18": (18, 0),
            # "21": (21, 0),  # 비활성 — 세션종료 마감 루틴으로 단일화 (위 주석 참조)
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
