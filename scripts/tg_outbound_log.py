# -*- coding: utf-8 -*-
"""텔레그램 발신 메시지 공용 로깅 + 30일 자동 정리.
best-effort: 로깅 실패가 실제 발신을 절대 막지 않는다(전부 예외 무시)."""
import os, json, glob, datetime, time

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

# ── 전역 발송 페이싱 (프로세스 간) — 텔레그램 429 플러드 근본차단 (2026-07-16 CMO 배1198) ──
# 여러 루틴이 한 봇 토큰으로 발송 → 버스트 시 429(연장 페널티까지). 파일락 + 마지막 발송 시각으로
# 프로세스 간 최소 간격을 강제한다. best-effort: 락/파일 실패해도 실제 발송은 절대 막지 않는다.
_LAST_SEND_FILE = os.path.join(_LOG_DIR, '.tg_last_send')
_LOCK_FILE = os.path.join(_LOG_DIR, '.tg_send.lock')
_MIN_INTERVAL = 1.2  # 초 — 텔레그램 그룹 안전 페이스(초당 1건 미만)

def pace(min_interval=_MIN_INTERVAL):
    """직전 전역 발송 이후 min_interval 초 경과를 보장(프로세스 간 직렬화). 발송 '직전'에 호출."""
    try:
        os.makedirs(_LOG_DIR, exist_ok=True)
        f = open(_LOCK_FILE, 'a+b')
    except Exception:
        return
    locked = False
    try:
        try:
            import msvcrt
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_LOCK, 1)  # 배타 락(블로킹·~10s 후 예외)
            locked = True
        except Exception:
            locked = False  # 락 실패 → 페이싱만 스킵(발송은 진행)
        last = 0.0
        try:
            with open(_LAST_SEND_FILE) as tf:
                last = float((tf.read() or '0').strip())
        except Exception:
            last = 0.0
        gap = time.time() - last
        if 0 <= gap < min_interval:
            time.sleep(min_interval - gap)
        try:
            with open(_LAST_SEND_FILE, 'w') as tf:
                tf.write(str(time.time()))
        except Exception:
            pass
    finally:
        if locked:
            try:
                import msvcrt
                f.seek(0)
                msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
            except Exception:
                pass
        try:
            f.close()
        except Exception:
            pass


def send(token, chat_id, text, source='', kind='sendMessage', extra=None,
         min_interval=_MIN_INTERVAL, max_attempts=6, timeout=15):
    """페이싱 + 429 자가재시도(retry_after 존중) + 로깅 통합 발송. return ok(bool).
    각 루틴이 자체 urlopen 대신 이 함수를 쓰면 전역 페이싱에 자동 편입된다."""
    import urllib.request, urllib.parse, urllib.error
    payload = {'chat_id': chat_id, 'text': text}
    if extra:
        payload.update(extra)
    data = urllib.parse.urlencode(payload).encode('utf-8')
    url = 'https://api.telegram.org/bot%s/sendMessage' % token
    ok = False
    for attempt in range(max_attempts):
        pace(min_interval)
        try:
            req = urllib.request.Request(url, data=data, method='POST')
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                ok = (resp.status == 200)
                break
        except urllib.error.HTTPError as ex:
            if ex.code == 429 and attempt < max_attempts - 1:
                ra = 3
                try:
                    ra = int(json.loads(ex.read().decode()).get('parameters', {}).get('retry_after', 3))
                except Exception:
                    pass
                time.sleep(min(ra + 2 * (attempt + 1), 60))
                continue
            break
        except Exception:
            break
    try:
        log_outbound(text, chat_id=chat_id, source=source, ok=ok, kind=kind)
    except Exception:
        pass
    return ok


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
