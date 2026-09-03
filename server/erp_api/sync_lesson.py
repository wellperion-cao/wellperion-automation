# -*- coding: utf-8 -*-
"""강습 회원관리(membership.html?manage=lesson) 읽기 → 서버 PostgreSQL 미러 (읽기 전용 단방향 · 배 922 레인 W).

원천 = 화면이 부르는 퍼널 GAS 읽기 액션 3종을 그대로 부른다(시트·GAS 는 절대 쓰지 않는다).
  lesson_stats(type, scope=year|all)           → kind=stats    key=type|scope
  lesson_registered_roster(type)               → kind=roster   key=type   (GAS 10분 캐시 그대로 · fresh 안 씀)
  lesson_registry_list(type, from=2000-01-01)  → kind=registry key=type   (전 구간 · 날짜 필터는 API 가 등록일로 자른다)
type = 성인강습 · 유소년강습(화면 lsType 두 값). 응답 JSON 을 통째로 lesson_records 에 싣고 화면은 GAS 모양 그대로 읽는다.
종목명은 GAS 가 준 이름을 손대지 않는다(두 벌 존재 — 조인·정규화 금지).

실행: python3 /srv/erp/api/sync_lesson.py   (cron 5분 · /etc/cron.d/erp-lesson-sync)
자체점검: python3 sync_lesson.py --selftest  (tenant 'selftest' · 네트워크 없음)
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sync_inquiries import db, gas_get, load_env  # noqa: E402  — 같은 원천(FUNNEL_EXEC_URL)·같은 env·같은 DB

TYPES = ["성인강습", "유소년강습"]


def fetch_all():
    """(kind, key, payload) 목록. 한 건이라도 실패하면 그 건만 빠진다 — 있는 것만 갈아끼운다."""
    out = []
    for t in TYPES:
        for scope in ("year", "all"):
            d = gas_get("lesson_stats", {"type": t, "scope": scope}, timeout=120)
            if d:
                out.append(("stats", t + "|" + scope, d))
        d = gas_get("lesson_registered_roster", {"type": t}, timeout=180)
        if d:
            out.append(("roster", t, d))
        d = gas_get("lesson_registry_list", {"type": t, "from": "2000-01-01", "to": "2099-12-31"}, timeout=180)
        if d:
            out.append(("registry", t, d))
    return out


def upsert(conn, items, now):
    with conn:
        conn.executemany(
            "INSERT INTO lesson_records (tenant_id, kind, key, data, synced_at) VALUES (%s,%s,%s,%s,%s)"
            " ON CONFLICT (tenant_id, kind, key) DO UPDATE SET data = EXCLUDED.data, synced_at = EXCLUDED.synced_at",
            [(db.TENANT, k, key, json.dumps(d, ensure_ascii=False), now) for k, key, d in items])
    return len(items)


def main():
    load_env()
    conn = db.connect()
    db.init_schema(conn)
    now = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(time.time() + 9 * 3600))
    items = fetch_all()
    ok = len(items) == len(TYPES) * 4          # 2 type × (stats 2 + roster 1 + registry 1)
    if items:
        print("[ok] %d/%d 건 갱신" % (upsert(conn, items, now), len(TYPES) * 4))
    with conn:
        if ok:
            db.meta_set(conn, "lesson_last_sync", now)
        db.meta_set(conn, "lesson_last_failed", "" if ok else now)
    conn.close()
    print("[done] %s · %s" % (now, "정상" if ok else "일부 실패 — 빠진 건은 기존 미러 유지"))
    return 0 if ok else 1


def selftest():
    db.TENANT = "selftest"
    conn = db.connect()
    db.init_schema(conn)
    T = (db.TENANT,)
    try:
        assert upsert(conn, [("stats", "성인강습|year", {"ok": True, "total": 1}), ("roster", "성인강습", {"ok": True, "roster": []})], "t0") == 2
        assert upsert(conn, [("stats", "성인강습|year", {"ok": True, "total": 2})], "t1") == 1, "같은 열쇠는 덮어쓴다"
        rows = conn.execute("SELECT kind, key, data FROM lesson_records WHERE tenant_id=%s ORDER BY kind", T).fetchall()
        assert len(rows) == 2 and json.loads(rows[1]["data"])["total"] == 2, rows
    finally:
        with conn:
            conn.execute("DELETE FROM lesson_records WHERE tenant_id=%s", T)
        conn.close()
    print("selftest ok")
    return 0


if __name__ == "__main__":
    sys.exit(selftest() if "--selftest" in sys.argv else main())
