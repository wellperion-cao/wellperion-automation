# -*- coding: utf-8 -*-
"""종합접수처 시트 → 서버 PostgreSQL 미러 동기화 (읽기 전용 단방향) — 배 922 · AWS 전환 1호.

sync_inquiries.py 와 같은 규칙. 원천은 종합접수처_현황.html 이 부르는 GAS 액션 그대로 —
  접수 GAS(RECEPTION_EXEC_URL): reg_dashboard(접수 8종 보드+점수판 all+담당자) · reg_scoreboard(week/month) · lf_list · hold_done_keys
  회원 GAS(FUNNEL_EXEC_URL):    member_hold_intake_list(휴회)
시트·GAS 는 절대 쓰지 않는다. 조회 실패면 그 표는 그대로 둔다(빈 값으로 덮지 않음 — INC-052 재발 시 화면이 안 빈다).
휴회 행에는 hold_done_keys 를 조인해 done 을 박는다(화면 _holdKey · GAS _vFp_ 와 같은 해시).

실행: python3 /srv/erp/api/sync_reception.py   (cron 5분 · /etc/cron.d/erp-reception-sync)
자체점검: python3 sync_reception.py --selftest  (같은 DB 의 tenant 'selftest' · 네트워크 없음)
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
import gas_key  # noqa: E402  — 접수 GAS 게이트 열쇠(RECEPTION_TOKEN). 비어 있으면 무동작.


def gas_get(url_key, action, params=None, timeout=90):
    """GAS GET 1회 — sync_inquiries.gas_get 과 같되 원천 URL 을 고른다(접수 GAS / 회원 GAS)."""
    url = os.environ.get(url_key, "")
    if not url:
        raise SystemExit("%s 없음 — /srv/erp/api.env 를 확인" % url_key)
    q = {"action": action}
    q.update(params or {})
    q = gas_key.sign_params(url_key, q)   # lf_list 는 GATED — 스위치가 켜지면 열쇠가 있어야 통과한다
    req = urllib.request.Request(url + "?" + urllib.parse.urlencode(q), headers={"User-Agent": "wellperion-erp-api"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print("[warn] %s 조회 실패: %s: %s" % (action, type(e).__name__, str(e)[:120]))
        return None
    if not data.get("ok"):
        print("[warn] %s 응답 ok=false" % action)
        return None
    return data


def js_hash(s):
    """화면 _wHash · GAS _vFp_ 와 같은 32비트 문자열 해시 — 휴회 완료키 조인용."""
    h = 0
    for ch in s:
        h = ((h << 5) - h + ord(ch)) & 0xFFFFFFFF
    return str(h - 0x100000000 if h >= 0x80000000 else h)


def hold_key(r):
    ph = re.sub(r"\D", "", str(r.get("phone") or ""))
    ymd = re.sub(r"\D", "", str(r.get("start") or ""))[:8]
    nm = re.sub(r"\s", "", str(r.get("name") or ""))
    return js_hash("%s|%s|%s" % (ph, ymd, nm))


def _replace(conn, table, cols, recs):
    """한 표를 통째로 갈아끼운다(시트가 정본). 호출부가 조회 성공을 확인한 뒤에만 부른다.
    [2026-09-04 시우] 0건 보호 — GAS 가 권한 오류를 삼키고 ok:true·빈 목록을 돌려주는 날(2026-09-03 실사고:
    스프레드시트 스코프 누락으로 reg_list 137건 → 0건)에는 거울까지 비어 버렸다. 새 목록이 비었는데 거울에
    행이 남아 있으면 지난 값을 그대로 둔다 — 원천이 진짜로 0건이 되는 경우는 없다(접수 원장은 지우지 않는다)."""
    if not recs:
        cur = conn.execute("SELECT COUNT(*) FROM %s WHERE tenant_id=%%s" % table, (db.TENANT,)).fetchone()[0]
        if cur > 0:
            print("[keep] %s — 원천 0건 응답, 거울 %d행 유지(원천 조회 이상 의심)" % (table, cur))
            return cur
    with conn:
        conn.execute("DELETE FROM %s WHERE tenant_id=%%s" % table, (db.TENANT,))
        conn.executemany("INSERT INTO %s (%s) VALUES (%s)" % (table, ",".join(cols), ",".join(["%s"] * len(cols))), recs)
    return len(recs)


def replace_board(conn, rows, now):
    recs = [(db.TENANT, str(r["regId"]), r.get("category"), r.get("dept"), r.get("status"), r.get("createdAt"),
             json.dumps(r, ensure_ascii=False), now) for r in rows if r.get("regId")]
    return _replace(conn, "reception_items", ["tenant_id", "reg_id", "category", "dept", "status", "created_at", "data", "synced_at"], recs)


def replace_lost(conn, rows, now):
    recs = [(db.TENANT, str(r["foundId"]), r.get("status"), r.get("createdAt"), json.dumps(r, ensure_ascii=False), now)
            for r in rows if r.get("foundId")]
    return _replace(conn, "lost_found", ["tenant_id", "found_id", "status", "created_at", "data", "synced_at"], recs)


def replace_hold(conn, rows, done_keys, now):
    """done_keys 가 None(완료키 조회 실패)이면 종전 행의 done 을 이어받는다 — 완료분이 갑자기 되살아나지 않게."""
    prev = {}
    if done_keys is None:
        prev = {r["intake_row"]: r["done"] for r in conn.execute("SELECT intake_row, done FROM hold_items WHERE tenant_id=%s", (db.TENANT,))}
    recs = []
    for r in rows:
        key = str(r.get("intakeRow") or "")
        if not key:
            continue
        done = (hold_key(r) in done_keys) if done_keys is not None else bool(prev.get(key, False))
        recs.append((db.TENANT, key, r.get("status"), done, r.get("appliedAt"), json.dumps(r, ensure_ascii=False), now))
    return _replace(conn, "hold_items", ["tenant_id", "intake_row", "status", "done", "applied_at", "data", "synced_at"], recs)


def main():
    load_env()
    conn = db.connect()
    db.init_schema(conn)                      # 멱등 — 새 표 3개가 없으면 만든다
    pv = os.environ.get("RECEPTION_PV", "")
    now = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(time.time() + 9 * 3600))   # 서버 시계 UTC → KST
    counts, failed = {}, []

    dash = gas_get("RECEPTION_EXEC_URL", "reg_dashboard", {"pv": pv, "period": "all"})
    if dash and isinstance(dash.get("board"), list):
        counts["board"] = replace_board(conn, dash["board"], now)
        with conn:
            db.meta_set(conn, "reception_scoreboard_all", json.dumps(dash.get("scoreboard") or {"ok": True, "board": []}, ensure_ascii=False))
            db.meta_set(conn, "reception_staff_names", json.dumps(dash.get("staffNames") or [], ensure_ascii=False))
    else:
        failed.append("board")
    for p in ("week", "month"):
        sb = gas_get("RECEPTION_EXEC_URL", "reg_scoreboard", {"period": p})
        if sb:
            with conn:
                db.meta_set(conn, "reception_scoreboard_" + p, json.dumps(sb, ensure_ascii=False))
        else:
            failed.append("scoreboard_" + p)

    lf = gas_get("RECEPTION_EXEC_URL", "lf_list")
    if lf and isinstance(lf.get("data"), list):
        counts["lost"] = replace_lost(conn, lf["data"], now)
    else:
        failed.append("lost")

    hold = gas_get("FUNNEL_EXEC_URL", "member_hold_intake_list")
    if hold and isinstance(hold.get("data"), list):
        dk = gas_get("RECEPTION_EXEC_URL", "hold_done_keys")
        done_keys = set(dk["keys"]) if dk and isinstance(dk.get("keys"), list) else None
        if done_keys is None:
            failed.append("hold_done_keys")
        counts["hold"] = replace_hold(conn, hold["data"], done_keys, now)
    else:
        failed.append("hold")

    with conn:
        db.meta_set(conn, "reception_last_sync", now)
        db.meta_set(conn, "reception_last_failed", ",".join(failed))
    conn.close()
    print("[done] %s · %s · 실패 %s" % (now, counts, failed or "없음"))
    return 1 if failed else 0


def selftest():
    db.TENANT = "selftest"                      # 같은 DB · 다른 tenant — 실데이터는 한 줄도 안 건드린다
    conn = db.connect()
    db.init_schema(conn)
    assert js_hash("abc") == "96354", js_hash("abc")          # JS ((h<<5)-h+c)|0 과 같은 값
    assert js_hash("휴회완료키") == js_hash("휴회완료키")
    board = [{"regId": "R1", "category": "컴플레인 접수", "status": "접수"}, {"regId": "R2", "status": "완료"}, {"content": "id없음"}]
    hold = [{"intakeRow": 2, "name": "홍 길동", "phone": "010-1234-5678", "start": "2026-09-01"}, {"intakeRow": 3, "name": "김철수"}]
    try:
        assert replace_board(conn, board, "t0") == 2, "regId 없는 행은 버린다"
        assert replace_board(conn, board[:1], "t1") == 1, "통째로 교체"
        assert replace_lost(conn, [{"foundId": "F1"}, {}], "t1") == 1
        assert replace_hold(conn, hold, {js_hash("01012345678|20260901|홍길동")}, "t1") == 2
        done = dict(conn.execute("SELECT intake_row, done FROM hold_items WHERE tenant_id=%s", (db.TENANT,)).fetchall())
        assert done == {"2": True, "3": False}, done
        replace_hold(conn, hold, None, "t2")          # 완료키 조회 실패 → 종전 done 유지
        done = dict(conn.execute("SELECT intake_row, done FROM hold_items WHERE tenant_id=%s", (db.TENANT,)).fetchall())
        assert done == {"2": True, "3": False}, done
    finally:
        with conn:
            for t in ("reception_items", "lost_found", "hold_items", "sync_meta"):
                conn.execute("DELETE FROM %s WHERE tenant_id=%%s" % t, (db.TENANT,))
        conn.close()
    print("selftest ok")
    return 0


if __name__ == "__main__":
    sys.exit(selftest() if "--selftest" in sys.argv else main())
