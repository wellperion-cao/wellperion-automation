# -*- coding: utf-8 -*-
"""지출품의(구매요청) 원장 읽기 API — sync_proc.py 가 옮긴 proc_items 를 GAS 응답 모양 그대로 돌려준다.

  GET /api/proc/list?mode=active|all|ledger[&no=128][&status=승인][&images=0]
      응답 = {"ok":true,"mode":...,"count":N,"data":[...]}  — 품의 GAS list 와 같은 모양이다.
      화면이 주소만 바꾸면 그대로 읽히게 하려고 칸 이름을 새로 짓지 않았다.
      images=0 이면 이미지 칸을 빈 값으로 지워 보낸다(전량 1.29MB 중 1.1MB 가 이미지다 — 목록만 볼 땐 빼면 빠르다).
  GET /api/proc/health

★mode 의 뜻은 GAS 가 가른 대로 둔다(우리 기준을 새로 짓지 않는다 — INC-055 와 같은 실수를 피한다).
  active = 진행중 목록(2026-09-11 실측 21건 · 상태 정산·검토) · all = 지난 이력(326건 · 상태 승인·완료·미승인·캔슬·반려).
  두 목록은 시트 행이 겹치지 않는다 — GAS 의 all 은 active 를 포함하지 않는다.
  ledger = 둘을 합친 우리 원장 전체(347건). GAS 에 없는 이름이라 화면이 이걸 GAS 로 되물을 일이 없다.
거울에 아무것도 없으면 지어내지 않고 502 를 돌려준다 — 화면은 종전 GAS 로 조용히 돌아간다.

★화면은 건드리지 않았다(CFO 화면은 나우열M 소관). 이 파일은 통로만 낸다.
app.py 가 같은 폴더의 api_*.py 를 자동 등록한다 — app.py 본문은 건드리지 않는다.

자체점검: python3 api_proc.py --selftest  (같은 DB 의 tenant 'selftest' · 네트워크 없음)
"""
import json
import os
import sys

from fastapi import APIRouter, HTTPException, Request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sync_proc import db, load_env  # noqa: E402  — 같은 env·같은 DB

SOURCE = "sheet-mirror"
router = APIRouter(prefix="/api/proc")
load_env()


@router.get("/health")
def health():
    conn = db.connect(readonly=True)
    with conn:
        rows = conn.execute("SELECT src, status, COUNT(*) c FROM proc_items WHERE tenant_id=%s"
                            " GROUP BY src, status", (db.TENANT,)).fetchall()
        last = conn.execute("SELECT MAX(synced_at) s FROM proc_items WHERE tenant_id=%s", (db.TENANT,)).fetchone()
        meta = dict(conn.execute("SELECT k, v FROM sync_meta WHERE tenant_id=%s AND k LIKE 'proc_last%%'",
                                 (db.TENANT,)).fetchall())
    conn.close()
    return {"ok": True, "rows": sum(r["c"] for r in rows),
            "by_status": {"%s/%s" % (r["src"], r["status"] or "(빈칸)"): r["c"] for r in rows},
            "newest_synced_at": last["s"] if last else None,
            "last_sync_kst": meta.get("proc_last_sync"), "last_failed": meta.get("proc_last_failed") or "",
            "_source": SOURCE}


@router.get("/list")
def proc_list(request: Request):
    q = dict(request.query_params)
    mode = q.get("mode") or "active"
    where, args = ["tenant_id=%s"], [db.TENANT]
    if mode != "ledger":
        where.append("src=%s")
        args.append("all" if mode == "all" else "active")
    if q.get("no"):
        where.append("no=%s")
        args.append(str(q["no"]).strip())
    if q.get("status"):
        where.append("status=%s")
        args.append(str(q["status"]).strip())
    conn = db.connect(readonly=True)
    with conn:
        rows = conn.execute("SELECT data FROM proc_items WHERE %s ORDER BY row" % " AND ".join(where),
                            tuple(args)).fetchall()
        # 조건에 맞는 게 없는 것과 원장이 통째로 빈 것은 다르다 — 뒤엣것은 화면이 GAS 로 돌아가야 한다.
        total = rows and 1 or conn.execute("SELECT COUNT(*) FROM proc_items WHERE tenant_id=%s",
                                           (db.TENANT,)).fetchone()[0]
    conn.close()
    if not total:
        raise HTTPException(502, "품의 원장이 비어 있다 — sync_proc.py 를 먼저 돌린다")
    data = [json.loads(r["data"]) for r in rows]
    if q.get("images") == "0":
        data = [dict(d, 이미지="") for d in data]
    return {"ok": True, "mode": mode, "count": len(data), "data": data, "_source": SOURCE}


# ── 자체점검 ──────────────────────────────────────────────────────────────

def selftest():
    from sync_proc import upsert
    db.TENANT = "selftest"                   # 같은 DB · 다른 tenant — 실데이터는 한 줄도 안 건드린다
    conn = db.connect()
    db.init_schema(conn)

    class _Req:                              # FastAPI Request 대역 — 쿼리만 쓴다
        def __init__(self, q):
            self.query_params = q
    try:
        with conn:
            conn.execute("DELETE FROM proc_items WHERE tenant_id=%s", (db.TENANT,))
        upsert(conn, [{"row": 10, "번호": "1", "상태": "승인", "물품": "가", "이미지": "data:image/png;base64,AA"},
                      {"row": 11, "번호": "2", "상태": "완료", "물품": "나", "이미지": ""}], "t0", "all")
        upsert(conn, [{"row": 12, "번호": "", "상태": "검토", "물품": "다", "이미지": "http://x/y.png"}], "t0", "active")
        d = proc_list(_Req({"mode": "all"}))                     # GAS all = 지난 이력만(진행중은 안 낀다)
        assert d["count"] == 2 and [x["물품"] for x in d["data"]] == ["가", "나"], d
        d = proc_list(_Req({}))                                  # 기본 = active(진행중)
        assert d["count"] == 1 and d["data"][0]["물품"] == "다", d
        d = proc_list(_Req({"mode": "ledger"}))                  # 우리 원장 전체 = 둘의 합
        assert d["count"] == 3 and [x["물품"] for x in d["data"]] == ["가", "나", "다"], d
        d = proc_list(_Req({"no": "2", "mode": "all"}))
        assert d["count"] == 1 and d["data"][0]["물품"] == "나", d
        d = proc_list(_Req({"status": "검토", "mode": "ledger"}))
        assert d["count"] == 1 and d["data"][0]["물품"] == "다", d
        d = proc_list(_Req({"mode": "all", "images": "0"}))
        assert all(x["이미지"] == "" for x in d["data"]), "images=0 이면 이미지 칸이 빈다"
        d = proc_list(_Req({"mode": "all", "images": "1"}))
        assert d["data"][0]["이미지"].startswith("data:"), "기본은 원본 그대로"
        d = proc_list(_Req({"no": "없는번호", "mode": "all"}))   # 원장은 있는데 조건이 안 맞는 것 = 빈 목록
        assert d["count"] == 0 and d["ok"], d
        h = health()
        assert h["rows"] == 3 and h["by_status"]["all/승인"] == 1 and h["by_status"]["active/검토"] == 1, h
        with conn:
            conn.execute("DELETE FROM proc_items WHERE tenant_id=%s", (db.TENANT,))
        try:                                                     # 원장이 통째로 비면 502 — 화면이 GAS 로 돌아간다
            proc_list(_Req({"mode": "all"}))
            raise AssertionError("502 이어야 한다")
        except HTTPException as e:
            assert e.status_code == 502
    finally:
        with conn:
            conn.execute("DELETE FROM proc_items WHERE tenant_id=%s", (db.TENANT,))
        conn.close()
    print("selftest ok")
    return 0


if __name__ == "__main__":
    sys.exit(selftest() if "--selftest" in sys.argv else 2)
