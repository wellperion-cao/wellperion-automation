# -*- coding: utf-8 -*-
"""되밀기 워커 — 서버 원장 → GAS(시트) (배 960 레인 J · 2026-09-04 시토).

server 모드(origin_switch.py)에서 화면은 서버 원장에만 적고 즉시 ok 를 받는다 — GAS 왕복을 안 기다리니 응답이 빨라진다.
시트는 이 워커가 1분마다 채운다: gas_status='queued' 인 행을 raw_body(받은 본문 그대로)로 같은 GAS 에 POST 하고,
닿으면 pushed_at·gas_status·gas_response 를 적고 raw_body 를 지운다(사진·서명 base64 를 계속 이고 있지 않게).
성공 상태값은 이중기록 때와 같다(intake_log='200' · write_log='ok') — 대조(reconcile_dual_write.py)가 그대로 돈다.
실무진·기존 GAS 소비자(알림 트리거 등)는 시트가 계속 채워지므로 영향 0.

  못 닿으면      push_tries 를 올리며 5회까지 재시도 → 그 뒤엔 손을 뗀다(행은 queued 로 남아 헬스 unpushed 에 잡힌다)
  GAS 가 거부하면(ok:false) 되민 것으로 치되 gas-error 로 남긴다 — 재시도해도 같은 답이고, 시트엔 안 들어갔으니 사람이 봐야 한다
  둘 다              /srv/erp/status/pushback_failed.json + GET /api/intake/health 의 pushback.failed 에 뜬다
  거울               되민 쓰기가 거울(sync_*)을 더럽히면 배치 끝에 해당 동기화를 1회 돌린다(api_write 의 MIRROR_SYNC 그대로)

실행:     python3 /srv/erp/api/pushback.py      (cron 1분 · /etc/cron.d/erp-pushback)
자체점검: python3 pushback.py --selftest        (DB·네트워크 없음 — 판정만)
끝단점검: python3 pushback.py --e2e             (서버에서 · tenant 'selftest' 로 한 바퀴 돌리고 지운다 · 실데이터 폼 무관)
"""
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from api_intake import FORMS, PUSH_MAX_TRIES, gas_forward  # noqa: E402  — 전달·상한은 이중기록 때와 같은 것을 쓴다
from api_reception_ops import write_gas_key as _rc_gas_key  # noqa: E402
from api_write import MIRROR_SYNC, _SYNC_ARGS, _gas_key  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
BATCH = 100                       # 1분에 이만큼씩 — 밀려도 다음 분이 이어 받는다
STATUS_DIR = os.environ.get("ERP_STATUS_DIR", "/srv/erp/status")
FAILED_FILE = os.path.join(STATUS_DIR, "pushback_failed.json")
# 원장별 다른 것 세 가지: 시각 칸 이름 · 닿았을 때 적을 상태값 · gas_response 칸이 JSONB 인가(write_log 만).
LEDGERS = {"intake_log": {"ts": "received_at", "ok": "200", "jsonb": False},
           "write_log": {"ts": "at", "ok": "ok", "jsonb": True}}
UNPUSHED = "gas_status='queued' AND pushed_at IS NULL"
FAILED = ("(pushed_at IS NULL AND push_tries >= %d) OR (pushed_at IS NOT NULL AND gas_status='gas-error')"
          % PUSH_MAX_TRIES)


def dest_key(table, row):
    """이 행을 어느 GAS 로 되밀 것인가 — 이중기록 때 쓰던 목적지 판정 그대로(순서까지 같게)."""
    if table == "write_log":
        try:
            payload = json.loads(row["raw_body"] or "{}")
        except ValueError:
            payload = {}
        return _rc_gas_key(row["action"], payload) or _gas_key(row["action"])
    form = row["form"]
    return FORMS.get(form) or ("SELFTEST_PUSH_URL" if form == "selftest" else None)


def judge(table, status, resp):
    """(적을 상태값, 되민 것으로 칠까). GAS 가 200 이어도 ok:false 면 시트엔 안 들어갔다 — 사람이 볼 자리로 보낸다."""
    if status != "200":
        return "push-error:%s" % status, False
    try:
        data = json.loads(resp)
    except (ValueError, TypeError):
        data = None
    if isinstance(data, dict) and not data.get("ok", True):
        return "gas-error", True
    return LEDGERS[table]["ok"], True


def push_row(conn, table, row):
    """한 행을 되민다. 네트워크는 여기서만. 반환 = 되밀었나(True/False)."""
    spec = LEDGERS[table]
    key = dest_key(table, row)
    url = os.environ.get(key or "", "")
    if not url:
        status, resp = "error:no-url", "%s 없음 — /srv/erp/api.env" % (key or "목적지 미상")
    else:
        status, resp = gas_forward(url, (row["raw_body"] or "").encode("utf-8"))
    new_status, pushed = judge(table, status, resp)
    stored = json.dumps(resp, ensure_ascii=False)[:20000] if spec["jsonb"] else resp[:4000]
    with conn:
        if pushed:
            conn.execute("UPDATE %s SET gas_status=%%s, gas_response=%%s, pushed_at=%%s, push_tries=push_tries+1,"
                         " raw_body=NULL WHERE id=%%s" % table,
                         (new_status, stored, _now_kst(), row["id"]))
        else:
            conn.execute("UPDATE %s SET gas_status=%%s, gas_response=%%s, push_tries=push_tries+1 WHERE id=%%s" % table,
                         (new_status, stored, row["id"]))
    return pushed


def _now_kst():
    import time
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(time.time() + 9 * 3600))


def run(conn, limit=BATCH):
    """되밀 행을 훑는다. 반환 {pushed, failed, syncs}."""
    out = {"pushed": 0, "failed": 0, "syncs": set()}
    for table in LEDGERS:
        rows = conn.execute("SELECT * FROM %s WHERE %s AND push_tries < %%s ORDER BY id LIMIT %%s"
                            % (table, UNPUSHED), (PUSH_MAX_TRIES, limit)).fetchall()
        for row in rows:
            if push_row(conn, table, row):
                out["pushed"] += 1
                if table == "write_log" and row["action"] in MIRROR_SYNC:
                    out["syncs"].add(MIRROR_SYNC[row["action"]])
            else:
                out["failed"] += 1
    for script in out["syncs"]:      # 되민 쓰기가 시트를 바꿨으니 거울을 다시 뜬다(5분 cron 을 기다리지 않게)
        with open("/srv/erp/%s.log" % script[:-3], "a") as log:
            subprocess.Popen([sys.executable, os.path.join(HERE, script)] + _SYNC_ARGS.get(script, []),
                             stdout=log, stderr=subprocess.STDOUT)
    return out


def write_failed(conn, tenant):
    """사람이 봐야 하는 행만 파일 하나로 — 5회까지 못 닿은 행 + GAS 가 거부한 행. 없으면 count 0 으로 덮어쓴다.
    헬스(api_intake)와 같은 잣대·같은 tenant 로 센다 — 두 숫자가 어긋나면 사람이 못 믿는다."""
    rows = []
    for table, spec in LEDGERS.items():
        for r in conn.execute("SELECT id, %s AS at, gas_status, push_tries, gas_response FROM %s"
                              " WHERE tenant_id=%%s AND (%s) ORDER BY id DESC LIMIT 100"
                              % (spec["ts"], table, FAILED), (tenant,)).fetchall():
            rows.append({"ledger": table, "id": r["id"], "at": r["at"], "gas_status": r["gas_status"],
                         "tries": r["push_tries"], "detail": str(r["gas_response"] or "")[:300]})
    result = {"generated_at": _now_kst(), "count": len(rows), "max_tries": PUSH_MAX_TRIES,
              "note": "되밀기 실패 — 시트에 안 들어간 행. 원인을 고친 뒤 push_tries 를 0 으로 되돌리면 다시 되민다.",
              "rows": rows[:100]}
    os.makedirs(STATUS_DIR, exist_ok=True)
    tmp = FAILED_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
    os.replace(tmp, FAILED_FILE)
    return len(rows)


def main():
    from common import db  # noqa: PLC0415 — selftest 는 DB 없이 돌아야 한다
    conn = db.connect()
    out = run(conn)
    bad = write_failed(conn, db.TENANT)
    conn.close()
    if out["pushed"] or out["failed"] or bad:      # 1분마다 도는 cron — 할 일이 없으면 로그를 남기지 않는다
        print("되밀기 %s · 성공 %d · 실패 %d · 사람이 볼 행 %d" % (_now_kst(), out["pushed"], out["failed"], bad))
    return 0


def selftest():
    # 목적지 — 이중기록 때와 같은 GAS 로 간다(여기가 새면 시트가 엉뚱한 곳에 쌓인다)
    assert dest_key("intake_log", {"form": "inquiry"}) == "INTAKE_GAS_URL"
    assert dest_key("intake_log", {"form": "sunday"}) == "INSTRUCTOR_GAS_URL"
    assert dest_key("intake_log", {"form": "reception"}) == "RECEPTION_EXEC_URL"
    assert dest_key("intake_log", {"form": "selftest"}) == "SELFTEST_PUSH_URL"   # 시험 행은 시험 주소로만
    assert dest_key("write_log", {"action": "todo_add", "raw_body": '{"action":"todo_add"}'}) == "TODO_GAS_URL"
    assert dest_key("write_log", {"action": "member_owner_save", "raw_body": None}) == "FUNNEL_EXEC_URL"

    # 판정 — 200 이라도 ok:false 면 시트엔 없다. 못 닿은 건 재시도 대상(되민 것으로 치지 않는다).
    assert judge("intake_log", "200", '{"ok":true,"id":"L260908-101010"}') == ("200", True)
    assert judge("write_log", "200", '{"ok":true}') == ("ok", True)
    assert judge("write_log", "200", '{"ok":false,"error":"bad-token"}') == ("gas-error", True)
    assert judge("intake_log", "200", "<html>로그인 화면</html>") == ("200", True)   # JSON 아니면 GAS 판정 없음 → 닿은 것으로
    assert judge("intake_log", "error:URLError", "timed out") == ("push-error:error:URLError", False)
    assert judge("write_log", "500", "boom") == ("push-error:500", False)

    # 상한·조건문 — 헬스(api_intake)와 같은 잣대로 세야 숫자가 어긋나지 않는다
    from api_intake import _PUSH_FAILED, _UNPUSHED
    assert UNPUSHED == _UNPUSHED and FAILED == _PUSH_FAILED and PUSH_MAX_TRIES == 5
    assert "push_tries >= 5" in FAILED
    print("selftest ok")
    return 0


def e2e():
    """서버에서 한 바퀴 — 스위치 server(selftest 폼만) → 공개 POST → queued 행 → 되밀기 → 메아리 도착 → 행 삭제·스위치 원복.
    실데이터 폼·시트는 건드리지 않는다(목적지 = 이 프로세스가 띄운 127.0.0.1 메아리 서버)."""
    import threading
    import urllib.request
    from http.server import BaseHTTPRequestHandler, HTTPServer

    from common import db  # noqa: PLC0415
    import origin_switch

    marker = "레인J-%s" % _now_kst()
    got = {}

    class Echo(BaseHTTPRequestHandler):
        def do_POST(self):
            got["body"] = self.rfile.read(int(self.headers.get("Content-Length", 0))).decode("utf-8", "replace")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok":true,"id":"ECHO"}')

        def log_message(self, *a):
            pass

    echo = HTTPServer(("127.0.0.1", 0), Echo)
    threading.Thread(target=echo.serve_forever, daemon=True).start()
    os.environ["SELFTEST_PUSH_URL"] = "http://127.0.0.1:%d/" % echo.server_port

    path = origin_switch.PATH                     # 스위치를 잠깐 켠다 — 끝나면 원래 파일로 되돌린다
    before = open(path, encoding="utf-8").read() if os.path.exists(path) else None
    conf = json.loads(before) if before else {}
    conf["selftest"] = "server"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(conf, f, ensure_ascii=False, indent=1)
    steps = []
    try:
        req = urllib.request.Request("http://127.0.0.1:8001/api/intake/selftest",
                                     data=json.dumps({"marker": marker}, ensure_ascii=False).encode("utf-8"),
                                     headers={"Content-Type": "text/plain;charset=utf-8"}, method="POST")
        with urllib.request.urlopen(req, timeout=20) as r:
            resp = json.loads(r.read().decode("utf-8"))
        assert resp.get("ok") and resp.get("mode") == "server", resp
        steps.append("POST 즉시 ok · mode=server · 접수번호 %s" % resp.get("id"))

        conn = db.connect()
        row = conn.execute("SELECT id, gas_status, raw_body, pushed_at FROM intake_log WHERE tenant_id='selftest'"
                           " ORDER BY id DESC LIMIT 1").fetchone()
        assert row and row["gas_status"] == "queued" and marker in (row["raw_body"] or ""), dict(row or {})
        steps.append("원장 %d 행 queued · 본문 보관됨(GAS 대기 없음)" % row["id"])

        out = run(conn)
        assert marker in got.get("body", ""), "메아리가 못 받음: %s" % got
        after = conn.execute("SELECT gas_status, pushed_at, raw_body FROM intake_log WHERE id=%s",
                             (row["id"],)).fetchone()
        assert after["gas_status"] == "200" and after["pushed_at"] and after["raw_body"] is None, dict(after)
        steps.append("되밀기 1회 → 같은 본문 도착 · 상태 200 · pushed_at %s · 본문 지움" % after["pushed_at"])
        steps.append("배치 결과 성공 %d · 실패 %d" % (out["pushed"], out["failed"]))

        with conn:
            conn.execute("DELETE FROM intake_log WHERE tenant_id='selftest'")
        steps.append("시험 행 삭제(tenant selftest) — 실데이터 무관")
        conn.close()
    finally:
        echo.shutdown()
        try:                          # 도중에 엎어져도 시험 행을 남기지 않는다 — 1분 cron 이 헛되밀지 않게
            c2 = db.connect()
            with c2:
                c2.execute("DELETE FROM intake_log WHERE tenant_id='selftest' AND gas_status='queued'")
            c2.close()
        except db.Error:
            pass
        if before is None:
            os.remove(path)
        else:
            with open(path, "w", encoding="utf-8") as f:
                f.write(before)
    print("e2e ok\n  " + "\n  ".join("· " + s for s in steps))
    return 0


if __name__ == "__main__":
    sys.exit(selftest() if "--selftest" in sys.argv else e2e() if "--e2e" in sys.argv else main())
