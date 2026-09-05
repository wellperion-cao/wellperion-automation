# -*- coding: utf-8 -*-
"""시모 퍼널 GAS 읽기 4액션 → 서버 PostgreSQL 거울 (읽기 전용 단방향) — 배 960 레인 U.

sync_inquiries.py 와 같은 GAS(FUNNEL_EXEC_URL · Survey 프로젝트)의 집계 액션을 그대로 불러 응답을 통째로 둔다 — 시트는 안 쓴다.
  funnel_conversion · funnel_conversion_detail · lesson_breakdown (인자 없음)
  period_breakdown&from=&to= (이번달 1일~오늘 + 지난 2개월 월 범위 = 월간마케팅보고서가 고르는 범위)
표 = funnel_cache(action, params) · api_funnel.py 가 같은 열쇠로 돌려준다(캐시에 없는 범위는 API 가 그 자리에서 1회 떠와 채운다).

실행: python3 /srv/erp/api/sync_funnel.py   (cron 5분 · /etc/cron.d/erp-funnel-sync)
자체점검: python3 sync_funnel.py --selftest  (같은 DB 의 tenant 'selftest' · 네트워크 없음)
"""
import json
import os
import sys
import time
import urllib.parse
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sync_inquiries import db, gas_get, load_env  # noqa: E402  — 같은 env·같은 GAS·같은 DB

PLAIN = ("funnel_conversion", "funnel_conversion_detail", "lesson_breakdown", "stage_funnel")


def _kst_now():
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(time.time() + 9 * 3600))


def key_of(params):
    """쿼리 → 열쇠 문자열(정렬 · action·_pv 제외). 화면이 어떤 순서로 붙여도 같은 행에 맞는다."""
    return urllib.parse.urlencode(sorted((k, v) for k, v in params.items() if k not in ("action", "_pv")))


def store(conn, action, params, data, now):
    with conn:
        conn.execute("INSERT INTO funnel_cache (tenant_id, action, params, data, synced_at) VALUES (%s,%s,%s,%s,%s)"
                     " ON CONFLICT (tenant_id, action, params) DO UPDATE SET data=EXCLUDED.data, synced_at=EXCLUDED.synced_at",
                     (db.TENANT, action, key_of(params), json.dumps(data, ensure_ascii=False), now))


def month_ranges(today):
    first = today.replace(day=1)
    out = [(first, today)]                                   # 이번달 1일~오늘
    for _ in range(2):                                       # 지난 2개월은 1일~말일
        last = first - timedelta(days=1)
        first = last.replace(day=1)
        out.append((first, last))
    return out


def main():
    load_env()
    conn = db.connect()
    now, failed = _kst_now(), []
    jobs = [(a, {}) for a in PLAIN]
    today = date.fromtimestamp(time.time() + 9 * 3600)
    jobs += [("period_breakdown", {"from": f.isoformat(), "to": t.isoformat()}) for f, t in month_ranges(today)]
    # member_calendar — 예약 달력(배1039-A). 화면 기본 노출 범위(이전·이번·다음 달)만 미리 데운다.
    # 다른 달은 api_funnel.py 의 캐시미스 1회 폴백이 채운다(월별 캐시 키라 안전).
    cal_first = today.replace(day=1)
    cal_prev = (cal_first - timedelta(days=1)).replace(day=1)
    cal_next = (cal_first + timedelta(days=32)).replace(day=1)
    jobs += [("member_calendar", {"month": m.strftime("%Y-%m")}) for m in (cal_prev, cal_first, cal_next)]
    for action, params in jobs:
        data = gas_get(action, params)
        if data is None:
            failed.append(action)
            continue
        store(conn, action, params, data, now)
    with conn:
        db.meta_set(conn, "funnel_last_sync", now)
        db.meta_set(conn, "funnel_last_failed", ",".join(failed))
    conn.close()
    print("funnel sync %s · %d/%d ok%s" % (now, len(jobs) - len(failed), len(jobs), (" · 실패 " + ",".join(failed)) if failed else ""))
    return 1 if failed else 0


def selftest():
    db.TENANT = "selftest"                      # 같은 DB · 다른 tenant — 실데이터는 한 줄도 안 건드린다
    conn = db.connect()
    store(conn, "period_breakdown", {"to": "2026-09-03", "from": "2026-09-01", "_pv": "1"}, {"ok": True, "n": 1}, _kst_now())
    store(conn, "period_breakdown", {"from": "2026-09-01", "to": "2026-09-03"}, {"ok": True, "n": 2}, _kst_now())   # 순서 달라도 같은 행
    with conn:
        rows = conn.execute("SELECT params, data FROM funnel_cache WHERE tenant_id=%s AND action='period_breakdown'", (db.TENANT,)).fetchall()
    conn.close()
    assert len(rows) == 1 and rows[0]["params"] == "from=2026-09-01&to=2026-09-03" and json.loads(rows[0]["data"])["n"] == 2, rows
    assert month_ranges(date(2026, 9, 3))[2] == (date(2026, 7, 1), date(2026, 7, 31))
    print("selftest ok")
    return 0


if __name__ == "__main__":
    sys.exit(selftest() if "--selftest" in sys.argv else main())
