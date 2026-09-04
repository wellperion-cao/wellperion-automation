# -*- coding: utf-8 -*-
"""소형 GAS 읽기 거울 (배 960 #9). 화면 소유자 확인·GAS 생존·쓰임 근거(page_ping.json) 판정 결과 —
지출현황·리셉션 업무·라커관리는 「보류·그대로」(GAS 살아 있음·쓰기 있음/쓰임 불명 — 지우지 않는다, 코드 무변경).
renewal 개인 GAS(재등록 화면 상단 월별 통계, PIN 없이 보는 공개 집계)만 「거울」— 읽기 전용·응답이 이미
localStorage 스냅샷으로 캐시내성 있게 설계돼 있어 5분 주기 미러에 적합하다. PIN 뒤 명단(PII)은 그대로 GAS 직결—
서버가 PIN 을 대신 쥐지 않는다(보안 축소 금지).

GAS 응답이 JSONP(`__wp({...})`)라 sync_funnel.py 류와 달리 콜백을 벗겨 판정 없이 통째로 저장한다.

실행: python3 /srv/erp/api/sync_misc.py   (cron 5분 · /etc/cron.d/erp-misc-sync)
자체점검: python3 sync_misc.py --selftest  (같은 DB 의 tenant 'selftest' · 네트워크 없음)
"""
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sync_inquiries import db, load_env  # noqa: E402  — 같은 env·같은 DB

GAS_ENV = {"renewal": "RENEWAL_GAS_URL"}
ACTIONS = {"renewal": ("stats",)}
CALLBACK = "__wp"


def _kst_now():
    return time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(time.time() + 9 * 3600))


def _strip_jsonp(text, cb):
    """`cb({...})` 또는 `cb({...});` → dict. 콜백명이 안 맞거나 괄호가 없으면 ValueError(지어내지 않는다)."""
    m = re.match(r"^\s*" + re.escape(cb) + r"\s*\((.*)\)\s*;?\s*$", text, re.S)
    if not m:
        raise ValueError("jsonp 형식 아님: %s" % text[:80])
    return json.loads(m.group(1))


def gas_call(gas, action, timeout=60):
    """GAS 1회(JSONP GET). 성공 시 dict(응답 그대로), 실패 시 None(지어내지 않는다)."""
    url = os.environ.get(GAS_ENV[gas], "")
    if not url:
        raise SystemExit("%s 없음 — /srv/erp/api.env 를 확인" % GAS_ENV[gas])
    q = urllib.parse.urlencode({"callback": CALLBACK, "_": int(time.time())})
    req = urllib.request.Request(url + "?" + q, headers={"User-Agent": "wellperion-erp-api"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = _strip_jsonp(r.read().decode("utf-8"), CALLBACK)
    except Exception as e:
        print("[warn] %s/%s 조회 실패: %s: %s" % (gas, action, type(e).__name__, str(e)[:120]))
        return None
    if not isinstance(data, dict) or not data.get("months"):
        print("[warn] %s/%s 응답에 months 없음" % (gas, action))
        return None
    return data


def store(conn, gas, action, params, data, now):
    with conn:
        conn.execute("INSERT INTO misc_cache (tenant_id, gas, action, params, data, synced_at) VALUES (%s,%s,%s,%s,%s,%s)"
                     " ON CONFLICT (tenant_id, gas, action, params) DO UPDATE SET data=EXCLUDED.data, synced_at=EXCLUDED.synced_at",
                     (db.TENANT, gas, action, params, json.dumps(data, ensure_ascii=False), now))


def jobs():
    """(gas, action, params) — 표를 늘리려면 여기 한 줄 + GAS_ENV/ACTIONS 만 추가한다(파일은 하나로 유지)."""
    return [("renewal", "stats", "")]


def main():
    load_env()
    conn = db.connect()
    db.init_schema(conn)                         # 멱등 — misc_cache 표가 없으면 만든다
    now = _kst_now()
    n_ok, failed = 0, []
    for gas, action, params in jobs():
        data = gas_call(gas, action)
        if data is None:
            failed.append("%s/%s" % (gas, action))
            continue                              # 실패 — 기존 거울을 그대로 둔다
        store(conn, gas, action, params, data, now)
        n_ok += 1
    with conn:
        db.meta_set(conn, "misc_last_sync", now)
        db.meta_set(conn, "misc_last_failed", ",".join(failed))
    conn.close()
    print("misc sync %s · 갱신 %d · 실패 %s" % (now, n_ok, failed or "없음"))
    return 1 if failed else 0


def selftest():
    db.TENANT = "selftest"                       # 같은 DB · 다른 tenant — 실데이터는 한 줄도 안 건드린다
    conn = db.connect()
    db.init_schema(conn)
    try:
        with conn:
            conn.execute("DELETE FROM misc_cache WHERE tenant_id=%s", (db.TENANT,))
        assert _strip_jsonp('__wp({"a":1});', "__wp") == {"a": 1}
        assert _strip_jsonp('__wp({"a":1})', "__wp") == {"a": 1}, "세미콜론 없어도 파싱"
        try:
            _strip_jsonp('<html>error</html>', "__wp")
            raise AssertionError("형식 아니면 ValueError 여야")
        except ValueError:
            pass
        store(conn, "renewal", "stats", "", {"updated": "t0", "months": [{"num": 8}]}, "2026-09-04 10:00:00")
        store(conn, "renewal", "stats", "", {"updated": "t1", "months": [{"num": 9}]}, "2026-09-04 10:05:00")
        r = conn.execute("SELECT data, synced_at FROM misc_cache WHERE tenant_id=%s AND gas='renewal' AND action='stats'",
                         (db.TENANT,)).fetchall()
        assert len(r) == 1 and r[0]["synced_at"] == "2026-09-04 10:05:00" and json.loads(r[0]["data"])["months"][0]["num"] == 9, r
        assert jobs() == [("renewal", "stats", "")]
        assert all(a in ACTIONS[g] for g, a, _ in jobs()), "모든 일감은 API 허용 액션 안"
    finally:
        with conn:
            conn.execute("DELETE FROM misc_cache WHERE tenant_id=%s", (db.TENANT,))
        conn.close()
    print("selftest ok")
    return 0


if __name__ == "__main__":
    sys.exit(selftest() if "--selftest" in sys.argv else main())
