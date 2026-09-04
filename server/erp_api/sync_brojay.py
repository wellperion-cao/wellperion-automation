# -*- coding: utf-8 -*-
"""브로제이(외부 CRM) 매출·입장 → 서버 PostgreSQL 적재 (읽기 전용 단방향 · 배 959).

하루치를 날짜 열쇠로 담는다 — kind = sales(일 매출·계약 건별) · entries(입장). 응답을 통째로 싣는 것은
lesson_records 와 같은 이유다: 브로제이 칸 이름을 우리가 정규화하면 그쪽이 바뀔 때마다 깨진다.
대조·집계는 읽는 쪽(api_brojay.py · 화면)이 한다. 브로제이에는 절대 쓰지 않는다(읽기 전용 원칙).

★ 2026-09-04 현재 브로제이 API 사양·계정 미수령(배 908 대기). 그래서 호출 모양을 코드에 박지 않고
  /srv/erp/api.env 4줄로 뺐다 — 사양이 오면 코드 수정·배포 없이 그 4줄만 채우면 그 자리에서 돈다.
    BROJAY_SALES_URL=https://<브로제이>/<매출경로>?date={date}
    BROJAY_ENTRIES_URL=https://<브로제이>/<입장경로>?date={date}
    BROJAY_API_KEY=<발급키>
    BROJAY_AUTH=Authorization: Bearer {key}      (기본값 · 헤더 이름·접두가 다르면 이 줄만 바꾼다)
  자격증명이 없으면 아무것도 지어내지 않고 brojay_last_failed 에 사유를 적고 2번으로 끝난다.

실행: python3 /srv/erp/api/sync_brojay.py                       오늘+어제(KST)
      python3 /srv/erp/api/sync_brojay.py 2026-08-01 2026-09-03  소급 구간(첫 실행)
자체점검: python3 sync_brojay.py --selftest                      (tenant 'selftest' · 네트워크 없음)

예약 실행은 자격증명이 들어온 뒤에 건다 — 부를 곳이 없는데 5분마다 도는 것은 로그만 더럽힌다. 넣을 때 한 줄:
  sudo tee /etc/cron.d/erp-brojay-sync <<< '*/5 * * * * ec2-user /usr/bin/python3 /srv/erp/api/sync_brojay.py >> /srv/erp/sync_brojay.log 2>&1'
"""
import json
import os
import sys
import time
import urllib.request
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sync_inquiries import db, load_env  # noqa: E402  — 같은 api.env · 같은 DB 접속 자리

SOURCES = [("sales", "BROJAY_SALES_URL"), ("entries", "BROJAY_ENTRIES_URL")]
DEFAULT_AUTH = "Authorization: Bearer {key}"


def kst_now():
    return time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(time.time() + 9 * 3600))


def days(frm, to):
    """frm~to 양끝 포함 날짜 목록. 거꾸로 주면 빈 목록(구간을 지어내지 않는다)."""
    a, b = date.fromisoformat(frm), date.fromisoformat(to)
    return [(a + timedelta(days=i)).isoformat() for i in range((b - a).days + 1)]


def fetch(url_tpl, key, auth_tpl, day, timeout=60):
    """하루치 1회 조회. 성공 = 파싱된 JSON, 실패 = None(빈 값으로 덮어쓰지 않는다)."""
    name, _, val = auth_tpl.partition(":")
    headers = {"User-Agent": "wellperion-erp-api", name.strip(): val.strip().replace("{key}", key)}
    req = urllib.request.Request(url_tpl.replace("{date}", day), headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print("[warn] %s %s 조회 실패: %s: %s" % (url_tpl.split("?")[0], day, type(e).__name__, str(e)[:150]))
        return None


def upsert(conn, items, now):
    """(kind, 날짜, payload) 를 멱등 적재 — 같은 날짜를 다시 부르면 덮어쓴다."""
    with conn:
        conn.executemany(
            "INSERT INTO brojay_records (tenant_id, kind, key, data, synced_at) VALUES (%s,%s,%s,%s,%s)"
            " ON CONFLICT (tenant_id, kind, key) DO UPDATE SET data = EXCLUDED.data, synced_at = EXCLUDED.synced_at",
            [(db.TENANT, k, key, json.dumps(d, ensure_ascii=False), now) for k, key, d in items])
    return len(items)


def main(argv):
    load_env()
    now = kst_now()
    key = os.environ.get("BROJAY_API_KEY", "")
    urls = {k: os.environ.get(env, "") for k, env in SOURCES}
    missing = [env for k, env in SOURCES if not urls[k]] + ([] if key else ["BROJAY_API_KEY"])
    conn = db.connect()
    db.init_schema(conn)
    if missing:
        with conn:
            db.meta_set(conn, "brojay_last_failed", now + " 자격증명 없음: " + ",".join(missing))
        conn.close()
        print("[blocked] %s 없음 — /srv/erp/api.env 에 채우면 코드 수정 없이 그때부터 돈다" % ", ".join(missing))
        return 2

    today = date.fromisoformat(now[:10])
    frm, to = (argv[0], argv[1]) if len(argv) >= 2 else ((today - timedelta(days=1)).isoformat(), today.isoformat())
    auth = os.environ.get("BROJAY_AUTH", DEFAULT_AUTH)
    want, items = 0, []
    for kind, _ in SOURCES:
        for day in days(frm, to):
            want += 1
            d = fetch(urls[kind], key, auth, day)
            if d is not None:
                items.append((kind, day, d))
    if items:
        print("[ok] %d/%d 건 적재 (%s~%s)" % (upsert(conn, items, now), want, frm, to))
    ok = len(items) == want and want > 0
    with conn:
        if ok:
            db.meta_set(conn, "brojay_last_sync", now)
        db.meta_set(conn, "brojay_last_failed", "" if ok else now + " 일부 실패 — 빠진 날짜는 기존 값 유지")
    conn.close()
    print("[done] %s · %s" % (now, "정상" if ok else "일부 실패"))
    return 0 if ok else 1


def selftest():
    assert days("2026-09-03", "2026-09-04") == ["2026-09-03", "2026-09-04"]
    assert days("2026-09-04", "2026-09-04") == ["2026-09-04"]
    assert days("2026-09-04", "2026-09-03") == [], "거꾸로 준 구간은 비어야 한다"
    db.TENANT = "selftest"
    conn = db.connect()
    db.init_schema(conn)
    T = (db.TENANT,)
    try:
        assert upsert(conn, [("sales", "2026-09-03", {"total": 1}), ("entries", "2026-09-03", {"count": 7})], "t0") == 2
        assert upsert(conn, [("sales", "2026-09-03", {"total": 2})], "t1") == 1, "같은 날짜는 덮어쓴다"
        rows = conn.execute("SELECT kind, key, data FROM brojay_records WHERE tenant_id=%s ORDER BY kind", T).fetchall()
        assert len(rows) == 2, rows
        assert json.loads(rows[1]["data"])["total"] == 2, rows[1]
    finally:
        with conn:
            conn.execute("DELETE FROM brojay_records WHERE tenant_id=%s", T)
        conn.close()
    print("selftest ok")
    return 0


if __name__ == "__main__":
    sys.exit(selftest() if "--selftest" in sys.argv else main(sys.argv[1:]))
