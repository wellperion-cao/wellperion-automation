# pre_task_notifier.py
# 정기 자동화 루틴 H-15분 사전 알림 — AI CTO v2.0
# 2026-04-21 / 2026-05-22 보류 옵션 폐기, 보류 단일 휴면 상태로 통합
#
# [2026-06-01 CTO 이관 완료 — status/schedule.json 소스 전환, 노션 의존 0]
#   본 알림기는 '실행 시간'(예: '매주 월요일 08:00') 필드 기준 H-15분 알람이 핵심.
#   데이터 소스를 레포 status/schedule.json (실행시간 SSOT)으로 전환했다.
#   schedule.json 스키마: sid(기존 page_id 보존) / name / exec_time(원문) / clevel.
#   sid는 state.json pre_task_notified 중복방지 키와 호환 유지(재발송 방지).
#   AUTOMATION-DB-MIGRATE 대체설계 1단계. 폴백·중복방지·파싱 로직은 그대로 재사용.

import sys
import os
import re
import json
import logging
import subprocess
from datetime import datetime, timezone, timedelta

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

import requests  # send_telegram 발송용

try:  # 발신 공용 로깅(best-effort) — 임포트 실패해도 발신 무영향
    _scr = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'scripts'))
    if _scr not in sys.path:
        sys.path.insert(0, _scr)
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

# ── 환경 변수 ──────────────────────────────────────────────────────────────────
TELEGRAM_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
OWNER_ID       = os.getenv('OWNER_ID')

# 실행시간 SSOT — 레포 status/schedule.json
SCHEDULE_FILE = os.path.normpath(
    os.path.join(os.path.dirname(__file__), '..', 'status', 'schedule.json')
)

KST = timezone(timedelta(hours=9))

# H-15분 알림 윈도우: 실행 시간 -15분 ±2분 (5분 폴링 주기 고려)
NOTIFY_BEFORE_MINUTES = 15
NOTIFY_WINDOW_MINUTES = 2   # ±2분 허용 (오버랩 방지)

# ── 로깅 ──────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    handlers=[
        logging.FileHandler(
            os.path.join(os.path.dirname(__file__), 'pre_task_notifier.log'),
            encoding='utf-8'
        ),
        logging.StreamHandler(sys.stdout),
    ]
)
logger = logging.getLogger(__name__)

WEEKDAY_KO_MAP = {
    '월요일': 1, '화요일': 2, '수요일': 3,
    '목요일': 4, '금요일': 5, '토요일': 6, '일요일': 7,
}


def parse_exec_schedule(text: str):
    """
    '매주 월요일 08:00 / 30분' → (isoweekday, hour, minute)
    '매일 09:00 / 15분' → (0, hour, minute)  # 0 = 매일
    '상시 ...' 등 비정기 → None (조용히 무시)
    """
    if not text:
        return None
    if text.startswith('상시') or '간격 폴링' in text or 'BIOS' in text:
        return None
    m = re.search(r'(\d{1,2}):(\d{2})', text)
    if not m:
        return None
    hour, minute = int(m.group(1)), int(m.group(2))
    if '매일' in text:
        return (0, hour, minute)
    dow = None
    for ko, num in WEEKDAY_KO_MAP.items():
        if ko in text:
            dow = num
            break
    if dow is None:
        return None
    return (dow, int(m.group(1)), int(m.group(2)))


def is_h15_window(exec_text: str, now: datetime) -> bool:
    """
    현재 시각이 실행 시간 H-15분 ±2분 윈도우 내인지 확인.
    [TEST] 태그 포함 시 요일 무관 현재 요일로 처리.
    """
    parsed = parse_exec_schedule(exec_text)
    if not parsed:
        return False
    dow, hour, minute = parsed

    is_test = '[TEST]' in exec_text
    if dow == 0:
        pass  # 매일 실행 — 요일 체크 불필요
    elif not is_test and now.isoweekday() != dow:
        return False

    # 실행 예정 시각 (당일)
    exec_dt = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    # H-15분 알림 목표 시각
    notify_dt = exec_dt - timedelta(minutes=NOTIFY_BEFORE_MINUTES)
    # 윈도우: notify_dt ±2분
    lo = notify_dt - timedelta(minutes=NOTIFY_WINDOW_MINUTES)
    hi = notify_dt + timedelta(minutes=NOTIFY_WINDOW_MINUTES)

    return lo <= now <= hi


# ── 교차검증 게이트(2026-07-30 시토·배39) ─────────────────────────────────────
#   실사고: schedule.json 항목 7건(대응하는 실제 Windows 예약작업이 없는 유령)에
#   대해 "곧 실행됩니다" 알림이 실제로 GM·C-레벨에게 나갔다(state.json 2026-07-05~06
#   발송 이력 실측). 원인 = 이 파일이 schedule.json 만 보고 "그 실행이 진짜 있는가"를
#   한 번도 확인하지 않았기 때문. 새 파일·새 검사기를 만들지 않고 이 소비처 하나
#   (약속 L21 — schedule.json 의 유일 소비자)에 발송 직전 존재확인만 끼워 넣는다.
_WEL_TASK_NAME_RE = re.compile(r'(?i)wel.?perion')  # Wellperion·Welperion(오타 L한개) 둘 다
_TOKEN_STOPWORDS = {'cto', 'cmo', 'coo', 'cpo', 'chro', 'cfo', 'ceo'}


def _fetch_windows_task_names():
    """Wellperion*·Welperion* 예약작업 이름 전체 조회.

    Get-ScheduledTask(CIM) 사용 — `schtasks /tn`의 'Access is denied'를 '작업 없음'으로
    오독하지 않기 위해서다(2026-07-30 배39 실측 교훈: 권한 오류를 없음으로 읽으면 없는
    버그를 보고하게 된다). 조회 자체가 실패하면 None을 반환한다 — 호출부는 None이면
    게이트를 건너뛰고 기존 동작(발송)을 유지해야 한다(조회 실패로 정상 알림까지
    끊기면 안 된다)."""
    try:
        # TaskName(리프 이름)뿐 아니라 TaskPath(폴더)도 본다 — \Welperion\Auto-Shutdown-2330
        # 처럼 이름 자체엔 Welperion이 없고 폴더에만 있는 작업이 있다(scripts/schedule_
        # inventory.py 와 동일 교훈, 2026-07-30 배39).
        ps_cmd = (
            "Get-ScheduledTask -ErrorAction Stop | "
            "Where-Object { $_.TaskName -match '(?i)wel.?perion' -or $_.TaskPath -match '(?i)wel.?perion' } | "
            "Select-Object -ExpandProperty TaskName"
        )
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
        )
        if result.returncode != 0:
            logger.warning(f'[게이트] Windows 예약작업 조회 실패(rc={result.returncode}) — 게이트 건너뜀(기존 발송 유지): {result.stderr.strip()[:200]}')
            return None
        names = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        return names
    except Exception as e:
        logger.warning(f'[게이트] Windows 예약작업 조회 예외 — 게이트 건너뜀(기존 발송 유지): {e}')
        return None


def _name_tokens(text: str) -> set:
    """비교용 토큰화 — 접두사(Wellperion-/Welperion-) 제거, 소문자, 비영숫자 분리,
    1자 이하·순수숫자·직함 불용어 제거(잡음 매칭 방지). 'AI'처럼 2자라도 이 저장소
    맥락에선 뜻있는 토큰이라 2자부터 허용한다(3자 컷은 'AI'만 지워 유효매칭을 깨뜨렸다
    — 2026-07-30 배39 dry-run 실측 중 발견·수정)."""
    t = _WEL_TASK_NAME_RE.sub('', text or '')
    toks = set(re.split(r'[^a-z0-9]+', t.lower()))
    return {w for w in toks if len(w) > 1 and not w.isdigit() and w not in _TOKEN_STOPWORDS}


def has_matching_scheduled_task(rec: dict, task_names) -> bool:
    """rec(schedule.json 항목)에 대응하는 실제 Windows 예약작업이 있는지 이름 기준으로
    판정한다. sid·name 양쪽에서 토큰을 뽑아 실제 작업명 토큰과 2개 이상 겹치면 '있음'.
    이 저장소의 sid 체계상 사람이 붙인 슬러그(예: cto-2026-06-23-ai-education-auto-learner)는
    실제 작업명(Wellperion-AI-Education-Weekly)과 토큰이 겹치고, 노션 이관 시절 UUID형
    sid(예: 3500407d-a948-...)는 애초에 의미있는 토큰이 없어 자동으로 매칭 실패(=스킵)
    한다 — 정확히 오늘 확인된 유령 7건이 이 경로로 걸러진다. 겹치는 게 없으면(확신
    없으면) '없음' 쪽으로 기울인다(보수적)."""
    if task_names is None:
        return True  # 조회 실패 — 게이트 무력화, 기존 발송 동작 유지
    cand = _name_tokens(str(rec.get('id', ''))) | _name_tokens(str(rec.get('name', '')))
    if not cand:
        return False  # 비교할 토큰 자체가 없음 — 확신 없으므로 보수적으로 '없음'
    for tn in task_names:
        if len(cand & _name_tokens(tn)) >= 2:
            return True
    return False


def fetch_scheduled_records() -> list[dict]:
    """status/schedule.json (실행시간 SSOT) 정기 루틴 레코드 전체 조회.

    반환 형식은 기존과 동일: list[dict] (키: id=sid, name, exec_time, clevel).
    파일이 없으면 [] 반환 + 경고 로그.
    """
    if not os.path.exists(SCHEDULE_FILE):
        logger.warning(f'schedule.json 없음: {SCHEDULE_FILE}')
        return []
    try:
        with open(SCHEDULE_FILE, encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        logger.error(f'schedule.json 로드 실패: {e}')
        return []
    results = []
    for r in data:
        results.append({
            'id': r.get('sid', ''),
            'name': r.get('name', ''),
            'exec_time': r.get('exec_time', ''),
            'clevel': r.get('clevel', ''),
        })
    return results


def send_telegram(msg: str) -> bool:
    if not TELEGRAM_TOKEN or not OWNER_ID:
        return False
    try:
        pace()
        resp = requests.post(
            f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage',
            json={'chat_id': OWNER_ID, 'text': msg},
            timeout=10
        )
        log_outbound(msg, chat_id=OWNER_ID, source='pre_task_notifier.send_telegram', ok=(resp.status_code == 200), kind='sendMessage')
        return resp.status_code == 200
    except Exception as e:
        log_outbound(msg, chat_id=OWNER_ID, source='pre_task_notifier.send_telegram', ok=False, kind='sendMessage')
        logger.error(f'텔레그램 발송 실패: {e}')
        return False


# ── state.json — 중복 알림 방지 ───────────────────────────────────────────────
STATE_FILE = os.path.join(os.path.dirname(__file__), 'state.json')


def _load_state() -> dict:
    try:
        import json
        with open(STATE_FILE, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def _save_state(state: dict):
    import json
    try:
        with open(STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f'state.json 저장 실패: {e}')


def _already_notified(page_id: str, notify_date: str) -> bool:
    """동일 레코드에 오늘 이미 H-15분 알림을 발송했는지 확인"""
    state = _load_state()
    notified = state.get('pre_task_notified', {})
    return notified.get(page_id) == notify_date


def _mark_notified(page_id: str, notify_date: str):
    import json
    state = _load_state()
    notified = state.get('pre_task_notified', {})
    notified[page_id] = notify_date
    state['pre_task_notified'] = notified
    _save_state(state)


# ── 메인 체크 함수 ────────────────────────────────────────────────────────────
def check_and_notify():
    """
    5분 주기로 호출. 보류 레코드 중 H-15분 윈도우 진입 시
    CEO에게 텔레그램 '진행 요청' 알림 발송.
    """
    now = datetime.now(KST)
    logger.info('=== pre_task_notifier 체크 시작 ===')

    if muted('pre_task'):
        logger.info('[무음] pre_task 저신호 설정 — 사전 알림 발송 스킵 (notify_prefs.py)')
        return 0

    records = fetch_scheduled_records()
    logger.info(f'보류 레코드 {len(records)}건 조회')

    today_str = now.strftime('%Y-%m-%d')
    notified_count = 0

    # 교차검증 게이트용 — 5분마다 매번 PowerShell 을 돌리지 않게 실제로 H-15 창에
    # 걸린 레코드가 나올 때만 지연 조회한다(1회만, 이 함수 호출 안에서 캐시).
    task_names_cache = {}

    def _task_names():
        if 'v' not in task_names_cache:
            tn = _fetch_windows_task_names()
            if tn is None:
                logger.warning('[게이트] Windows 예약작업 조회 불가 — 이번 회차는 교차검증 없이 기존 동작으로 진행')
            else:
                logger.info(f'[게이트] Windows 예약작업 {len(tn)}건 조회(Wellperion+Welperion)')
            task_names_cache['v'] = tn
        return task_names_cache['v']

    for rec in records:
        exec_text = rec.get('exec_time', '')
        page_id   = rec['id']
        name      = rec.get('name', '(이름 없음)')
        clevel    = rec.get('clevel', '?')

        if not exec_text:
            continue

        parsed = parse_exec_schedule(exec_text)
        if not parsed:
            continue

        if not is_h15_window(exec_text, now):
            continue

        # 교차검증 게이트 — 대응하는 실제 Windows 예약작업이 없으면 발송하지 않는다
        # (2026-07-30 배39: 유령 7건 실오발송 확인 후 신설). 조회 실패 시엔 통과(기존 동작).
        if not has_matching_scheduled_task(rec, _task_names()):
            logger.info(f'[게이트 스킵] 대응 Windows 예약작업 없음 — 발송 안 함: {name} (sid={page_id})')
            continue

        # 오늘 이미 알림 발송한 경우 스킵
        if _already_notified(page_id, today_str):
            logger.info(f'[스킵] 이미 알림 발송: {name}')
            continue

        _, hour, minute = parsed
        exec_time_str = f'{hour:02d}:{minute:02d}'

        msg = (
            f'[AI CTO → CEO] 업무자동화 사전 알림\n\n'
            f'루틴: {name}\n'
            f'담당: {clevel}\n'
            f'예정 실행 시각: {exec_time_str} KST (약 15분 후)\n\n'
            f'정기 루틴 실행 사전 안내입니다. (실행 트리거=작업 스케줄러 자동)\n\n'
            f'[자체 결정] AI CTO — H-15분 사전 알림 v1.1'
        )

        ok = send_telegram(msg)
        if ok:
            _mark_notified(page_id, today_str)
            logger.info(f'[알림 발송] {name} | 실행 {exec_time_str} H-15분')
            notified_count += 1
        else:
            logger.error(f'알림 발송 실패: {name}')

    logger.info(f'=== pre_task_notifier 체크 완료: 발송 {notified_count}건 ===')
    return notified_count


if __name__ == '__main__':
    check_and_notify()
