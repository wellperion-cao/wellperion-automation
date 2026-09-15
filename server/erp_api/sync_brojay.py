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

★ 2026-09-15 추가(배 2663·2664 · GM 지시) — 세 가지를 더 담는다. 값은 같은 api.env 에 한 줄씩(없으면 그 kind 만 건너뛴다 — 매출·입장은 그대로 돈다).
    BROJAY_SESSIONS_URL=https://api.broj.co.kr/v1/schedules?group_id=<센터>&search_start={date}&search_end={date}
        kind=sessions · 날짜 열쇠. 강습 일정마다 reservations.booked[].attendance(SHOW/NOSHOW)·ticket(잔여 회차)·
        trainer_ids·lesson_minus_count(차감 횟수)가 그대로 온다 = 「출석 차감 기록」의 원천(사양서 getScheduleList).
    BROJAY_MEMBERS_URL=https://api.broj.co.kr/v1/members?group_id=<센터>&limit=200
        kind=members · 스냅샷(열쇠=받은 날짜 · 최신 한 벌만 남긴다). member_id·name·phone_number 로 결제↔회원 다리.
    BROJAY_TRAINERS_URL=https://api.broj.co.kr/v1/trainers?group_id=<센터>
        kind=trainers · 스냅샷. sessions 의 trainer_ids 를 이름으로 바꾸는 표(37명 · 1콜).
  스냅샷 두 kind 는 하루 한 번만 부른다(그날 열쇠가 이미 있으면 건너뜀 · --snapshots 로 강제). 콜 = members 50(9,837명 · 탈퇴·만료 포함 전원 · 200명/장) + trainers 1 = 하루 51 → 월 약 1,550(무료 10,000 의 16%).
  장 넘김: 응답 pagination.has_next 면 next_cursor 를 cursor= 로 이어 부른다(사양서 Pagination — 매출·회원 공통).

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
import urllib.parse
import urllib.request
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sync_inquiries import db, load_env  # noqa: E402  — 같은 api.env · 같은 DB 접속 자리

SOURCES = [("sales", "BROJAY_SALES_URL"), ("entries", "BROJAY_ENTRIES_URL")]
OPTIONAL_DAILY = [("sessions", "BROJAY_SESSIONS_URL")]                                 # 날짜 열쇠 · env 없으면 건너뜀
SNAPSHOTS = [("members", "BROJAY_MEMBERS_URL"), ("trainers", "BROJAY_TRAINERS_URL")]   # 하루 1회 · 최신 한 벌만
DEFAULT_AUTH = "Authorization: Bearer {key}"


def kst_now():
    return time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(time.time() + 9 * 3600))


def days(frm, to):
    """frm~to 양끝 포함 날짜 목록. 거꾸로 주면 빈 목록(구간을 지어내지 않는다)."""
    a, b = date.fromisoformat(frm), date.fromisoformat(to)
    return [(a + timedelta(days=i)).isoformat() for i in range((b - a).days + 1)]


CALL_GAP = 1.1          # 호출 사이 초 — 브로제이 분당 60 콜 제한 아래로. ponytail: 고정 간격 · 429 재시도는 다음 cron 이 한다
MAX_PAGES = 100         # 폭주 방지 — 회원 명단이 9,837명=50장(2026-09-15 실측)이라 50 이면 딱 걸린다 · 이보다 많으면 사양 변경이니 사람이 본다
_PAGE_RE = re.compile(r"([?&]page_index=)(\d+)")


def _one(url, headers, timeout):
    """한 장 조회. 성공 = 파싱된 JSON, 실패 = None."""
    time.sleep(CALL_GAP)                 # 분당 60 제한(429) — 소급 8일치를 한숨에 부르다 걸렸다(2026-09-15 실측)
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:  # noqa: BLE001 — 사유를 찍고 그 날짜는 건드리지 않는다
        print("[warn] %s 조회 실패: %s: %s" % (url.split("?")[0], type(e).__name__, str(e)[:150]))
        return None


def _cursor_pages(url, headers, timeout, label):
    """커서 장 넘김(사양서 Pagination: has_next 면 next_cursor 를 다음 요청 cursor= 로). 한 장이면 응답 그대로,
    여러 장이면 data 를 이어 붙인 {"data": [...], "_pages": n}. 목록으로 오는 응답(/v1/trainers)은 {"data": 목록} 으로 감싼다.
    중간 장이 실패하면 None — 반쪽을 저장하지 않는다."""
    d = _one(url, headers, timeout)
    if d is None:
        return None
    if isinstance(d, list):
        return {"data": d}
    pg = d.get("pagination") if isinstance(d, dict) else None
    if not (isinstance(pg, dict) and pg.get("has_next")):
        return d
    rows, page = list(d.get("data") or []), 1
    while isinstance(pg, dict) and pg.get("has_next") and page < MAX_PAGES:
        cur = pg.get("next_cursor")
        if not cur:
            print("[warn] %s %s has_next 인데 next_cursor 가 비었다 — 반쪽 저장을 막는다" % (url.split("?")[0], label))
            return None
        d = _one(url + "&cursor=" + urllib.parse.quote(str(cur), safe=""), headers, timeout)
        if d is None:
            return None
        rows.extend(d.get("data") or [])
        pg = d.get("pagination")
        page += 1
    if isinstance(pg, dict) and pg.get("has_next"):
        print("[warn] %s %s 장이 %d 을 넘었다 — 사양 변경 의심, 저장하지 않는다" % (url.split("?")[0], label, MAX_PAGES))
        return None
    return {"data": rows, "_pages": page}


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
        return _cursor_pages(url, headers, timeout, day)

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


def _has(conn, kind, key):
    with conn:
        return conn.execute("SELECT 1 FROM brojay_records WHERE tenant_id=%s AND kind=%s AND key=%s",
                            (db.TENANT, kind, key)).fetchone() is not None


def prune_snapshots(conn, fresh):
    """스냅샷 kind 는 최신 한 벌만 남긴다 — 회원 명단 한 벌이 2~3MB 라 날마다 쌓으면 표가 부풀 뿐 쓸 데가 없다.
    fresh = [(kind, key)] 방금 넣은 것. 그 열쇠보다 오래된 같은 kind 행을 지운다."""
    with conn:
        for kind, key in fresh:
            conn.execute("DELETE FROM brojay_records WHERE tenant_id=%s AND kind=%s AND key < %s", (db.TENANT, kind, key))


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
    flags, argv = [a for a in argv if a.startswith("--")], [a for a in argv if not a.startswith("--")]
    frm, to = (argv[0], argv[1]) if len(argv) >= 2 else ((today - timedelta(days=1)).isoformat(), today.isoformat())
    auth = os.environ.get("BROJAY_AUTH", DEFAULT_AUTH)
    want, items = 0, []
    for kind, env in SOURCES + OPTIONAL_DAILY:
        url = os.environ.get(env, "")
        if not url:
            print("[skip] %s 없음 — kind=%s 는 api.env 에 그 줄을 넣으면 그때부터 담긴다" % (env, kind))
            continue
        for day in days(frm, to):
            want += 1
            d = fetch(url, key, auth, day)
            if d is not None:
                items.append((kind, day, d))
    snap_key = today.isoformat()
    for kind, env in SNAPSHOTS:
        url = os.environ.get(env, "")
        if not url:
            print("[skip] %s 없음 — kind=%s 는 api.env 에 그 줄을 넣으면 그때부터 담긴다" % (env, kind))
            continue
        if "--snapshots" not in flags and _has(conn, kind, snap_key):
            continue                                       # 오늘 치가 있으면 다시 안 부른다(콜 예산)
        want += 1
        d = fetch(url, key, auth, snap_key)
        if d is not None:
            items.append((kind, snap_key, d))
    if items:
        print("[ok] %d/%d 건 적재 (%s~%s)" % (upsert(conn, items, now), want, frm, to))
        prune_snapshots(conn, [(k, key_) for k, key_, _ in items if k in dict(SNAPSHOTS)])
    ok = len(items) == want and want > 0
    with conn:
        if ok:
            db.meta_set(conn, "brojay_last_sync", now)
        db.meta_set(conn, "brojay_last_failed", "" if ok else now + " 일부 실패 — 빠진 날짜는 기존 값 유지")
    conn.close()
    print("[done] %s · %s" % (now, "정상" if ok else "일부 실패"))
    return 0 if ok else 1


def _selfcheck_cursor():
    """커서 장 넘김 — 네트워크 없이 _one 을 가짜로 바꿔 본다. 세 장을 이어 붙이고, 목록 응답은 감싸고, has_next 인데 커서가 없으면 None."""
    global _one
    real = _one
    pages = {"": {"data": [1, 2], "pagination": {"has_next": True, "next_cursor": "c1"}},
             "c1": {"data": [3], "pagination": {"has_next": True, "next_cursor": "c 2"}},
             "c%202": {"data": [4], "pagination": {"has_next": False}}}
    try:
        _one = lambda u, h, t: pages[u.partition("&cursor=")[2]]  # noqa: E731
        got = _cursor_pages("https://x/v1/members?limit=2", {}, 1, "t")
        assert got == {"data": [1, 2, 3, 4], "_pages": 3}, got
        _one = lambda u, h, t: [{"trainer_id": "a"}]  # noqa: E731
        assert _cursor_pages("https://x/v1/trainers", {}, 1, "t") == {"data": [{"trainer_id": "a"}]}
        _one = lambda u, h, t: {"data": [1], "pagination": {"has_next": True}}  # noqa: E731
        assert _cursor_pages("https://x/v1/members", {}, 1, "t") is None, "커서 없는 has_next 는 저장 금지"
        _one = lambda u, h, t: {"data": [1], "pagination": {"has_next": False}}  # noqa: E731
        assert _cursor_pages("https://x/v1/sales", {}, 1, "t") == {"data": [1], "pagination": {"has_next": False}}
    finally:
        _one = real
    print("selfcheck cursor ok")
    return 0


def selftest():
    _selfcheck_cursor()
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
        upsert(conn, [("members", "2026-09-14", {"data": []}), ("members", "2026-09-15", {"data": [1]})], "t2")
        assert not _has(conn, "members", "2026-09-16") and _has(conn, "members", "2026-09-14")
        prune_snapshots(conn, [("members", "2026-09-15")])
        keys = [r["key"] for r in conn.execute("SELECT key FROM brojay_records WHERE tenant_id=%s AND kind='members'", T).fetchall()]
        assert keys == ["2026-09-15"], "스냅샷은 최신 한 벌만 남는다: %s" % keys
    finally:
        with conn:
            conn.execute("DELETE FROM brojay_records WHERE tenant_id=%s", T)
        conn.close()
    print("selftest ok")
    return 0


if __name__ == "__main__":
    sys.exit(selftest() if "--selftest" in sys.argv else _selfcheck_cursor() if "--selfcheck" in sys.argv else main(sys.argv[1:]))
