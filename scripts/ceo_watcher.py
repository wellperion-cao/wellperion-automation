"""
AI CEO 깨어남 watcher.
15초 polling으로 status/_queue.json 큐 미처리 항목 처리.
"""
import json
import os
import subprocess
import time
import logging
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
import requests

PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(PROJECT_ROOT / 'telegram_bot' / '.env')

STATUS_DIR = PROJECT_ROOT / 'status'
QUEUE_PATH = STATUS_DIR / '_queue.json'
LOG_PATH = STATUS_DIR / '_ceo_log.jsonl'
CEO_META_PATH = STATUS_DIR / 'ceo.json'

POLL_INTERVAL = 15  # seconds
TELEGRAM_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
CHAT_ID = '8254867551'

logger = logging.getLogger('ceo_watcher')
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    handlers=[logging.StreamHandler(), logging.FileHandler(STATUS_DIR / 'watcher.log', encoding='utf-8')]
)


def load_queue() -> list:
    if not QUEUE_PATH.exists():
        return []
    try:
        return json.loads(QUEUE_PATH.read_text(encoding='utf-8'))
    except Exception as e:
        logger.warning(f'큐 로드 실패: {e}')
        return []


def save_queue(queue: list):
    QUEUE_PATH.write_text(json.dumps(queue, ensure_ascii=False, indent=2), encoding='utf-8')


def load_logged_ids() -> set:
    if not LOG_PATH.exists():
        return set()
    ids = set()
    try:
        for line in LOG_PATH.read_text(encoding='utf-8').splitlines():
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
                ids.add(entry.get('task_id'))
            except Exception:
                continue
    except Exception as e:
        logger.warning(f'로그 로드 실패: {e}')
    return ids


def append_log(entry: dict):
    entry['logged_at'] = datetime.now().isoformat()
    with LOG_PATH.open('a', encoding='utf-8') as f:
        f.write(json.dumps(entry, ensure_ascii=False) + '\n')


def update_ceo_meta(**kwargs):
    try:
        meta = json.loads(CEO_META_PATH.read_text(encoding='utf-8'))
    except Exception:
        meta = {'clevel': 'ceo', 'status': 'IDLE'}
    meta.update(kwargs)
    CEO_META_PATH.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding='utf-8')


def verify_layer1(task: dict) -> tuple[bool, str]:
    """1층 기계 검증 — 커밋 존재 + SSOT 중복 grep (스켈레톤)."""
    sha = task.get('commit_sha')
    if not sha:
        return False, 'commit_sha 없음'
    try:
        result = subprocess.run(
            ['git', 'show', '--quiet', sha],
            capture_output=True, timeout=10, cwd=str(PROJECT_ROOT)
        )
        if result.returncode != 0:
            return False, f'커밋 미존재: {sha[:8]}'
    except Exception as e:
        return False, f'git show 실패: {e}'
    return True, 'OK'


def verify_layer2(task: dict) -> tuple[bool, str]:
    """2층 AI 검증 — 원칙 위반·의도 부합 (Claude CLI 통합 추후)."""
    # 스켈레톤: 일단 통과
    return True, 'AI 검증 skeleton (Claude CLI 통합 예정)'


def notify_telegram(text: str) -> bool:
    if not TELEGRAM_TOKEN:
        logger.warning('TELEGRAM_BOT_TOKEN 미설정')
        return False
    try:
        r = requests.post(
            f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage',
            json={'chat_id': CHAT_ID, 'text': text},
            timeout=10,
        )
        return r.status_code == 200
    except Exception as e:
        logger.warning(f'텔레그램 송부 실패: {e}')
        return False


def process_task(task: dict, logged: set) -> bool:
    """단일 task 처리. 처리 시 True 반환."""
    tid = task.get('task_id')
    if not tid:
        return True  # 무효한 task는 큐에서 제거
    if tid in logged:
        logger.info(f'헛깨움 방지: {tid} 이미 LOGGED')
        return True

    clevel = task.get('clevel', 'unknown')
    sha = task.get('commit_sha', '')

    # 1층 기계 검증
    ok1, msg1 = verify_layer1(task)
    if not ok1:
        append_log({
            'task_id': tid, 'clevel': clevel, 'result': 'REJECTED',
            'layer': 1, 'reason': msg1, 'commit_sha': sha
        })
        notify_telegram(
            f'[CEO 검증 반려] {clevel} {tid}\n'
            f'1층 기계 실패: {msg1}\n'
            f'자동 재작업 금지. GM 결재 후 재시작.'
        )
        return True

    # 2층 AI 검증
    ok2, msg2 = verify_layer2(task)
    if not ok2:
        append_log({
            'task_id': tid, 'clevel': clevel, 'result': 'REJECTED',
            'layer': 2, 'reason': msg2, 'commit_sha': sha
        })
        notify_telegram(
            f'[CEO 검증 반려] {clevel} {tid}\n'
            f'2층 AI 실패: {msg2}\n'
            f'자동 재작업 금지. GM 결재 후 재시작.'
        )
        return True

    # 통과 → VERIFIED
    append_log({
        'task_id': tid, 'clevel': clevel, 'result': 'VERIFIED',
        'commit_sha': sha
    })
    notify_telegram(
        f'[CEO 검증 통과] {clevel} {tid}\n'
        f'commit {sha[:8]}'
    )
    return True


def main_loop():
    logger.info(f'AI CEO watcher 시작 (polling {POLL_INTERVAL}s)')
    STATUS_DIR.mkdir(exist_ok=True)
    update_ceo_meta(
        watcher_started_at=datetime.now().isoformat(),
        status='WATCHING'
    )
    while True:
        try:
            queue = load_queue()
            if queue:
                logged = load_logged_ids()
                update_ceo_meta(
                    last_trigger_at=datetime.now().isoformat(),
                    queue_unprocessed=len(queue)
                )
                task = queue[0]
                processed = process_task(task, logged)
                if processed:
                    queue.pop(0)
                    save_queue(queue)
                    update_ceo_meta(queue_unprocessed=len(queue))
        except Exception as e:
            logger.exception(f'루프 예외: {e}')
        time.sleep(POLL_INTERVAL)


if __name__ == '__main__':
    main_loop()
