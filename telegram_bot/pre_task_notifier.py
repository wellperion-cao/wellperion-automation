# pre_task_notifier.py
# 업무자동화 DB 보류 레코드 H-15분 사전 알림 — AI CTO v1.1
# 2026-04-21 / 2026-05-22 보류 옵션 폐기, 보류 단일 휴면 상태로 통합

import sys
import os
import re
import logging
from datetime import datetime, timezone, timedelta

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

import requests

# ── 환경 변수 ──────────────────────────────────────────────────────────────────
NOTION_TOKEN   = os.getenv('NOTION_TOKEN') or os.getenv('NOTION_API_KEY')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
OWNER_ID       = os.getenv('OWNER_ID')

AUTOMATION_DB_ID = os.getenv('NOTION_AUTOMATION_DB_ID', 'aac275a4-fd54-4d97-8971-4f7050de4f6e')

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

# ── Notion API 헬퍼 ───────────────────────────────────────────────────────────
NOTION_HEADERS = {
    'Authorization': f'Bearer {NOTION_TOKEN}',
    'Notion-Version': '2022-06-28',
    'Content-Type': 'application/json',
}

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


def fetch_scheduled_records() -> list[dict]:
    """업무자동화 DB 상태=보류 레코드 전체 조회"""
    resp = requests.post(
        f'https://api.notion.com/v1/databases/{AUTOMATION_DB_ID}/query',
        headers=NOTION_HEADERS,
        json={
            'filter': {
                'property': '상태',
                'select': {'equals': '보류'}
            },
            'page_size': 50,
        },
        timeout=15
    )
    if resp.status_code != 200:
        logger.error(f'업무자동화 DB 쿼리 실패: {resp.status_code}')
        return []
    results = []
    for r in resp.json().get('results', []):
        props = r.get('properties', {})
        def pt(key):
            p = props.get(key, {})
            t = p.get('type', '')
            if t == 'title':
                return ''.join(x['plain_text'] for x in p.get('title', []))
            elif t == 'rich_text':
                return ''.join(x['plain_text'] for x in p.get('rich_text', []))
            elif t == 'select':
                s = p.get('select')
                return s['name'] if s else ''
            return ''
        results.append({
            'id': r['id'],
            'name': pt('업무명') or pt('Name') or pt('이름'),
            'exec_time': pt('실행 시간'),
            'clevel': pt('담당 C-Level') or pt('담당'),
        })
    return results


def send_telegram(msg: str) -> bool:
    if not TELEGRAM_TOKEN or not OWNER_ID:
        return False
    try:
        resp = requests.post(
            f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage',
            json={'chat_id': OWNER_ID, 'text': msg},
            timeout=10
        )
        return resp.status_code == 200
    except Exception as e:
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

    records = fetch_scheduled_records()
    logger.info(f'보류 레코드 {len(records)}건 조회')

    today_str = now.strftime('%Y-%m-%d')
    notified_count = 0

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

        # 오늘 이미 알림 발송한 경우 스킵
        if _already_notified(page_id, today_str):
            logger.info(f'[스킵] 이미 알림 발송: {name}')
            continue

        _, hour, minute = parsed
        exec_time_str = f'{hour:02d}:{minute:02d}'

        msg = (
            f'[AI CTO → CEO] 업무자동화 진행 요청\n\n'
            f'레코드: {name}\n'
            f'담당: {clevel}\n'
            f'예정 실행 시각: {exec_time_str} KST (약 15분 후)\n\n'
            f'CEO께서 해당 레코드 상태를 진행중으로 변경해 주시면\n'
            f'auto_task_watcher가 자동 감지하여 에이전트를 기동합니다.\n\n'
            f'[자체 결정] AI CTO — H-15분 사전 알림 v1.0'
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
