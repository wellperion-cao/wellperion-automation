# -*- coding: utf-8 -*-
"""텔레그램 알림 헬스체크 — 조용한 실패 자가탐지.

목적:
    봇 토큰 유효성, 3개 그룹방 멤버십, 당일 발송 원장(ok=false 건수)을
    매일 자동으로 점검하여 문제 발견 시에만 OWNER에게 경보를 보낸다.
    정상이면 발송하지 않는다(침묵).

실행법:
    python scripts/telegram_health_check.py            # 실제 실행 (문제 시 OWNER 경보)
    python scripts/telegram_health_check.py --dry-run  # 드라이런 (발송 없이 stdout만)

스케줄 안내:
    Task Scheduler 에 1일 1회(예: 09:00) 등록 권장.
    daily_scheduler.py 와 별도 프로세스로 독립 동작.
"""
from __future__ import annotations

import argparse
import datetime
import glob
import json
import os
import sys

import requests

# ── 경로 설정 ─────────────────────────────────────────────────────────────────
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT_DIR = os.path.dirname(_SCRIPT_DIR)
_ENV_PATH = os.path.join(_ROOT_DIR, 'telegram_bot', '.env')
_LOG_DIR = os.path.join(_ROOT_DIR, 'logs')

# ── tg_outbound_log 임포트 (best-effort — 없으면 무음 fallback) ───────────────
try:
    sys.path.insert(0, _SCRIPT_DIR)
    from tg_outbound_log import log_outbound as _log_outbound
except ImportError:
    def _log_outbound(*args, **kwargs):  # type: ignore[misc]
        pass


# ── .env 로더 ─────────────────────────────────────────────────────────────────
def _load_env(path: str) -> dict:
    """key=value .env 파싱. 주석·빈줄 무시."""
    env: dict = {}
    try:
        with open(path, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                if '=' in line:
                    k, _, v = line.partition('=')
                    env[k.strip()] = v.strip()
    except Exception as e:
        print(f"[WARN] .env 읽기 실패: {e}", flush=True)
    return env


# ── Telegram API 호출 헬퍼 ────────────────────────────────────────────────────
def _tg_get(token: str, method: str, params: dict | None = None, timeout: int = 10):
    """GET 호출. (response_dict, http_status) 반환. 예외 시 (None, 0)."""
    try:
        resp = requests.get(
            f"https://api.telegram.org/bot{token}/{method}",
            params=params or {},
            timeout=timeout,
        )
        return resp.json(), resp.status_code
    except Exception as e:
        print(f"[WARN] {method} 호출 예외: {e}", flush=True)
        return None, 0


# ── 점검 1: 봇 생존 + bot_id 획득 ────────────────────────────────────────────
def _get_bot_info(token: str) -> tuple[bool, int | None, str]:
    """getMe → (alive, bot_id, detail).
    bot_id 는 getChatMember 에 필요."""
    data, status = _tg_get(token, 'getMe')
    if data is None:
        return False, None, "네트워크 오류 또는 타임아웃"
    if status == 200 and data.get('ok'):
        result = data.get('result', {})
        return True, result.get('id'), f"@{result.get('username', '?')}"
    return False, None, f"status={status} ok={data.get('ok')} desc={data.get('description', '')}"


# ── 점검 2: 그룹방 멤버십 ────────────────────────────────────────────────────
def _check_rooms(token: str, bot_id: int, rooms: list[tuple[str, int]]) -> list[str]:
    """각 방에 대해 getChatMember → 문제 목록 반환."""
    issues: list[str] = []
    for room_name, chat_id in rooms:
        try:
            data, status = _tg_get(token, 'getChatMember', {'chat_id': chat_id, 'user_id': bot_id})
            if data is None or status == 0:
                issues.append(f"봇이 [{room_name}] 방 접근 불가 (네트워크 오류)")
                continue
            if not data.get('ok'):
                desc = data.get('description', '')
                issues.append(f"봇이 [{room_name}] 방 접근 불가 — {desc}")
                continue
            member_status = data.get('result', {}).get('status', '')
            if member_status in ('left', 'kicked'):
                issues.append(f"봇이 [{room_name}] 방에서 퇴장/추방 (status={member_status})")
        except Exception as e:
            issues.append(f"봇이 [{room_name}] 방 점검 예외: {e}")
    return issues


# ── GAS exec URL (daily_scheduler.py 상수와 동일 소스) ───────────────────────
_VOC_DIAG_URL = (
    "https://script.google.com/macros/s/"
    "AKfycbwk2XS1FND9V2xtXlWgsXzgA5p0FG7jVm6YKD74JK_ME_ZvHsNUUfGE5A_8p0X8VcF3gQ/exec"
)
_FUNNEL_DIAG_URL = (
    "https://script.google.com/macros/s/"
    "AKfycbzdwSCCSSJ6JXLDoWuo7HG0JmBM2iy10TujFQ_O5JbTjnWaN7gOk-ddA4IAvsNfelg0xA/exec"
)
_CHECK_DIAG_URL = (
    "https://script.google.com/macros/s/"
    "AKfycbyXw4ZaA6hLK567GC7NY33Y8SvNPW6kNtrXFz2OsSdFVBmCnZP-2oD-RQiX0IpekBu1/exec"
)


# ── 점검 3a: GAS 설정 진단 프로브 ────────────────────────────────────────────
def _check_gas_diag() -> list[str]:
    """VOC·Survey GAS 설정 정상 여부를 ping.
    네트워크 실패 = WARN 로그만(오탐 방지·경보 제외).
    hasToken/hasChatId false = 설정 누락 → 경보 흐름에 합류.
    """
    issues: list[str] = []
    probes = [
        # (이름, URL, action 파라미터, 불리언 필드 목록)
        ("VOC GAS",    _VOC_DIAG_URL,    "diag",               ["hasToken", "hasChatId"]),
        ("Survey GAS", _FUNNEL_DIAG_URL, "diag_inquiry_state", []),
        ("점검 GAS",   _CHECK_DIAG_URL,  "diag",               ["hasToken", "hasChatId"]),
    ]
    for name, url, action, bool_fields in probes:
        try:
            resp = requests.get(url, params={"action": action}, timeout=15)
            if resp.status_code != 200:
                print(f"[WARN] {name} diag HTTP {resp.status_code} — 네트워크 이상(경보 제외)", flush=True)
                continue
            data = resp.json()
            if not data.get("ok"):
                issues.append(f"{name} 설정 이상 — GAS 응답 ok=false: {str(data)[:100]}")
                continue
            for field in bool_fields:
                if not data.get(field):
                    issues.append(f"{name} 설정 누락({field}=false) — GAS ScriptProperties 미설정")
        except Exception as e:
            print(f"[WARN] {name} diag 프로브 예외: {e} — 네트워크 이상(경보 제외)", flush=True)
    return issues


# ── 점검 3: 발송 원장 리컨실 ─────────────────────────────────────────────────
def _check_log_failures() -> list[str]:
    """오늘자 telegram_sent-*.log 에서 ok=false 건 집계 → 문제 목록 반환."""
    today = datetime.date.today().strftime('%Y-%m-%d')
    pattern = os.path.join(_LOG_DIR, f'telegram_sent-{today}.log')
    fail_records: list[dict] = []

    for path in glob.glob(pattern):
        try:
            with open(path, encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                        if rec.get('ok') is False:
                            fail_records.append(rec)
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            return [f"발송 원장 읽기 실패: {e}"]

    if not fail_records:
        return []

    targets = list(dict.fromkeys(str(r.get('chat_id', '?')) for r in fail_records))
    return [f"발송 실패 {len(fail_records)}건 — 대상 chat_id: {', '.join(targets)}"]


# ── 경보 발송 ─────────────────────────────────────────────────────────────────
def _send_alert(token: str, owner_id: int, message: str, dry_run: bool) -> None:
    """OWNER DM으로 경보. dry_run=True 면 stdout만."""
    if dry_run:
        print(f"[DRY-RUN] 경보 발송 생략 → chat_id={owner_id}", flush=True)
        print(f"[DRY-RUN] 메시지:\n{message}", flush=True)
        return
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={'chat_id': owner_id, 'text': message},
            timeout=15,
        )
        ok = resp.status_code == 200 and resp.json().get('ok', False)
        _log_outbound(message, chat_id=owner_id, source='telegram_health_check', ok=ok, kind='sendMessage')
        if not ok:
            print(f"[WARN] 경보 발송 실패: status={resp.status_code} body={resp.text[:200]}", flush=True)
    except Exception as e:
        print(f"[WARN] 경보 발송 예외: {e}", flush=True)


# ── 메인 ──────────────────────────────────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(description='텔레그램 알림 헬스체크')
    parser.add_argument('--dry-run', action='store_true', help='경보 발송 없이 stdout만')
    args = parser.parse_args()

    env = _load_env(_ENV_PATH)
    token = env.get('TELEGRAM_BOT_TOKEN', '')
    owner_id_str = env.get('OWNER_ID') or env.get('TELEGRAM_CHAT_ID', '')
    rooms = [
        ('점검관리방', int(env.get('TELEGRAM_CHECK_CHAT_ID', '-5136037543'))),
        ('문의알림방', int(env.get('TELEGRAM_INQUIRY_CHAT_ID', '-5516675010'))),
        ('종합접수처', int(env.get('TELEGRAM_RECEPTION_CHAT_ID', '-5065206276'))),
    ]

    all_issues: list[str] = []

    # 1. 봇 생존 + bot_id
    bot_id: int | None = None
    if not token:
        all_issues.append("TELEGRAM_BOT_TOKEN 미설정")
    else:
        try:
            alive, bot_id, detail = _get_bot_info(token)
            if not alive:
                all_issues.append(f"봇 생존 확인 실패: {detail}")
        except Exception as e:
            all_issues.append(f"봇 생존 확인 예외: {e}")

    # 2. 방 멤버십 (봇이 살아있고 bot_id 확보된 경우만)
    if token and bot_id is not None:
        try:
            all_issues.extend(_check_rooms(token, bot_id, rooms))
        except Exception as e:
            all_issues.append(f"방 멤버십 점검 예외: {e}")
    elif token and bot_id is None and not all_issues:
        all_issues.append("bot_id 획득 실패 — 방 멤버십 점검 건너뜀")

    # 3. 발송 원장 리컨실
    try:
        all_issues.extend(_check_log_failures())
    except Exception as e:
        all_issues.append(f"발송 원장 리컨실 예외: {e}")

    # 4. GAS 설정 진단 프로브 (VOC·Survey)
    try:
        all_issues.extend(_check_gas_diag())
    except Exception as e:
        all_issues.append(f"GAS 진단 프로브 예외: {e}")

    # 5. 결과 출력 및 경보
    if all_issues:
        today_str = datetime.date.today().strftime('%Y-%m-%d')
        alert_msg = (
            f"[텔레그램 헬스체크 경보] {today_str}\n"
            f"문제 {len(all_issues)}건 발견:\n"
            + '\n'.join(f"• {issue}" for issue in all_issues)
        )
        print(alert_msg, flush=True)
        headline = ' / '.join(all_issues[:2])
        summary = f"HEALTH: {len(all_issues)}건 - {headline}"
        print(summary, flush=True)
        if token and owner_id_str:
            _send_alert(token, int(owner_id_str), alert_msg, args.dry_run)
        else:
            print("[WARN] OWNER_ID 또는 TOKEN 없음 — 경보 발송 불가", flush=True)
    else:
        print("HEALTH: OK", flush=True)


if __name__ == '__main__':
    main()
