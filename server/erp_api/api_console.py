"""C레벨 관제판 라이브 원천 — 세션 생존 신호를 서버가 직접 받는다(배 12723 · GM 2026-09-17 「자율현황은 라이브가 아니라 안 본다」).

  POST /api/console/heartbeat   로그인 없는 통로 · 열쇠 헤더 X-Token-Push-Key(api.env ERP_TOKEN_PUSH_KEY · api_token_usage.py 와 같은 값)
                                본문 = {"role":"cto", "nick":…, "session":…, "ts":…, "now":{…}, "idle_since":…,
                                        "open_ships":{"count":N,"top":[…]}, "gm":{"received":N,"done":N}, "calls_open":N, "saves_today":N}
                                role 만 필수 · 나머지 키는 없으면 이전 값을 유지한다(부분 갱신).
  GET  /api/console/state       로그인 세션(/api/ 기본 관문) · {"published_at":…, "roles":{role: {...,"alive":bool,"seen_at":…}}}
                                alive = 마지막 신호가 90분 안. 화면(erp/admin/자율현황.html)이 15초마다 읽는다.

nginx = console.nginx.conf(heartbeat 만 auth_request 없이) · 상태는 메모리 + /srv/erp/api/console_state.json(재기동 뒤 복원).
보내는 쪽 = scripts/session_register.py --heartbeat(웰리 2026-09-17) · 값 원천은 kungjjak_board._board 와 같다.
"""
from __future__ import annotations

import datetime
import hmac
import json
import os
import threading

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

router = APIRouter()

STATE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "console_state.json")
ALIVE_SEC = 90 * 60
ROLES = ("ceo", "cto", "cmo", "cpo", "coo", "cbo", "chro", "cfo")
KEEP = ("nick", "session", "ts", "now", "idle_since", "open_ships", "gm", "calls_open", "saves_today")
_LOCK = threading.Lock()
_STATE: dict = {}


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).isoformat(timespec="seconds")


def _load() -> None:
    global _STATE
    try:
        with open(STATE_PATH, encoding="utf-8") as f:
            _STATE = json.load(f)
    except Exception:
        _STATE = {}


def _save() -> None:
    tmp = STATE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(_STATE, f, ensure_ascii=False)
    os.replace(tmp, STATE_PATH)


def _check_key(request: Request) -> bool:
    want = os.environ.get("ERP_TOKEN_PUSH_KEY", "")
    got = request.headers.get("x-token-push-key", "")
    return bool(want) and hmac.compare_digest(got, want)


def merge(state: dict, body: dict, seen_at: str) -> dict:
    """역할 한 칸 부분 갱신 — 순수 함수(자체점검이 잰다). 모르는 키는 버린다."""
    role = str(body.get("role") or "").strip().lower()
    if role not in ROLES:
        raise ValueError("role")
    cur = dict(state.get(role) or {})
    for k in KEEP:
        if k in body:
            cur[k] = body[k]
    cur["seen_at"] = seen_at
    state[role] = cur
    return state


def view(state: dict, now: datetime.datetime) -> dict:
    """alive 계산을 붙인 응답 모양."""
    out = {}
    for role, v in state.items():
        d = dict(v)
        try:
            seen = datetime.datetime.fromisoformat(str(d.get("seen_at")))
            if seen.tzinfo is None:
                seen = seen.replace(tzinfo=now.tzinfo)
            d["alive"] = (now - seen).total_seconds() < ALIVE_SEC
        except Exception:
            d["alive"] = False
        out[role] = d
    return {"published_at": now.isoformat(timespec="seconds"), "roles": out}


@router.post("/api/console/heartbeat")
async def heartbeat(request: Request):
    if not _check_key(request):
        raise HTTPException(401)
    try:
        body = await request.json()
        if not isinstance(body, dict):
            raise ValueError
    except Exception:
        raise HTTPException(400, "json body")
    with _LOCK:
        if not _STATE:
            _load()
        try:
            merge(_STATE, body, _now_iso())
        except ValueError:
            raise HTTPException(400, "role")
        _save()
    return {"ok": True, "seen_at": _STATE[str(body["role"]).strip().lower()]["seen_at"]}


@router.get("/api/console/state")
def state():
    with _LOCK:
        if not _STATE:
            _load()
        snap = json.loads(json.dumps(_STATE))
    return JSONResponse(view(snap, datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9)))))


def _selfcheck() -> None:
    st = {}
    merge(st, {"role": "cto", "nick": "시토", "saves_today": 3, "junk": 1}, "2026-09-17T15:00:00+09:00")
    assert st["cto"]["saves_today"] == 3 and "junk" not in st["cto"]
    merge(st, {"role": "cto", "calls_open": 1}, "2026-09-17T15:01:00+09:00")
    assert st["cto"]["saves_today"] == 3 and st["cto"]["calls_open"] == 1, "부분 갱신은 이전 값을 지운다"
    try:
        merge(st, {"role": "nobody"}, "x"); raise AssertionError("모르는 역할이 들어갔다")
    except ValueError:
        pass
    tz = datetime.timezone(datetime.timedelta(hours=9))
    v = view(st, datetime.datetime(2026, 9, 17, 15, 30, tzinfo=tz))
    assert v["roles"]["cto"]["alive"] is True
    v = view(st, datetime.datetime(2026, 9, 17, 18, 0, tzinfo=tz))
    assert v["roles"]["cto"]["alive"] is False, "90분 넘으면 죽은 것"
    print("selfcheck ok")


if __name__ == "__main__":
    _selfcheck()
