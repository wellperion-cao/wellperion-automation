"""읽기 전용 로컬 HTTP 서버 — 지금 GM PC 에서 Claude Code CLI 가 뭘 하고 있는지
세션 jsonl(C:\\Users\\jjky0\\.claude\\projects\\...\\<세션id>.jsonl)을 실시간으로 읽어
자율현황.html 맨 위 라이브 섹션에 뿌린다. 커밋·푸시 지연(raw.githubusercontent.com 경유,
몇 분~몇십 분) 없이 로컬에서 바로 본다(GM 지시 2026-08-15).

daily_scheduler.py 가 기동 시 데몬 스레드로 1회 띄운다 — 새 예약작업 없음(약속 L21).
쓰기·명령 실행 경로 없음(읽기 전용). 127.0.0.1 바인딩만 — 외부 접근 불가.
"""
from __future__ import annotations

import glob
import http.server
import json
import os
import re
import socketserver
import threading
from datetime import datetime, timezone

TRANSCRIPT_DIR = os.path.expanduser(
    r"~\.claude\projects\C--Users-jjky0-welperion-automation"
)
PORT = 8787
TAIL_BYTES = 300_000   # 파일 끝에서만 읽는다 — 세션 jsonl 은 수십MB 까지 큰다
HEAD_BYTES = 4_000     # 세션 시작시각 추정용(첫 줄만)
MAX_ITEMS = 25
BUSY_WINDOW_SEC = 60

# ── 비밀 마스킹 ────────────────────────────────────────────────────────────
_SECRET_RE = re.compile(
    r'(?i)(token|password|passwd|secret|api[_-]?key|authorization)\s*[:=]\s*["\']?([^\s"\',}]{4,})'
)
_BEARER_RE = re.compile(r'(?i)bearer\s+[a-z0-9._-]{10,}')
_LONGTOKEN_RE = re.compile(r'\b[a-zA-Z0-9_-]{32,}\b')


def _mask(s: str) -> str:
    if not s:
        return s
    s = _SECRET_RE.sub(lambda m: m.group(1) + '=***', s)
    s = _BEARER_RE.sub('Bearer ***', s)
    s = _LONGTOKEN_RE.sub(lambda m: m.group(0)[:6] + '...', s)
    return s


def _clip(s, n: int = 120) -> str:
    s = _mask(str(s or '').replace('\n', ' ').strip())
    return (s[:n] + '…') if len(s) > n else s


def _latest_session():
    files = glob.glob(os.path.join(TRANSCRIPT_DIR, '*.jsonl'))
    if not files:
        return None
    return max(files, key=os.path.getmtime)


def _tool_summary(name, inp) -> str:
    inp = inp or {}
    target = (inp.get('file_path') or inp.get('path') or inp.get('pattern')
              or inp.get('command') or inp.get('description') or inp.get('query') or '')
    return _clip('도구 ' + str(name) + ' — ' + str(target))


def _read_tail_lines(path):
    size = os.path.getsize(path)
    with open(path, 'rb') as f:
        if size > TAIL_BYTES:
            f.seek(size - TAIL_BYTES)
            f.readline()  # 중간에서 잘린 첫 줄은 버린다
        else:
            f.seek(0)
        raw = f.read()
    return [ln for ln in raw.decode('utf-8', errors='ignore').splitlines() if ln.strip()]


def _read_head_timestamp(path):
    try:
        with open(path, 'rb') as f:
            raw = f.read(HEAD_BYTES)
        for line in raw.decode('utf-8', errors='ignore').splitlines():
            try:
                o = json.loads(line)
            except Exception:
                continue
            if o.get('timestamp'):
                return o['timestamp']
    except Exception:
        pass
    return None


def _events_from_lines(lines):
    """jsonl 줄들 → (timestamp, 종류, 한줄요약) 리스트. 종류 = 지시/도구/응답."""
    events = []
    for line in lines:
        try:
            o = json.loads(line)
        except Exception:
            continue
        t = o.get('type')
        ts = o.get('timestamp')
        content = o.get('message', {}).get('content') if isinstance(o.get('message'), dict) else None
        if t == 'user':
            if isinstance(content, str) and content.strip():
                events.append((ts, '지시', _clip(content)))
            elif isinstance(content, list):
                for c in content:
                    if isinstance(c, dict) and c.get('type') == 'text' and c.get('text', '').strip():
                        events.append((ts, '지시', _clip(c['text'])))
        elif t == 'assistant' and isinstance(content, list):
            for c in content:
                if not isinstance(c, dict):
                    continue
                if c.get('type') == 'tool_use':
                    events.append((ts, '도구', _tool_summary(c.get('name'), c.get('input'))))
                elif c.get('type') == 'text' and c.get('text', '').strip():
                    events.append((ts, '응답', _clip(c['text'])))
    return events


def _build_payload():
    path = _latest_session()
    if not path:
        return {'busy': False, 'items': [], 'session_started': None, 'last_activity_at': None}
    events = _events_from_lines(_read_tail_lines(path))[-MAX_ITEMS:]
    events.sort(key=lambda e: e[0] or '')
    last_ts = events[-1][0] if events else None
    busy = False
    if last_ts:
        try:
            dt = datetime.fromisoformat(last_ts.replace('Z', '+00:00'))
            busy = (datetime.now(timezone.utc) - dt).total_seconds() < BUSY_WINDOW_SEC
        except Exception:
            pass
    return {
        'session_started': _read_head_timestamp(path),
        'last_activity_at': last_ts,
        'busy': busy,
        'items': [{'ts': ts, 'kind': kind, 'text': text} for ts, kind, text in events],
    }


class _Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass  # 콘솔·로그 스팸 방지 — 3초 폴링이라 시끄럽다

    def do_GET(self):
        if self.path.rstrip('/') != '/live':
            self.send_response(404)
            self.end_headers()
            return
        try:
            body = json.dumps(_build_payload(), ensure_ascii=False).encode('utf-8')
            self.send_response(200)
        except Exception as exc:  # noqa: BLE001 — 읽기 실패해도 서버는 계속 산다
            body = json.dumps({'error': str(exc)}, ensure_ascii=False).encode('utf-8')
            self.send_response(500)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def start_server(logger=None):
    """daily_scheduler.py 기동 시 1회 호출. 데몬 스레드라 스케줄러 종료 시 같이 죽는다.
    실패해도 예외를 삼키고 None 을 돌려준다 — 스케줄러 본 기능은 이 서버 없이도 산다."""
    try:
        httpd = socketserver.TCPServer(('127.0.0.1', PORT), _Handler)
        httpd.allow_reuse_address = True
        threading.Thread(target=httpd.serve_forever, name='live-cli-status', daemon=True).start()
        (logger.info if logger else print)(f"[live_cli_status_server] 기동 완료 http://127.0.0.1:{PORT}/live")
        return httpd
    except Exception as exc:  # noqa: BLE001
        (logger.warning if logger else print)(f"[live_cli_status_server] 기동 실패(무시하고 계속): {exc}")
        return None


def _selftest():
    assert '***' in _mask('token=abcd1234efgh5678'), '토큰 마스킹 실패'
    assert _clip('가나다라마바사 ' * 30).endswith('…'), '120자 클립 실패'
    sample = json.dumps({
        'type': 'assistant', 'timestamp': '2026-08-15T00:00:00Z',
        'message': {'content': [{'type': 'tool_use', 'name': 'Read', 'input': {'file_path': 'x.py'}}]},
    })
    ev = _events_from_lines([sample])
    assert ev and ev[0][1] == '도구' and 'Read' in ev[0][2], f'이벤트 추출 실패: {ev}'
    print('selftest OK')


if __name__ == '__main__':
    import sys
    if '--selftest' in sys.argv:
        _selftest()
    else:
        start_server()
        print(json.dumps(_build_payload(), ensure_ascii=False, indent=2))
