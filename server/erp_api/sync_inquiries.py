# -*- coding: utf-8 -*-
"""문의 시트 → 서버 SQLite 미러 동기화 (읽기 전용 단방향).

원천은 이미 프로덕션에서 도는 GAS 엔드포인트(scripts/cpo_report.py FUNNEL_EXEC_URL)를
그대로 재사용한다 — 시트 파싱을 새로 포팅하지 않는다(드리프트 0). 시트·GAS 는 절대 쓰지 않는다.

실행: python3 /srv/erp/api/sync_inquiries.py   (cron 5분)
자체점검: python3 sync_inquiries.py --selftest  (임시 DB 로 upsert 로직만 확인, 네트워크 없음)
"""
import json
import os
import sqlite3
import sys
import time
import urllib.parse
import urllib.request

DB_PATH = os.environ.get("ERP_DB", "/srv/erp/erp.db")
ENV_FILE = os.environ.get("ERP_API_ENV", "/srv/erp/api.env")

# (type, GAS action, 추가 파라미터) — 화면들이 쓰는 액션 그대로.
SOURCES = [
    ("멤버십", "member_inquiry_list", None),
    ("성인강습", "lesson_inquiry_list", {"type": "성인강습"}),
    ("유소년강습", "lesson_inquiry_list", {"type": "유소년강습"}),
]

SCHEMA = """
CREATE TABLE IF NOT EXISTS inquiries (
  id        TEXT PRIMARY KEY,
  type      TEXT NOT NULL,
  row_key   TEXT,
  name      TEXT,
  phone     TEXT,
  status    TEXT,
  timestamp TEXT,
  data      TEXT NOT NULL,
  synced_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_inq_type_ts ON inquiries(type, timestamp);
CREATE TABLE IF NOT EXISTS sync_meta (k TEXT PRIMARY KEY, v TEXT);
"""


def load_env():
    """/srv/erp/api.env 를 읽어 os.environ 에 채운다(비밀값은 저장소에 두지 않는다)."""
    try:
        with open(ENV_FILE, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    except OSError:
        pass


def gas_get(action, params, timeout=60):
    """GAS GET 1회. 성공 시 dict, 실패 시 None(지어내지 않는다)."""
    url = os.environ.get("FUNNEL_EXEC_URL", "")
    if not url:
        raise SystemExit("FUNNEL_EXEC_URL 없음 — %s 를 확인" % ENV_FILE)
    q = {"action": action}
    if params:
        q.update(params)
    req = urllib.request.Request(
        url + "?" + urllib.parse.urlencode(q), headers={"User-Agent": "wellperion-erp-api"}
    )
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


def replace_type(conn, kind, rows, now):
    """한 유형을 통째로 갈아끼운다 — 시트가 정본이라 미러는 원천과 같아야 한다.
    호출부가 '조회 성공 + 행 있음'을 이미 확인한 뒤에만 부른다(빈 값으로 지우지 않기 위해)."""
    recs = []
    for r in rows:
        key = str(r.get("rowKey") or r.get("rowIndex") or "")
        if not key:
            continue
        recs.append((
            "%s|%s" % (kind, key), kind, key,
            r.get("name"), r.get("phone"), r.get("status"), r.get("timestamp"),
            json.dumps(r, ensure_ascii=False), now,
        ))
    with conn:
        conn.execute("DELETE FROM inquiries WHERE type=?", (kind,))
        conn.executemany(
            "INSERT OR REPLACE INTO inquiries"
            " (id,type,row_key,name,phone,status,timestamp,data,synced_at)"
            " VALUES (?,?,?,?,?,?,?,?,?)", recs)
    return len(recs)


def main():
    load_env()
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    # 서버 시계는 UTC — 저장소·화면이 다 KST 라 여기서 맞춰 적는다(읽는 쪽이 헷갈리지 않게).
    now = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(time.time() + 9 * 3600))
    total, failed = 0, []
    for kind, action, params in SOURCES:
        data = gas_get(action, params)
        rows = (data or {}).get("data")
        if not isinstance(rows, list) or not rows:
            failed.append(kind)  # 실패 — 기존 미러를 그대로 둔다(빈 값으로 덮지 않음)
            continue
        n = replace_type(conn, kind, rows, now)
        total += n
        print("[ok] %s %d건" % (kind, n))
    with conn:
        conn.execute("INSERT OR REPLACE INTO sync_meta VALUES ('last_sync',?)", (now,))
        conn.execute("INSERT OR REPLACE INTO sync_meta VALUES ('last_failed',?)", (",".join(failed),))
    print("[done] %s · 갱신 %d건 · 실패 %s" % (now, total, failed or "없음"))
    return 1 if failed else 0


def selftest():
    conn = sqlite3.connect(":memory:")
    conn.executescript(SCHEMA)
    rows = [{"rowKey": "a", "name": "홍길동", "timestamp": "2026-01-01"},
            {"rowKey": "b", "name": "김철수", "timestamp": "2026-02-01"},
            {"name": "키없음"}]
    assert replace_type(conn, "멤버십", rows, "t0") == 2, "rowKey 없는 행은 버린다"
    assert replace_type(conn, "멤버십", rows[:1], "t1") == 1, "같은 유형은 통째로 교체"
    assert conn.execute("SELECT COUNT(*) FROM inquiries").fetchone()[0] == 1
    replace_type(conn, "성인강습", rows, "t1")
    assert conn.execute("SELECT COUNT(*) FROM inquiries WHERE type='멤버십'").fetchone()[0] == 1, \
        "다른 유형 교체가 남의 유형을 지우면 안 된다"
    print("selftest ok")
    return 0


if __name__ == "__main__":
    sys.exit(selftest() if "--selftest" in sys.argv else main())
