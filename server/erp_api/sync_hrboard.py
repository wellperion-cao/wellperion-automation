# -*- coding: utf-8 -*-
"""인사 스케줄보드·온보딩 명단 → 서버 board_cache 미러 (배12615 · GM 지시 2026-09-15 「남은 것도 다 이관」).

인사 화면 4장(chro/hub/schedule.html·schedule-mobile.html·onboarding.html·onboarding-self.html)이
GAS(HR_GAS_URL)를 직접 부르는 마지막 자리였다. 그 중 비밀번호 없이 읽히는 액션 2개만 미러한다
(그 밖 — db 읽기·onbo-checkin-read·onbo-self-read 등 — 은 비밀번호·PIN 이 필요해 GAS 그대로 둔다):
  schedboard-list     → HR_SCHEDBOARD  (근무표 보드 63행 · roster·holidays·ann 동봉 · 화면이 j 그대로 소비)
  onbo-active-names   → HR_ONBO_NAMES  (온보딩 진행중 명단)

저장은 sync_board.py 의 board_cache 표·put() 을 그대로 쓴다(새 표 안 만든다) — 읽기는
기존 api_board.py 의 GET /api/board/{key} 가 그대로 내준다(키가 다를 뿐 같은 거울, 값은 GAS 응답 통째).
CHECK_GAS_URL(action=board) 이 아니라 HR_GAS_URL 에 다른 액션을 POST 해야 해서 sync_board.gas_board()는
못 쓴다 — 이 파일이 자체 POST 호출(gas_hr)을 갖는다. 재시도 규칙(3회·백오프)은 sync_inquiries 값을 그대로 쓴다.

실행: python3 /srv/erp/api/sync_hrboard.py   (cron 5분 · /etc/cron.d/erp-hrboard-sync)
자체점검: python3 sync_hrboard.py --selftest  (같은 DB 의 tenant 'selftest' · 네트워크 없음)
"""
import json
import os
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sync_board import put  # noqa: E402 — 저장은 한 곳(board_cache)만
from sync_inquiries import GAS_BACKOFF_SEC, GAS_NO_RETRY_CODES, GAS_TRIES, db, load_env  # noqa: E402 — 재시도 규칙 공용

HR_ACTIONS = {
    "HR_SCHEDBOARD": "schedboard-list",
    "HR_ONBO_NAMES": "onbo-active-names",
}


def gas_hr(action, timeout=60):
    """HR_GAS_URL 에 action 하나 POST(비밀번호 없이 읽히는 액션 한정). 성공 시 dict, 실패 시 None(지어내지 않는다)."""
    url = os.environ.get("HR_GAS_URL", "")
    if not url:
        raise SystemExit("HR_GAS_URL 없음 — /srv/erp/api.env 를 확인")
    body = json.dumps({"action": action}).encode("utf-8")
    why = ""
    for attempt in range(1, GAS_TRIES + 1):
        try:
            req = urllib.request.Request(url, data=body, method="POST",
                                         headers={"Content-Type": "text/plain;charset=utf-8",
                                                  "User-Agent": "wellperion-erp-api"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = json.loads(r.read().decode("utf-8", "replace"))
            if not isinstance(data, dict) or not data.get("ok"):
                why = "응답 ok=false"
            else:
                if attempt > 1:
                    print("[ok] %s — %d번째 시도에 성공(앞선 실패는 일시 오류)" % (action, attempt))
                return data
        except Exception as e:
            code = getattr(e, "code", None)
            why = "%s: %s" % (type(e).__name__, str(e)[:120])
            if code in GAS_NO_RETRY_CODES:
                print("[warn] %s 조회 실패(재시도 안 함): %s" % (action, why))
                return None
        if attempt < GAS_TRIES:
            time.sleep(GAS_BACKOFF_SEC[attempt - 1])
    print("[warn] %s 조회 실패 — %d번 다 실패: %s" % (action, GAS_TRIES, why))
    return None


def main():
    load_env()
    conn = db.connect()
    db.init_schema(conn)                        # 멱등 — board_cache 표가 없으면 만든다
    now = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(time.time() + 9 * 3600))   # 서버는 UTC · 기록은 KST
    n_ok, failed = 0, []
    for key, action in HR_ACTIONS.items():
        data = gas_hr(action)
        if data is None:
            failed.append(key)                  # 실패 — 기존 미러를 그대로 둔다
            continue
        put(conn, key, data, now)
        n_ok += 1
    with conn:
        db.meta_set(conn, "hrboard_last_sync", now)
        db.meta_set(conn, "hrboard_last_failed", ",".join(failed))
    conn.close()
    print("[done] %s · 갱신 %d/%d건 · 실패 %s" % (now, n_ok, len(HR_ACTIONS), failed or "없음"))
    return 1 if failed else 0


def selftest():
    db.TENANT = "selftest"                       # 같은 DB · 다른 tenant — 실데이터는 한 줄도 안 건드린다
    conn = db.connect()
    db.init_schema(conn)
    try:
        with conn:
            conn.execute("DELETE FROM board_cache WHERE tenant_id=%s", (db.TENANT,))
        put(conn, "HR_SCHEDBOARD", {"ok": True, "data": {"a": {"2026-09-01": "휴"}}}, "t0")
        put(conn, "HR_SCHEDBOARD", {"ok": True, "data": {"a": {"2026-09-01": "휴"}, "b": {}}}, "t1")
        r = conn.execute("SELECT data, synced_at FROM board_cache WHERE tenant_id=%s AND key='HR_SCHEDBOARD'",
                         (db.TENANT,)).fetchone()
        assert r["synced_at"] == "t1" and len(json.loads(r["data"])["data"]) == 2, "같은 열쇠는 덮어쓴다"
    finally:
        with conn:
            conn.execute("DELETE FROM board_cache WHERE tenant_id=%s", (db.TENANT,))
        conn.close()
    print("selftest ok")
    return 0


if __name__ == "__main__":
    sys.exit(selftest() if "--selftest" in sys.argv else db.run_sync("hrboard", main))
