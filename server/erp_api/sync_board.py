# -*- coding: utf-8 -*-
"""공용 보드(GAS action=board) → 서버 PostgreSQL 미러 동기화 (읽기 전용 단방향) — 배 926.

점검 GAS(sync_check.py 와 같은 CHECK_GAS_URL)는 board 라는 범용 키-값 저장소도 겸한다.
GM 담당 칸(GM_TASK_OWNERS) 등 화면 여러 곳이 이미 이 GAS 로 읽고 쓰는데, 응답이 느린 날
(실측 3,765~24,118ms) 클라이언트 타임아웃(8초)에 걸려 담당 칸 71개가 통째로 빈 화면이 됐다
(2026-09-04). 이 표는 알려진 board 키를 5분마다 미리 떠 둔다 — 화면은 이 미러를 먼저 읽는다.

BOARD_KEYS = grep -rho "action=board&key=[A-Za-z_]*" "3. 웰페리온 가이드" + BOARD_KEY 변수 정의 전수(2026-09-04).
FACILITY_CHECK_* 는 날짜별 동적 키라 sync_check.py(check_records 표)가 이미 따로 미러한다 — 여기서 중복 안 한다.

실행: python3 /srv/erp/api/sync_board.py   (cron 5분 · /etc/cron.d/erp-board-sync)
자체점검: python3 sync_board.py --selftest  (같은 DB 의 tenant 'selftest' · 네트워크 없음)
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sync_inquiries import db, load_env  # noqa: E402  — 같은 env·같은 DB

BOARD_KEYS = (
    "GM_TASK_OWNERS", "CHAIRMAN_REPORTED", "OPS_POLICY_BOARD", "OPS_GUIDE_BOARD",
    "OPS_MANUAL_BOARD", "BROJ_TASK_BOARD", "SUPPORT_LAUNDRY",
)


def gas_board(key, timeout=60):
    """board 1건 조회. 성공 시 dict(GAS 응답 그대로), 실패 시 None(지어내지 않는다)."""
    url = os.environ.get("CHECK_GAS_URL", "")
    if not url:
        raise SystemExit("CHECK_GAS_URL 없음 — /srv/erp/api.env 를 확인")
    q = {"action": "board", "key": key, "_pv": int(time.time())}
    req = urllib.request.Request(url + "?" + urllib.parse.urlencode(q), headers={"User-Agent": "wellperion-erp-api"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print("[warn] %s 조회 실패: %s: %s" % (key, type(e).__name__, str(e)[:120]))
        return None
    if not isinstance(data, dict) or not data.get("ok"):
        print("[warn] %s 응답 ok=false" % key)
        return None
    return data


def put(conn, key, data, now):
    with conn:
        conn.execute(
            "INSERT INTO board_cache (tenant_id,key,data,synced_at) VALUES (%s,%s,%s,%s)"
            " ON CONFLICT (tenant_id,key) DO UPDATE SET data=EXCLUDED.data, synced_at=EXCLUDED.synced_at",
            (db.TENANT, key, json.dumps(data, ensure_ascii=False), now))


def main():
    load_env()
    conn = db.connect()
    db.init_schema(conn)                        # 멱등 — board_cache 표가 없으면 만든다
    now = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(time.time() + 9 * 3600))   # 서버는 UTC · 기록은 KST
    n_ok, failed = 0, []
    for key in BOARD_KEYS:
        data = gas_board(key)
        if data is None:
            failed.append(key)                  # 실패 — 기존 미러를 그대로 둔다
            continue
        put(conn, key, data, now)
        n_ok += 1
    with conn:
        db.meta_set(conn, "board_last_sync", now)
        db.meta_set(conn, "board_last_failed", ",".join(failed))
    conn.close()
    print("[done] %s · 갱신 %d/%d건 · 실패 %s" % (now, n_ok, len(BOARD_KEYS), failed or "없음"))
    return 1 if failed else 0


def selftest():
    db.TENANT = "selftest"                       # 같은 DB · 다른 tenant — 실데이터는 한 줄도 안 건드린다
    conn = db.connect()
    db.init_schema(conn)
    try:
        with conn:
            conn.execute("DELETE FROM board_cache WHERE tenant_id=%s", (db.TENANT,))
        put(conn, "GM_TASK_OWNERS", {"ok": True, "board": {"a": "1"}}, "t0")
        put(conn, "GM_TASK_OWNERS", {"ok": True, "board": {"a": "1", "b": "2"}}, "t1")
        r = conn.execute("SELECT data, synced_at FROM board_cache WHERE tenant_id=%s AND key='GM_TASK_OWNERS'",
                         (db.TENANT,)).fetchone()
        assert r["synced_at"] == "t1" and len(json.loads(r["data"])["board"]) == 2, "같은 열쇠는 덮어쓴다"
    finally:
        with conn:
            conn.execute("DELETE FROM board_cache WHERE tenant_id=%s", (db.TENANT,))
        conn.close()
    print("selftest ok")
    return 0


if __name__ == "__main__":
    sys.exit(selftest() if "--selftest" in sys.argv else main())
