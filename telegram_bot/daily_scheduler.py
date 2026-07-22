"""
웰페리온 일일 자동 보고 스케줄러 v2.1
-------------------------------
정규 스케줄: 06/12/18/21/23시 텔레그램 자동 보고 (GM 알림 홍수 축소 · 2026-07-18 GM 승인)
  · GM DM: 06(개인)·18(개인)·21(마감)·23(마감점검 — 이상시만 조건부 발송)
  · 12시는 점검관리방(실무진) 전용 — GM DM 아님
  · 점검 알림 통합(GM 2026-07-18 추가 확정): 오전점검(12시)·마감점검 개인DM(23시)은
    킬스위치 CHECK_MORNING_1200_ENABLED/CHECK_2300_GM_DM_ENABLED=False 로 발송만 OFF
    (22:30 점검관리방 다이제스트·23:00 카카오 4부서 요약은 무변경 유지). 계산/원장 적재는 보존.
  · 07(어제결산)·09(매출/진행)·15(중간정리)·22(취침) GM DM 슬롯은 08:00 통합브리프로 흡수·폐지
테스트 모드: python daily_scheduler.py --test  →  1시간 주기 실행
※ 08시(오늘의 항로 통합브리프)는 ceo_morning_pipeline.py (별도 Task Scheduler) 담당 —
   어제완료·매출1줄·북극성top·직원카드를 흡수(2026-07-18). 여기서 중복 발송 없음

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
from collections import Counter
import html
import json
import logging
import os
import random
import re
import subprocess
import sys
import time
import unicodedata
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
    from tg_outbound_log import log_outbound, pace
except Exception:
    def log_outbound(*a, **k):
        pass
    def pace(*a, **k):
        return None

try:  # 저신호 무음 플래그(best-effort) — 임포트 실패해도 발신 무영향(False 폴백)
    from notify_prefs import muted
except Exception:
    def muted(kind: str) -> bool:
        return False

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

# 점검 미완료 반복 감지기 (scripts/check_incomplete_detector.py) — GM 2026-07-15.
#   import 실패해도 발신 무영향(무동작 폴백 — 원장 적재·제안 생략).
try:
    import os as _os3, sys as _sys3
    _scr3 = _os3.path.abspath(_os3.path.join(_os3.path.dirname(_os3.path.abspath(__file__)), "..", "scripts"))
    if _scr3 not in _sys3.path:
        _sys3.path.insert(0, _scr3)
    import check_incomplete_detector as _cid
    _CID_OK = True
except Exception:
    _CID_OK = False
    _cid = None  # type: ignore[assignment]

# 운영 다이제스트 공용 수집층 (scripts/collectors/ops_shared.py) — GAS URL 상수 3종
# (FUNNEL_EXEC_URL·VOC_EXEC_URL·SSOT_API_URL)·재시도 GET 래퍼·UTC→KST 변환·업무완료
# 상태셋. scripts/ops_daily_digest.py(아침)와의 중복 정의를 여기로 수렴한다
# (2026-07-21 순수 리팩터 — 값·동작 무변경). import 실패 시 원본과 완전히 동일한
# 인라인 정의로 폴백(이 파일은 상주 봇이라 기동 실패를 절대 허용하지 않는다).
try:
    import os as _os4, sys as _sys4
    _scr4 = _os4.path.abspath(_os4.path.join(_os4.path.dirname(_os4.path.abspath(__file__)), "..", "scripts"))
    if _scr4 not in _sys4.path:
        _sys4.path.insert(0, _scr4)
    from collectors.ops_shared import (
        FUNNEL_EXEC_URL,
        VOC_EXEC_URL,
        SSOT_API_URL,
        TODO_DONE_STATUSES as _TODO_DONE_STATUSES,
        gas_get as _gas_get_shared,
        utc_iso_to_kst_date as _utc_iso_to_kst_date,
    )

    def _gas_get(
        url: str,
        params: dict | None = None,
        *,
        timeout: int = 40,
        attempts: int = 3,
        label: str = "GAS",
    ) -> requests.Response | None:
        """GAS(script.google.com) GET 재시도 래퍼 — ops_shared.gas_get에 logger.warning을
        log_fn으로 바인딩해 기존 실패 경보 동작을 그대로 보존."""
        return _gas_get_shared(url, params, timeout=timeout, attempts=attempts, label=label, log_fn=logger.warning)
except Exception:
    FUNNEL_EXEC_URL = (
        "https://script.google.com/macros/s/"
        "AKfycbykgMyFc-g_KG7x3HoKStKBwerKhYYfmbqNeFqCL5O1b_4-1nng4wEiKhkNJtfB4BWo/exec"
    )
    VOC_EXEC_URL = (
        "https://script.google.com/macros/s/"
        "AKfycbwk2XS1FND9V2xtXlWgsXzgA5p0FG7jVm6YKD74JK_ME_ZvHsNUUfGE5A_8p0X8VcF3gQ/exec"
    )
    SSOT_API_URL = "https://script.google.com/macros/s/AKfycbxDwFkrxK1YIaEoSNcuw2MiHiZQ-7o5N6311ytksSyeEd86ZFOhLknOWqQgNArQvZ-7/exec"
    _TODO_DONE_STATUSES = {"완료", "폐기", "DONE", "완료됨"}

    def _gas_get(
        url: str,
        params: dict | None = None,
        *,
        timeout: int = 40,
        attempts: int = 3,
        label: str = "GAS",
    ) -> requests.Response | None:
        for attempt in range(1, attempts + 1):
            try:
                resp = requests.get(url, params=params, timeout=timeout)
                if resp.status_code == 200:
                    return resp
                logger.warning(f"{label} HTTP {resp.status_code} (시도 {attempt}/{attempts})")
            except Exception as e:
                logger.warning(f"{label} 조회 실패 (시도 {attempt}/{attempts}): {e}")
        return None

    def _utc_iso_to_kst_date(iso_str: str) -> str:
        from datetime import timezone as _tz
        try:
            s = str(iso_str).rstrip("Z").replace("T", " ")
            dt_utc = datetime.fromisoformat(s).replace(tzinfo=_tz.utc)
            return (dt_utc + timedelta(hours=9)).strftime("%Y-%m-%d")
        except Exception:
            return ""

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
# 점검 미완료 누적 원장 (지원부 v1) — 하루 마감(23시) 최종 미완료 적재·반복 감지 소스. GM 2026-07-15.
CHECK_INCOMPLETE_LEDGER = STATUS_DIR / "check_incomplete_ledger.json"
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

# 업무현황 SSOT API (G1 할일, 09·15시 공용) — 정의는 collectors.ops_shared(위에서 import).

# ── 점검 알림 통합 킬스위치 (GM 2026-07-18) ────────────────────────────────────
#   가역·발송만 게이트(계산/원장 적재 등 부작용은 항상 보존). True로 되돌리면 즉시 부활.
CHECK_MORNING_1200_ENABLED = False   # GM 2026-07-18: 오전 점검(12시) 알림 없앰. True로 되돌리면 부활
CHECK_2300_GM_DM_ENABLED = False     # GM 2026-07-18: 마감점검 개인DM 중복 제거(점검관리방·카톡으로 수신). True로 부활


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
def send_telegram(chat_id: int, text: str, parse_mode: str = "MarkdownV2") -> bool:
    """HTTP POST. 재시도 3회 지수 백오프. ok:true 검증. 연속 실패 시 fallback."""
    url = f"{TELEGRAM_API}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode}
    for attempt in range(1, 4):
        try:
            pace()
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
                    pace()
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


# ── 자동봇 커밋 노이즈 필터 (07시 결산용) ──────────────────────────────────────
# erp_status_publisher.py 가 30분 주기로 생성하는 chore(erp) 봇 커밋을 제외한다.
_NOISE_COMMIT_RE = re.compile(
    r"시스템 현황 자동 발행|erp_status\.json",
    re.IGNORECASE,
)

# ── conventional-commit prefix → 한글 태그 변환 (07시 결산 표시용) ─────────────
_CC_KOR_MAP: dict[str, str] = {
    "feat": "기능", "fix": "수정", "chore": "정리",
    "docs": "문서", "refactor": "구조개선", "style": "스타일",
    "test": "테스트", "perf": "성능", "ci": "CI",
    "build": "빌드", "revert": "되돌림",
}
_CC_HUMANIZE_RE = re.compile(
    r"^(feat|fix|chore|refactor|style|test|docs|perf|ci|build|revert)"
    r"(?:\([^)]*\))?!?:\s*",
    re.IGNORECASE,
)


def _humanize_commit(msg: str) -> str:
    """conventional-commit prefix 를 한글 태그로 변환.
    예: feat(auth): 로그인 개선  →  [기능] 로그인 개선
    prefix 없는 메시지는 원문 그대로 반환."""
    m = _CC_HUMANIZE_RE.match(msg)
    if not m:
        return msg
    label = _CC_KOR_MAP.get(m.group(1).lower(), m.group(1))
    body = msg[m.end():]
    return f"[{label}] {body}"


# ── 봇 자동기록성 배 제목 필터 (07시 업무완료 집계 제외) ─────────────────────────
# "auto(", "auto-log", "검수 승인 건 발행", "자동기록" 등은 사람/AI 실작업이 아닌 봇 로그.
_AUTO_TASK_RE = re.compile(
    r"auto\(|auto-log|검수 승인 건 발행|자동기록|입항완료 자동",
    re.IGNORECASE,
)

# ── 배 제목에서 닉네임 추출 ([시포], [웰리] 등) ──────────────────────────────────
_NICK_RE = re.compile(r"^\[([가-힣A-Za-z0-9]{2,6})\]")


# ── GAS(script.google.com) 콜 공용 재시도 헬퍼 (2026-07-03 시토) ────────────────
# GAS는 콜드스타트 시 15s를 넘겨 응답하는 경우가 있어 단발 timeout=15로는
# 조용히 빈칸/실패가 났다 (09시 매출칸 누락·12시 "Read timed out" 재발 사고).
# _fetch_cfo_finance_block에 적용한 timeout=40 + 3회 재시도 패턴을 공용 헬퍼로 일반화.
# 정의는 collectors.ops_shared(위에서 logger.warning 바인딩 래퍼로 import).


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
    resp = _gas_get(SSOT_API_URL, params={"action": "todo_list"}, label="_fetch_yesterday_done_todos")
    if resp is None:
        return []
    try:
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


def _fetch_yesterday_queue_done() -> list[str]:
    """
    status/_queue.json 에서 어제 완료된 배 제목 목록 반환.
    processed_at(우선) 또는 enqueued_at 이 어제 날짜인 DONE/완료 항목.
    실패 시 빈 리스트.
    """
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    queue_path = REPO_ROOT / "status" / "_queue.json"
    try:
        with open(queue_path, encoding="utf-8") as _f:
            items = json.load(_f)
    except Exception as e:
        logger.warning(f"_fetch_yesterday_queue_done 예외: {e}")
        return []
    result = []
    for x in items:
        if x.get("status") not in ("DONE", "완료", "done"):
            continue
        date_val = str(x.get("processed_at") or x.get("enqueued_at") or "")
        if not date_val.startswith(yesterday):
            continue
        title = str(x.get("title") or "").strip()
        if title:
            result.append(title[:60])
    return result


def _fetch_open_todo_cards_for_tomorrow() -> list[dict]:
    """
    미완료(진행중·보류·대기) 항목 중 내일 항로점 브릿지 대상.
    21시 '내일 항로점' 섹션용. 실패 시 빈 리스트.
    """
    resp = _gas_get(SSOT_API_URL, params={"action": "todo_list"}, label="_fetch_open_todo_cards_for_tomorrow")
    if resp is None:
        return []
    try:
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
# _TODO_DONE_STATUSES 정의는 collectors.ops_shared(위에서 import).


def fetch_gm_todos(only_in_progress: bool = False) -> list[str] | None:
    """
    업무현황 SSOT API에서 GM(김남욱) 담당 미완료 항목 제목 리스트 반환.
    - 담당자 필드에 '김남욱' 포함 AND 상태가 완료·폐기·DONE 아님
    - only_in_progress=True 면 상태에 '진행' 포함 건만(보류·대기 제외) — 15시 진행 체크용
    - 실패 시 None 반환
    """
    resp = _gas_get(SSOT_API_URL, params={"action": "todo_list"}, label="fetch_gm_todos")
    if resp is None:
        return None
    try:
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
    resp = _gas_get(SSOT_API_URL, params={"action": "todo_list"}, label="fetch_gm_todo_cards")
    if resp is None:
        return None
    try:
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
        lines.append(f"[{_clevel_display(clevel)}] {len(items)}건")
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

# C-Level 표시 라벨: 공식 AI 직함 + 닉네임 (GM 2026-07-07 지시 — 보고 라벨 통일)
_CLEVEL_DISPLAY: dict[str, str] = {
    "CEO": "AI CEO-웰리",
    "CFO": "AI CFO-시뽀",
    "CHRO": "AI CHRO-시로",
    "CMO": "AI CMO-시모",
    "COO": "AI COO-시우",
    "CPO": "AI CPO-시포",
    "CTO": "AI CTO-시토",
}


def _clevel_display(clevel: str) -> str:
    """C-Level 코드(CEO 등) → 보고 표시 라벨(AI CEO-웰리). 미매핑은 원본 유지."""
    return _CLEVEL_DISPLAY.get(clevel, clevel)


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
    resp = _gas_get(SSOT_API_URL, params={"action": "gm_hangro"}, label="gm_hangro")
    if resp is None:
        return None
    try:
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
            lines.append(f"[{_clevel_display(clevel)}] {len(clevel_items)}건")
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

# ── 18시 저녁 명언 (개인 톤·정적 리스트·지어내기 아님) — GM 2026-07-09 ──────────
# 18시는 운영 데이터 0의 개인 메시지(퇴근+저녁루틴+명언). 날짜 결정론 선택(day % len)
# 으로 매일 하나 고정 노출 — 랜덤/외부호출 없음. 카피는 GM이 자유롭게 다듬을 수 있음.
EVENING_QUOTES = [
    "잘 쉰 하루가 내일의 힘이 됩니다.",
    "오늘 못 다한 일은 내일의 몫으로 남겨두세요.",
    "저녁의 여유가 하루의 무게를 덜어줍니다.",
    "천천히 걸어도 멈추지만 않으면 도착합니다.",
    "가장 좋은 재충전은 완전히 손을 놓는 것입니다.",
    "하루를 잘 마무리하는 사람이 내일을 잘 시작합니다.",
    "지금 이 순간, 나에게 수고했다고 말해주세요.",
    "작은 성취도 오늘의 나를 앞으로 데려갑니다.",
    "몸이 쉬어야 마음도 회복됩니다.",
    "오늘의 마침표가 내일의 시작을 가볍게 합니다.",
]

# ── 통일 포맷 헬퍼 (2026-06-11 GM 지시) ────────────────────────────────────────
# 9슬롯(06/07/09/12/15/18/21/22/23) 출력 포맷을 단일 템플릿으로 통일.
#   · 공통 헤더:  🕐 HH시 · 분류 — 짧은목적  + 짧은날짜줄 + 구분선
#   · 분류 라벨:  개인 / 회사 / 개인&회사  (GM 한눈 파악 핵심)
#   · 공통 구분선·푸터 단일화 (중복 제거)
# ※ 07s(직원 공유 카드)는 GM 2026-06-29 지시로 07:00 본문에 합본(분리발송 폐지).
# ※ 시간·내용 substance·로직은 불변. 시각 구조(헤더/구분/푸터)만 통일.
# ※ 헤더 압축형 GM 2026-06-29 — 대괄호 제거·날짜 MM-DD 단축·시계 이모지 추가.
_DIVIDER = "━━━━━━━━━━━━━━━━"
_AUTO_FOOTER = "_본 메시지는 자동 발송입니다._"
_CLOCK_FACES = ['🕛','🕐','🕑','🕒','🕓','🕔','🕕','🕖','🕗','🕘','🕙','🕚']


def _unified_header(hour: str, category: str, purpose: str) -> str:
    """슬롯 공통 헤더(압축형 GM 2026-06-29) — '🕐 HH시 · 분류 — 짧은목적' + 짧은날짜 + 구분선.

    hour:     "06" 등 2자리 시
    category: "개인" | "회사" | "개인&회사"
    purpose:  한 줄 목적 (예: "하루시작·운동")
    """
    now = datetime.now()
    date_str = now.strftime("%m-%d")
    weekday_kor = _WEEKDAY_KOR[now.weekday()]
    try:
        clock = _CLOCK_FACES[int(hour) % 12]
    except Exception:
        clock = '🕐'
    return (
        f"{clock} {hour}시 · {category} — {purpose}\n"
        f"{date_str}({weekday_kor})\n"
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
        f"{_unified_header('06', '개인', '하루시작·운동')}\n"
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
        f"회원 한 사람의 건강한 하루를 완성한다\n\n"
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
    """07시 — 어제 결산 (업무 완료 중심 · 코드 저장 보조 지표) [개인&회사]"""
    now = datetime.now()
    yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%d")
    yesterday_wd = _WEEKDAY_KOR[(now - timedelta(days=1)).weekday()]
    today_str = now.strftime("%Y-%m-%d")
    weekday_kor = _WEEKDAY_KOR[now.weekday()]

    # ① 코드 저장 수 (보조 지표) ─ 노이즈 필터 후 카운트만 (목록 나열 없음)
    # max_lines=150: 노이즈(~48건) + 실제 커밋이 하루 100건 이내라 충분
    commits_raw = _git_log_between(f"{yesterday} 00:00", f"{today_str} 00:00", max_lines=150)
    commits = [c for c in commits_raw if not _NOISE_COMMIT_RE.search(c)]
    n_noise = len(commits_raw) - len(commits)
    n_commits = len(commits)

    # ② 업무 완료 (중심 지표) ─ GAS todo_list + _queue.json DONE 머지
    done_gas = _fetch_yesterday_done_todos()
    done_queue = _fetch_yesterday_queue_done()
    # 제목 기준 중복 제거 (GAS 우선)
    seen_titles: set[str] = set(done_gas)
    for t in done_queue:
        if t not in seen_titles:
            done_gas.append(t)
            seen_titles.add(t)
    # 봇 자동기록성 ADHOC 제외 → 실제 사람/AI 작업만
    real_todos = [t for t in done_gas if not _AUTO_TASK_RE.search(t)]
    n_todos = len(real_todos)

    # 닉네임별 건수 요약 한 줄
    nick_count: Counter[str] = Counter()
    for t in real_todos:
        m = _NICK_RE.match(t)
        nick_count[m.group(1) if m else "기타"] += 1
    nick_parts = [f"{k} {v}건" for k, v in nick_count.most_common(6)]
    if len(nick_count) > 6:
        nick_parts.append("...")
    nick_summary = " · ".join(nick_parts) if nick_parts else "없음"

    # 대표 제목 최대 5건
    todo_lines = []
    for t in real_todos[:5]:
        ship = classify_ship({"업무명": t})
        line = render_ship_line(t, "", ship)
        todo_lines.append(f"  {line}")
    if n_todos > 5:
        todo_lines.append(f"  ... 외 {n_todos - 5}건")
    todo_block = "\n".join(todo_lines) if todo_lines else "  (어제 완료 항목 없음)"

    # 코드 저장 — 한 줄 숫자 요약만 (목록 나열 금지, 20줄 이내 준수)
    noise_note = f" (자동발행 {n_noise}회 별도)" if n_noise > 0 else ""
    code_line = f"🛠 코드 저장 {n_commits}회{noise_note}"

    return (
        f"{_unified_header('07', '개인&회사', '어제 결산')}\n"
        f"🏁 {yesterday} ({yesterday_wd}) 결산\n\n"
        f"✅ 업무 완료  {n_todos}건\n"
        f"  {nick_summary}\n"
        f"{todo_block}\n\n"
        f"{code_line}\n\n"
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


_FINANCE_CACHE = Path(__file__).parent / ".finance_cache.txt"


def _write_finance_cache(text: str) -> None:
    try:
        _FINANCE_CACHE.write_text(text, encoding="utf-8")
    except Exception as e:
        logger.warning(f"매출 캐시 저장 실패: {e}")


def _read_finance_cache() -> str:
    try:
        if _FINANCE_CACHE.exists():
            return _FINANCE_CACHE.read_text(encoding="utf-8")
    except Exception as e:
        logger.warning(f"매출 캐시 읽기 실패: {e}")
    return ""


def _fetch_cfo_finance_block() -> str:
    """
    매출·지출 현황 조회 — ERP home과 동일 소스(SSOT API home_kpi) 사용.
    home(wellperion_guide)이 'action=home_kpi'의 sales/expense를 그대로 표시하므로
    9시 보고도 같은 엔드포인트를 fetch해 home과 수치를 일치시킨다 (2026-06-12 시토).
    CFO_SHEET_URL이 .env에 별도 등록돼 있으면 그것을 우선(override)한다.
    """
    src_url = CFO_SHEET_URL or SSOT_API_URL
    action = "summary" if CFO_SHEET_URL else "home_kpi"
    # GAS(script.google.com)는 콜드스타트 시 느려 단발 15s로는 조용히 빈칸이 나갔다
    # (2026-07-03 09시 보고 매출칸 누락 사고). timeout 상향 + 재시도로 견고화.
    data = None
    last_err = None
    for attempt in range(3):
        try:
            resp = requests.get(src_url, params={"action": action}, timeout=40)
            if resp.status_code != 200:
                last_err = f"HTTP {resp.status_code}"
                continue
            data = resp.json()
            break
        except Exception as e:
            last_err = str(e)[:80]
            logger.warning(f"매출·지출(home_kpi) 조회 실패 (시도 {attempt+1}/3): {e}")
    if data is None:
        # 3회 실패 → 마지막 정상값 캐시로 폴백(빈칸 대신 직전 수치 노출)
        cached = _read_finance_cache()
        if cached:
            return f"{cached}\n  ⚠️ 실시간 조회 지연 — 직전 정상값 표시 (원인: {last_err})"
        return f"💰 매출·지출 현황\n  조회 오류: {last_err}"

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
    result = f"💰 매출·지출 현황 (ERP home 동일 소스)\n{table_str}{today_line}"
    _write_finance_cache(result)  # 다음 조회 실패 시 폴백용 마지막 정상값
    return result


def _build_09_body() -> str:
    """09시 — 업무·매출·지출 현황 [회사] (기존 오늘할일 → 08시 중복 폐기·대체)"""
    # ① 업무현황: C-Level별 진행 (_queue.json + status/*.json)
    progress = fetch_current_progress()

    # ② 매출·지출 (CFO 시트)
    finance_block = _fetch_cfo_finance_block()

    return (
        f"{_unified_header('09', '회사', '업무·매출·지출')}\n"
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
    resp = _gas_get(f"{CHECKLIST_API_URL}?date={today}&zone=all", label="12시 Sheets API")
    if resp is None:
        return None
    try:
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


def _fetch_facility_today() -> dict | None:
    """시설부 오늘자 점검 진행 — monthly_report&dept=facility의 dailySeries에서 오늘 행 추출.
    시설부는 지원부와 달리 weekly엔 값이 없고 monthly_report 경로에 실데이터가 있다(입력률·이상 구조).
    GAS 일시 지연에도 '-'로 새지 않게 _gas_get 재시도(3회·40초)를 사용한다.
    반환: {date,total,done,pct,sessionCount,outOfRangeCount} 또는 None."""
    today = datetime.now().strftime("%Y-%m-%d")
    resp = _gas_get(
        f"{SUPPORT_CHECK_API_URL}?action=monthly_report&dept=facility&date={today}&_pv={int(time.time())}",
        label="12시 시설부",
    )
    if resp is None:
        return None
    try:
        d = resp.json()
        if d.get("ok"):
            for row in d.get("dailySeries", []):
                if row.get("date") == today:
                    return row
    except Exception as e:
        logger.warning(f"12시 시설부 응답 파싱 실패: {e}")
    return None


def _fetch_facility_board(today: str) -> dict:
    """시설부 오늘 board 한 번 호출 — 작업사항(fc_work) 원문 + 제출 회차수(submissions len)
    + 기준이탈 조치/해결(fc_ooc_action, GM 승인 2026-07-13 시우).
    회차는 monthly의 sessionCount(라운드종류=1 고정)가 아니라 실제 제출 건수(페이지 'N회 완료'와 일치)."""
    out = {"work": None, "sessions": 0, "ooc_action": None}
    try:
        resp = _gas_get(f"{SUPPORT_CHECK_API_URL}?action=board&key=FACILITY_CHECK_{today}", label="12시 시설부board")
        if resp is None:
            return out
        store = (resp.json().get("board", {}) or {}).get("store", {}) or {}
        daily = store.get("daily", {}) or {}
        w = daily.get("fc_work")
        if isinstance(w, str) and w.strip():
            w = w.strip()
            out["work"] = w[:400] + "…" if len(w) > 400 else w
        oa = daily.get("fc_ooc_action")
        if isinstance(oa, str) and oa.strip():
            oa = oa.strip()
            out["ooc_action"] = oa[:200] + "…" if len(oa) > 200 else oa
        subs = store.get("submissions")
        if isinstance(subs, list):
            out["sessions"] = len(subs)
    except Exception:
        pass
    return out


def _is_closed_day(d=None) -> bool:
    """휴관일 = 매월 2·4주 일요일 + 1/1 (프론트 getDayInfo와 동일 규칙)."""
    import math
    if d is None:
        d = datetime.now()
    wk = math.ceil(d.day / 7)
    if d.weekday() == 6 and wk in (2, 4):  # 일요일(파이썬 Sun=6) & 2·4주
        return True
    if d.strftime("%m-%d") == "01-01":
        return True
    return False


def _support_monthly_rate() -> str | None:
    """published 당월 누적 지원부 완료율 병기 문자열. 없으면 None."""
    try:
        import json, os
        p = os.path.join(os.path.dirname(__file__), "..", "status", "kpi_values.json")
        with open(p, encoding="utf-8") as f:
            kv = json.load(f)
        # 중첩 dict 어디에 있든 재귀로 키 탐색
        def find(o, key):
            if isinstance(o, dict):
                if key in o: return o[key]
                for v in o.values():
                    r = find(v, key)
                    if r is not None: return r
            elif isinstance(o, list):
                for v in o:
                    r = find(v, key)
                    if r is not None: return r
            return None
        rate = find(kv, "지원부_점검완료율")
        basis = find(kv, "지원부_점검완료율_기준") or ""
        if isinstance(rate, (int, float)) and not isinstance(rate, bool):
            b = f" ({basis.split('(')[0]})" if basis else ""
            return f"📊 당월 누적 지원부 완료율: {round(rate*100)}%{b}"
    except Exception:
        pass
    return None


def _build_checklist_block(slot_label: str, html_link: bool = False, now: datetime | None = None) -> str:
    """
    12시/23시(폴백) 공용 — 체크리스트 대시보드 박스표 블록 생성.
    slot_label: "12:00" | "23:00"
    html_link: True면 parse_mode=HTML 메시지용 — 본문을 html.escape해 &/</> 파싱 오류를 방지한다.
               False(기존 MarkdownV2 경로)는 동작 변경 없음.
    now: 검증용 날짜 주입(기본 datetime.now()). 오늘자 조회·휴관일 판정에 사용.

    대시보드 링크 정책(GM 2026-07-15): 의미 낮은 '🔗 대시보드: 링크' 전면 삭제(텔레그램 점검 알림 미노출).
    그 자리에 반복 미완료 제안(있을 때만·지원부 원장 기반 과거 패턴)만 12·23시 공용 삽입.
    """
    now = now or datetime.now()
    today = now.strftime("%Y-%m-%d")
    weekday_kor = _WEEKDAY_KOR[now.weekday()]
    day_kor = ["월", "화", "수", "목", "금", "토", "일"][now.weekday()]

    # 반복 미완료 제안 라인(콜드스타트·0건이면 [] → 줄 생략, 정직) — 12·23시 공용.
    suggest_lines = _cid.suggestion_lines_for_today(CHECK_INCOMPLETE_LEDGER, today) if _CID_OK else []

    if _is_closed_day(now):
        body = f"🛠 시설·지원 점검 현황 — {slot_label} ({day_kor})\n🚫 오늘은 휴관일 — 점검 없음"
        if html_link:
            return html.escape(body, quote=False)
        return body

    # 지원부·시설부 라이브 소스로 조회 — 옛 CHECKLIST_API_URL은 오늘 빈 응답(rows=0)이라 폐기(2026-07-08 GM):
    #   지원부=today_live&dept=support(실데이터·완료율) · 시설부=monthly_report 오늘행(입력률+이상). 두 지표 체계는 다름(억지 통일 안 함).
    #   주차관리부는 SSOT상 독립·점검 제외 부서(weekly가 구조상 전부 0) → 12시 표에서 제외.
    support_live = _fetch_support_today_live(today)
    # 시설부=monthly_report 한 번 호출로 입력률 + 기준이탈 항목·값·기준까지 확보(12시 상세 노출).
    monthly = _fetch_facility_monthly(today)
    facility_today = _facility_today_row(monthly, today)
    # board 한 번 호출로 작업사항 + 실제 제출 회차수 확보(회차=페이지 'N회 완료'와 일치)
    fac_board = _fetch_facility_board(today) if facility_today is not None else {"work": None, "sessions": 0, "ooc_action": None}

    def _support_cell() -> str:
        if not support_live:
            return "-"
        t = support_live.get("total", 0)
        if not t:
            return "미가동"
        dn = support_live.get("done", 0)
        return f"{dn}/{t}({round(dn / t * 100)}%)"

    def _facility_cell() -> str:  # 12시·23시 공용 — 이벤트 중심(회차·이상 유무, GM 2026-07-13)
        if facility_today is None:
            return "-"
        f_total = facility_today.get("total", 0)
        if not f_total:
            return "미가동"
        sc = fac_board.get("sessions") or facility_today.get("sessionCount") or 0
        ooc = facility_today.get("outOfRangeCount", 0)
        return f"{sc}회·이상 {ooc}건" if ooc else f"{sc}회·이상 없음"

    ooc_cnt = (facility_today or {}).get("outOfRangeCount", 0)
    mrate = _support_monthly_rate()

    if html_link:
        # 12시 — 점검 보고형: 시설부=이벤트 중심(회차·이상 유무·이상 내용·작업사항, GM 2026-07-13 % 제거),
        #   지원부=완료율. 시토 918 기준이탈 상세는 '이상 내용'으로 보존, 순수 입력률% 블록은 제거.
        # 지원부 = 오전·저녁 회차 분리(12시엔 오전만 완료가 정상 · 저녁은 아직 0, GM 2026-07-13)
        sl = support_live or {}
        amT, amD = sl.get("amTotal", 0), sl.get("am", 0)
        evT = sl.get("pmTotal", 0) + sl.get("closeTotal", 0) + sl.get("nightTotal", 0)
        evD = sl.get("pm", 0) + sl.get("close", 0) + sl.get("night", 0)
        lines = [f"🔧 시설부  {_facility_cell()}"]
        if sl.get("total"):
            lines.append(f"📋 지원부 오전  {amD}/{amT}" + (f" ({round(amD / amT * 100)}%)" if amT else ""))
            lines.append(f"🌙 지원부 저녁  {evD}/{evT}" + (f" ({round(evD / evT * 100)}%)" if evT else " (예정)"))
        else:
            lines.append(f"📋 지원부  {_support_cell()}")
        if mrate:
            lines.append(mrate)
        status = "\n".join(lines)

        # 지원부 오전 미이행 항목 노출 — 실무진이 '당일 점검 대상 아님' 판별해 매뉴얼 수정 요청용.
        # (GM 2026-07-14: 이행률<100%는 대개 당일 비대상 항목이 분모에 남은 것 · 매뉴얼 정리 실무 진행 중 · 알림에서만 노출)
        # 12시엔 오전 회차만 마감 대상(저녁 pm/close는 아직 예정이라 미이행이 정상 → 노출 제외).
        ubs = sl.get("uncheckedByShift") or {}
        am_un = ubs.get("am") or {}
        am_items = sorted(set((am_un.get("m") or []) + (am_un.get("f") or [])))
        unchecked_block = ""
        if am_items:
            shown = ", ".join(am_items[:12]) + (f" 외 {len(am_items) - 12}건" if len(am_items) > 12 else "")
            unchecked_block = (
                f"📌 지원부 오전 미이행 {len(am_items)}건 — 당일 점검 대상이 아니면 매뉴얼 수정 요청 주세요\n  · {shown}"
            )

        # 이상 내용(기준이탈 상세) — 시토 918 유용분 보존(GM '어떤 문제였는지')
        if ooc_cnt:
            issue = _build_facility_ooc_detail(monthly, today)  # "⚠️ 시설부 기준이탈 N건\n  · 항목: 값 (기준 lo~hi)"
            ooc_action = fac_board.get("ooc_action")  # 실무진이 조치칸에 남긴 해결내용(GM 승인 2026-07-13 시우)
            if ooc_action:
                issue = f"{issue}\n  [조치] {ooc_action}"
        else:
            issue = "✅ 이상 없음 — 시설 측정 전 항목 정상"

        # 작업사항 원문(이상 내용·해결) — GM 승인 포맷 A
        fac_work = fac_board.get("work")
        work_block = f"─ 시설부 작업사항 ─\n{fac_work}" if fac_work else ""

        # 반복 미완료 제안(있을 때만) — 매일 무의미 링크 대체(GM 2026-07-15).
        suggest_block = "\n".join(suggest_lines) if suggest_lines else ""
        parts = (
            [status]
            + ([unchecked_block] if unchecked_block else [])
            + [issue]
            + ([work_block] if work_block else [])
            + ([suggest_block] if suggest_block else [])
        )
        body_safe = html.escape("\n\n".join(parts), quote=False)
        return body_safe

    # 23시 폴백(MarkdownV2 안전) — 기존 박스표 형식 유지. 링크만 시설부(이탈 부서)로 교정.
    #   시설부는 GM 지시(2026-07-13)로 %(입력률) 대신 회차·이상유무 중심 + 작업사항 원문 노출.
    table_str = "\n".join(_count_table([
        ("지원부 체크", _support_cell()),
        ("시설부 점검", _facility_cell()),
    ]))
    fac_work = fac_board.get("work")
    work_block = f"\n\n─ 시설부 작업사항 ─\n{fac_work}" if fac_work else ""
    mrate_block = f"\n{mrate}" if mrate else ""
    suggest_block = ("\n\n" + "\n".join(suggest_lines)) if suggest_lines else ""
    body_plain = (
        f"🛠 시설·지원 점검 현황 — {slot_label} ({day_kor})\n"
        f"   체크리스트 진행 상황\n"
        f"{table_str}"
        f"{mrate_block}"
        f"{work_block}"
        f"{suggest_block}"
    )
    return body_plain


def _build_12_body() -> str:
    """12시 — 시설·지원 체크리스트 진행현황 박스표.
    이 메시지는 parse_mode=HTML로 발송(run_report에서 slot=="12" 분기).
    _AUTO_FOOTER는 MarkdownV2 이탤릭 문법(_..._)이라 HTML 모드에선 그대로 나가버려
    이 메시지 전용으로 <i> 태그 버전을 사용한다."""
    checklist_block = _build_checklist_block("12:00", html_link=True)

    # 제목 = 'MM-DD(요일) 오전 점검 현황보고' (GM 2026-07-13: '12시·회사' 표기 제거)
    now = datetime.now()
    hdr = f"🕛 {now.strftime('%m-%d')}({_WEEKDAY_KOR[now.weekday()]}) 오전 점검 현황보고\n{_DIVIDER}"
    return (
        f"{hdr}\n"
        f"{checklist_block}\n\n"
        f"<i>본 메시지는 자동 발송입니다.</i>"
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
        f"{_unified_header('15', '개인&회사', '오늘 1차 정리')}\n"
        f"👤 GM 진행 중 ({n_gm}건)\n"
        f"{gm_section}\n\n"
        f"{_DIVIDER}\n"
        f"🏢 C-Level 진행현황\n"
        f"{progress}\n\n"
        f"{_AUTO_FOOTER}"
    )


def _build_18_body() -> str:
    """18시 — 퇴근 인사 + 저녁 루틴 + 명언 [개인] (운영 데이터 0·GM 2026-07-09)

    [GM 2026-07-09] 18시를 개인 메시지로 축소 — 점검 현황·오늘 성과(커밋)·대시보드
    링크 전부 제거. 시설·지원·주차 마감 현황은 23시로 일원화. 여기는 퇴근+저녁루틴+
    명언만. 명언은 EVENING_QUOTES 정적 리스트에서 날짜 결정론(day % len) 선택.
    """
    now = datetime.now()
    quote = EVENING_QUOTES[now.day % len(EVENING_QUOTES)]

    return (
        f"{_unified_header('18', '개인', '퇴근·저녁')}\n"
        f"🌙 오늘도 수고하셨습니다.\n"
        f"🌆 저녁 루틴 — 오늘 마무리하고 재충전하세요.\n"
        f'\n> "{quote}"\n\n'
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
    done_today: list[str] = []
    resp = _gas_get(SSOT_API_URL, params={"action": "todo_list"}, label="21시 오늘완료")
    if resp is not None:
        try:
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
        f"{_unified_header('21', '개인&회사', '오늘 마감·내일 정립')}\n"
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
    """22시 — 취침·전자기기off + 마무리(종료) 인사 + 명언 [개인] (북극성은 08시로 일원화·GM 2026-06-29)

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
        f"{_unified_header('22', '개인', '전자기기 OFF·취침')}\n"
        f"오늘 하루도 고생 많으셨습니다, GM님.\n"
        f"📵 전자기기 off — 수면 루틴 시작\n"
        f"{quote_line}"
        f"{_AUTO_FOOTER}"
    )


# ── 23시 마감 점검 차트 상세형 헬퍼 (today_live 지원부 회차×성별) ──────────────
# [GM 2026-07-09] 23시 마감 대시보드 링크 제거 → 기준이탈은 내용으로 정리(_build_facility_ooc_detail).


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

    # [GM 2026-07-19] 분모(total)>0 회차만 렌더 — 주말은 서버가 pmTotal=0을 주므로
    # 오후조 유령행(0/0)이 자동 제외됨(주말 2회차·평일 3회차 정합). 홈 parseGenderKpi와 동일 규칙.
    _all_rows = [("오전조", "am"), ("오후조", "pm"), ("마감조", "close")]
    rows = [(lb, k) for lb, k in _all_rows if (d.get(k + "Total", 0) or 0) > 0]

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


def _fetch_facility_monthly(today: str) -> dict | None:
    """시설부 monthly_report 전체 응답(dailySeries + outOfRange 상세). 실패 시 None.
    시설부는 weekly엔 값이 없고 monthly_report에 실데이터(입력률+기준이탈 항목·값)가 있다."""
    resp = _gas_get(
        f"{SUPPORT_CHECK_API_URL}?action=monthly_report&dept=facility&date={today}&_pv={int(time.time())}",
        label="23시 시설부 monthly",
    )
    if resp is None:
        return None
    try:
        d = resp.json()
        return d if d.get("ok") else None
    except Exception as e:
        logger.warning(f"23시 시설부 monthly 파싱 실패: {e}")
        return None


def _facility_today_row(monthly: dict | None, today: str) -> dict | None:
    """monthly_report dailySeries에서 오늘 행({total,done,pct,outOfRangeCount}) 추출."""
    if not monthly:
        return None
    for row in monthly.get("dailySeries", []):
        if row.get("date") == today:
            return row
    return None


def _build_facility_ooc_detail(monthly: dict | None, today: str) -> str:
    """오늘자 시설부 기준이탈(outOfRange) 항목·값·기준 나열 블록. 없으면 '' (줄 생략).
    데이터 지어내기 없음 — monthly_report outOfRange.list의 오늘 date만 사용."""
    if not monthly:
        return ""
    lst = [
        x for x in ((monthly.get("outOfRange") or {}).get("list") or [])
        if str(x.get("date", "")) == today
    ]
    if not lst:
        return ""
    lines = []
    for x in lst[:6]:
        name = str(x.get("name", "")).strip() or "(항목미상)"
        val, lo, hi = x.get("value", ""), x.get("min", ""), x.get("max", "")
        lines.append(f"  · {name}: {val} (기준 {lo}~{hi})")
    extra = len(lst) - 6
    if extra > 0:
        lines.append(f"  ... 외 {extra}건")
    return f"⚠️ 시설부 기준이탈 {len(lst)}건\n" + "\n".join(lines)


def _dept_status_lines(facility_row: dict | None, facility_sessions: int = 0) -> str:
    """4부서 상태 줄 (지원=별도 차트, 나머지). 주차=weekly(점검 제외 부서라 통상 미가동).

    시설부(2026-07-18 시토, INC 07-16 관련 정합 수리): monthly_report dailySeries의 오늘 행(total)은
    신뢰불가로 확인됨(07-15 stale 값이 재노출된 사례) — '활동 있었는지' 판정은 board(FACILITY_CHECK_{date}
    .store.submissions 실 제출건수, kakao_daily_check_share.py::build_facility_lines와 동일 정본 소스)로
    한다. facility_row(monthly)는 여전히 done/total/pct·기준이탈 건수 "장식"에만 쓰되, total=0인데
    board엔 실제 세션이 있으면(stale 케이스) 세션 수 기준으로 활동 표시(미가동 오탐 차단)."""
    parking = _fetch_dept_weekly("parking")

    def dept_line(icon: str, name: str, data: dict | None) -> str:
        if data is None:
            return f"{icon} {name}: -"
        total = data.get("total", 0)
        if total == 0:
            return f"{icon} {name}: 미가동(자체점검 준비 중)"
        done = data.get("done", 0)
        pct = data.get("pct", round(done / total * 100) if total else 0)
        ooc = data.get("outOfRangeCount", 0)
        return f"{icon} {name}: {done}/{total}({pct}%)" + (f" ⚠{ooc}" if ooc else "")

    facility_total = (facility_row or {}).get("total", 0)
    if facility_total:
        fac_line = dept_line("🏗", "시설부", facility_row)
    elif facility_sessions:
        # monthly_report는 미가동(total=0)이지만 board엔 실제 제출 기록 있음 → stale 판정 오탐, 정본(board)으로 표시.
        ooc = (facility_row or {}).get("outOfRangeCount", 0)
        fac_line = f"🏗 시설부: {facility_sessions}회 점검" + (f" ⚠{ooc}" if ooc else "")
    else:
        fac_line = "🏗 시설부: 미가동(자체점검 준비 중)"

    return (
        f"{fac_line}\n"
        f"{dept_line('🅿', '주차', parking)}\n"
        f"🏢 운영부: 점검 체계 없음(규정·매뉴얼 운영)"
    )


def _compute_23_body_and_anomaly() -> tuple[str, bool]:
    """23시 마감 점검 본문 + 이상여부(has_anomaly)를 함께 반환.

    이상 = 미완 회차(약점 pct<100) OR 시설부 기준이탈(ooc) OR 반복 미완료 제안 중 하나라도 존재.
    - live None(데이터 없음): (폴백본문, False) — 판정 불가라 GM DM 조건부 미발신(상세는 카톡 23시 담당).
    - 정상(전 회차 완료·이탈 0): (본문, False) → GM DM 미발신.
    - 이상 존재: (본문, True) → GM DM 발신.
    부작용(미완료 원장 적재)은 기존과 동일하게 유지 — 23시 1회 실행 전제.
    """
    today = datetime.now().strftime("%Y-%m-%d")
    live = _fetch_support_today_live(today)

    # 하루 마감(23시) 최종 미완료 원장 적재 — 라이브 실값만·같은 날 멱등(GM 2026-07-15).
    #   23시 블록 경로에서만 적재(12시엔 오전만 끝나 미완료가 정상). live None이면 데이터 없어 스킵(정직).
    if _CID_OK and live is not None:
        _cid.append_daily_from_live(
            CHECK_INCOMPLETE_LEDGER, today, live.get("uncheckedByShift") or {}
        )

    if live is None:
        # 폴백 — 기존 12/18 공용 블록 재사용. 판정 불가 → 이상 아님(조건부 미발신).
        checklist_block = _build_checklist_block("23:00")
        body = (
            f"{_unified_header('23', '회사', '마감 점검')}\n"
            f"{checklist_block}\n\n"
            f"{_AUTO_FOOTER}"
        )
        return body, False

    chart = _build_support_check_chart(live)
    weakspot = _build_support_weakspot(live)

    # 시설·주차 통합 현황 + 기준이탈 내용(대시보드 링크 대체) — monthly_report 1회 조회로 재사용
    facility_monthly = _fetch_facility_monthly(today)
    facility_row = _facility_today_row(facility_monthly, today)
    # 2026-07-18 시토(INC 07-16 관련 정합 수리): 시설부 활동 판정을 monthly_report(stale 이력 있음) 대신
    # board(정본·kakao_daily_check_share.py와 동일 소스)로 교정 — _dept_status_lines 참조.
    fac_board_23 = _fetch_facility_board(today)
    dept_lines = _dept_status_lines(facility_row, fac_board_23.get("sessions", 0))
    ooc_detail = _build_facility_ooc_detail(facility_monthly, today)
    ooc_block = f"\n\n{ooc_detail}" if ooc_detail else ""

    # 반복 미완료 제안(있을 때만) — 원장 기반 과거 패턴(방금 오늘분 적재 포함). 콜드스타트·0건이면 생략(정직).
    suggest_lines = _cid.suggestion_lines_for_today(CHECK_INCOMPLETE_LEDGER, today) if _CID_OK else []
    suggest_block = ("\n\n" + "\n".join(suggest_lines)) if suggest_lines else ""

    # 이상 판정 — 약점(미완회차)·기준이탈·반복제안 중 하나라도 있으면 True.
    #   weakspot: "✅ 짚을 점 없음…"=정상, "⚠️ 짚을 점: 진행 데이터 없음"=데이터부재(이상 아님),
    #   "⚠️ 짚을 점: … 독려 필요"=실제 미완(이상).
    weakspot_anomaly = weakspot.startswith("⚠️") and "진행 데이터 없음" not in weakspot
    has_anomaly = bool(weakspot_anomaly or ooc_detail or suggest_lines)

    body = (
        f"{_unified_header('23', '회사', '마감 점검')}\n"
        f"{chart}\n"
        f"{weakspot}\n\n"
        f"{dept_lines}"
        f"{ooc_block}"
        f"{suggest_block}\n\n"
        f"{_AUTO_FOOTER}"
    )
    return body, has_anomaly


def _build_23_body() -> str:
    """23시 — 마감 점검 현황 차트 상세형 [회사]. (--manual-test·폴백 미리보기용 · 본문만)

    today_live(지원부 회차×성별) 성공 시 차트+약점+4부서 상태.
    실패 시 기존 _build_checklist_block('23:00')로 폴백(빈 메시지/크래시 금지).
    ※ 정규 23시 발신은 run_report가 _compute_23_body_and_anomaly()로 조건부(이상시만) 처리.
    """
    body, _ = _compute_23_body_and_anomaly()
    return body


# ── 지원부 점검 미완 자동 독려 (오후17시·마감22시·미완시만·하루1회) — 시우 2026-06-18 ──
# 점검 관리 방(점검 독려 대상). 핵심멤버방 3분류 분리(시우 102, 2026-06-24): 점검 알림 → '점검 관리' 방.
# .env TELEGRAM_CHECK_CHAT_ID 사용. 폴백=점검관리방(-5136037543). [시토 2026-06-29] 폴백 리터럴 오타 수정(구: -5065206276 종합접수처 → 점검 독려가 엉뚱한 방 갈 위험 제거).
CHECK_NUDGE_CHAT_ID = int(ENV.get("TELEGRAM_CHECK_CHAT_ID") or -5136037543)

# ── 하루 일과 정리 알림 (매일 22:30) — 문의·점검·접수 3방 — GM 2026-06-29 ──────
DIGEST_INQUIRY_CHAT_ID   = int(ENV.get("TELEGRAM_INQUIRY_CHAT_ID")   or -5516675010)
DIGEST_CHECK_CHAT_ID     = int(ENV.get("TELEGRAM_CHECK_CHAT_ID")     or -5136037543)
DIGEST_RECEPTION_CHAT_ID = int(ENV.get("TELEGRAM_RECEPTION_CHAT_ID") or -5065206276)
# FUNNEL_EXEC_URL·VOC_EXEC_URL 정의는 collectors.ops_shared(위에서 import).


def _merged_unchecked_names(live: dict, shift: str) -> list[str]:
    """today_live 응답의 uncheckedByShift[shift] — m+f 미체크 항목명 병합.
    필드 없음/빈값 → 빈 리스트(호출부가 안전하게 줄 생략). GM go 2026-07-09, 배선: 지원팀 일일점검.js handleTodayLive."""
    bucket = (live.get("uncheckedByShift") or {}).get(shift) or {}
    names = list(bucket.get("m") or []) + list(bucket.get("f") or [])
    return [str(n).strip() for n in names if str(n or "").strip()]


def _support_sheet_activity_today(today: str) -> tuple[int, int]:
    """영속 시트(monthly_report·dailySeries) 기준 '오늘' 실완료 수·제출 세션 수. (sumDone, sessionCount).
    today_live(ScriptProperties 원장)가 실제 제출과 어긋나 0으로 비는 글리치를 판별하는 크로스체크용.
    조회 실패=(0,0)(가드 미발동=기존 동작 유지). 2026-07-16 시토(잘못된 미완 독려 방지)."""
    try:
        resp = requests.get(
            f"{SUPPORT_CHECK_API_URL}?action=monthly_report&dept=support&date={today}&_pv={int(time.time())}",
            timeout=20, allow_redirects=True,
        )
        if resp.status_code == 200:
            d = resp.json()
            if d.get("ok"):
                for row in (d.get("dailySeries") or []):
                    if isinstance(row, dict) and str(row.get("date")) == today:
                        return int(row.get("sumDone") or 0), int(row.get("sessionCount") or 0)
    except Exception as e:
        logger.warning(f"독려 글리치판별 monthly 조회 실패: {e}")
    return 0, 0


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

    # [2026-07-16 시토] today_live 글리치 가드 — today_live(ScriptProperties 원장)가 실제 제출과 어긋나 done=0으로
    #   비는 사례 확인(영속 시트엔 실데이터 존재: 예 55/108·제출3). 이때 "미완 0/N" 독려는 거짓 → '점검 했는데?' 혼란.
    #   회차 done==0인데 영속 시트(monthly)에 오늘 실완료·제출이 있으면 today_live 글리치로 보고 침묵(잘못된 독려 방지).
    #   근본(today_live 원장 정합)은 시우 점검 GAS 영역 — 별도. 여기선 거짓 독려만 안전 차단.
    if done == 0:
        _sheet_done, _sheet_sessions = _support_sheet_activity_today(today)
        if _sheet_done > 0 or _sheet_sessions > 0:
            logger.info(
                f"[독려:{shift}] today_live done=0 이나 영속시트 활동(완료 {_sheet_done}·제출 {_sheet_sessions}회) "
                f"→ today_live 글리치 판단, 거짓 미완 독려 침묵"
            )
            return None

    g = live.get("byGender", {})
    m = g.get("m", {})
    f = g.get("f", {})
    mT, m_done = m.get(shift + "Total", 0), m.get(shift, 0)
    fT, f_done = f.get(shift + "Total", 0), f.get(shift, 0)

    if shift == "pm":
        label, action = "오후조", "마감 전 점검 부탁드립니다"
    else:
        label, action = "마감조", "마감 점검 부탁드립니다"

    # 미체크 항목명(GM go 2026-07-09) — uncheckedByShift 없거나 빈 값이면 조용히 줄 생략(안전, 지어내기 금지).
    unchecked_names = _merged_unchecked_names(live, shift)
    unchecked_line = ""
    if unchecked_names:
        shown = unchecked_names[:8]
        extra = len(unchecked_names) - len(shown)
        tail = f" 외 {extra}" if extra > 0 else ""
        unchecked_line = f"\n미체크: {', '.join(shown)}{tail}"

    return (
        f"⚠️ [{label}] 지원부 점검 미완 — "
        f"남 {m_done}/{mT} · 여 {f_done}/{fT} (합 {done}/{total}). {action}."
        f"{unchecked_line}"
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


# ── 하루 일과 정리 빌더 3종 + 오케스트레이터 ─────────────────────────────────
# _utc_iso_to_kst_date 정의는 collectors.ops_shared(위에서 import).


def _inquiry_stage_of(raw: str) -> int:
    """진행상태 → 전환 단계 rank. .deploy-funnel/Survey.js `_stageOf_` 와 동일 규칙(SSOT 2026-06-15) 이식.
    0=이탈, 1=문의(신규/접수/빈칸), 2=응대, 3=예약, 4=방문, 5=가입."""
    s = str(raw or "").strip()
    if not s:
        return 1  # 빈칸 → 최소단계(①문의)
    if re.search(r"이탈|보류|포기|거절|취소|종료|loss", s, re.I):
        return 0
    if re.fullmatch(r"(suc|단기\s*suc)", s, re.I):
        return 5
    if re.search(r"가입|등록|전환|회원|완납|결제완|키오스크\s*완", s):
        return 5
    if re.search(r"(ot|상담)\s*완료", s, re.I):
        return 4
    if re.search(r"방문|내방|방문완료", s):
        return 4
    if re.search(r"예약|투어|상담", s):
        return 3
    if re.search(r"응대|연락|통화|문자|회신|컨택", s):
        return 2
    if re.search(r"신규|접수", s):
        return 1
    return 1  # 미인식 → ① 문의(안전 처리)


# 종목·유형 색상 도트(GM 확정 스킴, _sportColor와 동일) — 텔레그램 텍스트 색상 불가 → 원형 이모지. 2026-07-18 시토(GM).
# 2026-07-20 GM(결함3) — 영문 탭 별칭 추가(대소문자 무시 매칭, _split_sports 참고). 매칭은 대소문자 무시로
# 수행하므로 여기 표기 케이스는 가독성용일 뿐 실제 비교에는 영향 없음.
_DIGEST_SPORT_DOT = [
    ("아쿠아", "🔵"), ("수영", "🔵"), ("Swimming", "🔵"),
    ("P.T", "🔴"), ("PT", "🔴"), ("Personal Training", "🔴"),
    ("필라", "🟠"), ("Pilates", "🟠"),
    ("스쿼시", "🟩"), ("Squash", "🟩"),
    ("골프", "🟢"), ("Golf", "🟢"),
    ("트램폴린", "🟦"), ("체조", "🟦"), ("Gymnastics", "🟦"),
    ("멤버십", "🟡"), ("Membership", "🟡"),
    ("뮤지컬", "⚫"), ("Musical", "⚫"),
    ("발레", "🟣"), ("바레", "🟣"), ("루프", "🟣"), ("Ballet", "🟣"), ("Barre", "🟣"),
]


def _digest_dot(s: str) -> str:
    k = (s or "").strip().lower()
    for kw, dot in _DIGEST_SPORT_DOT:
        if kw.lower() in k:
            return dot + " "
    return ""


# 종목 정규명 — _DIGEST_SPORT_DOT 매칭 키워드 → 표시용 정식 명칭(예: '필라'→'필라테스', 'Swimming'→'수영').
# 2026-07-20 GM(수정1) — _split_sports() 전용, 색상 도트 매칭(_digest_dot)과는 별개 표시 이름 테이블.
# 결함4(2026-07-20): 발레·바레·루프 는 사내 정규명이 '루프메소드' 하나로 통일 — 3개 키워드 모두 흡수.
_DIGEST_SPORT_CANON = {
    "아쿠아": "아쿠아", "Swimming": "수영", "수영": "수영",
    "P.T": "P.T", "PT": "P.T", "Personal Training": "P.T",
    "필라": "필라테스", "Pilates": "필라테스",
    "스쿼시": "스쿼시", "Squash": "스쿼시",
    "골프": "골프", "Golf": "골프",
    "트램폴린": "트램폴린", "체조": "체조", "Gymnastics": "체조",
    "멤버십": "멤버십", "Membership": "멤버십",
    "뮤지컬": "뮤지컬", "Musical": "뮤지컬",
    "발레": "루프메소드", "바레": "루프메소드", "루프": "루프메소드",
    "Ballet": "루프메소드", "Barre": "루프메소드",
}


def _digest_paren_has_sport(text: str) -> bool:
    """괄호 안 내용에 _DIGEST_SPORT_DOT 키워드가 하나라도 있으면 True(대소문자 무시).
    결함4 — '웰니스 프로그램(바레, 발레)'처럼 괄호 안이 실제 종목 나열인 경우를 판별."""
    t = (text or "").lower()
    return any(kw.lower() in t for kw, _dot in _DIGEST_SPORT_DOT)


def _digest_top_level_split(text: str) -> list[str]:
    """콤마 등 구분자로 쪼개되 괄호 안의 구분자는 무시한다(깊이 추적) — 결함4/이전 라운드 수정4의
    후속: 예전엔 괄호를 먼저 통째로 지웠지만, 이번엔 괄호 안 내용을 종목 나열로 살릴 수도 있어야
    해서 괄호 깊이를 실제로 추적하는 파서로 교체."""
    parts: list[str] = []
    buf: list[str] = []
    depth = 0
    for ch in text:
        if ch in "([（":
            depth += 1
            buf.append(ch)
        elif ch in ")]）":
            depth = max(0, depth - 1)
            buf.append(ch)
        elif ch in ",·/|" and depth == 0:
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    parts.append("".join(buf))
    return parts


def _digest_expand_segment(seg: str) -> list[str]:
    """세그먼트 안 괄호 부연 하나를 처리(결함4). 괄호 안에 종목 키워드가 있으면 그 내용을
    (콤마 등으로 재분해해) 분해 대상으로 쓰고 바깥 라벨은 버린다(예: '웰니스 프로그램(바레, 발레)'
    → ['바레', ' 발레']). 키워드가 없으면 기존처럼 괄호+내용만 지우고 바깥 라벨을 남긴다
    (예: '뮤지컬 (Brad Little Star Academy)' → ['뮤지컬'])."""
    import re as _re

    m = _re.search(r"[\(（]([^()（）]*)[\)）]", seg)
    if m and _digest_paren_has_sport(m.group(1)):
        return _digest_top_level_split(m.group(1))
    return [_re.sub(r"\s*[\(（][^()（）]*[\)）]", "", seg)]


def _split_sports(s: str) -> list[str]:
    """한 사람이 여러 종목을 콤마 등으로 나열한 문자열을 종목별로 쪼갠다(GM 2026-07-20 수정2, 결함2~4 수리).
    구분자 = , · / | ('&'는 분리 안 함 — '체조 & 트램폴린'은 한 종목으로 유지·이후 정규화 단계에서
    '체조' 로 흡수).
    1) 업스트림에 HTML 엔티티가 섞여 있으면 먼저 풀어서 복구(html.unescape, 결함1).
    2) 괄호 깊이를 추적해 최상위 구분자로만 분리(괄호 안의 , / · 는 안 건드림).
    3) 세그먼트별 괄호 처리(_digest_expand_segment) — 종목 나열 괄호는 살리고, 부연 설명 괄호는 버림.
    4) 조각마다 WSC 접두어 제거 후 _DIGEST_SPORT_DOT 키워드 중 '문자열에서 가장 앞서 나온'(인덱스
       최소, 동률이면 더 긴 키워드) 키워드의 정규명으로 통일(대소문자 무시) — 매칭이 여러 개여도
       원문을 살리지 않는다(결함2: '체조 & 트램폴린' → '체조'). 매칭이 아예 없는 조각만 정리된
       원문을 그대로 유지.
    중복 제거·순서 보존·빈값 제외."""
    import re as _re

    raw = html.unescape(str(s or "")).strip()
    if not raw:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for seg in _digest_top_level_split(raw):
        for piece in _digest_expand_segment(seg):
            p = piece.strip()
            if not p:
                continue
            p = _re.sub(r"^WSC\s*", "", p, flags=_re.IGNORECASE).strip()
            if not p:
                continue
            p_lower = p.lower()
            matches = []
            for kw, _dot in _DIGEST_SPORT_DOT:
                idx = p_lower.find(kw.lower())
                if idx != -1:
                    matches.append((idx, -len(kw), kw))
            if matches:
                matches.sort()
                name = _DIGEST_SPORT_CANON.get(matches[0][2], matches[0][2])
            else:
                name = p
            if name not in seen:
                seen.add(name)
                out.append(name)
    return out


def _digest_fetch_list(action: str, **params) -> list:
    """funnel-v2 목록 조회(멤버십·강습). 실패 시 예외 전파(호출부에서 폴백)."""
    r = requests.get(FUNNEL_EXEC_URL, params=dict(action=action, **params), timeout=40, allow_redirects=True)
    r.raise_for_status()
    d = r.json()
    return d.get("data", []) if d.get("ok") else []


# QA/배포검증 더미 행 판정 — .deploy-funnel/Survey.js:787-792 _isTestInquiryRow_() 와 동일 규칙
# (정본, 두 곳이 어긋나면 안 됨 — GM 2026-07-20). 새 규칙 발명 금지, 그대로 이식.
_DIGEST_TEST_ROW_RE = re.compile(r"테스트|자동검증|E2E|�|\[자동")


def _is_test_row(r: dict) -> bool:
    """전화번호가 010-0000 더미로 시작하거나, name+phone+content/memo 텍스트에 테스트성 마커
    (테스트/자동검증/E2E/깨진문자�/[자동)가 섞이면 QA/배포검증용 더미 행으로 판정."""
    phone = str(r.get("phone", "") or "")
    digits = re.sub(r"\D", "", phone)
    if digits.startswith("0100000"):
        return True
    name = str(r.get("name", "") or "")
    content = " ".join([
        str(r.get("inquiryContent", "") or ""),
        str(r.get("memo", "") or ""),
        str(r.get("content", "") or ""),
    ])
    blob = f"{name} {phone} {content}"
    return bool(_DIGEST_TEST_ROW_RE.search(blob))


def _filter_test_rows(rows: list) -> tuple:
    """_is_test_row() 로 QA/배포검증 더미 행을 걸러낸다. 반환 = (필터된 rows, 제외 건수).
    오늘 문의 목록·미처리 현황 집계 양쪽이 같은 필터링 결과를 공유하도록 호출부(딱 한 곳,
    _build_digest_inquiry의 GAS 응답 수신 직후)에서만 호출한다 — GM 2026-07-20."""
    kept: list = []
    removed = 0
    for r in rows:
        if _is_test_row(r):
            removed += 1
        else:
            kept.append(r)
    return kept, removed


# 회원관리 미처리 현황 판정 상태값 — cpo_report.py _LOSS_STATUSES/_SUCCESS_STATUSES 정본과 동일.
# 2026-07-20 GM: 담당자 미배정 집계에서 이미 종결(LOSS/성공)된 건은 정상(담당자 없어도 OK)이라 제외.
_DIGEST_LOSS_STATUSES = {"LOSS", "환불", "양도LOSS"}
_DIGEST_SUCCESS_STATUSES = {"SUC", "단기SUC"}


def _digest_unprocessed_counts(rows: list, field: str, month_prefix: str) -> tuple:
    """rows 전체(누적, 필터 없음) + 이번 달(month_prefix="YYYY-MM") 두 축을 동시에 집계 —
    종목별 {종목: [당월미정, 당월미배정, 누적미정, 누적미배정]} + 카테고리 전체 합계 4종 반환
    (GM 2026-07-20 — 금일 축 폐기, 당월/누적 두 축으로 교체. 담당자 미배정은 '오늘' 단위가
    의미 없다는 GM 지적).
    미처리 = 진행상태 미정(status 공백) 또는 담당자 미배정(owner 공백 & 비종결) 하나라도 해당하는 건.
    한 사람이 여러 종목이면 _split_sports() 로 쪼개 종목마다 각각 1건씩 계상."""
    counts: dict = {}
    cat = [0, 0, 0, 0]  # [당월미정, 당월미배정, 누적미정, 누적미배정]
    for r in rows:
        ts = str(r.get("timestamp", "") or "")
        status = str(r.get("status", "") or "").strip()
        owner = str(r.get("owner", "") or "").strip()
        undecided = not status
        is_terminal = status in _DIGEST_LOSS_STATUSES or status in _DIGEST_SUCCESS_STATUSES
        unassigned = (not owner) and not is_terminal
        if not undecided and not unassigned:
            continue
        is_month = ts.startswith(month_prefix)
        species = _split_sports(str(r.get(field, "") or "")) or ["미분류"]
        for sp in species:
            c = counts.setdefault(sp, [0, 0, 0, 0])
            if undecided:
                c[2] += 1
                cat[2] += 1
                if is_month:
                    c[0] += 1
                    cat[0] += 1
            if unassigned:
                c[3] += 1
                cat[3] += 1
                if is_month:
                    c[1] += 1
                    cat[1] += 1
    return counts, cat


# ── 고정폭 표 렌더 유틸(GM 2026-07-20) — 한글/이모지 표시폭 기준 패딩. len() 정렬 금지(한글 어긋남) ──
def _disp_width(s: str) -> int:
    """문자열 표시폭 합산. 전각(동아시아 W/F)·이모지(≥U+1F300)=2, 결합문자/변이선택자=0, 그 외=1."""
    width = 0
    for ch in s:
        if unicodedata.combining(ch) != 0 or ch in ("️", "︎", "‍"):
            continue
        if unicodedata.east_asian_width(ch) in ("W", "F"):
            width += 2
        elif ord(ch) >= 0x1F300:
            width += 2
        else:
            width += 1
    return width


def _truncate_disp(s: str, width: int) -> str:
    """표시폭 width 를 넘으면 그 안에 맞춰 자르고 … 를 붙인다(… 자리 1칸 확보)."""
    if _disp_width(s) <= width:
        return s
    out: list[str] = []
    w = 0
    for ch in s:
        cw = _disp_width(ch)
        if w + cw > width - 1:
            break
        out.append(ch)
        w += cw
    return "".join(out) + "…"


def _pad_right(s: str, width: int) -> str:
    s = _truncate_disp(s, width)
    return s + (" " * max(0, width - _disp_width(s)))


def _pad_left(s: str, width: int) -> str:
    s = _truncate_disp(s, width)
    return (" " * max(0, width - _disp_width(s))) + s


# <pre> 위치 마커 — _build_digest_inquiry() 는 이 마커가 박힌 '로직 메시지'를 만들고,
# _digest_finalize_html/_digest_finalize_plain 이 채널별로 최종 페이로드를 뽑아낸다.
_PRE_OPEN = "\x01PRE_OPEN\x01"
_PRE_CLOSE = "\x01PRE_CLOSE\x01"

_DIGEST_TABLE_SPECIES_W = 14
_DIGEST_TABLE_NUM_W = 8

# team_sales 팀 키 → 다이제스트 정규 종목명(_DIGEST_SPORT_CANON 표기와 동일) 매핑.
# 정본 = .deploy-todo/업무&결재 현황.js:1332-1341 TEAM_LABEL_MAP — 새 규칙 발명 금지, 그대로 이식.
# '체조&트램'(key=gym) = 다이제스트의 '체조'와 같은 것(GM 2026-07-20 확인).
_TEAM_SALES_KEY_TO_CANON = {
    "pt": "P.T", "pilates": "필라테스", "swim": "수영", "squash": "스쿼시",
    "gym": "체조", "golf": "골프", "musical": "뮤지컬", "gxe": "GXE",
}

_digest_sport_rank_cache: dict = {}  # {"YYYY-MM-DD": [(종목, 누적매출), ...] | None} — 당일 1회 캐시


def _digest_sport_rank(today: str) -> list | None:
    """team_sales_h1(1~6월 합산, scripts/kpi_collector.py:127-130 _CFO_GAS = 이 파일의
    SSOT_API_URL과 동일 GAS) + team_sales(7월~당월, 개별 월 합산) 로 종목별 연중 누적매출
    내림차순 순위를 만든다(GM 2026-07-20 — 표 정렬을 매출 순위 고정으로 교체, 당월 단독이면
    월초에 순서가 요동쳐 '고정'이 안 됨). [(종목, 누적매출원), ...] 매출 내림차순 반환.
    프로세스 메모리에 당일 1회만 캐시(다이제스트는 하루 한 번이라 재조회 불필요).
    실패 시 예외를 던지지 않고 None 반환 — 호출부는 기존 당월 합 내림차순 정렬로 폴백한다."""
    if today in _digest_sport_rank_cache:
        return _digest_sport_rank_cache[today]

    result = None
    try:
        year = int(today[:4])
        cur_month = int(today[5:7])
        totals: dict = {}

        h1_resp = _gas_get(SSOT_API_URL, params={"action": "team_sales_h1", "year": year}, label="team_sales_h1")
        if h1_resp is None:
            raise RuntimeError("team_sales_h1 조회 실패(재시도 소진)")
        h1 = h1_resp.json()
        if not h1.get("ok"):
            raise RuntimeError(f"team_sales_h1 ok=false: {h1.get('error')}")
        for q in ("q1", "q2"):
            for key, v in (h1.get(q) or {}).items():
                actual = v.get("actual") if isinstance(v, dict) else None
                if actual is None:
                    continue
                canon = _TEAM_SALES_KEY_TO_CANON.get(key, key)
                totals[canon] = totals.get(canon, 0) + actual

        for m in range(7, cur_month + 1):
            resp = _gas_get(SSOT_API_URL, params={"action": "team_sales", "year": year, "month": m},
                             label=f"team_sales({m}월)")
            if resp is None:
                continue
            d = resp.json()
            if not d.get("ok"):
                continue
            for t in d.get("teams") or []:
                actual = t.get("actual")
                if actual is None:
                    continue
                canon = _TEAM_SALES_KEY_TO_CANON.get(t.get("key"), t.get("name"))
                totals[canon] = totals.get(canon, 0) + actual

        if not totals:
            raise RuntimeError("팀별 매출 합계가 비어있음(모든 월 조회 실패)")

        result = sorted(totals.items(), key=lambda kv: -kv[1])
    except Exception as e:
        logger.warning(f"[하루 일과 정리] 매출 순위(team_sales) 조회 실패 — 당월 합 내림차순으로 폴백: {e}")
        result = None

    _digest_sport_rank_cache[today] = result
    return result


def _digest_table_lines(counts: dict, cat: list, fixed_dot: str, rank: list | None = None,
                         cap: int | None = None) -> list[str]:
    """종목별 당월/누적 카운트를 고정폭 표 라인 리스트로 렌더(<pre> 안에 그대로 들어갈 내용,
    태그 없음). 색은 기존 종목 고유색(_digest_dot/fixed_dot) 그대로 — 심각도 색 아님.
    rank 가 있으면(매출 순위) 그 순서를 우선 적용하고, rank 에 없는 종목(매출 원장 자체가
    없는 루프메소드 등)은 뒤로 붙여 그들끼리 당월 합 내림차순(GM 2026-07-20). rank 가 없으면
    (폴백 또는 멤버십) 기존대로 당월 합 내림차순·동률 시 누적 합 내림차순.
    cap 을 주면 상한 줄 수 + '…외 N개 종목' 유지(멤버십 전용, 성인·유소년은 cap=None=무제한).
    마지막에 구분선 + 합계 행(표에 안 잡힌 잘린 종목까지 포함한 카테고리 전체 합계)."""
    sw, nw = _DIGEST_TABLE_SPECIES_W, _DIGEST_TABLE_NUM_W
    lines = [_pad_right("종목", sw) + " " + _pad_left("진행상태", nw) + "  " + _pad_left("담당자", nw)]

    if rank:
        rank_index = {name: i for i, (name, _amt) in enumerate(rank)}

        def _sort_key(kv):
            sp, (mu, ma, cu, ca) = kv
            idx = rank_index.get(sp)
            if idx is not None:
                return (0, idx)
            return (1, -(mu + ma), -(cu + ca))

        ordered = sorted(counts.items(), key=_sort_key)
    else:
        ordered = sorted(counts.items(), key=lambda kv: (-(kv[1][0] + kv[1][1]), -(kv[1][2] + kv[1][3])))

    shown = ordered[:cap] if cap else ordered
    for sp, (mu, ma, cu, ca) in shown:
        dot = fixed_dot or _digest_dot(sp)
        label = f"{dot}{sp}"
        lines.append(_pad_right(label, sw) + " " + _pad_left(f"{mu}/{cu}", nw) + "  " + _pad_left(f"{ma}/{ca}", nw))
    if cap:
        remaining = len(ordered) - len(shown)
        if remaining > 0:
            lines.append(f"…외 {remaining}개 종목")
    lines.append("─" * (sw + 1 + nw + 2 + nw))
    cmu, cma, ccu, cca = cat
    lines.append(_pad_left("합계", sw) + " " + _pad_left(f"{cmu}/{ccu}", nw) + "  " + _pad_left(f"{cma}/{cca}", nw))
    return lines


def _digest_unprocessed_section(title: str, rows: list, field: str, month_prefix: str,
                                 fixed_dot: str = "", rank: list | None = None,
                                 cap: int | None = None) -> str:
    """▸ {title} 카테고리 블록. 미처리 있으면 고정폭 표(<pre> 마커로 감쌈), 없으면 담백한 완료
    격려 1줄(표 없음). 카테고리 제목은 표 밖에 둔다(GM 2026-07-20 — 표 가시성 개선)."""
    head = f"▸ {title}"
    counts, cat = _digest_unprocessed_counts(rows, field, month_prefix)
    if not counts:
        return f"{head}\n✅ 진행상태·담당자 모두 정리 완료."
    table = _digest_table_lines(counts, cat, fixed_dot, rank=rank, cap=cap)
    return f"{head}\n{_PRE_OPEN}" + "\n".join(table) + _PRE_CLOSE


def _build_digest_member_unprocessed(mem: list, adult: list, youth: list, today: str) -> str:
    """🗂 회원관리 미처리 현황(종목별, 당월/누적, 고정폭 표) — 오늘 문의 목록 뒤·마케팅 섹션 앞에
    삽입(GM 2026-07-20 — 표 렌더로 가시성 개선. 색은 기존 종목 고유색 유지, 심각도 색 아님).
    성인강습·유소년강습은 매출 순위(_digest_sport_rank) 고정 순서를 공유(GM 지시) — 순위 조회
    실패 시 기존 당월 합 내림차순으로 폴백. 멤버십은 종목 개념이 달라 현행 그대로(순위·상한
    모두 무변경). 한 사람 다종목은 _split_sports() 로 종목별로 나눠 계상."""
    month_prefix = today[:7]  # "YYYY-MM"
    month_label = f"{today[:4]}년 {int(today[5:7])}월"
    title = "━━━━━━━━━━\n🗂 회원관리 미처리 현황"
    sport_rank = _digest_sport_rank(today)
    sections = [
        _digest_unprocessed_section("멤버십", mem, "program", month_prefix, fixed_dot="🟡 ", cap=8),
        _digest_unprocessed_section("성인강습", adult, "sport", month_prefix, rank=sport_rank),
        _digest_unprocessed_section("유소년강습", youth, "sport", month_prefix, rank=sport_rank),
    ]
    # 세 카테고리 전부 완료(표를 만든 카테고리가 하나도 없음)면 섹션 전체를 담백한 한 줄로
    # 대체(직전 라운드 로직 그대로 — GM 2026-07-20 유지 지시).
    if all(_PRE_OPEN not in s for s in sections):
        return f"{title}\n✅ 전 종목 진행상태·담당자 배정 완료. 미처리 0건입니다."
    return f"{title}\n{month_label} · 숫자 = 당월/누적\n\n" + "\n\n".join(sections)


def _digest_finalize_html(logical: str) -> str:
    """로직 메시지(<pre> 마커 포함, 아직 미이스케이프) → 텔레그램 parse_mode=HTML 페이로드.
    전체를 한 번에 html.escape() 해 이름·채널·종목명 등 어떤 동적 텍스트에도 빠짐없이 적용되게
    한 뒤, <pre> 마커만 실제 태그로 되돌린다(마커는 &/</> 를 포함하지 않아 escape 로 안 바뀜)."""
    escaped = html.escape(logical, quote=False)
    return escaped.replace(_PRE_OPEN, "<pre>").replace(_PRE_CLOSE, "</pre>")


def _digest_finalize_plain(logical: str) -> str:
    """로직 메시지 → 카카오톡 등 HTML 을 못 읽는 채널용 평문. 마커만 제거(이스케이프 없음 —
    실제 태그를 넣은 적이 없으므로 벗길 엔티티도 없다). 표의 공백 패딩 정렬은 그대로 남는다."""
    return logical.replace(_PRE_OPEN, "").replace(_PRE_CLOSE, "")


def _append_digest_marketing_section(msg: str) -> str:
    """문의 정리 메시지 맨 끝에 📣 마케팅 정리 섹션을 붙인다(GM 2026-07-20, 21시 단독발송 통합·하루 카드 하나).
    실패해도 문의 정리 본문은 그대로 나가야 한다 — best-effort try/except.
    _build_digest_inquiry() 의 모든 return 경로가 이 함수를 거쳐 나가므로, HTML 엔티티 유출 방지
    (결함1) 최종 안전망도 여기서 한 번에 건다: send_telegram() 기본 parse_mode=MarkdownV2 라
    &amp;/&lt;/&gt; 이스케이프는 불필요·유해 — 남아있으면 무조건 풀어서(html.unescape) 발송한다."""
    try:
        import weekly_marketing_feedback as _wmf  # scripts/ 는 상단에서 sys.path 삽입됨

        card_text = _wmf.build_daily_card_text()
        card_lines = card_text.split("\n")
        body = "\n".join(card_lines[1:]).strip("\n") if len(card_lines) > 1 else card_text
        result = f"{msg}\n\n━━━━━━━━━━\n📣 마케팅 정리\n{body}"
    except Exception as e:
        logger.warning(f"[하루 일과 정리] 마케팅 섹션 병합 실패(문의 정리 본문은 그대로 발송): {e}")
        result = msg

    if any(bad in result for bad in ("&amp;", "&lt;", "&gt;")):
        logger.warning("[하루 일과 정리] 최종 메시지에 HTML 엔티티 잔존 감지 — html.unescape 로 강제 정규화")
        result = html.unescape(result)
    return result


def _build_digest_inquiry(today: str) -> str:
    """문의알림방 — 오늘 문의를 멤버십/성인강습/유소년강습 카테고리로 정리 + 회원관리 미처리 현황 +
    마케팅 정리(21시 단독발송 통합, GM 2026-07-20). str 반환(전송 분리).
    intake(자체폼) 병합 조회라 실시간 알림이 누락된 건(예: 자체폼 강습)도 여기서 전부 포함된다. 2026-07-18 GM 고도화."""
    weekday = _WEEKDAY_KOR[datetime.now().weekday()]
    header = f"📊 [하루 일과 정리] {today}({weekday})\n🔔 오늘의 문의 정리"
    try:
        mem_raw = _digest_fetch_list("member_inquiry_list")
        adult_raw = _digest_fetch_list("lesson_inquiry_list", type="성인강습")
        youth_raw = _digest_fetch_list("lesson_inquiry_list", type="유소년강습")
    except Exception:
        msg = f"{header}\n\n조회 지연으로 문의 현황을 불러오지 못했습니다. (서버 콜드스타트 추정 — 잠시 후 재시도됩니다)"
        return _append_digest_marketing_section(msg)

    # QA/배포검증 더미 행 제외 — GAS 응답 수신 직후 한 곳에서만 필터링(GM 2026-07-20).
    # 이후 오늘 문의 목록·미처리 현황 집계 모두 이 필터된 리스트를 공유해서 쓴다(중복 필터링 금지).
    mem, mem_removed = _filter_test_rows(mem_raw)
    adult, adult_removed = _filter_test_rows(adult_raw)
    youth, youth_removed = _filter_test_rows(youth_raw)
    test_removed_total = mem_removed + adult_removed + youth_removed

    def _today(rows: list) -> list:
        return [r for r in rows if str(r.get("timestamp", "")).startswith(today)]

    mem_t, adult_t, youth_t = _today(mem), _today(adult), _today(youth)
    total = len(mem_t) + len(adult_t) + len(youth_t)
    if total == 0:
        msg = f"{header}\n\n오늘 신규 문의 없음."
    else:
        def _section(title: str, rows: list, field: str, fixed_dot: str = "") -> str:
            """종목별 그룹 렌더(GM 2026-07-20 수정3 — 사람 한 줄 나열 → 종목별 그룹).
            _split_sports() 로 한 사람이 여러 종목이면 종목마다 각각 노출(의도된 중복)."""
            if not rows:
                return f"■ {title} (0)"
            groups: dict = {}
            for r in rows:
                nm = html.unescape(str(r.get("name", "") or "-")).strip() or "-"
                ph = html.unescape(str(r.get("phone", "") or "-")).strip() or "-"
                ch = html.unescape(str(r.get("channel", "") or "")).strip()
                species = _split_sports(str(r.get(field, "") or "")) or ["미분류"]
                for sp in species:
                    groups.setdefault(sp, []).append((nm, ph, ch))
            person_count = len(rows)
            species_count = sum(len(v) for v in groups.values())
            lines = [f"■ {title} ({person_count}명 · 종목 {species_count}건)"]
            ranked = sorted(groups.items(), key=lambda kv: -len(kv[1]))
            for sp, entries in ranked:
                dot = fixed_dot or _digest_dot(sp)  # 멤버십=유형색 고정(🟡) / 강습=종목색
                lines.append(f"{dot}{sp} ({len(entries)})")
                for nm, ph, ch in entries[:20]:
                    line = f"   {nm} · {ph}"
                    if ch:
                        line += f" · {ch}"
                    lines.append(line)
                if len(entries) > 20:
                    lines.append(f"   …외 {len(entries) - 20}명")
            return "\n".join(lines)

        body = "\n\n".join([
            _section("멤버십", mem_t, "program", fixed_dot="🟡 "),
            _section("성인강습", adult_t, "sport"),
            _section("유소년강습", youth_t, "sport"),
        ])
        msg = f"{header}\n\n총 {total}건\n\n{body}"

    unprocessed = _build_digest_member_unprocessed(mem, adult, youth, today)
    msg = f"{msg}\n\n{unprocessed}"

    result = _append_digest_marketing_section(msg)
    if test_removed_total:
        result = f"{result}\n· (테스트행 {test_removed_total}건 제외)"
    return result


def _build_digest_check(today: str) -> str:
    """점검관리방 — 3섹션 핵심요약(🏗 시설부 / 🛠 지원부 / 🅿 주차부). str 반환(전송 분리).
    GM 2026-07-19: 카톡 23시 공유방과 **동일 포맷**(공용 모듈 support_check_summary)으로 통일 +
    지원부 회차분해 요일 반영(주말=오전조·마감조 2회차, 평일 3회차 · 서버 total>0 회차만)."""
    weekday = _WEEKDAY_KOR[datetime.now().weekday()]
    md = datetime.now().strftime("%m-%d")
    # 제목 = 'MM-DD(요일) 금일 점검 현황보고' (GM 2026-07-13: 12시 오전보고와 짝 · 저녁=금일 종합)
    header = f"🌙 {md}({weekday}) 금일 점검 현황보고\n{_DIVIDER}"
    try:
        import support_check_summary as _scs   # scripts/ 는 상단에서 sys.path 삽입됨
        lines, _filled = _scs.build_summary_lines(date=today)
        return f"{header}\n\n" + "\n".join(lines)
    except Exception as e:
        logger.warning(f"점검 핵심요약 렌더 실패(폴백): {e}")
        return f"{header}\n\n점검 데이터 조회 실패."


def _build_digest_reception(today: str) -> str:
    """종합접수처 — 오늘 VOC 접수 핵심요약 + 상세. str 반환(전송 분리)."""
    weekday = _WEEKDAY_KOR[datetime.now().weekday()]
    header = f"📋 [하루 일과 정리] {today}({weekday})\n📮 오늘의 접수 현황"
    try:
        resp = requests.get(
            VOC_EXEC_URL, params={"action": "reg_list"},
            timeout=20, allow_redirects=True,
        )
        if resp.status_code != 200:
            return f"{header}\n\n조회 실패 (HTTP {resp.status_code})"
        data = resp.json()
        if not data.get("ok"):
            return f"{header}\n\n조회 실패 (ok=False)"
        rows = data.get("data", [])
    except Exception as e:
        return f"{header}\n\n조회 오류: {str(e)[:120]}"

    # createdAt = "YYYY-MM-DD HH:MM:SS" (KST 로컬)
    today_rows = [r for r in rows if str(r.get("createdAt", "")).startswith(today)]
    if not today_rows:
        return f"{header}\n\n오늘 신규 접수 없음."

    cat_count: dict[str, int] = {}
    undone = 0
    for r in today_rows:
        cat = r.get("category", "기타") or "기타"
        cat_count[cat] = cat_count.get(cat, 0) + 1
        if str(r.get("status", "")) != "완료":
            undone += 1

    summary_lines = [f"총 {len(today_rows)}건 (미처리 {undone}건)"]
    for cat, c in sorted(cat_count.items(), key=lambda x: -x[1]):
        summary_lines.append(f"  · {cat}: {c}건")

    detail_lines: list[str] = []
    for r in today_rows[:15]:
        created = str(r.get("createdAt", ""))
        hm = created[11:16] if len(created) >= 16 else "--:--"
        cat = r.get("category", "") or ""
        equip = r.get("equipName", "") or r.get("loc", "") or ""
        st = r.get("status", "") or ""
        detail_lines.append(f"  {hm} [{cat}] {equip[:20]} — {st}")

    over = len(today_rows) - 15
    if over > 0:
        detail_lines.append(f"  …외 {over}건")

    return (
        f"{header}\n\n"
        f"[핵심 요약]\n" + "\n".join(summary_lines) + "\n\n"
        f"[상세]\n" + "\n".join(detail_lines)
    )


# 카카오톡 ★부서장 방 이름 — kakao_report_sender.py --only-room 매칭(열린 채팅창 제목과 정확히 일치해야 함).
# GM이 2026-07-18 개설. 창 제목이 다르면 이 값을 실제 제목으로 맞출 것.
KAKAO_DEPTHEAD_ROOM = "★부서장"


def _is_rest_day(d) -> bool:
    """주말(토·일) 또는 휴관·공휴일(close_days) → 20시 발송."""
    import close_days as _cd  # scripts/ 는 상단에서 sys.path 삽입됨
    return d.weekday() >= 5 or _cd.is_closed(d)


def run_daily_digest(early: bool = False) -> None:
    """3방 하루 일과 정리 알림 오케스트레이터 — 매일 20:00/22:30 둘 다 등록되지만,
    휴일(주말·close_days)은 20:00(early=True)만 실행 / 평일은 22:30(early=False)만 실행
    (GM 2026-07-20, close_days 공휴일 반영 — 기존 요일 고정 mon-fri/sat,sun 을 대체).
    문의 정리는 카카오톡 ★부서장 방에도 추가 발송(GM 2026-07-18)."""
    from datetime import timezone as _tz3
    now_dt = datetime.now(_tz3.utc) + timedelta(hours=9)
    today = now_dt.strftime("%Y-%m-%d")
    rest_day = _is_rest_day(now_dt.date())
    if rest_day != early:
        logger.info(f"[하루 일과 정리] 게이트 스킵 — early={early} rest_day={rest_day} today={today}")
        return
    label = "[하루 일과 정리]"
    logger.info(f"{label} 시작 — today={today}")

    # ── 스트림 #1 문의 및 컨택&등록 현황 (통일 포맷 msg5618 · 2026-07-22) ────────────────
    # 옛 _build_digest_inquiry(종목별 그룹) 대체. 확정 포맷: report_stream_1_inquiry.
    inquiry_plain = None  # 카카오용 평문(태그·엔티티 없음)
    try:
        import report_stream_1_inquiry as _s1
        import re as _re_s1, html as _html_s1
        inquiry_html = _s1.build_digest(today)
        inquiry_plain = _re_s1.sub(r"<[^>]+>", "", _html_s1.unescape(inquiry_html))
        success = send_telegram(DIGEST_INQUIRY_CHAT_ID, inquiry_html, parse_mode="HTML")
        if success:
            logger.info(f"{label} 문의알림방 발송 완료 chat_id={DIGEST_INQUIRY_CHAT_ID} (stream1·HTML·msg5618)")
        else:
            logger.error(f"{label} 문의알림방 발송 실패 chat_id={DIGEST_INQUIRY_CHAT_ID}")
    except Exception as e:
        logger.error(f"{label} 문의알림방(stream1) 예외: {e}")

    # ── 스트림 #2 점검+이슈 현황 (점검현황방 단독 · 2026-07-22) ─────────────────────
    try:
        import report_stream_2_check as _s2
        s2_msg = _s2.build_digest(today)
        success = send_telegram(DIGEST_CHECK_CHAT_ID, s2_msg)
        if success:
            logger.info(f"{label} 점검현황방 발송 완료 chat_id={DIGEST_CHECK_CHAT_ID} (stream2)")
        else:
            logger.error(f"{label} 점검현황방 발송 실패 chat_id={DIGEST_CHECK_CHAT_ID}")
    except Exception as e:
        logger.error(f"{label} 점검현황방(stream2) 예외: {e}")

    # ── 스트림 #2b 종합접수 현황+미처리 적체 리마인드 (종합접수방 단독 복원 · 2026-07-22) ──
    # 배9424(2026-07-21)의 '점검현황방 병합'을 되돌림 — GM 지시. 접수만 별도 종합접수방으로.
    try:
        import report_stream_2b_reception as _s2b
        s2b_msg = _s2b.build_digest(today)
        success = send_telegram(DIGEST_RECEPTION_CHAT_ID, s2b_msg)
        if success:
            logger.info(f"{label} 종합접수방 발송 완료 chat_id={DIGEST_RECEPTION_CHAT_ID} (stream2b)")
        else:
            logger.error(f"{label} 종합접수방 발송 실패 chat_id={DIGEST_RECEPTION_CHAT_ID}")
    except Exception as e:
        logger.error(f"{label} 종합접수방(stream2b) 예외: {e}")

    # 카카오톡 ★부서장 방에도 문의 정리 발송 (GM 2026-07-18 · best-effort).
    if inquiry_plain:
        try:
            sender = REPO_ROOT / "scripts" / "kakao_report_sender.py"
            env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
            proc = subprocess.run(
                [sys.executable, str(sender), "--message", inquiry_plain, "--only-room", KAKAO_DEPTHEAD_ROOM],
                cwd=str(REPO_ROOT), capture_output=True, text=True,
                encoding="utf-8", errors="replace", env=env, timeout=180,
            )
            tail = (proc.stdout or "").strip().splitlines()[-1:] or ["(출력없음)"]
            logger.info(f"{label} 카톡 {KAKAO_DEPTHEAD_ROOM} 발송: {tail[0]}")
        except Exception as e:
            logger.error(f"{label} 카톡 {KAKAO_DEPTHEAD_ROOM} 발송 예외: {e}")


def run_stream_3_mgmt() -> None:
    """스트림 #3 매출+운영+인사 현황 보고 (매일 09:30 · 업무보고방) — CTO 2026-07-22.
    확정 포맷: ops_mgmt_digest_test v3 (54% 압축 · GM ok). 카카오=GM go 후 활성화.
    시우(COO) 최종목표 씨앗 — 자율화 완성 시 COO 인계 예정."""
    label = "[스트림 #3 매출+운영+인사]"
    logger.info(f"{label} 시작")
    try:
        import report_stream_3_mgmt as _s3
        _s3.run(dry_run=False, kakao_go=False)
        logger.info(f"{label} 완료 (업무보고방 발송 · 카카오=GM go 후속)")
    except Exception as e:
        logger.error(f"{label} 예외: {e}")


def _build_07_combined_body() -> str:
    """07시 통합(GM 2026-06-29): 어제 항로 결산 + 직원 공유 카드를 한 메시지로(07:05 분리발송 폐지)."""
    main = _build_07_body()
    card = _build_share_card_body()
    return (
        f"{main}\n\n"
        f"✂️ ───── 직원 공유용 (아래부터 복사) ─────\n\n"
        f"{card}"
    )


SLOT_BUILDERS = {
    "06": _build_06_body,
    "07": _build_07_combined_body,
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
    slot: "06" | "07" | "09" | "12" | "15" | "18" | "21" | "22" | "23"
    """
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    label = f"[{'TEST ' if test_mode else ''}{slot}시 보고]"
    logger.info(f"{label} 트리거 실행 시작 ({now_str})")

    owner_id = get_owner_id()
    if not owner_id:
        logger.error(f"{label} owner_id 미등록 — state.json 확인 필요. 보고 생략.")
        return

    # 23시 마감 점검 = 조건부 GM DM (GM 2026-07-18): 점검 이상(미완 회차·기준이탈·반복제안)
    #   있을 때만 GM DM 발신, 정상이면 미발신 — 상세 점검은 카톡 23시가 담당.
    #   test_mode는 미리보기라 항상 발신(GM DM). 여기서 본문을 한 번만 산출해 재조회 방지.
    body_override: str | None = None
    if slot == "23" and not test_mode:
        _b23, _anom23 = _compute_23_body_and_anomaly()
        if not _anom23:
            logger.info(f"{label} 마감 점검 이상 0 — GM DM 조건부 미발신(상세는 카톡 23시 담당)")
            return
        if not CHECK_2300_GM_DM_ENABLED:
            logger.info(f"{label} CHECK_2300_GM_DM_ENABLED=False — 마감점검 개인DM 게이트 OFF(점검관리방·카톡 23시로 수신, 계산/원장 적재는 보존). 미발신")
            return
        body_override = _b23
        logger.info(f"{label} 마감 점검 이상 감지 — GM DM 발신")

    try:
        if body_override is not None:
            body = body_override
        elif (builder := SLOT_BUILDERS.get(slot)):
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

    # 06시 개인(하루시작·운동) 슬롯만 저신호 무음 대상 — 다른 슬롯(07/08/12/21 등 고신호)은 무영향.
    if slot == "06" and not test_mode:
        try:
            skip_personal_0600 = muted("personal_0600")
        except Exception:
            skip_personal_0600 = False
        if skip_personal_0600:
            logger.info(f"{label} [무음] personal_0600 저신호 설정 — 06시 개인 슬롯 발송 스킵 (notify_prefs.py)")
            return

    # 12시 메시지는 대시보드 링크를 클릭형 앵커로 내보내기 위해 HTML 모드로 발송 — 2026-07-10 GM.
    # 다른 슬롯은 MarkdownV2 그대로(무영향).
    parse_mode = "HTML" if slot == "12" else "MarkdownV2"

    # 12시 점검현황 = 점검관리방 전용(GM 2026-07-13) — 업무보고(owner DM) 중복 발송 제거.
    #   test_mode는 GM DM(owner)로 미리보기만(방 오발송 방지).
    if slot == "12" and not test_mode:
        if not CHECK_MORNING_1200_ENABLED:
            logger.info(f"{label} CHECK_MORNING_1200_ENABLED=False — 오전점검(12시) 게이트 OFF. 점검관리방 미발신(본문 계산은 보존)")
            return
        room_ok = send_telegram(CHECK_NUDGE_CHAT_ID, body, parse_mode=parse_mode)
        logger.info(f"{label} 점검관리방 발송 {'완료' if room_ok else '실패'} chat_id={CHECK_NUDGE_CHAT_ID}")
        return

    success = send_telegram(owner_id, body, parse_mode=parse_mode)
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
    # 배1307 시토 2026-07-20: 07-14 GAS 호출 확장(비교기준선 2종) 이후 실측 211s 소요 →
    # 구 timeout=120 이 매 실행 강제종료(SIGTERM)해 kpi_values.json 이 07-14 09:17 이후 6일간
    # 갱신 정지(scheduler.log 전 회차 timeout ERROR 확인). 실측치+여유분으로 300s 상향.
    def _collect_kpi():
        try:
            subprocess.run(
                [sys.executable, "scripts/kpi_collector.py"],
                cwd=str(BASE.parent), timeout=300,
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

    # ── 시트 칸 계약 점검 (매일 07:50 — 08:00 통합 브리프 직전) — CPO 2026-07-20 ──
    # 재발방지 A안 0단계(GM 확정, 값 규칙 포함). 정상이면 완전 침묵 — 어긋남만 업무보고방 알림.
    def _check_sheet_contract():
        try:
            subprocess.run(
                [sys.executable, "scripts/collectors/cpo_sheet_contract.py"],
                cwd=str(BASE.parent), timeout=180,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            logger.info("cpo_sheet_contract 실행 완료 (시트 칸 계약 점검)")
        except Exception as e:
            logger.error(f"cpo_sheet_contract 실행 실패: {e}")

    scheduler.add_job(
        _check_sheet_contract,
        trigger=CronTrigger(hour=7, minute=50),
        id="cpo_sheet_contract_check",
        misfire_grace_time=600,
        coalesce=True,
    )
    logger.info("cpo_sheet_contract 등록 완료 (매일 07:50) — 시트 칸 계약 점검(재발방지 A안 0단계)")

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
    _FUNNEL_EXEC = 'https://script.google.com/macros/s/AKfycbykgMyFc-g_KG7x3HoKStKBwerKhYYfmbqNeFqCL5O1b_4-1nng4wEiKhkNJtfB4BWo/exec'

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
        next_run_time=datetime.now(),
    )
    logger.info("queue_archive_sweep 등록 완료 (6시간 주기, 부팅 즉시 1회) — _queue.json 비대화 방지")

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
        logger.info("=== 정규 스케줄 시작: 06/12/18/21/23시 (GM 알림 홍수 축소 · 2026-07-18 GM 승인) ===")
        # [2026-06-07 GM 확정] 08시는 ceo_morning_pipeline(별도 Task Scheduler) 담당.
        # [2026-07-18 GM 승인] GM DM 홍수 축소 — 07(어제결산)·09(매출/진행)·15(중간정리)·
        #   22(취침) GM DM 슬롯 폐지. 핵심값(어제완료·매출1줄·북극성top·직원카드)은 08:00
        #   통합브리프(ceo_morning_pipeline)로 흡수. 23시는 조건부(점검 이상시만 GM DM,
        #   정상이면 미발신 — 상세는 카톡 23시 담당). 12시는 점검관리방(실무진) 전용이라 유지.
        #   builder 함수(_build_07/09/15/22_body)는 보존 — 되돌림·--manual-test 미리보기용.
        schedule_map = {
            "06": (6, 0),
            "12": (12, 0),
            "18": (18, 0),
            "21": (21, 0),
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

        # ── 하루 일과 정리 — 문의·점검·접수 3방 핵심+상세 — CTO 2026-06-29 ──
        #   마감시간 연동: 휴일(주말·close_days 공휴일)=20:00 / 평일=22:30 (GM 2026-07-20,
        #   요일 고정(mon-fri/sat,sun) 대신 close_days 판정으로 교체 — 신정 등 평일 공휴일도 20시 반영).
        #   두 잡 모두 매일 등록하되 run_daily_digest(early) 내부 게이트가 실제 실행 여부를 가른다.
        scheduler.add_job(
            run_daily_digest,
            trigger=CronTrigger(hour=20, minute=0, timezone="Asia/Seoul"),
            args=[True],
            id="daily_digest_early",
            misfire_grace_time=600,
            coalesce=True,
        )
        scheduler.add_job(
            run_daily_digest,
            trigger=CronTrigger(hour=22, minute=30, timezone="Asia/Seoul"),
            args=[False],
            id="daily_digest_late",
            misfire_grace_time=600,
            coalesce=True,
        )
        logger.info("daily_digest 등록 완료 — 매일 20:00(휴일 게이트)/22:30(평일 게이트), 하루 일과 정리 3방 발송")

        # ── 스트림 #3 매출+운영+인사 현황 보고 (매일 09:30) — CTO 2026-07-22 ───────────
        try:
            scheduler.add_job(
                run_stream_3_mgmt,
                trigger=CronTrigger(hour=9, minute=30, timezone="Asia/Seoul"),
                id="stream_3_mgmt_0930",
                misfire_grace_time=600,
                coalesce=True,
            )
            logger.info("stream_3_mgmt 등록 완료 — 매일 09:30 업무보고방 발송 (스트림 #3)")
        except Exception as e:
            logger.warning(f"stream_3_mgmt 등록 실패: {e}")

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
