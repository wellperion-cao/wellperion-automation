# -*- coding: utf-8 -*-
"""텔레그램 발신 메시지 공용 로깅 + 30일 자동 정리.
best-effort: 로깅 실패가 실제 발신을 절대 막지 않는다(전부 예외 무시)."""
import os, json, glob, datetime, time, re

_LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'logs')
_RETAIN_DAYS = 30

def log_outbound(text, chat_id=None, source='', ok=None, kind='sendMessage', channel='telegram'):
    """channel: 'telegram'(기본) → logs/telegram_sent-*.log / 'kakao' → logs/kakao_sent-*.log.
    배99(2026-07-25): 카톡도 하루 단위로 셀 수 있게 같은 관문 로거를 채널만 나눠 재사용(L21)."""
    try:
        os.makedirs(_LOG_DIR, exist_ok=True)
        now = datetime.datetime.now()
        path = os.path.join(_LOG_DIR, '%s_sent-%s.log' % (channel, now.strftime('%Y-%m-%d')))
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


# ── 발신 전 자동 검수 (2026-07-31 웰리) ────────────────────────────────
# 왜: 2026-07-31 하루에 실무진·GM 화면으로 나가는 메시지 결함 4건을 **전부 GM이 먼저 찾았다** —
#   ①08:00 보고에 마크다운 표 기호가 그대로 찍힘(텔레그램은 표를 못 그린다) ②문장이 날짜·약어의
#   마침표에서 잘림 ③목록 15줄을 한 방에 통째로 쏟음 ④내가 넣은 링크가 없는 페이지(404).
#   ①②④는 사람이 눈으로 볼 일이 아니라 기계가 보내기 전에 잡을 일이다.
# ▸새 감시기·새 예약을 만들지 않는다(약속 L21) — 이미 모든 발신이 지나가는 이 함수 안에서 잰다.
# ▸막지 않는다(1단계). 발신은 그대로 하고 status/outbound_lint.jsonl 에 적기만 한다 —
#   오탐이 남아 있는 채로 실무진 알림을 끊는 것이 더 나쁘다. 아침 자가점검이 이 기록을 읽는다.
#   무결이 쌓이면 그때 차단으로 올린다(라이브 검증 무조건 → 신뢰 후 점감).
_LINT_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          'status', 'outbound_lint.jsonl')
_MD_TABLE_RE = re.compile(r'^\s*\|[\s:|-]+\|\s*$', re.M)   # |---|---| 구분줄
_MD_EMPH_RE = re.compile(r'(\*\*[^*\n]{1,60}\*\*)|(_[^_\n]{1,60}_)')
_SENDER_HINT = ('웰리', '시우', '시포', '시모', '시토', '봇', 'AI')


def lint_outbound(text, chat_id, source=''):
    """보내기 전에 텍스트를 잰다. 반환 = 문제 목록(빈 리스트면 이상 없음).

    텔레그램에서 읽히게 만드는 수단은 줄바꿈·기호·들여쓰기뿐이다 — 표·굵게는 안 먹는다.
    """
    issues = []
    t = str(text or '')
    if _MD_TABLE_RE.search(t):
        issues.append({'kind': 'md_table', 'detail': '마크다운 표 구분줄 — 텔레그램에선 파이프 기호가 그대로 보인다'})
    m = _MD_EMPH_RE.search(t)
    if m and 'HTML' not in str(source):
        issues.append({'kind': 'md_emphasis', 'detail': '마크다운 강조 잔재 %r — 평문 발신이면 기호가 그대로 보인다' % (m.group(0)[:30],)})
    if len(t) > 4096:
        issues.append({'kind': 'too_long', 'detail': '%d자 — 4096자 상한 초과(분할 위치가 표·문단 중간이면 맥락이 끊긴다)' % len(t)})
    # 실무진 방(= 개인 DM 이 아닌 그룹)으로 나가는데 보낸이가 안 밝혀져 있으면 짚는다.
    try:
        is_group = int(str(chat_id)) < 0
    except Exception:
        is_group = False
    if is_group and not any(h in t[:400] for h in _SENDER_HINT):
        issues.append({'kind': 'no_sender', 'detail': '실무진 방인데 앞부분에 보낸이 표기가 없다 — 받는 사람이 어디에 답할지 모른다'})
    return issues


def _log_lint(issues, chat_id, source):
    if not issues:
        return
    try:
        os.makedirs(os.path.dirname(_LINT_PATH), exist_ok=True)
        with open(_LINT_PATH, 'a', encoding='utf-8') as f:
            f.write(json.dumps({
                'ts': time.strftime('%Y-%m-%dT%H:%M:%S'),
                'chat_id': str(chat_id), 'source': str(source),
                'issues': issues,
            }, ensure_ascii=False) + '\n')
    except Exception:
        pass   # 검수 실패가 발신을 막지 않는다


_URL_WITH_SPACE = re.compile(
    r'https?://[^\s]+(?:[ ][^\s]+)+?\.(?:html?|png|jpe?g|pdf|json|csv|xlsx?)\b')


def encode_url_spaces(text):
    """메시지 안의 링크에 낀 공백을 %20 으로 바꾼다.

    우리 페이지 경로에는 한글 공백이 흔하다(`.../coo/check/시설부 체계.html`).
    카톡·텔레그램은 공백에서 링크를 끊어 버려서 앞부분만 눌리고 404 가 난다.
    GM 이 같은 지적을 반복했다("또 시설부 체계 링크 짤리게 했네") — 보내는
    사람마다 손으로 인코딩하는 한 계속 샌다. 그래서 발신 관문에서 한 번 막는다.

    확장자로 끝나는 구간만 바꾼다 — "주소 뒤 문장"까지 삼키지 않게 하는 울타리다.
    """
    def _fix(m):
        return m.group(0).replace(' ', '%20')
    return _URL_WITH_SPACE.sub(_fix, str(text or ''))


def send(token, chat_id, text, source='', kind='sendMessage', extra=None,
         min_interval=_MIN_INTERVAL, max_attempts=6, timeout=15):
    """페이싱 + 429 자가재시도(retry_after 존중) + 로깅 통합 발송. return ok(bool).
    각 루틴이 자체 urlopen 대신 이 함수를 쓰면 전역 페이싱에 자동 편입된다."""
    import urllib.request, urllib.parse, urllib.error
    text = encode_url_spaces(text)
    _log_lint(lint_outbound(text, chat_id, source), chat_id, source)
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
                # ★2026-08-04 시토: HTTP 200 만으로는 부족하다 — 텔레그램 Bot API 는
                #   일부 검증 오류에서도 200 + {"ok": false} 를 돌려준다(문서화된 동작).
                #   status만 보면 그 실패가 '보냄'으로 로그에 남아 재시도가 안 걸린다
                #   (오늘 카톡 발신에서 같은 부류 버그 2건 잡음 — 배347/348). 응답 본문의
                #   ok 필드까지 확인해야 진짜 성공이다.
                body = resp.read().decode('utf-8', 'replace')
                ok = resp.status == 200 and json.loads(body).get('ok') is True
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
        for p in glob.glob(os.path.join(_LOG_DIR, '*_sent-*.log')):
            base = os.path.basename(p)[:-len('.log')].rsplit('_sent-', 1)[-1]
            try:
                d = datetime.datetime.strptime(base, '%Y-%m-%d')
            except ValueError:
                continue
            if d < cutoff:
                os.remove(p)
    except Exception:
        pass
