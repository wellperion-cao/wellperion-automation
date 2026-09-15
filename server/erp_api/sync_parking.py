# -*- coding: utf-8 -*-
"""주차 매출 원천(랩스 ppark-wall) → 서버 PostgreSQL 적재 (읽기 전용 단방향 · 배 2668 · GM 지시 2026-09-15).

계정은 디스크에 두지 않는다 — 실행 때마다 GET /api/partner-secrets/fetch?tenant=wellperion&channel=parking
(헤더 X-Token-Push-Key = api.env ERP_TOKEN_PUSH_KEY)로 받아 메모리에만 둔다(project_partner_credentials_server_only_1531).
계정 자체는 ERP 플랫폼관리(erp/admin/index.html 파트너사 계정 표 · 코드 1531)에 GM 이 넣는다.

★ 2026-09-15 현재 계정 미수령 — 로그인 폼·parkStat 응답 모양을 실측하지 못했다. 그래서 셋을 env 로 뺐다
  (/srv/erp/api.env, 없으면 기본값으로 시도하되 실패해도 추측으로 값을 만들지 않는다):
    PARKING_LOGIN_URL   기본 http://ppark-wall.iptime.org:8280/login       로그인 POST 주소
    PARKING_LOGIN_ID_FIELD / PARKING_LOGIN_PW_FIELD   기본 userId / userPw   로그인 폼 칸 이름
    PARKING_STAT_URL    기본 http://ppark-wall.iptime.org:8280/parkStat?parkId=1057&date={date}   일 매출 조회
    PARKING_REVENUE_FIELD   매출 칸 경로("data.total" 처럼 점으로 중첩) — 없으면 revenue_krw=None,
                            raw 원문은 항상 담는다(칸 이름을 지어내 잘못된 값을 저장하지 않는다).
  ponytail: 로그인 성공 판정은 "예외 없이 200번대"뿐이다(진짜 로그인 성공/실패 신호는 실측 후 갈아끼운다).

실행: python3 /srv/erp/api/sync_parking.py                오늘(KST)
      python3 /srv/erp/api/sync_parking.py 2026-09-01 2026-09-14   소급 구간
자체점검: python3 sync_parking.py --selftest              (tenant 'selftest' · 네트워크 없음)

예약 실행은 계정이 들어온 뒤에 건다:
  sudo tee /etc/cron.d/erp-parking-sync <<< '*/30 * * * * ec2-user /usr/bin/python3 /srv/erp/api/sync_parking.py >> /srv/erp/sync_parking.log 2>&1'
"""
import json
import os
import sys
import time

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sync_brojay import days, kst_now  # noqa: E402 — 같은 날짜 유틸 재사용(브로제이와 중복 구현 안 함)
from sync_inquiries import load_env  # noqa: E402 — 같은 api.env

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common import db  # noqa: E402

KIND = "daily"
CALL_GAP = 1.0          # ponytail: 고정 간격 — 실제 제한값 실측 전엔 브로제이(1.1초)와 같은 자릿수로 보수적으로
SELF_BASE_URL = os.environ.get("ERP_SELF_BASE_URL", "http://127.0.0.1:8000")  # api_hr.py AUTH_CHECK_URL_DEFAULT 와 같은 관례


def _env(name, default):
    return os.environ.get(name, default)


def fetch_creds():
    """서버 자신의 /api/partner-secrets/fetch 로 이번 실행분 계정만 받는다. 없으면 (None, None)."""
    key = os.environ.get("ERP_TOKEN_PUSH_KEY", "")
    if not key:
        print("[warn] ERP_TOKEN_PUSH_KEY 없음 — 계정을 받을 수 없다")
        return None, None
    try:
        r = requests.get(SELF_BASE_URL + "/api/partner-secrets/fetch",
                          params={"tenant": db.TENANT, "channel": "parking"},
                          headers={"X-Token-Push-Key": key}, timeout=10)
        d = r.json()
    except Exception as e:  # noqa: BLE001
        print("[warn] 계정 조회 실패: %s: %s" % (type(e).__name__, str(e)[:150]))
        return None, None
    if not d.get("ok"):
        print("[warn] 계정 없음: %s" % d.get("error", ""))
        return None, None
    return d.get("id", ""), d.get("pw", "")


def _login(session, user_id, pw):
    """랩스(ppark-wall) 로그인. 성공 = True. 폼 모양이 실측 전이라 상태코드만 본다(ponytail 위 문서 참고)."""
    url = _env("PARKING_LOGIN_URL", "http://ppark-wall.iptime.org:8280/login")
    id_field = _env("PARKING_LOGIN_ID_FIELD", "userId")
    pw_field = _env("PARKING_LOGIN_PW_FIELD", "userPw")
    try:
        r = session.post(url, data={id_field: user_id, pw_field: pw}, timeout=15)
        return r.status_code < 400
    except Exception as e:  # noqa: BLE001
        print("[warn] 로그인 실패: %s: %s" % (type(e).__name__, str(e)[:150]))
        return False


def extract_revenue(data, field_path):
    """field_path="data.total" 처럼 점으로 중첩된 칸을 뽑는다. 없거나 숫자가 아니면 None(지어내지 않는다)."""
    if not field_path:
        return None
    cur = data
    for part in field_path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    if isinstance(cur, bool):
        return None
    if isinstance(cur, (int, float)):
        return int(cur)
    if isinstance(cur, str):
        try:
            return int(cur.replace(",", "").strip())
        except ValueError:
            return None
    return None


def fetch_day(session, day):
    """하루치 parkStat 조회. 성공 = {"revenue_krw":…, "raw":…}, 실패 = None(그 날은 안 건드린다)."""
    time.sleep(CALL_GAP)
    url = _env("PARKING_STAT_URL", "http://ppark-wall.iptime.org:8280/parkStat?parkId=1057&date={date}").replace("{date}", day)
    try:
        r = session.get(url, timeout=30)
        if r.status_code >= 400:
            print("[warn] %s 조회 실패: HTTP %d" % (day, r.status_code))
            return None
        try:
            raw = r.json()
        except ValueError:
            raw = {"_raw_text": r.text[:5000]}
    except Exception as e:  # noqa: BLE001
        print("[warn] %s 조회 실패: %s: %s" % (day, type(e).__name__, str(e)[:150]))
        return None
    return {"revenue_krw": extract_revenue(raw, _env("PARKING_REVENUE_FIELD", "")), "raw": raw}


def upsert(conn, items, now):
    """(날짜, payload) 를 멱등 적재 — 같은 날짜를 다시 부르면 덮어쓴다."""
    with conn:
        conn.executemany(
            "INSERT INTO parking_records (tenant_id, kind, key, data, synced_at) VALUES (%s,%s,%s,%s,%s)"
            " ON CONFLICT (tenant_id, kind, key) DO UPDATE SET data = EXCLUDED.data, synced_at = EXCLUDED.synced_at",
            [(db.TENANT, KIND, key, json.dumps(d, ensure_ascii=False), now) for key, d in items])
    return len(items)


def main(argv):
    load_env()
    now = kst_now()
    conn = db.connect()
    db.init_schema(conn)
    user_id, pw = fetch_creds()
    if not user_id or not pw:
        with conn:
            db.meta_set(conn, "parking_last_failed", now + " 계정 없음 — ERP 플랫폼관리(코드 1531)에 parking 계정을 넣으면 그때부터 돈다")
        conn.close()
        print("[blocked] 계정 없음")
        return 2

    from datetime import date, timedelta
    today = date.fromisoformat(now[:10])
    frm, to = (argv[0], argv[1]) if len(argv) >= 2 else ((today - timedelta(days=1)).isoformat(), today.isoformat())

    session = requests.Session()
    if not _login(session, user_id, pw):
        with conn:
            db.meta_set(conn, "parking_last_failed", now + " 로그인 실패")
        conn.close()
        print("[blocked] 로그인 실패")
        return 2

    want, items = 0, []
    for day in days(frm, to):
        want += 1
        d = fetch_day(session, day)
        if d is not None:
            items.append((day, d))
    if items:
        print("[ok] %d/%d 건 적재 (%s~%s)" % (upsert(conn, items, now), want, frm, to))
    ok = len(items) == want and want > 0
    with conn:
        if ok:
            db.meta_set(conn, "parking_last_sync", now)
        db.meta_set(conn, "parking_last_failed", "" if ok else now + " 일부 실패 — 빠진 날짜는 기존 값 유지")
    conn.close()
    print("[done] %s · %s" % (now, "정상" if ok else "일부 실패"))
    return 0 if ok else 1


def selftest():
    assert extract_revenue({"data": {"total": 12000}}, "data.total") == 12000
    assert extract_revenue({"data": {"total": "12,000"}}, "data.total") == 12000
    assert extract_revenue({"data": {}}, "data.total") is None, "없는 칸은 None"
    assert extract_revenue({"data": {"total": "abc"}}, "data.total") is None, "숫자 아니면 None"
    assert extract_revenue({"total": 1}, "") is None, "필드명 없으면 지어내지 않는다"

    db.TENANT = "selftest"
    conn = db.connect()
    db.init_schema(conn)
    T = (db.TENANT,)
    try:
        assert upsert(conn, [("2026-09-14", {"revenue_krw": 10000, "raw": {}}), ("2026-09-15", {"revenue_krw": None, "raw": {"x": 1}})], "t0") == 2
        assert upsert(conn, [("2026-09-14", {"revenue_krw": 20000, "raw": {}})], "t1") == 1, "같은 날짜는 덮어쓴다"
        rows = conn.execute("SELECT key, data FROM parking_records WHERE tenant_id=%s ORDER BY key", T).fetchall()
        assert len(rows) == 2, rows
        assert json.loads(rows[0]["data"])["revenue_krw"] == 20000, rows[0]
    finally:
        with conn:
            conn.execute("DELETE FROM parking_records WHERE tenant_id=%s", T)
        conn.close()
    print("selftest ok")
    return 0


if __name__ == "__main__":
    sys.exit(selftest() if "--selftest" in sys.argv else main([a for a in sys.argv[1:] if not a.startswith("--")]))
