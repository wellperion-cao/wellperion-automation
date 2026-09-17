"""C레벨 관제판 활동 푸시 — GM PC 의 각 C레벨 창 대화 기록(jsonl)을 3초마다 읽어 새 활동(지시·응답)을 서버로 보낸다.
배 12723 3차 · GM 2026-09-17 「AWS 라서 라이브 되지 않나 · 직관적이고 액티비티하게」.

  어느 jsonl 이 어느 창인지 = status/sessions/.sid_{role}(worklog 접수 훅이 세션 id 를 적는다).
  파서 = scripts/live_cli_status_server._events_from_lines 그대로(8787 로컬 라이브와 같은 눈) · 값은 _mask 로 가린다.
  도구 호출은 보내지 않는다(GM 은 비개발자 · 2026-08-18 결정) — 대신 마지막 도구 시각을 busy_at 으로 보내 「작업 중」 불이 켜진다.
  보내는 곳 = POST https://erp.wellperion.com/api/console/event · 열쇠 헤더 X-Token-Push-Key(~/.claude/token_push.key).
  실행 = daily_scheduler 데몬 스레드(start_pusher) 또는 단독: C:/Python314/python.exe scripts/console_activity_push.py
"""
from __future__ import annotations

import glob
import json
import os
import sys
import threading
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import live_cli_status_server as live  # noqa: E402

_PHONE = __import__("re").compile(r"01[016789][-\s.]?\d{3,4}[-\s.]?\d{4}")
_RRN = __import__("re").compile(r"\d{6}[-\s]?[1-4]\d{6}")


def mask(text: str) -> str:
    """8787 로컬 라이브의 _mask 위에 전화·주민번호를 한 번 더 가린다 — 서버(밖)로 나가는 글자라 더 보수적으로."""
    t = live._mask(text)
    t = _RRN.sub("******-*******", t)
    return _PHONE.sub("010-****-****", t)

_NOISE_PREFIX = ("Stop hook feedback", "[SYSTEM", "<", "[Cross-session", "Another Claude session", "This is how Claude Code",
                 "[형식 고정", "C-Level 부팅", "PreToolUse", "PostToolUse", "UserPromptSubmit", "Called the ", "Result of calling")


def is_noise(text: str) -> bool:
    """훅·시스템 알림·세션 간 통지 = GM 이 볼 활동이 아니다."""
    t = (text or "").lstrip()
    return (not t) or t.startswith(_NOISE_PREFIX)


def clean(text: str) -> str:
    """8요소 표·줄글 벽은 첫 줄(상태 결론)만 — 표 기호(|)·마크다운 굵게를 걷는다."""
    t = (text or "").strip()
    first = t.splitlines()[0] if t else ""
    if first.startswith("|"):                      # 표부터 시작하면 첫 칸 내용
        first = first.strip("|").split("|")[0]
    first = first.replace("**", "").strip(" |")
    return first[:120]


SESS_DIR = os.path.join(ROOT, "status", "sessions")
KEY_PATH = os.path.expanduser("~/.claude/token_push.key")
URL = os.environ.get("CONSOLE_EVENT_URL", "https://erp.wellperion.com/api/console/event")
PERIOD_SEC = 3.0
MAX_EVENTS_PER_PUSH = 20
ROLES = ("ceo", "cto", "cmo", "cpo", "coo", "cbo")
_OFFSET: dict = {}      # path → 마지막으로 읽은 바이트 위치
_LAST_TOOL: dict = {}   # role → 마지막 도구 시각


def _key() -> str:
    try:
        return open(KEY_PATH, encoding="utf-8").read().strip()
    except Exception:
        return ""


def _sid(role: str) -> str:
    try:
        return open(os.path.join(SESS_DIR, ".sid_%s" % role), encoding="utf-8").read().strip()
    except Exception:
        return ""


def _jsonl(sid: str) -> str:
    hits = glob.glob(os.path.join(live.TRANSCRIPT_DIR, sid + ".jsonl"))
    return hits[0] if hits else ""


def read_new_lines(path: str) -> list:
    """마지막 위치 이후 새 줄만(첫 호출은 끝에서 시작 = 과거를 다시 보내지 않는다)."""
    size = os.path.getsize(path)
    pos = _OFFSET.get(path)
    if pos is None or pos > size:
        _OFFSET[path] = size
        return []
    if pos == size:
        return []
    with open(path, "rb") as f:
        f.seek(pos)
        raw = f.read(size - pos)
    _OFFSET[path] = size
    return [ln for ln in raw.decode("utf-8", errors="ignore").splitlines() if ln.strip()]


def collect(role: str) -> dict | None:
    sid = _sid(role)
    path = _jsonl(sid) if sid else ""
    if not path:
        return None
    events = live._events_from_lines(read_new_lines(path))
    if not events:
        return None
    tools = [e for e in events if e[1] == "도구"]
    if tools:
        _LAST_TOOL[role] = tools[-1][0]
    shown = [{"ts": ts, "kind": kind, "text": mask(clean(text))} for ts, kind, text in events
             if kind != "도구" and not is_noise(text)]
    return {"role": role, "events": shown[-MAX_EVENTS_PER_PUSH:], "busy_at": _LAST_TOOL.get(role)}


def push(payload: dict) -> bool:
    key = _key()
    if not key:
        return False
    req = urllib.request.Request(URL, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                                 headers={"Content-Type": "application/json", "X-Token-Push-Key": key}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            return r.status == 200
    except Exception:
        return False


def tick() -> int:
    """창 6개를 한 통(batch)으로 — 요청 수를 3초에 1번으로 묶는다(nginx limit_req · 서버 파일 쓰기 1회)."""
    batch = [p for p in (collect(r) for r in ROLES) if p and (p["events"] or p["busy_at"])]
    if not batch:
        return 0
    return len(batch) if push({"batch": batch}) else 0


def loop():
    while True:
        try:
            tick()
        except Exception:
            pass
        time.sleep(PERIOD_SEC)


def start_pusher(logger=None):
    t = threading.Thread(target=loop, daemon=True, name="console-activity-push")
    t.start()
    if logger:
        logger.info("관제판 활동 푸시 시작(3초 · %s)", URL)
    return t


def _selftest():
    import tempfile
    d = tempfile.mkdtemp()
    p = os.path.join(d, "x.jsonl")
    open(p, "w", encoding="utf-8").write('{"type":"user","timestamp":"t1","message":{"content":"옛 지시"}}\n')
    assert read_new_lines(p) == [], "첫 호출은 과거를 안 보낸다"
    with open(p, "a", encoding="utf-8") as f:
        f.write('{"type":"assistant","timestamp":"t2","message":{"content":[{"type":"tool_use","name":"Bash","input":{"command":"ls"}}]}}\n')
        f.write('{"type":"assistant","timestamp":"t3","message":{"content":[{"type":"text","text":"끝났다 010-1234-5678"}]}}\n')
    ev = live._events_from_lines(read_new_lines(p))
    assert [e[1] for e in ev] == ["도구", "응답"], ev
    assert "1234" not in mask(ev[1][2]), "전화번호는 가린다"
    assert read_new_lines(p) == []
    assert is_noise("Stop hook feedback: [x]") and is_noise("<cross-session-message from=…>") and not is_noise("배편 리스트업해줘")
    assert clean("✅완료 · 시토 · 관제판" + chr(10) + chr(10) + "| 📌 GM 요청 | … |") == "✅완료 · 시토 · 관제판"
    assert clean("| 📌 GM 요청 | 관제판 |") == "📌 GM 요청"
    print("selfcheck ok")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _selftest()
    else:
        loop()
