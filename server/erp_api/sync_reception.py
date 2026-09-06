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
    # [2026-09-05 시토 · 검수 C1] 통째 DELETE→INSERT 를 upsert 로 바꿨다. 배984 부터 접수·습득물이 서버 DB 에만 적히는데
    # 통째 갈아끼우면 시트에 없는 서버 원장 행이 5분 뒤 사라진다. 시트 행은 갱신·추가만 하고, 서버가 적은 행은 그대로 둔다.
    # 키 = cols[1](reception_items.reg_id · lost_found.found_id · hold_items.intake_row) — 표 정의(schema.sql PK) 와 같은 순서.
    key = cols[1]
    sets = ", ".join("%s=EXCLUDED.%s" % (c, c) for c in cols[2:])
    # [2026-09-06 시토 · 배1090 장애] 서버가 편집한 행(data._server_edited 표식 · api_reception /update)은 시트 값으로
    # 되돌리지 않는다 — 시트는 동결된 과거 기록이라 서버보다 새로울 수 없다. 표식 없는 행만 종전대로 갱신.
    guard = " WHERE (%s.data::jsonb ->> '_server_edited') IS NULL" % table if "data" in cols else ""
    with conn:
        conn.executemany(
            "INSERT INTO %s (%s) VALUES (%s) ON CONFLICT (tenant_id, %s) DO UPDATE SET %s%s"
            % (table, ",".join(cols), ",".join(["%s"] * len(cols)), key, sets, guard), recs)
    return len(recs)


def replace_board(conn, rows, now):
    # 테스트/더미 접수는 미러에 안 싣는다(AWS DB 더미 전수정리 · 2026-09-05) — 시트 자체는 손대지 않는다.
    recs = [(db.TENANT, str(r["regId"]), r.get("category"), r.get("dept"), r.get("status"), r.get("createdAt"),
             json.dumps(r, ensure_ascii=False), now) for r in rows if r.get("regId") and not db.is_test_payload(r)]
    return _replace(conn, "reception_items", ["tenant_id", "reg_id", "category", "dept", "status", "created_at", "data", "synced_at"], recs)


def replace_lost(conn, rows, now):
    recs = [(db.TENANT, str(r["foundId"]), r.get("status"), r.get("createdAt"), json.dumps(r, ensure_ascii=False), now)
            for r in rows if r.get("foundId") and not db.is_test_payload(r)]
    return _replace(conn, "lost_found", ["tenant_id", "found_id", "status", "created_at", "data", "synced_at"], recs)


def replace_hold(conn, rows, done_keys, now):
    """done_keys 가 None(완료키 조회 실패)이면 종전 행의 done 을 이어받는다 — 완료분이 갑자기 되살아나지 않게.
    [2026-09-05 배 1039-D] 서버 hold_complete(api_reception.py)가 done 을 직접 True 로 적으므로, done_keys 가
    있어도 종전 값이 True 면 그대로 유지한다(sticky — 한 번 완료면 되돌리지 않음). GAS(휴회접수 시트)가 아직
    모르는 완료를 5분 동기화가 되돌리는 사고를 막는다."""
    prev = {r["intake_row"]: r["done"] for r in conn.execute("SELECT intake_row, done FROM hold_items WHERE tenant_id=%s", (db.TENANT,))}
    recs = []
    for r in rows:
        key = str(r.get("intakeRow") or "")
        if not key:
            continue
        prev_done = bool(prev.get(key, False))
        done = prev_done if done_keys is None else (prev_done or hold_key(r) in done_keys)
        recs.append((db.TENANT, key, r.get("status"), done, r.get("appliedAt"), json.dumps(r, ensure_ascii=False), now))
    return _replace(conn, "hold_items", ["tenant_id", "intake_row", "status", "done", "applied_at", "data", "synced_at"], recs)


def _server_edited_snapshot(conn):
    """서버 편집 표식(_server_edited) 행의 status·dept 스냅샷 — 동기화 전후 비교용(배1090·INC-056 ③정합 자가검사).
    _replace() 의 WHERE 가드가 이 행들을 시트 값으로 안 덮어야 정상 — 바뀌면 가드가 뚫린 것."""
    rows = conn.execute("SELECT reg_id, status, dept FROM reception_items WHERE tenant_id=%s"
                        " AND (data::jsonb ->> '_server_edited') IS NOT NULL", (db.TENANT,)).fetchall()
    return {r["reg_id"]: (r["status"], r["dept"]) for r in rows}


def _pushback_backlog(conn, minutes=30):
    """접수 되밀기(write_log reg_* 큐)가 minutes 분 넘게 안 나갔으면 그 건수 — pushback.py 1분 cron 이 죽었다는 신호
    (배1090·INC-056 ③정합 자가검사)."""
    cutoff = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(time.time() + 9 * 3600 - minutes * 60))
    return conn.execute("SELECT COUNT(*) FROM write_log WHERE tenant_id=%s AND action LIKE 'reg_%%'"
                        " AND gas_status='queued' AND pushed_at IS NULL AND at < %s", (db.TENANT, cutoff)).fetchone()[0]


def guard_alert(conn, drifted, backlog):
    """상태가 나쁨으로 바뀌거나 나쁨의 내용이 달라질 때만 보낸다(sync_members.alert_on_change 와 같은 규칙 —
    5분마다 같은 말 반복 금지). 반환 = 보낼 문구(없으면 None)."""
    fp = "d=%s|b=%d" % (",".join(drifted), backlog)
    bad = bool(drifted) or backlog > 0
    prev = db.meta_get(conn, "reception_guard_alert_fp") or ""
    if fp == prev:
        return None
    with conn:
        db.meta_set(conn, "reception_guard_alert_fp", fp)
    if bad:
        lines = ["⚠ 종합접수처 정합 이상(INC-056)"]
        if drifted:
            lines.append("   서버 편집 표식 행이 동기화에 되돌아감: %s" % ", ".join(drifted[:10]))
        if backlog:
            lines.append("   시트 되밀기(pushback) 30분 이상 밀림: %d건" % backlog)
        lines.append("   👉 시토 확인")
        return "\n".join(lines)
    return "✅ 종합접수처 정합 정상 복귀" if prev else None


def main():
    load_env()
    conn = db.connect()
    db.init_schema(conn)                      # 멱등 — 새 표 3개가 없으면 만든다
    pv = os.environ.get("RECEPTION_PV", "")
    now = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(time.time() + 9 * 3600))   # 서버 시계 UTC → KST
    counts, failed = {}, []

    before_edit = _server_edited_snapshot(conn)   # ③정합 자가검사 — 동기화 전
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

    # ③정합 자가검사(배1090·INC-056) — 매 동기화 뒤: (a) 서버 편집 행이 시트 값으로 되돌아갔는지 (b) 시트 되밀기가 밀렸는지
    after_edit = _server_edited_snapshot(conn)
    drifted = sorted(k for k, v in before_edit.items() if after_edit.get(k) != v)
    backlog = _pushback_backlog(conn)
    msg = guard_alert(conn, drifted, backlog)
    if msg:
        from sync_members import _tell_gm  # noqa: PLC0415 — 새 발신기 안 만들고 기존 헬퍼 재사용
        print("[guard-alert]", "보냄" if _tell_gm(msg) else "못 보냄(TG 키 없음)", "—", msg.splitlines()[0])
    else:
        print("[guard] 정합 정상 — 되돌아간 행 0 · 되밀기 밀림 0")

    conn.close()
    print("[done] %s · %s · 실패 %s" % (now, counts, failed or "없음"))
    return 1 if failed else 0


def selftest():
    db.TENANT = "selftest"                      # 같은 DB · 다른 tenant — 실데이터는 한 줄도 안 건드린다
    conn = db.connect()
    db.init_schema(conn)
    assert js_hash("abc") == "96354", js_hash("abc")          # JS ((h<<5)-h+c)|0 과 같은 값
    assert js_hash("휴회완료키") == js_hash("휴회완료키")
    board = [{"regId": "R1", "category": "컴플레인 접수", "status": "접수"}, {"regId": "R2", "status": "완료"},
              {"content": "id없음"}, {"regId": "R3", "content": "테스트 중 입니다."}]
    hold = [{"intakeRow": 2, "name": "홍 길동", "phone": "010-1234-5678", "start": "2026-09-01"}, {"intakeRow": 3, "name": "김철수"}]
    try:
        assert replace_board(conn, board, "t0") == 2, "regId 없는 행·테스트 더미 행은 버린다"
        assert replace_board(conn, board[:1], "t1") == 1, "통째로 교체"
        assert replace_lost(conn, [{"foundId": "F1"}, {}, {"foundId": "F2", "itemDesc": "테스트입니다"}], "t1") == 1, "더미 습득물은 버린다"
        assert replace_hold(conn, hold, {js_hash("01012345678|20260901|홍길동")}, "t1") == 2
        done = dict(conn.execute("SELECT intake_row, done FROM hold_items WHERE tenant_id=%s", (db.TENANT,)).fetchall())
        assert done == {"2": True, "3": False}, done
        replace_hold(conn, hold, None, "t2")          # 완료키 조회 실패 → 종전 done 유지
        done = dict(conn.execute("SELECT intake_row, done FROM hold_items WHERE tenant_id=%s", (db.TENANT,)).fetchall())
        assert done == {"2": True, "3": False}, done

        # ③정합 자가검사(배1090·INC-056) — 서버 편집 표식 행이 동기화로 되돌아가면 잡아낸다.
        edited = [{"regId": "R1", "category": "컴플레인 접수", "status": "완료", "dept": "운영부", "_server_edited": "t1"}]
        assert replace_board(conn, edited, "t2") == 1
        snap1 = _server_edited_snapshot(conn)
        assert snap1 == {"R1": ("완료", "운영부")}, snap1
        sheet_stale = [{"regId": "R1", "category": "컴플레인 접수", "status": "접수", "dept": ""}]   # 시트의 옛 값
        assert replace_board(conn, sheet_stale, "t3") == 1
        assert _server_edited_snapshot(conn) == snap1, "가드가 안 먹으면 R1 이 시트 옛 값(접수)으로 되돌아간다"

        assert _pushback_backlog(conn) == 0
        with conn:
            conn.execute("INSERT INTO write_log (tenant_id, at, action, payload, user_email, gas_status, raw_body)"
                         " VALUES (%s,%s,%s,%s,%s,'queued',%s)",
                         (db.TENANT, "2000-01-01 00:00:00", "reg_update", "{}", "", "{}"))
        assert _pushback_backlog(conn) == 1

        with conn:
            db.meta_set(conn, "reception_guard_alert_fp", "")
        assert guard_alert(conn, [], 0) is None                       # 정상 · 첫 기록 — 알림 없음
        msg = guard_alert(conn, ["R1"], 1)
        assert msg and "R1" in msg and "1건" in msg, msg               # 나쁨으로 바뀜 — 알림
        assert guard_alert(conn, ["R1"], 1) is None                    # 같은 나쁨 반복 — 재알림 금지
        assert guard_alert(conn, [], 0) == "✅ 종합접수처 정합 정상 복귀"
    finally:
        with conn:
            for t in ("reception_items", "lost_found", "hold_items", "write_log", "sync_meta"):
                conn.execute("DELETE FROM %s WHERE tenant_id=%%s" % t, (db.TENANT,))
        conn.close()
    print("selftest ok")
    return 0


if __name__ == "__main__":
    sys.exit(selftest() if "--selftest" in sys.argv else main())
