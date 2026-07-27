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
    "AKfycbykgMyFc-g_KG7x3HoKStKBwerKhYYfmbqNeFqCL5O1b_4-1nng4wEiKhkNJtfB4BWo/exec"
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
        # [2026-07-27 시모] 퍼널 GAS 만 hasToken/hasChatId 진단이 없어, 문의 알림 백엔드의
        #   봇 토큰이 아예 없어도 아무도 모르는 상태였다. 실측으로 드러난 실제 값 = hasToken:false
        #   (즉 v2 는 텔레그램을 못 보낸다 — 트리거만 옮겼으면 문의 알림이 전부 끊겼을 상황).
        #   같은 계약을 퍼널에도 채워 다른 GAS 와 동일하게 판정한다.
        ("Survey GAS 알림설정", _FUNNEL_DIAG_URL, "diag_notify_config", ["hasToken", "hasChatId"]),
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
            # [배140 · 2026-07-27 시모] 문의 알림 '도착 확인' — 지금까지 사각지대였다.
            #   개별 문의 알림은 GAS 가 텔레그램으로 직접 쏘므로 이 저장소 발신 원장에 안 남는다.
            #   → 봇·방·로컬 원장만 보던 이 헬스체크는 "알림이 안 가도 모르는" 상태였다.
            #   diag_inquiry_state 가 이미 돌려주는 INQ_LASTROW 마커를 판정에 쓰면 새 장치 없이
            #   그 사각지대가 메워진다(약속 L21 — 이미 지나가는 관문에 흡수).
            #   marker_value=null  → 알림 파이프가 이 백엔드에서 한 번도 돈 적 없음(치명)
            #   marker_vs_real≤-3 → 실데이터가 마커보다 앞섬 = 그만큼 미발송 적체
            for sh in (data.get("sheets") or []):
                if sh.get("real_lastDataRow") is None:
                    continue                      # 데이터가 아예 없는 시트는 판정 대상 아님
                stype = sh.get("type") or "?"
                if sh.get("marker_value") is None:
                    issues.append(
                        f"{name} 문의알림 마커 미설정({stype}) — 이 백엔드에서 알림 파이프가 "
                        "한 번도 돌지 않음(트리거 미설치 의심). 알림이 다른 스크립트에서 나가는지 확인 요망"
                    )
                    continue
                lag = sh.get("marker_vs_real")
                if isinstance(lag, (int, float)) and lag <= -3:
                    issues.append(
                        f"{name} 문의알림 적체({stype}) — 마커가 실데이터보다 {abs(int(lag))}행 뒤짐"
                        f"(마지막 접수 {sh.get('real_lastDataTs')}). 미발송 가능성"
                    )
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


# ── 점검 5: 봇 폴링 하트비트 (2026-07-03 CTO, 배102) ─────────────────────────
# getMe(점검 1)는 텔레그램 API 도달성만 확인 — 실제 run_polling() 이 살아서
# 수신 중인지는 모른다(오늘 Bad Gateway 로 폴링이 죽었는데도 getMe 는 OK 였음).
# bot.py 가 5분마다 telegram_bot/bot_heartbeat.txt 를 갱신 — 20분(4회) 이상
# 미갱신이면 폴링 정지 의심으로 경보. 파일 자체가 없으면(이 배포 이후 봇
# 미재기동) 오탐 방지 위해 경보에서 제외하고 안내만 출력한다.
_HEARTBEAT_PATH = os.path.join(_ROOT_DIR, 'telegram_bot', 'bot_heartbeat.txt')
_HEARTBEAT_STALE_MIN = 20


def _check_heartbeat(now: datetime.datetime | None = None) -> list[str]:
    """하트비트 파일 신선도 점검 → 문제 목록 반환(정상/미도입 시 빈 리스트)."""
    now = now or datetime.datetime.now()
    if not os.path.exists(_HEARTBEAT_PATH):
        print(
            "[INFO] 하트비트 파일 없음 — 봇 미재기동(하트비트 미도입 상태), 경보 제외",
            flush=True,
        )
        return []
    try:
        with open(_HEARTBEAT_PATH, encoding='utf-8') as f:
            ts = datetime.datetime.fromisoformat(f.read().strip())
    except Exception as e:
        return [f"하트비트 파일 파싱 실패: {e}"]

    age_min = (now - ts).total_seconds() / 60
    if age_min > _HEARTBEAT_STALE_MIN:
        return [
            f"🔴 봇 폴링 의심 정지 — 하트비트 {age_min:.0f}분째 미갱신 (bot.py 재기동 필요)"
        ]
    return []


# ── 점검 6: GAS 버전 위생 (2026-07-18 CTO) ───────────────────────────────────
# funnel GAS가 200버전 하드리밋에 걸려 배포가 막힌 사고 재발방지 — 5개 GAS
# 프로젝트의 배포 버전수를 조회해 임계(>=180)일 때만 경보 흐름에 합류시킨다.
# 새 정기 알림 채널이 아니라 기존 13시 헬스체크에 얹는 방식(GM 알림 과부하 방지).
def _check_gas_versions() -> list[str]:
    """gas_version_monitor 임계(>=180) 결과만 문제 목록에 반영.
    조회 실패는 오탐 방지 위해 WARN 로그만(경보 제외)."""
    try:
        sys.path.insert(0, _SCRIPT_DIR)
        from gas_version_monitor import collect as _gas_collect
        from gas_version_monitor import _ALERT_THRESHOLD, _HARD_LIMIT
    except ImportError as e:
        print(f"[WARN] gas_version_monitor 임포트 실패: {e}", flush=True)
        return []

    try:
        results = _gas_collect()
    except Exception as e:
        print(f"[WARN] GAS 버전 조회 예외: {e} — 네트워크 이상(경보 제외)", flush=True)
        return []

    # 하트비트(배1307 5차) — collect() 성공 = 실제 결과 산출 시점(임계 초과 여부와 무관).
    try:
        from module_heartbeat import record_heartbeat
        record_heartbeat("cto-gas-version-monitor",
                          detail=f"{len(results)}개 프로젝트 조회")
    except Exception:
        pass  # 하트비트 실패가 헬스체크 본 작업을 막지 않는다(fail-soft)

    # [2026-07-21 병합] gas 버전경보는 self_health_watchdog 일일 디제스트로 이관, 역롤백=주석해제
    # issues: list[str] = []
    # for r in results:
    #     count = r.get('version_count')
    #     if count is None:
    #         print(f"[WARN] {r['project']} 버전 조회 실패 — 경보 제외", flush=True)
    #         continue
    #     if count >= _ALERT_THRESHOLD:
    #         issues.append(f"⚠️ GAS 버전 임박: {r['project']} {count}/{_HARD_LIMIT}")
    # return issues
    return []


# ── 기본 점검 방 목록 (self_health_watchdog 재사용용으로 추출 · 동작 불변) ────────
# [2026-07-22 배9420 확장·CTO] main() 인라인 리스트를 함수로 추출만 함(로직·기본값 불변).
# self_health_watchdog.py 가 이 함수를 그대로 import 해 봇 폴링/방 멤버십 점검을
# 재수집 없이 재사용한다(중복 정의 금지).
def _default_rooms(env: dict) -> list[tuple[str, int]]:
    """헬스체크 대상 3개 그룹방 목록(env 오버라이드 지원, 기본값은 main()과 동일)."""
    return [
        ('점검관리방', int(env.get('TELEGRAM_CHECK_CHAT_ID', '-5136037543'))),
        ('문의알림방', int(env.get('TELEGRAM_INQUIRY_CHAT_ID', '-5516675010'))),
        ('종합접수처', int(env.get('TELEGRAM_RECEPTION_CHAT_ID', '-5065206276'))),
    ]


# ── 경보 발송 ─────────────────────────────────────────────────────────────────
def _send_alert(token: str, owner_id: int, message: str, dry_run: bool) -> None:
    """경보 발송. dry_run=True 면 stdout만.

    ★2026-07-24 GM 지시로 **확인방(자동화현황방)** 으로 보낸다 — 예전엔 GM 업무보고방이었다.
      헬스체크 경보는 'GM 이 손으로 할 일'이 아니라 '기계가 스스로 확인한 결과'다.
      GM 업무보고방에 섞이면 정작 GM 이 결정해야 할 건이 묻힌다.
      분류 판단은 scripts/alert_router.py 한 곳에서만 한다(약속 L01).
    """
    try:
        from alert_router import TECH_CHECK, route
        owner_id = route(TECH_CHECK)
    except Exception as _exc:  # 라우터를 못 읽으면 원래 대상으로 보낸다(알림을 잃지 않는다)
        print(f"[WARN] 알림 라우터 사용 불가 — 기존 대상 유지: {_exc}", flush=True)
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
    rooms = _default_rooms(env)

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

    # 5. 봇 폴링 하트비트 (getMe 사각지대 보완)
    try:
        all_issues.extend(_check_heartbeat())
    except Exception as e:
        all_issues.append(f"하트비트 점검 예외: {e}")

    # 6. GAS 버전 위생 (임계 미만이면 무발신 — 새 정기 알림 아님)
    try:
        all_issues.extend(_check_gas_versions())
    except Exception as e:
        all_issues.append(f"GAS 버전 점검 예외: {e}")

    # 7. 결과 출력 및 경보
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
