# -*- coding: utf-8 -*-
"""텔레그램 발신 메시지 공용 로깅 + 30일 자동 정리.
best-effort: 로깅 실패가 실제 발신을 절대 막지 않는다(전부 예외 무시)."""
import os, json, glob, datetime

_LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'logs')
_RETAIN_DAYS = 30

def log_outbound(text, chat_id=None, source='', ok=None, kind='sendMessage'):
    try:
        os.makedirs(_LOG_DIR, exist_ok=True)
        now = datetime.datetime.now()
        path = os.path.join(_LOG_DIR, 'telegram_sent-%s.log' % now.strftime('%Y-%m-%d'))
        rec = {
            'ts': now.strftime('%Y-%m-%dT%H:%M:%S'),
            'source': source, 'chat_id': chat_id, 'kind': kind, 'ok': ok,
            'text': text if isinstance(text, str) else str(text),
        }
        with open(path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(rec, ensure_ascii=False) + '\n')
        _cleanup(now)
    except Exception:
        pass

def _cleanup(now):
    try:
        cutoff = now - datetime.timedelta(days=_RETAIN_DAYS)
        for p in glob.glob(os.path.join(_LOG_DIR, 'telegram_sent-*.log')):
            base = os.path.basename(p)[len('telegram_sent-'):-len('.log')]
            try:
                d = datetime.datetime.strptime(base, '%Y-%m-%d')
            except ValueError:
                continue
            if d < cutoff:
                os.remove(p)
    except Exception:
        pass
