# -*- coding: utf-8 -*-
"""구글시트 gviz 직접 읽기 화면 2종 → 서버 sales_cache 거울 (읽기 전용) — 배12615 · CFO(나우열M) 요청 2026-09-14.

CFO 화면(cfo/finance/매출지출현황.html)이 gviz 를 fetch 로 직접 읽던 것 중 요청서3 우선순위 🔴1·2 만 옮긴다.
sales_cache(sync_sales.py) 를 그대로 쓴다 — gas="sheet", action="labor"|"expense", params 없음(빈 열쇠).
저장 모양 = gviz 원본 그대로(화면 loadData·loadDeptPnl 과 같은 자르기: JSON.parse(첫'{' ~ 마지막'}')) —
칸 이름을 새로 짓지 않는다. 화면은 통로가 붙으면 주소 한 줄만 바꾼다(CFO 가 함).

  labor    강사 인건비 마스터 시트(46행×12개월, gid 없음=첫 시트) — 시트 id 는 화면 SHEET_ID 그대로
  expense  26년 총지출분석 시트 gid 1837105712(부서별 손익 9서브테이블) — 시트 id 는 화면 OPS_SHEET 그대로

실행: python3 /srv/erp/api/sync_sheet.py   (cron 5분 · 요청서3 §1 · 시토가 크론에 얹는다)
      python3 sync_sheet.py --only labor  — 한 열쇠만 TTL 무시하고 즉시
자체점검: python3 sync_sheet.py --selftest
  ①껍데기 벗기기·모양 검사는 네트워크 없이 돈다(이 부분은 이 PC 에서도 통과 실측함).
  ②DB 라운드트립은 같은 DB 의 tenant 'selftest' — 이 PC 엔 ERP_DB_URL 이 없어 RuntimeError 로 건너뛴다.
    시토가 서버에서 --selftest 로 이어 확인한다.
"""
import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sync_inquiries import db, load_env  # noqa: E402  — 같은 env·같은 DB
from sync_sales import _kst_now, fresh, store  # noqa: E402  — sales_cache 관례 재사용(캐시 표는 새로 안 만든다)

GAS = "sheet"
# (시트 id, gid) — gid 없으면(None) 첫 시트. id 는 화면(cfo/finance/매출지출현황.html) SHEET_ID·OPS_SHEET 그대로.
SHEETS = {
    "labor": ("1uAmZXX0GbiDImORxEwnDFm4_C-r0W43s-_tV_cPq9lE", None),
    "expense": ("1gCQNny8TDls5SjrtMkINu4HCltvFkoXmkTeXO_c3q58", "1837105712"),
}
TTL_MIN = 5   # 요청서3 §1 5분 cron


def unwrap(text):
    """gviz 응답 껍데기 벗기기 — 화면(`t.substring(t.indexOf("{"),t.lastIndexOf("}")+1)`)과 같은 자르기."""
    i, j = text.find("{"), text.rfind("}")
    if i < 0 or j < i:
        raise ValueError("gviz 응답에 JSON 이 없다: %s" % text[:120])
    return json.loads(text[i:j + 1])


def gviz_fetch(key, timeout=60):
    """시트 1회. 성공 시 dict(gviz 응답 그대로), 실패 시 None(지어내지 않는다)."""
    sheet_id, gid = SHEETS[key]
    url = "https://docs.google.com/spreadsheets/d/%s/gviz/tq?tqx=out:json" % sheet_id
    if gid:
        url += "&gid=" + gid
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "wellperion-erp-api"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = unwrap(r.read().decode("utf-8"))
    except Exception as e:
        print("[warn] sheet/%s 조회 실패: %s: %s" % (key, type(e).__name__, str(e)[:160]))
        return None
    if data.get("status") != "ok" or not isinstance(data.get("table"), dict):
        print("[warn] sheet/%s 응답 status!=ok: %s" % (key, str(data)[:160]))
        return None
    return data


def main(only=""):
    load_env()
    conn = db.connect()
    db.init_schema(conn)                       # 멱등 — sales_cache 는 이미 있다(새 표 없음)
    now = _kst_now()
    n_ok, n_skip, failed = 0, 0, []
    for key in SHEETS:
        if only and key != only:
            continue
        if not only and fresh(conn, now, GAS, key, {}, TTL_MIN):
            n_skip += 1
            continue
        data = gviz_fetch(key)
        if data is None:
            failed.append(key)
            continue
        store(conn, GAS, key, {}, data, now)
        n_ok += 1
    if not only:
        with conn:
            db.meta_set(conn, "sheet_last_sync", now)
            db.meta_set(conn, "sheet_last_failed", ",".join(failed))
    conn.close()
    print("sheet sync%s %s · 갱신 %d · 건너뜀 %d · 실패 %s" % (" " + only if only else "", now, n_ok, n_skip, failed or "없음"))
    return 1 if failed else 0


def selftest():
    # ① 껍데기 벗기기 — 네트워크 없이. 실제 gviz 응답 모양: `/*O_o*/\ngoogle.visualization.Query.setResponse({...});`
    sample = '/*O_o*/\ngoogle.visualization.Query.setResponse({"status":"ok","table":{"cols":[],"rows":[{"c":[{"v":1}]}]}});\n'
    d = unwrap(sample)
    assert d["status"] == "ok" and d["table"]["rows"][0]["c"][0]["v"] == 1, d
    try:
        unwrap("no json here")
        raise AssertionError("중괄호가 없으면 ValueError 여야 한다")
    except ValueError:
        pass
    assert set(SHEETS) == {"labor", "expense"}, SHEETS
    assert SHEETS["labor"][1] is None, "인건비 마스터는 gid 없이 첫 시트"
    assert SHEETS["expense"][1] == "1837105712", "총지출분석은 부서별 손익 탭 gid 여야 한다(화면 DEPT_PNL_GVIZ 와 같다)"
    print("selftest ok — 껍데기 벗기기·모양 검사")
    # ② DB 라운드트립 — 같은 DB 의 tenant 'selftest'. 이 PC 엔 ERP_DB_URL 이 없어 여기부터는 서버에서 확인한다.
    db.TENANT = "selftest"
    try:
        conn = db.connect()
    except RuntimeError as e:
        print("[skip] DB 라운드트립 — 이 PC 엔 DB 접속정보 없음(%s) · 시토가 서버에서 --selftest 로 이어 확인" % e)
        return 0
    db.init_schema(conn)
    try:
        with conn:
            conn.execute("DELETE FROM sales_cache WHERE tenant_id=%s AND gas=%s", (db.TENANT, GAS))
        store(conn, GAS, "labor", {}, {"status": "ok", "table": {"rows": [1]}}, "2026-09-14 18:00:00")
        assert fresh(conn, "2026-09-14 18:03:00", GAS, "labor", {}, TTL_MIN), "5분 안 = 건너뜀"
        assert not fresh(conn, "2026-09-14 18:06:00", GAS, "labor", {}, TTL_MIN), "5분 밖 = 다시 떠온다"
        r = conn.execute("SELECT data FROM sales_cache WHERE tenant_id=%s AND gas=%s AND action='labor'",
                         (db.TENANT, GAS)).fetchone()
        assert json.loads(r["data"])["table"]["rows"] == [1], r
    finally:
        with conn:
            conn.execute("DELETE FROM sales_cache WHERE tenant_id=%s AND gas=%s", (db.TENANT, GAS))
        conn.close()
    print("selftest ok — DB 라운드트립")
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    _i = sys.argv.index("--only") if "--only" in sys.argv else -1
    sys.exit(main(sys.argv[_i + 1] if _i >= 0 and _i + 1 < len(sys.argv) else ""))
