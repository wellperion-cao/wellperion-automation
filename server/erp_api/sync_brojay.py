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
import re
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


MAX_PAGES = 50          # 폭주 방지 — 하루치가 이보다 많으면 사양이 바뀐 것이니 사람이 본다
_PAGE_RE = re.compile(r"([?&]page_index=)(\d+)")


def _one(url, headers, timeout):
    """한 장 조회. 성공 = 파싱된 JSON, 실패 = None."""
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:  # noqa: BLE001 — 사유를 찍고 그 날짜는 건드리지 않는다
        print("[warn] %s 조회 실패: %s: %s" % (url.split("?")[0], type(e).__name__, str(e)[:150]))
        return None


def fetch(url_tpl, key, auth_tpl, day, timeout=60):
    """하루치 **전량** 조회. 성공 = {"data":[...]}, 실패 = None(빈 값으로 덮어쓰지 않는다).

    브로제이는 한 날이 여러 장이다(시포 실측 2026-09-08: 매출 27건 1장 · 입장 744건 4장).
    한 번만 부르면 입장이 200건에서 잘리는데, 잘린 줄 모르고 저장되는 것이 제일 나쁘다.
    장 넘기는 방식이 둘이라 갈라서 다룬다:
      · 입장 — 주소에 page_index=N. 0부터 올려 가며 빈 장이 나오면 멈춘다.
      · 매출 — 응답에 pagination{has_next,next_cursor}. 지금은 has_next=false 한 장으로 끝난다.
               ★has_next 가 true 인데 이어 부를 방법을 모르면 **그 날짜를 실패로 돌린다** —
               커서 파라미터 이름을 지어내 반쪽만 저장하느니 안 저장하는 쪽이 낫다(다음 실행이 다시 시도).
    """
    name, _, val = auth_tpl.partition(":")
    headers = {"User-Agent": "wellperion-erp-api", name.strip(): val.strip().replace("{key}", key)}
    url = url_tpl.replace("{date}", day)

    if not _PAGE_RE.search(url):
        d = _one(url, headers, timeout)
        if d is None:
            return None
        pg = d.get("pagination") if isinstance(d, dict) else None
        if isinstance(pg, dict) and pg.get("has_next"):
            print("[warn] %s %s 이어질 장이 있는데(has_next) 커서 사양을 몰라 반쪽 저장을 막는다 — 이 날짜는 건너뛴다"
                  % (url.split("?")[0], day))
            return None
        return d

    rows, page = [], 0
    while page < MAX_PAGES:
        d = _one(_PAGE_RE.sub(lambda m: m.group(1) + str(page), url), headers, timeout)
        if d is None:
            return None                      # 중간 장이 실패하면 그 날은 통째로 안 건드린다
        got = d.get("data") if isinstance(d, dict) else None
        if not isinstance(got, list) or not got:
            break
        rows.extend(got)
        page += 1
    else:
        print("[warn] %s %s 장이 %d 을 넘었다 — 사양 변경 의심, 저장하지 않는다" % (url.split("?")[0], day, MAX_PAGES))
        return None
    return {"data": rows, "_pages": page}


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
