# -*- coding: utf-8 -*-
"""점검 GAS(시설부·지원부·주차관리부) → 서버 PostgreSQL 미러 동기화 (읽기 전용 단방향) — 배 922 레인 S.

sync_members.py 와 같은 규칙이다. 원천은 화면들이 이미 부르는 점검 GAS 액션(board · 조별 원장 · today_live ·
monthly_report · weekly)을 그대로 부르고 응답을 통째로 저장한다 — 시트·GAS 는 절대 쓰지 않는다.
표 하나(check_records)에 부서·종류·열쇠(날짜/날짜|성별/월)로 싣는다. 점검 원장은 부서마다 구조가 달라
(시설=측정 blob · 지원=조×성별 원장 · 주차=원장 m) 칸을 쪼개면 세 벌이 되고, 화면은 GAS 응답 모양 그대로 원한다.

주기: 오늘·어제는 매번 다시 떠오고, 최근 30일 중 미러에 없는 날은 한 번에 몇 날씩 채운다(GAS 호출 수 억제).
GAS URL 은 /srv/erp/api.env 의 CHECK_GAS_URL 한 줄(저장소에 안 둔다).

실행: python3 /srv/erp/api/sync_check.py   (cron 5분 · /etc/cron.d/erp-check-sync)
      python3 sync_check.py --today          오늘치 원장·보드만(5호출) — /api/write 점검 쓰기 직후 거울 즉시 반영(배 960 #5b)
자체점검: python3 sync_check.py --selftest  (같은 DB 의 tenant 'selftest' · 네트워크 없음)
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sync_inquiries import db, load_env  # noqa: E402  — 같은 env·같은 DB

DEPTS = ("facility", "support", "parking")
BACKFILL_DAYS = 30
BACKFILL_PER_RUN = 6      # ponytail: 한 번에 6날만 채운다(시설 1+지원 3+주차 1 = 날당 5호출) · 30일은 5번 돌면 다 찬다


def _kst_today():
    return date.fromtimestamp(time.time() + 9 * 3600)


def gas_get(params, require_ok=True, timeout=60):
    """점검 GAS GET 1회. 성공 시 dict, 실패 시 None(지어내지 않는다). 조별 원장 조회는 ok 를 안 싣는다(require_ok=False)."""
    url = os.environ.get("CHECK_GAS_URL", "")
    if not url:
        raise SystemExit("CHECK_GAS_URL 없음 — /srv/erp/api.env 를 확인")
    q = dict(params, _pv=int(time.time()))
    req = urllib.request.Request(url + "?" + urllib.parse.urlencode(q), headers={"User-Agent": "wellperion-erp-api"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print("[warn] %s 조회 실패: %s: %s" % (params, type(e).__name__, str(e)[:120]))
        return None
    if not isinstance(data, dict) or (require_ok and not data.get("ok")):
        print("[warn] %s 응답 ok=false" % (params,))
        return None
    return data


def day_sources(dept, d):
    """(kind, key, GAS params, require_ok) — 화면·요약 스크립트가 그 날짜에 대해 부르는 읽기 액션 그대로."""
    if dept == "facility":
        return [("board", d, {"action": "board", "key": "FACILITY_CHECK_" + d}, True)]
    if dept == "support":
        return [("ledger", d + "|m", {"date": d, "dept": "support", "gender": "m"}, False),
                ("ledger", d + "|f", {"date": d, "dept": "support", "gender": "f"}, False),
                ("today_live", d, {"action": "today_live", "dept": "support", "date": d}, True)]
    return [("ledger", d + "|m", {"date": d, "dept": "parking", "gender": "m"}, False)]


def put(conn, dept, kind, key, data, now):
    with conn:
        conn.execute(
            "INSERT INTO check_records (tenant_id,dept,kind,key,data,synced_at) VALUES (%s,%s,%s,%s,%s,%s)"
            " ON CONFLICT (tenant_id,dept,kind,key) DO UPDATE SET data=EXCLUDED.data, synced_at=EXCLUDED.synced_at",
            (db.TENANT, dept, kind, key, json.dumps(data, ensure_ascii=False), now))


def have_keys(conn, dept, kind):
    return {r[0] for r in conn.execute("SELECT key FROM check_records WHERE tenant_id=%s AND dept=%s AND kind=%s",
                                       (db.TENANT, dept, kind))}


def plan(conn, today):
    """(dept, kind, key, params, require_ok) 목록 — 오늘·어제 전부 + 빈 날 채움 + 이달·지난달 월간 + 주간."""
    jobs, backfill = [], []
    for dept in DEPTS:
        had = {k: have_keys(conn, dept, k) for k in ("board", "ledger", "today_live")}
        for i in range(BACKFILL_DAYS + 1):
            d = (today - timedelta(days=i)).isoformat()
            for kind, key, params, ok in day_sources(dept, d):
                job = (dept, kind, key, params, ok)
                if i <= 1:
                    jobs.append(job)
                elif key not in had[kind]:
                    backfill.append(job)
        for m in {today.strftime("%Y-%m"), (today.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")}:
            jobs.append((dept, "monthly", m, {"action": "monthly_report", "dept": dept, "month": m}, True))
        if dept != "facility":     # weekly 는 조별 원장 부서만 뜻이 있다(시설은 GAS 도 안 센다)
            jobs.append((dept, "weekly", "-", {"action": "weekly", "dept": dept}, True))
    return jobs + backfill[:BACKFILL_PER_RUN * 5]


def plan_today(today):
    """오늘치 원장·보드만 — /api/write 쓰기 직후 거울을 즉시 맞출 때(배 960 #5b). 월간·주간·빈날채움은 5분 cron 몫."""
    d = today.isoformat()
    return [(dept, kind, key, params, ok) for dept in DEPTS for kind, key, params, ok in day_sources(dept, d)]


def main(only_today=False):
    load_env()
    conn = db.connect()
    today = _kst_today()
    now = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(time.time() + 9 * 3600))
    n_ok, failed = 0, []
    for dept, kind, key, params, ok in (plan_today(today) if only_today else plan(conn, today)):
        data = gas_get(params, require_ok=ok)
        if data is None:
            failed.append("%s/%s/%s" % (dept, kind, key))   # 실패 — 기존 미러를 그대로 둔다
            continue
        put(conn, dept, kind, key, data, now)
        n_ok += 1
    with conn:
        db.meta_set(conn, "check_last_sync", now)
        if not only_today:
            # 오늘치만 돈 판으로 전량 실패 목록을 덮으면 health 가 실제보다 깨끗해 보인다.
            db.meta_set(conn, "check_last_failed", ",".join(failed))
    conn.close()
    print("[done] %s · 갱신 %d건 · 실패 %s" % (now, n_ok, failed or "없음"))
    return 1 if failed else 0


def selftest():
    db.TENANT = "selftest"                      # 같은 DB · 다른 tenant — 실데이터는 한 줄도 안 건드린다
    conn = db.connect()
    today = date(2026, 9, 3)
    try:
        with conn:
            conn.execute("DELETE FROM check_records WHERE tenant_id=%s", (db.TENANT,))
        put(conn, "facility", "board", "2026-09-03", {"ok": True, "board": {"store": {"submissions": [1, 2]}}}, "t0")
        put(conn, "facility", "board", "2026-09-03", {"ok": True, "board": {"store": {"submissions": [1, 2, 3]}}}, "t1")
        r = conn.execute("SELECT data, synced_at FROM check_records WHERE tenant_id=%s AND dept='facility' AND kind='board'",
                         (db.TENANT,)).fetchall()
        assert len(r) == 1 and r[0]["synced_at"] == "t1" and len(json.loads(r[0]["data"])["board"]["store"]["submissions"]) == 3, "같은 열쇠는 덮어쓴다"
        jobs = plan(conn, today)
        keys = {(j[0], j[1], j[2]) for j in jobs}
        assert ("facility", "board", "2026-09-02") in keys and ("support", "ledger", "2026-09-03|f") in keys
        assert ("facility", "board", "2026-09-03") in keys, "오늘은 있어도 다시 떠온다"
        assert ("parking", "monthly", "2026-08") in keys and ("support", "weekly", "-") in keys
        assert len([j for j in jobs if j[1] in ("board", "ledger", "today_live") and j[2] < "2026-09-02"]) <= BACKFILL_PER_RUN * 5, "빈 날 채움은 상한 안"
        assert day_sources("support", "2026-09-03")[0][3] is False, "조별 원장은 ok 없는 응답"
        tkeys = {(j[0], j[1], j[2]) for j in plan_today(today)}   # --today = 오늘치 원장·보드만(월간·주간·빈날 없음)
        assert ("support", "today_live", "2026-09-03") in tkeys and ("facility", "board", "2026-09-03") in tkeys
        assert not [k for k in tkeys if k[1] in ("monthly", "weekly")] and len(tkeys) == 5
    finally:
        with conn:
            conn.execute("DELETE FROM check_records WHERE tenant_id=%s", (db.TENANT,))
        conn.close()
    print("selftest ok")
    return 0


if __name__ == "__main__":
    sys.exit(selftest() if "--selftest" in sys.argv else main("--today" in sys.argv))
