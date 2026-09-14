# -*- coding: utf-8 -*-
"""지출품의(구매요청)·자산대장 시트 → 서버 PostgreSQL 원장 (읽기 전용 단방향) — AWS 이관 「매출·지출 원장」 단계.

sync_reception.py 와 같은 규칙이다. 화면이 이미 부르는 읽기 액션(list, mode=all)을 그대로 부르고
행 하나를 행 하나로 옮긴다 — 시트·GAS 는 한 줄도 쓰지 않는다.

sales_cache(sync_sales.py)와 무엇이 다른가: 저건 GAS 집계 응답을 통째로 담는 캐시라 「9월 지출 합계」
같은 덩어리만 있고 품의 한 건을 꺼낼 수 없다. 이 표는 행이 품의 한 건이라 번호·상태로 곧장 찾는다.

왜 만들었나(2026-09-11 실측): GAS list(mode=all)는 326행·1,291,203바이트·37.7초다. 그중 1,097,856바이트가
이미지(base64 68건·드라이브 주소 198건). 그 무게 때문에 큰 응답이 리다이렉트 왕복에서 끊겨 목록이 빈 손으로
돌아오는 날이 있었다(2026-09-11 21:0x 4회 연속). 원장이 서버에 있으면 그 조회가 로컬 SQL 이 된다.

★건드리지 않는 것: 매출 시트 보고(09:00·09:30 발송 배관)와 CFO 화면(나우열M 소관). 이 파일은 배관만 놓는다.

자산대장(2026-09-14 시토 · 배12615 CFO 요청서3 §3): GAS asset_list → proc_assets 표. 새 파일을 안 만든 이유 —
api_write.py MIRROR_SYNC 가 asset_issue·asset_del·asset_update·asset_label 뒤 이미 "sync_proc.py"(이 파일)를
예약해 둬서(3초 디바운스), main() 에 한 단계만 얹으면 그 관문을 그대로 탄다(품의 add·status 뒤 즉시 반영과 같은 값).

실행: python3 /srv/erp/api/sync_proc.py   (cron 10분 · /etc/cron.d/erp-proc-sync)
      python3 sync_proc.py --once        — cron 없이 한 번
자체점검: python3 sync_proc.py --selftest  (같은 DB 의 tenant 'selftest' · 네트워크 없음)
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sync_inquiries import db, load_env  # noqa: E402  — 같은 env·같은 DB

# 컬럼으로 빼는 칸 = 거르는 데 쓰는 것만. 나머지는 data 에 시트 머리글 그대로 남는다(칸 이름을 새로 짓지 않는다).
COLS = (("no", "번호"), ("ymd", "날짜"), ("requester", "요청자"), ("dept", "소속"),
        ("item", "물품"), ("status", "상태"))


def _kst_now():
    return time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(time.time() + 9 * 3600))


def gas_list(mode="all", timeout=180):
    """품의 목록 1회. 성공 시 행 목록, 실패 시 None(지어내지 않는다).

    POST + password 는 이 GAS 의 관문이다 — 화면(procCall)도 같은 값을 본문에 넣는다.
    timeout 이 큰 이유: 전량 조회 실측 37.7초(2026-09-11). 화면이 아니라 cron 이 기다린다."""
    url = os.environ.get("PROC_GAS_URL", "")
    if not url:
        raise SystemExit("PROC_GAS_URL 없음 — /srv/erp/api.env 를 확인")
    body = urllib.parse.urlencode({"action": "list", "mode": mode,
                                   "password": os.environ.get("SALES_GATE_PW", "")}).encode()
    try:
        req = urllib.request.Request(url, data=body, headers={"User-Agent": "wellperion-erp-api"})
        d = json.loads(urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8"))
    except Exception as e:
        print("[warn] 품의 목록 조회 실패: %s: %s" % (type(e).__name__, str(e)[:160]))
        return None
    if not isinstance(d, dict) or not d.get("ok") or not isinstance(d.get("data"), list):
        print("[warn] 품의 목록 응답이 ok 가 아니다: %s" % str(d)[:160])
        return None
    return d["data"]


def _price(v):
    """가격 칸은 숫자로 올 때도, '101,700' 처럼 올 때도, 빈칸일 때도 있다. 못 읽으면 0 — 원본은 data 에 그대로 남는다."""
    try:
        return int(float(str(v).replace(",", "").strip() or 0))
    except ValueError:
        return 0


def upsert(conn, rows, now, src="all"):
    """행 하나 = 품의 하나. 열쇠는 시트 행번호(row) — GAS status 액션이 쓰는 바로 그 값이다.

    src = 어느 목록에서 왔나(active=진행중 · all=지난 이력). 두 목록은 행이 겹치지 않는다(2026-09-11 실측).

    rows 는 항상 전량(gas_list 가 from/to 없이 부르는 mode=active/all) — 이번 회차에 없는 row 는 시트에서
    지워진 것이라 같은 src 안에서 지운다(품의 유령 행 수리 · 2026-09-14). ⚠️ from/to 로 범위를 잘라 받는
    호출(화면 mode=done 같은)을 여기 새로 연결한다면 부분 목록이라 이 삭제를 타면 안 된다 — 지우지 않는다."""
    n = 0
    row_nums = []
    with conn:
        for r in rows:
            try:
                row = int(r.get("row"))
            except (TypeError, ValueError):
                continue                      # row 없는 줄은 원장 열쇠가 없다 — 건너뛴다
            row_nums.append(row)
            vals = [str(r.get(col) or "").strip() for _, col in COLS]
            conn.execute(
                "INSERT INTO proc_items (tenant_id,row,src,no,ymd,requester,dept,item,status,price,data,synced_at)"
                " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
                " ON CONFLICT (tenant_id,row) DO UPDATE SET src=EXCLUDED.src, no=EXCLUDED.no, ymd=EXCLUDED.ymd,"
                " requester=EXCLUDED.requester, dept=EXCLUDED.dept, item=EXCLUDED.item, status=EXCLUDED.status,"
                " price=EXCLUDED.price, data=EXCLUDED.data, synced_at=EXCLUDED.synced_at",
                tuple([db.TENANT, row, src] + vals + [_price(r.get("가격")),
                                                      json.dumps(r, ensure_ascii=False), now]))
            n += 1
        # row_nums 가 비면 `<> ALL(빈 배열)` 이 항상 참이 되어 그 src 전체가 지워진다 — 반드시 건너뛴다.
        deleted = conn.execute(
            "DELETE FROM proc_items WHERE tenant_id=%s AND src=%s AND row <> ALL(%s)",
            (db.TENANT, src, row_nums)).rowcount if row_nums else 0
    return n, deleted


# 자산대장 — 컬럼으로 빼는 칸도 거르는 데 쓰는 것만(GAS assetRows_ 머리글 그대로 data 에 남는다).
ASSET_COLS = (("label", "라벨"), ("item", "품명"), ("req_no", "품의번호"), ("status", "상태"))


def gas_asset_list(timeout=60):
    """자산대장 전체 1회(assetList — 필터 없이 부른다). 성공 시 행 목록, 실패 시 None(지어내지 않는다)."""
    url = os.environ.get("PROC_GAS_URL", "")
    if not url:
        raise SystemExit("PROC_GAS_URL 없음 — /srv/erp/api.env 를 확인")
    body = urllib.parse.urlencode({"action": "asset_list", "password": os.environ.get("SALES_GATE_PW", "")}).encode()
    try:
        req = urllib.request.Request(url, data=body, headers={"User-Agent": "wellperion-erp-api"})
        d = json.loads(urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8"))
    except Exception as e:
        print("[warn] 자산대장 조회 실패: %s: %s" % (type(e).__name__, str(e)[:160]))
        return None
    if not isinstance(d, dict) or not d.get("ok") or not isinstance(d.get("data"), list):
        print("[warn] 자산대장 응답이 ok 가 아니다: %s" % str(d)[:160])
        return None
    return d["data"]


def upsert_assets(conn, rows, now):
    """행 하나 = 라벨 하나. 열쇠 = 시트 행번호(row) — upsert() 와 같은 규칙(유령 행은 이번 회차에 없으면 지운다).

    GAS assetDel 이 행을 실제로 지워 아래 행 번호가 밀린다 — 그래도 매 회차 전량을 이 규칙으로 다시 담기
    때문에 문제없다(proc_items 도 같은 전제)."""
    n = 0
    row_nums = []
    with conn:
        for r in rows:
            try:
                row = int(r.get("row"))
            except (TypeError, ValueError):
                continue
            row_nums.append(row)
            vals = [str(r.get(col) or "").strip() for _, col in ASSET_COLS]
            conn.execute(
                "INSERT INTO proc_assets (tenant_id,row,label,item,req_no,status,data,synced_at)"
                " VALUES (%s,%s,%s,%s,%s,%s,%s,%s)"
                " ON CONFLICT (tenant_id,row) DO UPDATE SET label=EXCLUDED.label, item=EXCLUDED.item,"
                " req_no=EXCLUDED.req_no, status=EXCLUDED.status, data=EXCLUDED.data, synced_at=EXCLUDED.synced_at",
                tuple([db.TENANT, row] + vals + [json.dumps(r, ensure_ascii=False), now]))
            n += 1
        deleted = conn.execute(
            "DELETE FROM proc_assets WHERE tenant_id=%s AND row <> ALL(%s)",
            (db.TENANT, row_nums)).rowcount if row_nums else 0
    return n, deleted


def main():
    load_env()
    conn = db.connect()
    db.init_schema(conn)                      # 멱등 — proc_items·proc_assets 표가 없으면 만든다
    now = _kst_now()
    done, deleted, failed = {}, {}, []
    for src in ("active", "all"):              # 두 목록은 겹치지 않는다 — 둘 다 받아야 원장이 온전해진다
        rows = gas_list(src)
        if rows is None:
            failed.append(src)
            continue
        if not rows:
            # 0건 보호 — sync_reception._replace 와 같은 이유(2026-09-03 실사고: GAS 가 권한 오류를 삼키고 빈 목록을 준다).
            cur = conn.execute("SELECT COUNT(*) FROM proc_items WHERE tenant_id=%s AND src=%s",
                               (db.TENANT, src)).fetchone()[0]
            print("[keep] %s — 원천 0건 응답, 원장 %d행 유지(조회 이상 의심)" % (src, cur))
            failed.append(src)
            continue
        done[src], deleted[src] = upsert(conn, rows, now, src)
    arows = gas_asset_list()
    if arows is None:
        failed.append("asset")
    elif not arows:
        cur = conn.execute("SELECT COUNT(*) FROM proc_assets WHERE tenant_id=%s", (db.TENANT,)).fetchone()[0]
        print("[keep] asset — 원천 0건 응답, 원장 %d행 유지(조회 이상 의심)" % cur)
        failed.append("asset")
    else:
        done["asset"], deleted["asset"] = upsert_assets(conn, arows, now)
    with conn:
        if done:
            db.meta_set(conn, "proc_last_sync", now)
            db.meta_set(conn, "proc_last_count", json.dumps(done))
        db.meta_set(conn, "proc_last_failed", ",".join(failed))
    conn.close()
    print("proc sync %s · 원장 반영 %s · 유령행 삭제 %s · 실패 %s" % (now, done or "없음", deleted or "없음", failed or "없음"))
    return 1 if failed else 0


def selftest():
    db.TENANT = "selftest"                    # 같은 DB · 다른 tenant — 실데이터는 한 줄도 안 건드린다
    conn = db.connect()
    db.init_schema(conn)
    try:
        with conn:
            conn.execute("DELETE FROM proc_items WHERE tenant_id=%s", (db.TENANT,))
            conn.execute("DELETE FROM proc_assets WHERE tenant_id=%s", (db.TENANT,))
        assert _price(101700) == 101700 and _price("101,700") == 101700 and _price("") == 0 and _price("싯가") == 0
        base = {"row": 375, "번호": "128", "날짜": "2026. 9. 1", "요청자": "탕청소", "소속": "시설",
                "물품": "락풍 3개", "상태": "정산", "가격": "101,700", "이미지": "data:image/jpeg;base64,AAA"}
        assert upsert(conn, [base, dict(base, row=376, 번호="", 상태="검토")], "t0", "active") == (2, 0)
        assert upsert(conn, [dict(base, row=3, 상태="완료")], "t0", "all") == (1, 0)
        assert upsert(conn, [{"물품": "row 없는 줄"}], "t0") == (0, 0), "row 없는 줄은 원장에 안 들어가고, 빈 배치라 지우지도 않는다"
        r = conn.execute("SELECT * FROM proc_items WHERE tenant_id=%s AND row=375", (db.TENANT,)).fetchone()
        assert r["no"] == "128" and r["status"] == "정산" and r["price"] == 101700 and r["item"] == "락풍 3개", dict(r)
        assert r["src"] == "active", dict(r)
        assert json.loads(r["data"])["이미지"].startswith("data:"), "원본 칸은 통째로 남는다"
        n, deleted = upsert(conn, [dict(base, 상태="완료", 가격=0)], "t1", "active")   # 같은 행이 두 번 들어오면 덮어쓴다
        assert n == 1 and deleted == 1, "row 376 이 이번 회차 active 목록에 없으니 유령 행으로 지워진다"
        r = conn.execute("SELECT status, price, synced_at FROM proc_items WHERE tenant_id=%s AND row=375",
                         (db.TENANT,)).fetchone()
        assert r["status"] == "완료" and r["price"] == 0 and r["synced_at"] == "t1", dict(r)
        assert conn.execute("SELECT 1 FROM proc_items WHERE tenant_id=%s AND row=376",
                            (db.TENANT,)).fetchone() is None, "지워진 유령 행이 남아 있다"
        n = conn.execute("SELECT COUNT(*) FROM proc_items WHERE tenant_id=%s", (db.TENANT,)).fetchone()[0]
        assert n == 2, "row 375(active)·row 3(all) 만 남는다"
        n = conn.execute("SELECT COUNT(*) FROM proc_items WHERE tenant_id=%s AND src='active'",
                         (db.TENANT,)).fetchone()[0]
        assert n == 1, "src 로 두 목록이 갈린다 — active 에는 375 만 남는다"
        # 자산대장 — GAS assetRows_ 그대로 온 행(라벨·품명·품의번호·상태 + row).
        albase = {"row": 2, "라벨": "WP26 0001", "품명": "노트북", "분류": "비품", "부서": "시설",
                  "위치": "1층", "관리자": "이가나", "취득일": "2026-09-01", "품의번호": "PR-1",
                  "부착": True, "부착일": "2026-09-02", "상태": "사용중"}
        assert upsert_assets(conn, [albase, dict(albase, row=3, 라벨="WP26 0002", 부착=False)], "t0") == (2, 0)
        r = conn.execute("SELECT * FROM proc_assets WHERE tenant_id=%s AND row=2", (db.TENANT,)).fetchone()
        assert r["label"] == "WP26 0001" and r["req_no"] == "PR-1" and r["status"] == "사용중", dict(r)
        assert json.loads(r["data"])["관리자"] == "이가나", "원본 칸은 통째로 남는다"
        n, adel = upsert_assets(conn, [dict(albase, 상태="불용")], "t1")   # row 3 이 이번 회차에 없다
        assert n == 1 and adel == 1, "row 3 이 유령 행으로 지워진다"
        r = conn.execute("SELECT status FROM proc_assets WHERE tenant_id=%s AND row=2", (db.TENANT,)).fetchone()
        assert r["status"] == "불용", dict(r)
        assert conn.execute("SELECT 1 FROM proc_assets WHERE tenant_id=%s AND row=3",
                            (db.TENANT,)).fetchone() is None, "지워진 유령 행이 남아 있다"
        assert upsert_assets(conn, [{"품명": "row 없는 줄"}], "t1") == (0, 0), "row 없는 줄은 안 담고, 빈 배치라 지우지도 않는다"
    finally:
        with conn:
            conn.execute("DELETE FROM proc_items WHERE tenant_id=%s", (db.TENANT,))
            conn.execute("DELETE FROM proc_assets WHERE tenant_id=%s", (db.TENANT,))
        conn.close()
    print("selftest ok")
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    sys.exit(main())
