"""
웰페리온 일일 자동 보고 스케줄러 v2.2
-------------------------------
정규 스케줄: 06/12/21/23시 텔레그램 자동 보고 (GM 알림 홍수 축소 · 2026-07-18 GM 승인)
  · GM DM: 06(개인)·21(마감 — 18시 퇴근·저녁·명언 흡수)·23(마감점검, GM DM은 폐지·원장 적재만 보존)
  · 12시는 점검관리방(실무진) 전용이었으나 GM DM 아님 — 발신 자체는 폐지(아래 참조)
  · ★배10011(2026-07-24, GM 승인) — 알림 묶기 1주차:
      ①18:00 GM DM 폐지, 내용(퇴근인사·저녁루틴·명언)은 21:00 본문 서두로 흡수(builder 함수는
        되돌림·--manual-test 미리보기용으로 보존 — 07/09/15/22 폐지 때와 동일 관례).
      ②오전점검(12시)·마감점검 개인DM(23시) 킬스위치(CHECK_MORNING_1200_ENABLED/
        CHECK_2300_GM_DM_ENABLED)를 "끄기"에서 "삭제"로 전환 — 되돌릴 수 있는 스위치를
        남겨두면 죽은 코드로 있다 누가 또 켠다(배10008과 동일 원칙). 발신은 구조적으로
        영구 미발신, 23시의 원장 적재(CHECK_INCOMPLETE_LEDGER, 카톡 22:30/23:00 "반복 미완료
        제안"이 계속 소비)는 그대로 보존.
  · 07(어제결산)·09(매출/진행)·15(중간정리)·22(취침) GM DM 슬롯은 08:00 통합브리프로 흡수·폐지
테스트 모드: python daily_scheduler.py --test  →  1시간 주기 실행
※ 08시(오늘의 항로 통합브리프)는 ceo_morning_pipeline.py (별도 Task Scheduler) 담당 —
   어제완료·매출1줄·북극성top·직원카드를 흡수(2026-07-18). 여기서 중복 발송 없음

슬롯 정본 = 웰페리온 ERP T2(업무자동화SSOT) 텔레그램탭 — 슬롯 변경 시 T2만 수정
※ 08시(오늘의 항로)는 ceo_morning_pipeline.py 별도 Task Scheduler 담당 — 여기서 중복 발송 없음

운영 원칙:
- 워처 3종 (archive_result_watcher·planning_to_archive_watcher·permission_watcher)은 2026-05-31 제거·파일부재(하단 주석 참조)
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


_LOCK_FILE = Path(__file__).parent / "daily_scheduler.lock"
_LOCK_FH = None          # ★전역으로 붙들고 있어야 락이 유지된다(닫히면 풀린다)


def _acquire_single_instance() -> None:
    """진짜 중복 기동 차단 — 파일 배타 락. 프로세스가 죽으면 OS 가 알아서 놓는다.

    ★왜 PID 파일로는 안 됐나 (2026-08-13 실측 · 배596):
      PID 파일 방식은 '누가 파일에 적혀 있나'를 본다. 그런데 이 모듈을 **함수 하나 쓰려고
      import 하는 짧은 프로세스**도 그 자리에서 자기 PID 를 적고 곧 죽었다. 그러면 파일은
      죽은 PID 를 가리키게 되고, 다음에 뜨는 진짜 스케줄러는 가드를 그냥 통과한다 —
      그래서 두 인스턴스가 같이 살았다(같은 방으로 두 번 발신될 뻔했다).
      락은 '지금 이 순간 누가 쥐고 있나'를 본다. 적히는 게 아니라 쥐는 것이라 찌꺼기가 없다.
      2026-08-01 배265 의 반대 사고(죽은 PID 를 살아있다고 오판해 12시간 정지)도 함께 사라진다.
    """
    global _LOCK_FH
    import msvcrt
    try:
        _LOCK_FH = open(_LOCK_FILE, "a+")
        _LOCK_FH.seek(0)
        msvcrt.locking(_LOCK_FH.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        print("[daily_scheduler] 이미 실행 중. 중복 기동 차단 후 종료.", flush=True)
        sys.exit(0)
    except Exception as exc:  # noqa: BLE001
        # 락 자체를 못 잡으면 조용히 통과시키지 않는다 — 통과 = 중복 발신 위험.
        print(f"[daily_scheduler] 중복 기동 검사 실패({exc}) — 안전을 위해 종료.", flush=True)
        sys.exit(1)
    _PID_FILE.write_text(str(os.getpid()))    # 표시용(사람이 보는 값)


def _check_pid_lock() -> None:
    """구 PID 파일 검사 — 남겨 두되 더는 쓰지 않는다(위 _acquire_single_instance 가 정본)."""
    if _PID_FILE.exists():
        try:
            old_pid = int(_PID_FILE.read_text().strip())
            # ★2026-08-01(시토 · 배265) — PID 재사용 오탐 차단.
            #   실사고: 어제 죽은 스케줄러의 PID 2824 를 윈도우가 svchost 에 재배정했고,
            #   "그 PID 가 살아있다"만 보던 이 검사가 '이미 실행 중'으로 오판해
            #   로그온 재기동을 12시간 넘게 막았다(00:28~13:00 전 예약작업 정지).
            #   PID 존재만이 아니라 **그게 우리 프로세스인지**까지 본다.
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {old_pid}",
                 "/FI", "IMAGENAME eq python*", "/FO", "CSV"],
                capture_output=True, text=True, shell=True
            )
            if str(old_pid) in result.stdout:
                print(f"[daily_scheduler] 이미 실행 중 (PID {old_pid}). 중복 기동 차단 후 종료.", flush=True)
                sys.exit(0)
        except Exception:
            pass
    _PID_FILE.write_text(str(os.getpid()))


# ★직접 실행할 때만 잠근다 — 함수만 쓰려고 import 하는 프로세스는 건드리지 않는다(배596 원인).
if __name__ == "__main__":
    _acquire_single_instance()

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

try:  # 자율현황 라이브 섹션용 로컬 읽기전용 서버(best-effort) — 임포트 실패해도 발신 무영향
    from live_cli_status_server import start_server as start_live_cli_status_server
except Exception:
    def start_live_cli_status_server(logger=None):
        return None

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

# 미체크 항목명 병합(scripts/support_check_summary.py) — 정본 위임. GM 2026-07-23(시토).
#   22:30 보고와 17시·22시 독려가 같은 로직을 쓰게 단일화. import 실패해도 발신 무영향
#   (이 파일은 상주 봇이라 기동 실패를 절대 허용하지 않는다 — 아래 로컬 폴백 유지).
try:
    import os as _os3b, sys as _sys3b
    _scr3b = _os3b.path.abspath(_os3b.path.join(_os3b.path.dirname(_os3b.path.abspath(__file__)), "..", "scripts"))
    if _scr3b not in _sys3b.path:
        _sys3b.path.insert(0, _scr3b)
    from support_check_summary import merged_unchecked_names as _scs_merged_unchecked_names
    _SCS_OK = True
except Exception:
    _SCS_OK = False
    _scs_merged_unchecked_names = None  # type: ignore[assignment]

# 운영 다이제스트 공용 수집층 (scripts/collectors/ops_shared.py) — GAS URL 상수 3종
# (FUNNEL_EXEC_URL·RECEPTION_EXEC_URL·SSOT_API_URL)·재시도 GET 래퍼·UTC→KST 변환·업무완료
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
        RECEPTION_EXEC_URL,
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
    RECEPTION_EXEC_URL = (
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
        # ops_shared.utc_iso_to_kst_date와 동일 로직(폴백 경로 — import 실패시만 사용).
        # 2026-07-27 시토(배10357): GAS inquiry_list KST 직렬화 전환에 맞춰 Z유무 분기 추가(이중변환 방지).
        from datetime import timezone as _tz
        s = str(iso_str or "").strip()
        if not s:
            return ""
        try:
            if s.endswith("Z"):
                dt_utc = datetime.fromisoformat(s.rstrip("Z").replace("T", " ")).replace(tzinfo=_tz.utc)
                return (dt_utc + timedelta(hours=9)).strftime("%Y-%m-%d")
            return s[:10]
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

# ── 점검 알림 통합 킬스위치 — 배10011(2026-07-24, GM 승인)로 삭제됨 ──────────────
#   과거 CHECK_MORNING_1200_ENABLED/CHECK_2300_GM_DM_ENABLED(둘 다 False)는 재부팅
#   가능한 스위치라 "꺼두면 죽은 코드로 남아 누가 또 켠다"(배10008과 동일 원칙) 위험이
#   있어 삭제했다. 12시·23시 GM DM은 run_report() 내부에서 무조건 미발신으로 고정됐고
#   (23시의 원장 적재 부작용은 보존), 되돌리려면 이 커밋을 revert해야 한다(실수로 못 켬).


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
    # ★2026-08-03 시토 — parse_mode=None 이면 **키 자체를 빼야 한다.**
    #   종전엔 None 도 그대로 실어 보내 텔레그램에 `"parse_mode": null` 이 갔고,
    #   텔레그램은 그걸 400 `unsupported parse_mode` 로 거절한다(평문 발송이 통째로 실패).
    #   실사고: 2026-08-03 14:00 「회차 제출누락 알림」이 3회 재시도 전부 이 오류로 실패해
    #   점검관리방에 안 갔고, GM 데스크톱 경보만 떴다. 평문으로 보내려던 호출 3곳
    #   (2484·2674·3062줄)이 전부 같은 구멍을 통과하고 있었다 — 관문 한 곳에서 막는다(약속 L21).
    payload = {"chat_id": chat_id, "text": text}
    if parse_mode:
        payload["parse_mode"] = parse_mode
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


def _fetch_yesterday_queue_done(day: str | None = None, with_evidence: bool = False) -> list[str]:
    """
    status/_queue.json 에서 그날 완료된 배 제목 목록 반환.
    updated_at(우선) · processed_at · enqueued_at 중 하나가 그 날짜인 DONE/완료 항목.
    day 를 안 주면 예전 그대로 '어제'(기존 호출부 동작 불변).
    with_evidence=True 면 제목 앞에 증거 유무를 붙인다(✅=증거 있음 · 🔍=증거 없음).

    ★2026-08-13(시토 · 배447) — 날짜 인자와 updated_at 을 더했다.
      왜: 21시 알림이 업무 시트(GAS todo_list)만 보고 배 원장은 아예 안 봐서, 실제로 닫힌
      배가 '업무 완료 0건'으로 나갔다(웰리 실측 2026-08-09 · 그날 DONE 2척). 21시 쪽에서
      쓰려면 '오늘'이 필요하고, 배를 닫을 때 실제로 찍히는 칸은 updated_at 이다.
      새 함수를 만들지 않고 이 함수 하나를 넓힌다(약속 L21·L01).
    """
    target = day or (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
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
        dates = [str(x.get(k) or "") for k in ("updated_at", "processed_at", "enqueued_at")]
        if not any(d.startswith(target) for d in dates):
            continue
        title = str(x.get("title") or "").strip()
        if not title:
            continue
        if with_evidence:
            has_ev = bool(str(x.get("artifact_url") or "").strip())
            # 낱말 중간에서 자르지 않는다 — 마지막 공백까지만 남기고 …를 붙인다.
            short = title
            if len(short) > 56:
                cut = short[:56]
                sp = cut.rfind(" ")
                short = (cut[:sp] if sp > 30 else cut).rstrip(" ·—-") + "…"
            result.append(("✅ " if has_ev else "🔍 ") + short)
        else:
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

    # GM 지시 2026-08-12 — 아침에 무엇을 먹고 어떤 순서로 움직이는지를 G1 에 적어 둔 그대로 읊는다.
    # 여기서 새로 적지 않는다: 정본은 status/gm_personal_routine.json 이고 그 값은 G1 「내 리듬」 표에서 왔다.
    plan_lines = []
    try:
        import gm_checkin as _ck
        plan_lines = _ck.morning_plan_lines()
    except Exception as e:
        logger.warning(f"[06시] 아침 계획 줄 실패: {e}")

    workout_lines = ["🏋️ 오늘 운동 점검"]
    for name, unit in DAILY_WORKOUT_ITEMS:
        workout_lines.append(f"  • {name}  ___{unit}  ☐")

    return (
        f"{_unified_header('06', '개인', '하루시작·운동')}\n"
        f"오늘도 좋은 하루 되십시오."
        f"{quote_line}\n"
        + ("\n".join(plan_lines) + "\n\n" if plan_lines else "")
        + "\n".join(workout_lines)
        + _checkin_morning_block()
        + f"\n\n{_AUTO_FOOTER}"
    )


def _checkin_morning_block() -> str:
    """06시 본문 뒤에 붙는 「오늘 하나씩」 — 07:00 단독 알림을 여기로 흡수(GM 2026-08-08).

    GM: "06:00 하루 시작 / 07:00 = 21:30 같은 맥락? / 22:00 하루 마무리."
    아침 인사와 오늘 할 네 가지는 같은 맥락이라 알림 두 개로 나눌 이유가 없다.
    개인 알림을 하루 4개에서 2개로 줄인다 — 아침 한 번, 저녁 한 번.
    """
    try:
        import gm_checkin as _ck
        p = _ck.plan()
        if not p:
            return ""
        lines = ["", "", "🌅 오늘 하나씩 — 큰 거 아닙니다"]
        for tid, icon, label, _k in _ck.TOROKS:
            if p.get(tid):
                lines.append(f"  {icon} {label}   {p[tid]}")
        lines.append("  저녁에 이 다섯 가지를 그대로 여쭙겠습니다.")
        return "\n".join(lines)
    except Exception:
        return ""


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
    """한국식 금액 표기. 정본 = scripts/erp_status_publisher.kr_amt (2026-08-08 단일화).

    같은 규칙을 보고기마다 따로 갖고 있으면 한 곳만 고쳤을 때 표기가 어긋난다(약속 L01).
    임포트가 실패해도 돈 표기 하나 때문에 09시 보고가 통째로 죽으면 안 되므로 폴백을 둔다.
    """
    try:
        from erp_status_publisher import kr_amt
        return kr_amt(n)
    except Exception:
        try:
            v = round(float(n))
        except (TypeError, ValueError):
            return "—"
        return f"{v:,}원"


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

    # 마감 전(당월)엔 s_month 가 항상 null 이라 '—' 로 나갔다 — 08시 보고와 같은 뿌리(배446,
    # 2026-08-08). 스냅샷의 당월 진행중 누적으로 떨어지고 '(진행 중)'을 붙여 마감값과 구분한다.
    # 판정·표기는 erp_status_publisher 한 곳이 한다(약속 L01).
    try:
        from erp_status_publisher import read_sales_month_display
        _s_text, _in_progress = read_sales_month_display()
    except Exception:
        _s_text, _in_progress = "—", False
    if _s_text == "—":
        _s_text = _kr_amt(s_month)
    table_rows = [
        ("이달 매출", f"{_s_text}{' (진행 중)' if _in_progress else ''}"),
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


def _18_evening_lines() -> str:
    """18시 콘텐츠(퇴근인사·저녁루틴·명언) — 배10011(2026-07-24)로 21시 본문 서두에 흡수.
    명언은 EVENING_QUOTES 정적 리스트에서 날짜 결정론(day % len) 선택."""
    now = datetime.now()
    quote = EVENING_QUOTES[now.day % len(EVENING_QUOTES)]
    return (
        f"🌙 오늘도 수고하셨습니다.\n"
        f"🌆 저녁 루틴 — 오늘 마무리하고 재충전하세요.\n"
        f'\n> "{quote}"\n'
    )


def _build_18_body() -> str:
    """18시 — 퇴근 인사 + 저녁 루틴 + 명언 [개인] (운영 데이터 0·GM 2026-07-09)

    [GM 2026-07-09] 18시를 개인 메시지로 축소 — 점검 현황·오늘 성과(커밋)·대시보드
    링크 전부 제거. 시설·지원·주차 마감 현황은 23시로 일원화. 여기는 퇴근+저녁루틴+
    명언만.

    ★배10011(2026-07-24, GM 승인): 18:00 단독 발신은 폐지, 내용은 21:00 본문 서두로
    흡수(schedule_map에서 "18" 제거 — 이 함수는 더 이상 cron으로 안 불림). 이 함수 자체는
    되돌림·--manual-test 미리보기용으로 보존한다(2026-07-18 07/09/15/22 폐지 때와 동일 관례).
    """
    return (
        f"{_unified_header('18', '개인', '퇴근·저녁')}\n"
        f"{_18_evening_lines()}\n"
        f"{_AUTO_FOOTER}"
    )


def _build_21_body() -> str:
    """21시 — 오늘 최종 정리 + 내일 항로점 브릿지 [회사] · 업무보고방(GM_DM)

    ★배10011(2026-07-24, GM 승인): 18:00 퇴근인사·저녁루틴·명언(_18_evening_lines)을
    본문 서두에 흡수(18시 단독 발신 폐지).
    ★배541(2026-08-12): 그 개인 3줄을 20:30 하루 방 저녁 정리본(run_gm_evening_recap)으로
    옮겼다. GM 정의상 이 메시지가 가는 업무보고방은 개인 내용을 담지 않는다 — 지운 게 아니라
    방을 바꾼 것이라 개인 슬롯은 그대로 살아 있고 하루 발신 통수도 그대로다."""
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

    # ②-b 오늘 실제로 닫힌 '배'(status/_queue.json) — 업무 시트와 **다른 장부**다(배447).
    #   GM 지적(2026-08-07) '업무 완료도 이상하고' 의 실체: 이 알림은 업무 시트만 봐서
    #   회의 일정 제목을 '업무 완료 1건'으로 냈고, 실제로 닫힌 배 5척은 아예 안 보였다.
    #   GM 결정 = 둘 다 보여준다. 단 **섹션을 갈라** 싣는다 — 섞으면 어느 쪽 숫자인지 모른다.
    done_ships = _fetch_yesterday_queue_done(day=today_str, with_evidence=True)

    # 박스표: 오늘 성과 요약
    table_rows = [
        ("코드·자동화", str(n_commits)),
        ("끝낸 배",     str(len(done_ships))),
        ("일정·회의",   str(len(done_today))),
        ("미완 이월",   str(len(open_cards))),
    ]
    table_str = "\n".join(_count_table(table_rows))

    # 오늘 커밋 목록
    commit_lines = [f"  · {c}" for c in today_commits[:7]]
    if n_commits > 7:
        commit_lines.append(f"  ... 외 {n_commits - 7}건")
    commit_block = "\n".join(commit_lines) if commit_lines else "  (오늘 커밋 없음)"

    # 끝낸 배 목록(배 원장) — 매일 바뀌는 쪽이라 일정보다 먼저 낸다
    ship_lines = [f"  {t}" for t in done_ships[:6]]
    if len(done_ships) > 6:
        ship_lines.append(f"  ... 외 {len(done_ships) - 6}척")
    ship_block = "\n".join(ship_lines) if ship_lines else "  (오늘 닫힌 배 없음)"

    # 일정·회의 목록(업무 시트) — 고정 일정이 섞여 날마다 같을 수 있다
    done_lines = [f"  · {t}" for t in done_today[:4]]
    if len(done_today) > 4:
        done_lines.append(f"  ... 외 {len(done_today) - 4}건")
    done_block = "\n".join(done_lines) if done_lines else "  (오늘 처리 표시된 일정 없음)"

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
        f"{_unified_header('21', '회사', '오늘 마감·내일 정립')}\n"
        f"{_DIVIDER}\n"
        f"   오늘의 성과\n"
        f"{table_str}\n\n"
        f"🏁 오늘 끝낸 배 (작업 원장)\n"
        f"{ship_block}\n\n"
        f"🗓 일정·회의 (업무 시트)\n"
        f"{done_block}\n\n"
        f"🚢 코드·자동화\n"
        f"{commit_block}\n\n"
        f"{_DIVIDER}\n"
        f"🔗 내일 항로점 ({tmr_str} {tmr_wd})\n"
        f"  (업무 시트 미완 → 이월 · 고정 일정 포함)\n"
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
# FUNNEL_EXEC_URL·RECEPTION_EXEC_URL 정의는 collectors.ops_shared(위에서 import).


def _merged_unchecked_names(live: dict, shift: str) -> list[str]:
    """today_live 응답의 uncheckedByShift[shift] — m+f 미체크 항목명 병합.
    필드 없음/빈값 → 빈 리스트(호출부가 안전하게 줄 생략). GM go 2026-07-09, 배선: 지원팀 일일점검.js handleTodayLive.
    정본은 scripts/support_check_summary.merged_unchecked_names — 여기선 위임(soft import,
    상단에서 _SCS_OK 판정). import 실패 시에만 아래 로컬 구현으로 폴백(봇 기동 실패 방지,
    GM 2026-07-23 시토 — 22:30 보고와 로직 단일화)."""
    if _SCS_OK and _scs_merged_unchecked_names is not None:
        try:
            return _scs_merged_unchecked_names(live, shift)
        except Exception:
            pass  # 폴백으로 계속
    bucket = (live.get("uncheckedByShift") or {}).get(shift) or {}
    names = list(bucket.get("m") or []) + list(bucket.get("f") or [])
    return [str(n).strip() for n in names if str(n or "").strip()]


# ── 지원부 점검 미완 독려 경로 = 폐지 (GM 2026-07-23) ──
#   17:00·22:00 슬롯 제거와 함께 전용 함수(run_nudge·_build_nudge_body·
#   _notify_nudge_suppressed·_support_sheet_activity_today)도 호출부 0 이 되어 삭제.
#   독려 정보는 22:30 하루 일과 정리가 담당한다(support_check_summary '🔔 독려 대상').
#   되살리려면 git 이력에서 이 커밋 직전 버전 참조.

# GM 보고봇방 — 억제 알림 전용(실무진 방으로 보내면 소음). canon: telegram_chat_id.
_GM_REPORT_CHAT_ID = int(ENV.get("TELEGRAM_CHAT_ID") or 8254867551)


# 카카오톡 ★부서장 방 이름 — kakao_report_sender.py --only-room 매칭(열린 채팅창 제목과 정확히 일치해야 함).
# GM이 2026-07-18 개설. 창 제목이 다르면 이 값을 실제 제목으로 맞출 것.
KAKAO_DEPTHEAD_ROOM = "★부서장"

# (KAKAO_OPS_DEPT_ROOM 삭제 2026-08-08 — 업무 SSOT 09:30 카톡 ★운영부 발송을 GM 지시로
#  없애면서 쓰는 곳이 사라졌다. 안 쓰는 상수를 남기면 다음 사람이 되살릴 자리로 오해한다.)
# ★2026-08-27 GM 지시로 되살림 — 하루 일과 정리의 '멤버십' 몫이 이 방으로 간다
#  (담당 임정은M). 강습 몫은 ★부서장 그대로. 표기는 kakao_rooms.json 과 같아야 한다.
KAKAO_OPS_DEPT_ROOM = "★운영부"


def _kakao_fail_notify(tag: str, detail: str, room: str = "") -> None:
    """카톡 발송 실패 1회 알림 — 실무진 방이 아니라 GM 업무보고방으로(실무진에겐 소음).

    ★모듈 수준에 둔다(2026-07-31) — 처음엔 run_daily_digest 안 지역 함수로 넣었다가,
    다른 발신(회차 제출누락 알림)에서 부르면 이름을 못 찾는 상태였다. 카톡을 쓰는 곳이
    늘어나는데 실패 알림이 한 곳에만 묶여 있으면 나머지는 조용히 실패한다(약속 L21 관문).
    """
    try:
        send_telegram(
            _GM_REPORT_CHAT_ID,
            "⚠️ 카톡 발송이 안 나갔습니다\n"
            f"▪ {room or KAKAO_OPS_ROOM} · {tag}\n"
            f"   {detail}\n"
            "   PC 카카오톡에서 그 방 창이 열려 있는지 확인해 주세요.\n"
            "   (텔레그램 쪽은 이미 정상 발송됐습니다)",
            parse_mode=None,
        )
    except Exception as e:
        logger.error(f"카톡 실패 알림 자체 실패: {e}")

# 카카오톡 ★운영+시설+지원+주차 방 — 점검현황·종합접수현황 분리 발송 게이트(GM 2026-07-22 go).
# --only-room 매칭이라 방 이름은 열린 채팅창 제목과 정확히 일치해야 함(실측 검증됨,
# scripts/poc-evidence/kakao_send_★운영+시설+지원+주차_*.png). 역롤백(1줄): 아래를 False로.
KAKAO_GO_STREAM2 = True
KAKAO_OPS_ROOM = "★운영+시설+지원+주차"
# 카톡 발신 맨 끝에 한 번만 붙이는 웰리 서명 — report_stream_2/2b 가 각자 머리에 넣던 것과
# 같은 문구(2026-08-15 GM 지시로 카톡 합본 머리글을 한 줄로 줄이며 맨 끝 1회로 이동).
_SENDER_LINE_TAIL = "— 웰페리온 AI 운영지원 '웰리'가 정리해 보내드립니다."


def _is_rest_day(d) -> bool:
    """주말(토·일) 또는 휴관·공휴일(close_days) → 20시 발송."""
    import close_days as _cd  # scripts/ 는 상단에서 sys.path 삽입됨
    return d.weekday() >= 5 or _cd.is_closed(d)


def run_daily_digest(early: bool = False) -> None:
    """3방 하루 일과 정리 알림 오케스트레이터 — 매일 20:00/22:30 둘 다 등록되지만,
    휴일(주말·close_days)은 20:00(early=True)만 실행 / 평일은 22:30(early=False)만 실행
    (GM 2026-07-20, close_days 공휴일 반영 — 기존 요일 고정 mon-fri/sat,sun 을 대체).
    문의 정리는 카카오톡 ★부서장 방에도 추가 발송(GM 2026-07-18). ★중간관리자 방
    알림성 합본(mgmt_notice_queue)은 여기 안 얹는다 — run_mgmt_notice_digest(매일
    17:00)가 분리 발송한다(GM 지시 2026-08-10: 알림성 카톡을 밤으로 미루지 않는다)."""
    from datetime import timezone as _tz3
    now_dt = datetime.now(_tz3.utc) + timedelta(hours=9)
    today = now_dt.strftime("%Y-%m-%d")
    rest_day = _is_rest_day(now_dt.date())
    if rest_day != early:
        logger.info(f"[하루 일과 정리] 게이트 스킵 — early={early} rest_day={rest_day} today={today}")
        return
    label = "[하루 일과 정리]"
    logger.info(f"{label} 시작 — today={today}")

    # 상주 프로세스라 sys.modules 캐시가 기동 시점 소스에 고정된다 — 그날 커밋된 코드를
    #   다음 재기동 전까지 아무 job 도 못 본다. 실사고(2026-08-05): collectors/ops_shared.py 에
    #   reception_elapsed_days 가 10:02 에 추가됐는데 22:31 종합접수방 발송이 캐시된 옛 모듈을
    #   보고 ImportError 로 통째 실패했다(그날 발송 0건). 이 파이프라인이 쓰는 모듈만 다시 읽는다.
    #   collectors 를 먼저 읽어야 그걸 import 하는 report_stream_* 이 새 심볼을 본다.
    #   실패해도 정리는 계속된다(fail-soft — 재읽기 때문에 발송이 멈추면 안 된다).
    import importlib as _importlib
    for _mod_name in sorted(
        (m for m in list(sys.modules)
         if m.startswith("collectors.") or m.startswith("report_stream_")),
        key=lambda m: (not m.startswith("collectors."), m),
    ):
        try:
            _importlib.reload(sys.modules[_mod_name])
        except Exception as _reload_err:
            logger.warning(f"{label} 모듈 재읽기 실패 {_mod_name}: {_reload_err}")

    # ── 스트림 #1 문의 및 컨택&등록 현황 (통일 포맷 msg5618 · 2026-07-22) ────────────────
    # 옛 _build_digest_inquiry(종목별 그룹) 대체. 확정 포맷: report_stream_1_inquiry.
    inquiry_plain = None  # 카카오용 평문(태그·엔티티 없음)
    # 완료 알림 커서 — 아래 발송이 커서를 옮기기 전 상태를 떠 둔다. 같은 회차에서 방별로
    # 다시 만들 때 이 사본을 물려야 "이미 알린 건"으로 지워지지 않는다(2026-08-27).
    _completion_cursor_before = None
    try:
        import report_stream_1_impl as _s1i_pre
        _completion_cursor_before = dict(_s1i_pre._load_completion_state())
    except Exception as e:
        logger.warning(f"{label} 완료 알림 커서 스냅샷 실패(방별 분리 시 완료 알림 누락 가능): {e}")
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

    # ── 강습 담당 배정 독려 — 독립 메시지 (2026-08-05 GM 지시) ──────────────────────
    # 예전엔 stream1(위) 안에 "📌 3일 넘게 담당이 안 정해진 문의" 한 블록으로 섞여 나가
    # 배정 독려가 신규문의·컨택&등록 등 다른 내용에 묻혔다(GM 실측 지적). unassigned_nudge.py
    # 는 그대로 두고(새 스크립트 없음), 여기서 stream1 발송 직후 그것만 담은 메시지로 같은
    # 방(문의알림방=STAFF_CHAT_ID, 목적지 그대로)에 매일 독립 발송한다. 새 예약작업·새 방 없음
    # — 기존 send_telegram 관문 + 기존 run_daily_digest 스케줄만 재사용.
    try:
        import unassigned_nudge as _un
        un_payload = _un.build_payload(today)
        un_text = un_payload["text"]
        if un_text:
            un_ok = send_telegram(DIGEST_INQUIRY_CHAT_ID, un_text, parse_mode=None)
            if un_ok:
                logger.info(f"{label} 담당배정 독려 발송 완료 chat_id={DIGEST_INQUIRY_CHAT_ID} "
                            f"(선발 {len(un_payload['selected'])}건/미배정 {len(un_payload['eligible'])}건)")
                _un._record_sent(un_payload["selected"], un_payload["notified"], un_payload["today"],
                                  len(un_payload["eligible"]), len(un_payload["dormant"]))
            else:
                logger.error(f"{label} 담당배정 독려 발송 실패 chat_id={DIGEST_INQUIRY_CHAT_ID}")
        else:
            logger.info(f"{label} 담당배정 독려 — 오늘 보낼 신규 대상 없음(가드/미배정 0건)")
    except Exception as e:
        logger.error(f"{label} 담당배정 독려 예외: {e}")

    # ── 24시간 SLA 위반 — 카카오 ★부서장 방 (2026-08-05 GM 지시) ──────────────────
    # GM: "8월부터는 무조건 철저하게 관리해줘야해 담당자 24시간 내 미배정 및 컨택
    # 안되었을 시에는 카카오톡 부서장방에 전달." 위 배정 독려(텔레그램·상한없음)와 다른
    # 층 — 대상 8/1 이후 신규만, 문턱 24시간, 목적지 카카오뿐(텔레그램 안 건드림). 새
    # 스크립트·새 예약작업·새 방 없음 — unassigned_nudge.py 가 이미 읽는 데이터에 얹은
    # 판정을 기존 카카오 관문(kakao_report_sender.py --message --only-room)으로만 보낸다.
    # 도배 방지: run_daily_digest 자체가 하루 1회 게이트(위 rest_day 분기)라 별도 가드
    # 없이도 하루 1회. 위반 0건이면 build_sla_alert_text가 빈 문자열 — 발송 자체를 스킵.
    # ── 멤버십 문의 담당 자동 배정 (GM 지시 2026-08-14) ────────────────────────────
    #   GM: "멤버십은 담당자가 임정은M 밖에 없을텐데? 자동으로 배정해줘."
    #   경보를 만들기 전에 먼저 채운다 — 그래야 '담당없음' 으로 잘못 실려 나가지 않는다.
    #   대상 0건이면 GAS 쓰기 자체가 없다(조회 1회로 끝).
    try:
        _asg = _un.assign_member_owners(apply=True)
        if _asg:
            _bad = [x for x in _asg if not x.get("ok")]
            logger.info(f"{label} 멤버십 담당 자동배정 {len(_asg) - len(_bad)}건 성공 · {len(_bad)}건 실패")
    except Exception as e:
        logger.error(f"{label} 멤버십 담당 자동배정 예외: {e}")

    # ★2026-08-18 GM 결정(배670) — 아래서 계산만 하고 보내지 않는다. ★부서장 방에
    #   22:31 미배정(이 블록)·22:32 문의 정리(아래 inquiry_plain)가 1분 간격 두 통으로
    #   따로 갔었다(실측). 같은 방·같은 목적(문의 도메인)이라 한 통으로 묶어 아래
    #   inquiry_plain 발송 지점에서 함께 보낸다 — sla_violations/sla_text 만 여기서 만든다.
    sla_violations: list = []
    sla_text = ""
    try:
        sla_violations = _un.collect_sla_violations()
        sla_text = _un.build_sla_alert_text(sla_violations)
        # 2026-08-15 GM 지시(중복 알림 정리) — 변화 없는 재독촉을 끊는다. 실측: 8/10~14
        #   같은 명단이 "9일째"→"13일째"로 숫자만 오르며 5번 독촉, 움직임 0건. 직전 발신
        #   대비 신규·해소가 있을 때만 보내고, 전체 명단은 월요일에만 재노출(unassigned_nudge
        #   .sla_alert_gate — 정본은 그 함수, 여기서 다시 판정하지 않는다).
        if sla_text and not _un.sla_alert_gate(sla_violations):
            logger.info(f"{label} 24h SLA 위반 {len(sla_violations)}건 — 직전 발신과 변화 없음, 발송 SKIP")
            sla_text = ""
        elif not sla_text:
            logger.info(f"{label} 24h SLA 위반 0건")
    except Exception as e:
        logger.error(f"{label} 24h SLA 위반 집계 예외: {e}")
        sla_violations, sla_text = [], ""

    # ── 60일 무응답 카톡 발송 삭제 (GM 지시 2026-08-08 "이거 보내지마") ──
    #   GM 원문: "이거 부서장에 보내는건데 이거 보내지마 일단 알림한장에서도 삭제해놔
    #             시포한테 전달하긴했는데 하지말라했는데 오늘 또 나갔네."
    #   ▸501건을 매일 5건씩 회전 노출하는 구조였다. 가장 오래된 건이 218일째라
    #     회전으로는 끝이 안 보이고, 부서장이 매일 같은 종류를 받아 곧 안 읽게 된다.
    #   ▸게이트를 꺼서 남기지 않고 지운다 — 꺼둔 코드는 죽은 코드가 되고 누가 다시
    #     켠다(약속 L21). 되살릴 일이 생기면 이 커밋을 되돌리면 된다.
    #   ▸판정 함수(unassigned_nudge.collect_noresponse 등)는 남긴다 — 시포가 화면에서
    #     쓰는 집계이고, 없애야 하는 것은 "매일 부서장 방으로 밀어 넣는 행위"다.

    # ── 스트림 #2 점검+이슈 현황 (점검현황방 단독 · 2026-07-22) ─────────────────────
    s2_msg = None  # 카톡 ★운영+시설+지원+주차 재사용(아래) — 빌드 실패 시 None 유지, 카톡 스킵.
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
    s2b_msg = None  # 카톡 ★운영+시설+지원+주차 재사용(아래) — 빌드 실패 시 None 유지, 카톡 스킵.
    try:
        import report_stream_2b_reception as _s2b
        s2b_msg = _s2b.build_digest(today)
        success = send_telegram(DIGEST_RECEPTION_CHAT_ID, s2b_msg)
        if success:
            # ★2026-08-05 시토 — 처리완료 통보 커서는 '실제로 나간 뒤에만' 전진시킨다.
            #   전에는 build_digest() 안에서 곧바로 파일에 적어, 발송이 실패해도 커서가
            #   움직여 그 완료건들이 영영 통보되지 않았다(조용히 사라지는 사고).
            _s2b.commit_completion_cursor()
            logger.info(f"{label} 종합접수방 발송 완료 chat_id={DIGEST_RECEPTION_CHAT_ID} (stream2b)")
        else:
            logger.error(f"{label} 종합접수방 발송 실패 chat_id={DIGEST_RECEPTION_CHAT_ID} — 완료통보 커서 미전진(다음 회차 재통보)")
    except Exception as e:
        logger.error(f"{label} 종합접수방(stream2b) 예외: {e}")

    # ── 카카오톡 ★운영+시설+지원+주차 — 점검현황+종합접수현황 합본 1통 (GM 2026-07-22 go) ──
    # 텔레그램 본문(s2_msg/s2b_msg) 그대로 재사용(중복 조립 금지). 텔레그램은 방이 서로 달라
    # (점검현황방/종합접수방) 2통 그대로 두지만, 카톡은 같은 방(KAKAO_OPS_ROOM)으로 나가
    # 제목이 완전히 같은 [하루 일과 정리] 2통이 연달아 뜨고 있었다(2026-08-15 GM 지시,
    # 실측 22:32 연속 2통×5일=10통). 부문 소제목으로 갈라 한 통으로 합친다 — 내용 삭제 없음.
    # ★2026-08-15 GM 추가 지시("헤드값을 변경해줘, 간단하게 타이틀로 [오늘 하루 정리]
    #   이런식으로") — 3줄짜리 머리글(제목·부제·웰리 서명)을 한 줄 타이틀로 줄인다. 부문
    #   구분은 머리글이 아니라 본문 소제목(🏗 점검/📮 종합접수)으로 옮기고, 웰리 서명은
    #   맨 끝에 한 번만 둔다. 실패해도 텔레그램 발송(위)은 이미 완료된 상태이므로 GM은
    #   텔레그램으로 항상 현황을 받는다.
    # ★한계(정직 표기): 카카오 발송은 PC 카톡 앱 UI자동화(kakao_report_sender.py)에 의존해
    # 트레이 최소화·포커스 경합 등으로 실패할 수 있다(배9423, 07-22 아침 09:30 3방 발송 실패
    # 전례). 주경로=카톡 창을 미리 열어둔 상태 유지. 역롤백(1줄): KAKAO_GO_STREAM2 = False.
    if KAKAO_GO_STREAM2:
        _kakao_sender = REPO_ROOT / "scripts" / "kakao_report_sender.py"
        _kakao_env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")

        def _send_ops_kakao(text: str, tag: str) -> None:
            try:
                proc = subprocess.run(
                    [sys.executable, str(_kakao_sender), "--message", text, "--only-room", KAKAO_OPS_ROOM],
                    cwd=str(REPO_ROOT), capture_output=True, text=True,
                    encoding="utf-8", errors="replace", env=_kakao_env, timeout=180,
                )
                tail = (proc.stdout or "").strip().splitlines()[-1:] or ["(출력없음)"]
                logger.info(f"{label} 카톡 {KAKAO_OPS_ROOM}({tag}) 발송: {tail[0]}")
                # ★2026-07-31 웰리 — 실패를 조용히 넘기지 않는다.
                #   카톡 발송은 PC 카톡 앱 UI 자동화라 창이 닫혀 있으면 그냥 안 나간다. 지금까지는
                #   로그에만 남아서, 실무진 방에 아무것도 안 갔는데 아무도 몰랐다(GM 이 다음 날 물어야
                #   드러났다). 실패했을 때만 GM 업무보고방에 한 줄 — 성공하면 완전 침묵.
                if proc.returncode != 0:
                    _kakao_fail_notify(tag, tail[0])
            except Exception as e:
                logger.error(f"{label} 카톡 {KAKAO_OPS_ROOM}({tag}) 발송 예외: {e}")
                _kakao_fail_notify(tag, str(e)[:120])

        _ops_title = f"🌙 오늘 점검·접수 정리 {now_dt.month}/{now_dt.day}({_WEEKDAY_KOR[now_dt.weekday()]})"

        # ★2026-08-18 GM 결정(배670 · 재설계안 확정) — 카톡은 텔레그램 전문(s2_msg/s2b_msg)을
        # 그대로 안 쓴다. 4,559자(회차별 일지·측정값 20줄·미처리 적체 전체목록)를 실측 지적받아
        # 800자 상한 압축본으로 간다. 회차별 일지·전체 목록은 링크(체계 페이지)로 뺀다 —
        # 텔레그램 쪽(위 s2_msg/s2b_msg 발송)은 전문 그대로라 정보 손실 없음.
        try:
            check_compact = _s2.build_kakao_digest(today) if s2_msg else ""
        except Exception as e:
            logger.error(f"{label} 카톡 압축본(점검) 빌드 예외: {e}")
            check_compact = ""
        try:
            reception_compact = _s2b.build_kakao_digest(today) if s2b_msg else ""
        except Exception as e:
            logger.error(f"{label} 카톡 압축본(접수) 빌드 예외: {e}")
            reception_compact = ""

        if check_compact or reception_compact:
            body = "\n".join(p for p in (check_compact, reception_compact) if p)
            merged = f"{_ops_title}\n\n{body}\n\n{_SENDER_LINE_TAIL}"
            if len(merged) > 900:
                logger.warning(f"{label} 카톡 {KAKAO_OPS_ROOM} 압축본이 900자 초과({len(merged)}자) — 800자 상한 재검토 필요")
            _send_ops_kakao(merged, "점검현황+종합접수현황(압축)")
        else:
            logger.info(f"{label} 카톡 {KAKAO_OPS_ROOM} SKIP — 압축본 둘 다 없음(빌드 실패)")

        # ── 강습·업장(팀) 기한초과분만 ★부서장 방으로 (GM 지시 2026-08-18 · 배696) ──
        #   위 합본은 이제 강습·업장을 뺀 몫이다(_aging_block scope="ops"). 그 몫만 여기서
        #   따로 보낸다 — 같은 목록을 두 방에 통째로 보내지 않는다(중복 발신 금지).
        #   없는 날은 빈 문자열이 와서 아무것도 안 나간다.
        try:
            import report_stream_2b_reception as _s2b_lesson
            _lesson_msg = _s2b_lesson.build_lesson_digest(today)
            if _lesson_msg:
                _room_lesson = _s2b_lesson._INTAKE_ROOM_LESSON
                proc = subprocess.run(
                    [sys.executable, str(_kakao_sender), "--message", _lesson_msg,
                     "--only-room", _room_lesson],
                    cwd=str(REPO_ROOT), capture_output=True, text=True,
                    encoding="utf-8", errors="replace", env=_kakao_env, timeout=180,
                )
                tail = (proc.stdout or "").strip().splitlines()[-1:] or ["(출력없음)"]
                logger.info(f"{label} 카톡 {_room_lesson}(강습·업장 접수) 발송: {tail[0]}")
                if proc.returncode != 0:
                    _kakao_fail_notify("강습·업장 접수", tail[0])
            else:
                logger.info(f"{label} 강습·업장 기한초과 0건 — ★부서장 발신 없음")
        except Exception as e:
            logger.error(f"{label} 강습·업장 접수 발송 예외: {e}")
    else:
        logger.info(f"{label} 카톡 {KAKAO_OPS_ROOM} SKIP (KAKAO_GO_STREAM2=False)")

    # ── 오늘 완료된 운영부 업무 — 하루 일과 정리에도 포함 (GM 2026-08-06 "완료 알림은
    #   완료 시 즉각 1회, 하루 일과 정리에서도 꼭 체크하고 정리해서 보내줘야해") ──────
    #   (즉각 알림 자체는 2026-08-18 삭제 — 배670, 위 job 정의부 주석 참조. 이 밤 절은
    #   그대로 유지) build_daily_done_section 으로 '오늘' 완료건 전체를 매번 다시
    #   모은다(중복억제 없음, GM 지시). 발송처 = ★운영부(send_ops_digest.TARGET_ROOM).
    #   같은 킬스위치(status/ops_digest_send.json)를 공유해 GM이 그
    #   기능을 끄면 여기도 같이 꺼진다(새 킬스위치 안 만듦).
    try:
        import send_ops_digest as _od
        if _od.kill_switch_enabled():
            # 실무진 피드백 '처리완료' 건도 같은 한 통에 붙인다(GM 지시 2026-08-24 —
            # 하루 1회 묶음). 발신을 두 번으로 늘리지 않는다.
            _parts = [p for p in (
                _od.build_daily_done_section(_od._fetch_todo_rows(), today),
                _od.build_daily_feedback_done_section(today),
            ) if p]
            daily_done_msg = "\n\n".join(_parts)
            if daily_done_msg:
                sender = REPO_ROOT / "scripts" / "kakao_report_sender.py"
                proc = subprocess.run(
                    [sys.executable, str(sender), "--message", daily_done_msg, "--only-room", _od.TARGET_ROOM],
                    cwd=str(REPO_ROOT), capture_output=True, text=True,
                    encoding="utf-8", errors="replace", timeout=180,
                    env=dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1"),
                )
                tail = (proc.stdout or "").strip().splitlines()[-1:] or ["(출력없음)"]
                logger.info(f"{label} 카톡 {_od.TARGET_ROOM}(오늘 완료건) 발송: {tail[0]}")
                if proc.returncode != 0:
                    _kakao_fail_notify("오늘 완료된 운영부 업무", tail[0], room=_od.TARGET_ROOM)
            else:
                logger.info(f"{label} 오늘 완료된 운영부 업무 0건 — 카톡 발송 없음")
        else:
            logger.info(f"{label} 완료건 정리 SKIP — ops_digest_send 킬스위치 OFF")
    except Exception as e:
        logger.error(f"{label} 오늘 완료건 카톡 발송 예외: {e}")

    # 카카오톡 ★부서장 방에도 문의 정리 발송 (GM 2026-07-18 · best-effort).
    # ★2026-08-18 GM 결정(배670) — 문의 정리 + 24h SLA 위반(sla_text, 위에서 계산분)을
    #   한 통으로 묶어 보낸다. 종전엔 22:31 미배정 557자·22:32 문의 639자가 1분 간격
    #   두 통이었다(실측) — 같은 방·같은 문의 도메인이라 병합.
    # ★2026-08-27 GM 지시 — 멤버십과 강습을 한 통에 섞어 보내니 각 담당이 자기 것을 못 찾고
    #   컨택이 밀린다(실측: 멤버십 미컨택 11건 중앙값 13.9일 vs 강습 5~7일). 방을 가른다.
    #   강습(성인+유소년) → ★부서장(강습 팀장) / 멤버십 → ★운영부(담당 임정은M).
    #   완료 알림 커서는 회차 안에서 공유한다 — 앞선 문의알림방 발송이 이미 커서를 옮겼으므로
    #   그 전 상태 사본을 두 통에 똑같이 물려 같은 회차에 같은 내용이 나가게 한다.
    try:
        import report_stream_1_impl as _s1i
        import re as _re_s2, html as _html_s2
        _cursor = dict(_completion_cursor_before or _s1i._load_completion_state())

        def _scoped_plain(scope: str) -> str:
            raw = _s1i.build_digest(today, persist_completion=False, scope=scope,
                                    completion_state=dict(_cursor))
            return _re_s2.sub(r"<[^>]+>", "", _html_s2.unescape(raw))

        room_payload = [
            (KAKAO_DEPTHEAD_ROOM, "강습",
             _scoped_plain("lesson"),
             _un.build_sla_alert_text([v for v in sla_violations if "강습" in v["type"]])
             if sla_text else ""),
            (KAKAO_OPS_DEPT_ROOM, "멤버십",
             _scoped_plain("membership"),
             _un.build_sla_alert_text([v for v in sla_violations if v["type"] == "멤버십"])
             if sla_text else ""),
        ]
    except Exception as e:
        logger.error(f"{label} 문의 정리 방별 분리 실패 — 종전 병합본으로 발송: {e}")
        room_payload = [(KAKAO_DEPTHEAD_ROOM, "문의+SLA", inquiry_plain or "", sla_text)]

    _sent_any = False
    for _room, _tag, _body, _sla in room_payload:
        parts = [p for p in (_body, _sla) if p]
        if not parts:
            logger.info(f"{label} 카톡 {_room}({_tag}) 보낼 내용 없음 — 발송 없음")
            continue
        try:
            sender = REPO_ROOT / "scripts" / "kakao_report_sender.py"
            env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
            proc = subprocess.run(
                [sys.executable, str(sender), "--message", "\n\n".join(parts), "--only-room", _room],
                cwd=str(REPO_ROOT), capture_output=True, text=True,
                encoding="utf-8", errors="replace", env=env, timeout=180,
            )
            tail = (proc.stdout or "").strip().splitlines()[-1:] or ["(출력없음)"]
            logger.info(f"{label} 카톡 {_room}({_tag}) 발송: {tail[0]}")
            # ★2026-08-05 시토 수리 — 위 SLA·60일 무응답과 같은 구멍(returncode 미확인).
            if proc.returncode != 0:
                _kakao_fail_notify(f"문의 정리+SLA({_tag})", tail[0], room=_room)
            else:
                _sent_any = True
        except Exception as e:
            logger.error(f"{label} 카톡 {_room}({_tag}) 발송 예외: {e}")
    if _sent_any and sla_violations:
        _un.record_sla_alert_sent(sla_violations)  # 발송 성공 뒤에만 커서 전진


def run_mgmt_notice_digest() -> None:
    """★중간관리자 알림성 합본 — 매일 17:00 낮 시간 단독 발송(배499 큐 그대로 재사용).
    처음엔 run_daily_digest(평일 22:30/휴일 20:00) 안에 얹혀 밤에 나갔으나, GM 지시
    2026-08-10 "갑자기 낮시간 카톡 자동화 중단 발송은 밤으로 이동하면 안되" 로 낮
    시간(17:00)으로 분리했다. 알림성 건은 mgmt_notice_queue(scripts/mgmt_notice_queue.py)
    에 하루 동안 쌓이고 여기서 한 번에 팝해 보낸다. 답요구 건·3-트리거(💰🔒🚫) 긴급건은
    그 모듈 add()가 category 가드로 거부해 여기 안 섞인다 — 그런 건 즉시 개별 발송 유지."""
    label = "[★중간관리자 알림성 합본]"
    today = datetime.now().strftime("%Y-%m-%d")
    try:
        import mgmt_notice_queue as _mnq
        import send_ops_digest as _od3
        notice_items = _mnq.pop_today(today)
        notice_text = _mnq.build_digest_text(notice_items, today)
        if notice_text:
            sender = REPO_ROOT / "scripts" / "kakao_report_sender.py"
            proc = subprocess.run(
                [sys.executable, str(sender), "--message", notice_text, "--only-room", _od3.RELAY_ROOM],
                cwd=str(REPO_ROOT), capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=180,
                env=dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1"),
            )
            tail = (proc.stdout or "").strip().splitlines()[-1:] or ["(출력없음)"]
            logger.info(f"{label} 카톡 {_od3.RELAY_ROOM}({len(notice_items)}건) 발송: {tail[0]}")
            if proc.returncode != 0:
                _kakao_fail_notify("알림성 합본", tail[0], room=_od3.RELAY_ROOM)
        else:
            logger.info(f"{label} 오늘 큐 0건, 발송 없음")
    except Exception as e:
        logger.error(f"{label} 예외: {e}")


# (완료 즉시 알림 10분 주기 삭제 2026-08-18 GM 결정 · 배670 재설계안) ──────────────
#   ★운영부가 매일 4통(아침정리+매출이미지+채움보드+완료알림)을 받던 것을 줄이는 재편의
#   일부. 완료알림은 다음 날 아침 「어제 정리」의 「✅ 어제 완료 N건」(ops_daily_digest.py
#   build_work_block)이 이미 같은 내용을 싣고 있어 순수 중복이었다(실측 확인). run_daily_digest
#   의 밤 「오늘 완료된 운영부 업무」 절(build_daily_done_section)은 그대로 둔다 — 그건
#   이 10분 즉시알림과 다른 별개 발신이다. 되살릴 일이 있으면 이 커밋을 되돌리면 된다.


# ── 운영부 주간 보고 초안 — ★중간관리자 방 (GM 2026-08-06 "표준 양식은 의미없고,
#   보고 내용을 중간관리자 방에다가 보고할 수 있거나 정리할 수 있게 도와줬으면") ──────
#   빈 양식표는 아무도 안 채운다 — 이경연 실장이 손으로 안 써도 초안이 나가고, 실장은
#   고치거나 그대로 쓴다. 금요일 17:00을 고른 이유: 그 주가 끝나기 전, 실장이 아직
#   자리에 있는 시간대에 그 주 진행상황을 정리해 두면 다음 주 계획 전에 검토할 여유가
#   있다(월요일 발송이면 '지난주' 데이터를 다시 조사해야 해서 실장이 손볼 타이밍을 놓친다).
#   새 예약작업·새 발신기 없음(약속 L21) — 상주 스케줄러 잡 하나 + kakao_report_sender.py
#   --only-room 재사용. 판정 로직(운영부 담당자·완료건)은 send_ops_digest.py 함수 재사용
#   (약속 L01). 킬스위치 = ops_digest_send.json 공유(새 킬스위치 안 만듦).
# ── GM 개인 하루 체크인 (매일 21:30 · 업무보고방) — GM 승인 2026-08-08 A안 ──────────
#   왜 텔레그램인가: G1 「오늘 체크인」은 칸이 11개라 매일 페이지를 열어야 했고 이틀 만에
#   끊겼다(2026-05-26·05-27 뒤 73일 공백). 「GM의 일요일」이 계속 도는 이유는 사람이 하는
#   일이 사진 한 장뿐이기 때문이다 — 같은 구조로 옮긴다. 봇이 묻고 GM 은 버튼만 누른다.
#   새 파일·새 저장소 없음: status/gm_personal_routine.json 을 그대로 쓴다(G1 페이지와 같은 정본).
#   21:30 을 고른 이유 = 22:00 취침 안내(개인 슬롯) 앞. 하루가 끝난 뒤이면서 잠들기 전이다.
#   안 누르면 그날은 조용히 빈다 — 재촉 알림을 만들지 않는다(점수·심판이 아니라 거울).
#   받는 방: .env TELEGRAM_PERSONAL_CHAT_ID 가 있으면 그 방(개인 전용·실측 -5074392439), 없으면 업무보고방.
#   GM 지적(2026-08-08): "이런 건 개인적인 부분이라 업무보고방이 아니라 개인한테." 업무보고방은
#   하루 종일 업무가 흐르는 곳이라 개인 기록이 그 사이에 묻힌다. 키가 비면 지금처럼 동작한다(회귀 0).
def _checkin_chat_id() -> str:
    return str(ENV.get("TELEGRAM_PERSONAL_CHAT_ID") or _GM_REPORT_CHAT_ID)


def run_gm_checkin(weekly: bool = False) -> None:
    """기본=저녁 확인(버튼) · weekly=한 주 카드. (아침 「오늘 하나씩」은 06:00 하루시작 카드에
    _checkin_morning_block() 이 흡수 — 별도 morning 분기 없음. 업무 브리핑은 run_gm_morning_brief.)
    """
    label = "[GM 개인 체크인]"
    try:
        import gm_checkin as _ck
        from tg_outbound_log import send as _send
        token = ENV.get("TELEGRAM_BOT_TOKEN") or ""
        if not token:
            logger.warning(f"{label} 토큰 없음 — 건너뜀")
            return
        chat = _checkin_chat_id()
        if weekly:
            ok = _send(token, chat, _ck.week_card(), source="gm_checkin_week")
            logger.info(f"{label} 한 주 카드 발송 ok={ok} chat={chat}")
            return
        # 저녁은 설문 첫 문항 하나만 보낸다 — 나머지는 같은 메시지를 갈아 끼우며 진행한다
        # (GM 2026-08-08 "Survey 처럼"). 버튼 10개를 한 화면에 깔던 옛 카드는 폐기.
        # 취침 안내·명언은 마지막 마무리 화면 꼬리로 옮겼다(build_step 마지막 단계).
        step = _ck.build_step(0)
        ok = _send(token, chat, step["text"], source="gm_checkin",
                   extra={"reply_markup": json.dumps(step["markup"], ensure_ascii=False)})
        logger.info(f"{label} 저녁 설문 1문항 발송 ok={ok} chat={chat}")
    except Exception as e:
        logger.warning(f"{label} 실패: {e}")


# ── 08:00 GM 업무 브리핑 (월~토 · 나의하루 방) — 배514 미배선 해소, GM 지시 2026-08-10 ──
#   gm_checkin.schedule_lines() 는 있었는데 그걸 부르는 08:00 잡이 저장소에 0건이었다(죽은
#   코드) — 이 잡이 그걸 실제로 쓴다. 전사일정+GM업무(월간 「GM 직접」)+업무SSOT 김남욱 담당+
#   회장님 보고건 4소스를 gm_checkin.build_morning_brief() 가 4묶음으로 정직하게 낸다.
#   받는 방 = 개인 나의하루(TELEGRAM_PERSONAL_CHAT_ID) — ceo_morning_pipeline.py 의 08:00
#   통합브리프(업무보고방·회사 전체용)와는 방·내용이 다르므로 "08시 중복 발송 없음" 원칙과
#   충돌하지 않는다(위 파일 헤더 주석 참조). chat_id 인자는 시험 발송용(기본=나의하루 방).
def run_gm_morning_brief(chat_id: str | None = None) -> None:
    label = "[GM 아침 브리핑]"
    try:
        import gm_checkin as _ck
        from tg_outbound_log import send as _send
        token = ENV.get("TELEGRAM_BOT_TOKEN") or ""
        if not token:
            logger.warning(f"{label} 토큰 없음 — 건너뜀")
            return
        chat = chat_id or _checkin_chat_id()
        text = _ck.build_morning_brief()
        ok = _send(token, chat, text, source="gm_morning_brief")
        logger.info(f"{label} 발송 ok={ok} chat={chat}")
    except Exception as e:
        logger.warning(f"{label} 실패: {e}")
    # 부문별 배 목록(배편)은 「나의하루」에 안 보낸다 — GM 지시 2026-08-12 "하루 방은 개인것만".
    # 계산은 그대로 두고 받는 방만 AI 진행현황방으로 옮긴다.
    if chat_id is None:
        _run_dept_block_to_ai_room()
    # ── 08:00 카톡 「김남욱」 개인방 짧은 일정판 삭제 (GM 지시 2026-08-18 · 배691) ──
    # GM 원문: "하루(GM 개인)으로 오늘의 업무 아침 브리핑과 카카오톡 오늘 일정 브리핑 —
    #          일정없어도 매일 발신이랑 중복이니까 병합하면 될듯."
    # 위 텔레그램 브리핑(build_morning_brief)이 같은 원천(전사일정 오늘분)을 이미
    # 「오늘 잡힌 일정」 절로 낸다 — 카톡 사본은 같은 것을 한 번 더 알리는 중복이었고,
    # 일정이 없는 날에도 '오늘 잡힌 일정은 없습니다' 한 통이 따로 나갔다.
    # ▸게이트로 꺼두지 않고 지운다 — 꺼둔 코드는 죽은 코드가 된다(약속 L21).
    #   되살릴 일이 생기면 이 커밋을 되돌린다.


def _run_dept_block_to_ai_room() -> None:
    """부문별 오늘 핵심(배편) → AI 진행현황방. 발송 관문은 기존 notify_gm_progress 하나만 쓴다."""
    label = "[부문별 배편]"
    try:
        import gm_checkin as _ck
        from notify_gm_progress import resolve_room  # 목적지 해소도 그 관문이 갖고 있다
        from tg_outbound_log import send as _send
        text = _ck.build_dept_block()
        if not text:
            logger.info(f"{label} 보낼 것 없음 — 생략")
            return
        chat = resolve_room()
        if not chat:
            logger.warning(f"{label} AI 진행현황방 chat_id 해소 실패 — 생략")
            return
        ok = _send(ENV.get("TELEGRAM_BOT_TOKEN") or "", chat, text, source="dept_block_ai_room")
        logger.info(f"{label} 발송 ok={ok} chat={chat}")
    except Exception as e:
        logger.warning(f"{label} 실패: {e}")


# ── 미팅 30분 전 리마인드 → 텔레그램 「하루(개인)」 방 (배451 · GM 확정 2026-08-07 ·
#   목적지 이전 2026-08-18 배691) ────────────────────────────────────────────────
#   GM 원문(2026-08-07): "미팅 30분 전에만 김남욱 방에다가 링크까지 포함해서 전달해주면 내가
#   리마인드 되어서 놓칠 일이 없을 듯." (중간관리자 방 사전 공유는 사람이 그때그때 — 자동화 대상 아님)
#   GM 원문(2026-08-18): "미팅 30분전 리마인드도 하루(GM 개인) 텔레그램으로 병합" —
#   시각 트리거·문구는 그대로 두고 **목적지만** 카톡 개인방에서 텔레그램 하루방으로 옮긴다.
#   이로써 GM 개인 카톡방으로 나가는 자동 발신은 0건이 된다.
#
#   ★새 예약작업·새 감시기·새 파일 0 (약속 L21). 이미 상주하는 이 스케줄러에 5분 주기 절 하나,
#     일정 읽기는 gm_checkin(08:00 브리핑이 쓰는 그 함수), 발신은 kakao_report_sender 관문 그대로.
#   ★중복 발신: 관문(kakao_report_sender)이 방+내용 서명으로 2시간 창 안 재발신을 이미 막는다.
#     그 위에 프로세스 안 기억을 하나 더 둔다(같은 회차에 subprocess 를 두 번 띄우지 않으려고).
#   ★시각 없는 종일 일정은 계산할 수 없다 — 빼되 **뺐다는 사실을 로그에 남긴다**(조용한 누락 금지).
_MEETING_REMIND_SENT: set = set()
_MEETING_REMIND_LEAD_MIN = 30
_MEETING_REMIND_TOLERANCE = 3      # 5분 주기라 정확히 30분에 걸리지 않는다 — 27~33분 사이면 발신


def _run_meeting_reminder() -> None:
    label = "[미팅 30분전]"
    try:
        import gm_checkin as _ck
        from tg_outbound_log import send as _send
        token = ENV.get("TELEGRAM_BOT_TOKEN") or ""
        if not token:
            logger.warning(f"{label} 토큰 없음 — 건너뜀")
            return
        chat = _checkin_chat_id()
        now = datetime.now()
        day = now.strftime("%Y-%m-%d")
        items, ok = _ck._load_schedule_items_ex()
        if not ok:
            logger.warning(f"{label} 전사일정을 못 읽음 — 이번 회차 건너뜀(0건과 구분)")
            return
        pairs = _ck._filter_today_items(items, day)          # [(HH:MM, 제목)] · GM 담당분만
        no_time = [t for hhmm, t in pairs if not hhmm]
        if no_time:
            logger.info(f"{label} 시각 없는 일정 {len(no_time)}건 제외(계산 불가): {', '.join(no_time[:3])}")
        for hhmm, title in pairs:
            if not hhmm:
                continue
            try:
                hh, mm = [int(x) for x in hhmm.split(":")]
            except Exception:
                continue
            start = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
            lead = (start - now).total_seconds() / 60.0
            if abs(lead - _MEETING_REMIND_LEAD_MIN) > _MEETING_REMIND_TOLERANCE:
                continue
            key = f"{day}|{hhmm}|{title}"
            if key in _MEETING_REMIND_SENT:
                continue
            text = (
                f"⏰ 30분 뒤 미팅 — {hhmm}\n"
                f"{title}\n\n"
                f"GM업무 화면\n"
                f"https://wellperion-cao.github.io/wellperion-automation/coo/chairman/GM%EC%97%85%EB%AC%B4.html"
            )
            if _send(token, chat, text, source="gm_meeting_reminder"):
                _MEETING_REMIND_SENT.add(key)
                logger.info(f"{label} 발송 {hhmm} {title} → 하루방({chat})")
            else:
                logger.error(f"{label} 발송 실패 {hhmm} {title} → 하루방({chat})")
    except Exception as e:
        logger.error(f"{label} 예외: {e}")


# ── 20:30 GM 저녁 정리 카드(월~토 · 나의하루 방) — GM 지시 2026-08-10 ──────────────
#   08:00 업무 브리핑(할 일)의 짝 — 저녁엔 오늘 worklog GM지시 항목을 ok/warn ref 로 짝지어
#   끝낸 것·아직 남은 것 체크 카드로 낸다(gm_checkin.build_evening_recap). 21:00 저녁 끼니슬롯·
#   22:00 저녁 설문과 겹치지 않게 20:30 을 쓴다. chat_id 인자는 시험 발송용.
def run_gm_evening_recap(chat_id: str | None = None) -> None:
    label = "[GM 저녁 정리]"
    try:
        import gm_checkin as _ck
        from tg_outbound_log import send as _send
        token = ENV.get("TELEGRAM_BOT_TOKEN") or ""
        if not token:
            logger.warning(f"{label} 토큰 없음 — 건너뜀")
            return
        chat = chat_id or _checkin_chat_id()
        step = _ck.build_evening_recap()
        extra = {"reply_markup": json.dumps(step["markup"], ensure_ascii=False)} if step.get("markup") else None
        # 퇴근인사·저녁루틴·명언은 개인 몫이라 하루 방(여기)에 붙인다 — 21시 업무보고방 본문에서
        # 옮겨 온 것이다(배541 · 2026-08-12). GM 정의: 하루 방은 업무 제외, 업무관리는 개인 제외.
        # 배10011(2026-07-24)로 18시 단독 발신을 접으면서 21시에 얹었던 것이 그 정의보다 앞선다.
        text = step["text"].rstrip() + "\n\n" + _18_evening_lines().rstrip()
        ok = _send(token, chat, text, source="gm_evening_recap", extra=extra)
        logger.info(f"{label} 발송 ok={ok} chat={chat}")
    except Exception as e:
        logger.warning(f"{label} 실패: {e}")


# ── 시점별 체크(끼니·운동) 4슬롯 (09:00·13:30·16:30·21:00 · 개인 방) — GM 요청 2026-08-09 ──
#   기존 22:00 저녁 설문(run_gm_checkin)은 하루가 끝난 뒤 5토막·기분을 묻는다. 이 4슬롯은
#   그때그때 끼니·운동만 묻는다 — 겹치지 않는다. 시각·항목 정본 = gm_checkin.SLOTS.
def run_gm_checkin_slot(slot_id: str) -> None:
    label = f"[GM 체크인·{slot_id}]"
    try:
        import gm_checkin as _ck
        from tg_outbound_log import send as _send
        token = ENV.get("TELEGRAM_BOT_TOKEN") or ""
        if not token:
            logger.warning(f"{label} 토큰 없음 — 건너뜀")
            return
        chat = _checkin_chat_id()
        step = _ck.build_slot(slot_id)
        extra = {"reply_markup": json.dumps(step["markup"], ensure_ascii=False)} if step.get("markup") else None
        ok = _send(token, chat, step["text"], source=f"gm_checkin_{slot_id}", extra=extra)
        logger.info(f"{label} 발송 ok={ok} chat={chat}")
    except Exception as e:
        logger.warning(f"{label} 실패: {e}")


def run_weekly_ops_report() -> None:
    try:
        import send_ops_digest as _od
    except Exception as exc:
        logger.warning(f"[주간 보고] send_ops_digest import 실패: {exc}")
        return
    if not _od.kill_switch_enabled():
        logger.info("[주간 보고] 킬스위치 OFF(ops_digest_send.json) — 생략")
        return
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        draft = _od.build_weekly_report_draft(_od._fetch_todo_rows(), today)
        if not draft:
            logger.info("[주간 보고] 이번 주 진행/멈춤/완료 없음 — 발송 생략")
            return
        proc = subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "kakao_report_sender.py"),
             "--message", draft, "--only-room", _od.WEEKLY_ROOM],
            cwd=str(REPO_ROOT), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=180,
            env=dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1"),
        )
        tail = (proc.stdout or "").strip().splitlines()[-1:] or ["(출력없음)"]
        logger.info(f"[주간 보고] 카톡 {_od.WEEKLY_ROOM} 발송: {tail[0]}")
        if proc.returncode != 0:
            _kakao_fail_notify("주간 보고 초안", tail[0], room=_od.WEEKLY_ROOM)
    except Exception as exc:
        logger.error(f"[주간 보고] 예외: {exc}")


def run_stream_3_mgmt() -> None:
    """스트림 #3 매출+운영+인사 현황 보고 (매일 09:30 · 업무보고방) — CTO 2026-07-22.
    확정 포맷: report_stream_3_impl v3 (54% 압축 · GM ok). 카카오=GM go 후 활성화.
    시우(COO) 최종목표 씨앗 — 자율화 완성 시 COO 인계 예정.

    ★배10011(2026-07-24, GM 승인): 09:10 모듈 데일리(자동화현황방 — GM 2인 전용 실측 확인,
    수신자 손실 없음)를 이 메시지 맨 앞 섹션으로 흡수한다. 09:30 을 유지한 이유(09:10 대신) —
    module_reporter 는 별도 Windows 예약작업(Wellperion-Module-Report-Daily, 09:10)이라
    스트림#3(이 함수, daily_scheduler 상주 프로세스 내부)과 다른 프로세스다. 09:10에 정확히
    맞춰 동시 실행하면 pending 파일 기록이 아직 안 끝났을 때 여기가 먼저 읽어버리는 경합이
    생길 수 있어, 20분 버퍼를 주는 09:30 유지가 더 안전하다."""
    label = "[스트림 #3 매출+운영+인사]"
    logger.info(f"{label} 시작")
    try:
        import weekly_bundle_pending as _bundle
        import module_reporter as _mr
        absorbed = _bundle.consume("stream3_daily")
        prefix_parts = [it["text"] for it in absorbed if it.get("text")]

        import report_stream_3_mgmt as _s3
        _s3.run(dry_run=False, kakao_go=False, prefix_parts=prefix_parts)

        # 매출 보고 시트 '운영 현황 한눈에' 탭 자동 갱신(2026-08-10 GM 승인) — 텔레그램 발송에
        # 얹는 한 줄. 실패해도 위 텔레그램 발송은 이미 끝난 뒤라 무영향(best-effort).
        try:
            import ops_digest_sheet_push as _odp
            _odp.push()
        except Exception as e:
            logger.error(f"{label} 운영현황시트 갱신 실패(무영향): {e}")

        if absorbed:
            keys = [it["source"] for it in absorbed]
            _mr.mark_bundle_sent(keys, cadence="daily")
        logger.info(f"{label} 완료 (업무보고방 발송 · 흡수 {len(absorbed)}건)")

        # ── ★운영부 카톡 발송 삭제 (GM 지시 2026-08-08) ──
        # GM: "운영부 방에는 어제 운영부 정리 이 1건만 자동 발송. 하루 일과 정리, 사람이
        #      처리할 업무 건은 이제 삭제해줘. 통합해서 중간관리자방에 보내는걸로."
        # 여기서 ★운영부로 보내던 「하루 일과 정리(업무 SSOT 현황)」를 지운다. 지연 목록을
        # 본인이 봐야 한다는 2026-07-31 판단은 유효하지만, 그 몫은 ★중간관리자 방으로 통합된다
        # (실장·소장·나우열M 이 그 방에 다 있어 나누는 자리가 거기다 · 약속 L24 채널 분리).
        # ▸게이트를 꺼서 남기지 않고 지운다 — 꺼둔 코드는 죽은 코드가 되고 나중에 누가 다시
        #   켠다(약속 L21). 되살릴 일이 생기면 이 커밋을 되돌리면 된다.
        # ▸GM 업무보고방(텔레그램) 발송은 위 report_stream_3_mgmt.run 그대로 살아 있다 —
        #   없어진 것은 카톡 ★운영부 사본 하나뿐이다(정보 손실 없음).
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

    # ★배10011(2026-07-24, GM 승인): 23시 GM 개인DM은 완전 폐지(끄기가 아니라 삭제 —
    #   되돌릴 수 있는 킬스위치를 남기면 죽은 코드로 있다 누가 또 켠다·배10008과 동일 원칙).
    #   단 _compute_23_body_and_anomaly() 내부의 미완료 원장 적재(CHECK_INCOMPLETE_LEDGER
    #   append_daily_from_live) 부작용은 카톡 22:30/23:00 "반복 미완료 제안"이 계속 소비하므로
    #   계산 호출 자체는 보존한다(호출부 확인 완료 — support_check_summary/kakao 23시 경로).
    body_override: str | None = None
    if slot == "23" and not test_mode:
        _compute_23_body_and_anomaly()  # 원장 적재 부작용만 필요 — 반환값은 GM DM에 안 씀(폐지)
        logger.info(f"{label} 23시 GM DM 폐지(배10011) — 원장 적재만 수행, 발신 없음(상세는 카톡 23시·점검관리방)")
        return

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
    #   ★배10011(2026-07-24, GM 승인): CHECK_MORNING_1200_ENABLED 킬스위치를 삭제하고
    #   점검관리방 발신을 구조적으로 영구 미발신 고정(끄기가 아니라 삭제 — 배10008과 동일
    #   원칙). builder(_build_12_body)는 되돌림·--manual-test 미리보기용으로 보존.
    if slot == "12" and not test_mode:
        logger.info(f"{label} 12시 점검관리방 발신 폐지(배10011, 2026-07-18 GM 결정 영구화) — 미발신")
        return

    # 개인 슬롯(06 하루시작·운동 / 22 취침)은 개인 방으로 — GM 지시 2026-08-08
    # "이런 건 개인적인 부분이라 업무보고방이 아니라 개인한테". 업무보고방은 하루 종일
    # 업무가 흐르는 곳이라 개인 문구가 그 사이에 묻힌다. 키가 없으면 지금 그대로(회귀 0).
    target_id = owner_id
    if slot in ("06", "22") and not test_mode:
        personal = ENV.get("TELEGRAM_PERSONAL_CHAT_ID")
        if personal:
            target_id = int(personal)

    # 22시 취침 안내는 22:00 체크인 카드(run_gm_checkin) 꼬리로 흡수됐다 — 여기서 또 보내면
    # 같은 분에 두 번 울린다. 문구는 없어진 게 아니라 카드 안으로 자리를 옮겼다(GM 2026-08-08).
    # builder(_build_22_body)는 되돌림·--manual-test 미리보기용으로 남긴다.
    if slot == "22" and not test_mode:
        logger.info(f"{label} 22시 취침 안내는 22:00 체크인 카드로 흡수 — 단독 발신 안 함")
        return

    success = send_telegram(target_id, body, parse_mode=parse_mode)
    if success:
        logger.info(f"{label} 텔레그램 발송 완료 chat_id={target_id}")
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
    #   planning_to_archive_watcher.py)은 제거·파일부재(2026-07-22 확인).

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
    #   제거·파일부재(2026-07-22 확인).

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

    # ── 미팅 30분 전 리마인드 (5분 주기 · 카톡 김남욱 방) — 배451 · GM 확정 2026-08-07 ──
    scheduler.add_job(
        _run_meeting_reminder,
        trigger=IntervalTrigger(minutes=5),
        id="meeting_reminder_30min",
        misfire_grace_time=120,
        coalesce=True,
    )
    logger.info("meeting_reminder_30min 등록 완료 (5분 주기 · 전사일정 시각 있는 GM 일정만)")

    # (ops_done_immediate_alert 10분 주기 잡 삭제 2026-08-18 — 배670, _check_ops_done_immediate
    #   정의부 자리의 주석 참조. 다음 날 아침 「어제 완료」가 커버해 순수 중복이었다.)

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
    # [2026-07-23 시토] '실행 완료' 로그가 성공을 위장하던 문제 수리.
    #   기존: subprocess.run 을 check 없이 호출하고 stdout/stderr 를 DEVNULL 로 버린 뒤
    #   무조건 "실행 완료 (kpi_values.json 갱신)" 을 남겼다. 그래서 수집기가 죽어도
    #   로그는 초록불이었고, kpi_values.json 이 07-20 10:14 이후 3일간 멈춰 있었는데도
    #   scheduler.log 만 보면 정상으로 보였다(무결성 경보가 먼저 잡아냄).
    #   수리: ①종료코드 확인 ②실패 시 stderr 꼬리를 로그에 남김 ③**generated_at 이
    #   실제로 앞으로 갔는지 대조** — 로그가 아니라 산출물로 성공을 판정한다.
    def _collect_kpi():
        kpi_path = BASE.parent / "status" / "kpi_values.json"

        def _stamp():
            try:
                return json.loads(kpi_path.read_text(encoding="utf-8")).get("generated_at")
            except Exception:
                return None

        before = _stamp()
        try:
            proc = subprocess.run(
                [sys.executable, "scripts/kpi_collector.py"],
                cwd=str(BASE.parent), timeout=300,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
        except Exception as e:
            logger.error(f"kpi_collector 실행 실패(예외): {type(e).__name__}: {e}")
            return
        if proc.returncode != 0:
            tail = (proc.stderr or b"").decode("utf-8", "replace").strip()[-400:]
            logger.error(f"kpi_collector 종료코드 {proc.returncode} — stderr: {tail}")
            return
        after = _stamp()
        if after and after != before:
            logger.info(f"kpi_collector 실행 완료 — kpi_values.json 갱신 확인 ({after})")
        else:
            tail = (proc.stderr or b"").decode("utf-8", "replace").strip()[-400:]
            logger.error(
                "kpi_collector 가 0으로 끝났으나 kpi_values.json 이 갱신되지 않음 "
                f"(generated_at 그대로: {before}) — stderr: {tail}"
            )

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

    # ── 화면 열람 흔적 수집 (매일 07:40) — 시토 2026-08-12 · 배478 (GM 승인) ──────
    #   화면 쪽 짝 = _assets/page_ping.js 가 열릴 때 경로+시각만 남긴다. 여기서 하루 한 번
    #   걷어 status/page_ping.json 으로 낸다 → 부팅 저점 목록이 "아무도 안 여는 화면"을
    #   함께 보여 준다. 사람 방으로 아무것도 안 보낸다(발신 아님).
    #   새 모듈·새 예약작업을 만들지 않고 이미 도는 이 스케줄러에 얹었다(약속 L21).
    def _collect_page_ping():
        try:
            proc = subprocess.run(
                [sys.executable, "scripts/page_score_extract.py", "--ping"],
                cwd=str(BASE.parent), timeout=300,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
        except Exception as e:
            logger.error(f"page_ping 수집 실패(예외): {type(e).__name__}: {e}")
            return
        if proc.returncode != 0:
            tail = (proc.stderr or b"").decode("utf-8", "replace").strip()[-400:]
            logger.error(f"page_ping 수집 종료코드 {proc.returncode} — stderr: {tail}")
            return
        logger.info((proc.stdout or b"").decode("utf-8", "replace").strip() or "page_ping 수집 완료")

    scheduler.add_job(
        _collect_page_ping,
        trigger=CronTrigger(hour=7, minute=40),
        id="page_ping_collect",
        misfire_grace_time=1800,
        coalesce=True,
    )
    logger.info("page_ping 수집 등록 완료 (매일 07:40) — 화면 열람 흔적")

    # ── 구역 전체 미점검 알림 (14:00·20:00 · 0건일 때만 · 구역당 하루 1회) — 웰리 2026-07-31 ──
    # GM 지시: "실무진에서 매일 돌아가야 하는 부분이 안 돌아가면 알림 줘야 할 것 같은데 —
    #   오늘은 여자 지원부 점검을 안 했는데." 그날 실측 = 여성구역 0/52(전 회차 0).
    # ★2026-07-23 GM 이 없앤 17시·22시 고정 독려를 되살리는 것이 아니다(그건 매일 떠서 소음이었다).
    #   여기는 **한 구역이 통째로 0건**일 때만 뜬다 — 덜 된 것은 안 알린다. 평소엔 완전 침묵.
    # 판정은 support_check_summary.zero_zones() 한 곳(22:30 보고와 같은 원천 · 약속 L01).
    _ZERO_ALERT_STATE = REPO_ROOT / "status" / "check_zero_alert.json"

    # ── 낮 1회 점검 현황 = 폐지 (GM 지시 2026-08-13 "점심 점검현황 하지말아줘 저녁에 한번만 해줘") ──
    #   2026-08-07 에 "낮에는 어디에도 안 보인다"는 지적으로 14:00 슬롯에 얹었던 한 장이다.
    #   GM 이 오늘 직접 그만하라고 했다 — 하루 정리는 22:30 한 번(report_stream_2_check)으로 족하다.
    #   ▸게이트를 꺼서 남기지 않고 **지운다**(약속 L21 — 꺼둔 코드는 죽은 코드가 되고 누가 다시 켠다).
    #     되살릴 일이 생기면 이 커밋을 되돌리면 된다. 렌더 함수(report_stream_2_check)는 그대로 산다.
    #   ▸구역 0건 침묵형 경보(_zero_zone_alert)는 남긴다 — 문제가 있을 때만 울리는 다른 장치다.

    def _zero_zone_alert(shift_key: str):
        try:
            import sys as _s
            _sp = str(REPO_ROOT / "scripts")
            if _sp not in _s.path:
                _s.path.insert(0, _sp)
            from support_check_summary import shift_gaps, facility_gap
            today = datetime.now().strftime("%Y-%m-%d")
            gaps = shift_gaps(today, shift_key)
            # 시설부가 통째로 0건인 날도 잡는다(배436 잔여 2번 · 2026-08-07 시토).
            # 그 전에는 지원부 남/여 구역만 봐서, 시설부가 하루 종일 0건이어도 아무도 몰랐다.
            # 조회 실패는 0으로 치지 않는다 — facility_gap 이 그때 None 을 준다.
            fac = facility_gap(today)
            if fac:
                gaps = gaps + [fac]
            if not gaps:
                return                      # 정상 — 아무 말도 하지 않는다
            try:
                state = json.loads(_ZERO_ALERT_STATE.read_text(encoding="utf-8"))
            except Exception:
                state = {}
            sent = set(state.get(today) or [])
            fresh = [g for g in gaps if f"{g['zone']}|{g['shift']}" not in sent]
            if not fresh:
                return                      # 오늘 이미 짚은 회차 — 두 번 보내지 않는다
            # ★사람이 옆에서 짚어주듯 쓴다(2026-07-31 GM 지시). 숫자만 던지면 받는 사람은
            #   무엇을 하라는 건지 모른다. '무슨 일이 일어난 것 같은지'까지 말해 준다.
            # '제출만 빠짐'(체크는 다 하고 제출 버튼만 안 누른 조)도 같은 문구로 묶는다
            # — 받는 사람이 할 일이 똑같다: 들어가서 제출 한 번(GM 지시 2026-08-25).
            miss = [g for g in fresh if g["likely"] in ("제출누락", "제출만 빠짐")]
            only_fac = all(g["zone"] == "시설부" for g in fresh)
            head = ("🔔 시설부 점검 입력이 아직 없습니다" if only_fac else
                    "🔔 점검은 도신 것 같은데 제출이 안 들어왔습니다" if miss else
                    "🔔 아직 시작 전인 회차가 있습니다")
            body = [head, "— 웰페리온 AI 운영지원 '웰리'가 보내드립니다.", ""]
            for g in fresh:
                if g["zone"] == "시설부":
                    body.append("▪ 시설부 — 오늘 점검 입력이 한 건도 없습니다")
                    body.append("   이미 도셨다면 입력만 부탁드립니다.")
                    continue
                if g["likely"] == "제출만 빠짐":
                    body.append(f"▪ {g['zone']} {g['shift']} — {g.get('done', 0)}/{g['total']}건 체크하셨는데 제출이 안 들어왔습니다")
                    body.append("   마지막에 [제출]만 한 번 눌러 주시면 됩니다.")
                    continue
                body.append(f"▪ {g['zone']} {g['shift']} — {g['total']}건 예정인데 제출 0건")
                if g["likely"] == "제출누락":
                    other = "여성구역" if g["zone"] == "남성구역" else "남성구역"
                    # 받침 유무로 은/는을 고른다 — 조사가 틀리면 '사람이 짚어준 느낌'이 깨진다.
                    _josa = "은" if (ord(other[-1]) - 0xAC00) % 28 else "는"
                    body.append(f"   같은 {g['shift']}에 {other}{_josa} 들어와 있어서,")
                    body.append("   하시고 입력만 못 하신 것 같습니다. 확인 부탁드립니다.")
                else:
                    body.append("   아직 시작 전이시면 그대로 두셔도 됩니다.")
                    body.append("   이미 하셨다면 제출만 부탁드립니다.")
            body.append("")
            # ★2026-08-08 GM 지적 "링크가 짤려서 보내지네 · 들어가보니 404".
            #   파일 이름에 띄어쓰기가 있어 그대로 붙이면 카카오톡·텔레그램이 **띄어쓰기에서
            #   주소를 끊는다.** 앞 반쪽만 링크가 되어 404 가 뜬다. 띄어쓰기만 %20 으로 바꾼다
            #   (한글까지 전부 바꾸면 사람이 주소만 보고 어느 페이지인지 알 수 없다 — 실무진이 본다).
            #   같은 규칙이 scripts/report_stream_2_check.py _page_url 에도 있다.
            _page = "시설부 체계.html" if only_fac else "지원부 체계.html"
            body.append("👉 https://wellperion-cao.github.io/wellperion-automation/coo/check/"
                        + _page.replace(" ", "%20"))
            # parse_mode=None = 평문. 본문에 '—'·'('·'.' 가 있어 MarkdownV2 로 보내면 파싱 오류가 난다.
            text = "\n".join(body)
            # 2026-08-15 GM 지시(중복 알림 정리) — 텔레그램 점검관리방(DIGEST_CHECK_CHAT_ID)
            #   발신을 끊는다. 실측: 이 문구가 같은 시각 report_stream_2_check.py 의 22:30
            #   점검현황과 겹쳐 실무진이 같은 내용을 텔레그램·카톡 두 채널로 받고 있었다
            #   (8/10~14 8회×2채널=16통, 본문 한 글자까지 동일). 카톡만 남긴다 — 실무진이
            #   실제로 보는 곳은 카톡 ★운영+시설+지원+주차다(2026-07-31 GM 지시 그대로 유지).
            #   정보는 사라지지 않는다: 이 알림의 사실(0건 구역)은 카톡으로 그대로 나가고,
            #   같은 사실이 텔레그램 점검관리방엔 22:30 하루 일과 정리(요약)로 이미 뜬다.
            ok = False
            try:
                kproc = subprocess.run(
                    [sys.executable, str(REPO_ROOT / "scripts" / "kakao_report_sender.py"),
                     "--message", text, "--only-room", KAKAO_OPS_ROOM],
                    cwd=str(REPO_ROOT), capture_output=True, text=True,
                    encoding="utf-8", errors="replace", timeout=180,
                    env=dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1"),
                )
                ktail = (kproc.stdout or "").strip().splitlines()[-1:] or ["(출력없음)"]
                logger.info(f"[zero-zone {shift_key}] 카톡 {KAKAO_OPS_ROOM}: {ktail[0]}")
                ok = kproc.returncode == 0
                if not ok:
                    _kakao_fail_notify(f"회차 제출누락({shift_key})", ktail[0])
            except Exception as ke:
                logger.error(f"[zero-zone {shift_key}] 카톡 발송 예외: {ke}")
            if ok:
                state[today] = sorted(sent | {f"{g['zone']}|{g['shift']}" for g in fresh})
                _ZERO_ALERT_STATE.write_text(
                    json.dumps(state, ensure_ascii=False), encoding="utf-8")
                logger.info(f"[zero-zone {shift_key}] 발송: {[(g['zone'], g['likely']) for g in fresh]}")
            else:
                logger.error(f"[zero-zone {shift_key}] 발송 실패 — 상태 미기록(다음 슬롯 재시도)")
        except Exception as e:
            logger.error(f"[zero-zone {shift_key}] 예외: {e}")

    # 14:00 = 오전조가 끝난 뒤 / 20:00 = 오후조가 끝난 뒤 / 22:45 = 마감조(22:00~22:30) 끝난 뒤.
    # ★2026-08-20 GM 지시(배704 후속) — "둘 중에 한 부서라도 진행이 안 된 것은 카카오톡
    #   알림까지 해줘야 해." 마감조는 원래 "22:30 하루 정리가 담당한다"고 미뤄뒀으나(위 주석
    #   구판), 그 22:30 요약은 완료율 문장 속에 묻혀 있어 이 알림처럼 "어느 구역·회차가
    #   0건인지"를 사람이 짚어주듯 못 짚는다. 새 스크립트·새 예약작업 없이 같은 함수
    #   (_zero_zone_alert)를 같은 스케줄러에 한 슬롯만 더 얹는다(22:30 하루정리와 15분
    #   띄워 카톡 PC 자동화 동시실행 겹침을 피함).
    for _h, _m, _sk in ((14, 0, "am"), (20, 0, "pm"), (22, 45, "close")):
        scheduler.add_job(
            _zero_zone_alert,
            trigger=CronTrigger(hour=_h, minute=_m),
            id=f"zero_zone_alert_{_h}{_m:02d}",
            args=[_sk],
            misfire_grace_time=1800,
            coalesce=True,
        )
    logger.info("회차 제출누락 알림 등록 완료 (14:00 오전조·20:00 오후조·22:45 마감조 · 0건일 때만 · 회차당 하루 1회)")

    # ── 시트 칸 계약 점검 (매일 07:50 — 08:00 통합 브리프 직전) — CPO 2026-07-20 ──
    # 재발방지 A안 0단계(GM 확정, 값 규칙 포함). 정상이면 완전 침묵 — 어긋남만 알린다.
    # ★받는 방 = 자동화현황방(-5498808140). 2026-08-12 실측 정정 — 여기 '업무보고방'이라 적혀
    # 있었지만 실제 경로는 cpo_sheet_contract.py _send_alert() → notify_gm_progress.resolve_room()
    # 이라 자동화현황방으로 간다. 등록부(notify_registry tg-0750-cpo-sheet-contract)도 같은 값.
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
        logger.info("=== 정규 스케줄 시작: 06/12/21/23시 (GM 알림 홍수 축소 · 2026-07-18 GM 승인, 배10011로 18시 흡수) ===")
        # [2026-06-07 GM 확정] 08시는 ceo_morning_pipeline(별도 Task Scheduler) 담당.
        # [2026-07-18 GM 승인] GM DM 홍수 축소 — 07(어제결산)·09(매출/진행)·15(중간정리)·
        #   22(취침) GM DM 슬롯 폐지. 핵심값(어제완료·매출1줄·북극성top·직원카드)은 08:00
        #   통합브리프(ceo_morning_pipeline)로 흡수. 12시·23시 GM DM은 배10011(2026-07-24)로
        #   킬스위치가 삭제되며 구조적으로 영구 미발신(23시 원장 적재만 보존) — 아래 run_report 참조.
        #   builder 함수(_build_07/09/12/15/18/22_body)는 보존 — 되돌림·--manual-test 미리보기용.
        # [2026-07-24 GM 승인·배10011] 18시(퇴근인사·저녁루틴·명언) 단독 발신 폐지 — 21시 본문
        #   서두로 흡수(_build_21_body 참조). schedule_map에서 "18" 제거.
        schedule_map = {
            "06": (6, 0),
            "12": (12, 0),
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

        # ── 지원부 점검 미완 독려 17:00·22:00 슬롯 = 폐지 (GM 2026-07-23) ──
        #   GM 판단: "알림·현황 보고가 너무 많다" → 22:30 하루 일과 정리 하나로 통합.
        #   독려 내용(미완 회차 + 미체크 항목명)은 22:30 지원부 섹션이 상시 포함한다
        #   (support_check_summary.build_support_section 의 '🔔 독려 대상' 블록).
        #   덤: 옛 독려 경로에 있던 today_live 글리치 가드가 진짜 미완을 삼키던 문제
        #   (07-17·07-22 총 4건 소실)도 경로 자체가 사라져 원천 해소된다 — 22:30 은
        #   그런 억제 장치 없이 실측 숫자를 그대로 낸다.

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

        # ── 접수 즉시 부서 전달 (15분 간격) — CTO 배627 · GM 승인 2026-08-15 ───────────
        # GM: "다 운영부 라인으로 넘기니 병목이 일어나고 처리가 안 된다. 각 부서에 전달되어
        # 그 부서에서 조치·회신까지 챙기게 하라." 새 예약작업을 만들지 않고 이미 상주하는
        # 이 스케줄러에 잡 하나만 얹는다(약속 L21). 부서별로 따로 한 통씩 나가고, 새 접수가
        # 없는 부서는 아무것도 보내지 않는다. 게이트 = dept_completion_notify.json
        # intake_relay_enabled(꺼두면 이 잡이 돌아도 발송 0).
        try:
            from report_stream_2b_reception import run_intake_relay  # noqa: PLC0415

            scheduler.add_job(
                lambda: run_intake_relay(dry_run=False),
                trigger=IntervalTrigger(minutes=15),
                id="reception_intake_relay_15min",
                misfire_grace_time=300,
                coalesce=True,
            )
            logger.info("reception_intake_relay 등록 완료 — 15분 간격, 새 접수를 부서별로 종합접수처방 전달")
        except Exception as e:  # noqa: BLE001
            logger.error(f"reception_intake_relay 등록 실패: {e}")

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

        # ── GM 개인 하루 체크인 (매일 21:30) + 한 주 카드 (일요일 21:40) — GM 승인 2026-08-08 ──
        try:
            # 개인 알림은 하루 두 번뿐 — 아침(06:00 하루 시작에 「오늘 하나씩」 흡수)과
            # 저녁(22:00 하루 마무리에 취침 안내 흡수). GM 2026-08-08:
            # "06:00 하루 시작 / 07:00 = 21:30 같은 맥락? / 22:00 하루 마무리".
            # 아침 제안은 별도 잡이 아니라 _build_06_body() 안 _checkin_morning_block() 이 낸다.
            scheduler.add_job(
                run_gm_checkin,
                trigger=CronTrigger(hour=22, minute=0, timezone="Asia/Seoul"),
                id="gm_checkin_2200",
                misfire_grace_time=1800,
                coalesce=True,
            )
            scheduler.add_job(
                run_gm_checkin,
                trigger=CronTrigger(day_of_week="sun", hour=22, minute=10, timezone="Asia/Seoul"),
                args=[True],
                id="gm_checkin_week_sun2210",
                misfire_grace_time=1800,
                coalesce=True,
            )
            logger.info("gm_checkin 등록 완료 — 06:00 아침(하루시작에 흡수), 22:00 하루 마무리, 일요일 22:10 한 주 카드")
        except Exception as e:
            logger.warning(f"gm_checkin 등록 실패: {e}")

        # ── 시점별 체크(끼니·운동) 4슬롯 — GM 요청 2026-08-09 ───────────────────
        try:
            import gm_checkin as _ck_slots
            for _sid, _h, _m, _title, _items in _ck_slots.SLOTS:
                scheduler.add_job(
                    run_gm_checkin_slot,
                    trigger=CronTrigger(hour=_h, minute=_m, timezone="Asia/Seoul"),
                    args=[_sid],
                    id=f"gm_checkin_slot_{_sid}",
                    misfire_grace_time=600,
                    coalesce=True,
                )
            logger.info("gm_checkin_slot 등록 완료 — 09:00 아침·13:30 점심·16:30 간식·21:00 저녁 4슬롯")
        except Exception as e:
            logger.warning(f"gm_checkin_slot 등록 실패: {e}")

        # ── GM 아침 업무 브리핑 (월~토 08:00 · 나의하루 방) — 배514 미배선 해소, GM 2026-08-10 ──
        try:
            scheduler.add_job(
                run_gm_morning_brief,
                trigger=CronTrigger(day_of_week="mon-sat", hour=8, minute=0, timezone="Asia/Seoul"),
                id="gm_morning_brief_0800",
                misfire_grace_time=1800,
                coalesce=True,
            )
            logger.info("gm_morning_brief 등록 완료 — 월~토 08:00 나의하루 방(일요일 스킵)")
        except Exception as e:
            logger.warning(f"gm_morning_brief 등록 실패: {e}")

        # ── GM 저녁 정리 카드(월~토 20:30 · 나의하루 방) — GM 지시 2026-08-10 ──────
        #   08:00 브리핑의 짝. 21:00 저녁 끼니슬롯·22:00 저녁 설문과 안 겹치는 20:30.
        try:
            scheduler.add_job(
                run_gm_evening_recap,
                trigger=CronTrigger(day_of_week="mon-sat", hour=20, minute=30, timezone="Asia/Seoul"),
                id="gm_evening_recap_2030",
                misfire_grace_time=1800,
                coalesce=True,
            )
            logger.info("gm_evening_recap 등록 완료 — 월~토 20:30 나의하루 방(일요일 스킵)")
        except Exception as e:
            logger.warning(f"gm_evening_recap 등록 실패: {e}")

        # ── 운영부 주간 보고 초안 (금요일 17:00 · ★중간관리자 방) — CTO 2026-08-06 ──
        try:
            scheduler.add_job(
                run_weekly_ops_report,
                trigger=CronTrigger(day_of_week="fri", hour=17, minute=0, timezone="Asia/Seoul"),
                id="weekly_ops_report_fri1700",
                misfire_grace_time=600,
                coalesce=True,
            )
            logger.info("weekly_ops_report 등록 완료 — 매주 금 17:00 ★중간관리자 발송")
        except Exception as e:
            logger.warning(f"weekly_ops_report 등록 실패: {e}")

        # ── ★중간관리자 알림성 합본 (매일 17:05) — GM 지시 2026-08-10: 알림성 카톡을
        #   밤으로 미루지 않는다. 금요일 17:00 weekly_ops_report(위)와 같은 방이라
        #   5분 뒤로 둬 두 발신이 겹치지 않게 한다(약속 L21 — 새 방·새 발신기 안 만듦).
        try:
            scheduler.add_job(
                run_mgmt_notice_digest,
                trigger=CronTrigger(hour=17, minute=5, timezone="Asia/Seoul"),
                id="mgmt_notice_digest_1705",
                misfire_grace_time=600,
                coalesce=True,
            )
            logger.info("mgmt_notice_digest 등록 완료 — 매일 17:05 ★중간관리자 알림성 합본")
        except Exception as e:
            logger.warning(f"mgmt_notice_digest 등록 실패: {e}")

    # ── git 죽은 잠금 청소 (배9889 · 2026-07-23 시토) ──────────────────────
    #   `git commit -- <경로>` 가 쓰는 임시 인덱스(next-index-<PID>.lock)는 그 프로세스가
    #   중간에 죽으면 잔해로 남는다. 2026-07-23 실측 22개(07-20부터 누적) — 동시 커밋
    #   경합으로 중단된 커밋들이 쌓인 것이다. 죽은 index.lock 이 남으면 그 뒤 **전
    #   C-Level 커밋이 전부 실패**하므로(시우 발견), 기동할 때 한 번 치우고 시작한다.
    #   ★안전은 청소기 쪽이 책임진다: 잠금 주인이 살아있거나 파일이 점유 중이면
    #   아무것도 건드리지 않는다(오판 시 인덱스 손상). 실패해도 기동을 막지 않는다.
    #
    #   [2026-07-24 시토 보강] 처음엔 '기동할 때 1회'로만 돌렸다. 오늘 그게 부족하다는 게
    #   드러났다 — 07:40 에 생긴 죽은 잠금이 09:04 까지 84분을 버텼다. 기동 이후에 생긴
    #   잠금은 다음 재기동까지 아무도 안 치우기 때문이다(그 사이 전 세션의 git add 가 실패).
    #   그래서 10분 간격 점검을 추가한다. 윈도우 예약 슬롯을 새로 만들지 않고 이미 도는
    #   스케줄러 안에 얹으며, 알림은 여전히 0통이다(로그만).
    def _sweep_git_locks(when: str) -> None:
        try:
            r = subprocess.run(
                [sys.executable, "scripts/git_lock_janitor.py", "--apply"],
                cwd=str(BASE.parent), timeout=120,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
            tail = (r.stdout or b"").decode("utf-8", "replace").strip().splitlines()
            line = " | ".join(tail[-2:]) if tail else "출력 없음"
            # 치운 게 있을 때만 눈에 띄게 남긴다 — 10분마다 조용한 성공 로그로 도배하지 않는다.
            if "정리 완료" in line:
                logger.info(f"git 잠금 청소({when}): {line}")
            else:
                logger.debug(f"git 잠금 청소({when}): {line}")
        except Exception as exc:
            logger.warning(f"git 잠금 청소 건너뜀({when}): {type(exc).__name__}: {exc}")

    # ── 매출보고 구글 세션 지킴이 (배10021 · INC-033 · GM 2026-07-24 B안) ──────────
    #   구글 세션은 약 14일 주기로 반드시 만료되는데, 지금까지는 09:30 발송하려는 순간에야
    #   알았고 그때는 이미 회장님·관리부·운영부 보고가 펑크난 뒤였다. 08:10 에 미리 확인해
    #   만료면 **로그인 창만 띄운다** — 텔레그램·카톡 알림은 한 통도 보내지 않는다
    #   (배10011 '알림 신설 금지' 준수. 화면에 뜬 창이 신호다).
    def _guard_sales_session() -> None:
        try:
            r = subprocess.run(
                [sys.executable, "scripts/sales_session_guard.py"],
                cwd=str(BASE.parent), timeout=300,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
            tail = (r.stdout or b"").decode("utf-8", "replace").strip().splitlines()
            logger.info("매출보고 세션 점검: " + (tail[-1] if tail else "출력 없음"))
        except Exception as exc:
            logger.warning(f"매출보고 세션 점검 건너뜀: {type(exc).__name__}: {exc}")

    try:
        scheduler.add_job(
            _guard_sales_session,
            trigger=CronTrigger(hour=8, minute=10),
            id="sales_session_guard_0810",
            replace_existing=True,
            misfire_grace_time=1800,
            coalesce=True,
        )
        logger.info("매출보고 세션 지킴이 등록 완료 — 매일 08:10(알림 0통·만료 시 로그인 창만)")
    except Exception as _exc:
        logger.warning(f"매출보고 세션 지킴이 등록 실패(기동은 계속): {_exc}")

    _sweep_git_locks("기동")
    try:
        scheduler.add_job(
            _sweep_git_locks,
            trigger=IntervalTrigger(minutes=10),
            args=["주기"],
            id="git_lock_janitor_10min",
            replace_existing=True,
            misfire_grace_time=300,
            coalesce=True,
        )
        logger.info("git 잠금 청소 등록 완료 — 10분 간격(알림 없음·로그만)")
    except Exception as _exc:
        logger.warning(f"git 잠금 청소 주기 등록 실패(기동은 계속): {_exc}")

    start_live_cli_status_server(logger)

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
