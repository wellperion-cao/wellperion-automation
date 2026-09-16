# -*- coding: utf-8 -*-
"""주차 매출 원천(랩스 ppark-wall) → 서버 PostgreSQL 적재 (읽기 전용 단방향 · 배 2668 · GM 지시 2026-09-15).

계정은 디스크에 두지 않는다 — 실행 때마다 GET /api/partner-secrets/fetch?tenant=wellperion&channel=parking
(헤더 X-Token-Push-Key = api.env ERP_TOKEN_PUSH_KEY)로 받아 메모리에만 둔다(project_partner_credentials_server_only_1531).
계정 자체는 ERP 플랫폼관리(erp/admin/index.html 파트너사 계정 표 · 코드 1531)에 GM 이 넣는다.

2026-09-16 실측 완료(시토·계정 GM 등록 2026-09-15 18:38 이후) — 로그인·응답 모양 확정:
    로그인  POST http://ppark-wall.iptime.org:8280/login.htm  필드 loginId/loginPw (login.htm 폼 실측)
    통계    POST http://ppark-wall.iptime.org:8280/io/getParkStat  JSON 바디 {"searchParkId":"1057"}
            (parkStat.js 실측 — GET·date 파라미터 아님. 응답 data.salesCardTodayAmt/salesCashTodayAmt/salesEtcTodayAmt
             = "오늘" 누적만 제공, 과거 특정일 조회 API 없음 → 소급 구간 불가·매 실행은 오늘 하루치만 적재)
  env(선택 · /srv/erp/api.env, 없으면 위 실측값을 기본으로 쓴다):
    PARKING_LOGIN_URL / PARKING_LOGIN_ID_FIELD / PARKING_LOGIN_PW_FIELD / PARKING_STAT_URL / PARKING_PARK_ID

실행: python3 /srv/erp/api/sync_parking.py                오늘(KST) 누적 매출 1회 적재(멱등 — 여러 번 돌려도 최신값으로 덮어씀)
자체점검: python3 sync_parking.py --selftest              (tenant 'selftest' · 네트워크 없음)

예약 실행:
  sudo tee /etc/cron.d/erp-parking-sync <<< '*/30 * * * * ec2-user /usr/bin/python3 /srv/erp/api/sync_parking.py >> /srv/erp/sync_parking.log 2>&1'
"""
import json
import os
import sys
import time

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sync_brojay import kst_now  # noqa: E402 — 같은 날짜 유틸 재사용(브로제이와 중복 구현 안 함)
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
    """랩스(ppark-wall) 로그인. 성공 = True (실측 2026-09-16: login.htm 폼 필드 loginId/loginPw)."""
    url = _env("PARKING_LOGIN_URL", "http://ppark-wall.iptime.org:8280/login.htm")
    id_field = _env("PARKING_LOGIN_ID_FIELD", "loginId")
    pw_field = _env("PARKING_LOGIN_PW_FIELD", "loginPw")
    try:
        r = session.post(url, data={id_field: user_id, pw_field: pw}, timeout=15)
        return r.status_code < 400
    except Exception as e:  # noqa: BLE001
        print("[warn] 로그인 실패: %s: %s" % (type(e).__name__, str(e)[:150]))
        return False


def extract_revenue(data):
    """오늘 매출 3종 합계(카드+현금+기타) — 실측(parkStat.js)한 칸 이름 그대로. 하나라도 없으면 None(지어내지 않는다)."""
    fields = ("salesCardTodayAmt", "salesCashTodayAmt", "salesEtcTodayAmt")
    if not isinstance(data, dict) or any(f not in data for f in fields):
        return None
    try:
        return sum(int(str(data[f]).replace(",", "").strip()) for f in fields)
    except (ValueError, TypeError):
        return None


def fetch_today(session):
    """오늘 누적 parkStat 조회(과거 날짜 조회 API 없음 — 항상 "지금까지 오늘"). 성공 = {"revenue_krw":…, "raw":…}, 실패 = None."""
    time.sleep(CALL_GAP)
    url = _env("PARKING_STAT_URL", "http://ppark-wall.iptime.org:8280/io/getParkStat")
    park_id = _env("PARKING_PARK_ID", "1057")
    try:
        r = session.post(url, json={"searchParkId": park_id}, timeout=30)
        if r.status_code >= 400:
            print("[warn] 조회 실패: HTTP %d" % r.status_code)
            return None
        try:
            body = r.json()
        except ValueError:
            body = {"_raw_text": r.text[:5000]}
    except Exception as e:  # noqa: BLE001
        print("[warn] 조회 실패: %s: %s" % (type(e).__name__, str(e)[:150]))
        return None
    data = body.get("data") if isinstance(body, dict) else None
    return {"revenue_krw": extract_revenue(data), "raw": data if data is not None else body}


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

    session = requests.Session()
    if not _login(session, user_id, pw):
        with conn:
            db.meta_set(conn, "parking_last_failed", now + " 로그인 실패")
        conn.close()
        print("[blocked] 로그인 실패")
        return 2

    today = now[:10]
    d = fetch_today(session)
    ok = d is not None
    if ok:
        upsert(conn, [(today, d)], now)
        print("[ok] %s 적재 · revenue_krw=%s" % (today, d["revenue_krw"]))
    with conn:
        if ok:
            db.meta_set(conn, "parking_last_sync", now)
        db.meta_set(conn, "parking_last_failed", "" if ok else now + " 조회 실패")
    conn.close()
    print("[done] %s · %s" % (now, "정상" if ok else "실패"))
    return 0 if ok else 1


def selftest():
    assert extract_revenue({"salesCardTodayAmt": 1000, "salesCashTodayAmt": "2,000", "salesEtcTodayAmt": 0}) == 3000
    assert extract_revenue({"salesCardTodayAmt": 0}) is None, "칸이 빠지면 None"
    assert extract_revenue({"salesCardTodayAmt": "x", "salesCashTodayAmt": 0, "salesEtcTodayAmt": 0}) is None, "숫자 아니면 None"
    assert extract_revenue(None) is None

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
