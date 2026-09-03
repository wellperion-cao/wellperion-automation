# -*- coding: utf-8 -*-
"""카톡전송관리(cto/automation/카톡전송관리.html) 방 목록 → 서버 PostgreSQL 미러 (읽기 전용 단방향 · 배 922 레인 W).

원천 = 화면이 부르는 업무 GAS(TODO_GAS_URL) 의 kakao_rooms_get 그대로. 저장·삭제는 화면이 계속 GAS 로 쓴다.
열쇠 = 방 이름(GAS 도 이름으로 upsert). 순서(ord)는 시트 순 = 화면 표시 순.

실행: python3 /srv/erp/api/sync_kakao.py   (cron 5분 · /etc/cron.d/erp-kakao-sync)
자체점검: python3 sync_kakao.py --selftest  (tenant 'selftest' · 네트워크 없음)
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sync_todo import ENV_FILE, db, load_env  # noqa: E402  — 같은 GAS(TODO_GAS_URL)·같은 env·같은 DB


def gas_rooms(timeout=60):
    url = os.environ.get("TODO_GAS_URL", "")
    if not url:
        raise SystemExit("TODO_GAS_URL 없음 — %s 를 확인" % ENV_FILE)
    req = urllib.request.Request(url + "?" + urllib.parse.urlencode({"action": "kakao_rooms_get"}),
                                 headers={"User-Agent": "wellperion-erp-api"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print("[warn] kakao_rooms_get 조회 실패: %s: %s" % (type(e).__name__, str(e)[:120]))
        return None
    if not data.get("ok") or not isinstance(data.get("rooms"), list):
        print("[warn] kakao_rooms_get 응답 ok=false")
        return None
    return data["rooms"]


def replace_all(conn, rooms, now):
    """통째로 교체 — 호출부가 '조회 성공' 을 확인한 뒤에만 부른다(방 0개도 정상값이라 빈 목록도 반영)."""
    seen, rows = set(), []
    for r in rooms:
        name = str(r.get("name") or "")
        if not name or name in seen:            # GAS 도 이름으로 upsert 하니 같은 이름은 첫 행만
            continue
        seen.add(name)
        rows.append((db.TENANT, name, str(r.get("prefix") or ""), len(rows), now))
    with conn:
        conn.execute("DELETE FROM kakao_rooms WHERE tenant_id=%s", (db.TENANT,))
        conn.executemany("INSERT INTO kakao_rooms (tenant_id, name, prefix, ord, synced_at) VALUES (%s,%s,%s,%s,%s)", rows)
    return len(rows)


def main():
    load_env()
    conn = db.connect()
    db.init_schema(conn)
    now = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(time.time() + 9 * 3600))
    rooms = gas_rooms()
    ok = rooms is not None
    if ok:
        print("[ok] 방 %d건" % replace_all(conn, rooms, now))
    with conn:
        if ok:
            db.meta_set(conn, "kakao_last_sync", now)
        db.meta_set(conn, "kakao_last_failed", "" if ok else now)
    conn.close()
    print("[done] %s · %s" % (now, "정상" if ok else "실패 — 기존 미러 유지"))
    return 0 if ok else 1


def selftest():
    db.TENANT = "selftest"
    conn = db.connect()
    db.init_schema(conn)
    T = (db.TENANT,)
    try:
        assert replace_all(conn, [{"name": "운영부", "prefix": "[운영]"}, {"name": "", "prefix": "x"}, {"name": "운영부"}], "t0") == 1, "이름 없는 행 버림·중복 이름 1건"
        assert replace_all(conn, [], "t1") == 0 and conn.execute("SELECT COUNT(*) FROM kakao_rooms WHERE tenant_id=%s", T).fetchone()[0] == 0, "빈 목록도 반영"
    finally:
        with conn:
            conn.execute("DELETE FROM kakao_rooms WHERE tenant_id=%s", T)
        conn.close()
    print("selftest ok")
    return 0


if __name__ == "__main__":
    sys.exit(selftest() if "--selftest" in sys.argv else main())
