# -*- coding: utf-8 -*-
"""공용 보드(GAS action=board) 읽기 거울 (배 926).

board_cache(sync_board.py 가 5분마다 GAS board 응답을 그대로 떠온 것)를 GAS 와 같은 모양으로 돌려준다.
  GET  /api/board/{key}           캐시값 그대로 ({ok,key,board,...,synced_at,_source})
  POST /api/board/{key}/refresh   그 키만 GAS 에서 즉시 다시 떠와 캐시 갱신 — 화면이 saveBoard 성공 직후
                                    부른다(5분 주기를 안 기다리고 바로 반영, best-effort).
  GET  /api/board/health          키별 마지막 동기화 시각
미러에 없는 키는 404 — 화면은 404 를 받으면 종전 GAS 로 돌아간다(api_check.py 와 같은 폴백 규칙).
app.py 가 같은 폴더의 api_*.py 를 자동 등록한다 — app.py 본문은 건드리지 않는다.

자체점검: python3 api_board.py --selftest (같은 DB 의 tenant 'selftest' · 네트워크 없음)
"""
import json
import os
import sys
import time

from fastapi import APIRouter, HTTPException

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # 저장소 server/ = 서버 /srv/erp/
from common import db  # noqa: E402  — DB 를 여는 유일한 자리
from sync_board import gas_board, put  # noqa: E402  — GAS 호출·저장 로직은 한 곳만(sync_board.py)

SOURCE = "sheet-mirror"
router = APIRouter(prefix="/api/board")


def _conn():
    try:
        return db.connect(readonly=True)
    except db.Error as e:
        raise HTTPException(503, "DB 열기 실패: %s" % e)


@router.get("/health")
def health():
    conn = _conn()
    with conn:
        rows = conn.execute("SELECT key, synced_at FROM board_cache WHERE tenant_id=%s", (db.TENANT,)).fetchall()
    return {"ok": True, "keys": {r["key"]: r["synced_at"] for r in rows}, "_source": SOURCE}


@router.get("/{key}")
def board_get(key: str):
    conn = _conn()
    with conn:
        r = conn.execute("SELECT data, synced_at FROM board_cache WHERE tenant_id=%s AND key=%s",
                         (db.TENANT, key)).fetchone()
    if r is None:
        raise HTTPException(404, "미러 없음: %s" % key)
    data = json.loads(r["data"])
    data["synced_at"] = r["synced_at"]
    data["_source"] = SOURCE
    return data


@router.post("/{key}/refresh")
def board_refresh(key: str):
    data = gas_board(key)
    if data is None:
        raise HTTPException(502, "GAS 조회 실패: %s" % key)
    conn = db.connect()
    now = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(time.time() + 9 * 3600))
    put(conn, key, data, now)
    conn.close()
    return {"ok": True, "key": key, "synced_at": now}


if __name__ == "__main__" and "--selftest" in sys.argv:
    db.TENANT = "selftest"
    _c = db.connect()
    db.init_schema(_c)
    try:
        with _c:
            _c.execute("DELETE FROM board_cache WHERE tenant_id=%s", (db.TENANT,))
        put(_c, "GM_TASK_OWNERS", {"ok": True, "board": {"x": "1"}}, "t0")
        _r = _c.execute("SELECT data FROM board_cache WHERE tenant_id=%s AND key='GM_TASK_OWNERS'",
                        (db.TENANT,)).fetchone()
        assert json.loads(_r["data"])["board"]["x"] == "1", "board_get 이 읽을 원본이 저장돼 있어야 한다"
    finally:
        with _c:
            _c.execute("DELETE FROM board_cache WHERE tenant_id=%s", (db.TENANT,))
        _c.close()
    print("selftest ok")
