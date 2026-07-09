# -*- coding: utf-8 -*-
"""
telegram_send.py — 범용 텔레그램 발송 leaf (부작용 없는 안전 import).
─────────────────────────────────────────────────────────────────────────────
module_reporter 등 신규 보고 인프라가 쓰는 단일 발송기. daily_scheduler.py의
send_telegram(:320-367) 재시도·지수백오프·연속실패추적·local_fallback_alert 로직을
**복제 이식**했다(원본 파일은 미수정 — 의식적 병존, 통합은 후속 배).

leaf 원칙(반드시 지킬 것):
  - import-time 부작용 0: 토큰은 send() 호출 시에만 .env에서 직독. 모듈레벨 sys.exit·
    로깅 config·PID락·네트워크 없음 → 어디서든 안전하게 import 가능.
  - 봇 토큰 단일출처 = telegram_bot/.env 의 TELEGRAM_BOT_TOKEN(신규 자격증명 0).
  - chat_id 가 None 이면 즉시 False 반환(방 미지정 → 발송 스킵).

반환: send(chat_id, text) -> bool  (성공 True / 실패·스킵 False)
"""
from __future__ import annotations

import json
import os
import subprocess
import time
from datetime import datetime
from pathlib import Path

# ── 경로 상수 (모듈레벨 실행 없음 — 상수 정의만) ─────────────────────────────
_SCRIPTS_DIR = Path(__file__).resolve().parent.parent          # scripts/
_PROJECT_ROOT = _SCRIPTS_DIR.parent                            # repo root
_ENV_FILE = _PROJECT_ROOT / "telegram_bot" / ".env"
_STATUS_DIR = _PROJECT_ROOT / "status"
# 신 발송기 전용 실패 추적(스케줄러 state.json 미접촉 — 불가침 보존)
_FAILURE_STATE_FILE = _STATUS_DIR / "module_send_failure.json"

_MAX_ATTEMPTS = 3
_TIMEOUT = 15


# ── .env 직독 (호출 시점 lazy) ────────────────────────────────────────────────
def _read_token() -> str:
    """telegram_bot/.env 에서 TELEGRAM_BOT_TOKEN 직독. 환경변수 우선."""
    if os.environ.get("TELEGRAM_BOT_TOKEN"):
        return os.environ["TELEGRAM_BOT_TOKEN"].strip()
    if not _ENV_FILE.exists():
        return ""
    for line in _ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        if k.strip() == "TELEGRAM_BOT_TOKEN":
            return v.strip()
    return ""


# ── 연속 실패 추적 (daily_scheduler record_send_failure 미러 — 독립 파일) ──────
def _record_failure() -> int:
    count = 1
    try:
        if _FAILURE_STATE_FILE.exists():
            prev = json.loads(_FAILURE_STATE_FILE.read_text(encoding="utf-8"))
            count = int(prev.get("consecutive_failures", 0)) + 1
    except Exception:
        count = 1
    try:
        _FAILURE_STATE_FILE.write_text(
            json.dumps(
                {"timestamp": datetime.now().isoformat(), "consecutive_failures": count},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    except Exception:
        pass
    return count


def _record_success() -> None:
    try:
        _FAILURE_STATE_FILE.write_text(
            json.dumps(
                {"timestamp": datetime.now().isoformat(), "consecutive_failures": 0},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    except Exception:
        pass


# ── 로컬 fallback 경보 (daily_scheduler local_fallback_alert 미러 — 비차단) ────
def _local_fallback_alert(message: str) -> None:
    """발송 3회 실패 시 Windows 데스크톱 경보 + 콘솔. Popen 비차단(테스트 무해)."""
    print(f"[FALLBACK ALERT] {message}")
    try:
        safe = message.replace("'", " ")
        ps_cmd = (
            "Add-Type -AssemblyName System.Windows.Forms; "
            f"[System.Windows.Forms.MessageBox]::Show('{safe}', "
            "'웰페리온 모듈보고 경보', 0, 48)"
        )
        subprocess.Popen(
            ["powershell", "-NonInteractive", "-Command", ps_cmd],
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception as e:  # 경보 실패가 본류를 죽이지 않음
        print(f"[FALLBACK ALERT] 로컬 알림 실패: {e}")


def send(chat_id, text: str) -> bool:
    """HTTP POST sendMessage. 재시도 3회 지수백오프(3→6→12s)·ok 검증·연속실패추적.

    chat_id=None → 즉시 False(방 미지정 스킵, 네트워크 없음).
    성공 True / 3회 실패 후 False(+local_fallback_alert).
    """
    if chat_id is None:
        return False

    token = _read_token()
    if not token:
        _local_fallback_alert("발송 실패: TELEGRAM_BOT_TOKEN 미설정")
        return False

    # requests 는 발송 시점에만 import(테스트·dry-run에서 미접촉 시 부담 0)
    import requests  # noqa: PLC0415

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            resp = requests.post(url, json=payload, timeout=_TIMEOUT)
            if resp.status_code == 200 and resp.json().get("ok"):
                _record_success()
                return True
            print(
                f"[telegram_send] 실패 attempt={attempt} "
                f"status={resp.status_code} body={resp.text[:160]}"
            )
        except Exception as e:
            print(f"[telegram_send] 요청 예외 attempt={attempt}: {e}")
        if attempt < _MAX_ATTEMPTS:
            time.sleep(3 * (2 ** (attempt - 1)))  # 3s → 6s
    count = _record_failure()
    _local_fallback_alert(f"텔레그램 전송 {_MAX_ATTEMPTS}회 실패 (연속 {count}회) — chat_id={chat_id}")
    return False
