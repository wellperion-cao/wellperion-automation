# -*- coding: utf-8 -*-
"""매출·지출 집계 GAS 3종 → 서버 PostgreSQL 거울 (읽기 전용 단방향) — 배 960 레인 E.

sync_funnel.py 와 같은 규칙이다. 화면들이 이미 부르는 읽기 액션을 그대로 부르고 응답을 통째로 저장한다 —
시트·GAS 는 절대 쓰지 않는다. 표 하나(sales_cache)에 (gas, action, params) 열쇠로 싣는다.
  salesops  매출 배관 sales-api(.deploy-salesops) — sales_dept_pub · sales_instr_pub(월별) ·
            sales_month · sales_ops · sales_dept · labor_time(게이트 비번 POST)
  proc      운영요약 — sales_instr_pub(월별) · proc_summary · sales_dept(게이트 비번 POST)
  deptrep   보고시트 — dump(보고탭 · 일자탭 구간) · lesson(강습 신규·재등록)
화면 = CFO 매출지출현황 · 월간운영계획 · 매출회원현황보고 · 파트너팀 체계.

무거운 집계(수십 초)는 매 5분마다 다시 부르면 GAS 실행 할당량을 먹는다 — 액션마다 TTL(분)을 두고
그보다 새 것은 건너뛴다. 지난달 강사별 공개값은 안 변하므로 하루 1회면 된다.
보고시트는 이번 달 파일 id 를 ERP GAS(daily_report_sheet)로 먼저 찾아 붙인다(화면과 같은 해석).

실행: python3 /srv/erp/api/sync_sales.py   (cron 5분 · /etc/cron.d/erp-sales-sync)
자체점검: python3 sync_sales.py --selftest  (같은 DB 의 tenant 'selftest' · 네트워크 없음)
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sync_inquiries import db, load_env  # noqa: E402  — 같은 env·같은 DB

GAS_ENV = {"salesops": "SALES_GAS_URL", "proc": "PROC_GAS_URL", "deptrep": "DEPTREP_GAS_URL"}
POST_ACTIONS = ("sales_month", "sales_ops", "sales_dept", "labor_time", "proc_summary")   # 게이트 비번 POST 집계
ACTIONS = {"salesops": ("sales_dept_pub", "sales_instr_pub", "sales_month", "sales_ops", "sales_dept", "labor_time"),
           "proc": ("sales_instr_pub", "proc_summary", "sales_dept"),
           "deptrep": ("dump", "lesson")}
# 열쇠에서 뺄 쿼리 — 액션 이름·캐시깨기·인증·이번달 파일 id(달마다 바뀌지만 같은 '이번 달 보고'다)
DROP = ("action", "_pv", "cb", "_cb", "nocache", "token", "password", "file", "dump", "lesson")
DAY_RANGES = ("A1:S20", "A21:N45", "A46:N60")   # 매출회원현황보고 일자탭 3조각(한 번에 400칸 제한)


def _kst_now():
    return time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(time.time() + 9 * 3600))


def _kst_today():
    return date.fromtimestamp(time.time() + 9 * 3600)


def key_of(params):
    """쿼리 → 열쇠 문자열(정렬 · DROP 제외). 화면이 어떤 순서로 붙여도 같은 행에 맞는다."""
    return urllib.parse.urlencode(sorted((k, str(v)) for k, v in params.items() if k not in DROP))


def gas_call(gas, action, params, timeout=180):
    """GAS 1회. 성공 시 dict(응답 그대로), 실패 시 None(지어내지 않는다)."""
    url = os.environ.get(GAS_ENV[gas], "")
    if not url:
        raise SystemExit("%s 없음 — /srv/erp/api.env 를 확인" % GAS_ENV[gas])
    q = {k: v for k, v in params.items() if k not in DROP}
    try:
        if gas == "deptrep":
            q.update({"token": os.environ.get("DEPTREP_TOKEN", ""), action: "1", "cb": int(time.time())})
            req = urllib.request.Request(url + "?" + urllib.parse.urlencode(q), headers={"User-Agent": "wellperion-erp-api"})
        elif action in POST_ACTIONS:
            body = dict(q, action=action, password=os.environ.get("SALES_GATE_PW", ""))
            req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), method="POST",
                                         headers={"Content-Type": "text/plain;charset=utf-8", "User-Agent": "wellperion-erp-api"})
        else:
            q.update({"action": action, "_pv": int(time.time())})
            req = urllib.request.Request(url + "?" + urllib.parse.urlencode(q), headers={"User-Agent": "wellperion-erp-api"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print("[warn] %s/%s %s 조회 실패: %s: %s" % (gas, action, key_of(params), type(e).__name__, str(e)[:120]))
        return None
    if not isinstance(data, dict) or not data.get("ok"):
        print("[warn] %s/%s %s 응답 ok=false" % (gas, action, key_of(params)))
        return None
    return data


def store(conn, gas, action, params, data, now):
    with conn:
        conn.execute("INSERT INTO sales_cache (tenant_id, gas, action, params, data, synced_at) VALUES (%s,%s,%s,%s,%s,%s)"
                     " ON CONFLICT (tenant_id, gas, action, params) DO UPDATE SET data=EXCLUDED.data, synced_at=EXCLUDED.synced_at",
                     (db.TENANT, gas, action, key_of(params), json.dumps(data, ensure_ascii=False), now))


def report_file():
    """이번 달 「2026년 N월 매출 보고」 파일 id — 화면(reportFile)과 같은 해석. 못 찾으면 빈 값(붙은 파일이 열린다)."""
    url = os.environ.get("TODO_GAS_URL", "")
    t = _kst_today()
    if not url:
        return ""
    q = {"action": "daily_report_sheet", "year": t.year, "month": t.month, "cb": int(time.time())}
    try:
        with urllib.request.urlopen(urllib.request.Request(url + "?" + urllib.parse.urlencode(q),
                                                           headers={"User-Agent": "wellperion-erp-api"}), timeout=60) as r:
            d = json.loads(r.read().decode("utf-8"))
        return d.get("fileId", "") if d.get("ok") else ""
    except Exception as e:
        print("[warn] daily_report_sheet 실패: %s: %s" % (type(e).__name__, str(e)[:120]))
        return ""


def jobs(today):
    """(gas, action, params, ttl분) — 화면이 부르는 읽기 액션 그대로. ttl = 이보다 새 거울은 건너뛴다."""
    cut, out = today.month, []
    out += [("salesops", "sales_dept_pub", {}, 15), ("salesops", "sales_instr_pub", {}, 15)]
    for m in range(1, cut + 1):
        ttl = 15 if m == cut else 1440          # 지난달 공개값은 안 변한다 — 하루 1회
        out += [("salesops", "sales_instr_pub", {"month": m}, ttl), ("proc", "sales_instr_pub", {"month": m}, ttl)]
    out += [("salesops", a, {}, 30) for a in ("sales_month", "sales_ops", "sales_dept", "labor_time")]
    out += [("proc", "proc_summary", {}, 30), ("proc", "sales_dept", {}, 30)]
    out += [("deptrep", "dump", {}, 5), ("deptrep", "lesson", {}, 5)]
    out += [("deptrep", "dump", {"sheet": today.day, "range": r}, 5) for r in DAY_RANGES]
    return out


def fresh(conn, now, gas, action, params, ttl):
    """거울이 ttl분 안에 갱신됐으면 True — 그만큼 GAS 를 안 부른다."""
    r = conn.execute("SELECT synced_at FROM sales_cache WHERE tenant_id=%s AND gas=%s AND action=%s AND params=%s",
                     (db.TENANT, gas, action, key_of(params))).fetchone()
    if not r:
        return False
    try:
        age = (time.mktime(time.strptime(now, "%Y-%m-%d %H:%M:%S")) - time.mktime(time.strptime(r["synced_at"], "%Y-%m-%d %H:%M:%S"))) / 60.0
    except ValueError:
        return False
    return 0 <= age < ttl


def main():
    load_env()
    conn = db.connect()
    db.init_schema(conn)                        # 멱등 — sales_cache 표가 없으면 만든다
    now, today = _kst_now(), _kst_today()
    fid = None
    n_ok, n_skip, failed = 0, 0, []
    for gas, action, params, ttl in jobs(today):
        if fresh(conn, now, gas, action, params, ttl):
            n_skip += 1
            continue
        if gas == "deptrep":
            if fid is None:
                fid = report_file()
            params = dict(params, file=fid) if fid else params
        data = gas_call(gas, action, params)
        if data is None:
            failed.append("%s/%s%s" % (gas, action, ("?" + key_of(params)) if key_of(params) else ""))
            continue                            # 실패 — 기존 거울을 그대로 둔다
        store(conn, gas, action, params, data, now)
        n_ok += 1
    with conn:
        db.meta_set(conn, "sales_last_sync", now)
        db.meta_set(conn, "sales_last_failed", ",".join(failed))
    conn.close()
    print("sales sync %s · 갱신 %d · 건너뜀 %d · 실패 %s" % (now, n_ok, n_skip, failed or "없음"))
    return 1 if failed else 0


def selftest():
    db.TENANT = "selftest"                      # 같은 DB · 다른 tenant — 실데이터는 한 줄도 안 건드린다
    conn = db.connect()
    db.init_schema(conn)
    try:
        with conn:
            conn.execute("DELETE FROM sales_cache WHERE tenant_id=%s", (db.TENANT,))
        assert key_of({"month": 8, "_pv": 1, "cb": 2, "file": "x", "action": "a"}) == "month=8", "열쇠는 캐시깨기·파일 id 를 뺀다"
        assert key_of({"range": "A1:S20", "sheet": 4}) == key_of({"sheet": "4", "range": "A1:S20"}), "순서·형이 달라도 같은 열쇠"
        store(conn, "proc", "sales_instr_pub", {"month": 8, "cb": 9}, {"ok": True, "n": 1}, "2026-09-04 10:00:00")
        store(conn, "proc", "sales_instr_pub", {"month": "8"}, {"ok": True, "n": 2}, "2026-09-04 10:20:00")
        rows = conn.execute("SELECT params, data FROM sales_cache WHERE tenant_id=%s AND gas='proc'", (db.TENANT,)).fetchall()
        assert len(rows) == 1 and rows[0]["params"] == "month=8" and json.loads(rows[0]["data"])["n"] == 2, rows
        assert fresh(conn, "2026-09-04 10:30:00", "proc", "sales_instr_pub", {"month": 8}, 15), "15분 안 = 건너뜀"
        assert not fresh(conn, "2026-09-04 11:00:00", "proc", "sales_instr_pub", {"month": 8}, 15), "15분 밖 = 다시 떠온다"
        assert not fresh(conn, "2026-09-04 10:30:00", "proc", "sales_instr_pub", {"month": 7}, 15), "없는 열쇠 = 다시 떠온다"
        j = jobs(date(2026, 9, 4))
        keys = {(g, a, key_of(p)) for g, a, p, _ in j}
        assert ("salesops", "sales_dept_pub", "") in keys and ("salesops", "sales_month", "") in keys
        assert ("proc", "sales_instr_pub", "month=1") in keys and ("proc", "sales_instr_pub", "month=9") in keys
        assert ("proc", "sales_instr_pub", "month=10") not in keys, "안 지난 달은 안 부른다"
        assert ("deptrep", "dump", "") in keys and ("deptrep", "dump", "range=A21%3AN45&sheet=4") in keys
        assert ("deptrep", "lesson", "") in keys
        assert [t for g, a, p, t in j if a == "sales_instr_pub" and p.get("month") == 8][0] == 1440, "지난달은 하루 1회"
        assert all(a in ACTIONS[g] for g, a, _, _ in j), "모든 일감은 API 허용 액션 안"
    finally:
        with conn:
            conn.execute("DELETE FROM sales_cache WHERE tenant_id=%s", (db.TENANT,))
        conn.close()
    print("selftest ok")
    return 0


if __name__ == "__main__":
    sys.exit(selftest() if "--selftest" in sys.argv else main())
