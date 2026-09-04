# -*- coding: utf-8 -*-
"""리셉션 업무·라커관리 읽기 통로 + 마지막 정상본 거울 (배 960 #9i · 2026-09-04 시토).

두 화면(coo/리셉션 업무/index.html · .../라커관리/index.html)은 실시간 셀 편집(30초 자동새로고침)이라
5분 주기 캐시 거울이 안 맞는다 — 낡은 값을 먼저 보여주면 방금 옆자리에서 고친 칸이 되돌아간 것처럼 보인다.
그래서 이 통로는 캐시를 앞에 두지 않는다. 읽기는 **매번 GAS 로 그대로 나가고**, 그 응답을 프로세스 안에
「마지막 정상본」으로만 쥔다. 구글이 데이터 대신 안내 HTML 을 돌려주는 날(화면 주석 2026-08-03)
저장본이 없는 PC(처음 들어온 컴퓨터)가 빈 화면에서 막히지 않게 하는 실패 대비다.

  POST /api/reception-ops          화면이 GAS 로 보내던 본문 그대로. 응답도 GAS 응답 그대로(unauthorized 포함).
                                   서버가 GAS 에 못 닿으면 {ok:false, error:'server-forward-failed',
                                   _stale:<마지막 정상본>} — 화면은 먼저 종전 GAS 직접 경로를 한 번 시도하고
                                   그것마저 막히면 _stale 을 쓴다(_assets/erp_write.js erpRcPost).
  GET  /api/reception-ops/health   쥐고 있는 시트·시각·환경변수 유무

비밀번호는 서버가 쥐지 않는다. 화면이 실은 그대로 GAS 에 넘기고 판정도 GAS 가 한다(읽기 비번·쓰기 비번 모두).
마지막 정상본은 그 응답을 만들어 낸 비밀번호의 sha256 과 함께 쥐고 같은 비밀번호로 물어볼 때만 돌려준다.
개인정보(성함·전화)가 들어 있으므로 DB 에 남기지 않는다 — 프로세스 메모리뿐이고 재시작하면 사라진다.
쓰기가 통하면 그 시트의 정상본은 버린다(api_write 가 forget 호출) — 낡은 값을 실패 대비로 내주지 않는다.
쓰기(update·append)는 이 통로가 받지 않는다 — /api/write 로 가야 write_log 이중기록이 남는다.
nginx auth_request 가 앞에서 ERP 로그인을 검사한다(api.nginx.conf) — 이 통로는 로그인 뒤에만 열린다.

app.py 가 같은 폴더의 api_*.py 를 자동 등록한다 — app.py 본문은 건드리지 않는다.
자체점검: python3 api_reception_ops.py --selftest   (네트워크·DB 없음)
"""
import hashlib
import json
import os
import sys
import time
import urllib.request

from fastapi import APIRouter, Request

SOURCE = "server-last-good"
FORWARD_TIMEOUT = 55          # 화면 읽기 대기 상한보다 짧게 — 화면이 끊기 전에 server-forward-failed 를 받게
_LAST = {}                    # (환경변수 열쇠, 시트) -> {"pw": sha256, "data": {...}, "at": KST}
_LAST_MAX = 32                # 리셉션 9시트 + 라커 3탭 — ponytail: 상한만 두고 가장 먼저 들어온 것부터 버린다
_WRITE_ACTIONS = ("update", "append")

router = APIRouter()


def target(payload):
    """(환경변수 열쇠, 시트 이름) — 라커관리는 db, 리셉션 업무는 tab. 둘 다 아니면 None.

    두 화면의 액션 이름(read·update·append)이 너무 흔해 다른 GAS 와 섞인다. 그래서 본문 모양으로 가른다.
    이 판정이 목적지 정본 — api_write 도 이 함수를 불러 쓴다(규칙이 두 곳에 생기면 한쪽만 늘어난다)."""
    if not isinstance(payload, dict):
        return None
    if "db" in payload:
        return ("LOCKER_GAS_URL", str(payload["db"]))
    if "tab" in payload:
        return ("RCOPS_GAS_URL", str(payload["tab"]))
    return None


def write_gas_key(action, payload):
    """리셉션 업무·라커관리 쓰기면 그 GAS 환경변수 열쇠, 아니면 None(다른 갈래는 건드리지 않는다)."""
    t = target(payload)
    return t[0] if (str(action) in _WRITE_ACTIONS and t) else None


def _kst():
    return time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(time.time() + 9 * 3600))


def _pw(payload):
    """읽기 비번의 sha256 — 비번 자체는 어디에도 남기지 않는다."""
    pw = payload.get("password", "") if isinstance(payload, dict) else ""
    return hashlib.sha256(str(pw).encode("utf-8")).hexdigest()


def remember(t, payload, data):
    if t not in _LAST and len(_LAST) >= _LAST_MAX:
        _LAST.pop(next(iter(_LAST)), None)
    _LAST[t] = {"pw": _pw(payload), "data": data, "at": _kst()}


def forget(payload):
    """쓰기가 통한 시트의 마지막 정상본을 버린다 — 낡은 값을 실패 대비로 내주지 않는다. 해당 없으면 아무 일 없음."""
    t = target(payload)
    if t:
        _LAST.pop(t, None)


def _failed(detail, t, payload):
    out = {"ok": False, "error": "server-forward-failed", "detail": detail, "noRetry": False}
    last = _LAST.get(t)
    if last and last["pw"] == _pw(payload):      # 같은 비밀번호로 떠온 것만 돌려준다(개인정보)
        out["_stale"] = dict(last["data"], _source=SOURCE, _synced_at=last["at"])
    return out


@router.post("/api/reception-ops")
async def reception_ops(request: Request):
    body = await request.body()
    try:
        payload = json.loads(body.decode("utf-8"))
    except Exception:
        return {"ok": False, "error": "bad-payload", "detail": "JSON 객체여야 합니다", "noRetry": True}
    t = target(payload)
    if not t:
        return {"ok": False, "error": "bad-payload",
                "detail": "tab(리셉션 업무) 또는 db(라커관리)가 있어야 합니다", "noRetry": True}
    if write_gas_key(payload.get("action", ""), payload):
        # 쓰기가 이리 오면 write_log 이중기록이 빠진다. 화면이 관문을 잘못 고른 것 — 조용히 흘려보내지 않는다.
        return {"ok": False, "error": "bad-payload", "detail": "쓰기는 /api/write 로", "noRetry": True}
    url = os.environ.get(t[0], "")
    if not url:
        return _failed("%s 없음 — /srv/erp/api.env" % t[0], t, payload)
    req = urllib.request.Request(url, data=body, method="POST",
                                 headers={"Content-Type": "text/plain;charset=utf-8",
                                          "User-Agent": "wellperion-erp-api"})
    try:
        with urllib.request.urlopen(req, timeout=FORWARD_TIMEOUT) as r:
            data = json.loads(r.read().decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("GAS 응답이 객체가 아님")
    except Exception as e:
        return _failed("%s: %s" % (type(e).__name__, str(e)[:200]), t, payload)
    if data.get("ok"):
        remember(t, payload, data)
    return data                                   # unauthorized·ok=false 도 그대로 — 로그인 판정은 GAS 것


@router.get("/api/reception-ops/health")
def health():
    return {"ok": True,
            "sheets": {"%s/%s" % k: v["at"] for k, v in _LAST.items()},
            "gas": {k: bool(os.environ.get(k)) for k in ("RCOPS_GAS_URL", "LOCKER_GAS_URL")},
            "_source": SOURCE}


def selftest():
    assert target({"tab": "키관리", "action": "read"}) == ("RCOPS_GAS_URL", "키관리")
    assert target({"db": "men", "password": "x"}) == ("LOCKER_GAS_URL", "men")
    # 라커 쓰기는 db·_sheet_row 를 같이 싣는다 — db 판정이 먼저라 라커 GAS 로 간다.
    assert target({"action": "update", "db": "golf", "_sheet_row": 12, "fields": {}}) == ("LOCKER_GAS_URL", "golf")
    assert target({"action": "member_active_update", "no": "M1"}) is None    # 다른 도메인은 안 건드린다
    assert target(None) is None and target({"action": "read"}) is None
    assert write_gas_key("update", {"tab": "키관리"}) == "RCOPS_GAS_URL"
    assert write_gas_key("append", {"tab": "시재금입출내역"}) == "RCOPS_GAS_URL"
    assert write_gas_key("update", {"db": "men", "_sheet_row": 3}) == "LOCKER_GAS_URL"
    assert write_gas_key("read", {"tab": "키관리"}) is None                  # 읽기는 /api/write 로 안 간다
    assert write_gas_key("save", {"tab": "키관리"}) is None                  # 점검 GAS 액션이 새면 안 된다
    assert write_gas_key("update", {"no": "M1"}) is None

    _LAST.clear()
    t = ("RCOPS_GAS_URL", "키관리")
    remember(t, {"password": "비번"}, {"ok": True, "values": [["a"]]})
    r = _failed("테스트", t, {"password": "비번"})
    assert r["error"] == "server-forward-failed" and r["_stale"]["values"] == [["a"]]
    assert r["_stale"]["_source"] == SOURCE and r["_stale"]["_synced_at"]
    assert "_stale" not in _failed("테스트", t, {"password": "틀린비번"})     # 비번이 다르면 개인정보를 안 준다
    assert "_stale" not in _failed("테스트", ("LOCKER_GAS_URL", "men"), {"password": "비번"})
    forget({"action": "update", "tab": "키관리", "row": 2})                  # 쓰기 뒤에는 버린다
    assert "_stale" not in _failed("테스트", t, {"password": "비번"})
    forget({"no": "M1"})                                                     # 해당 없으면 아무 일 없음

    for i in range(_LAST_MAX + 5):                                           # 상한을 넘겨도 무한히 안 는다
        remember(("RCOPS_GAS_URL", "s%d" % i), {"password": "p"}, {"ok": True})
    assert len(_LAST) == _LAST_MAX
    _LAST.clear()
    print("selftest ok")
    return 0


if __name__ == "__main__":
    sys.exit(selftest())
